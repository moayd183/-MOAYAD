"""Independent coordinate resolvers: direct, NASA Exoplanet TAP, JPL Horizons, CDS Sesame."""
import csv
from datetime import date, timedelta
import io
import math
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote
from ..settings import EXOPLANET_ENDPOINT, HORIZONS_ENDPOINT, SESAME_ENDPOINTS
from .remote import get_bytes, UpstreamError

# Explicit JPL target IDs; not ephemerides or hardcoded target positions.
_TAP_CACHE: dict[tuple[str,int,int], tuple[float, dict]] = {}

# Search conveniences; always fetch actual catalog coordinates from a live resolver.
# Full designation from SIMBAD: https://simbad.u-strasbg.fr/simbad/sim-id?Ident=WISE+J085510.83-071442.5
NAME_ALIASES = {
    'wise 0855': 'WISE J085510.83-071442.5',
    'wise 0855-0714': 'WISE J085510.83-071442.5',
}

SOLAR_IDS = {
    'mercury': '199', 'venus': '299', 'earth': '399', 'mars': '499',
    'jupiter': '599', 'saturn': '699', 'uranus': '799', 'neptune': '899',
    'pluto': '999', 'sun': '10', 'moon': '301',
}


def parse_angle(value, *, ra: bool) -> float:
    raw = str(value).strip().replace('−', '-').replace('°', 'd').replace('′', 'm').replace('″', 's')
    if not raw:
        raise ValueError('Coordinate is blank.')
    if re.fullmatch(r'[+-]?\d+(?:\.\d+)?', raw):
        deg = float(raw)
    else:
        sexa = raw.lower()
        is_hours = ra and (bool(re.search(r'[:h]', sexa)) or len(sexa.split()) >= 2)
        components = re.findall(r'[+-]?\d+(?:\.\d+)?', sexa)
        if not 2 <= len(components) <= 3:
            raise ValueError('Invalid sexagesimal coordinate.')
        values = [float(v) for v in components]
        if values[1] >= 60 or (len(values) > 2 and values[2] >= 60):
            raise ValueError('Minutes and seconds must be below 60.')
        sign = -1 if raw.lstrip().startswith('-') else 1
        deg = sign * (abs(values[0]) + values[1] / 60 + (values[2] if len(values) > 2 else 0) / 3600)
        if is_hours:
            deg *= 15
    if (ra and not (0 <= deg < 360)) or (not ra and not (-90 <= deg <= 90)):
        raise ValueError('RA must be 0–360°; Dec must be -90–90°.')
    return round(deg, 9)


def clean_name(name: str) -> str:
    name = name.strip()
    if not re.fullmatch(r"[\w .+*()/'\-]{1,130}", name, re.UNICODE):
        raise ValueError('Object name contains unsupported characters.')
    return name


def tap_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


async def resolve_horizons(name: str, epoch: str | None) -> dict:
    if name.lower() == 'earth':
        raise ValueError('Earth cannot be located from an Earth-geocentric observer. Select a different body or observatory.')
    target = SOLAR_IDS[name.lower()]
    when = date.fromisoformat(epoch) if epoch else date.today()
    params = {
        'format': 'json', 'COMMAND': f"'{target}'", 'MAKE_EPHEM': "'YES'",
        'EPHEM_TYPE': "'OBSERVER'", 'CENTER': "'500@399'",
        'START_TIME': f"'{when.isoformat()}'",
        'STOP_TIME': f"'{(when + timedelta(days=1)).isoformat()}'",
        'STEP_SIZE': "'1 d'", 'QUANTITIES': "'1'", 'ANG_FORMAT': "'DEG'",
        'CSV_FORMAT': "'YES'", 'OBJ_DATA': "'NO'",
    }
    import json
    data = json.loads((await get_bytes(HORIZONS_ENDPOINT, params=params, max_bytes=2000000)).decode())
    if data.get('error'):
        raise UpstreamError('JPL Horizons: ' + str(data['error'])[:180])
    ephem = data.get('result', '')
    if '$$SOE' not in ephem or '$$EOE' not in ephem:
        raise UpstreamError('JPL Horizons returned no matching ephemeris.')
    line = ephem.split('$$SOE', 1)[1].split('$$EOE', 1)[0].strip().splitlines()[0]
    columns = next(csv.reader([line], skipinitialspace=True))
    # In Horizons observer CSV, first fields are date and solar illumination marker;
    # with QUANTITIES=1, the subsequent coordinate columns are RA, Dec in degrees.
    possible = []
    for cell in columns[1:]:
        try:
            possible.append(float(cell.strip()))
        except ValueError:
            possible.append(None)
    for i in range(len(possible) - 1):
        ra, dec = possible[i:i+2]
        if ra is not None and dec is not None and 0 <= ra < 360 and -90 <= dec <= 90:
            return {'name': name, 'type': 'solar_system', 'ra': ra, 'dec': dec,
                    'coordinate_source': 'NASA/JPL Horizons', 'epoch': when.isoformat(),
                    'note': 'Geocentric apparent position for this date, not a fixed sky coordinate.'}
    raise UpstreamError('JPL Horizons ephemeris coordinates could not be parsed safely.')


