"""Automated tests.  Run:  python -m unittest -v"""
import os
import tempfile
import threading
import unittest

import db
import seed
import services
from app import create_app

SITA = "9800000001"        # household KTM-W10-0042
SITA_GATE = "KTM-W10-0042"
RAM_GATE = "KTM-W10-0043"


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = os.path.join(self.tmp.name, "test.db")
        self.client = create_app(self.path).test_client()
        conn = db.connect(self.path)
        seed.seed(conn)
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    # helpers
    def missed_call(self, phone=SITA):
        return self.client.post("/api/webhooks/missed-call", json={"from": phone})

    def collect(self, ticket_id, gate=SITA_GATE, collector=1, verified=True):
        return self.client.post(
            f"/api/requests/{ticket_id}/collect",
            json={"scanned_gate_id": gate, "collector_id": collector, "segregation_verified": verified},
        )


class MissedCallTests(ApiTestCase):
    def test_missed_call_creates_ticket(self):
        r = self.missed_call("+977 980-0000001")  # messy formatting is fine
        self.assertEqual(r.status_code, 201)
        data = r.get_json()
        self.assertEqual(data["outcome"], "created")
        self.assertEqual(data["ticket"]["status"], "requested")
        self.assertEqual(data["ticket"]["waste_type"], "both")
        self.assertEqual(data["ticket"]["source"], "missed_call")
        self.assertEqual(data["ticket"]["gate_id"], SITA_GATE)

    def test_repeat_calls_return_same_ticket(self):
        first = self.missed_call().get_json()["ticket"]["id"]
        for _ in range(3):
            r = self.missed_call()
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.get_json()["outcome"], "duplicate")
            self.assertEqual(r.get_json()["ticket"]["id"], first)
        self.assertEqual(self.client.get("/api/requests").get_json()["count"], 1)

    def test_unregistered_number_makes_no_ticket(self):
        r = self.missed_call("9899999999")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["outcome"], "unregistered")
        self.assertEqual(self.client.get("/api/requests").get_json()["count"], 0)

    def test_bad_phone_is_rejected(self):
        self.assertEqual(self.missed_call("12345").status_code, 400)
        self.assertEqual(self.client.post("/api/webhooks/missed-call", json={}).status_code, 400)


