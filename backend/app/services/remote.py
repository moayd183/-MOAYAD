"""Bounded GET requests to fixed, allow-listed astronomy services."""
import asyncio
import logging
from urllib.parse import urljoin, urlparse
import httpx
from ..settings import TIMEOUT, MAX_REMOTE_BYTES

LOG = logging.getLogger(__name__)
ALLOWED_HOSTS = {
    'irsa.ipac.caltech.edu',
    'exoplanetarchive.ipac.caltech.edu',
    'ssd.jpl.nasa.gov',
    'vizier.idia.ac.za',
    'vizier.cfa.harvard.edu',
    'cds.unistra.fr',
}
RETRYABLE = {429, 500, 502, 503, 504}


class UpstreamError(Exception):
    """Remote astronomy service error, optionally carrying its HTTP status code."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code



def validated_url(url: str, spherex_only: bool = False) -> str:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('The data source URL is not trusted.')
    if spherex_only and (parsed.hostname != 'irsa.ipac.caltech.edu' or not parsed.path.startswith('/ibe/data/spherex/')):
        raise ValueError('This record is not an IRSA SPHEREx FITS product.')
    return url


async def get_bytes(url: str, params: dict | None = None, max_bytes: int = MAX_REMOTE_BYTES, spherex_only: bool = False) -> bytes:
    """Download bounded content; manually follow only allow-listed HTTPS redirects.

    Automatic redirects are disabled so a compromised upstream cannot bypass the
    astronomy-host allowlist. Redirect count and cycles are bounded. The query
    parameters are passed on the *initial* request only; Location then governs
    the next URL as required by HTTP.
    """
    validated_url(url, spherex_only=spherex_only)
    timeout = httpx.Timeout(connect=min(8, TIMEOUT), read=TIMEOUT, write=TIMEOUT, pool=TIMEOUT)
    last_error = None
    for attempt in range(3):
        try:
            current_url, current_params = url, params
            visited = set()
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=False,
                headers={'User-Agent': 'SkyShiftAI/0.2.1 scientific-education; contact via repository'},
            ) as client:
                for _ in range(6):  # initial response + at most five redirects
                    async with client.stream('GET', current_url, params=current_params) as response:
                        requested = str(response.request.url)
                        if requested in visited:
                            raise UpstreamError('Astronomy mirror produced a redirect loop.')
                        visited.add(requested)
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get('location', '')
                            if not location:
                                raise UpstreamError('Astronomy mirror redirected without a destination.')
                            next_url = urljoin(requested, location)
                            try:
                                validated_url(next_url, spherex_only=spherex_only)
                            except ValueError as exc:
                                raise UpstreamError('Astronomy mirror redirected to an untrusted destination.') from exc
                            current_url, current_params = next_url, None
                            continue
                        if response.status_code in RETRYABLE:
                            raise httpx.HTTPStatusError('Transient upstream status', request=response.request, response=response)
                        if response.status_code >= 400:
                            raise UpstreamError(
                                f'Upstream HTTP {response.status_code} ({response.request.url.host}). ' +
                                ('The archive rejected this cutout or query; a different observation may work.'
                                 if response.status_code == 422 else 'Please retry or choose another observation.'),
                                status_code=response.status_code)
                        total = 0
                        parts = []
                        async for chunk in response.aiter_bytes():
                            total += len(chunk)
                            if total > max_bytes:
                                raise UpstreamError('Remote response exceeds configured size limit.')
                            parts.append(chunk)
                        return b''.join(parts)
                raise UpstreamError('Astronomy mirror exceeded the safe redirect limit.')
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_error = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in RETRYABLE:
                break
            LOG.warning('Remote astronomy request retry %s: %s', attempt + 1, str(exc)[:160])
            if attempt < 2:
                await asyncio.sleep(0.3 * (2 ** attempt))
    raise UpstreamError(f'Astronomy service unavailable after retries: {type(last_error).__name__}')
