"""Audit saved question-end PDFs and unchanged pixels outside intentional marks."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import argparse
import json
import math
from PIL import Image,ImageChops,ImageDraw,ImageStat
import pymupdf as fitz


def rgb(pix):return Image.frombytes('RGB',(pix.width,pix.height),pix.samples)


def verify(out):
    inventory=json.loads((out/'inventory.json').read_text(encoding='utf8'))
    reports=[]
    for exam in inventory:
        if exam['status']!='included':continue
        meta=json.loads(Path(exam.get('marked_manifest',out/'inputs'/exam['id']/'watermarked.manifest.json')).read_text(encoding='utf8'))
        entries=[]
        with fitz.open(exam['capture_inputs']['watermarked']) as marked,fitz.open(exam['capture_inputs']['layout_control']) as control,fitz.open(exam['capture_inputs']['original']) as original:
            for i,page in enumerate(meta['pages']):
                b=meta['border_pt'];marks=page['question_marks'];plan=page['question_layout']
                slots=[s for c in plan['columns'] for s in c['slots']]
                if len(slots)!=len(marks) or any(m['qr_status']!='placed' for m in marks):
                    raise ValueError('Missing question-end QR')
                for m,s in zip(marks,slots):
                    if m['number']!=s['question']['number'] or not fitz.Rect(s['slot_bbox']).contains(fitz.Rect(m['label_source_bbox'])):
                        raise ValueError('QR/label outside reserved row or mismatched question')
                a=control[i].get_pixmap(alpha=False);z=marked[i].get_pixmap(alpha=False)
                if (a.width,a.height)!=(z.width,z.height):raise ValueError('Different control dimensions')
                diff=ImageChops.difference(rgb(a),rgb(z));draw=ImageDraw.Draw(diff)
                before=rgb(original[i].get_pixmap(alpha=False));plain=rgb(a)
                source_delta=0;source_mean=0;source_body_delta=0
                # A logo straddling the column split is resampled as two image
                # fragments. Record that difference, and also check exam content
                # separately without this non-question header artwork.
                header_images=[fitz.Rect(v['bbox']) for v in original[i].get_image_info()
                               if v['bbox'][3]<original[i].rect.height*.2
                               and v['bbox'][0]<original[i].rect.width/2<v['bbox'][2]]
                chunks=[]
                for col in plan['columns']:
                    previous=0;shift=0
                    for slot in col['slots']+[dict(cut=plan['footer'])]:
                        chunks.append((col['x0'],previous,col['x1'],slot['cut'],shift))
                        previous=slot['cut'];shift+=plan['gap']
                chunks.append((0,plan['footer'],plan['original_size'][0],plan['original_size'][1],plan['added_height']))
                for x0,y0,x1,y1,shift in chunks:
                    crop=(math.ceil(x0)+1,math.ceil(y0)+1,math.floor(x1)-1,math.floor(y1)-1)
                    if crop[2]<=crop[0] or crop[3]<=crop[1]:continue
                    dst=(int(crop[0]+b),int(crop[1]+b+shift),int(crop[2]+b),int(crop[3]+b+shift))
                    delta=ImageChops.difference(before.crop(crop),plain.crop(dst))
                    source_delta=max(source_delta,max(v[1] for v in delta.getextrema()))
                    source_mean=max(source_mean,max(ImageStat.Stat(delta).mean))
                    body_draw=ImageDraw.Draw(delta)
                    for r in header_images:
                        body_draw.rectangle((math.floor(r.x0)-crop[0]-2,math.floor(r.y0)-crop[1]-2,
                                             math.ceil(r.x1)-crop[0]+2,math.ceil(r.y1)-crop[1]+2),fill=0)
                    source_body_delta=max(source_body_delta,max(v[1] for v in delta.getextrema()))
                w,h=marked[i].rect.width,marked[i].rect.height
                regions=[(0,0,w,b),(0,h-b,w,h),(0,0,b,h),(w-b,0,w,h)]
                regions += [m[k] for m in marks for k in ('qr_bbox','label_bbox')]
                regions += [r for box in page['passage_boxes'] for r in box['output_regions']]
                for x0,y0,x1,y1 in regions:
                    draw.rectangle((math.floor(x0)-2,math.floor(y0)-2,math.ceil(x1)+2,math.ceil(y1)+2),fill=0)
                max_delta=max(v[1] for v in diff.getextrema());mean=max(ImageStat.Stat(diff).mean)
                entries.append(dict(page=i+1,qr=len(marks),boxes=len(page['passage_boxes']),body_max_delta=max_delta,body_mean_delta=mean,
                    original_to_control_max_delta=source_delta,original_to_control_max_chunk_mean=source_mean,
                    original_to_control_body_max_delta=source_body_delta))
        # Every scored question must have a corresponding QR on its source page.
        for section in exam['sections']:
            for p,batch in section['pages'].items():
                actual={m['number'] for idx,item in enumerate(meta['pages']) for m in item['question_marks'] if m.get('origin_page',idx+1)==int(p)}
                if not set(batch['questions'])<=actual:raise ValueError('A scored question has no QR')
        reports.append(dict(exam=exam['source'],pages=entries))
        print(exam['id'],'qr',sum(p['qr'] for p in entries),'boxes',sum(p['boxes'] for p in entries),
              'max',max(p['body_max_delta'] for p in entries),'mean',max(p['body_mean_delta'] for p in entries),flush=True)
    result=dict(exams=reports,total_pages=sum(len(e['pages']) for e in reports),
        total_qr=sum(p['qr'] for e in reports for p in e['pages']),
        total_boxes=sum(p['boxes'] for e in reports for p in e['pages']),
        scored_questions_have_qr=True,
        note='Pixel differences compare the same reflowed layout with and without marks; added border, QR/captions and replaced frame strips are masked.')
    (out/'layout_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args();verify(args.output.resolve())
