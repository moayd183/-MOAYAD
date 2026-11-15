"""Ensure the central wavelength is sampled at the actual target position.
Isolated lightweight stubs let this regression run without optional Astropy.
"""
import sys
import types
import numpy as np
from backend.app.services import science


def test_spectrum_at_target_uses_sky_to_pixel_not_center(monkeypatch):
    astropy=types.ModuleType('astropy');astropy.__path__=[]
    coords=types.ModuleType('astropy.coordinates')
    coords.SkyCoord=lambda **kw:kw
    units=types.ModuleType('astropy.units')
    units.deg=1.0
    monkeypatch.setitem(sys.modules,'astropy',astropy)
    monkeypatch.setitem(sys.modules,'astropy.coordinates',coords)
    monkeypatch.setitem(sys.modules,'astropy.units',units)
    class Spatial:
        def world_to_pixel(self,c):
            assert c['ra']==33.1 and c['dec']==-4.2
            return np.array([16.2]),np.array([7.3])
    class Spectral:pass
    monkeypatch.setattr(science,'_sample_wavelength',lambda w,x,y:[x,y])
    data={'wcs':Spatial(),'spectral_wcs':Spectral(),'spectral_center':[99.,99.]}
    assert science.spectrum_at_target(data,33.1,-4.2)==[16.2,7.3]


def test_spectrum_at_target_does_not_invent_missing_wave():
    assert science.spectrum_at_target({'wcs':object(),'spectral_wcs':None,'spectral_center':None},10,20) is None


def test_render_png_rejects_blank_fits():
    import pytest
    with pytest.raises(ValueError,match='scientifically usable'):
        science.render_png(np.full((3,3),np.nan))
