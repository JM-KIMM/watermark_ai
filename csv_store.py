# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""CSV-only storage. Local file locks, bounded retention and spreadsheet-safe cells."""
from contextlib import contextmanager
import csv
import io
import ipaddress
import math
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
from urllib.parse import urlsplit

SCHEMAS = {
    "campaigns": {"id": str, "title": str, "base_url": str, "created": float, "starts": float, "expires": float,
                  "retention_days": int, "max_events": int, "active": int, "issuance_ref": str},
    "tokens": {"token": str, "campaign_id": str, "page": int, "question": str},
    "scans": {"id": int, "token": str, "timestamp": float, "ip": str},
    "cases": {"id": int, "subject_ref": str, "status": str, "notes": str,
              "scan_id": int, "created": float, "expires": float},
    "counters": {"name": str, "value": int},
}
LOCKS = {}
REGISTRY_LOCK = threading.Lock()


def safe_cell(value):
    text = "" if value is None else str(value)
    if text.startswith("'") or text.lstrip("\ufeff\u200b \t\r\n").startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def restore_cell(text):
    if text.startswith("'"):
        rest = text[1:]
        if safe_cell(rest) == text:
            return rest
    return text


def export_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or (list(rows[0]) if rows else ["id", "timestamp", "ip", "page", "question"])
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows({key: safe_cell(row.get(key)) for key in fields} for row in rows)


