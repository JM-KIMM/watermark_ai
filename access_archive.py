# SPDX-License-Identifier: GPL-3.0-only
"""Durable issued-link registry and access archive, independent of short-lived CSV logs."""
from contextlib import contextmanager
import csv
from datetime import datetime,timezone,timedelta
import hashlib
import ipaddress
import os
from pathlib import Path
import sqlite3
import threading
import time

from csv_store import safe_cell

EVENT_FIELDS=['id','timestamp_utc','timestamp_kst','ip','visitor_id','issuance_ref','campaign_id','title','page','question','token_sha256','user_agent','method','status']
VISITOR_FIELDS=['visitor_id','ip','first_seen_utc','first_seen_kst']
LOCKS={};LOCKS_GUARD=threading.Lock()


def times(ts):
    utc=datetime.fromtimestamp(ts,timezone.utc)
    return utc.isoformat(timespec='milliseconds'),utc.astimezone(timezone(timedelta(hours=9))).isoformat(timespec='milliseconds')


class AccessArchive:
    supports_user_agent=True

    def __init__(self,path):
        self.path=Path(path).resolve();self.path.mkdir(parents=True,exist_ok=True)
        with LOCKS_GUARD:self.lock=LOCKS.setdefault(str(self.path),threading.RLock())
        with self.locked():
            with self.connect() as db:
                db.executescript('''
                    CREATE TABLE IF NOT EXISTS campaigns(id TEXT PRIMARY KEY,title TEXT NOT NULL,issuance_ref TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,created REAL NOT NULL);
                    CREATE TABLE IF NOT EXISTS tokens(digest TEXT PRIMARY KEY,campaign_id TEXT NOT NULL,page INTEGER NOT NULL,question TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS visitors(visitor_id TEXT PRIMARY KEY,ip TEXT UNIQUE NOT NULL,first_seen REAL NOT NULL);
                    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp REAL NOT NULL,ip TEXT NOT NULL,visitor_id TEXT NOT NULL,
                        issuance_ref TEXT NOT NULL,campaign_id TEXT NOT NULL,title TEXT NOT NULL,page INTEGER NOT NULL,question TEXT NOT NULL,
                        token_sha256 TEXT NOT NULL,user_agent TEXT NOT NULL,status INTEGER NOT NULL);
                    CREATE INDEX IF NOT EXISTS events_campaign ON events(campaign_id,id);
                    CREATE INDEX IF NOT EXISTS events_visitor ON events(visitor_id,id);
                    CREATE TABLE IF NOT EXISTS imported_legacy(digest TEXT PRIMARY KEY);
                ''')
                if 'method' not in {r[1] for r in db.execute('PRAGMA table_info(events)')}:
                    db.execute("ALTER TABLE events ADD COLUMN method TEXT NOT NULL DEFAULT 'GET'")
            # Rebuild exports after a restart to repair an interrupted CSV append.
            self._export_all()

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path/'archive.sqlite3',timeout=15)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
        try:
            with db:yield db
        finally:db.close()

    @contextmanager
    def locked(self):
        with self.lock:
            with (self.path/'.archive.lock').open('a+b') as handle:
                handle.seek(0,2)
                if handle.tell()==0:handle.write(b'0');handle.flush()
                handle.seek(0)
                if os.name=='nt':
                    import msvcrt
                    deadline=time.monotonic()+15
                    while True:
                        try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1);break
                        except OSError:
                            if time.monotonic()>deadline:raise
                            time.sleep(.02)
                else:
                    import fcntl
                    fcntl.flock(handle,fcntl.LOCK_EX)
                try:yield
                finally:
                    handle.seek(0)
                    if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                    else:fcntl.flock(handle,fcntl.LOCK_UN)

    @staticmethod
    def event(row):
        row=dict(row);utc,kst=times(row.pop('timestamp'))
        return dict(row,timestamp_utc=utc,timestamp_kst=kst)

    def _append(self,name,fields,rows):
        path=self.path/name;header=not path.exists() or path.stat().st_size==0
        with path.open('a',encoding='utf-8-sig' if header else 'utf-8',newline='') as h:
            writer=csv.DictWriter(h,fields,quoting=csv.QUOTE_ALL)
            if header:writer.writeheader()
            for row in rows:writer.writerow({k:safe_cell(row.get(k)) for k in fields})
            h.flush();os.fsync(h.fileno())

    def _export_all(self):
        with self.connect() as db:
            for name,fields,query in [('events.csv',EVENT_FIELDS,'SELECT * FROM events ORDER BY id'),
                                      ('visitors.csv',VISITOR_FIELDS,'SELECT * FROM visitors ORDER BY first_seen,visitor_id')]:
                tmp=self.path/(name+'.tmp')
                with tmp.open('w',encoding='utf-8-sig',newline='') as h:
                    writer=csv.DictWriter(h,fields,quoting=csv.QUOTE_ALL);writer.writeheader()
                    for r in db.execute(query):
                        if name=='events.csv':row=self.event(r)
                        else:
                            utc,kst=times(r['first_seen']);row=dict(visitor_id=r['visitor_id'],ip=r['ip'],first_seen_utc=utc,first_seen_kst=kst)
                        writer.writerow({k:safe_cell(row.get(k)) for k in fields})
                    h.flush();os.fsync(h.fileno())
                os.replace(tmp,self.path/name)

    def register(self,store,campaign_id):
        # Snapshot the issuance ledger once. Expiry/cleanup of the old ledger
        # must never delete this registry or previously recorded access events.
        with store._state() as state:
            campaign=next(c for c in state['campaigns'] if c['id']==campaign_id)
            tokens=[dict(t) for t in state['tokens'] if t['campaign_id']==campaign_id]
        if not campaign['active']:raise ValueError('활성화된 QR 발급만 등록할 수 있습니다.')
        with self.locked(),self.connect() as db:
            db.execute('INSERT OR IGNORE INTO campaigns(id,title,issuance_ref,created) VALUES(?,?,?,?)',
                       (campaign_id,campaign['title'],campaign['issuance_ref'],campaign['created']))
            db.executemany('INSERT OR IGNORE INTO tokens VALUES(?,?,?,?)',
                [(hashlib.sha256(t['token'].encode()).hexdigest(),campaign_id,t['page'],t['question']) for t in tokens])

    def access(self,token,ip,*,record=True,now=None,user_agent='',method='GET'):
        ip=str(ipaddress.ip_address(ip));now=time.time() if now is None else now
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.locked():
            with self.connect() as db:
                issued=db.execute('SELECT t.*,c.title,c.issuance_ref,c.active FROM tokens t JOIN campaigns c ON c.id=t.campaign_id WHERE digest=?',(digest,)).fetchone()
                if issued is None:return 404
                status=200 if issued['active'] else 410
                if not record:return status
                visitor=hashlib.sha256(ip.encode()).hexdigest()[:20]
                new=db.execute('INSERT OR IGNORE INTO visitors VALUES(?,?,?)',(visitor,ip,now)).rowcount>0
                ua=str(user_agent).replace('\r',' ').replace('\n',' ')[:512]
                values=(now,ip,visitor,issued['issuance_ref'],issued['campaign_id'],issued['title'],issued['page'],issued['question'],digest,ua,str(method)[:10],status)
                identifier=db.execute('INSERT INTO events(timestamp,ip,visitor_id,issuance_ref,campaign_id,title,page,question,token_sha256,user_agent,method,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',values).lastrowid
                db.commit()
                row=self.event(db.execute('SELECT * FROM events WHERE id=?',(identifier,)).fetchone())
            self._append('events.csv',EVENT_FIELDS,[row])
            if new:
                utc,kst=times(now);self._append('visitors.csv',VISITOR_FIELDS,[dict(visitor_id=visitor,ip=ip,first_seen_utc=utc,first_seen_kst=kst)])
        return status

    def cleanup(self,*args):
        pass  # Archive and issued links persist until an explicit operator action.

    def set_active(self,campaign_id,active):
        with self.locked(),self.connect() as db:
            if not db.execute('UPDATE campaigns SET active=? WHERE id=?',(int(active),campaign_id)).rowcount:
                raise ValueError('발급 시험지가 없습니다.')

    def import_legacy(self,store):
        """Copy surviving old CSV records without expiry cleanup or mutation."""
        with store._state() as state:
            campaigns={c['id']:dict(c) for c in state['campaigns']}
            tokens={t['token']:dict(t) for t in state['tokens']}
            scans=[dict(s) for s in state['scans']]
        imported=0
        with self.locked():
            with self.connect() as db:
                for scan in scans:
                    token=tokens.get(scan['token']);c=campaigns.get(token['campaign_id']) if token else None
                    if not c:continue
                    key=hashlib.sha256(repr(sorted(scan.items())).encode()).hexdigest()
                    if not db.execute('INSERT OR IGNORE INTO imported_legacy VALUES(?)',(key,)).rowcount:continue
                    ip=str(ipaddress.ip_address(scan['ip']));visitor=hashlib.sha256(ip.encode()).hexdigest()[:20]
                    digest=hashlib.sha256(scan['token'].encode()).hexdigest()
                    db.execute('INSERT OR IGNORE INTO campaigns VALUES(?,?,?,?,?)',(c['id'],c['title'],c['issuance_ref'],c['active'],c['created']))
                    db.execute('INSERT OR IGNORE INTO tokens VALUES(?,?,?,?)',(digest,c['id'],token['page'],token['question']))
                    db.execute('INSERT INTO visitors VALUES(?,?,?) ON CONFLICT(ip) DO UPDATE SET first_seen=MIN(first_seen,excluded.first_seen)',(visitor,ip,scan['timestamp']))
                    db.execute('INSERT INTO events(timestamp,ip,visitor_id,issuance_ref,campaign_id,title,page,question,token_sha256,user_agent,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                               (scan['timestamp'],ip,visitor,c['issuance_ref'],c['id'],c['title'],token['page'],token['question'],digest,'',200))
                    imported+=1
            if imported:self._export_all()
        return imported

    def snapshot(self,after=0,limit=200):
        with self.connect() as db:
            count,last=db.execute('SELECT COUNT(*),COALESCE(MAX(id),0) FROM events').fetchone()
            visitors=db.execute('SELECT COUNT(*) FROM visitors').fetchone()[0]
            rows=[self.event(r) for r in db.execute('SELECT * FROM events WHERE id>? ORDER BY id DESC LIMIT ?',(max(0,int(after)),min(500,max(1,int(limit)))))]
            campaigns=[dict(r) for r in db.execute('SELECT c.*,COUNT(t.digest) AS issued FROM campaigns c LEFT JOIN tokens t ON t.campaign_id=c.id GROUP BY c.id ORDER BY c.created DESC')]
        return dict(total=count,last_id=last,observed_ips=visitors,events=rows,campaigns=campaigns,
                    retention='직접 삭제하기 전까지 로컬 보관',identity_note='관측 IP와 발급 대상의 연결 기록이며 개인 신원이나 부정행위 확정이 아닙니다.')
