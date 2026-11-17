# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""Loopback-only HTML interface. PDF work runs in a bounded child process."""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import multiprocessing as mp
from pathlib import Path
import queue
import re
import secrets
import socket
import sqlite3
import threading
import time
from urllib.parse import urlsplit, quote
import webbrowser

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
MAX_PDF = 25*1024*1024


def parse_time(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.timestamp()


def build_options(settings, data_root):
    level = int(settings.get("intensity",2))
    if level not in (1,2):
        raise ValueError("강도 1·2 중 하나를 선택하세요.")
    tracking = None
    if settings.get("tracking") is True:
        tracking = dict(db=str(data_root/"qr_csv"),base_url=str(settings.get("base_url","http://127.0.0.1:8765")),
                        starts_at=parse_time(settings.get("starts_at")),ends_at=parse_time(settings.get("ends_at")),
                        days=7,retention_days=int(settings.get("retention_days",7)),
                        max_events=int(settings.get("max_events",1000)),issuance_ref=str(settings.get('issuance_ref',''))[:200],
                        archive=str(data_root/'qr_archive'))
    placement = settings.get("qr_placement", "question-end" if level != 1 else "fixed")
    qr_size = float(settings.get("qr_size", 40))
    # Defaults follow the two treatments that lowered accuracy in the OCR+LLM measurement:
    # the border in its measured form (6pt, 0.45, ±25% size, source glyphs, command +
    # other-page excerpts) and per-question bait. The bait is printed on the border and on
    # passage-box frames ('frames') rather than between body lines ('lines', the measured
    # placement), because lines between the text confuse the people sitting the exam.
    # The QR stays for access logging.
    decoy = settings.get('decoy', 'frames')
    decoy = 'lines' if decoy is True else (decoy or None)
    return dict(intensity=level,question_style="qr",qr_size=qr_size,
                mode="cycle",font_mode=settings.get("font_mode","source"),
                size=float(settings.get("font_size",6)),opacity=float(settings.get("opacity",.45)),
                band=max(20, qr_size+16) if placement == "gutter" else 20,
                size_jitter=float(settings.get("size_jitter",.25)),
                width_jitter=float(settings.get("width_jitter",0)),seed=42,
                qr_placement=placement,replace_passage_boxes=bool(settings.get("replace_passage_boxes", False)),
                payload_policy=settings.get('payload_policy'),
                decoy=decoy,decoy_style=str(settings.get('decoy_style','labelled')),decoy_number=str(settings.get('decoy_number','absent')),
                prompts_file=str(ROOT/"prompts_ko.json"),tracking=tracking)


def generate_worker(source, output, options, events):
    try:
        import pymupdf as fitz
        from watermark import build
        with fitz.open(source) as doc:
            if doc.needs_pass:
                raise ValueError("암호를 해제한 PDF를 선택하세요.")
            if not 1 <= len(doc) <= 100:
                raise ValueError("한 번에 1~100쪽 PDF를 처리할 수 있습니다.")
        report = build(source,output,**options,
                       progress=lambda page,total: events.put(dict(kind="progress",page=page,total=total)))
        marks = [m for p in report["pages"] for m in p["question_marks"]]
        events.put(dict(kind="done",summary=dict(pages=len(report["pages"]),
            qr=sum(m["qr_status"]=="placed" for m in marks),
            skipped=sum(m["qr_status"]=="skipped-no-whitespace" for m in marks),
            boxes=sum(len(p.get("passage_boxes", [])) for p in report["pages"]),
            decoys=sum(len(p.get("decoy_lines", [])) for p in report["pages"]),
            baits=sum(len(p.get("decoy_baits", [])) for p in report["pages"]),
            intensity=report["intensity"],tracking=bool(report["tracking"]),
            campaign_id=report['tracking']['campaign_id'] if report['tracking'] else None,
            captions_skipped=sum(m.get("label_status")=="skipped-no-whitespace" for m in marks))))
    except Exception as exc:
        message = str(exc) if isinstance(exc,(ValueError,RuntimeError)) else "PDF를 처리하지 못했습니다. 파일과 설정을 확인하세요."
        events.put(dict(kind="error",message=message))


def lan_address():
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.connect(('192.0.2.1',80));return sock.getsockname()[0]
    except OSError:return '127.0.0.1'


class Application:
    def __init__(self, root=ROOT, *, job_timeout=900,collector_host=None,collector_port=None):
        self.root=Path(root).resolve()
        self.output=self.root/"outputs"/"web"
        self.output.mkdir(parents=True,exist_ok=True)
        self.data=self.root/"data"
        from access_archive import AccessArchive
        self.archive=AccessArchive(self.data/'qr_archive')
        if (self.data/'qr_csv'/'scans.csv').exists():
            from csv_store import CSVStore
            self.archive.import_legacy(CSVStore(self.data/'qr_csv'))
        self.collector_host=collector_host or (lan_address() if self.root==ROOT.resolve() else '127.0.0.1')
        self.collector_port=(8765 if self.root==ROOT.resolve() else 0) if collector_port is None else collector_port
        self.token=secrets.token_urlsafe(32)
        self.jobs={}
        self.lock=threading.RLock()
        self.busy=None
        self.collector=None
        self.collector_thread=None
        self.job_timeout=job_timeout
        # Only delete known artifacts inside this app's output directory.
        cutoff=time.time()-7*86400
        for folder in self.output.iterdir():
            if folder.is_dir() and re.fullmatch(r"[a-f0-9]{32}",folder.name) and folder.stat().st_mtime<cutoff:
                for name in ("source.pdf","result.pdf","result.preview.png","result.manifest.json"):
                    (folder/name).unlink(missing_ok=True)
                if not any(folder.iterdir()):
                    folder.rmdir()

    def submit(self,payload):
        with self.lock:
            if self.busy:
                raise ValueError("현재 PDF를 생성 중입니다. 완료 후 다시 시도하세요.")
            if len(self.jobs)>=20:
                raise ValueError("이번 실행의 생성 한도에 도달했습니다. 앱을 다시 실행하세요.")
            settings=payload.get("settings",{})
            if not isinstance(settings,dict):
                raise ValueError("설정 형식이 올바르지 않습니다.")
            settings=dict(settings)
            settings.setdefault('tracking',True)
            if settings['tracking']:
                self.start_collector()
                settings.setdefault('base_url',self.collector_status()['base_url'])
            options=build_options(settings,self.data)
            data=base64.b64decode(payload.get("file",""),validate=True)
            if not 0<len(data)<=MAX_PDF or b"%PDF-" not in data[:1024]:
                raise ValueError("25MB 이하의 PDF 파일을 선택하세요.")
            filename=re.sub(r'[\x00-\x1f<>:"/\\|?*]','_',str(payload.get("filename","시험지.pdf")))[:120]
            if options['tracking']:
                # Keep the uploaded title: the private temporary file is always
                # named source.pdf and must not become every dashboard title.
                from tracking_db import open_store
                t=options['tracking'];ledger=open_store(t['db'])
                t['campaign_id']=ledger.create_campaign(Path(filename).stem,t['base_url'],
                    days=t['days'],retention_days=t['retention_days'],max_events=t['max_events'],
                    issuance_ref=t['issuance_ref'],starts_at=t['starts_at'],ends_at=t['ends_at'])
                ledger.activate(t['campaign_id'])
            identifier=secrets.token_hex(16)
            folder=self.output/identifier
            folder.mkdir()
            source=folder/"source.pdf"
            source.write_bytes(data)
            context=mp.get_context("spawn")
            events=context.Queue(maxsize=256)
            process=context.Process(target=generate_worker,args=(str(source),str(folder/"result.pdf"),options,events),daemon=True)
            job=dict(id=identifier,name=filename,state="working",page=0,total=0,
                     message="PDF를 확인하고 있습니다.",folder=folder,process=process,started=time.monotonic())
            self.jobs[identifier]=job
            self.busy=identifier
            try:
                process.start()
            except Exception:
                self.jobs.pop(identifier,None);self.busy=None
                raise
            threading.Thread(target=self._watch,args=(job,events),daemon=True).start()
            return self.public_job(identifier)

    def _watch(self,job,events):
        process=job["process"]
        finished=False
        try:
            while not finished:
                if time.monotonic()-job["started"]>self.job_timeout:
                    process.terminate()
                    with self.lock:
                        job.update(state="error",message="처리 시간이 15분을 넘었습니다. PDF를 나눠서 다시 시도하세요.")
                    break
                try:
                    event=events.get(timeout=.25)
                except queue.Empty:
                    if not process.is_alive():
                        # A completed child can exit just before its final queued message is read.
                        try:
                            event=events.get(timeout=.5)
                        except queue.Empty:
                            with self.lock:
                                job.update(state="error",message="생성 작업이 중단됐습니다. 파일을 확인한 후 다시 시도하세요.")
                            break
                    else:
                        continue
                with self.lock:
                    if event["kind"]=="progress":
                        job.update(page=event["page"],total=event["total"],message="워터마크를 배치하고 있습니다.")
                    elif event["kind"]=="done":
                        campaign=event['summary'].get('campaign_id')
                        if campaign:
                            try:
                                from tracking_db import open_store
                                self.archive.register(open_store(self.data/'qr_csv'),campaign)
                                manifest=job['folder']/'result.manifest.json'
                                record=json.loads(manifest.read_text(encoding='utf8'))
                                record['tracking']['access_policy']='persistent LAN registry; until manually revoked'
                                manifest.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
                            except (OSError,ValueError,sqlite3.Error):
                                job.update(state='error',message='QR 발급 등록을 저장하지 못했습니다. 저장 공간과 CSV 파일 잠금을 확인하세요.')
                                finished=True;continue
                        job.update(state="done",summary=event["summary"],message="PDF 생성이 완료됐습니다.")
                        finished=True
                    else:
                        job.update(state="error",message=event.get("message","생성 실패"));finished=True
        finally:
            process.join(timeout=2)
            if process.is_alive():
                process.terminate();process.join(timeout=2)
            events.close()
            try:
                (job["folder"]/"source.pdf").unlink(missing_ok=True)
            except OSError:
                pass  # A locked file is retried by the seven-day cleanup.
            with self.lock:
                if self.busy==job["id"]:
                    self.busy=None

    def public_job(self,identifier):
        with self.lock:
            job=self.jobs.get(identifier)
            if not job:
                raise ValueError("생성 기록이 없습니다.")
            return {key:job[key] for key in ("id","name","state","page","total","message","summary") if key in job}

    def collector_status(self):
        port=self.collector.server_port if self.collector else self.collector_port
        return dict(running=self.collector is not None,host=self.collector_host,port=port,
                    base_url=f'http://{self.collector_host}:{port}',retention='직접 삭제하기 전까지 보관')

    def start_collector(self):
        from tracking_db import create_server
        with self.lock:
            if self.collector is None:
                self.collector=create_server(self.archive,host=self.collector_host,port=self.collector_port,request_budget=6000)
                self.collector_thread=threading.Thread(target=self.collector.serve_forever,daemon=True)
                self.collector_thread.start()
        return self.collector_status()

    def stop_collector(self):
        with self.lock:
            collector,self.collector=self.collector,None
        if collector:
            collector.shutdown();collector.server_close()
        return self.collector_status()

    def close(self):
        self.stop_collector()
        with self.lock:
            jobs=list(self.jobs.values())
        for job in jobs:
            if job["process"].is_alive():
                job["process"].terminate();job["process"].join(timeout=2)


def create_web_server(app,port=8766):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def allowed_host(self):
            return self.headers.get("Host","") in (f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}")

        def reply(self,code,body,content_type="application/json; charset=utf-8",filename=None):
            if isinstance(body,dict):
                body=json.dumps(body,ensure_ascii=False).encode("utf-8")
            elif isinstance(body,str):
                body=body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if filename:
                self.send_header("Content-Disposition",f"attachment; filename*=UTF-8''{quote(filename)}")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            origin=self.headers.get("Origin")
            origins=(f"http://127.0.0.1:{self.server.server_port}",f"http://localhost:{self.server.server_port}")
            return self.allowed_host() and (not origin or origin in origins) and secrets.compare_digest(self.headers.get("X-Local-Token",""),app.token)

        def do_GET(self):
            if not self.allowed_host():
                self.reply(403,dict(error="허용되지 않은 호스트입니다."));return
            path=urlsplit(self.path).path
            if path in ('/','/dashboard'):
                html=(ROOT/"web"/('dashboard.html' if path=='/dashboard' else 'index.html')).read_text(encoding="utf-8").replace("__LOCAL_TOKEN__",app.token)
                self.reply(200,html,"text/html; charset=utf-8");return
            if path in ("/app.js","/style.css",'/dashboard.js','/dashboard.css'):
                self.reply(200,(ROOT/"web"/path[1:]).read_bytes(),"text/javascript; charset=utf-8" if path.endswith("js") else "text/css; charset=utf-8");return
            if not self.authorized():
                self.reply(403,dict(error="앱 화면에서 다시 시도하세요."));return
            try:
                if path=="/api/collector":
                    self.reply(200,app.collector_status());return
                if path=='/api/dashboard':
                    from urllib.parse import parse_qs
                    after=int(parse_qs(urlsplit(self.path).query).get('after',['0'])[0])
                    self.reply(200,dict(**app.archive.snapshot(after=after),collector=app.collector_status()));return
                if path in ('/api/archive/events.csv','/api/archive/visitors.csv'):
                    name=path.rsplit('/',1)[-1]
                    with app.archive.locked():data=(app.archive.path/name).read_bytes()
                    self.reply(200,data,'text/csv; charset=utf-8',filename=name);return
                if path in ("/api/scans","/api/scans.csv"):
                    from tracking_db import open_store,stamp
                    from csv_store import safe_cell
                    rows=open_store(app.data/"qr_csv").scans(500 if path.endswith("scans") else 10000)
                    if path.endswith(".csv"):
                        buffer=io.StringIO(newline="")
                        fields=["id","timestamp","ip","page","question","campaign_id"]
                        writer=csv.DictWriter(buffer,fieldnames=fields,quoting=csv.QUOTE_ALL)
                        writer.writeheader()
                        for row in rows:
                            row=dict(row,timestamp=stamp(row["timestamp"]))
                            writer.writerow({key:safe_cell(row.get(key)) for key in fields})
                        self.reply(200,b'\xef\xbb\xbf'+buffer.getvalue().encode("utf-8"),"text/csv; charset=utf-8",filename="qr_access.csv")
                    else:
                        self.reply(200,dict(rows=[dict(row,timestamp=stamp(row["timestamp"])) for row in rows]))
                    return
                match=re.fullmatch(r"/api/jobs/([a-f0-9]{32})(?:/(pdf|preview|manifest))?",path)
                if match:
                    identifier,kind=match.groups()
                    if not kind:
                        self.reply(200,app.public_job(identifier));return
                    job=app.public_job(identifier)
                    if job["state"]!="done":
                        raise ValueError("PDF가 아직 준비되지 않았습니다.")
                    filenames={"pdf":"result.pdf","preview":"result.preview.png","manifest":"result.manifest.json"}
                    file=app.output/identifier/filenames[kind]
                    kind_type={"pdf":"application/pdf","preview":"image/png","manifest":"application/json; charset=utf-8"}[kind]
                    download=Path(job["name"]).stem+"_워터마크.pdf" if kind=="pdf" else "설정기록.json" if kind=="manifest" else None
                    self.reply(200,file.read_bytes(),kind_type,filename=download);return
                self.reply(404,dict(error="페이지가 없습니다."))
            except (ValueError,OSError,sqlite3.Error) as exc:
                self.reply(400,dict(error=str(exc)))

        def do_POST(self):
            if not self.authorized():
                self.reply(403,dict(error="앱 화면에서 다시 시도하세요."));return
            try:
                size=int(self.headers.get("Content-Length",0))
                if not 0<size<=36*1024*1024:
                    self.reply(413,dict(error="파일 크기 한도는 25MB입니다."));return
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict):
                    raise ValueError("요청 형식이 올바르지 않습니다.")
                path=urlsplit(self.path).path
                if path=="/api/jobs":
                    self.reply(202,app.submit(payload))
                elif path=="/api/collector/start":
                    self.reply(200,app.start_collector())
                elif path=="/api/collector/stop":
                    self.reply(200,app.stop_collector())
                elif path=='/api/campaign/active':
                    if type(payload.get('active')) is not bool:raise ValueError('활성 상태를 확인하세요.')
                    app.archive.set_active(str(payload.get('campaign_id','')),payload['active'])
                    self.reply(200,dict(ok=True))
                else:
                    self.reply(404,dict(error="페이지가 없습니다."))
            except (ValueError,OSError,TypeError,sqlite3.Error) as exc:
                self.reply(400,dict(error=str(exc)))

    class Server(ThreadingHTTPServer):
        daemon_threads=True
        def get_request(self):
            conn,address=super().get_request();conn.settimeout(15);return conn,address
    return Server(("127.0.0.1",port),Handler)


