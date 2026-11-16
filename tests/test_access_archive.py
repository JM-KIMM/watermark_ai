import csv
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from access_archive import AccessArchive
from csv_store import CSVStore
from tracking_db import create_server
from webapp import Application,create_web_server


def issued(root):
    store=CSVStore(root/'ledger')
    campaign=store.create_campaign('exam','http://127.0.0.1:8765',issuance_ref='A-023')
    token=store.issue(campaign,2,'7').rsplit('/',1)[1];store.activate(campaign)
    archive=AccessArchive(root/'archive');archive.register(store,campaign)
    return store,archive,campaign,token


class AccessArchiveTests(unittest.TestCase):
    def test_existing_csv_is_imported_once_without_cleanup(self):
        with TemporaryDirectory() as folder:
            store,archive,c,token=issued(Path(folder))
            store.access(token,'192.168.1.7')
            self.assertEqual(archive.import_legacy(store),1)
            self.assertEqual(archive.import_legacy(store),0)
            self.assertEqual(archive.snapshot()['total'],1)
    def test_first_ip_csv_and_persistence_after_ledger_cleanup(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);store,archive,c,token=issued(root)
            self.assertEqual(archive.access(token,'192.168.1.3',user_agent='=BAD\nUA'),200)
            self.assertEqual(archive.access(token,'192.168.1.3'),200)
            self.assertEqual(archive.snapshot()['observed_ips'],1)
            with (archive.path/'visitors.csv').open(encoding='utf-8-sig',newline='') as h:self.assertEqual(len(list(csv.DictReader(h))),1)
            with (archive.path/'events.csv').open(encoding='utf-8-sig',newline='') as h:
                rows=list(csv.DictReader(h));self.assertEqual(len(rows),2);self.assertEqual(rows[0]['issuance_ref'],'A-023');self.assertTrue(rows[0]['user_agent'].startswith("'="))
            store.delete_campaign(c)
            self.assertEqual(archive.access(token,'192.168.1.4'),200)
            # Repair a missing export using the durable canonical database.
            (archive.path/'events.csv').write_text('',encoding='utf8')
            reopened=AccessArchive(archive.path)
            self.assertEqual(reopened.snapshot()['total'],3)
            with (archive.path/'events.csv').open(encoding='utf-8-sig',newline='') as h:self.assertEqual(len(list(csv.DictReader(h))),3)
            reopened.set_active(c,False)
            self.assertEqual(reopened.access(token,'192.168.1.4'),410)
            self.assertEqual(reopened.snapshot()['total'],4)

    def test_concurrent_access_no_lost_first_visit(self):
        with TemporaryDirectory() as folder:
            _,archive,_,token=issued(Path(folder))
            with ThreadPoolExecutor(max_workers=8) as pool:
                statuses=list(pool.map(lambda n:archive.access(token,f'192.168.1.{n%10+1}'),range(40)))
            self.assertEqual(set(statuses),{200})
            self.assertEqual(archive.snapshot()['total'],40)
            self.assertEqual(archive.snapshot()['observed_ips'],10)
            with (archive.path/'events.csv').open(encoding='utf-8-sig',newline='') as h:self.assertEqual(len(list(csv.DictReader(h))),40)

    def test_real_http_ua_spoofed_ip_head_and_private_dashboard(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);_,archive,c,token=issued(root)
            server=create_server(archive,port=0)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            app=Application(root/'app');app.archive=archive
            admin=create_web_server(app,0);threading.Thread(target=admin.serve_forever,daemon=True).start()
            try:
                base=f'http://127.0.0.1:{server.server_port}'
                with urlopen(Request(base+'/q/'+token,headers={'X-Forwarded-For':'8.8.8.8','User-Agent':'test-client'})) as r:self.assertEqual(r.status,200)
                with urlopen(Request(base+'/q/'+token,method='HEAD')) as r:self.assertEqual(r.status,200)
                data=archive.snapshot();self.assertEqual(data['total'],2)
                self.assertEqual(data['events'][0]['method'],'HEAD')
                self.assertEqual(data['events'][1]['ip'],'127.0.0.1');self.assertEqual(data['events'][1]['user_agent'],'test-client')
                with self.assertRaises(HTTPError):urlopen(base+'/api/dashboard')
                url=f'http://127.0.0.1:{admin.server_port}'
                with self.assertRaises(HTTPError):urlopen(url+'/api/dashboard')
                with urlopen(Request(url+'/api/dashboard',headers={'X-Local-Token':app.token})) as r:self.assertEqual(json.load(r)['total'],2)
                with urlopen(Request(url+'/api/archive/events.csv',headers={'X-Local-Token':app.token})) as r:self.assertIn(b'A-023',r.read())
            finally:
                server.shutdown();server.server_close();admin.shutdown();admin.server_close();app.close()
