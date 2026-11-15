"""Optional Astropy, Reproject and scientific computations. No invented spectra."""
from io import BytesIO
import warnings
import numpy as np
from PIL import Image


class ScienceDependencyMissing(RuntimeError):
    pass


def scalar_wcs_pixel(value, axis):
    """Return one finite WCS pixel coordinate, accepting Astropy NumPy scalars/arrays.

    An array with multiple pixels is not a scalar target position: do not silently
    take its first element, as that could misidentify the target on an image.
    """
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'FITS WCS returned an invalid {axis} pixel coordinate.') from exc
    if array.size != 1:
        raise ValueError(f'FITS WCS returned {array.size} {axis} pixel coordinates; expected exactly one.')
    pixel = float(array.reshape(-1)[0])
    if not np.isfinite(pixel):
        raise ValueError(f'FITS WCS returned a non-finite {axis} pixel coordinate.')
    return pixel



def _sample_wavelength(wcs, x: float, y: float):
    """Sample approximate SPHEREx WAVE-TAB wavelength/bandwidth in *micrometers*.

    IRSA documents this alternate FITS WCS for visualization; science-grade
    flux analysis needs the calibrated per-pixel CWAVE/CBAND calibration.
    """
    import astropy.units as u
    world = wcs.pixel_to_world_values(float(x), float(y))
    if not isinstance(world, (tuple, list)) or len(world) < 2:
        return None
    axis_units = wcs.world_axis_units
    if len(axis_units) < 2 or not axis_units[0] or not axis_units[1]:
        return None
    wave = (float(np.asarray(world[0]).item()) * u.Unit(axis_units[0])).to(u.um).value
    bandwidth = (float(np.asarray(world[1]).item()) * u.Unit(axis_units[1])).to(u.um).value
    if not (np.isfinite(wave) and np.isfinite(bandwidth) and wave > 0 and bandwidth > 0):
        return None
    return [float(wave), float(bandwidth)]


def spectrum_at_target(data: dict, ra: float, dec: float):
    """Use the user's sky position, not an arbitrary pixel, for wavelength QA."""
    if data.get('spectral_wcs') is None or data.get('wcs') is None:
        return data.get('spectral_center')
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    x, y = data['wcs'].world_to_pixel(SkyCoord(ra=ra*u.deg, dec=dec*u.deg))
    x = scalar_wcs_pixel(x, 'x')
    y = scalar_wcs_pixel(y, 'y')
    return _sample_wavelength(data['spectral_wcs'], x, y)

def require_science(alignment=False):
    try:
        from astropy.io import fits
        from astropy.wcs import WCS
    except ImportError as exc:
        raise ScienceDependencyMissing('Astropy is required to open genuine SPHEREx FITS products. Install requirements-science.txt.') from exc
    if alignment:
        try:
            from reproject import reproject_interp
        except ImportError as exc:
            raise ScienceDependencyMissing('Reproject is required for scientific WCS alignment. Install requirements-science.txt.') from exc


