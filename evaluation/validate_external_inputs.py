"""Pixel-level input audit before any external-exam inference."""
import json
import math
from pathlib import Path
import pymupdf as fitz
from PIL import Image,ImageChops,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/external_validity'

def main():
    results=[]
    for folder in sorted((OUT/'inputs').iterdir()):
        meta=json.loads((folder/'marked.manifest.json').read_text(encoding='utf8'))
        with fitz.open(folder/'marked.pdf') as marked,fitz.open(folder/'control.pdf') as control:
            for i,page in enumerate(meta['pages']):
                a=control[i].get_pixmap(dpi=200,alpha=False);b=marked[i].get_pixmap(dpi=200,alpha=False)
                assert (a.width,a.height)==(b.width,b.height)
                diff=ImageChops.difference(Image.frombytes('RGB',(a.width,a.height),a.samples),Image.frombytes('RGB',(b.width,b.height),b.samples))
                draw=ImageDraw.Draw(diff);w,h=marked[i].rect.width,marked[i].rect.height;band=meta['border_pt'];scale=200/72
                regions=[(0,0,w,band),(0,h-band,w,h),(0,0,band,h),(w-band,0,w,h)]
                regions += [m[k] for m in page['question_marks'] for k in ('qr_bbox','label_bbox') if m.get(k)]
                regions += [r for box in page['passage_boxes'] for r in box['output_regions']]
                regions += [line['output_bbox'] for line in page.get('decoy_lines',[])]
                for x0,y0,x1,y1 in regions:draw.rectangle((math.floor(x0*scale)-3,math.floor(y0*scale)-3,math.ceil(x1*scale)+3,math.ceil(y1*scale)+3),fill=0)
                delta=max(v[1] for v in diff.getextrema())
                results.append(dict(exam=folder.name,page=i+1,body_max_delta=delta,qr=len(page['question_marks']),frames=len(page['passage_boxes'])))
                if delta:diff.save(OUT/f'audit-diff-{folder.name}-{i+1}.png')
    (OUT/'pixel_audit.json').write_text(json.dumps(results,indent=2))
    assert not any(r['body_max_delta'] for r in results),results
    print('PASS',len(results),'pages: no changed body pixels outside declared marks')
if __name__=='__main__':main()
