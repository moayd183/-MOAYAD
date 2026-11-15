"""Regression tests for annual year sampling and signed difference visualization."""
from datetime import datetime, timezone
from io import BytesIO
import numpy as np
from PIL import Image
import pytest
from backend.app.models import SearchRequest
from backend.app.services.spherex import balanced_year_sample, search_spherex
from backend.app.services.science import render_signed_difference_png


def record(y, i):
    return {'date': f'{y}-01-{i:02d}T00:00:00Z', 'obs_id':f'{y}_{i}', 'detector':1, 'access_url': f'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/{y}_{i}.fits'}


def test_year_sample_preserves_later_year_and_limits_count():
    # Previously the first 6/48 exposures from a single year dominated.
    rows = [record(2025, i) for i in range(1, 13)] + [record(2026, i) for i in range(1, 13)]
    sampled=balanced_year_sample(rows, 6)
    assert len(sampled)==6
    assert sum(r['date'].startswith('2025') for r in sampled)==3
    assert sum(r['date'].startswith('2026') for r in sampled)==3


def test_sample_handles_single_year_and_missing_dates():
    rows=[record(2025, i) for i in range(1, 5)] + [{'date':None,'obs_id':'undated'}]
    sample=balanced_year_sample(rows, 3)
    assert len(sample)==3
    assert {r['obs_id'] for r in sample} <= {r['obs_id'] for r in rows}


@pytest.mark.asyncio
async def test_real_spherex_search_reports_and_includes_both_years(monkeypatch):
    from backend.app.services import spherex
    dates=[datetime(y,1,4,tzinfo=timezone.utc) for y in [2025,2026]]
    mjds=[(d-datetime(1858,11,17,tzinfo=timezone.utc)).total_seconds()/86400 for d in dates]
    async def fake_get(url,params=None,max_bytes=None):return b'not-used'
    monkeypatch.setattr(spherex,'get_bytes',fake_get)
    def rows(payload):
        collection={'collection':None}
        return [dict(obs_id=f'obs{i}_{j}', obs_collection='spherex_dr1', s_ra='12.1',s_dec='2.1',
              t_min=str(mjds[i]),energy_bandpassname='D2',
              access_url=f'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/obs{i}_{j}.fits')
              for i in range(2) for j in range(30)]
    monkeypatch.setattr(spherex,'parse_votable',rows)
    res=await search_spherex(SearchRequest(ra=12.1,dec=2.1,collections=['spherex_dr1'],max_records=10))
    assert res['years_available']==['2025','2026']
    assert res['year_counts']=={'2025':30,'2026':30}
    assert res['count']==10 and res['truncated']
    assert sum(x['date'][:4]=='2026' for x in res['observations'])==5


def test_signed_difference_shows_both_directions():
    a=np.array([[-9.,0.,9.],[0.,0.,0.]])
    image=Image.open(BytesIO(render_signed_difference_png(a,np.ones_like(a,dtype=bool)))).convert('RGB')
    neg=image.getpixel((0,0));zero=image.getpixel((1,0));pos=image.getpixel((2,0))
    assert neg[2]>neg[0] and pos[0]>pos[2]
    assert zero==(25,29,45)


def test_signed_difference_rejects_no_finite_pixels():
    with pytest.raises(ValueError,match='No scientifically usable'):render_signed_difference_png(np.array([[float('nan')]]))