def open_science(path):
    require_science()
    from astropy.io import fits
    from astropy.wcs import WCS
    with fits.open(path, memmap=False, ignore_missing_end=False) as h:
        image = np.asarray(h['IMAGE'].data, dtype=np.float64).copy()
        variance = np.asarray(h['VARIANCE'].data, dtype=np.float64).copy() if 'VARIANCE' in h else np.full_like(image, np.nan)
        flags = np.asarray(h['FLAGS'].data).copy() if 'FLAGS' in h else np.zeros_like(image, dtype=np.int32)
        header = h['IMAGE'].header.copy()
        with warnings.catch_warnings(record=True) as spatial_warnings:
            warnings.simplefilter('always')
            wcs = WCS(header, key=' ')  # spatial WCS, including SIP where present
        if not wcs.has_celestial:
            raise ValueError('FITS cutout has no valid celestial WCS.')
        band = None
        spectral_wcs = None
        with warnings.catch_warnings(record=True) as spectral_warnings:
            warnings.simplefilter('always')
            try:
                spectral_wcs = WCS(header=header, fobj=h, key='W')
                # Per the official IRSA tutorial: spatial SIP does NOT belong
                # on the detector-fixed alternative spectral WCS (WAVE-TAB).
                spectral_wcs.sip = None
                y, x = (v // 2 for v in image.shape)
                band = _sample_wavelength(spectral_wcs, float(x), float(y))
            except (ValueError, KeyError, TypeError, IndexError, RuntimeError):
                spectral_wcs = None
    good = np.isfinite(image) & np.isfinite(variance) & (variance > 0) & (flags == 0)
    return {'image': image, 'variance': variance, 'flags': flags, 'mask': good,
            'header': header, 'wcs': wcs, 'spectral_wcs': spectral_wcs, 'spectral_center': band,
            'valid_fraction': float(np.mean(good)), 'unit': str(header.get('BUNIT', 'unknown')),
            'wcs_warnings': list(dict.fromkeys(str(v.message) for v in [*spatial_warnings, *spectral_warnings]))[:4]}


def render_png(data, mask=None):
    image = np.asarray(data, dtype=float)
    mask = (np.isfinite(image) if mask is None else np.isfinite(image) & mask)
    if not np.any(mask):
        raise ValueError('No scientifically usable pixels to display.')
    lo, hi = np.percentile(image[mask], [2, 99.5])
    if not hi > lo:
        hi = lo + 1
    scaled = np.arcsinh(np.clip((image - lo) / (hi - lo), 0, 1) * 10) / np.arcsinh(10)
    arr = np.uint8(np.nan_to_num(np.clip(scaled, 0, 1), nan=0.0, posinf=1.0, neginf=0.0) * 255)
    arr[~mask] = 0
    img = Image.fromarray(arr, mode='L')
    out = BytesIO()
    img.save(out, format='PNG')
    return out.getvalue()


def render_signed_difference_png(data, mask=None):
    """Visualize both positive and negative WCS-aligned differences.

    This is an illustrative signed-flux visualization, not a significance
    detection; red = brightened in later image, blue = dimmed.
    """
    a = np.asarray(data, dtype=np.float64)
    valid = np.isfinite(a) if mask is None else np.asarray(mask, dtype=bool) & np.isfinite(a)
    if not np.any(valid):
        raise ValueError('No scientifically usable difference pixels to display.')
    scale = float(np.percentile(np.abs(a[valid]), 98))
    if not np.isfinite(scale) or scale <= 0:
        scale = 1.0
    weight = np.arcsinh(np.clip(np.abs(a)/scale, 0, 1)*10)/np.arcsinh(10)
    weight = np.clip(np.nan_to_num(weight, nan=0.0, posinf=1.0), 0, 1)
    rgb = np.zeros((*a.shape, 3), dtype=np.uint8)
    rgb[:, :] = (25, 29, 45)
    bright = valid & (a > 0)
    dim = valid & (a < 0)
    base = np.array([25, 29, 45], dtype=float)
    for region, color in ((bright, [255, 100, 90]), (dim, [85, 162, 255])):
        if np.any(region):
            w = weight[region, None]
            rgb[region] = np.asarray(base*(1-w) + np.asarray(color, dtype=float)*w, dtype=np.uint8)
    out = BytesIO()
    Image.fromarray(rgb, 'RGB').save(out, format='PNG')
    return out.getvalue()


def preview_details(data):
    a = data['image']
    return {
        'shape': list(a.shape), 'valid_fraction': data['valid_fraction'],
        'pixel_units': data['unit'], 'spectral_center': data['spectral_center'],
        'quality': 'valid_with_flags_masked' if np.any(data['mask']) else 'no_valid_pixels',
        'warning': 'WAVE-TAB wavelength is approximate and position dependent; scientific calibration needs CWAVE/CBAND and PSF/background matching.',
        'wcs_warnings': data.get('wcs_warnings', [])
    }


def compare(first, second, method='difference'):
    require_science(alignment=True)
    from reproject import reproject_interp
    if first['spectral_center'] and second['spectral_center']:
        la, lb = first['spectral_center'][0], second['spectral_center'][0]
        if la > 0 and lb > 0 and abs(la-lb) / ((la+lb)/2) > .04:
            raise ValueError('The sampled wavelengths differ by more than 4%; scientifically incompatible for direct comparison.')
    else:
        raise ValueError('Per-pixel spectral WCS unavailable. Comparison blocked rather than implying wavelength compatibility.')
    # Reproject both the second image and its variance/mask onto the first image WCS.
    shape = first['image'].shape
    im2, footprint = reproject_interp((second['image'], second['wcs']), first['wcs'], shape_out=shape)
    var2, _ = reproject_interp((second['variance'], second['wcs']), first['wcs'], shape_out=shape)
    mask2, _ = reproject_interp((second['mask'].astype(float), second['wcs']), first['wcs'], shape_out=shape)
    valid = first['mask'] & (mask2 > .99) & (footprint > .99) & np.isfinite(im2) & np.isfinite(var2) & (var2 > 0)
    if not np.any(valid):
        raise ValueError('No overlapping quality-controlled WCS pixels.')
    if method == 'difference':
        result = im2 - first['image']
        sigma = np.sqrt(np.maximum(first['variance'] + var2, 1e-20))
        snr = np.where(valid, result / sigma, np.nan)
        return {'image': result, 'snr': snr, 'mask': valid,
                'note': 'Exploratory WCS-reprojected difference with an approximate WAVE-TAB wavelength check. PSF/background and accurate CWAVE/CBAND are not matched; no confirmed motion or variability.'}
    w1 = np.where(valid, 1 / np.maximum(first['variance'], 1e-20), 0)
    w2 = np.where(valid, 1 / np.maximum(var2, 1e-20), 0)
    result = np.where(w1+w2 > 0, (w1*first['image'] + w2*im2) / np.maximum(w1+w2, 1e-20), np.nan)
    return {'image': result, 'mask': valid, 'note': 'Inverse-variance weighted stack, WCS reprojected, flags/footprint filtered; wavelengths cross-checked at cutout center.'}


def aperture_photometry(data, radius_px=3):
    """Simple aperture measurement; Jy from MJy/sr using WCS pixel solid angle."""
    from astropy.wcs.utils import proj_plane_pixel_area
    if data.get('unit', '').lower().replace(' ', '') != 'mjy/sr':
        raise ValueError('Cannot report Jy photometry without verified MJy/sr FITS units.')
    ny, nx = data['image'].shape
    y, x = np.ogrid[:ny, :nx]
    aperture = ((x - (nx - 1)/2)**2 + (y - (ny - 1)/2)**2 <= radius_px**2)
    good = aperture & data['mask']
    if np.mean(good[aperture]) < 0.8:
        raise ValueError('Insufficient good pixels in photometry aperture.')
    pixel_sr = abs(float(proj_plane_pixel_area(data['wcs']))) * (np.pi / 180)**2
    jy = float(np.sum(data['image'][good]) * pixel_sr * 1e6)
    err = float(np.sqrt(np.sum(data['variance'][good])) * pixel_sr * 1e6)
    return {'flux_jy': jy, 'uncertainty_jy': err, 'radius_pixels': radius_px,
            'note': 'Uncorrected circular aperture sum (no local background or PSF correction); not calibrated total-object photometry.'}
