"""Actual SIA2 discovery, dataset metadata and bounded FITS cutout fetches."""
from datetime import datetime, timedelta, timezone
from io import StringIO
from urllib.parse import urljoin
import csv
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import json
import re
import xml.etree.ElementTree as ET
from ..models import SearchRequest
from ..settings import SIA_ENDPOINT, FRAMES_DIR
from .remote import get_bytes, validated_url, UpstreamError


def mjd_to_iso(value):
    try:
        return (datetime(1858, 11, 17, tzinfo=timezone.utc) + timedelta(days=float(value))).isoformat().replace('+00:00', 'Z')
    except (ValueError, TypeError, OverflowError):
        return None


def parse_votable(payload: bytes) -> list[dict]:
    """Read real VOTable TABLEDATA with namespace-independent tags; reject error responses."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as e:
        raise UpstreamError('IRSA response is not valid VOTable XML.') from e
    for info in root.iter():
        if info.tag.split('}')[-1].upper() == 'INFO' and (info.attrib.get('name', '').upper() == 'QUERY_STATUS'):
            if info.attrib.get('value', '').upper() == 'ERROR':
                raise UpstreamError('IRSA SIA2 error: ' + (info.text or '')[:200])
    table = next((e for e in root.iter() if e.tag.split('}')[-1].upper() == 'TABLE'), None)
    if table is None:
        return []
    fields = [(e.attrib.get('name') or e.attrib.get('ID') or '').strip().lower() for e in table if e.tag.split('}')[-1].upper() == 'FIELD']
    rows = []
    # Avoid claiming a scientifically empty field when the service provided an
    # unsupported binary VOTable representation rather than TABLEDATA.
    if any(n.tag.split('}')[-1].upper() in ('BINARY', 'BINARY2', 'FITS') for n in table.iter()):
        raise UpstreamError('IRSA returned binary VOTable; TABLEDATA required. No-data is not asserted.')
    for tr in table.iter():
        if tr.tag.split('}')[-1].upper() == 'TR':
            values = [(td.text or '').strip() for td in tr if td.tag.split('}')[-1].upper() == 'TD']
            rows.append(dict(zip(fields, values)))
    return rows


def detector_number(value: str) -> int | None:
    if not value:
        return None
    m = re.search(r'(?:D|detector\s*)([1-6])\b', str(value), re.I)
    if m:
        return int(m.group(1))
    return None


def safe_record(row: dict, collection: str) -> dict | None:
    url = row.get('access_url', '')
    try:
        validated_url(url, spherex_only=True)
    except ValueError:
        # Some legitimate cloud products are excluded explicitly because the cutout endpoint
        # in this version only supports IRSA on-premise files.
        return None
    det = detector_number(row.get('energy_bandpassname', ''))
    if not det:
        det = detector_number(row.get('instrument_name', ''))
    if not det:
        det = detector_number(row.get('obs_id', ''))
    def number(k):
        try:
            return float(row[k]) if row.get(k) else None
        except ValueError:
            return None
    return {
        'obs_id': row.get('obs_id') or sha256(url.encode()).hexdigest()[:14],
        'collection': row.get('obs_collection') or collection,
        'ra': number('s_ra'), 'dec': number('s_dec'),
        't_min': number('t_min'), 't_max': number('t_max'),
        'date': mjd_to_iso(row.get('t_min')),
        'em_min_m': number('em_min'), 'em_max_m': number('em_max'),
        'detector': det,
        'bandpass': row.get('energy_bandpassname') or None,
        'access_url': url,
        'source': 'NASA/IPAC IRSA SPHEREx SIA2',
        'data_mode': 'real',
    }


def balanced_year_sample(records: list[dict], limit: int) -> list[dict]:
    """Preserve every available observation year when limiting returned metadata.

    Each release can contain hundreds of exposures from only a few days.
    Returning the first N chronologically inadvertently hides later observing years.
    Unknown observation dates are not assigned an invented year.
    """
    buckets: dict[str, list[dict]] = {}
    for record in records:
        date = record.get('date') or ''
        year = date[:4] if len(date) >= 4 and date[:4].isdigit() else 'unknown'
        buckets.setdefault(year, []).append(record)
    years = sorted(buckets, key=lambda y: (y == 'unknown', y))
    selected: list[dict] = []
    while len(selected) < limit and any(buckets.values()):
        for year in years:
            if buckets[year] and len(selected) < limit:
                selected.append(buckets[year].pop(0))
    return sorted(selected, key=lambda o: (o.get('date') or '', o.get('obs_id') or ''))



# Same NASA/IPAC IRSA archive, different documented interface.
# These are discovery records, not substitute observation images.
TAP_ENDPOINT = 'https://irsa.ipac.caltech.edu/TAP/sync'


def _tap_datetime(value: str) -> tuple[str | None, float | None]:
    """Return only an actually reported timestamp and its MJD."""
    if not value or not value.strip():
        return None, None
    raw = value.strip()
    try:
        if raw.replace('.', '', 1).isdigit():
            mjd = float(raw)
            return (mjd_to_iso(mjd), mjd) if 40000 <= mjd <= 100000 else (None, None)
        dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        mjd = (dt - datetime(1858, 11, 17, tzinfo=timezone.utc)).total_seconds() / 86400
        return dt.isoformat().replace('+00:00', 'Z'), mjd
    except (ValueError, OverflowError):
        return None, None


def _tap_record(row: dict, collection: str) -> dict | None:
    """Reject non-IRSA URLs, incorrect releases, and unverified survey groups."""
    relative = (row.get('uri') or '').strip()
    if (not relative or relative.startswith(('http:', 'https:', '//'))
            or collection.endswith('_deep')):
        return None
    url = urljoin('https://irsa.ipac.caltech.edu/', relative.lstrip('/'))
    try:
        validated_url(url, spherex_only=True)
    except ValueError:
        return None
    release = 'dr1' if collection == 'spherex_dr1' else 'qr3'
    if not urlsplit(url).path.startswith(f'/ibe/data/spherex/{release}/level2/'):
        return None
    bandpass = (row.get('energy_bandpassname') or '').strip()
    match = re.search(r'_2D([1-6])_', urlsplit(url).path, re.IGNORECASE)
    detector = detector_number(bandpass) or (int(match.group(1)) if match else None)
    date, t_min = _tap_datetime(row.get('time_bounds_lower') or '')
    return {
        'obs_id': Path(urlsplit(url).path).stem,
        'collection': collection, 'ra': None, 'dec': None,
        't_min': t_min, 't_max': None, 'date': date,
        'em_min_m': None, 'em_max_m': None,
        'detector': detector, 'bandpass': bandpass or None,
        'access_url': url,
        'source': 'NASA/IPAC IRSA SPHEREx TAP (SIA fallback)',
        'data_mode': 'real',
        'metadata_note': 'TAP: wide/deep classification and wavelength bounds unverified.',
    }


async def search_spherex_tap(ra: float, dec: float, collection: str, max_records: int) -> list[dict]:
    """Official IRSA TAP artifact/plane spatial metadata fallback (wide only)."""
    if collection not in ('spherex_dr1', 'spherex_qr3'):
        raise UpstreamError('TAP fallback unverified for deep-field collection.')
    release = collection.split('_')[1]
    query = (
        f"SELECT TOP {min(500, max(1, max_records) * 3)} a.uri AS uri, "
        "p.time_bounds_lower AS time_bounds_lower, "
        "p.energy_bandpassname AS energy_bandpassname "
        "FROM spherex.artifact a JOIN spherex.plane p ON a.planeid = p.planeid "
        f"WHERE 1 = CONTAINS(POINT('ICRS', {ra:.9f}, {dec:.9f}), p.poly) "
        f"AND a.uri LIKE '%/spherex/{release}/level2/%' "
        "ORDER BY p.time_bounds_lower"
    )
    raw = await get_bytes(TAP_ENDPOINT, params={'QUERY': query, 'FORMAT': 'CSV'}, max_bytes=10_000_000)
    try:
        reader = csv.DictReader(StringIO(raw.decode('utf-8-sig')))
        if reader.fieldnames is None:
            raise ValueError('CSV header missing')
        reader.fieldnames = [field.strip().lower() for field in reader.fieldnames]
        if not {'uri', 'time_bounds_lower', 'energy_bandpassname'}.issubset(reader.fieldnames):
            raise ValueError('CSV columns unexpected')
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        raise UpstreamError('IRSA TAP response cannot be parsed as observation metadata.') from exc
    results = [_tap_record(row, collection) for row in rows]
    accepted = [rec for rec in results if rec is not None]
    if rows and not accepted:
        raise UpstreamError('IRSA TAP rows had no verified SPHEREx FITS URLs.')
    return accepted


async def search_spherex(payload: SearchRequest) -> dict:
    """Search real archival data and distinguish empty, filtered, unsupported and failed results.

    The archive can return actual rows that cannot be downloaded by this viewer.
    Treating those as 'zero observations' is a misleading false negative.
    """
    radius = round(payload.fov_arcmin / 120, 7)
    results, errors, diagnostics = [], [], []
    raw_matched = 0
    unsupported = 0
    for collection in payload.collections:
        try:
            raw = await get_bytes(SIA_ENDPOINT, params={
                'COLLECTION': collection,
                'POS': f'CIRCLE {payload.ra:.9f} {payload.dec:.9f} {radius:.7f}',
                'MAXREC': min(500, payload.max_records * 3),
                'RESPONSEFORMAT': 'VOTABLE',
            }, max_bytes=15000000)
            rows = parse_votable(raw)
            raw_matched += len(rows)
            accepted = 0
            for row in rows:
                record = safe_record(row, collection)
                if record:
                    results.append(record)
                    accepted += 1
                else:
                    unsupported += 1
            diagnostics.append({'collection': collection, 'archive_rows': len(rows),
                                'supported_downloads': accepted, 'unsupported_downloads': len(rows)-accepted})
        except UpstreamError as exc:
            # TAP is a separate official IRSA metadata service, not simulated images.
            # Only use it after retryable SIA failures; never hide malformed responses.
            if 'Astronomy service unavailable after retries:' in str(exc) and not collection.endswith('_deep'):
                try:
                    tap_records = await search_spherex_tap(payload.ra, payload.dec, collection, payload.max_records)
                    results.extend(tap_records)
                    raw_matched += len(tap_records)
                    diagnostics.append({'collection': collection, 'source': 'IRSA TAP',
                                        'sia_error': str(exc), 'supported_downloads': len(tap_records),
                                        'note': 'TAP metadata fallback; per-record wavelength bounds unverified.'})
                    continue
                except UpstreamError as tap_exc:
                    errors.append({'collection': collection, 'message': str(exc), 'tap_error': str(tap_exc)})
                    diagnostics.append({'collection': collection, 'sia_error': str(exc), 'tap_error': str(tap_exc)})
                    continue
            errors.append({'collection': collection, 'message': str(exc)})
            diagnostics.append({'collection': collection, 'error': str(exc)})
    seen, deduped = set(), []
    filtered_out = 0
    for item in sorted(results, key=lambda x: (x['t_min'] or 0, x['obs_id'])):
        key = (item['obs_id'], item['access_url'].split('?', 1)[0])
        if key in seen:
            continue
        seen.add(key)
        if payload.detector and payload.detector != item['detector']:
            filtered_out += 1
            continue
        if item['date'] and payload.date_from and item['date'][:10] < payload.date_from:
            filtered_out += 1
            continue
        if item['date'] and payload.date_to and item['date'][:10] > payload.date_to:
            filtered_out += 1
            continue
        deduped.append(item)
    # Equal-year sampling is essential for actual multi-year comparisons.
    # A chronological first-page slice could hide all QR3/2026 observations.
    year_counts: dict[str, int] = {}
    for record in deduped:
        d = record.get('date') or ''
        year = d[:4] if len(d) >= 4 and d[:4].isdigit() else 'unknown'
        year_counts[year] = year_counts.get(year, 0) + 1
    clipped = balanced_year_sample(deduped, payload.max_records)
    if not clipped:
        if errors:
            status = 'upstream_error'
            message = 'Some IRSA collections failed; zero usable records does NOT establish absence of observations.'
        elif raw_matched and not results:
            status = 'unsupported'
            message = 'IRSA returned observations, but this viewer rejected their download URLs; observations exist in the archive.'
        elif results:
            status = 'filtered'
            message = 'IRSA returned observations, but the detector or date filters excluded them. Clear the filters and try again.'
        else:
            status = 'empty'
            message = 'No spectral-image rows matched the searched collections and sky region. This does not mean the DR1 all-sky cube is empty.'
    else:
        status = 'partial' if errors else 'ok'
        message = 'Some IRSA collections failed; results are incomplete.' if errors else None
    return {
        'observations': clipped, 'count': len(clipped), 'total_matched': len(deduped),
        'year_counts': year_counts, 'years_available': sorted(y for y in year_counts if y != 'unknown'),
        'truncated': len(deduped) > len(clipped),
        'collections_checked': payload.collections,
        'data_mode': 'real', 'source': 'NASA/IPAC IRSA SIA2',
        'source_url': SIA_ENDPOINT, 'fallback_url': TAP_ENDPOINT, 'errors': errors,
        'status': status, 'message': message, 'diagnostics': diagnostics,
        'archive_rows': raw_matched, 'supported_rows': len(results),
        'unsupported_rows': unsupported, 'filtered_out': filtered_out,
        'note': 'The DR1 all-sky cube is a separate collection, not a result in the spectral-image search.',
    }


def cutout_url(source_url: str, ra: float, dec: float, fov_arcmin: float) -> str:
    validated_url(source_url, spherex_only=True)
    parts = urlsplit(source_url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode({'center': f'{ra:.9f},{dec:.9f}', 'size': f'{fov_arcmin:.6f}arcmin', 'gzip': 'false'}), ''))


def frame_key(obs: dict, ra: float, dec: float, fov_arcmin: float) -> str:
    # No re-use across targets, releases, coordinates, wavelength or cutout sizes.
    identifying = {k: obs.get(k) for k in ('obs_id', 'collection', 'access_url', 'detector', 'date', 'em_min_m', 'em_max_m')}
    identifying.update(ra=round(ra, 9), dec=round(dec, 9), fov_arcmin=round(fov_arcmin, 5))
    return sha256(json.dumps(identifying, sort_keys=True).encode()).hexdigest()


async def download_frame(obs: dict, ra: float, dec: float, fov_arcmin: float):
    """Retrieve a genuine FITS cutout; retry a smaller *same-center* cutout on 422.

    IRSA can accept an SIA footprint yet reject a particular MEF cutout. Only
    HTTP 422 gets a smaller-size retry; invalid links and unrelated HTTP errors
    are never silently treated as data or swallowed. The effective FoV is
    recorded explicitly, so the UI never labels a small cutout as a large one.
    """
    for required in ('obs_id', 'collection', 'access_url', 'data_mode'):
        if required not in obs:
            raise ValueError(f'Observation missing {required}.')
    if obs['data_mode'] != 'real' or obs['collection'] not in (
        'spherex_dr1', 'spherex_qr3', 'spherex_dr1_deep', 'spherex_qr3_deep'):
        raise ValueError('Only real SPHEREx observations from approved collections may be fetched.')
    key = frame_key(obs, ra, dec, fov_arcmin)
    path = FRAMES_DIR / (key + '.fits')
    metadata = FRAMES_DIR / (key + '.json')
    if not (path.exists() and metadata.exists()):
        # Keep the science position fixed and reduce width only. Never switch
        # to a record-centered image, which may not contain the requested target.
        sizes = [float(fov_arcmin)]
        for size in (5., 2., 1.):
            if size < fov_arcmin and size not in sizes:
                sizes.append(size)
        failures = []
        for actual_size in sizes:
            url = cutout_url(obs['access_url'], ra, dec, actual_size)
            try:
                raw = await get_bytes(url, spherex_only=True)
            except UpstreamError as exc:
                failures.append(f'{actual_size:g} arcmin: {exc}')
                if exc.status_code == 422 and actual_size != sizes[-1]:
                    continue
                raise UpstreamError('IRSA could not generate this observation cutout. '
                                    + ' | '.join(failures)[-470:], exc.status_code) from exc
            if not (raw.startswith(b'SIMPLE  ') or raw.startswith(b'\x1f\x8b')):
                raise UpstreamError('IRSA cutout did not return a FITS file; no substitute data were created.')
            tmp = path.with_suffix('.partial')
            tmp.write_bytes(raw)
            tmp.replace(path)
            metadata.write_text(json.dumps({'observation': obs, 'ra': ra, 'dec': dec,
                 'requested_fov_arcmin': fov_arcmin, 'actual_fov_arcmin': actual_size,
                 'fov_arcmin': actual_size, 'cutout_url': url,
                 'warning': ('Archive rejected the original cutout size; a smaller, '
                             'same-center true FITS cutout was retrieved.' if actual_size < fov_arcmin else None)},
                 ensure_ascii=False))
            break
    return key, path, json.loads(metadata.read_text())


def load_frame(key: str) -> tuple[Path, dict]:
    if not re.fullmatch(r'[0-9a-f]{64}', key):
        raise ValueError('Invalid frame id.')
    path = FRAMES_DIR / (key + '.fits')
    meta = FRAMES_DIR / (key + '.json')
    if not path.exists() or not meta.exists():
        raise FileNotFoundError('Frame not cached; build it from a live SIA2 record first.')
    return path, json.loads(meta.read_text())
