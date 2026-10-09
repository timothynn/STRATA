from fastapi.testclient import TestClient
from app.domain import downstream,upstream
from app.main import create_app

def test_lineage():
    assert 'dash_revenue' in downstream('src_orders')
    assert 'src_payments' in upstream('dash_revenue')
    assert downstream('dash_ops')==[]

def test_incident_propagation_and_recovery(tmp_path):
    with TestClient(create_app(str(tmp_path/'test.db'))) as c:
        base=c.get('/api/overview').json()
        assert base['summary']['healthy']==9
        injected=c.post('/api/fault',json={'node_id':'src_orders','fault':'schema'})
        assert injected.status_code==200
        snap=injected.json()['overview']
        assert snap['summary']['failing']==1
        assert snap['summary']['impacted']>=3
        assert c.post('/api/fault',json={'node_id':'src_orders','fault':'schema'}).status_code==409
        checks=c.get('/api/checks').json()['checks']
        assert any(x['dataset']=='src_orders' and x['type']=='schema' and x['status']=='FAIL' for x in checks)
        assert c.post('/api/recover',json={'node_id':'src_orders'}).status_code==200
        assert c.get('/api/overview').json()['summary']['healthy']==9
        incidents=c.get('/api/incidents').json()['incidents']
        assert incidents[0]['status']=='RESOLVED'
        assert c.post('/api/fault',json={'node_id':'invalid','fault':'stale'}).status_code==404
        assert c.post('/api/fault',json={'node_id':'src_orders','fault':'broken'}).status_code==422

def test_reset(tmp_path):
    c=TestClient(create_app(str(tmp_path/'strata.db')))
    c.post('/api/fault',json={'node_id':'src_inventory','fault':'stale'})
    assert c.post('/api/reset').json()['overview']['summary']['healthy']==9
