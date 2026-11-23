"""Integration tests for the actual website API, sessions and shared database."""
import os
import tempfile
import unittest
from app import create_app
from web import attach

class WebsiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.app=create_app(os.path.join(self.tmp.name,'web.sqlite'))
        attach(self.app)
        self.resident=self.app.test_client()
        self.collector=self.app.test_client()
        self.other=self.app.test_client()
    def tearDown(self): self.tmp.cleanup()
    def login(self,client,code='COL-01',pin='1234'):
        return client.post('/api/collector-login',json={'collector_id':code,'pin':pin})
    def test_shared_workflow_and_permissions(self):
        self.assertEqual(self.resident.get('/api/requests').status_code,401)
        self.assertEqual(self.login(self.collector,pin='bad').status_code,401)
        self.assertEqual(self.login(self.collector).status_code,200)
        self.login(self.other,'COL-02','5678')
        tid=self.resident.post('/api/requests',json={'gate_id':'KTM-W10-0042','waste_type':'both'}).json['ticket']['id']
        duplicate=self.resident.post('/api/requests',json={'gate_id':'KTM-W10-0042','waste_type':'green'}).json
        self.assertTrue(duplicate['duplicate'])
        rows=self.collector.get('/api/requests').json['requests']
        self.assertEqual(rows[0]['id'],tid);self.assertEqual(rows[0]['lat'],27.6893)
        self.assertEqual(self.collector.post(f'/api/requests/{tid}/assign',json={'collector_id':2}).status_code,403)
        self.assertEqual(self.collector.post(f'/api/requests/{tid}/assign',json={'collector_id':1}).status_code,200)
        self.assertEqual(self.other.post(f'/api/requests/{tid}/assign',json={'collector_id':2}).status_code,409)
        data={'collector_id':1,'scanned_gate_id':'wrong','segregation_verified':True}
        self.assertEqual(self.collector.post(f'/api/requests/{tid}/collect',json=data).status_code,422)
        data['scanned_gate_id']='KTM-W10-0042'
        complete=self.collector.post(f'/api/requests/{tid}/collect',json=data)
        self.assertEqual(complete.status_code,201);self.assertEqual(complete.json['points_awarded'],20)
        self.assertEqual(self.collector.post(f'/api/requests/{tid}/collect',json=data).status_code,409)
        # Another browser reads the database result, without localStorage.
        h=self.app.test_client().get('/api/households/KTM-W10-0042').json
        self.assertEqual(h['green_points_balance'],20);self.assertEqual(h['streak_count'],1)
        self.assertEqual(h['latest_ticket']['status'],'completed')
        self.assertTrue(h['latest_ticket']['verified_clean'])
        self.assertEqual(self.collector.get('/api/collections').json['collections'][0]['waste_type'],'both')
        self.collector.post('/api/collector-logout')
        self.assertEqual(self.collector.get('/api/requests').status_code,401)
    def test_location_and_public_files(self):
        self.login(self.collector)
        route='/api/collectors/1/location'
        self.assertEqual(self.collector.post(route,json={'lat':999,'lng':85}).status_code,400)
        result=self.collector.post(route,json={'lat':27.7,'lng':85.3,'source':'simulation'})
        self.assertEqual(result.json['source'],'simulation')
        self.assertEqual(self.collector.get(route).json['lat'],27.7)
        self.assertEqual(self.collector.get('/api/collectors/2/location').status_code,403)
        for route in ['/','/resident/dashboard.html','/collector/index.html','/assets/tringgg-logo.png','/js/vendor/leaflet/leaflet.js']:
            response=self.resident.get(route)
            self.assertEqual(response.status_code,200,route)
            response.close()
        self.assertEqual(self.resident.get('/backend/app.py').status_code,404)
        self.assertEqual(self.resident.get('/data/backend.sqlite').status_code,404)
        self.assertNotIn('Access-Control-Allow-Origin',self.resident.get('/api/health').headers)
    def test_eight_verified_pickups_unlock_discount_and_mixed_resets(self):
        self.login(self.collector)
        for index in range(9):
            tid=self.resident.post('/api/requests',json={'gate_id':'KTM-W10-0042','waste_type':'green'}).json['ticket']['id']
            self.collector.post(f'/api/requests/{tid}/assign',json={'collector_id':1})
            self.collector.post(f'/api/requests/{tid}/collect',json={'collector_id':1,'scanned_gate_id':'KTM-W10-0042','segregation_verified':index<8})
            h=self.resident.get('/api/households/KTM-W10-0042').json
            if index==7: self.assertEqual(h['monthly_bill_npr'],320)
        self.assertEqual(h['green_points_balance'],80);self.assertEqual(h['streak_count'],0);self.assertEqual(h['monthly_bill_npr'],400)
