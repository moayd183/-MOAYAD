import io
import numpy as np
from PIL import Image
import pytest
from backend.app.services.science import render_png, ScienceDependencyMissing, require_science


def test_preview_uses_only_valid_scientific_pixels():
    arr=np.arange(100,dtype=float).reshape(10,10)
    arr[2,2]=np.nan
    mask=np.ones((10,10),dtype=bool)
    mask[1,1]=False
    image=Image.open(io.BytesIO(render_png(arr,mask)))
    assert image.size==(10,10)
    assert image.getpixel((1,1))==0
    assert image.getpixel((2,2))==0


def test_all_invalid_pixels_fail_not_fabricate():
    with pytest.raises(ValueError):render_png(np.full((10,10),np.nan))


def test_optional_science_dependency_explicitly_reported():
    try:require_science()
    except ScienceDependencyMissing as e:
        assert 'Astropy' in str(e)
