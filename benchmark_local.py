"""Paired, resumable local Ollama vision evaluation. No answers sent to model."""
import argparse
import base64
import hashlib
import json
import math
import random
from pathlib import Path
import time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

import pymupdf as fitz


def request(endpoint, payload=None, timeout=600):
    if urlsplit(endpoint).hostname not in ('127.0.0.1','localhost','::1'):
        raise ValueError('Only local inference endpoints are allowed')
    data=None if payload is None else json.dumps(payload).encode()
    with urlopen(Request(endpoint,data=data,headers={'Content-Type':'application/json'}),timeout=timeout) as r:
        return json.load(r)


def grade(answers, key):
    correct=sum(str(answers.get(q,'')) in [str(v) for v in (a if isinstance(a,list) else [a])] for q,a in key.items())
    return dict(correct=correct,total=len(key),answered=sum(str(answers.get(q,'')) in ('1','2','3','4','5') for q in key),score=100*correct/len(key))


def validate_choice_key(key):
    """Reject descriptive/misaligned datasets instead of silently scoring them."""
    if key.get('question_type','multiple_choice') != 'multiple_choice':
        raise ValueError('Only multiple-choice exams can be scored by this evaluator')
    ids=[q for questions in key['pages'].values() for q in questions]
    if not ids or len(ids)!=len(set(ids)) or set(ids)!=set(key['answers']):
        raise ValueError('Answer key must cover each question exactly once')
    for answer in key['answers'].values():
        values=answer if isinstance(answer,list) else [answer]
        if not values or any(type(v) is not int or v not in range(1,6) for v in values):
            raise ValueError('Expected accepted multiple-choice answers 1 through 5')


def paired_stats(results, key):
    def correct(condition,q):
        expected=key[q] if isinstance(key[q],list) else [key[q]]
        return str(results[condition].get(q,'')) in list(map(str,expected))
    changes=[int(correct('watermarked',q))-int(correct('original',q)) for q in key]
    lost=changes.count(-1);gained=changes.count(1);discordant=lost+gained
    p=min(1.,2*sum(math.comb(discordant,k) for k in range(min(lost,gained)+1))/2**discordant) if discordant else 1.
    rng=random.Random(42)
    samples=sorted(100*sum(rng.choices(changes,k=len(changes)))/len(changes) for _ in range(10000))
    return dict(original_correct_marked_wrong=lost,original_wrong_marked_correct=gained,
                mcnemar_exact_two_sided_p=p,paired_bootstrap_95_percent_interval=[samples[250],samples[9749]])


def run(args):
    key=json.loads(args.key.read_text(encoding='utf-8'))
    validate_choice_key(key)
    pages=key['pages']
    if args.limit:
        pages=dict(list(pages.items())[:args.limit])
    args.output.mkdir(parents=True,exist_ok=True)
    models=request(args.endpoint+'/api/tags',timeout=10)
    model=next((m for m in models['models'] if m['name']==args.model),None)
    if model is None: raise ValueError('Requested local model is not installed')
    metadata=dict(protocol='choice-schema-v2',model=model,seed=args.seed,dpi=args.dpi,num_ctx=8192,num_predict=2048,temperature=0,
                  source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
                  marked_sha256=hashlib.sha256(args.marked.read_bytes()).hexdigest(),
                  key_sha256=hashlib.sha256(args.key.read_bytes()).hexdigest(),pages=pages)
    identity=hashlib.sha256(json.dumps(metadata,sort_keys=True).encode()).hexdigest()
    manifest=args.output/'experiment.json'
    if manifest.exists() and json.loads(manifest.read_text())['identity']!=identity:
        raise ValueError('Experiment settings changed; use a new output folder')
    manifest.write_text(json.dumps(dict(identity=identity,**metadata),ensure_ascii=False,indent=2),encoding='utf-8')
    results={condition:{} for condition in ('original','watermarked')}
    elapsed={condition:0. for condition in results}
    with fitz.open(args.source) as original,fitz.open(args.marked) as marked:
        if len(original)!=len(marked): raise ValueError('Page counts differ')
        for page_index,(page,questions) in enumerate(pages.items()):
            # Alternate ordering to reduce cold-start/order effects.
            conditions=('original','watermarked') if page_index%2==0 else ('watermarked','original')
            for condition in conditions:
                cache=args.output/f'{condition}-{page}.json'
                if cache.exists(): record=json.loads(cache.read_text(encoding='utf-8'))
                else:
                    doc=original if condition=='original' else marked
                    image=doc[int(page)-1].get_pixmap(dpi=args.dpi).tobytes('png')
                    prompt=('Solve the multiple choice exam questions in this image. '
                            'Return only a JSON object mapping question numbers to choice numbers 1 to 5. '
                            'Answer these question numbers: '+', '.join(questions)+'. Do not omit any.')
                    start=time.monotonic()
                    schema=dict(type='object',properties={q:dict(type='integer',enum=[1,2,3,4,5]) for q in questions},
                                required=questions,additionalProperties=False)
                    response=request(args.endpoint+'/api/chat',dict(model=args.model,stream=False,format=schema,
                        messages=[dict(role='user',content=prompt,images=[base64.b64encode(image).decode()])],
                        options=dict(temperature=0,seed=args.seed,num_ctx=8192,num_predict=2048)))
                    raw=response['message']['content']
                    try:
                        parsed=json.loads(raw)
                        answers={str(q):str(v) for q,v in parsed.items() if str(q) in questions and str(v) in ('1','2','3','4','5')}
                        error=None
                    except (ValueError,AttributeError): answers={};error='invalid-answer-json'
                    record=dict(condition=condition,page=page,answers=answers,raw=raw,error=error,
                                seconds=time.monotonic()-start,eval_count=response.get('eval_count'),
                                done_reason=response.get('done_reason'))
                    cache.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                results[condition].update(record['answers'])
                elapsed[condition]+=record['seconds']
                print(condition,page,record['answers'],flush=True)
    selected={q:key['answers'][q] for questions in pages.values() for q in questions}
    scores={c:grade(a,selected) for c,a in results.items()}
    report=dict(model=args.model,identity=identity,scores=scores,
        paired=paired_stats(results,selected),seconds=elapsed,
        subjects={name:{c:grade(a,{q:v for q,v in selected.items() if low<=int(q)<=high}) for c,a in results.items()}
                  for name,low,high in [('public_finance',1,40),('tax_law',41,80)]
                  if any(low<=int(q)<=high for q in selected)},
        change_percentage_points=scores['watermarked']['score']-scores['original']['score'],
        note='Same-page paired evaluation; omissions/invalid answers count as incorrect. Not proof of general effectiveness.')
    (args.output/'scores.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True);p.add_argument('--marked',type=Path,required=True)
    p.add_argument('--key',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model',required=True);p.add_argument('--endpoint',default='http://127.0.0.1:11434')
    p.add_argument('--seed',type=int,default=42);p.add_argument('--dpi',type=int,default=150)
    p.add_argument('--limit',type=int,default=0)
    run(p.parse_args())
