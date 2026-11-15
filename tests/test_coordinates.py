import pytest
from backend.app.services.resolver import parse_angle, tap_literal, resolve_target

@pytest.mark.parametrize('value,ra,expected',[
 ('08:55:10.831',True,133.795129167),
 ('-07:14:42.53',False,-7.245147222),
 ('133.795129',True,133.795129),
 ('-7.245147',False,-7.245147),
 ('08h55m10.831s',True,133.795129167),
])
def test_angles(value,ra,expected):
    assert abs(parse_angle(value,ra=ra)-expected)<1e-6

@pytest.mark.parametrize('value,ra',['360',True] if False else [('360',True),('90.1',False),('25:78:00',True)])
def test_angle_reject(value,ra):
    with pytest.raises(ValueError):parse_angle(value,ra=ra)

def test_safe_tap_escaping():
    assert tap_literal("O'Kepler") == "'O''Kepler'"

@pytest.mark.asyncio
async def test_direct_coordinates_never_trigger_network(monkeypatch):
    async def forbidden(*args,**kwargs):raise AssertionError('unexpected request')
    monkeypatch.setattr('backend.app.services.resolver.get_bytes',forbidden)
    data=await resolve_target(None, '08h55m10.831s','-07:14:42.53')
    assert data['coordinate_source']=='User-supplied coordinates'
    assert 133<data['ra']<134

@pytest.mark.asyncio
async def test_wise_alias_uses_correct_sesame_query_form(monkeypatch):
    seen=[]
    async def fake_get(url,**kwargs):
        seen.append(url)
        return b'<Sesame><Target><Resolver><jradeg>133.8</jradeg><jdedeg>-7.24</jdedeg></Resolver></Target></Sesame>'
    monkeypatch.setattr('backend.app.services.resolver.get_bytes',fake_get)
    data=await resolve_target('WISE 0855')
    assert data['name']=='WISE 0855'
    assert data['catalog_name']=='WISE J085510.83-071442.5'
    assert seen[0].endswith('?WISE%20J085510.83-071442.5')
    assert data['coordinate_source'].startswith('CDS Sesame (live)')


@pytest.mark.asyncio
async def test_sesame_fallback_to_harvard_mirror(monkeypatch):
    from backend.app.services.remote import UpstreamError
    seen=[]
    async def fake_get(url,**kwargs):
        seen.append(url)
        if 'idia.ac.za' in url:
            raise UpstreamError('mirror degraded')
        return b'<Sesame xmlns="urn:test"><Resolver><jradeg>20.2</jradeg><jdedeg>10.1</jdedeg></Resolver></Sesame>'
    monkeypatch.setattr('backend.app.services.resolver.get_bytes',fake_get)
    data=await resolve_target('Vega')
    assert data['ra']==20.2
    assert 'vizier.cfa.harvard.edu' in seen[1]
    assert len(seen)==2


@pytest.mark.asyncio
async def test_sesame_does_not_fabricate_if_all_fail(monkeypatch):
    from backend.app.services.remote import UpstreamError
    async def fake_get(url,**kwargs):
        raise UpstreamError('remote down')
    monkeypatch.setattr('backend.app.services.resolver.get_bytes',fake_get)
    with pytest.raises(UpstreamError,match='trusted mirrors'):
        await resolve_target('WISE 0855')
