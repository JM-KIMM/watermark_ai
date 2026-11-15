from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from csv_store import CSVStore, safe_cell, restore_cell, export_csv
from tracking_db import Store, RequestBudget, create_server, open_store
from migrate_legacy import migrate


class CSVTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = CSVStore(self.root/"records")
        self.campaign = self.store.create_campaign("sample", "http://127.0.0.1:8765", max_events=3, retention_days=1)
        self.token = self.store.issue(self.campaign, 1, "3").rsplit("/", 1)[1]
        self.store.activate(self.campaign)

    def tearDown(self):
        self.temp.cleanup()

    def test_csv_cap_cases_expiry_and_roundtrip(self):
        self.store.access(self.token, "192.0.2.1")
        first = self.store.scans()[0]["id"]
        case = self.store.save_case("test", '=HYPERLINK("https://example.invalid")', scan_id=first)
        for i in range(2, 6):
            self.store.access(self.token, f"192.0.2.{i}")
        self.assertEqual(len(self.store.scans()), 3)
        self.assertIsNone(self.store.cases()[0]["scan_id"])
        reopened = CSVStore(self.root/"records")
        self.assertEqual(reopened.cases()[0]["notes"], '=HYPERLINK("https://example.invalid")')
        with (self.root/"records"/"cases.csv").open(encoding="utf-8-sig", newline="") as handle:
            self.assertTrue(next(csv.DictReader(handle))["notes"].startswith("'="))
        self.store.save_case("test", "reviewed", status="기각", case_id=case)
        self.assertEqual(self.store.cases()[0]["status"], "기각")
        self.store.cleanup(now=time.time()+2*86400)
        self.assertEqual(self.store.scans(), [])
        self.store.delete_case(case)
        self.assertEqual(self.store.cases(), [])

    def test_concurrent_writes_keep_unique_ids_and_capacity(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            codes = list(pool.map(lambda i: CSVStore(self.root/"records").access(self.token, f"192.0.2.{i+1}"), range(12)))
        self.assertEqual(codes, [200]*12)
        self.assertEqual(len(self.store.scans()), 3)
        self.assertEqual(len({r["id"] for r in self.store.scans()}), 3)

    def test_excel_escape_roundtrip(self):
        for text in ["=1+1", " +SUM(A1)", "@command", "-1", "\t=2", "'=1", "''", "normal", "＝1+1", "\ufeff=1"]:
            self.assertEqual(restore_cell(safe_cell(text)), text)
        export_csv(self.root/"export.csv", [{"notes": "=1+1"}])
        self.assertIn("'=1+1", (self.root/"export.csv").read_text(encoding="utf-8-sig"))

    def test_reissue_same_question_preserves_comparison_payload(self):
        again = self.store.issue(self.campaign, 1, "3")
        self.assertEqual(again.rsplit("/", 1)[1], self.token)
        self.assertEqual(self.store.campaigns()[0]["issued"], 1)

    def test_vpn_rotation_cannot_bypass_token_or_global_budget(self):
        budget = RequestBudget(total=50, per_token=2)
        self.assertTrue(budget.allow("192.0.2.1", "same", now=1))
        self.assertTrue(budget.allow("192.0.2.2", "same", now=1))
        self.assertFalse(budget.allow("192.0.2.3", "same", now=1))
        self.assertTrue(budget.allow("192.0.2.3", "same", now=62))
        budget = RequestBudget(total=1)
        self.assertTrue(budget.allow("192.0.2.1", "a", now=1))
        self.assertFalse(budget.allow("192.0.2.2", "b", now=1))

    def test_real_http_rate_limit_and_file_failure(self):
        server = create_server(self.store, port=0, request_budget=1)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/q/{self.token}"
        try:
            with urlopen(url, timeout=3) as response:
                self.assertEqual(response.status, 200)
            with self.assertRaises(HTTPError) as error:
                urlopen(url, timeout=3)
            self.assertEqual(error.exception.code, 429)
            self.assertEqual(self.store.scans()[0]["ip"], "127.0.0.1")
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_storage_error_returns_503_and_recovers(self):
        actual = self.store.access
        def fail(*args, **kwargs):
            raise OSError("simulated disk error")
        self.store.access = fail
        server = create_server(self.store, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        url = f"http://127.0.0.1:{server.server_port}/q/{self.token}"
        try:
            with self.assertRaises(HTTPError) as error:
                urlopen(url, timeout=3)
            self.assertEqual(error.exception.code, 503)
            self.store.access = actual
            with urlopen(url, timeout=3) as response:
                self.assertEqual(response.status, 200)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_worker_capacity_rejects_and_then_recovers(self):
        entered, release = threading.Event(), threading.Event()
        original = self.store.access
        def blocked(*args, **kwargs):
            entered.set(); release.wait(3)
            return original(*args, **kwargs)
        self.store.access = blocked
        server = create_server(self.store, port=0, workers=1)
        serving = threading.Thread(target=server.serve_forever, daemon=True); serving.start()
        url = f"http://127.0.0.1:{server.server_port}/q/{self.token}"
        statuses = []
        def first():
            with urlopen(url, timeout=5) as response:
                statuses.append(response.status)
        caller = threading.Thread(target=first, daemon=True); caller.start()
        try:
            self.assertTrue(entered.wait(2))
            with self.assertRaises(HTTPError) as error:
                urlopen(url, timeout=2)
            self.assertEqual(error.exception.code, 503)
            release.set(); caller.join(3)
            self.assertEqual(statuses, [200])
            with urlopen(url, timeout=3) as response:
                self.assertEqual(response.status, 200)
        finally:
            release.set(); caller.join(3)
            server.shutdown(); server.server_close(); serving.join()

    def test_read_only_migration_preserves_original(self):
        legacy_path = self.root/"old.sqlite3"
        legacy = Store(legacy_path)
        identifier = legacy.create_campaign("old", "http://127.0.0.1:8765")
        legacy.activate(identifier)
        before = hashlib.sha256(legacy_path.read_bytes()).digest()
        result = migrate(legacy_path, self.root/"migrated")
        self.assertEqual(result.campaigns()[0]["id"], identifier)
        self.assertEqual(hashlib.sha256(legacy_path.read_bytes()).digest(), before)
        with self.assertRaises(ValueError):
            open_store(legacy_path)


if __name__ == "__main__":
    unittest.main()
