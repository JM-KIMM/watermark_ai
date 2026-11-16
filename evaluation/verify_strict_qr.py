"""Decode every URL QR from the final PDF crop; never visit experimental links."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import cv2
import numpy as np
import pymupdf as fitz


def verify(out):
    inventory=json.loads((out/'inventory.json').read_text(encoding='utf8'))
    detector=cv2.QRCodeDetector();files=[];failures=[]
    for e in inventory:
        if e['status']!='included':continue
        path=Path(e['inputs']['current_choices'])
        meta=json.loads(path.with_suffix('.manifest.json').read_text(encoding='utf8'))
        counts={str(dpi):dict(correct=0,total=0) for dpi in (200,300)}
        with fitz.open(path) as doc:
            for i,page in enumerate(meta['pages']):
                for m in page['question_marks']:
                    expected=m['qr_payload'];url=urlsplit(expected)
                    if url.scheme not in ('http','https') or not url.path.startswith('/q/'):raise ValueError('QR is not an access URL')
                    for dpi in (200,300):
                        pix=doc[i].get_pixmap(dpi=dpi,clip=fitz.Rect(m['qr_bbox']),alpha=False)
                        array=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3)
                        actual,_,_=detector.detectAndDecode(array)
                        counts[str(dpi)]['total']+=1;counts[str(dpi)]['correct']+=actual==expected
                        if actual!=expected:failures.append(dict(exam=e['id'],page=i+1,question=m['number'],dpi=dpi,payload_sha256=hashlib.sha256(expected.encode()).hexdigest()))
        files.append(dict(exam=e['id'],decode=counts));print(e['id'],counts,flush=True)
    result=dict(files=files,failures=failures,http_requests_sent=0,
                note='Raster crop decode; neither a camera measurement nor proof that an LLM visits QR URLs.')
    (out/'qr_verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    if any(f['dpi']==300 for f in failures):raise ValueError('A 300dpi URL QR failed to decode')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);verify(p.parse_args().output.resolve())