class RequestTests(ApiTestCase):
    def test_app_request_and_lock(self):
        r = self.client.post("/api/requests", json={"gate_id": "ktm-w10-0042", "waste_type": "red"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["ticket"]["waste_type"], "red")
        again = self.client.post("/api/requests", json={"gate_id": SITA_GATE, "waste_type": "green"})
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.get_json()["duplicate"])

    def test_lock_covers_both_channels(self):
        self.missed_call()
        r = self.client.post("/api/requests", json={"gate_id": SITA_GATE, "waste_type": "both"})
        self.assertTrue(r.get_json()["duplicate"])

    def test_validation(self):
        self.assertEqual(self.client.post("/api/requests", json={"gate_id": "KTM-NOPE-1"}).status_code, 404)
        self.assertEqual(self.client.post("/api/requests", json={"gate_id": SITA_GATE, "waste_type": "blue"}).status_code, 400)
        self.assertEqual(self.client.post("/api/requests", json={}).status_code, 400)
        self.assertEqual(self.client.get("/api/requests?status=nonsense").status_code, 400)
        self.assertEqual(self.client.get("/api/requests/999").status_code, 404)

    def test_cancel_releases_lock(self):
        tid = self.missed_call().get_json()["ticket"]["id"]
        self.assertEqual(self.client.post(f"/api/requests/{tid}/cancel").get_json()["status"], "cancelled")
        r = self.missed_call()
        self.assertEqual(r.status_code, 201)
        self.assertNotEqual(r.get_json()["ticket"]["id"], tid)
        # cancelling something already cancelled is a conflict
        self.assertEqual(self.client.post(f"/api/requests/{tid}/cancel").status_code, 409)

    def test_old_ticket_expires(self):
        old = self.missed_call().get_json()["ticket"]["id"]
        conn = db.connect(self.path)
        conn.execute("UPDATE pickup_requests SET created_at = '2020-01-01T00:00:00Z' WHERE id = ?", (old,))
        conn.close()
        r = self.missed_call()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.get(f"/api/requests/{old}").get_json()["status"], "expired")

    def test_dashboard_read_expires_ticket_without_another_request(self):
        old = self.missed_call().get_json()["ticket"]["id"]
        conn = db.connect(self.path)
        conn.execute("UPDATE pickup_requests SET created_at='2020-01-01T00:00:00Z' WHERE id=?", (old,))
        conn.close()
        house = self.client.get(f"/api/households/{SITA_GATE}").get_json()
        self.assertIsNone(house["active_ticket"])
        self.assertEqual(house["latest_ticket"]["status"], "expired")
        self.assertEqual(self.client.get('/api/requests?status=requested').get_json()['count'], 0)
        self.assertEqual(self.client.post(f'/api/requests/{old}/assign', json={'collector_id':1}).status_code, 409)

    def test_registration_uses_next_gate_number(self):
        response = self.client.post('/api/households', json={'name':'Test resident','phone':'9849999999','ward':10,'address':'Test address'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()['gate_id'], 'KTM-W10-0044')

    def test_assign_and_filters(self):
        tid = self.missed_call().get_json()["ticket"]["id"]
        t = self.client.post(f"/api/requests/{tid}/assign", json={"collector_id": 1}).get_json()
        self.assertEqual(t["status"], "assigned")
        self.assertEqual(t["collector_name"], "Hari Prasad")
        self.assertEqual(self.client.get("/api/collectors/1/queue").get_json()["count"], 1)
        self.assertEqual(self.client.get("/api/collectors/2/queue").get_json()["count"], 0)
        self.assertEqual(self.client.get("/api/requests?status=assigned&ward=10").get_json()["count"], 1)
        self.assertEqual(self.client.get("/api/requests?ward=16").get_json()["count"], 0)
        self.assertEqual(self.client.post(f"/api/requests/{tid}/assign", json={"collector_id": 99}).status_code, 404)

    def test_lock_holds_under_simultaneous_calls(self):
        results = []

        def worker():
            conn = db.connect(self.path)
            try:
                _ticket, created = services.create_request(conn, 1, "both", "missed_call")
                results.append(created)
            finally:
                conn.close()

        threads = [threading.Thread(target=worker) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), 12)
        self.assertEqual(results.count(True), 1)  # exactly one ticket was created


class CollectionTests(ApiTestCase):
    def test_verified_pickup_awards_points(self):
        tid = self.missed_call().get_json()["ticket"]["id"]
        r = self.collect(tid, verified=True)
        self.assertEqual(r.status_code, 201)
        data = r.get_json()
        self.assertEqual(data["points_awarded"], 20)  # waste_type both
        self.assertEqual(data["green_points_balance"], 20)
        self.assertEqual(data["ticket"]["status"], "completed")
        self.assertEqual(data["ticket"]["collector_id"], 1)
        # event saved
        events = self.client.get("/api/collections").get_json()
        self.assertEqual(events["count"], 1)
        self.assertTrue(events["collections"][0]["segregation_verified"])

    def test_unverified_pickup_earns_nothing(self):
        tid = self.missed_call().get_json()["ticket"]["id"]
        data = self.collect(tid, verified=False).get_json()
        self.assertEqual(data["points_awarded"], 0)
        self.assertEqual(data["ticket"]["status"], "completed")
        summary = self.client.get(f"/api/households/{SITA_GATE}").get_json()
        self.assertEqual(summary["green_points_balance"], 0)
        self.assertEqual(summary["pickups_completed"], 1)

    def test_wrong_qr_is_rejected_and_ticket_stays_open(self):
        tid = self.missed_call().get_json()["ticket"]["id"]
        r = self.collect(tid, gate=RAM_GATE)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.get_json()["error"]["code"], "gate_mismatch")
        self.assertEqual(self.client.get(f"/api/requests/{tid}").get_json()["status"], "requested")

    def test_cannot_collect_twice(self):
        tid = self.missed_call().get_json()["ticket"]["id"]
        self.assertEqual(self.collect(tid).status_code, 201)
        r = self.collect(tid)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["error"]["code"], "already_collected")
        self.assertEqual(self.client.get(f"/api/households/{SITA_GATE}").get_json()["green_points_balance"], 20)

    def test_completing_releases_the_lock(self):
        tid = self.missed_call().get_json()["ticket"]["id"]
        self.collect(tid)
        again = self.client.post("/api/requests", json={"gate_id": SITA_GATE, "waste_type": "green"})
        self.assertEqual(again.status_code, 201)
        self.assertNotEqual(again.get_json()["ticket"]["id"], tid)

    def test_other_collectors_cannot_take_an_assigned_ticket(self):
        tid = self.missed_call().get_json()["ticket"]["id"]
        self.client.post(f"/api/requests/{tid}/assign", json={"collector_id": 1})
        r = self.collect(tid, collector=2)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["error"]["code"], "assigned_to_other_collector")

    def test_points_add_up_across_pickups(self):
        t1 = self.client.post("/api/requests", json={"gate_id": SITA_GATE, "waste_type": "green"}).get_json()["ticket"]["id"]
        self.collect(t1)  # 10
        t2 = self.client.post("/api/requests", json={"gate_id": SITA_GATE, "waste_type": "both"}).get_json()["ticket"]["id"]
        self.collect(t2)  # 20
        history = self.client.get(f"/api/households/{SITA_GATE}/points").get_json()
        self.assertEqual(history["green_points_balance"], 30)
        self.assertEqual([h["points"] for h in history["history"]], [20, 10])

    def test_collect_validation(self):
        tid = self.missed_call().get_json()["ticket"]["id"]
        url = f"/api/requests/{tid}/collect"
        self.assertEqual(self.client.post(url, json={"collector_id": 1, "segregation_verified": True}).status_code, 400)
        self.assertEqual(self.client.post(url, json={"scanned_gate_id": SITA_GATE, "collector_id": 1}).status_code, 400)
        self.assertEqual(
            self.client.post(url, json={"scanned_gate_id": SITA_GATE, "collector_id": 77, "segregation_verified": True}).status_code, 404
        )
        self.assertEqual(self.client.post("/api/requests/999/collect", json={"scanned_gate_id": SITA_GATE, "collector_id": 1, "segregation_verified": True}).status_code, 404)


