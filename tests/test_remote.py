from backend.app.services.remote import validated_url, UpstreamError, get_bytes
import pytest
import httpx

@pytest.mark.parametrize('url',[
 'http://irsa.ipac.caltech.edu/SIA',
 'https://example.com/anything',
 'https://irsa.ipac.caltech.edu.evil.org/ibe/data/spherex/x.fits',
])
def test_untrusted_url(url):
    with pytest.raises(ValueError):validated_url(url)

@pytest.mark.asyncio
async def test_503_retry_and_recovery(monkeypatch):
    attempts=[]
    transport=httpx.MockTransport(lambda req: (attempts.append(req),httpx.Response(503 if len(attempts)<3 else 200,content=b'recovered'))[1])
    orig=httpx.AsyncClient
    monkeypatch.setattr('backend.app.services.remote.httpx.AsyncClient', lambda **kw: orig(transport=transport,**kw))
    result=await get_bytes('https://irsa.ipac.caltech.edu/SIA')
    assert result==b'recovered'
    assert len(attempts)==3

@pytest.mark.asyncio
async def test_503_three_times_fails_and_never_substitutes_data(monkeypatch):
    transport=httpx.MockTransport(lambda req: httpx.Response(503))
    orig=httpx.AsyncClient
    monkeypatch.setattr('backend.app.services.remote.httpx.AsyncClient',lambda **kw: orig(transport=transport,**kw))
    with pytest.raises(UpstreamError):await get_bytes('https://irsa.ipac.caltech.edu/SIA')

@pytest.mark.asyncio
async def test_safe_redirect_to_cds_mirror(monkeypatch):
    visited=[]
    def responder(req):
        visited.append(str(req.url))
        if req.url.host == 'cds.unistra.fr':
            return httpx.Response(302, headers={'Location': 'https://vizier.cfa.harvard.edu/viz-bin/nph-sesame/-oxp?Vega'})
        return httpx.Response(200, content=b'<Sesame><jradeg>279</jradeg></Sesame>')
    transport=httpx.MockTransport(responder)
    orig=httpx.AsyncClient
    monkeypatch.setattr('backend.app.services.remote.httpx.AsyncClient', lambda **kw: orig(transport=transport,**kw))
    result=await get_bytes('https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp?Vega')
    assert result.startswith(b'<Sesame>')
    assert len(visited) == 2
    assert 'vizier.cfa.harvard.edu' in visited[1]


@pytest.mark.asyncio
async def test_reject_redirect_to_untrusted_host(monkeypatch):
    visited=[]
    def responder(req):
        visited.append(str(req.url))
        return httpx.Response(302,headers={'Location':'https://evil.example/private'})
    transport=httpx.MockTransport(responder)
    orig=httpx.AsyncClient
    monkeypatch.setattr('backend.app.services.remote.httpx.AsyncClient',lambda **kw:orig(transport=transport,**kw))
    with pytest.raises(UpstreamError,match='untrusted'):
        await get_bytes('https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp?Vega')
    assert len(visited)==1


@pytest.mark.asyncio
async def test_redirect_cycle_stops(monkeypatch):
    seen=[]
    def responder(req):
        seen.append(str(req.url))
        return httpx.Response(302, headers={'Location':'/cgi-bin/nph-sesame/-oxp?Vega'})
    transport=httpx.MockTransport(responder)
    orig=httpx.AsyncClient
    monkeypatch.setattr('backend.app.services.remote.httpx.AsyncClient', lambda **kw:orig(transport=transport,**kw))
    with pytest.raises(UpstreamError,match='loop'):
        await get_bytes('https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp?Vega')
    assert len(seen)==2


@pytest.mark.asyncio
async def test_relative_redirect_and_initial_query_preserved(monkeypatch):
    seen=[]
    def responder(req):
        seen.append(str(req.url))
        if len(seen)==1:
            return httpx.Response(307,headers={'Location':'/viz-bin/nph-sesame/-oxp?M31'})
        return httpx.Response(200,content=b'ok')
    transport=httpx.MockTransport(responder)
    orig=httpx.AsyncClient
    monkeypatch.setattr('backend.app.services.remote.httpx.AsyncClient',lambda **kw:orig(transport=transport,**kw))
    result=await get_bytes('https://vizier.idia.ac.za/viz-bin/nph-sesame/-oxp',params={'name':'M31'})
    assert result == b'ok'
    assert seen[0].endswith('?name=M31') and seen[1].endswith('?M31')


@pytest.mark.asyncio
async def test_fits_redirect_cannot_escape_spherex_path(monkeypatch):
    def responder(req):
        return httpx.Response(302,headers={'Location': 'https://irsa.ipac.caltech.edu/ibe/data/not-spherex/bogus.fits'})
    transport=httpx.MockTransport(responder)
    orig=httpx.AsyncClient
    monkeypatch.setattr('backend.app.services.remote.httpx.AsyncClient',lambda **kw:orig(transport=transport,**kw))
    with pytest.raises(UpstreamError,match='untrusted'):
        await get_bytes('https://irsa.ipac.caltech.edu/ibe/data/spherex/real.fits',spherex_only=True)