async def query_exoplanets(q: str = '', page: int = 1, page_size: int = 20) -> dict:
    # Keyset not needed for these bounded page sizes. Structured SQL is built from escaped literal.
    limit, offset = min(page_size, 50), (page - 1) * page_size
    cache_key = (q.lower(), page, limit)
    cached = _TAP_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < 600:
        return cached[1]
    predicate = f" where lower(pl_name) like {tap_literal('%' + q.lower() + '%')}" if q else ''
    cols = 'pl_name,hostname,ra,dec,discoverymethod,disc_year,pl_rade,pl_bmasse'
    query = f'select {cols} from pscomppars{predicate} order by pl_name'
    params = {'query': query, 'format': 'json'}
    import json
    all_rows = json.loads((await get_bytes(EXOPLANET_ENDPOINT, params=params, max_bytes=22000000)).decode())
    if not isinstance(all_rows, list):
        raise UpstreamError('NASA Exoplanet Archive returned an unexpected format.')
    total = len(all_rows)
    # NOTE: currently retrieves the full archive for complete consistent pagination; use TAP bounded server paging in production at scale.
    result = {'items': all_rows[offset:offset+limit], 'total': total, 'page': page,
              'page_size': limit, 'source': 'NASA Exoplanet Archive / pscomppars',
              'source_url': 'https://exoplanetarchive.ipac.caltech.edu/', 'live': True}
    if len(_TAP_CACHE) > 100:
        _TAP_CACHE.clear()
    _TAP_CACHE[cache_key] = (time.monotonic(), result)
    return result


async def resolve_exoplanet(name: str) -> dict | None:
    import json
    query = ('select top 1 pl_name,hostname,ra,dec,discoverymethod,disc_year '
             'from pscomppars where lower(pl_name) = ' + tap_literal(name.lower()))
    rows = json.loads((await get_bytes(EXOPLANET_ENDPOINT, params={'query': query, 'format': 'json'}, max_bytes=1000000)).decode())
    if not rows:
        return None
    r = rows[0]
    return {'name': r.get('pl_name') or name, 'host_star': r.get('hostname'),
            'ra': float(r['ra']), 'dec': float(r['dec']), 'type': 'exoplanet_system',
            'coordinate_source': 'NASA Exoplanet Archive / pscomppars',
            'note': 'Coordinates refer to the HOST STAR SYSTEM; not a direct image of the planet.',
            'direct_planet_image': False}


async def resolve_sesame(name: str) -> dict:
    canonical_name = NAME_ALIASES.get(name.casefold(), name)
    failures = []
    for base in SESAME_ENDPOINTS:
        try:
            # Sesame expects ?Object_Name, not /Object_Name (see CDS service docs).
            xml = await get_bytes(base + '?' + quote(canonical_name, safe=''), max_bytes=500000)
            root = ET.fromstring(xml)
            # Namespace-neutral search: mirrors may vary XML prefix/schema.
            coords = {}
            for item in root.iter():
                local_name = item.tag.rsplit('}', 1)[-1]
                if local_name in ('jradeg', 'jdedeg') and item.text:
                    coords.setdefault(local_name, item.text.strip())
            if 'jradeg' not in coords or 'jdedeg' not in coords:
                raise UpstreamError('Sesame returned no coordinates for this object name.')
            ra, dec = float(coords['jradeg']), float(coords['jdedeg'])
            if not (math.isfinite(ra) and math.isfinite(dec) and 0 <= ra < 360 and -90 <= dec <= 90):
                raise UpstreamError('Sesame returned invalid sky coordinates.')
            return {
                'name': name, 'catalog_name': canonical_name,
                'type': 'astronomical_object', 'ra': ra, 'dec': dec,
                'coordinate_source': 'CDS Sesame (live) / SIMBAD-NED',
                'note': ('Catalog coordinates, not an epoch-propagated prediction. '
                         'High-proper-motion sources such as WISE 0855 need correction '
                         'for the observing date before precise small-field cutouts.'),
            }
        except (ET.ParseError, UpstreamError, ValueError) as exc:
            failures.append(f'{base.split("/")[2]}: {str(exc)[:95]}')
    raise UpstreamError(
        'CDS object-name resolution unavailable across trusted mirrors. '
        'Try the full designation or enter known RA/Dec manually. '
        + ' | '.join(failures)[:290]
    )


async def resolve_target(name: str | None, ra=None, dec=None, epoch=None, category='all') -> dict:
    if ra is not None and dec is not None:
        return {'name': name or 'Custom coordinates', 'type': 'coordinates',
                'ra': parse_angle(ra, ra=True), 'dec': parse_angle(dec, ra=False),
                'coordinate_source': 'User-supplied coordinates',
                'note': 'Direct ICRS/J2000 interpretation; coordinate frame assumed ICRS.'}
    if not name:
        raise ValueError('Name or coordinates required.')
    name = clean_name(name)
    if name.lower() in SOLAR_IDS:
        return await resolve_horizons(name, epoch)
    if category == 'exoplanets' or re.search(r'\b[b-h]$', name, re.IGNORECASE):
        result = await resolve_exoplanet(name)
        if result:
            return result
        if category == 'exoplanets':
            raise ValueError('Planet not present in NASA Exoplanet Archive.')
    return await resolve_sesame(name)
