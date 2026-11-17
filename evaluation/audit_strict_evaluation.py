"""Independent raw-answer regrade, provenance checks and paired cluster intervals.

Does not import the inference parser or the driver's summarizer. Source text,
QR URLs, IPs and captured images are deliberately excluded from public exports.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.request import urlopen

import numpy as np


def read(p):
    return json.loads(Path(p).read_text(encoding='utf8'))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def capture_keys(seal):
    return {name.replace('\\','/'):digest for name,digest in seal['captures'].items()}


def logical_cluster(exam,section,q):
    family=section.removeprefix('odd_').removeprefix('even_')
    if family in ('odd','even'):family='english'
    return 'tax-account:'+q if exam in ('exam02','exam03','exam04') and int(q)<=40 else exam+':'+family+':'+q


def request_groups(inventory):
    """Transitive shared-image/batch groups, merging duplicate question identities.

    A supplementary conservative sensitivity analysis, not a replacement for
    the preregistered duplicate-question cluster bootstrap.
    """
    parents={};pages=defaultdict(list)
    def find(x):
        parents.setdefault(x,x)
        while parents[x]!=x:
            parents[x]=parents[parents[x]];x=parents[x]
        return x
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:parents[max(a,b)]=min(a,b)
    for e in inventory:
        if e['status']!='included':continue
        for s in e['sections']:
            for batch in s['pages'].values():
                clusters=[logical_cluster(e['id'],s['id'],q) for q in batch['questions']]
                for c in clusters:find(c)
                for page in batch['context']:pages[(e['id'],page)]+=clusters
    for clusters in pages.values():
        for c in clusters[1:]:union(clusters[0],c)
    return {c:find(c) for c in sorted(parents)}


def final_answers(raw, questions):
    raw=re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip())
    value=json.loads(raw)
    if set(value.get('answers',{}))!=set(questions):raise ValueError('Wrong final question IDs')
    if set(value.get('brief_reasons',{}))!=set(questions):raise ValueError('Wrong reason IDs')
    result={}
    for q,v in value['answers'].items():
        if isinstance(v,str):
            v=v.strip()
            if len(v)==1 and v in '①②③④⑤':v='①②③④⑤'.index(v)+1
            elif v in ('1','2','3','4','5'):v=int(v)
        if v is not None and (type(v)!=int or not 1<=v<=5):raise ValueError('Invalid explicit final answer')
        result[q]=v
    return result


def metrics(rows):
    valid=[r for r in rows if r['status'] in ('ok','refused')]
    answered=[r for r in valid if r['answer'] is not None]
    correct=sum(r['correct'] for r in valid)
    bycluster=defaultdict(list)
    for r in valid:bycluster[r['cluster']].append(r['correct'])
    return dict(total=len(rows),resolved=len(valid),correct=correct,
                percent=100*correct/len(valid) if valid else None,
                answered=len(answered),conditional_accuracy=100*correct/len(answered) if answered else None,
                quality_valid=len(rows)-len(valid)<=len(rows)*.01,
                all_scheduled_accuracy_bounds_percent=[100*correct/len(rows),100*(correct+len(rows)-len(valid))/len(rows)] if rows else None,
                statuses=dict(Counter(r['status'] for r in rows)),answers=dict(Counter(str(r['answer']) for r in valid)),
                unique_clusters=len(bycluster),cluster_mean_percent=100*np.mean([np.mean(v) for v in bycluster.values()]) if bycluster else None,
                points_using_frozen_weights=sum(r['weight']*r['correct'] for r in valid),max_frozen_weight=sum(r['weight'] for r in valid),
                uniform_random_expected_percent=100*sum(len(set(r['accepted']))/5 for r in rows)/len(rows) if rows else None,
                constant_choice_correct={str(c):sum(c in r['accepted'] for r in rows) for c in range(1,6)})


def paired(rows,a,b,iterations=10000,cluster_key='cluster'):
    keyed=defaultdict(dict)
    for r in rows:
        if r['condition'] in (a,b):keyed[(r['exam'],r['section'],r['question'])][r['condition']]=r
    allpairs=[(v[a],v[b]) for v in keyed.values() if a in v and b in v]
    pairs=[(x,y) for x,y in allpairs if x['status'] in ('ok','refused') and y['status'] in ('ok','refused')]
    if not pairs:return dict(conditions=[a,b],pairs=0)
    clusters=defaultdict(list)
    for x,y in pairs:clusters[x[cluster_key]].append(y['correct']-x['correct'])
    arrays=[clusters[name] for name in sorted(clusters)];sums=np.array([sum(v) for v in arrays]);sizes=np.array([len(v) for v in arrays]);means=sums/sizes
    rng=np.random.default_rng(20261116);indices=rng.integers(len(arrays),size=(iterations,len(arrays)))
    exposure=100*sums[indices].sum(axis=1)/sizes[indices].sum(axis=1)
    macro=100*means[indices].mean(axis=1)
    lower=upper=0
    for x,y in allpairs:
        xknown=x['status'] in ('ok','refused');yknown=y['status'] in ('ok','refused')
        lower+=(y['correct'] if yknown else 0)-(x['correct'] if xknown else 1)
        upper+=(y['correct'] if yknown else 1)-(x['correct'] if xknown else 0)
    return dict(conditions=[a,b],direction='second minus first; negative means lower accuracy',pairs=len(pairs),clusters=len(arrays),cluster_unit=cluster_key,
                all_scheduled_pairs=len(allpairs),all_scheduled_delta_bounds_percentage_points=[100*lower/len(allpairs),100*upper/len(allpairs)],
                correct_to_wrong=sum(x['correct'] and not y['correct'] for x,y in pairs),
                wrong_to_correct=sum(not x['correct'] and y['correct'] for x,y in pairs),
                correct_to_unanswered=sum(x['correct'] and y['answer'] is None for x,y in pairs),
                correct_to_answered_wrong=sum(x['correct'] and not y['correct'] and y['answer'] is not None for x,y in pairs),
                unanswered_to_correct=sum(x['answer'] is None and y['correct'] for x,y in pairs),
                answered_wrong_to_correct=sum(x['answer'] is not None and not x['correct'] and y['correct'] for x,y in pairs),
                delta_percentage_points=100*sum(sums)/sum(sizes),cluster_bootstrap_95=np.quantile(exposure,[.025,.975]).tolist(),
                cluster_mean_delta_percentage_points=100*float(means.mean()),cluster_mean_bootstrap_95=np.quantile(macro,[.025,.975]).tolist(),bootstrap_iterations=iterations)


def audit(out):
    plan=read(out/'plan.json');inventory=read(out/'inventory.json');seal=read(out/'input_seal.json')
    capture_digests=capture_keys(seal)
    frozen_plan={k:v for k,v in plan.items() if k!='identity'}
    identity=hashlib.sha256(json.dumps(dict(plan=frozen_plan,keys=[e['sections'] for e in inventory if e['status']=='included']),sort_keys=True).encode()).hexdigest()
    if identity!=plan['identity'] or seal['identity']!=identity:raise ValueError('Frozen plan or answer mapping changed')
    executable=Path(os.environ.get('TESSERACT_EXE','C:/Program Files/Tesseract-OCR/tesseract.exe'))
    if sha(executable)!=plan['tesseract']['executable_sha256']:raise ValueError('OCR executable changed')
    for lang,digest in plan['tesseract']['traineddata'].items():
        if sha(executable.parent/'tessdata'/(lang+'.traineddata'))!=digest:raise ValueError('OCR language data changed')
    with urlopen('http://127.0.0.1:11434/api/tags',timeout=10) as response:models=json.load(response)['models']
    for name,expected in plan['models'].items():
        if next(m['digest'] for m in models if m['name']==name)!=expected['digest']:raise ValueError('Inference model changed')
    root=Path(__file__).resolve().parent.parent
    for name,digest in plan['implementation'].items():
        if sha(root/name)!=digest:raise ValueError('Frozen implementation changed: '+name)
    if sha(root/'docs/STRICT_EXPERIMENT_PLAN.md')!=plan['plan_document_sha256']:raise ValueError('Plan document changed')
    for relative,digest in seal['captures'].items():
        if sha(out/relative)!=digest:raise ValueError('Changed capture: '+relative)
    payload_checks=[]
    for e in inventory:
        if e['status']!='included':continue
        if sha(root/e['source'])!=e['source_sha256']:raise ValueError('Original changed')
        for c,p in e['inputs'].items():
            if sha(p)!=seal['pdfs'][e['id']][c]:raise ValueError('Changed PDF')
        manifest=Path(e['inputs']['current_choices']).with_suffix('.manifest.json');meta=read(manifest)
        if meta['payload_policy']!='current-choices' or meta['math_watermark']:raise ValueError('Wrong payload policy or generated math')
        checked=0
        for s in e['sections']:
            for page,batch in s['pages'].items():
                items=meta['pages'][int(page)-1]['source_items']
                for q in batch['questions']:
                    item=next(v for v in items if v['question']==q)
                    if not item['complete'] or sorted(c['number'] for c in item['choices'])!=[1,2,3,4,5]:raise ValueError('Incomplete copied choices')
                    for c in item['choices']:
                        if hashlib.sha256(c['text'].encode()).hexdigest()!=c['sha256']:raise ValueError('Copied choice text changed')
                    checked+=1
        if any(p['typography'].get('unrenderable') or any(r['unrenderable'] for f in p['passage_boxes'] for r in f['rendering']) for p in meta['pages']):raise ValueError('Missing rendered glyphs')
        payload_checks.append(dict(exam=e['id'],scored_questions=checked,five_choices_complete=True,choice_text_hashes_verified=True,
             manifest_sha256=sha(manifest),math_source_only=meta['math_source_only'],generated_math=False,
             outer_border_source_glyph_uses=sum(p['typography'].get('matched_glyphs',0) for p in meta['pages'])))
    groups=request_groups(inventory)
    keys={(e['id'],s['id'],q):(s,q) for e in inventory if e['status']=='included' for s in e['sections'] for q in s['answers']}
    pilot={(v['exam'],v['section'],v['question']) for v in plan['pilot']}
    public={};allrows={}
    for backend in ('vision','ocr_llm'):
        rows=[];responses=sorted((out/'responses'/backend).glob('seed-*/*/*/*.json'));usages=[]
        for path in responses:
            r=read(path)
            usages += [a['usage'] for a in r['attempts'] if a.get('usage')]
            if r['identity']!=plan['identity'] or r['input_seal_sha256']!=sha(out/'input_seal.json'):raise ValueError('Response experiment changed')
            for p,digest in zip(r['context_pages'],r['image_sha256']):
                relative=f"captures/{r['exam']}/{r['condition']}/page-{p:03}.png"
                if capture_digests[relative]!=digest:raise ValueError('Wrong inference image')
            if backend=='ocr_llm':
                for p,digest in zip(r['context_pages'],r['ocr_text_sha256']):
                    cache=read(out/'ocr'/r['exam']/r['condition']/f'{p}.json')
                    if cache['lang'] not in plan['tesseract']['languages']:raise ValueError('Wrong OCR language')
                    if cache['text_sha256']!=digest or hashlib.sha256(cache['text'].encode()).hexdigest()!=digest:raise ValueError('Changed OCR')
                    image=f"captures/{r['exam']}/{r['condition']}/page-{p:03}.png"
                    if cache['image_sha256']!=capture_digests[image]:raise ValueError('Wrong OCR source image')
            if r['status']=='ok':
                answers=final_answers(r['attempts'][-1]['raw'],r['questions'])
                if answers!=r['answers']:raise ValueError('Stored answer disagrees with raw final answer')
            else:answers={q:None for q in r['questions']}
            for q,v in answers.items():
                key=(r['exam'],r['section'],q);s,_=keys[key];accepted=s['answers'][q]
                if not isinstance(accepted,list):accepted=[accepted]
                cluster=logical_cluster(r['exam'],r['section'],q)
                rows.append(dict(exam=r['exam'],section=r['section'],question=q,cluster=cluster,seed=r['seed'],condition=r['condition'],status=r['status'],answer=v,
                                 accepted=accepted,correct=int(r['status']=='ok' and v in accepted),weight=s['weights'][q],pilot=key in pilot))
        driver=read(out/(backend+'_questions.json'))
        order=lambda r:(r['exam'],r['section'],int(r['question']),r['seed'],r['condition'])
        if [{k:v for k,v in r.items() if k!='source'} for r in sorted(driver,key=order)]!=sorted(rows,key=order):raise ValueError('Independent question regrade disagrees with driver')
        for r in rows:r['request_context_group']=groups[r['cluster']]
        primary=[r for r in rows if r['seed']==42 and r['condition'] in plan['primary']]
        for c in plan['primary']:
            if sum(r['condition']==c for r in primary)!=554:raise ValueError('Incomplete primary')
        pilot_comparisons={}
        for seed in plan['seeds']:
            subset=[r for r in rows if r['pilot'] and r['seed']==seed]
            comparisons=[('original','current_choices'),('layout_control','current_choices')]
            if seed==42:comparisons += [('other_page','current_choices'),('command_only','current_choices')]
            pilot_comparisons[str(seed)]=[paired(subset,a,b) for a,b in comparisons]
        prompt_counts=[u['prompt_eval_count'] for u in usages if u.get('prompt_eval_count') is not None]
        public[backend]=dict(response_batches=len(responses),
             inference_checks=dict(max_observed_prompt_tokens=max(prompt_counts,default=0),
                configured_context=plan['num_ctx'],near_context_limit=sum(v>=plan['num_ctx']-64 for v in prompt_counts),
                done_reasons=dict(Counter(str(u.get('done_reason')) for u in usages))),
             primary={c:metrics([r for r in primary if r['condition']==c]) for c in plan['primary']},
             primary_comparisons=[paired(primary,'original','current_choices'),paired(primary,'layout_control','current_choices')],
             supplementary_shared_context_comparisons=[paired(primary,'original','current_choices',cluster_key='request_context_group'),paired(primary,'layout_control','current_choices',cluster_key='request_context_group')],
             excluding_all_choices_accepted={c:metrics([r for r in primary if r['condition']==c and len(set(r['accepted']))<5]) for c in plan['primary']},
             exams={e:{c:metrics([r for r in primary if r['exam']==e and r['condition']==c]) for c in plan['primary']} for e in sorted({r['exam'] for r in primary})},
             pilot={str(seed):{c:metrics([r for r in rows if r['pilot'] and r['seed']==seed and r['condition']==c]) for c in plan['primary']+(plan['diagnostics'] if seed==42 else [])} for seed in plan['seeds']},
             pilot_comparisons=pilot_comparisons)
        allrows[backend]=rows
    result=dict(identity=plan['identity'],independent_regrade=True,input_hashes_verified=True,environment_hashes_verified=True,input_seal_sha256=sha(out/'input_seal.json'),capture_count=len(seal['captures']),source_payload_preflight=payload_checks,backends=public,
                commercial=plan['commercial'],warning='Previously seen corpus; low original accuracy or answer collapse limits interpretation. Capture evaluation is not a real camera or AI glasses test.')
    from strict_score_units import score_units
    result['supplementary_subject_scores']={backend:score_units(rows) for backend,rows in allrows.items()}
    result['scoring_note']='Frozen weights for English/tax are question counts. Supplementary subject scores use English printed 2/3 points, Korean/math official points and tax 100-point conversion. See docs/SCORING_CLARIFICATION.md.'
    result['supplementary_shared_context_note']='Exploratory sensitivity analysis added during execution: merge logical question clusters transitively when requests share a source context page. Does not replace the preregistered question-cluster analysis.'
    (out/'independent_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    (out/'audited_questions.json').write_text(json.dumps(allrows,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v['primary'] for k,v in public.items()},ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);audit(p.parse_args().output.resolve())
