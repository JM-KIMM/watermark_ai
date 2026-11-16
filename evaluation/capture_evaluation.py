"""Fresh, resumable image-only local VLM evaluation of all objective exams."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import argparse
import base64
import csv
import hashlib
import json
import time
from urllib.error import HTTPError,URLError
import pymupdf as fitz
import corpus_evaluation as corpus
from benchmark_local import request,paired_stats
from question_layout import reserve_question_rows
from watermark import build
from webapp import build_options

ROOT=Path(__file__).resolve().parent.parent
CONDITIONS=('original','watermarked','layout_control')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')


def prepare(out):
    corpus.OUT=out
    corpus.ASSETS=out/'inputs'  # no unrelated legacy PDF image comparisons
    inventory=corpus.prepare(generate=False)
    for exam in inventory:
        if exam['status']!='included':continue
        source=ROOT/exam['source'];folder=out/'inputs'/exam['id'];folder.mkdir(parents=True,exist_ok=True)
        marked=folder/'watermarked.pdf';control=folder/'layout_control.pdf'
        options=build_options({},out)
        if not marked.exists():
            print('GENERATE',exam['id'],flush=True)
            build(source,marked,preview=True,**options)
        manifest=json.loads(marked.with_suffix('.manifest.json').read_text(encoding='utf8'))
        if manifest['source_sha256']!=sha(source) or manifest['feature_version']!='question-end-qr-passage-v3':
            raise ValueError('Changed inputs: use a new output directory')
        if not control.exists():
            with fitz.open(source) as original:
                for page in original:
                    if page.rotation:page.remove_rotation()
                doc,plans=reserve_question_rows(original,options['qr_size'])
                result=fitz.open()
                try:
                    for i,page in enumerate(doc):
                        b=manifest['border_pt']
                        p=result.new_page(width=page.rect.width+2*b,height=page.rect.height+2*b)
                        p.show_pdf_page(page.rect+(b,b,b,b),doc,i)
                    result.save(control,garbage=4,deflate=True)
                finally:result.close();doc.close()
        with fitz.open(marked) as m,fitz.open(control) as c:
            if [list(p.rect) for p in m]!=[list(p.rect) for p in c]:
                raise ValueError('Control and marked page sizes differ')
        exam['capture_inputs']={c:str(source if c=='original' else folder/(c+'.pdf')) for c in CONDITIONS}
        exam['capture_input_sha256']={c:sha(p) for c,p in exam['capture_inputs'].items()}
    write(out/'inventory.json',inventory)
    return inventory


def capture(out,exam,condition,page,dpi,doc):
    path=out/'captures'/exam['id']/condition/f'page-{page:03}.png'
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        doc[page-1].get_pixmap(dpi=dpi,alpha=False).save(path)
    return path


def infer(model,images,questions):
    prompt=('Solve the multiple-choice exam. Images show consecutive relevant pages in ascending page order. '
            'Read formulas, diagrams and passages from the images. '
            'Return only the choice number 1-5 for each requested question: '+', '.join(questions)+'.')
    attempts=[];start=time.monotonic()
    for attempt in range(3):
        values=[1,2,3,4,5] if attempt<2 else ['1','2','3','4','5']
        schema=dict(type='object',properties={q:dict(type='integer' if attempt<2 else 'string',enum=values) for q in questions},
                    required=questions,additionalProperties=False)
        try:
            response=request('http://127.0.0.1:11434/api/chat',dict(model=model,stream=False,format=schema,
                messages=[dict(role='user',content=prompt,images=images)],
                options=dict(seed=42,temperature=0,num_ctx=16384,num_predict=1024)),timeout=900)
            raw=response.get('message',{}).get('content','')
            parsed=json.loads(raw)
            if set(parsed)!=set(questions) or any(type(v) not in (int,str) or str(v) not in ('1','2','3','4','5') for v in parsed.values()):
                raise ValueError('Invalid answer schema')
            attempts.append(dict(raw=raw,encoding='integer' if attempt<2 else 'string',eval_count=response.get('eval_count')))
            return dict(answers={q:int(v) for q,v in parsed.items()},attempts=attempts,
                        seconds=time.monotonic()-start,error=None)
        except (ValueError,TypeError,AttributeError,HTTPError,URLError,TimeoutError) as exc:
            attempts.append(dict(error=str(exc),raw=locals().get('raw','')))
            if attempt<2:
                try:request('http://127.0.0.1:11434/api/generate',dict(model=model,keep_alive=0),timeout=60)
                except (HTTPError,URLError,TimeoutError):pass
    return dict(answers={q:None for q in questions},attempts=attempts,
                seconds=time.monotonic()-start,error='inference_failure')


def run(out,inventory,dpi):
    for exam in inventory:
        if exam['status']!='included':continue
        for condition,path in exam['capture_inputs'].items():
            if sha(path)!=exam['capture_input_sha256'][condition]:
                raise ValueError('An experiment PDF changed; use a new output directory')
    models=request('http://127.0.0.1:11434/api/tags',timeout=10)['models']
    model=next(m for m in models if m['name']=='qwen2.5vl:3b')
    protocol=dict(version=7,model=model,dpi=dpi,seed=42,temperature=0,num_ctx=16384,num_predict=1024,
        implementation_sha256={n:sha(ROOT/n) for n in ('watermark.py','question_layout.py','question_marks.py','passage_boxes.py')},
        conditions=list(CONDITIONS),input='Saved full-page PNG captures sent directly to the local vision model; no OCR, PDF text or answers in prompt',
        source='Digital PDF page rendering, not a physical camera photograph or AI-glasses measurement',
        control='Same question-end blank rows and outer canvas, without QR or watermark; separates layout/resizing effects',
        exclude='descriptive, math short-answer, English listening 1-17',
        retries='maximum 3; string schema only on third attempt; failures remain null',
        baseline='Fresh inference; no previous-version responses reused',
        grading_fix='English even-form question 44 is 3, verified against official answer-table image')
    identity=hashlib.sha256(json.dumps(dict(protocol=protocol,inputs=[e.get('capture_input_sha256') for e in inventory],
        keys=[[(s['id'],s['answers']) for s in e['sections']] for e in inventory]),sort_keys=True).encode()).hexdigest()
    if (out/'protocol.json').exists() and json.loads((out/'protocol.json').read_text(encoding='utf8'))['identity']!=identity:
        raise ValueError('Experiment identity changed; use a new output directory')
    write(out/'protocol.json',dict(identity=identity,**protocol))
    batch_index=0
    for exam in inventory:
        if exam['status']!='included':continue
        docs={c:fitz.open(exam['capture_inputs'][c]) for c in CONDITIONS}
        try:
            for section in exam['sections']:
                for page,batch in section['pages'].items():
                    order=CONDITIONS[batch_index%3:]+CONDITIONS[:batch_index%3];batch_index+=1
                    for condition in order:
                        cache=out/'responses'/exam['id']/section['id']/f'{condition}-{page}.json'
                        if cache.exists():
                            previous=json.loads(cache.read_text(encoding='utf8'))
                            if previous['identity']!=identity or any(sha(out/p)!=digest for p,digest in zip(previous['capture_paths'],previous['image_sha256'])):
                                raise ValueError('A cached response or its capture changed')
                            continue
                        paths=[capture(out,exam,condition,p,dpi,docs[condition]) for p in batch['context']]
                        data=[p.read_bytes() for p in paths]
                        record=infer(model['name'],[base64.b64encode(v).decode() for v in data],batch['questions'])
                        record.update(identity=identity,condition=condition,page=int(page),questions=batch['questions'],context_pages=batch['context'],
                            capture_paths=[str(p.relative_to(out)) for p in paths],image_sha256=[hashlib.sha256(v).hexdigest() for v in data])
                        write(cache,record)
                        print('DONE',batch_index,exam['id'],section['id'],page,condition,record['answers'],flush=True)
        finally:
            for d in docs.values():d.close()
        summarize(out,inventory,partial=True)
    return summarize(out,inventory)


def summarize(out,inventory,partial=False):
    rows=[];missing=[]
    for exam in inventory:
        if exam['status']!='included':continue
        for section in exam['sections']:
            answers={c:{} for c in CONDITIONS}
            for page in section['pages']:
                for c in CONDITIONS:
                    path=out/'responses'/exam['id']/section['id']/f'{c}-{page}.json'
                    if not path.exists():missing.append(str(path.relative_to(out)));continue
                    answers[c].update(json.loads(path.read_text(encoding='utf8'))['answers'])
            for q,expected in section['answers'].items():
                accepted=expected if isinstance(expected,list) else [expected]
                row=dict(exam=exam['source'],section=section['id'],question=q,accepted=accepted,weight=section['weights'][q])
                for c in CONDITIONS:
                    row[c]=answers[c].get(q)
                    row[c+'_status']='pending' if q not in answers[c] else 'inference_failure' if answers[c][q] is None else 'answered'
                    row[c+'_correct']=int(row[c] in accepted)
                rows.append(row)
    if missing and not partial:raise ValueError(f'Incomplete experiment: {len(missing)} missing responses')
    def scores(subset):
        return {c:dict(correct=sum(r[c+'_correct'] for r in subset),total=len(subset),
            percent=100*sum(r[c+'_correct'] for r in subset)/len(subset) if subset else None,
            inference_failures=sum(r[c+'_status']=='inference_failure' for r in subset),
            pending=sum(r[c+'_status']=='pending' for r in subset),
            points=sum(r[c+'_correct']*r['weight'] for r in subset),max_points=sum(r['weight'] for r in subset)) for c in CONDITIONS}
    report=dict(complete=not missing,total_exposures=len(rows),scores=scores(rows),
        exams=[dict(exam=e['source'],scores=scores([r for r in rows if r['exam']==e['source']])) for e in inventory if e['status']=='included'])
    if not missing:
        key={str(i):r['accepted'] for i,r in enumerate(rows)}
        report['paired']=paired_stats({c:{str(i):r[c] for i,r in enumerate(rows)} for c in ('original','watermarked')},key)
    write(out/'scores.json',report);write(out/'questions.json',rows)
    with (out/'questions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print('SCORES',json.dumps(report['scores']),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'outputs/capture_eval_v9')
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--summarize',action='store_true');p.add_argument('--dpi',type=int,default=150)
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    inventory=json.loads((out/'inventory.json').read_text(encoding='utf8')) if (out/'inventory.json').exists() else prepare(out)
    if args.summarize:summarize(out,inventory)
    elif not args.prepare_only:run(out,inventory,args.dpi)