class KathmanduTests(ApiTestCase):
    def test_nepal_mobile_numbers_only(self):
        self.assertEqual(self.missed_call("9199999999").status_code, 400)   # not a 96/97/98 number
        self.assertEqual(self.missed_call("+977-9800000001").status_code, 201)

    def test_messages_in_nepali_and_english(self):
        data = self.missed_call().get_json()
        self.assertIn("received", data["message"])
        self.assertIn("दर्ता", data["message_ne"])

    def test_times_shown_in_nepal_time(self):
        t = self.missed_call().get_json()["ticket"]
        self.assertTrue(t["created_at_npt"].endswith("NPT"))
        # NPT is UTC+05:45, so the minutes differ by 45 (mod 60) from the UTC value
        utc_min = int(t["created_at"][14:16])
        npt_min = int(t["created_at_npt"][14:16])
        self.assertEqual((utc_min + 45) % 60, npt_min)

    def test_ward_must_be_1_to_32(self):
        self.assertEqual(self.client.get("/api/requests?ward=33").status_code, 400)
        self.assertEqual(self.client.get("/api/requests?ward=0").status_code, 400)

    def test_register_household(self):
        r = self.client.post("/api/households", json={"name": "Maya Karki", "phone": "9841234567", "ward": 10, "address": "Baneshwor"})
        self.assertEqual(r.status_code, 201)
        gate = r.get_json()["gate_id"]
        # Seeded ward 10 gates end in 0042 and 0043; continue their sequence.
        self.assertEqual(gate, "KTM-W10-0044")
        # the new household can use the missed-call flow straight away
        call = self.missed_call("9841234567")
        self.assertEqual(call.get_json()["ticket"]["gate_id"], gate)
        # same phone again, or a bad ward, is refused
        dup = self.client.post("/api/households", json={"name": "X", "phone": "9841234567", "ward": 10})
        self.assertEqual(dup.status_code, 409)
        self.assertEqual(self.client.post("/api/households", json={"name": "X", "phone": "9851234567", "ward": 99}).status_code, 400)

    def test_collection_message_has_points(self):
        tid = self.missed_call().get_json()["ticket"]["id"]
        data = self.collect(tid).get_json()
        self.assertIn("20", data["message"])
        self.assertIn("हरित अंक", data["message_ne"])


if __name__ == "__main__":
    unittest.main()
