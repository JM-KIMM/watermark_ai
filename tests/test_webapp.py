import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

import pymupdf as fitz
from PIL import Image,ImageChops,ImageDraw,ImageStat

from csv_store import CSVStore
from watermark import build
from webapp import Application,create_web_server


def sample_pdf(path,pages=2):
    doc=fitz.open()
    for i in range(pages):
        p=doc.new_page()
        p.insert_text((80,150),f"{i+1}. Explain this question and choose the correct answer.")
        p.draw_line((60,320),(540,320),color=(0,0,0),width=.5)
        p.draw_line((80,420),(200,420),color=(0,0,0),width=.5)
        p.draw_line((80,420),(80,520),color=(0,0,0),width=.5)
        p.draw_rect(fitz.Rect(350,400,480,500),color=(0,0,0))
    doc.save(path);doc.close()


class GenerationTests(unittest.TestCase):
    def test_levels_pairs_and_graph_preservation(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/"source.pdf";sample_pdf(source)
            with self.assertRaises(ValueError):
                build(source,root/"level3.pdf",intensity=3,font_mode="file",preview=False)
            for level in (1,2):
                report=build(source,root/f"level{level}.pdf",intensity=level,font_mode="file",preview=False)
                self.assertEqual(report["border_pt"],0 if level==1 else 20)
                self.assertEqual(sum(m["qr_status"]=="placed" for p in report["pages"] for m in p["question_marks"]),2)
                for page in report["pages"]:
                    if level==1:
                        self.assertEqual(page["typography"],{})
                    else:
                        edges=page["typography"]["edge_payloads"]
                        self.assertEqual(edges["top"],edges["right"])
                        self.assertEqual(edges["bottom"],edges["left"])
                        self.assertNotIn("베트남",edges["top"]+edges["bottom"])
                        self.assertNotIn("Vietnam",edges["top"]+edges["bottom"])
                    self.assertNotIn("line_patterns",page)
                with fitz.open(source) as original, fitz.open(report["output"]) as generated:
                    band=report["border_pt"]
                    for i,record in enumerate(report["pages"]):
                        rect=original[i].rect
                        before=original[i].get_pixmap(alpha=False)
                        after=generated[i].get_pixmap(clip=fitz.Rect(band,band,band+rect.width,band+rect.height),alpha=False)
                        diff=ImageChops.difference(Image.frombytes("RGB",(before.width,before.height),before.samples),Image.frombytes("RGB",(after.width,after.height),after.samples))
                        draw=ImageDraw.Draw(diff)
                        regions=[mark["qr_bbox"] for mark in record["question_marks"] if mark["qr_status"]=="placed"]
                        regions += [mark["label_bbox"] for mark in record["question_marks"] if "label_bbox" in mark]
                        for x0,y0,x1,y1 in regions:
                            draw.rectangle((int(x0-band)-2,int(y0-band)-2,int(x1-band)+2,int(y1-band)+2),fill=(0,0,0))
                        self.assertLessEqual(max(hi for lo,hi in diff.getextrema()),2)
                        self.assertLess(max(ImageStat.Stat(diff).mean),.001)

    def test_qr_access_window(self):
        with TemporaryDirectory() as folder:
            store=CSVStore(Path(folder)/"csv");now=time.time()
            c=store.create_campaign("timed","http://127.0.0.1:8765",starts_at=now+60,ends_at=now+120)
            token=store.issue(c,1,"1").rsplit("/",1)[1];store.activate(c)
            self.assertEqual(store.access(token,"127.0.0.1",now=now),403)
            self.assertEqual(store.scans(),[])
            self.assertEqual(store.access(token,"127.0.0.1",now=now+61),200)
            self.assertEqual(store.access(token,"127.0.0.1",now=now+121),410)
            self.assertEqual(len(store.scans()),1)


class WebTests(unittest.TestCase):
    def test_upload_generate_download_and_auth(self):
        with TemporaryDirectory() as folder:
            app=Application(folder,job_timeout=60)
            server=create_web_server(app,0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f"http://127.0.0.1:{server.server_port}"
            source=Path(folder)/"upload.pdf";sample_pdf(source,pages=1)
            def request(path,payload=None,authorized=True):
                headers={"X-Local-Token":app.token} if authorized else {}
                data=json.dumps(payload).encode() if payload is not None else None
                return urlopen(Request(base+path,data=data,headers=headers),timeout=10)
            try:
                with urlopen(base) as response:
                    self.assertIn("시험지 워터마크",response.read().decode())
                with self.assertRaises(HTTPError) as error:
                    request("/api/collector",authorized=False)
                self.assertEqual(error.exception.code,403)
                bad=Request(base+"/api/collector",headers={"X-Local-Token":app.token,"Origin":"https://example.invalid"})
                with self.assertRaises(HTTPError):urlopen(bad)
                with request("/api/jobs",dict(filename="테스트.pdf",file=base64.b64encode(source.read_bytes()).decode(),settings=dict(intensity=1,font_mode="file"))) as response:
                    self.assertEqual(response.status,202);job=json.load(response)
                deadline=time.monotonic()+30
                while job["state"]=="working" and time.monotonic()<deadline:
                    time.sleep(.1)
                    with request("/api/jobs/"+job["id"]) as response:job=json.load(response)
                self.assertEqual(job["state"],"done",job)
                self.assertEqual(job["summary"]["qr"],1)
                with request("/api/jobs/"+job["id"]+"/pdf") as response:
                    self.assertTrue(response.read().startswith(b"%PDF"))
                with request("/api/jobs/"+job["id"]+"/manifest") as response:
                    self.assertEqual(json.load(response)["intensity"],1)
                with request("/api/scans.csv") as response:
                    self.assertTrue(response.read().startswith(b'\xef\xbb\xbf'))
            finally:
                server.shutdown();server.server_close();thread.join();app.close()


if __name__=="__main__":
    unittest.main()
