"""SkyShift final regressions: user-reported upstream HTTP 422, annual FITS fallback,
publication-safe chronological differences, and secure record provenance.
All network fixtures are deliberately synthetic; never advertise them as NASA observations.
"""
import time
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import main as api
from backend.app.services import spherex
from backend.app.services import remote
from backend.app.services.remote import UpstreamError


@pytest.mark.asyncio
async def test_upstream_422_keeps_status_and_does_not_retry(monkeypatch):
    seen = []
    transport = httpx.MockTransport(lambda req: (seen.append(str(req.url)), httpx.Response(422, text='Invalid image cutout'))[1])
    real = httpx.AsyncClient
    monkeypatch.setattr(remote.httpx, 'AsyncClient', lambda **kwargs: real(transport=transport, **kwargs))
    with pytest.raises(UpstreamError) as err:
        await remote.get_bytes('https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/test.fits?center=1,2&size=10arcmin')
    assert err.value.status_code == 422
    assert 'IRSA' not in str(err.value) or 'Upstream HTTP 422' in str(err.value)
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_cutout_422_falls_back_same_target_no_fabrication(monkeypatch, tmp_path):
    monkeypatch.setattr(spherex, 'FRAMES_DIR', tmp_path)
    seen = []
    async def fake_get(url, spherex_only=False):
        seen.append(url)
        if 'size=10.' in url:
            raise UpstreamError('Upstream HTTP 422', 422)
        return b'SIMPLE  ' + b' ' * 80
    monkeypatch.setattr(spherex, 'get_bytes', fake_get)
    rec = {'obs_id':'IRSA-001', 'collection':'spherex_dr1',
           'access_url':'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/obs.fits',
           'data_mode':'real'}
    key, path, meta = await spherex.download_frame(rec, 133.8, -7.2, 10.)
    assert path.read_bytes().startswith(b'SIMPLE')
    assert len(seen) == 2
    assert all('center=133.800000000%2C-7.200000000' in url for url in seen)
    assert 'size=5.' in seen[1]
    assert meta['requested_fov_arcmin'] == 10
    assert meta['actual_fov_arcmin'] == 5
    assert meta['warning']
    _, _, cached = await spherex.download_frame(rec, 133.8, -7.2, 10.)
    assert cached == meta and len(seen) == 2


@pytest.mark.asyncio
async def test_cutout_422_all_sizes_fail_explicitly(monkeypatch, tmp_path):
    monkeypatch.setattr(spherex, 'FRAMES_DIR', tmp_path)
    attempts=[]
    async def always_bad(url, spherex_only=False):
        attempts.append(url)
        raise UpstreamError('Upstream HTTP 422', 422)
    monkeypatch.setattr(spherex,'get_bytes',always_bad)
    rec={'obs_id':'bad','collection':'spherex_dr1','access_url':
        'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/bad.fits','data_mode':'real'}
    with pytest.raises(UpstreamError, match='could not generate') as exc:
        await spherex.download_frame(rec,2,3,10)
    assert exc.value.status_code==422
    assert len(attempts)==4
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_non_422_does_not_retry_smaller_cutout(monkeypatch, tmp_path):
    monkeypatch.setattr(spherex,'FRAMES_DIR',tmp_path)
    attempts=[]
    async def denied(url,spherex_only=False):
        attempts.append(url)
        raise UpstreamError('Upstream HTTP 403',403)
    monkeypatch.setattr(spherex,'get_bytes',denied)
    rec={'obs_id':'bad','collection':'spherex_dr1','access_url':
        'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/bad.fits','data_mode':'real'}
    with pytest.raises(UpstreamError) as exc:
        await spherex.download_frame(rec,2,3,10)
    assert exc.value.status_code==403
    assert len(attempts)==1


def _indexed_records(monkeypatch):
    monkeypatch.setattr(api,'OBSERVATION_INDEX',{})
    request_id='a'*32
    for year in [2025, 2026]:
        for n in [0,1,2]:
            rec={'search_request_id':request_id,'obs_id':f'{year}-{n}',
                 'collection':'spherex_dr1' if year==2025 else 'spherex_qr3',
                 'date':f'{year}-07-{n+10:02d}T00:00:00Z',
                 'access_url':f'https://irsa.ipac.caltech.edu/ibe/data/spherex/{year}/{n}.fits',
                 'detector':2,'em_min_m':1.2e-6,'em_max_m':1.3e-6,'data_mode':'real'}
            key=request_id+'|'+rec['obs_id']+'|'+rec['access_url']
            api.OBSERVATION_INDEX[key]={'record':rec,'search_ra':133.8,'search_dec':-7.2,
                 'search_fov':10,'seen_at':time.time()}
    return request_id


