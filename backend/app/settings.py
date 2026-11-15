"""Central settings. No external source is silently replaced with demo data."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv('SKYSHIFT_DATA_DIR', str(ROOT / 'local_data')))
CACHE_DIR = DATA_DIR / 'cache'
FRAMES_DIR = CACHE_DIR / 'frames'
DB_PATH = DATA_DIR / 'observations.sqlite3'
SIA_ENDPOINT = 'https://irsa.ipac.caltech.edu/SIA'
EXOPLANET_ENDPOINT = 'https://exoplanetarchive.ipac.caltech.edu/TAP/sync'
HORIZONS_ENDPOINT = 'https://ssd.jpl.nasa.gov/api/horizons.api'
# Current officially documented Sesame mirror API format is /-oxp?Object_Name.
# The Strasbourg CDS endpoint has been degraded since November 2026.
SESAME_ENDPOINTS = [
    'https://vizier.idia.ac.za/viz-bin/nph-sesame/-oxp',
    'https://vizier.cfa.harvard.edu/viz-bin/nph-sesame/-oxp',
    'https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp',
]
COLLECTIONS = ('spherex_dr1', 'spherex_qr3', 'spherex_dr1_deep', 'spherex_qr3_deep')
MAX_REMOTE_BYTES = int(os.getenv('SKYSHIFT_MAX_REMOTE_BYTES', '45000000'))
TIMEOUT = float(os.getenv('SKYSHIFT_HTTP_TIMEOUT', '18'))
FRONTEND_DIR = ROOT / 'frontend' / 'static'
for directory in (CACHE_DIR, FRAMES_DIR):
    directory.mkdir(parents=True, exist_ok=True)
