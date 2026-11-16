"""Preregistered, resumable vision and real OCR+LLM paired evaluation."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import subprocess
import time

import pymupdf as fitz
from benchmark_local import request
from capture_evaluation import sha
from csv_store import CSVStore
from question_layout import reserve_question_rows
from strict_model_client import infer,PROMPT,SYSTEM_PROMPT
from watermark import build
from webapp import lan_address

ROOT=Path(__file__).resolve().parent.parent
PRIMARY=('original','layout_control','current_choices')
ABLATIONS=('qr_only','helpful_legacy','command_only','other_page')
POLICY={'current_choices':'current-choices','qr_only':'qr-only','helpful_legacy':'helpful-legacy','command_only':'command-only','other_page':'other-page'}
TESSERACT=Path(os.environ.get('TESSERACT_EXE','C:/Program Files/Tesseract-OCR/tesseract.exe'))
IMPLEMENTATION=('watermark.py','watermark_payloads.py','question_layout.py','question_marks.py','passage_boxes.py','source_glyphs.py','evaluation/strict_model_client.py','evaluation/strict_evaluation.py')


def write(path,value):
    import tempfile
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.'+path.name,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf8') as h:
            json.dump(value,h,ensure_ascii=False,indent=2);h.flush();os.fsync(h.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def cluster(exam,section,q):
    if exam['id'] in ('exam02','exam03','exam04') and int(q)<=40:return 'tax-account:'+q
    family=section.removeprefix('odd_').removeprefix('even_')
    if family in ('odd','even'):family='english'
    return exam['id']+':'+family+':'+q


def select_pilot(inventory):
    selected=[]
    for e in inventory:
        if e['status']!='included':continue
        candidates=[dict(exam=e['id'],section=s['id'],question=q,cluster=cluster(e,s['id'],q)) for s in e['sections'] for q in s['answers']]
        if e['id']=='exam05':groups=[([v for v in candidates if v['section']==s],n) for s,n in [('odd_common',4),('odd_speech',3),('odd_language',3)]]
        elif e['id']=='exam08':groups=[([v for v in candidates if v['section']==s],n) for s,n in [('odd_common',3),('odd_probability',3),('odd_calculus',2),('odd_geometry',2)]]
        elif e['id']=='exam09':groups=[([v for v in candidates if v['section']=='odd'],10)]
        elif e['id'] in ('exam01','exam02'):groups=[([v for v in candidates if int(v['question'])<=40],5),([v for v in candidates if int(v['question'])>40],5)]
        else:groups=[([v for v in candidates if int(v['question'])>40],10)]
        for choices,n in groups:
            choices.sort(key=lambda v:hashlib.sha256(('2026-11-16|'+v['exam']+'|'+v['section']+'|'+v['question']).encode()).hexdigest())
            if len(choices)<n:raise ValueError('Insufficient fixed pilot stratum')
            selected+=choices[:n]
    if len(selected)!=70 or len({v['cluster'] for v in selected})!=70:raise ValueError('Pilot must contain 70 distinct question clusters')
    return selected


def initialize(out):
    inventory=json.loads((ROOT/'docs/evaluation/capture_inventory.json').read_text(encoding='utf8'))
    included=[e for e in inventory if e['status']=='included']
    for e in included:
        if sha(ROOT/e['source'])!=e['source_sha256']:raise ValueError('Original PDF has changed')
    if sum(len(s['answers']) for e in included for s in e['sections'])!=554:raise ValueError('Expected 554 objective exposures')
    models=request('http://127.0.0.1:11434/api/tags')['models']
    wanted={n:next(m for m in models if m['name']==n) for n in ('qwen2.5vl:7b','qwen2.5:7b')}
    plan=dict(version=1,dpi=200,num_ctx=32768,num_predict=1024,temperature=0,seeds=[42,314,2026],
        primary=list(PRIMARY),diagnostics=list(ABLATIONS),pilot=select_pilot(inventory),
        prompt=PROMPT,system_prompt=SYSTEM_PROMPT,models=wanted,ollama=request('http://127.0.0.1:11434/api/version'),
        tesseract=dict(version=subprocess.check_output([str(TESSERACT),'--version'],text=True,encoding='utf8',errors='replace').splitlines()[0],
                       executable_sha256=sha(TESSERACT),languages=['kor+eng'],psm=3,oem=1,
                       traineddata={lang:sha(TESSERACT.parent/'tessdata'/(lang+'.traineddata')) for lang in ('kor','eng')}),
        implementation={n:sha(ROOT/n) for n in IMPLEMENTATION},plan_document_sha256=sha(ROOT/'docs/STRICT_EXPERIMENT_PLAN.md'),
        commercial=dict(status='not_run',reason='Separate API connection selected by user; no configured credentials/model'),
        qr=dict(base_url=f'http://{lan_address()}:8765',tool_access=False,meaning='Model clients have no URL tools. Access logging is a separate HTTP functionality test.'),
        exclusions='listening, descriptive, math short-answer',
        prior_data='Previously seen corpus; no claim of an untouched external holdout')
    identity=hashlib.sha256(json.dumps(dict(plan=plan,keys=[e['sections'] for e in included]),sort_keys=True).encode()).hexdigest()
    if (out/'plan.json').exists():
        old=json.loads((out/'plan.json').read_text(encoding='utf8'))
        if old['identity']!=identity:raise ValueError('Frozen experiment changed: choose a new output directory')
        return json.loads((out/'inventory.json').read_text(encoding='utf8')),old
    write(out/'inventory.json',inventory);write(out/'plan.json',dict(identity=identity,**plan))
    return inventory,dict(identity=identity,**plan)


def prepare(out,inventory,plan):
    ledger=CSVStore(ROOT/'data/qr_csv')
    registry=out/'campaigns.json'
    campaigns=json.loads(registry.read_text(encoding='utf8')) if registry.exists() else {}
    for e in inventory:
        if e['status']!='included':continue
        source=ROOT/e['source'];folder=out/'inputs'/e['id'];folder.mkdir(parents=True,exist_ok=True)
        if e['id'] not in campaigns:
            campaigns[e['id']]=ledger.create_campaign('실험용 · '+e['source'],plan['qr']['base_url'],days=90,issuance_ref='EXPERIMENT · '+e['id'])
            ledger.activate(campaigns[e['id']]);write(registry,campaigns)
        tracking=dict(db=str(ledger.path),campaign_id=campaigns[e['id']],base_url=plan['qr']['base_url'],archive=str(ROOT/'data/qr_archive'))
        e['inputs']={'original':str(source)}
        for condition in ('current_choices',)+ABLATIONS:
            target=folder/(condition+'.pdf')
            if not target.exists():
                print('BUILD',e['id'],condition,flush=True)
                build(source,target,intensity=2,mode='command',font_mode='file',size=6,opacity=.9,band=20,
                      question_style='qr',qr_size=40,qr_placement='question-end',size_jitter=0,
                      replace_passage_boxes=condition!='qr_only',payload_policy=POLICY[condition],tracking=tracking,preview=condition=='current_choices')
            e['inputs'][condition]=str(target)
        control=folder/'layout_control.pdf'
        if not control.exists():
            with fitz.open(source) as original:
                if any(p.first_annot is not None for p in original):original.bake(annots=True,widgets=False)
                for p in original:
                    if p.rotation:p.remove_rotation()
                reflow,_=reserve_question_rows(original,40);result=fitz.open()
                try:
                    for i,p in enumerate(reflow):
                        target=result.new_page(width=p.rect.width+40,height=p.rect.height+40)
                        target.show_pdf_page(p.rect+(20,20,20,20),reflow,i)
                    result.save(control,garbage=4,deflate=True)
                finally:result.close();reflow.close()
        e['inputs']['layout_control']=str(control)
        e['input_sha256']={c:sha(p) for c,p in e['inputs'].items()}
        e['capture_inputs']={'original':str(source),'watermarked':e['inputs']['current_choices'],'layout_control':str(control)}
        e['marked_manifest']=str(folder/'current_choices.manifest.json')
        meta=json.loads(Path(e['marked_manifest']).read_text(encoding='utf8'))
        for s in e['sections']:
            for page,b in s['pages'].items():
                source_items=meta['pages'][int(page)-1]['source_items']
                for q in b['questions']:
                    item=next(v for v in source_items if v['question']==q)
                    if not item['complete'] or len(item['choices'])!=5:raise ValueError('Incomplete current-choice treatment')
        for p in meta['pages']:
            if p['typography'].get('unrenderable') or any(r['unrenderable'] for f in p['passage_boxes'] for r in f['rendering']):
                raise ValueError('Unrenderable source symbols: fix input fidelity before inference')
        # Same QR payload and location across every QR-bearing condition.
        reference=[[ (m['number'],m['qr_payload'],m['qr_bbox']) for m in p['question_marks']] for p in meta['pages']]
        for c in ABLATIONS:
            record=json.loads((folder/(c+'.manifest.json')).read_text(encoding='utf8'))
            actual=[[(m['number'],m['qr_payload'],m['qr_bbox']) for m in p['question_marks']] for p in record['pages']]
            if actual!=reference:raise ValueError('QR changed between ablation conditions')
        write(out/'inventory.json',inventory)
    from verify_capture_layout import verify
    verified=verify(out)
    if any(p['body_max_delta'] for e in verified['exams'] for p in e['pages']):
        raise ValueError('Treatment changed pixels outside declared watermark/QR regions')


def selected(plan,e,s,b):
    return any(v['exam']==e['id'] and v['section']==s['id'] and v['question'] in b['questions'] for v in plan['pilot'])


def image_path(out,e,c,page):return out/'captures'/e['id']/c/f'page-{page:03}.png'


def captures(out,inventory,plan):
    for e in inventory:
        if e['status']!='included':continue
        needed={c:set() for c in PRIMARY+ABLATIONS}
        for s in e['sections']:
            for b in s['pages'].values():
                for c in PRIMARY:needed[c].update(b['context'])
                if selected(plan,e,s,b):
                    for c in ABLATIONS:needed[c].update(b['context'])
        for c,pages in needed.items():
            with fitz.open(e['inputs'][c]) as d:
                for page in sorted(pages):
                    path=image_path(out,e,c,page)
                    if not path.exists():path.parent.mkdir(parents=True,exist_ok=True);d[page-1].get_pixmap(dpi=plan['dpi'],alpha=False).save(path)
        print('CAPTURED',e['id'],flush=True)
    seal=dict(identity=plan['identity'],pdfs={e['id']:{c:sha(p) for c,p in e['inputs'].items()} for e in inventory if e['status']=='included'},
              captures={str(p.relative_to(out)):sha(p) for p in sorted((out/'captures').glob('*/*/*.png'))})
    path=out/'input_seal.json'
    if path.exists() and json.loads(path.read_text(encoding='utf8'))!=seal:raise ValueError('Sealed captures changed')
    write(path,seal)


def ocr_one(out,e,c,page,plan):
    image=image_path(out,e,c,page);cache=out/'ocr'/e['id']/c/f'{page}.json'
    if cache.exists():
        record=json.loads(cache.read_text(encoding='utf8'))
        if record['image_sha256']!=sha(image):raise ValueError('OCR input image changed')
        if record['text_sha256']!=hashlib.sha256(record['text'].encode()).hexdigest():raise ValueError('OCR text changed')
        return cache
    cache.parent.mkdir(parents=True,exist_ok=True);prefix=cache.with_suffix('')
    # English exam task instructions are Korean as well.
    lang='kor+eng'
    env=dict(os.environ,OMP_THREAD_LIMIT='2')
    command=[str(TESSERACT),str(image),str(prefix),'-l',lang,'--oem','1','--psm','3','txt','tsv']
    begin=time.monotonic();done=subprocess.run(command,env=env,capture_output=True,timeout=300)
    if done.returncode:raise RuntimeError('OCR failed: '+done.stderr.decode('utf8',errors='replace')[:300])
    text=prefix.with_suffix('.txt').read_text(encoding='utf8')
    write(cache,dict(text=text,lang=lang,seconds=time.monotonic()-begin,image_sha256=sha(image),text_sha256=hashlib.sha256(text.encode()).hexdigest()))
    return cache


def run_backend(out,inventory,plan,backend,workers=2):
    seal_path=out/'input_seal.json';seal=json.loads(seal_path.read_text(encoding='utf8'));seal_digest=sha(seal_path)
    for relative,digest in seal['captures'].items():
        if sha(out/relative)!=digest:raise ValueError('A registered capture changed')
    model='qwen2.5vl:7b' if backend=='vision' else 'qwen2.5:7b'
    jobs=[]
    for seed in plan['seeds']:
        counter=0
        for e in inventory:
            if e['status']!='included':continue
            for s in e['sections']:
                for page,b in s['pages'].items():
                    is_pilot=selected(plan,e,s,b)
                    if seed!=42 and not is_pilot:continue
                    conditions=PRIMARY+(ABLATIONS if is_pilot and seed==42 else ())
                    order=conditions[counter%len(conditions):]+conditions[:counter%len(conditions)];counter+=1
                    for c in order:jobs.append((e,s,page,b,c,seed))
    ocr_futures={};pool=ThreadPoolExecutor(max_workers=workers) if backend=='ocr_llm' else None
    if pool:
        for e,_,_,b,c,_ in jobs:
            for page in b['context']:
                key=(e['id'],c,page)
                if key not in ocr_futures:ocr_futures[key]=pool.submit(ocr_one,out,e,c,page,plan)
    try:
        for index,(e,s,page,b,c,seed) in enumerate(jobs):
            target=out/'responses'/backend/f'seed-{seed}'/e['id']/s['id']/f'{c}-{page}.json'
            paths=[image_path(out,e,c,p) for p in b['context']];digests=[sha(p) for p in paths]
            if target.exists():
                previous=json.loads(target.read_text(encoding='utf8'))
                if previous['identity']!=plan['identity'] or previous['image_sha256']!=digests or previous['input_seal_sha256']!=seal_digest:raise ValueError('Cached inference identity mismatch')
                continue
            kwargs={};ocr_records=[]
            if backend=='vision':kwargs['images']=[p.read_bytes() for p in paths]
            else:
                for p in b['context']:
                    cache=ocr_futures[(e['id'],c,p)].result();ocr_records.append(json.loads(cache.read_text(encoding='utf8')))
                kwargs['ocr_text']='\n\n'.join(f'[PAGE {p}]\n'+r['text'] for p,r in zip(b['context'],ocr_records))
            record=infer(model,b['questions'],seed=seed,**kwargs)
            record.update(identity=plan['identity'],backend=backend,model=model,exam=e['id'],section=s['id'],page=int(page),
                          input_seal_sha256=seal_digest,
                          condition=c,seed=seed,questions=b['questions'],context_pages=b['context'],image_sha256=digests,
                          ocr_text_sha256=[r['text_sha256'] for r in ocr_records],input_characters=len(kwargs.get('ocr_text','')))
            write(target,record)
            print('STRICT',backend,index+1,'/',len(jobs),e['id'],s['id'],page,c,seed,record['status'],record['answers'],flush=True)
        summarize(out,inventory,plan,backend)
    finally:
        if pool:pool.shutdown(wait=True)
        request('http://127.0.0.1:11434/api/generate',dict(model=model,keep_alive=0),timeout=60)


def summarize(out,inventory,plan,backend):
    rows=[]
    for seed in plan['seeds']:
        for e in inventory:
            if e['status']!='included':continue
            for s in e['sections']:
                for page,b in s['pages'].items():
                    is_pilot=selected(plan,e,s,b)
                    if seed!=42 and not is_pilot:continue
                    for c in PRIMARY+(ABLATIONS if is_pilot and seed==42 else ()):
                        path=out/'responses'/backend/f'seed-{seed}'/e['id']/s['id']/f'{c}-{page}.json'
                        if not path.exists():raise ValueError('Cannot summarize unfinished strict evaluation')
                        r=json.loads(path.read_text(encoding='utf8'))
                        for q in b['questions']:
                            expected=s['answers'][q];accepted=expected if isinstance(expected,list) else [expected]
                            pilot=any(v['exam']==e['id'] and v['section']==s['id'] and v['question']==q for v in plan['pilot'])
                            rows.append(dict(exam=e['id'],source=e['source'],section=s['id'],question=q,cluster=cluster(e,s['id'],q),seed=seed,condition=c,pilot=pilot,
                                answer=r['answers'][q],accepted=accepted,status=r['status'],correct=int(r['answers'][q] in accepted),weight=s['weights'][q]))
    def metric(values):
        unresolved=sum(v['status'] not in ('ok','refused') for v in values);resolved=len(values)-unresolved
        answered=sum(v['status']=='ok' and v['answer'] is not None for v in values)
        correct=sum(v['correct'] for v in values if v['status']=='ok')
        return dict(total=len(values),correct=correct,resolved=resolved,answered=answered,unanswered=resolved-answered,unresolved=unresolved,
                    percent_resolved=100*correct/resolved if resolved else None,conditional_accuracy=100*correct/answered if answered else None,
                    quality_valid=unresolved<=len(values)*.01)
    result=dict(identity=plan['identity'],backend=backend,complete=True,
        primary={c:metric([r for r in rows if r['seed']==42 and r['condition']==c]) for c in PRIMARY},
        pilot={str(seed):{c:metric([r for r in rows if r['seed']==seed and r['condition']==c and r['pilot']]) for c in PRIMARY+(ABLATIONS if seed==42 else ())} for seed in plan['seeds']},
        exams={e['id']:{c:metric([r for r in rows if r['exam']==e['id'] and r['seed']==42 and r['condition']==c]) for c in PRIMARY} for e in inventory if e['status']=='included'})
    write(out/(backend+'_questions.json'),rows);write(out/(backend+'_scores.json'),result)
    print('STRICT RESULTS',backend,json.dumps(result['primary']),flush=True)
    return result


def ocr_jobs(out,inventory):
    for e in inventory:
        if e['status']!='included':continue
        for c in PRIMARY+ABLATIONS:
            for path in sorted((out/'captures'/e['id']/c).glob('page-*.png')):
                yield e,c,int(path.stem.split('-')[1])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'outputs/strict_eval_v1')
    parser.add_argument('--stage',choices=['all','prepare','captures','vision','ocr_llm','summarize'],default='all')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    inventory,plan=initialize(out)
    if args.stage in ('all','prepare'):prepare(out,inventory,plan)
    if args.stage in ('all','captures'):captures(out,inventory,plan)
    if args.stage=='all':
        # OCR subprocesses use two CPU threads each and can run while the GPU
        # vision phase executes. Complete/cache OCR before text-model inference.
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(ocr_one,out,e,c,p,plan) for e,c,p in ocr_jobs(out,inventory)]
            run_backend(out,inventory,plan,'vision')
            for future in futures:future.result()
        write(out/'ocr_seal.json',{str(p.relative_to(out)):json.loads(p.read_text(encoding='utf8'))['text_sha256'] for p in sorted((out/'ocr').glob('*/*/*.json'))})
        run_backend(out,inventory,plan,'ocr_llm')
    if args.stage=='vision':run_backend(out,inventory,plan,'vision')
    if args.stage=='ocr_llm':run_backend(out,inventory,plan,'ocr_llm')
    if args.stage=='summarize':
        for backend in ('vision','ocr_llm'):summarize(out,inventory,plan,backend)
