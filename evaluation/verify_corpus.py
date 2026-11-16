"""Check the actual corpus inputs and independently regrade every saved response."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repository root
import hashlib
import json
from pathlib import Path
import pymupdf as fitz
from PIL import Image,ImageChops,ImageDraw,ImageStat
from corpus_evaluation import OUT,ASSETS,ROOT


def main():
    inventory=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))
    checks=0;questions=0;totals={c:0 for c in ('original','level2','level3')};failures={c:0 for c in totals};render_flags=[]
    for exam in inventory:
        if exam['status']!='included':continue
        source=ROOT/exam['source']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==exam['source_sha256']
        with fitz.open(source) as original:
            for level in (2,3):
                path=ASSETS/exam['id']/f'level{level}.pdf'
                meta=json.loads(path.with_suffix('.manifest.json').read_text(encoding='utf-8'))
                assert meta['source_sha256']==exam['source_sha256']
                with fitz.open(path) as generated:
                    assert len(original)==len(generated)==len(meta['pages'])
                    for i,record in enumerate(meta['pages']):
                        band=meta['border_pt'];rect=original[i].rect
                        before=original[i].get_pixmap(alpha=False)
                        after=generated[i].get_pixmap(clip=fitz.Rect(band,band,band+rect.width,band+rect.height),alpha=False)
                        assert (before.width,before.height)==(after.width,after.height)
                        diff=ImageChops.difference(Image.frombytes('RGB',(before.width,before.height),before.samples),Image.frombytes('RGB',(after.width,after.height),after.samples))
                        draw=ImageDraw.Draw(diff)
                        regions=[m['qr_bbox'] for m in record['question_marks'] if m['qr_status']=='placed']+[m['output_bbox'] for m in record['line_patterns']]
                        regions += [m['label_bbox'] for m in record['question_marks'] if 'label_bbox' in m]
                        for x0,y0,x1,y1 in regions:draw.rectangle((int(x0-band)-2,int(y0-band)-2,int(x1-band)+2,int(y1-band)+2),fill=0)
                        maximum=max(v[1] for v in diff.getextrema());mean=max(ImageStat.Stat(diff).mean)
                        if maximum>2 or mean>=.001:
                            render_flags.append(dict(exam=exam['id'],level=level,page=i+1,max_channel_difference=maximum,mean_channel_difference=mean,bbox=diff.getbbox()))
                        checks+=1
        for section in exam['sections']:
            per_condition={c:{} for c in totals}
            for page,batch in section['pages'].items():
                for condition in totals:
                    record=json.loads((OUT/exam['id']/section['id']/f'{condition}-{page}.json').read_text(encoding='utf-8'))
                    if record.get('error'):
                        raw=record['answers']
                        assert set(raw)==set(batch['questions']) and all(v is None for v in raw.values())
                    else:
                        raw=json.loads(record['raw'])
                        assert {q:int(v) for q,v in raw.items()}==record['answers'] and set(raw)==set(batch['questions'])
                    assert record['context_pages']==batch['context']
                    assert not set(raw)&set(per_condition[condition])
                    per_condition[condition].update(raw)
            for q,key in section['answers'].items():
                accepted=key if isinstance(key,list) else [key]
                for condition,answers in per_condition.items():
                    totals[condition]+=answers[q] in accepted
                    failures[condition]+=answers[q] is None
                questions+=1
    reported=json.loads((OUT/'scores.json').read_text(encoding='utf-8'))
    assert questions==554==reported['total_exposures']
    assert totals==reported['totals']
    assert failures=={c:sum(e[c].get('inference_failures',0) for e in reported['exams']) for c in failures}
    result=dict(body_page_condition_checks=checks,render_strict_limit_flags=render_flags,independently_graded_questions=questions,totals=totals,inference_failures=failures,status='grading_passed')
    (OUT/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
