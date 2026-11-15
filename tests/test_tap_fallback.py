"""Mocked TAP fallback contracts: real archive only, no made-up success."""
import pytest
from backend.app.models import SearchRequest
from backend.app.services.remote import UpstreamError
from backend.app.services import spherex


@pytest.mark.asyncio
async def test_sia_502_uses_verified_irsa_tap(monkeypatch):
    calls = []
    csv_data = ('uri,time_bounds_lower,energy_bandpassname\n'
                'ibe/data/spherex/dr1/level2/2025W18_1B/1/level2_002_2D1_spx.fits,2025-08-01T12:30:00,D1\n')
    async def mock_fetch(url, params=None, max_bytes=None):
        calls.append((url, params))
        if url == spherex.SIA_ENDPOINT:
            raise UpstreamError('Astronomy service unavailable after retries: HTTP 502')
        if url == spherex.TAP_ENDPOINT:
            return csv_data.encode()
        raise AssertionError('unexpected upstream')
    monkeypatch.setattr(spherex, 'get_bytes', mock_fetch)
    result = await spherex.search_spherex(SearchRequest(ra=100, dec=-10, collections=['spherex_dr1']))
    assert result['status'] == 'ok'
    assert result['count'] == 1
    record = result['observations'][0]
    assert record['data_mode'] == 'real'
    assert record['date'].startswith('2025-08-01')
    assert record['detector'] == 1
    assert record['source'].endswith('(SIA fallback)')
    assert calls[1][0] == spherex.TAP_ENDPOINT
    assert "CONTAINS(POINT('ICRS', 100.000000000, -10.000000000), p.poly)" in calls[1][1]['QUERY']
    assert calls[1][1]['FORMAT'] == 'CSV'


@pytest.mark.asyncio
async def test_both_archive_services_fail_without_fake_records(monkeypatch):
    async def fail(*args, **kwargs):
        raise UpstreamError('Astronomy service unavailable after retries: HTTP 502')
    monkeypatch.setattr(spherex, 'get_bytes', fail)
    result = await spherex.search_spherex(SearchRequest(ra=200, dec=20, collections=['spherex_qr3']))
    assert result['status'] == 'upstream_error'
    assert result['count'] == 0 and result['observations'] == []
    assert len(result['errors']) == 1
    assert 'tap_error' in result['errors'][0]


def test_tap_rejects_unknown_urls_and_releases():
    good = {'time_bounds_lower': '2025-08-01T12:30:00', 'energy_bandpassname': 'D1'}
    for bad in ('https://evil.example/bad.fits', '//evil.example/x',
                'ibe/data/spherex/qr3/level2/thing.fits',
                'ibe/data/spherex/dr1/dark/secrets'):
        assert spherex._tap_record({**good, 'uri': bad}, 'spherex_dr1') is None


def test_tap_does_not_invent_unverified_time():
    row = {'uri': 'ibe/data/spherex/dr1/level2/obs_2D1_.fits',
           'time_bounds_lower': 'UNKNOWN', 'energy_bandpassname': 'D1'}
    rec = spherex._tap_record(row, 'spherex_dr1')
    assert rec['date'] is None and rec['t_min'] is None


@pytest.mark.asyncio
async def test_tap_deep_coverage_not_assumed(monkeypatch):
    async def fail(*args, **kwargs):
        raise UpstreamError('Astronomy service unavailable after retries: HTTP 502')
    monkeypatch.setattr(spherex, 'get_bytes', fail)
    result = await spherex.search_spherex(SearchRequest(ra=125, dec=10, collections=['spherex_dr1_deep']))
    assert result['status'] == 'upstream_error'
    assert result['count'] == 0


@pytest.mark.asyncio
async def test_retry_reports_real_http_status(monkeypatch):
    import httpx
    from backend.app.services import remote
    transport = httpx.MockTransport(lambda req: httpx.Response(502, text='Proxy Error'))
    original = httpx.AsyncClient
    monkeypatch.setattr(remote.httpx, 'AsyncClient', lambda **kw: original(transport=transport, **kw))
    with pytest.raises(UpstreamError, match=r'HTTP 502 \\(irsa.ipac.caltech.edu\\)'):
        await remote.get_bytes('https://irsa.ipac.caltech.edu/SIA')
