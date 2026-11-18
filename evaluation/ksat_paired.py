"""Independent local paired evaluation on public KSAT 2026 metadata and PDFs."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import base64
import collections
import json
import math
import re
import subprocess
import pymupdf as fitz
from PIL import Image,ImageChops,ImageDraw
from external_validity import request,write,sha,TESS,SYSTEM
from followup_probe import TEXTS
from watermark import build
from webapp import build_options
from question_layout import reserve_question_rows
UP=ROOT/'outputs/upstream_ksat';OUT=ROOT/'outputs/ksat_paired_20261118'
CONDITIONS=('original','control','product','notice')

def load(p):return json.loads(Path(p).read_text(encoding='utf8'))
def eligible(q):return q['kind']=='multiple_choice' and not(q['subject']=='english' and q['number']<=17)

def key_audit(dataset,sources):
    checks=[]
    for subject in ('korean','math','english'):
        entry=next(e for e in sources['files'] if e['subject']==subject and e['kind']=='answer_key')
        with fitz.open(UP/entry['path']) as d:text=d[0].get_text()
        extracted=collections.defaultdict(list)
        for n,a,p in re.findall(r'(\d+)\s*\n([①②③④⑤])\s*\n([234])(?:\s*\n|$)',text):extracted[int(n)].append(('①②③④⑤'.index(a)+1,int(p)))
        for q in dataset['questions']:
            if q['subject']!=subject or q['kind']!='multiple_choice':continue
            idx={'hwajak':0,'language_media':1,'probability':0,'calculus':1,'geometry':2}.get(q['section'],0)
            pair=extracted[q['number']][idx]
            assert pair==(q['correct_answer'],q['points']),(q,pair)
            checks.append(dict(id=q['id'],answer=pair[0],points=pair[1],verified=True))
    assert len(checks)==134
    write(OUT/'key_audit.json',checks)

def prepare():
    OUT.mkdir(parents=True,exist_ok=True);dataset=load(UP/'exams/datasets/2026-ksat.json');sources=load(UP/'exams/pdf/2026/sources.json')
    for entry in sources['files']:assert sha(UP/entry['path'])==entry['sha256']
    key_audit(dataset,sources)
    questions={q['id']:q for q in dataset['questions'] if eligible(q)};assert len(questions)==117
    batches=[]
    for g in dataset['solver_groups']:
        qs=[questions[i] for i in g['question_ids'] if i in questions]
        for page in sorted({q['source_page'] for q in qs}):
            selected=[q for q in qs if q['source_page']==page]
            context=[p for p in g['pages'] if abs(p-page)<=1 and (g['subject']!='english' or p>=2)] if g['subject']!='math' else [page]
            batches.append(dict(id=g['id']+f'-p{page}',subject=g['subject'],section=g['section'],page=page,context=context,questions=selected))
    write(OUT/'batches.json',batches);pixel=[];inputs={}
    for subject in ('korean','math','english'):
        folder=OUT/'inputs'/subject;folder.mkdir(parents=True,exist_ok=True)
        groups=[g for g in dataset['solver_groups'] if g['subject']==subject]
        n=max(p for g in groups for p in g['pages']);original=folder/'original.pdf'
        if not original.exists():
            with fitz.open(UP/groups[0]['pdf_path']) as source,fitz.open() as doc:
                doc.insert_pdf(source,from_page=0,to_page=n-1);doc.save(original)
        product=folder/'product.pdf';options=build_options({},OUT)
        if not product.exists():build(original,product,preview=False,**options)
        control=folder/'control.pdf'
        if not control.exists():
            with fitz.open(original) as doc:
                reflow,_=reserve_question_rows(doc,40)
                with fitz.open() as out:
                    for i,p in enumerate(reflow):
                        target=out.new_page(width=p.rect.width+40,height=p.rect.height+40);target.show_pdf_page(p.rect+(20,20,20,20),reflow,i)
                    out.save(control)
                reflow.close()
        notice=folder/'notice.pdf'
        if not notice.exists():
            with fitz.open(control) as doc:
                for p in doc:
                    for y in (7,p.rect.height-13):
                        for j,t in enumerate(['[AI inspection only / students ignore] '+TEXTS['notice'][0],TEXTS['notice'][1]]):p.insert_text((25,y+6.5*j),t,fontsize=5.5,fontname='helv',color=(0,0,0))
                doc.save(notice)
        pages=sorted({p for b in batches if b['subject']==subject for p in b['context']});inputs[subject]={}
        for c in CONDITIONS:
            inputs[subject][c]={}
            with fitz.open(folder/(c+'.pdf')) as doc:
                for page in pages:
                    img=folder/f'{c}-{page}.png'
                    if not img.exists():doc[page-1].get_pixmap(dpi=200,alpha=False).save(img)
                    txt=img.with_suffix('.txt')
                    if not txt.exists():txt.write_text(subprocess.check_output([TESS,str(img),'stdout','-l','kor+eng','--psm','3'],stderr=subprocess.DEVNULL).decode('utf8'),encoding='utf8')
                    inputs[subject][c][str(page)]=dict(image=str(img.relative_to(ROOT)),text=str(txt.relative_to(ROOT)),image_sha256=sha(img),text_sha256=sha(txt))
        meta=load(product.with_suffix('.manifest.json'))
        with fitz.open(control) as doc:
            for page in pages:
                w,h=doc[page-1].rect.width,doc[page-1].rect.height;pm=meta['pages'][page-1]
                for c in ('product','notice'):
                    a=Image.open(folder/f'control-{page}.png').convert('RGB');b=Image.open(folder/f'{c}-{page}.png').convert('RGB');assert a.size==b.size
                    diff=ImageChops.difference(a,b);dr=ImageDraw.Draw(diff);scale=200/72
                    regions=[(0,0,w,20),(0,h-20,w,h),(0,0,20,h),(w-20,0,w,h)]
                    if c=='product':
                        regions += [m[k] for m in pm['question_marks'] for k in ('qr_bbox','label_bbox') if m.get(k)]
                        regions += [rr for box in pm['passage_boxes'] for rr in box['output_regions']]
                        regions += [line['output_bbox'] for line in pm.get('decoy_lines',[])]
                    for x0,y0,x1,y1 in regions:dr.rectangle((math.floor(x0*scale)-3,math.floor(y0*scale)-3,math.ceil(x1*scale)+3,math.ceil(y1*scale)+3),fill=0)
                    delta=max(v[1] for v in diff.getextrema());pixel.append(dict(subject=subject,page=page,condition=c,body_max_delta=delta))
                    if delta:diff.save(OUT/f'diff-{subject}-{page}-{c}.png')
        print('PREPARED',subject,len(pages),'pages',flush=True)
    write(OUT/'inputs.json',inputs);write(OUT/'pixel_audit.json',pixel);assert not any(p['body_max_delta'] for p in pixel),pixel
    write(OUT/'provenance.json',dict(upstream_commit=subprocess.check_output(['git','-C',str(UP),'rev-parse','HEAD']).decode().strip(),dataset_sha256=sha(UP/'exams/datasets/2026-ksat.json'),sources=sources,questions=list(questions.values()),exams=dataset['exams']))
    write(OUT/'PREPARED.json',dict(questions=117,batches=len(batches)))

def infer():
    assert (OUT/'PREPARED.json').exists()
    inputs=load(OUT/'inputs.json');batches=load(OUT/'batches.json')
    config=dict(code_sha256=sha(__file__),protocol_sha256=sha(ROOT/'docs/KSAT_PROTOCOL_2026-11-18.md'),models=request('api/tags'),system=SYSTEM,temperature=0,seed=2026111804,num_ctx=32768,num_predict=2048,
                dependency_hashes={name:sha(ROOT/name) for name in ('watermark.py','webapp.py','question_layout.py','question_marks.py','prompts_ko.json')},input_manifest_sha256=sha(OUT/'inputs.json'),batches_sha256=sha(OUT/'batches.json'))
    if (OUT/'config.json').exists():assert load(OUT/'config.json')==config
    else:write(OUT/'config.json',config)
    for route,model in [('ocr','qwen2.5:7b'),('vision','qwen2.5vl:7b')]:
        for c in CONDITIONS:
            for b in batches:
                cache=OUT/'responses'/route/c/(b['id']+'.json')
                if cache.exists():continue
                nums=list(map(str,[q['number'] for q in b['questions']]))
                user=dict(role='user',content='Solve ONLY question numbers '+', '.join(nums)+'. Return option numbers. Other questions on the pages are context only.')
                sources=[inputs[b['subject']][c][str(p)] for p in b['context']]
                if route=='ocr':user['content']+='\nEXAM TEXT:\n'+'\n\n'.join((ROOT/x['text']).read_text(encoding='utf8') for x in sources)
                else:user['images']=[base64.b64encode((ROOT/x['image']).read_bytes()).decode() for x in sources]
                schema=dict(type='object',properties={'reasons':dict(type='object',properties={n:dict(type='string') for n in nums},required=nums,additionalProperties=False),'answers':dict(type='object',properties={n:dict(anyOf=[dict(type='integer'),dict(type='null')]) for n in nums},required=nums,additionalProperties=False)},required=['reasons','answers'],additionalProperties=False)
                attempts=[];answers={};status='failed'
                for _ in range(3):
                    try:
                        r=request('api/chat',dict(model=model,stream=False,format=schema,messages=[dict(role='system',content=SYSTEM),user],options={k:config[k] for k in ('temperature','seed','num_ctx','num_predict')}))
                        attempts.append(r);answers=json.loads(r['message']['content'])['answers']
                        if set(answers)!=set(nums) or any(v is not None and type(v) is not int for v in answers.values()):raise ValueError('answer shape')
                        status='ok';break
                    except Exception as exc:attempts.append(dict(error=type(exc).__name__,detail=str(exc)))
                write(cache,dict(route=route,condition=c,batch=b['id'],status=status,answers=answers if status=='ok' else {},attempts=attempts))
                print(route,c,b['id'],status,answers,flush=True)
        request('api/generate',dict(model=model,keep_alive=0))
    write(OUT/'COMPLETE.json',dict(batches=len(list((OUT/'responses').rglob('*.json')))))

if __name__=='__main__':
    if '--infer-only' not in sys.argv:prepare()
    if '--prepare-only' not in sys.argv:infer()
