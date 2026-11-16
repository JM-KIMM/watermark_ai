# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""Bounded local QR access/IP log and manually maintained incident records."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
import threading
from collections import OrderedDict, deque
from urllib.parse import urlsplit

MAX_EVENTS = 10000
MAX_CASES = 1000
MAX_CAMPAIGNS = 100
MAX_TOKENS = 20000


def stamp(ts):
    return datetime.fromtimestamp(ts, timezone(timedelta(hours=9))).isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, base_url TEXT NOT NULL,
                    created REAL NOT NULL, expires REAL NOT NULL,
                    retention_days INTEGER NOT NULL, max_events INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 0, issuance_ref TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS tokens (
                    token TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                    page INTEGER NOT NULL, question TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token TEXT NOT NULL REFERENCES tokens(token) ON DELETE CASCADE,
                    timestamp REAL NOT NULL, ip TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS scans_time ON scans(timestamp);
                CREATE TABLE IF NOT EXISTS cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, subject_ref TEXT NOT NULL,
                    status TEXT NOT NULL, notes TEXT NOT NULL,
                    scan_id INTEGER REFERENCES scans(id) ON DELETE SET NULL,
                    created REAL NOT NULL, expires REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS cases_expiry ON cases(expires);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def cleanup(self, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("DELETE FROM scans WHERE id IN (SELECT s.id FROM scans s JOIN tokens t ON s.token=t.token JOIN campaigns c ON t.campaign_id=c.id WHERE s.timestamp < ? - c.retention_days*86400)", (now,))
            db.execute("DELETE FROM cases WHERE expires<=?", (now,))
            # Expired links remain tombstoned briefly, with no indefinite lifetime.
            db.execute("DELETE FROM campaigns WHERE expires<? OR (active=0 AND created<?)", (now-86400, now-3600))
            self._cap(db, "scans", MAX_EVENTS)

    @staticmethod
    def _cap(db, table, limit):
        if table != "scans":
            raise ValueError("unsupported table")
        db.execute("DELETE FROM scans WHERE id IN (SELECT id FROM scans ORDER BY timestamp DESC, id DESC LIMIT -1 OFFSET ?)", (limit,))

    def create_campaign(self, title, base_url, *, days=7, retention_days=7,
                        max_events=1000, issuance_ref=""):
        parts = urlsplit(base_url)
        try:
            parts.port
        except ValueError as exc:
            raise ValueError("QR 접속 주소의 포트가 올바르지 않습니다.") from exc
        if parts.scheme not in ("http", "https") or not parts.hostname or any(c.isspace() for c in base_url) or parts.query or parts.fragment or parts.username or parts.path not in ("", "/"):
            raise ValueError("QR 접속 주소는 http(s)://호스트:포트 형태여야 합니다.")
        if not (1 <= days <= 90 and 1 <= retention_days <= 90 and 1 <= max_events <= MAX_EVENTS):
            raise ValueError("만료·보관 기간은 1~90일, 최대 기록은 1~10000건입니다.")
        self.cleanup()
        campaign = secrets.token_urlsafe(9)
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM campaigns").fetchone()[0] >= MAX_CAMPAIGNS:
                raise ValueError("캠페인 최대 100개에 도달했습니다. 기존 캠페인을 정리하세요.")
            db.execute("INSERT INTO campaigns VALUES (?,?,?,?,?,?,?,?,?)",
                       (campaign, title[:200], base_url.rstrip("/"), now, now+days*86400,
                        retention_days, max_events, 0, issuance_ref[:200]))
        return campaign

    def issue(self, campaign, page, question):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            c = db.execute("SELECT * FROM campaigns WHERE id=?", (campaign,)).fetchone()
            if not c or c["expires"] <= time.time():
                raise ValueError("발급 캠페인이 만료되었거나 없습니다.")
            if db.execute("SELECT count(*) FROM tokens").fetchone()[0] >= MAX_TOKENS:
                raise ValueError("QR 발급 한도 20000개에 도달했습니다.")
            token = secrets.token_urlsafe(12)
            db.execute("INSERT INTO tokens VALUES (?,?,?,?)", (token, campaign, page, str(question)))
            return f"{c['base_url']}/q/{token}"

    def activate(self, campaign):
        with self.connect() as db:
            db.execute("UPDATE campaigns SET active=1 WHERE id=?", (campaign,))

    def revoke(self, campaign):
        with self.connect() as db:
            db.execute("UPDATE campaigns SET active=0 WHERE id=?", (campaign,))

    def delete_campaign(self, campaign):
        with self.connect() as db:
            db.execute("DELETE FROM campaigns WHERE id=?", (campaign,))

    def access(self, token, ip, *, record=True, now=None):
        now = time.time() if now is None else now
        ip = str(ipaddress.ip_address(ip))
        self.cleanup(now)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT t.campaign_id,c.active,c.expires,c.max_events FROM tokens t JOIN campaigns c ON c.id=t.campaign_id WHERE token=?", (token,)).fetchone()
            if not row:
                return 404
            if not row["active"] or row["expires"] <= now:
                return 410
            if record:
                db.execute("INSERT INTO scans(token,timestamp,ip) VALUES (?,?,?)", (token, now, ip))
                db.execute("DELETE FROM scans WHERE id IN (SELECT s.id FROM scans s JOIN tokens t ON s.token=t.token WHERE t.campaign_id=? ORDER BY s.timestamp DESC,s.id DESC LIMIT -1 OFFSET ?)", (row["campaign_id"], row["max_events"]))
                self._cap(db, "scans", MAX_EVENTS)
        return 200

    def campaigns(self):
        self.cleanup()
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT c.*, (SELECT count(*) FROM tokens WHERE campaign_id=c.id) AS issued FROM campaigns c ORDER BY created DESC")]

    def scans(self, limit=500):
        self.cleanup()
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT s.*,t.page,t.question,t.campaign_id,c.title,c.issuance_ref FROM scans s JOIN tokens t ON s.token=t.token JOIN campaigns c ON t.campaign_id=c.id ORDER BY s.id DESC LIMIT ?", (max(1, min(int(limit), MAX_EVENTS)),))]

    def save_case(self, subject_ref, notes, *, status="검토중", scan_id=None, days=7, case_id=None):
        if status not in ("검토중", "확인", "기각") or not subject_ref.strip() or not notes.strip():
            raise ValueError("대상 식별자·사건 내용·유효한 상태가 필요합니다.")
        if not 1 <= days <= 90:
            raise ValueError("사건 보관 기간은 1~90일입니다.")
        self.cleanup()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if scan_id is not None and not db.execute("SELECT 1 FROM scans WHERE id=?", (scan_id,)).fetchone():
                raise ValueError("연결할 접속 기록이 없습니다.")
            values = (subject_ref[:200], status, notes[:10000], scan_id, time.time()+days*86400)
            if case_id is not None:
                result = db.execute("UPDATE cases SET subject_ref=?,status=?,notes=?,scan_id=?,expires=? WHERE id=?", (*values, case_id))
                if not result.rowcount:
                    raise ValueError("사건 기록이 없습니다.")
                return case_id
            if db.execute("SELECT count(*) FROM cases").fetchone()[0] >= MAX_CASES:
                raise ValueError("사건 기록 최대 1000개에 도달했습니다.")
            result = db.execute("INSERT INTO cases(subject_ref,status,notes,scan_id,created,expires) VALUES (?,?,?,?,?,?)", (*values[:4], time.time(), values[4]))
            return result.lastrowid

    def cases(self):
        self.cleanup()
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM cases ORDER BY id DESC")]

    def delete_case(self, case_id):
        with self.connect() as db:
            db.execute("DELETE FROM cases WHERE id=?", (case_id,))


def open_store(path):
    if Path(path).suffix.lower() in (".sqlite", ".sqlite3", ".db"):
        raise ValueError("현재 관리는 CSV 전용입니다. 이전 SQLite는 migrate_legacy.py로 먼저 이관하세요.")
    from csv_store import CSVStore
    return CSVStore(path)


class RequestBudget:
    def __init__(self, total=120, per_token=20, per_ip=30, window=60):
        self.total, self.per_token, self.per_ip, self.window = total, per_token, per_ip, window
        self.all = deque()
        self.keys = OrderedDict()
        self.lock = threading.Lock()

    def allow(self, ip, token, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            while self.all and self.all[0] <= now-self.window:
                self.all.popleft()
            for key in list(self.keys):
                q = self.keys[key]
                while q and q[0] <= now-self.window:
                    q.popleft()
                if not q:
                    del self.keys[key]
            groups = [(('ip', ip), self.per_ip)]
            if token:
                groups.append((('token', token), self.per_token))
            if len(self.all) >= self.total or any(len(self.keys.get(key, ())) >= limit for key, limit in groups):
                return False
            self.all.append(now)
            for key, _ in groups:
                self.keys.setdefault(key, deque()).append(now)
                self.keys.move_to_end(key)
            while len(self.keys) > 4096:
                self.keys.popitem(last=False)
            return True


def create_server(store, host="127.0.0.1", port=8765, *, request_budget=120, workers=8):
    if request_budget < 1 or not 1 <= workers <= 32:
        raise ValueError("요청 한도는 1 이상, 동시 연결은 1~32개입니다.")
    budget = RequestBudget(total=request_budget)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_request(self, head=False):
            try:
                request_path = urlsplit(self.path).path
            except ValueError:
                request_path = ""
            if request_path in ('/','/health'):
                body=json.dumps(dict(service='watermark-qr',ready=True,notice='발급된 QR 주소로 접속하세요. 관리 화면은 이 포트에 없습니다.'),ensure_ascii=False).encode('utf8')
                self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers()
                if not head:self.wfile.write(body)
                return
            match = re.fullmatch(r"/q/([A-Za-z0-9_-]{16})", request_path)
            token = match[1] if match else None
            if not budget.allow(self.client_address[0], token):
                code = 429
            elif not match or len(self.path) > 256:
                code = 404
            else:
                # Ignore X-Forwarded-For: untrusted clients cannot forge the saved IP.
                try:
                    kwargs=dict(record=not head)
                    if getattr(store,'supports_user_agent',False):
                        kwargs.update(user_agent=self.headers.get('User-Agent','')[:512],method='HEAD' if head else 'GET',record=True)
                    code = store.access(match[1], self.client_address[0], **kwargs)
                except (OSError, ValueError, sqlite3.Error):
                    code = 503
            body = json.dumps({"status": {200: "access recorded" if not head else "active", 403: "access window not started", 404: "not found", 410: "expired or revoked", 429: "request budget exceeded", 503: "storage unavailable"}[code],
                               "notice": "Requests to active QR links record the connecting IP and time."}).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            if code in (429, 503):
                self.send_header("Retry-After", "60")
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def do_GET(self):
            self.handle_request()

        def do_HEAD(self):
            self.handle_request(head=True)

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 16

        def __init__(self, *args):
            self.slots = threading.BoundedSemaphore(workers)
            super().__init__(*args)

        def process_request(self, request, address):
            if not self.slots.acquire(blocking=False):
                try:
                    request.settimeout(.5)
                    # Drain the small HTTP header before closing a rejected socket.
                    # On Windows, closing with unread request bytes can reset the
                    # connection and discard the 503 response sent to the client.
                    header=b""
                    try:
                        while b"\r\n\r\n" not in header and len(header)<4096:
                            chunk=request.recv(min(1024,4096-len(header)))
                            if not chunk:break
                            header+=chunk
                    except OSError:
                        pass
                    request.sendall(b"HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                except OSError:
                    pass
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, address)
            except Exception:
                self.slots.release()
                raise

        def process_request_thread(self, request, address):
            try:
                super().process_request_thread(request, address)
            finally:
                self.slots.release()

        def service_actions(self):
            if time.monotonic() - getattr(self, "last_cleanup", 0) > 30:
                try:
                    store.cleanup()
                except (OSError, ValueError, sqlite3.Error):
                    pass  # HTTP requests return 503 until storage is available again.
                self.last_cleanup = time.monotonic()

        def get_request(self):
            conn, address = super().get_request()
            conn.settimeout(5)
            return conn, address

    return Server((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description="QR 접속 IP 기록 서버 (관리 API 없음)")
    parser.add_argument("--db", default="data/qr_csv")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--requests-per-minute", type=int, default=120)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    server = create_server(open_store(args.db), args.host, args.port,
                           request_budget=args.requests_per_minute, workers=args.workers)
    print(f"QR server: http://{args.host}:{server.server_port}; DB: {Path(args.db).resolve()}", flush=True)
    try:
        server.serve_forever(poll_interval=1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
