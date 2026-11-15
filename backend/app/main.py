"""SkyShift AI FastAPI service: live-only astronomy sources, explicit scientific quality."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
import csv
import io
import json
import logging
import os
import sqlite3
import time
import uuid

from fastapi import FastAPI, HTTPException, Query, Response, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .models import ResolveRequest, SearchRequest, FrameRequest, CompareRequest, AnnotationRequest, LightCurveRequest, AnnualCompareRequest
from .settings import ROOT, FRONTEND_DIR, DB_PATH, COLLECTIONS
from .services.remote import UpstreamError
from .services.resolver import resolve_target, query_exoplanets, SOLAR_IDS
from .services.spherex import search_spherex, download_frame, load_frame
from .services.science import ScienceDependencyMissing, open_science, preview_details, render_png, render_signed_difference_png, compare, aperture_photometry, scalar_wcs_pixel, spectrum_at_target

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
LOG = logging.getLogger('skyshift')

app = FastAPI(title='SkyShift AI — Scientific Astronomy API', version='1.0.0',
              description='NASA/IPAC SPHEREx discovery with provenance. No fake observations.',
              docs_url='/api/docs', openapi_url='/api/openapi.json')
OBSERVATION_INDEX: dict[str, dict] = {}


@app.exception_handler(UpstreamError)
async def upstream_handler(request: Request, exc: UpstreamError):
    return JSONResponse(status_code=502, content={'status': 'upstream_error', 'message': str(exc), 'data_mode': 'unavailable'})


@app.exception_handler(ScienceDependencyMissing)
async def science_handler(request: Request, exc: ScienceDependencyMissing):
    return JSONResponse(status_code=503, content={'status': 'dependency_missing', 'message': str(exc), 'data_mode': 'unavailable'})


@app.exception_handler(ValueError)
async def value_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={'status': 'input_error', 'message': str(exc)})


@app.middleware('http')
async def response_headers(request: Request, call_next):
    result = await call_next(request)
    result.headers['X-Content-Type-Options'] = 'nosniff'
    result.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    result.headers['X-Frame-Options'] = 'DENY'
    if request.url.path.startswith('/api'):
        result.headers['Cache-Control'] = 'no-store'
    return result


@app.get('/api/health')
def health():
    try:
        import astropy
        science_available = True
    except ImportError:
        science_available = False
    try:
        import reproject
        alignment_available = True
    except ImportError:
        alignment_available = False
    return {'status': 'ok', 'service': 'SkyShift AI', 'version': '1.0.0',
            'data_mode': 'real_only', 'live_connection_tested': False,
            'features': {'search': True, 'resolver': True,
                         'fits_preview': science_available, 'wcs_alignment': alignment_available},
            'timestamp': datetime.now(timezone.utc).isoformat()}


@app.post('/api/objects/resolve')
async def objects_resolve(payload: ResolveRequest):
    data = await resolve_target(payload.name, payload.ra, payload.dec, payload.epoch, payload.category)
    return {'status': 'ok', 'object': data, 'data_mode': 'real_catalog',
            'request_id': uuid.uuid4().hex}


@app.get('/api/objects/suggest')
async def objects_suggest(q: str = Query(min_length=1, max_length=60)):
    # Suggestions are explicitly not a full live database search. Frontend submits names
    # to the resolver and NASA archive regardless of any local example suggestions.
    common = ['Barnard\'s Star', 'Epsilon Indi B', 'WISE 0855', 'RW Aurigae', 'R Draconis',
              'Andromeda Galaxy', 'M101', 'TRAPPIST-1 e', 'Kepler-22 b', 'Proxima Centauri b']
    matches = [n.title() for n in SOLAR_IDS if q.lower() in n.lower()]
    matches += [n for n in common if q.lower() in n.lower()]
    return {'suggestions': [{'name': n, 'source': 'example, resolved live on search'} for n in matches[:10]],
            'source': 'local examples only; not live catalog autocomplete'}


@app.get('/api/planets/solar')
def solar_catalog():
    return {'items': [{'name': name.title(), 'horizons_id': hid, 'coordinates': None,
                       'coordinate_source': 'JPL Horizons (computed when selected)'}
                      for name, hid in SOLAR_IDS.items()],
            'source': 'NASA/JPL Horizons', 'positions': 'dynamic, date-dependent'}


@app.get('/api/exoplanets/search')
async def exoplanets_search(q: str = Query(default='', max_length=70), page: int = Query(default=1, ge=1, le=10000),
                            page_size: int = Query(default=20, ge=1, le=50)):
    return await query_exoplanets(q=q, page=page, page_size=page_size)


@app.post('/api/spherex/observations/search')
async def spherex_search(payload: SearchRequest):
    result = await search_spherex(payload)
    # The index restricts subsequent downloads to records discovered from the trusted SIA API.
    search_id = uuid.uuid4().hex
    for record in result['observations']:
        record['search_request_id'] = search_id
        key = search_id + '|' + record['obs_id'] + '|' + record['access_url']
        OBSERVATION_INDEX[key] = {'record': record, 'search_ra': payload.ra, 'search_dec': payload.dec,
                                  'search_fov': payload.fov_arcmin, 'seen_at': time.time()}
    if len(OBSERVATION_INDEX) > 10000:
        cutoff = time.time() - 3600
        for key in list(OBSERVATION_INDEX):
            if OBSERVATION_INDEX[key]['seen_at'] < cutoff:
                del OBSERVATION_INDEX[key]
    result['request_id'] = search_id
    return result


def _registered_observation(record: dict, ra: float, dec: float, fov_arcmin: float) -> dict:
    key = str(record.get('search_request_id')) + '|' + str(record.get('obs_id')) + '|' + str(record.get('access_url'))
    indexed = OBSERVATION_INDEX.get(key)
    if not indexed or indexed['record'] != record or time.time() - indexed['seen_at'] > 3600:
        raise HTTPException(status_code=403, detail='Observation must be in a recent real SIA search; search again.')
    if abs(indexed['search_ra'] - ra) > 1e-7 or abs(indexed['search_dec'] - dec) > 1e-7:
        raise HTTPException(status_code=403, detail='Cutout coordinates must match the original search.')
    if fov_arcmin > indexed['search_fov']:
        raise HTTPException(status_code=403, detail='Cutout size cannot exceed the searched field.')
    return indexed


async def _build_registered_frame(record: dict, ra: float, dec: float, fov_arcmin: float) -> dict:
    _registered_observation(record, ra, dec, fov_arcmin)
    frame_id, path, meta = await download_frame(record, ra, dec, fov_arcmin)
    info = {'status': 'ok', 'frame_id': frame_id, 'data_mode': 'real',
            'source': 'NASA/IPAC IRSA SPHEREx', 'fits_url': f'/api/spherex/frames/{frame_id}/fits',
            'preview_url': f'/api/spherex/frames/{frame_id}/preview',
            'provenance': meta, 'byte_size': path.stat().st_size}
    try:
        parsed = open_science(path)
        from astropy.coordinates import SkyCoord
        import astropy.units as u
        x_raw, y_raw = parsed['wcs'].world_to_pixel(SkyCoord(ra=ra*u.deg, dec=dec*u.deg))
        x = scalar_wcs_pixel(x_raw, 'x')
        y = scalar_wcs_pixel(y_raw, 'y')
        ny, nx = parsed['image'].shape
        if not (0 <= x < nx and 0 <= y < ny):
            raise ValueError('This FITS cutout does not contain the requested target after WCS projection.')
        if parsed.get('mask') is not None and not parsed['mask'].any():
            raise ValueError('This cutout contains no scientifically valid image pixels.')
        parsed['spectral_center'] = spectrum_at_target(parsed, ra, dec)
        info['science'] = {**preview_details(parsed), 'target_pixel': [round(x, 2), round(y, 2)]}
    except ScienceDependencyMissing as exc:
        info['science'] = {'status': 'dependency_missing', 'message': str(exc)}
    except (OSError, KeyError, IndexError, TypeError) as exc:
        raise ValueError('The downloaded FITS cannot be decoded or projected reliably; choose another observation.') from exc
    return info


@app.post('/api/spherex/frames/build')
async def spherex_build(payload: FrameRequest):
    return await _build_registered_frame(payload.observation, payload.ra, payload.dec, payload.fov_arcmin)


def _band_rank(reference: dict, candidate: dict) -> float:
    """Rank likely wavelength match using *catalog* metadata; not a quality verdict."""
    def wavelength(r):
        a, b = r.get('em_min_m'), r.get('em_max_m')
        return (a+b)/2 if isinstance(a, (float,int)) and isinstance(b, (float,int)) and a > 0 and b > 0 else None
    same_detector = reference.get('detector') == candidate.get('detector') and reference.get('detector') is not None
    a, b = wavelength(reference), wavelength(candidate)
    return (0 if same_detector else 20) + (abs(a-b)/((a+b)/2) * 100 if a and b else 50)


@app.post('/api/spherex/years/compare')
async def compare_years(payload: AnnualCompareRequest):
    """Try independent real observations for both years; skip rejected 422 cutouts.

    Each record is previously returned by IRSA SIA to this exact search. A failed
    image never becomes a placeholder, and the selected years are not substituted.
    """
    matching = [row['record'] for row in OBSERVATION_INDEX.values()
                if row['record'].get('search_request_id') == payload.search_request_id
                and row['search_ra'] == payload.ra and row['search_dec'] == payload.dec
                and row['search_fov'] >= payload.fov_arcmin and time.time()-row['seen_at'] < 3600]
    # No duplicates from multiple queries; stable sort by date to prefer early epochs.
    by_year = {year: [] for year in (payload.year_a, payload.year_b)}
    for rec in matching:
        date = rec.get('date') or ''
        if len(date) >= 4 and date[:4].isdigit() and int(date[:4]) in by_year:
            by_year[int(date[:4])].append(rec)
    if any(not rows for rows in by_year.values()):
        raise HTTPException(status_code=422, detail='No real dated observation in one selected year. Search again or change the year.')
    for year in by_year:
        by_year[year].sort(key=lambda o: (o.get('date') or '', o.get('obs_id') or ''))
    attempts = []

    async def attempt(rec):
        try:
            frame = await _build_registered_frame(rec, payload.ra, payload.dec, payload.fov_arcmin)
            if frame.get('science', {}).get('status'):
                raise ValueError(frame['science'].get('message', 'Scientific preview unavailable.'))
            return frame
        except (UpstreamError, ValueError, ScienceDependencyMissing, HTTPException) as exc:
            attempts.append({'year': (rec.get('date') or '')[:4],
                             'obs_id': str(rec.get('obs_id') or '')[:100],
                             'message': str(exc.detail if isinstance(exc, HTTPException) else exc)[:230]})
            return None

    first = None
    for rec in by_year[payload.year_a][:5]:
        first = await attempt(rec)
        if first:
            break
    if not first:
        return {'status': 'no_usable_pair', 'data_mode': 'unavailable',
                'message': f'No usable FITS cutout for {payload.year_a} after checking alternative observations.',
                'attempts': attempts, 'frames': []}

    reference = first['provenance']['observation']
    candidates = sorted(by_year[payload.year_b], key=lambda r: (_band_rank(reference, r), r.get('date') or ''))
    second, alternative = None, None
    for rec in candidates[:6]:
        possible = await attempt(rec)
        if not possible:
            continue
        if alternative is None:
            alternative = possible
        wl_a = (first.get('science', {}).get('spectral_center') or [None])[0]
        wl_b = (possible.get('science', {}).get('spectral_center') or [None])[0]
        if wl_a and wl_b and wl_a > 0 and wl_b > 0 and abs(wl_a-wl_b)/((wl_a+wl_b)/2) <= .04:
            second = possible
            break
    if second is None:
        second = alternative
    if not second:
        return {'status': 'no_usable_pair', 'data_mode': 'unavailable',
                'message': f'{payload.year_a} has a valid frame, but {payload.year_b} cutouts were rejected or invalid.',
                'attempts': attempts, 'frames': [first]}

    band_a = (first.get('science', {}).get('spectral_center') or [None])[0]
    band_b = (second.get('science', {}).get('spectral_center') or [None])[0]
    spectral_match = bool(band_a and band_b and band_a > 0 and band_b > 0
                          and abs(band_a-band_b)/((band_a+band_b)/2) <= .04)
    return {'status': 'ok', 'data_mode': 'derived_from_real',
            'frames': [first, second], 'years': [payload.year_a, payload.year_b],
            'attempts': attempts, 'spectrally_comparable_at_cutout_center': spectral_match,
            'message': ('Two NASA FITS observations are displayed. The sampled wavelengths are compatible; '
                        'this is not proof of variability or movement.' if spectral_match else
                        'Two genuine years are available, but sampled wavelengths differ or are unknown. '
                        'A quantitative difference may be invalid and will be blocked by the science checker.')}


@app.get('/api/spherex/frames/{frame_id}/preview')
def frame_preview(frame_id: str):
    path, meta = load_frame(frame_id)
    data = open_science(path)
    return Response(render_png(data['image'], data['mask']), media_type='image/png',
                    headers={'X-Astronomy-Source': 'NASA-IPAC-IRSA-SPHEREx', 'X-Data-Mode': 'real'})


@app.get('/api/spherex/frames/{frame_id}/fits')
def frame_fits(frame_id: str):
    path, meta = load_frame(frame_id)
    return FileResponse(path, filename='spherex-cutout-' + frame_id[:12] + '.fits', media_type='application/fits')


@app.get('/api/spherex/frames/{frame_id}/details')
def frame_details(frame_id: str):
    path, meta = load_frame(frame_id)
    data = open_science(path)
    return {'id': frame_id, 'provenance': meta, 'science': preview_details(data)}


@app.post('/api/analysis/compare')
def analysis_compare(payload: CompareRequest):
    if payload.frame_a == payload.frame_b:
        raise ValueError('Two distinct real observations are required for comparison.')
    a_path, a_meta = load_frame(payload.frame_a)
    b_path, b_meta = load_frame(payload.frame_b)
    first_id, second_id = payload.frame_a, payload.frame_b
    first_date = a_meta.get('observation', {}).get('date')
    second_date = b_meta.get('observation', {}).get('date')
    if not first_date or not second_date:
        raise ValueError('Both observations must have a real UTC date for a signed difference.')
    if first_date > second_date:
        (a_path, b_path), (a_meta, b_meta) = (b_path, a_path), (b_meta, a_meta)
        (first_id, second_id), (first_date, second_date) = (second_id, first_id), (second_date, first_date)
    a, b = open_science(a_path), open_science(b_path)
    for item, meta in ((a, a_meta), (b, b_meta)):
        if meta.get('ra') is not None and meta.get('dec') is not None:
            item['spectral_center'] = spectrum_at_target(item, meta['ra'], meta['dec'])
    result = compare(a, b, method=payload.method)
    out = (render_signed_difference_png(result['image'], result['mask'])
           if payload.method == 'difference' else render_png(result['image'], result['mask']))
    from base64 import b64encode
    return {'status': 'ok', 'data_mode': 'derived_from_real',
            'image_data_url': 'data:image/png;base64,' + b64encode(out).decode(),
            'note': result['note'], 'source_frames': [first_id, second_id],
            'observation_dates': [first_date, second_date],
            'quality_pixels': int(result['mask'].sum()),
            'color_legend': ({'positive': 'red — later brighter', 'negative': 'blue — later dimmer'}
                             if payload.method == 'difference' else None)}


@app.post('/api/analysis/photometry')
def analysis_photometry(payload: CompareRequest):
    flux = []
    for frame_id in (payload.frame_a, payload.frame_b):
        path, meta = load_frame(frame_id)
        flux.append({'frame_id': frame_id, 'date': meta['observation']['date'],
                     **aperture_photometry(open_science(path))})
    return {'status': 'ok', 'points': flux, 'data_mode': 'derived_from_real',
            'note': 'Only two frame measurements; not evidence of variability without calibration and more epochs.'}



@app.post('/api/analysis/lightcurve')
def analysis_lightcurve(payload: LightCurveRequest):
    """Preliminary same-band light curve with measured uncertainties, not a discovery claim."""
    frames=[]
    measurements=[]
    for frame_id in payload.frame_ids:
        path, meta = load_frame(frame_id)
        dat = open_science(path)
        if meta.get('ra') is not None and meta.get('dec') is not None:
            dat['spectral_center'] = spectrum_at_target(dat, meta['ra'], meta['dec'])
        if not dat['spectral_center'] or not dat['spectral_center'][0]:
            raise ValueError('Missing per-pixel WCS-WAVE; cannot construct comparable light curve.')
        frames.append(dat)
        measurements.append({'frame_id': frame_id,
            'date': meta['observation'].get('date'),
            'obs_id': meta['observation'].get('obs_id'),
            'wavelength_um': float(dat['spectral_center'][0]),
            **aperture_photometry(dat, radius_px=payload.radius_pixels)})
    bands=[v['wavelength_um'] for v in measurements]
    avg=sum(bands)/len(bands)
    if avg <= 0 or any(abs(v - avg)/avg > .04 for v in bands):
        raise ValueError('Frames sample incompatible wavelengths. Photometry cannot be treated as one time series.')
    if any(not p['date'] for p in measurements):
        raise ValueError('Every plotted photometry point must have a documented observation date.')
    measurements.sort(key=lambda r: r.get('date') or '')
    return {'status':'ok', 'data_mode':'derived_from_real', 'points':measurements,
        'note':'Preliminary aperture photometry (Jy), not background/PSF corrected. ' +
               'Spectral compatibility checked at target cutout center only; ' +
               'variability and discovery are not confirmed.'}

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS annotations (
            id TEXT PRIMARY KEY, target TEXT, ra REAL, dec REAL, frame_id TEXT,
            note TEXT, kind TEXT, status TEXT, created_at TEXT)''')


@app.post('/api/annotations')
def add_annotation(payload: AnnotationRequest):
    load_frame(payload.frame_id)
    init_db()
    item_id = uuid.uuid4().hex
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('INSERT INTO annotations VALUES (?,?,?,?,?,?,?,?,?)',
                     (item_id, payload.target, payload.ra, payload.dec, payload.frame_id,
                      payload.note, payload.kind, 'needs_verification', datetime.now(timezone.utc).isoformat()))
    return {'status': 'ok', 'id': item_id, 'verification_status': 'needs_verification'}


@app.get('/api/annotations')
def list_annotations(limit: int = Query(default=40, ge=1, le=100)):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        result = [dict(r) for r in conn.execute('SELECT * FROM annotations ORDER BY created_at DESC LIMIT ?', (limit,))]
    return {'items': result, 'notice': 'Unreviewed community observations are not confirmed discoveries.'}


TARGETS = [
    {'name': "Barnard's Star", 'ra': None, 'dec': None},
    {'name': 'Epsilon Indi B', 'ra': None, 'dec': None},
    {'name': 'WISE 0855', 'ra': 133.795129, 'dec': -7.245147},
    {'name': 'RW Aurigae', 'ra': None, 'dec': None},
    {'name': 'R Draconis', 'ra': None, 'dec': None},
]


@app.get('/api/targets/validation')
def validation():
    return {'targets': [{**t, 'status': 'not_live_tested', 'test': 'resolve → SIA2 → FITS → compare compatible epochs'}
                        for t in TARGETS],
            'live_tests_executed': False,
            'warning': 'Offline environment: no authentic NASA observation queries were verified here.'}


@app.get('/api/sources')
def sources():
    return {'mission': 'NASA SPHEREx', 'verified_documentation': '2026-11-12',
            'items': [
                {'name': 'IRSA SIA2', 'url': 'https://irsa.ipac.caltech.edu/SIA', 'use': 'Real spatial image discovery'},
                {'name': 'SPHEREx Archive', 'url': 'https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/', 'use': 'Cutouts and release names'},
                {'name': 'NASA Exoplanet Archive', 'url': 'https://exoplanetarchive.ipac.caltech.edu/', 'use': 'Planet and host-system coordinates'},
                {'name': 'JPL Horizons', 'url': 'https://ssd-api.jpl.nasa.gov/doc/horizons.html', 'use': 'Dated solar-system positions'},
                {'name': 'CDS Sesame', 'url': 'https://cds.unistra.fr/doc/sesame.htx', 'use': 'Object names'},
            ], 'disclaimer': 'This project uses publicly available NASA and partner data. NASA does not endorse this project.'}


app.mount('/assets', StaticFiles(directory=str(FRONTEND_DIR)), name='assets')


@app.get('/')
def home():
    return FileResponse(FRONTEND_DIR / 'index.html')


@app.get('/{path:path}')
def spa(path: str):
    if path.startswith(('api/', 'assets/')):
        raise HTTPException(status_code=404, detail='Not found')
    return FileResponse(FRONTEND_DIR / 'index.html')