def _annual_payload(request_id):
    return dict(search_request_id=request_id,year_a=2025,year_b=2026,
                ra=133.8,dec=-7.2,fov_arcmin=10)


def test_year_compare_fallback_after_upstream_422_and_science_mismatch(monkeypatch):
    request_id=_indexed_records(monkeypatch)
    visited=[]
    async def fake_build(rec, ra, dec, fov):
        visited.append(rec['obs_id'])
        if rec['obs_id'] in ('2025-0','2026-0'):
            raise UpstreamError('Upstream HTTP 422',422)
        band=1.6 if rec['obs_id']=='2026-1' else 1.24
        return {'frame_id': rec['obs_id'], 'provenance':{'observation':rec},
                'science':{'spectral_center':[band]},
                'preview_url':'/api/spherex/frames/'+rec['obs_id']+'/preview'}
    monkeypatch.setattr(api,'_build_registered_frame',fake_build)
    response=TestClient(api.app).post('/api/spherex/years/compare',json=_annual_payload(request_id))
    assert response.status_code==200,response.text
    out=response.json()
    assert out['status']=='ok'
    assert out['years']==[2025,2026]
    assert out['frames'][0]['provenance']['observation']['date'].startswith('2025')
    assert out['frames'][1]['provenance']['observation']['date'].startswith('2026')
    assert out['spectrally_comparable_at_cutout_center'] is True
    assert len(out['attempts'])==2
    assert visited==['2025-0','2025-1','2026-0','2026-1','2026-2']


def test_year_compare_no_valid_2026_returns_no_fake_pair(monkeypatch):
    request_id=_indexed_records(monkeypatch)
    async def fake_build(rec,ra,dec,fov):
        if rec['date'].startswith('2026'):
            raise UpstreamError('HTTP 422',422)
        return {'frame_id':rec['obs_id'],'provenance':{'observation':rec},
                'science':{'spectral_center':[1.2]}}
    monkeypatch.setattr(api,'_build_registered_frame',fake_build)
    result=TestClient(api.app).post('/api/spherex/years/compare',json=_annual_payload(request_id))
    assert result.status_code==200
    data=result.json()
    assert data['status']=='no_usable_pair'
    assert len(data['frames'])==1
    assert all(a['year']=='2026' for a in data['attempts'])
    assert data['data_mode']=='unavailable'


def test_year_compare_requires_current_authenticated_sia_records(monkeypatch):
    request_id=_indexed_records(monkeypatch)
    bad=_annual_payload(request_id)
    bad['ra']=150.0
    response=TestClient(api.app).post('/api/spherex/years/compare',json=bad)
    assert response.status_code==422
    assert 'No real dated observation' in response.text
    bad=_annual_payload(request_id)
    bad['year_b']=2025
    assert TestClient(api.app).post('/api/spherex/years/compare',json=bad).status_code==422


def test_difference_uses_true_chronological_order_even_if_payload_reversed(monkeypatch, tmp_path):
    first=tmp_path/'2025.fits';first.write_bytes(b'A')
    second=tmp_path/'2026.fits';second.write_bytes(b'B')
    frames={'a'*64:(second,{'observation':{'date':'2026-09-01T00:00:00Z'}}),
            'b'*64:(first,{'observation':{'date':'2025-06-01T00:00:00Z'}})}
    monkeypatch.setattr(api,'load_frame',lambda key:frames[key])
    monkeypatch.setattr(api,'open_science',lambda p:{'year':int(p.stem)})
    def fake_compare(a,b,method):
        assert a['year']==2025 and b['year']==2026
        import numpy as np
        return {'image':np.array([[1.]]),'mask':np.array([[True]]),'note':'Chronological verified'}
    monkeypatch.setattr(api,'compare',fake_compare)
    monkeypatch.setattr(api,'render_signed_difference_png',lambda data,mask:b'PNG')
    response=TestClient(api.app).post('/api/analysis/compare',json={
        'frame_a':'a'*64,'frame_b':'b'*64,'method':'difference'})
    assert response.status_code==200,response.text
    data=response.json()
    assert data['source_frames']==['b'*64,'a'*64]
    assert data['observation_dates']==['2025-06-01T00:00:00Z','2026-09-01T00:00:00Z']
    assert data['color_legend']['positive'].startswith('red')


def test_difference_rejects_same_frame():
    response=TestClient(api.app).post('/api/analysis/compare',json={
        'frame_a':'f'*64,'frame_b':'f'*64,'method':'difference'})
    assert response.status_code==422
    assert 'distinct' in response.text


def test_bad_redirect_url_port_blocked():
    with pytest.raises(ValueError):
        remote.validated_url('https://irsa.ipac.caltech.edu:8080/ibe/data/spherex/record.fits')
