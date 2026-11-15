import pytest
from backend.app.services.spherex import parse_votable, safe_record, frame_key, cutout_url, search_spherex, mjd_to_iso
from backend.app.models import SearchRequest

VOTABLE=b'''<?xml version="1.0"?><VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE><TABLE>
<FIELD name="obs_id" datatype="char" arraysize="*"/><FIELD name="obs_collection" datatype="char" arraysize="*"/>
<FIELD name="s_ra" datatype="double"/><FIELD name="s_dec" datatype="double"/><FIELD name="t_min" datatype="double"/>
<FIELD name="energy_bandpassname" datatype="char" arraysize="*"/><FIELD name="access_url" datatype="char" arraysize="*"/>
<DATA><TABLEDATA><TR><TD>obs001</TD><TD>spherex_dr1</TD><TD>133.8</TD><TD>-7.2</TD><TD>60123.1</TD><TD>SPHEREx-D3</TD>
<TD>https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/f.fits</TD></TR></TABLEDATA></DATA>
</TABLE></RESOURCE></VOTABLE>'''

def test_parse_real_votable_fields():
    rows=parse_votable(VOTABLE)
    assert len(rows)==1
    a=safe_record(rows[0],'spherex_dr1')
    assert a['obs_id']=='obs001'
    assert a['detector']==3
    assert a['data_mode']=='real'
    assert a['date'] is not None

def test_source_restricted():
    row=parse_votable(VOTABLE)[0]
    row['access_url']='https://example.org/not-an-observation.fits'
    assert safe_record(row,'spherex_dr1') is None


def test_no_cross_target_cache_collisions():
    obs=safe_record(parse_votable(VOTABLE)[0],'spherex_dr1')
    assert frame_key(obs,133.7,-7.2,10)!=frame_key(obs,133.8,-7.2,10)
    assert frame_key(obs,133.8,-7.2,10)!=frame_key(obs,133.8,-7.2,20)
    assert 'center=133.800000000%2C-7.200000000' in cutout_url(obs['access_url'],133.8,-7.2,10)

@pytest.mark.asyncio
async def test_search_uses_actual_coordinate_and_deduplicates(monkeypatch):
    seen=[]
    async def fetch(url,params=None,max_bytes=None):
        seen.append(params)
        return VOTABLE
    monkeypatch.setattr('backend.app.services.spherex.get_bytes',fetch)
    result=await search_spherex(SearchRequest(ra=133.8,dec=-7.2,collections=['spherex_dr1','spherex_qr3']))
    assert result['count']==1
    assert result['data_mode']=='real'
    assert len(seen)==2
    assert all('133.800000000 -7.200000000' in x['POS'] for x in seen)

@pytest.mark.asyncio
async def test_different_coordinates_generate_different_sia_queries(monkeypatch):
    poses=[]
    async def fetch(url,params=None,max_bytes=None):
        poses.append(params['POS']);return VOTABLE
    monkeypatch.setattr('backend.app.services.spherex.get_bytes',fetch)
    await search_spherex(SearchRequest(ra=4,dec=-3,collections=['spherex_dr1']))
    await search_spherex(SearchRequest(ra=90,dec=12,collections=['spherex_dr1']))
    assert poses[0]!=poses[1]

@pytest.mark.asyncio
async def test_no_data_no_fabricated_fallback(monkeypatch):
    empty=b'<VOTABLE><RESOURCE><TABLE><DATA><TABLEDATA/></DATA></TABLE></RESOURCE></VOTABLE>'
    async def fetch(*args,**kwargs):return empty
    monkeypatch.setattr('backend.app.services.spherex.get_bytes',fetch)
    out=await search_spherex(SearchRequest(ra=42,dec=20))
    assert out['count']==0 and out['observations']==[]
    assert out['status']=='empty' and out['archive_rows']==0


def test_reject_bad_collection():
    from pydantic import ValidationError
    with pytest.raises(ValidationError): SearchRequest(ra=4,dec=10,collections=['faux'])


@pytest.mark.asyncio
async def test_archive_rows_with_unsupported_links_are_not_reported_empty(monkeypatch):
    async def fetch(*args,**kwargs):
        return VOTABLE.replace(b'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/f.fits', b'https://example.org/spherex.fits')
    monkeypatch.setattr('backend.app.services.spherex.get_bytes',fetch)
    result=await search_spherex(SearchRequest(ra=133.8,dec=-7.2,collections=['spherex_dr1']))
    assert result['status']=='unsupported'
    assert result['archive_rows']==1
    assert result['unsupported_rows']==1
    assert result['count']==0


@pytest.mark.asyncio
async def test_archive_rows_rejected_by_detector_filter_are_reported(monkeypatch):
    async def fetch(*args,**kwargs): return VOTABLE
    monkeypatch.setattr('backend.app.services.spherex.get_bytes',fetch)
    result=await search_spherex(SearchRequest(ra=133.8,dec=-7.2,collections=['spherex_dr1'],detector=4))
    assert result['status']=='filtered'
    assert result['archive_rows']==1
    assert result['filtered_out']==1


def test_votable_field_id_fallback():
    payload=VOTABLE.replace(b'FIELD name="access_url"', b'FIELD ID="access_url"')
    assert parse_votable(payload)[0]['access_url'].startswith('https://')