def main():
    parser=argparse.ArgumentParser(description="시험지 워터마크 로컬 웹 앱")
    parser.add_argument("--port",type=int,default=8766)
    parser.add_argument("--no-browser",action="store_true")
    parser.add_argument('--collector-host')
    parser.add_argument('--collector-port',type=int,default=8765)
    parser.add_argument('--legacy-port',type=int)
    args=parser.parse_args()
    app=Application(collector_host=args.collector_host,collector_port=args.collector_port)
    try:app.start_collector()
    except OSError as exc:print(f'QR collector unavailable: {exc}',flush=True)
    server=create_web_server(app,args.port)
    url=f"http://127.0.0.1:{server.server_port}"
    redirect=None
    if args.legacy_port is not None:
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(302);self.send_header('Location',url);self.send_header('Cache-Control','no-store');self.send_header('Content-Length','0');self.end_headers()
            do_HEAD=do_GET
        redirect=ThreadingHTTPServer(('127.0.0.1',args.legacy_port),Redirect)
        threading.Thread(target=redirect.serve_forever,daemon=True).start()
    print(f"Watermark app: {url}\nClose this window or press Ctrl+C to stop.",flush=True)
    if not args.no_browser:
        threading.Timer(.5,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close();app.close()
        if redirect:redirect.shutdown();redirect.server_close()


if __name__=="__main__":
    mp.freeze_support()
    main()
