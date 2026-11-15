"""Regression tests for real-user FITS frame/build HTTP 500 caused by ndarray rounding."""
import sys
import time
import types

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app import main as api
from backend.app.services.science import scalar_wcs_pixel


@pytest.mark.parametrize('value,expected', [
    (3.126, 3.126),
    (np.float64(3.126), 3.126),
    (np.array(3.126), 3.126),
    (np.array([3.126]), 3.126),
    (np.array([[3.126]]), 3.126),
])
def test_scalar_wcs_pixel_normalizes_numpy_values(value, expected):
    result = scalar_wcs_pixel(value, 'x')
    assert isinstance(result, float)
    assert result == expected


@pytest.mark.parametrize('value', [
    np.array([1., 2.]),
    np.array([]),
    np.array([np.nan]),
    np.array([np.inf]),
    'not a number',
])
def test_scalar_wcs_pixel_rejects_ambiguous_or_invalid_values(value):
    with pytest.raises(ValueError, match='FITS WCS'):
        scalar_wcs_pixel(value, 'y')


@pytest.mark.parametrize('pixel_x,expected_status', [
    (np.array([2.346]), 200),
    (np.array([2.346, 3.247]), 422),
])
def test_frame_build_numpy_wcs_projection_no_500(monkeypatch, tmp_path, pixel_x, expected_status):
    # Stub only the astronomy dependencies and network; exercise the actual HTTP route.
    astropy = types.ModuleType('astropy')
    astropy.__path__ = []
    coords = types.ModuleType('astropy.coordinates')
    coords.SkyCoord = lambda **kwargs: kwargs
    units = types.ModuleType('astropy.units')
    units.deg = 1.0
    monkeypatch.setitem(sys.modules, 'astropy', astropy)
    monkeypatch.setitem(sys.modules, 'astropy.coordinates', coords)
    monkeypatch.setitem(sys.modules, 'astropy.units', units)

    record = {
        'search_request_id': 'regression-test',
        'obs_id': 'verified-observation',
        'access_url': 'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/frame.fits',
    }
    index_key = 'regression-test|verified-observation|' + record['access_url']
    monkeypatch.setitem(api.OBSERVATION_INDEX, index_key, {
        'record': record, 'search_ra': 133.81890825, 'search_dec': -7.247048,
        'search_fov': 10.0, 'seen_at': time.time(),
    })

    science_path = tmp_path / 'frame.fits'
    science_path.write_bytes(b'FITS stub for isolated route regression test')
    async def fake_download(*args, **kwargs):
        return 'regression-frame-id', science_path, {'observation': record}
    class WCSStub:
        def world_to_pixel(self, coord):
            return pixel_x, np.array([4.567])
    def fake_open_science(path):
        return {'wcs': WCSStub(), 'image': np.ones((10, 10))}
    monkeypatch.setattr(api, 'download_frame', fake_download)
    monkeypatch.setattr(api, 'open_science', fake_open_science)
    monkeypatch.setattr(api, 'preview_details', lambda parsed: {'shape': [10, 10]})
    response = TestClient(api.app).post('/api/spherex/frames/build', json={
        'observation': record, 'ra': 133.81890825,
        'dec': -7.247048, 'fov_arcmin': 10.0,
    })
    assert response.status_code == expected_status, response.text
    if expected_status == 200:
        assert response.json()['science']['target_pixel'] == [2.35, 4.57]
        assert response.json()['data_mode'] == 'real'
    else:
        assert response.json()['status'] == 'input_error'