class CSVStore:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        with REGISTRY_LOCK:
            self.lock = LOCKS.setdefault(str(self.path), threading.RLock())
        with self._state(write=True):
            pass

    @contextmanager
    def _locked(self):
        with self.lock:
            with (self.path/".lock").open("a+b") as handle:
                handle.seek(0, 2)
                if not handle.tell():
                    handle.write(b"0"); handle.flush()
                start = time.monotonic()
                while True:
                    try:
                        handle.seek(0)
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic()-start > 3:
                            raise OSError("CSV 파일을 다른 프로세스가 사용 중입니다.")
                        time.sleep(.02)
                try:
                    yield
                finally:
                    handle.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _state(self, write=False):
        with self._locked():
            state, original = {}, {}
            for table, schema in SCHEMAS.items():
                path = self.path/f"{table}.csv"
                if path.exists() and path.stat().st_size > 32*1024*1024:
                    raise ValueError(f"CSV 파일 크기 한도 초과: {table}")
                raw = path.read_text(encoding="utf-8-sig") if path.exists() else ""
                original[table] = raw
                rows = []
                if raw:
                    reader = csv.DictReader(io.StringIO(raw))
                    old_campaign = table == "campaigns" and reader.fieldnames == [key for key in schema if key != "starts"]
                    if reader.fieldnames != list(schema) and not old_campaign:
                        raise ValueError(f"CSV 열 형식 오류: {table}")
                    for row in reader:
                        if old_campaign:
                            row["starts"] = row["created"]
                        if set(row) != set(schema) or any(not isinstance(value, str) for value in row.values()):
                            raise ValueError(f"CSV 행 형식 오류: {table}")
                        if len(rows) >= 25000:
                            raise ValueError(f"CSV 행 한도 초과: {table}")
                        rows.append({key: (None if key == "scan_id" and row[key] == "" else convert(restore_cell(row[key])))
                                     for key, convert in schema.items()})
                state[table] = rows
            yield state
            if write:
                for table, schema in SCHEMAS.items():
                    buffer = io.StringIO(newline="")
                    writer = csv.DictWriter(buffer, fieldnames=list(schema), quoting=csv.QUOTE_ALL)
                    writer.writeheader()
                    writer.writerows({key: safe_cell(row.get(key)) for key in schema} for row in state[table])
                    value = buffer.getvalue()
                    if value.replace("\r\n", "\n") == original[table].replace("\r\n", "\n"):
                        continue
                    descriptor, name = tempfile.mkstemp(dir=self.path, prefix=f".{table}-", suffix=".tmp")
                    try:
                        with os.fdopen(descriptor, "w", encoding="utf-8-sig", newline="") as handle:
                            handle.write(value); handle.flush(); os.fsync(handle.fileno())
                        os.replace(name, self.path/f"{table}.csv")
                    finally:
                        Path(name).unlink(missing_ok=True)

    @staticmethod
    def _cleanup(state, now):
        state["campaigns"] = [c for c in state["campaigns"] if c["expires"] >= now-86400 and (c["active"] or c["created"] >= now-3600)]
        campaigns = {c["id"]: c for c in state["campaigns"]}
        state["tokens"] = [t for t in state["tokens"] if t["campaign_id"] in campaigns]
        tokens = {t["token"]: t for t in state["tokens"]}
        scans = [s for s in state["scans"] if s["token"] in tokens and s["timestamp"] >= now-campaigns[tokens[s["token"]]["campaign_id"]]["retention_days"]*86400]
        state["scans"] = sorted(scans, key=lambda s: (s["timestamp"], s["id"]), reverse=True)[:10000]
        ids = {s["id"] for s in state["scans"]}
        state["cases"] = [c for c in state["cases"] if c["expires"] > now]
        for case in state["cases"]:
            if case["scan_id"] not in ids:
                case["scan_id"] = None

    @staticmethod
    def _next(state, key):
        row = next((r for r in state["counters"] if r["name"] == key), None)
        if row is None:
            row = {"name": key, "value": max((r["id"] for r in state[key]), default=0)}
            state["counters"].append(row)
        row["value"] = max(row["value"], max((r["id"] for r in state[key]), default=0))+1
        return row["value"]

    def cleanup(self, now=None):
        with self._state(write=True) as state:
            self._cleanup(state, time.time() if now is None else now)

    def create_campaign(self, title, base_url, *, days=7, retention_days=7, max_events=1000, issuance_ref="",
                        starts_at=None, ends_at=None):
        parts = urlsplit(base_url)
        try:
            parts.port
        except ValueError as exc:
            raise ValueError("접속 주소의 포트가 올바르지 않습니다.") from exc
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.query or parts.fragment or parts.path not in ("", "/") or any(c.isspace() for c in base_url):
            raise ValueError("QR 접속 주소는 http(s)://호스트:포트 형태여야 합니다.")
        if not (1 <= days <= 90 and 1 <= retention_days <= 90 and 1 <= max_events <= 10000):
            raise ValueError("만료·보관 1~90일, 접속 상한 1~10000건을 사용하세요.")
        now = time.time()
        starts = now if starts_at is None else float(starts_at)
        expires = now+days*86400 if ends_at is None else float(ends_at)
        if not all(math.isfinite(value) for value in (starts, expires)) or not (now-90*86400 <= starts < expires <= now+90*86400+1) or expires <= now:
            raise ValueError("QR 접근 시작·종료 순서와 최대 90일 범위를 확인하세요.")
        campaign = secrets.token_urlsafe(9)
        with self._state(write=True) as state:
            self._cleanup(state, now)
            if len(state["campaigns"]) >= 100:
                raise ValueError("캠페인 한도 100개에 도달했습니다.")
            state["campaigns"].append(dict(id=campaign, title=title[:200], base_url=base_url.rstrip("/"),
                created=now, starts=starts, expires=expires, retention_days=retention_days,
                max_events=max_events, active=0, issuance_ref=issuance_ref[:200]))
        return campaign

    def issue(self, campaign, page, question):
        with self._state(write=True) as state:
            row = next((c for c in state["campaigns"] if c["id"] == campaign), None)
            if not row or row["expires"] <= time.time():
                raise ValueError("발급 캠페인이 만료되었거나 없습니다.")
            existing = next((t for t in state["tokens"] if t["campaign_id"] == campaign and t["page"] == page and t["question"] == str(question)), None)
            if existing:
                return f"{row['base_url']}/q/{existing['token']}"
            if len(state["tokens"]) >= 20000:
                raise ValueError("QR 한도 20000개에 도달했습니다.")
            token = secrets.token_urlsafe(12)
            state["tokens"].append(dict(token=token, campaign_id=campaign, page=page, question=str(question)))
            return f"{row['base_url']}/q/{token}"

    def _active(self, campaign, value):
        with self._state(write=True) as state:
            for c in state["campaigns"]:
                if c["id"] == campaign:
                    c["active"] = value

    def activate(self, campaign):
        self._active(campaign, 1)

    def revoke(self, campaign):
        self._active(campaign, 0)

    def delete_campaign(self, campaign):
        with self._state(write=True) as state:
            state["campaigns"] = [c for c in state["campaigns"] if c["id"] != campaign]
            self._cleanup(state, time.time())

    def access(self, token, ip, *, record=True, now=None):
        ip = str(ipaddress.ip_address(ip))
        now = time.time() if now is None else now
        with self._state(write=True) as state:
            self._cleanup(state, now)
            row = next((t for t in state["tokens"] if t["token"] == token), None)
            if row is None:
                return 404
            c = next(c for c in state["campaigns"] if c["id"] == row["campaign_id"])
            if not c["active"] or c["expires"] <= now:
                return 410
            if c["starts"] > now:
                return 403
            if record:
                identifier = self._next(state, "scans")
                state["scans"].append(dict(id=identifier, token=token, timestamp=now, ip=ip))
                token_ids = {t["token"] for t in state["tokens"] if t["campaign_id"] == c["id"]}
                keep = {s["id"] for s in sorted((s for s in state["scans"] if s["token"] in token_ids), key=lambda s: (s["timestamp"], s["id"]), reverse=True)[:c["max_events"]]}
                state["scans"] = [s for s in state["scans"] if s["token"] not in token_ids or s["id"] in keep]
                self._cleanup(state, now)
        return 200

    def campaigns(self):
        self.cleanup()
        with self._state() as state:
            return [dict(c, issued=sum(t["campaign_id"] == c["id"] for t in state["tokens"])) for c in sorted(state["campaigns"], key=lambda c: c["created"], reverse=True)]

    def scans(self, limit=500):
        self.cleanup()
        with self._state() as state:
            tokens = {t["token"]: t for t in state["tokens"]}
            campaigns = {c["id"]: c for c in state["campaigns"]}
            result = []
            for scan in sorted(state["scans"], key=lambda s: s["id"], reverse=True)[:max(1, min(int(limit), 10000))]:
                token = tokens[scan["token"]]
                campaign = campaigns[token["campaign_id"]]
                result.append(dict(scan, page=token["page"], question=token["question"], campaign_id=campaign["id"], title=campaign["title"], issuance_ref=campaign["issuance_ref"]))
            return result

    def save_case(self, subject_ref, notes, *, status="검토중", scan_id=None, days=7, case_id=None):
        if status not in ("검토중", "확인", "기각") or not subject_ref.strip() or not notes.strip() or not 1 <= days <= 90:
            raise ValueError("대상 참조·내용·상태와 보관 기간(1~90일)을 확인하세요.")
        with self._state(write=True) as state:
            self._cleanup(state, time.time())
            if scan_id is not None and not any(s["id"] == scan_id for s in state["scans"]):
                raise ValueError("연결할 접속 기록이 없습니다.")
            row = next((c for c in state["cases"] if c["id"] == case_id), None)
            if row is None:
                if case_id is not None:
                    raise ValueError("사건 기록이 없습니다.")
                if len(state["cases"]) >= 1000:
                    raise ValueError("사건 한도 1000개에 도달했습니다.")
                row = dict(id=self._next(state, "cases"), created=time.time())
                state["cases"].append(row)
            row.update(subject_ref=subject_ref[:200], notes=notes[:10000], status=status,
                       scan_id=scan_id, expires=time.time()+days*86400)
            return row["id"]

    def cases(self):
        self.cleanup()
        with self._state() as state:
            return sorted(state["cases"], key=lambda c: c["id"], reverse=True)

    def delete_case(self, case_id):
        with self._state(write=True) as state:
            state["cases"] = [c for c in state["cases"] if c["id"] != case_id]
