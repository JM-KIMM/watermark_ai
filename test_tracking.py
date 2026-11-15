"""Integration tests for finite IP retention, explicit cases and QR HTTP access."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tracking_db import Store, create_server


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/"access.sqlite3")
        self.campaign = self.store.create_campaign("sample", "http://127.0.0.1:8765", max_events=2, retention_days=1)
        self.url = self.store.issue(self.campaign, 1, "12")
        self.token = self.url.rsplit("/", 1)[1]
        self.store.activate(self.campaign)

    def tearDown(self):
        self.temp.cleanup()

    def test_real_http_ip_and_spoofed_header(self):
        server = create_server(self.store, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = f"http://127.0.0.1:{server.server_port}/q/{self.token}"
        try:
            with urlopen(Request(endpoint, method="HEAD")) as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(self.store.scans(), [])
            with urlopen(Request(endpoint, headers={"X-Forwarded-For": "192.0.2.99"})) as response:
                self.assertEqual(json.load(response)["status"], "access recorded")
            scans = self.store.scans()
            self.assertEqual(len(scans), 1)
            self.assertEqual(scans[0]["ip"], "127.0.0.1")
            self.assertEqual(scans[0]["question"], "12")
            with self.assertRaises(HTTPError) as error:
                urlopen(f"http://127.0.0.1:{server.server_port}/admin")
            self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_cap_retention_and_linked_case(self):
        self.store.access(self.token, "192.0.2.1")
        first = self.store.scans()[0]["id"]
        identifier = self.store.save_case("test-reference", "synthetic test record", scan_id=first)
        self.store.access(self.token, "192.0.2.2")
        self.store.access(self.token, "192.0.2.3")
        self.assertEqual(len(self.store.scans()), 2)
        self.assertIsNone(self.store.cases()[0]["scan_id"])
        self.store.save_case("test-reference", "reviewed test", status="기각", case_id=identifier)
        self.assertEqual(self.store.cases()[0]["status"], "기각")
        self.store.cleanup(now=time.time()+2*86400)
        self.assertEqual(self.store.scans(), [])

    def test_expired_revoked_and_unknown(self):
        self.assertEqual(self.store.access("invalid", "127.0.0.1"), 404)
        self.store.revoke(self.campaign)
        self.assertEqual(self.store.access(self.token, "127.0.0.1"), 410)
        self.store.activate(self.campaign)
        with self.store.connect() as db:
            db.execute("UPDATE campaigns SET expires=? WHERE id=?", (time.time()-1, self.campaign))
        self.assertEqual(self.store.access(self.token, "127.0.0.1"), 410)
        self.assertEqual(self.store.scans(), [])

    def test_case_expiry_delete_and_validation(self):
        case = self.store.save_case("synthetic", "test", days=1)
        self.store.cleanup(now=time.time()+2*86400)
        self.assertEqual(self.store.cases(), [])
        case = self.store.save_case("synthetic", "test")
        self.store.delete_case(case)
        self.assertEqual(self.store.cases(), [])
        for days in (0, 91):
            with self.assertRaises(ValueError):
                self.store.create_campaign("bad", "http://127.0.0.1:8765", days=days)
        with self.assertRaises(ValueError):
            self.store.create_campaign("bad", "http://host/admin?x=1")


if __name__ == "__main__":
    unittest.main()
