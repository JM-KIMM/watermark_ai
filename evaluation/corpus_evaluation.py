"""Evaluate every local objective exam, preserving formulas and passage context."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repository root
import argparse
import base64
import csv
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError

import pymupdf as fitz
from benchmark_local import request
from question_marks import detect_questions
from watermark import build

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'outputs/corpus_evaluation_v5'
ASSETS=ROOT/'outputs/corpus_evaluation_v4'
KEYS=ROOT/'outputs/corpus_keys'
CIRCLED={c:i+1 for i,c in enumerate('①②③④⑤')}
TAX_ACCOUNT=[4,2,3,1,5,3,2,4,1,1,1,5,1,2,2,4,3,2,4,3,4,4,5,5,1,3,2,5,4,1,3,1,1,4,5,2,3,5,4,5]
TAX_LAWS={
 '상법':[4,1,1,4,4,4,3,2,2,1,2,5,5,4,5,1,4,2,5,1,3,5,1,2,4,2,5,3,3,1,[3,4],3,2,2,5,1,3,5,4,4],
 '민법':[4,3,4,5,5,5,5,2,4,1,4,1,2,2,1,4,4,3,3,2,2,1,4,2,5,5,3,5,5,2,1,1,3,2,3,4,2,1,3,3],
 '행정소송법':[4,2,3,2,5,1,3,5,1,1,5,3,5,3,4,2,5,1,4,2,1,2,4,1,2,5,3,4,5,5,4,3,2,2,4,4,1,1,3,4],
}
ENG_ODD=[3,2,1,5,1,4,1,5,4,4,1,2,2,3,3,1,5,2,1,2,2,1,3,2,4,3,4,4,2,5,1,5,4,3,4,4,5,5,3,3,2,5,5,3,5]
ENG_EVEN=[1,2,3,5,1,4,1,5,4,4,3,2,2,1,1,3,5,2,3,1,2,2,3,2,4,3,4,4,2,5,1,5,2,3,4,4,5,5,3,1,4,5,5,3,5]


def table_key(name):
    """Extract official answer and point columns by actual table geometry."""
    result=[{} for _ in range(5)]
    with fitz.open(KEYS/f'{name}.pdf') as doc:
        rows=doc[0].find_tables().tables[0].extract()
        for row in rows[3:]:
            for col in range(0,len(row),3):
                n,a,points=row[col:col+3]
                if n and n.isdigit() and a in CIRCLED:
                    result[col//3][str(int(n))]=(CIRCLED[a],int(points))
    return result


def sections(source):
    name=source.name
    if name.startswith('2026'):
        with fitz.open(source) as d:count=len(d)
        if '1교시' in name:
            key=json.loads((ROOT/'outputs/benchmark_input/key.json').read_text(encoding='utf-8'))['answers']
        else:
            law=next(k for k in TAX_LAWS if k in name)
            key={str(i+1):v for i,v in enumerate(TAX_ACCOUNT+TAX_LAWS[law])}
        return [('all',1,count,{q:(v,1) for q,v in key.items()})]
    if name.startswith('국어'):
        result=[]
        for form,offset in [('odd',0),('even',20)]:
            cols=table_key('kor_'+form)
            result.extend([(form+'_common',offset+1,offset+12,cols[0]|cols[1]),
                           (form+'_speech',offset+13,offset+16,cols[2]),
                           (form+'_language',offset+17,offset+20,cols[3])])
        return result
    if name.startswith('수학'):
        result=[]
        for form,offset in [('odd',0),('even',20)]:
            cols=table_key('math_'+form)
            result.extend([(form+'_common',offset+1,offset+6,{q:v for q,v in (cols[0]|cols[1]).items() if int(q)<=15}),
                (form+'_probability',offset+9,offset+11,cols[2]),
                (form+'_calculus',offset+13,offset+15,cols[3]),
                (form+'_geometry',offset+17,offset+19,cols[4])])
        return result
    if name.startswith('영어'):
        return [(form,offset+2,offset+8,{str(q):(values[q-1],1) for q in range(18,46)})
                for form,offset,values in [('odd',0,ENG_ODD),('even',8,ENG_EVEN)]]
    return []


def contexts(name,section,page,qs,start,end):
    if name.startswith('국어'):
        if section.endswith('common'):
            offset=start-1
            groups=[(1,3,1,1),(4,9,2,3),(10,13,3,4),(14,17,5,6),(18,21,6,7),
                    (22,26,8,9),(27,30,9,11),(31,34,11,12)]
            return sorted({p+offset for q in qs for lo,hi,a,b in groups if lo<=int(q)<=hi for p in range(a,b+1)})
        return list(range(start,end+1))
    # Other selected questions have their complete statements/choices on the page.
    return [page]


def prepare(generate=True):
    OUT.mkdir(parents=True,exist_ok=True)
    inventory=[]
    for i,source in enumerate(sorted(ROOT.glob('*.pdf'))):
        specs=sections(source)
        item=dict(id=f'exam{i+1:02}',source=source.name,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  status='included' if specs else 'excluded_descriptive',sections=[])
        if specs:
            folder=ASSETS/item['id'];folder.mkdir(parents=True,exist_ok=True)
            with fitz.open(source) as doc:
                for section,start,end,key in specs:
                    seen=set();pages={}
                    for p in range(start,end+1):
                        qs=sorted({q['number'] for q in detect_questions(doc[p-1]) if q['number'] in key}-seen,key=int)
                        if qs:
                            pages[str(p)]=dict(questions=qs,context=contexts(source.name,section,p,qs,start,end))
                            seen.update(qs)
                    if seen!=set(key):raise ValueError(f'Incomplete mapping: {source.name}/{section}: {set(key)-seen}')
                    item['sections'].append(dict(id=section,pages=pages,answers={q:v[0] for q,v in key.items()},weights={q:v[1] for q,v in key.items()}))
            for level in ((2,3) if generate else ()):
                target=folder/f'level{level}.pdf'
                if not target.exists():
                    print('GENERATE',item['id'],source.name,level,flush=True)
                    build(source,target,intensity=level,font_mode='source',size_jitter=.25,prompts_file=ROOT/'prompts_ko.json',math_watermark=False,qr_captions=False)
            # Detect genuinely identical variants before treating them as separate evidence.
            item['identical_stage_pages']=[]
            if (folder/'level3.manifest.json').exists():
                with fitz.open(folder/'level2.pdf') as a,fitz.open(folder/'level3.pdf') as b:
                    item['identical_stage_pages']=[p+1 for p in range(len(a)) if a[p].get_pixmap(dpi=150).tobytes('png')==b[p].get_pixmap(dpi=150).tobytes('png')]
        inventory.append(item)
    (OUT/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
    return inventory


def run(inventory):
    model=request('http://127.0.0.1:11434/api/tags')['models']
    model=next(m for m in model if m['name']=='qwen2.5vl:3b')
    (OUT/'protocol.json').write_text(json.dumps(dict(version=5,model=model,dpi=150,seed=42,temperature=0,num_ctx=16384,
        input='PDF images; Korean shared-passage context explicitly grouped; self-contained tax/math/English questions use current page',identical_image_policy='Reuse level2 response for byte-identical level3 context; not an independent trial',font_mode='source',exclude='descriptive, math short-answer, English listening 1-17'),ensure_ascii=False,indent=2),encoding='utf-8')
    for exam in inventory:
        if exam['status']!='included':continue
        folder=OUT/exam['id'];folder.mkdir(exist_ok=True);source=ROOT/exam['source'];assets=ASSETS/exam['id']
        docs={'original':fitz.open(source),'level2':fitz.open(assets/'level2.pdf'),'level3':fitz.open(assets/'level3.pdf')}
        try:
            for section in exam['sections']:
                dest=folder/section['id'];dest.mkdir(exist_ok=True)
                for page,batch in section['pages'].items():
                    qs=batch['questions'];ctx=batch['context']
                    for condition in ('original','level2','level3'):
                        cache=dest/f'{condition}-{page}.json'
                        if condition=='level3' and all(p in exam['identical_stage_pages'] for p in ctx):
                            # Avoid interpreting backend variability as an effect between identical inputs.
                            record=json.loads((dest/f'level2-{page}.json').read_text(encoding='utf-8'))
                            if cache.exists() and 'reused_from' not in json.loads(cache.read_text(encoding='utf-8')):
                                backup=cache.with_suffix('.repeat.json')
                                if not backup.exists():backup.write_bytes(cache.read_bytes())
                            record.update(condition='level3',reused_from=f'level2-{page}.json',seconds=0,eval_count=0)
                            cache.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                            continue
                        if cache.exists():continue
                        imgs=[base64.b64encode(docs[condition][p-1].get_pixmap(dpi=150).tobytes('png')).decode() for p in ctx]
                        prompt=('Solve the multiple-choice exam. Images show consecutive relevant pages in ascending page order. '
                            'Read formulas, diagrams and passages from the images. '
                            'Return only the choice number 1-5 for each requested question: '+', '.join(qs)+'.')
                        schema=dict(type='object',properties={q:dict(type='integer',enum=[1,2,3,4,5]) for q in qs},required=qs,additionalProperties=False)
                        begin=time.monotonic()
                        output_error=None
                        for attempt in range(3):
                            encoding='string-enum-fallback' if attempt==2 else 'integer-enum'
                            active_schema=schema if attempt<2 else dict(type='object',properties={q:dict(type='string',enum=['1','2','3','4','5']) for q in qs},required=qs,additionalProperties=False)
                            try:
                                response=request('http://127.0.0.1:11434/api/chat',dict(model=model['name'],stream=False,format=active_schema,
                                    messages=[dict(role='user',content=prompt,images=imgs)],options=dict(seed=42,temperature=0,num_ctx=16384,num_predict=1024)),timeout=900)
                            except HTTPError as exc:
                                if exc.code!=500:raise
                                response=dict(error=exc.read().decode('utf-8',errors='replace'),http_status=500,message=dict(content=''))
                            raw=response.get('message',{}).get('content','')
                            try:
                                parsed=json.loads(raw)
                                if set(parsed)!=set(qs) or any((type(v) is not int and not isinstance(v,str)) or str(v) not in ('1','2','3','4','5') for v in parsed.values()):raise ValueError('Invalid answer schema')
                                parsed={q:int(v) for q,v in parsed.items()}
                                break
                            except (ValueError,TypeError,AttributeError):
                                (dest/f'{condition}-{page}.attempt-{attempt}.failed.json').write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding='utf-8')
                                if attempt==2:
                                    parsed={q:None for q in qs};output_error='inference-failure-no-valid-response'
                                    break
                                # Reset a backend grammar/cache failure; preserve model/prompt/options.
                                request('http://127.0.0.1:11434/api/generate',dict(model=model['name'],keep_alive=0),timeout=60)
                        record=dict(page=page,condition=condition,questions=qs,context_pages=ctx,answers=parsed,raw=raw,seconds=time.monotonic()-begin,
                                    format_encoding=encoding,
                                    error=output_error,
                                    image_sha256=[hashlib.sha256(base64.b64decode(v)).hexdigest() for v in imgs],eval_count=response.get('eval_count'),done_reason=response.get('done_reason'))
                        cache.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                        print('DONE',exam['id'],section['id'],page,condition,parsed,flush=True)
        finally:
            for doc in docs.values():doc.close()
    summarize(inventory)


def summarize(inventory):
    rows=[];summary=[]
    for exam in inventory:
        if exam['status']!='included':continue
        for section in exam['sections']:
            answers={c:{} for c in ('original','level2','level3')}
            for page in section['pages']:
                for c in answers:
                    path=OUT/exam['id']/section['id']/f'{c}-{page}.json'
                    if not path.exists():raise ValueError('Cannot summarize an unfinished experiment')
                    answers[c].update(json.loads(path.read_text(encoding='utf-8'))['answers'])
            for q,expected in section['answers'].items():
                accepted=expected if isinstance(expected,list) else [expected]
                row=dict(exam=exam['source'],section=section['id'],question=q,accepted='/'.join(map(str,accepted)),weight=section['weights'][q])
                for c in answers:
                    row[c]=answers[c][q];row[c+'_correct']=int(answers[c][q] in accepted)
                    row[c+'_status']='inference_failure' if answers[c][q] is None else 'answered'
                rows.append(row)
        subset=[r for r in rows if r['exam']==exam['source']]
        result=dict(exam=exam['source'],total=len(subset),identical_stage_pages=len(exam['identical_stage_pages']))
        for c in answers:
            correct=sum(r[c+'_correct'] for r in subset);points=sum(r[c+'_correct']*r['weight'] for r in subset);maximum=sum(r['weight'] for r in subset)
            answered=sum(r[c] is not None for r in subset)
            result[c]=dict(correct=correct,accuracy=100*correct/len(subset),answered=answered,inference_failures=len(subset)-answered,
                           valid_response_accuracy=100*correct/answered if answered else None,points=points,max_points=maximum)
        summary.append(result)
    with (OUT/'questions.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (OUT/'scores.json').write_text(json.dumps(dict(exams=summary,total_exposures=len(rows),totals={c:sum(r[c+'_correct'] for r in rows) for c in ('original','level2','level3')}),ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'questions.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print('COMPLETE',len(rows),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--pipeline',action='store_true');p.add_argument('--summarize',action='store_true');args=p.parse_args()
    inventory=prepare(generate=not args.pipeline) if args.prepare or args.pipeline or not (OUT/'inventory.json').exists() else json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))
    if args.pipeline:
        for exam in inventory:
            if exam['status']!='included':continue
            while not (ASSETS/exam['id']/'level3.manifest.json').exists():time.sleep(5)
            with fitz.open(ASSETS/exam['id']/'level2.pdf') as a,fitz.open(ASSETS/exam['id']/'level3.pdf') as b:
                exam['identical_stage_pages']=[p+1 for p in range(len(a)) if a[p].get_pixmap(dpi=150).tobytes('png')==b[p].get_pixmap(dpi=150).tobytes('png')]
            run([exam])
        (OUT/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
        summarize(inventory)
    elif args.summarize:summarize(inventory)
    elif not args.prepare:run(inventory)
