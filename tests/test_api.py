import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client=TestClient(app)

def test_health():
    response=client.get('/api/health')
    assert response.status_code==200
    assert response.json()['data_mode']=='real_only'

def test_spa_home():
    r=client.get('/')
    assert r.status_code==200
    assert 'SkyShift AI' in r.text

def test_bad_inputs():
    r=client.post('/api/spherex/observations/search',json={'ra':400,'dec':0})
    assert r.status_code==422

def test_unregistered_record_cannot_be_downloaded():
    r=client.post('/api/spherex/frames/build',json={'observation':{
        'obs_id':'fake','access_url':'https://irsa.ipac.caltech.edu/ibe/data/spherex/fake.fits'},
        'ra':10,'dec':10})
    assert r.status_code==403

def test_catalog_solar_does_not_claim_static_positions():
    items=client.get('/api/planets/solar').json()['items']
    assert any(x['name']=='Mars' for x in items)
    assert all(x['coordinates'] is None for x in items)


def test_validation_reports_not_live_tested():
    data=client.get('/api/targets/validation').json()
    assert len(data['targets'])==5
    assert all(x['status']=='not_live_tested' for x in data['targets'])

def test_lightcurve_rejects_duplicate_frames():
    frame='a'*64
    response=client.post('/api/analysis/lightcurve',json={'frame_ids':[frame,frame]})
    assert response.status_code==422


def test_lightcurve_rejects_invalid_frame_id():
    response=client.post('/api/analysis/lightcurve',json={'frame_ids':['bad','wrong']})
    assert response.status_code==422
