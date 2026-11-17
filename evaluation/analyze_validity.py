"""Reproducible analysis; incomplete studies remain explicitly pending."""
import collections
import json
import math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from research_statistics import calibration,holm,jsd,mcnemar_exact,paired_cluster
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'docs/evaluation'
IMAGES=ROOT/'docs/images'

def load(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')

def historical():
    legacy=load(PUBLIC/'korean2025_distribution.json')
    result=[]
    for cond in legacy['protocol']['conditions']:
        rows=[r[cond] for r in legacy['questions']]
        probs=[[v*r['digit_mass'] for v in r['p']]+[1-r['digit_mass']] for r in rows]
        result.append(dict(study='legacy56',condition=cond,**calibration(probs,[r['key'] for r in rows])))
    probe=load(PUBLIC/'mechanism_probe.json')
    for route in ('ocr','vision'):
        for ignore in (False,True):
            for cond in ('original','neutral','marked'):
                rows=[r for r in probe['rows'] if r['route']==route and r['ignore']==ignore and r['name'].endswith('-'+cond)]
                probs=[]
                for r in rows:
                    p=[r['p'][str(k)] for k in range(1,7)];total=sum(p)
                    if total>1:p=[v/total for v in p] # floating-point roundoff only
                    probs.append(p+[max(0,1-sum(p))])
                result.append(dict(study='synthetic20',route=route,ignore=ignore,condition=cond,**calibration(probs,[r['key'] for r in rows])))
    write(PUBLIC/'validity_calibration.json',dict(results=result,
        caveat='Residual category combines unobserved digits and non-answer tokens. Top20 digits are lower-bound estimates. This is first-token digit-event calibration, not semantic final-answer confidence.'))
    fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for ax,study in zip(axs,('legacy56','synthetic20')):
        ax.plot([0,1],[0,1],'k--',label='ideal')
        for r in result:
            if r['study']!=study or r['condition'] not in ('original','frames6','marked'):continue
            if study=='synthetic20' and (r['route']!='ocr' or r['ignore']):continue
            bins=[b for b in r['bins'] if b['n']]
            ax.plot([b['confidence'] for b in bins],[b['accuracy'] for b in bins],'o-',label=r['condition'])
        ax.set(xlim=(0,1),ylim=(0,1),xlabel='Mean confidence',ylabel='Observed digit-label accuracy',title=study);ax.legend()
    fig.savefig(IMAGES/'validity_calibration.png',dpi=170);plt.close(fig)
    return result

def measurement():
    out=ROOT/'outputs/measurement_validity'
    if not (out/'COMPLETE.json').exists():return None
    rows=[load(p) for p in sorted((out/'raw').glob('*.json'))];assert len(rows)==120
    old=load(PUBLIC/'mechanism_probe.json')['rows'];summary=[]
    for route in ('ocr','vision'):
        base=[r for r in rows if r['route']==route and r['shift']==0]
        previous=[r for r in old if r['route']==route and not r['ignore'] and r['name'].endswith('-original')]
        orig={int(r['name'].split('-')[0]):r for r in previous}
        paired=[dict(i=r['i'],previous=orig[r['i']]['top_token'].strip()==str(r['key']),current=r['answer']==r['key']) for r in base]
        order=[]
        for i in range(10):
            rr=sorted([r for r in rows if r['route']==route and r['i']==i],key=lambda r:r['shift'])
            values=[r['choices'][r['answer']-1] if r['status']=='ok' and 1<=r['answer']<=5 else None for r in rr]
            order.append(dict(i=i,correct_by_shift=[r['answer']==r['key'] for r in rr],selected_values=values,invariant=len(set(values))==1 and values[0] is not None))
        summary.append(dict(route=route,original_first_token_correct=sum(p['previous'] for p in paired),clear_final_correct=sum(p['current'] for p in paired),n=20,
            first_final_mismatch=sum(orig[r['i']]['top_token'].strip()!=str(r['answer']) for r in base),
            errors=sum(r['status']!='ok' for r in base),order_invariant=sum(r['invariant'] for r in order),order_n=10,
            order_correct_by_shift=[sum(r['correct_by_shift'][s] for r in order) for s in range(5)],order=order,
            paired=paired))
    write(PUBLIC/'measurement_validity.json',dict(summary=summary,rows=rows,
        caveat='Prompt, reasoning and output length changed together. Differences do not identify a single cause; rotation is a separate within-prompt test.'))
    fig,ax=plt.subplots(figsize=(7,4),layout='constrained')
    for r in summary:ax.plot(range(5),np.array(r['order_correct_by_shift'])/10,'o-',label=r['route'])
    ax.set(ylim=(0,1.05),xlabel='Cyclic option shift',ylabel='Accuracy (10 fixed items)',title='Option-order robustness with explicit final-answer prompt');ax.legend()
    fig.savefig(IMAGES/'validity_order.png',dpi=170);plt.close(fig)
    return summary

def external():
    out=ROOT/'outputs/external_validity'
    if not (out/'COMPLETE_v2.json').exists():return None
    inv=load(out/'inventory.json');records=[];expected=sum(len(e['batches']) for e in inv)*8
    assert len(list((out/'responses_v2').rglob('*.json')))==expected
    # Merge batches sharing context pages within each exam into dependence clusters.
    clusters={}
    for e in inv:
        batches=e['batches'];parent=list(range(len(batches)))
        def find(i):
            while parent[i]!=i:i=parent[i]
            return i
        for i,a in enumerate(batches):
            for j,b in enumerate(batches[:i]):
                if set(a['context'])&set(b['context']):parent[find(i)]=find(j)
        for i,b in enumerate(batches):clusters[b['id']]=e['exam']+'-'+str(find(i))
    for route in ('ocr','vision'):
        for cond in ('original','control','marked','ignore'):
            for e in inv:
                for b in e['batches']:
                    r=load(out/'responses_v2'/route/cond/(b['id']+'.json'))
                    for q,key in b['answers'].items():
                        answer=r['answers'].get(q)
                        records.append(dict(route=route,condition=cond,exam=e['exam'],question=q,key=key,answer=answer,status=r['status'],correct=answer==key if r['status']=='ok' else None,cluster=clusters[b['id']],batch=b['id']))
    groups=[];contrasts=[]
    for route in ('ocr','vision'):
        for cond in ('original','control','marked','ignore'):
            for exam in ['all']+[e['exam'] for e in inv]:
                rs=[r for r in records if r['route']==route and r['condition']==cond and (exam=='all' or r['exam']==exam)]
                groups.append(dict(route=route,condition=cond,exam=exam,n=len(rs),resolved=sum(r['status']=='ok' for r in rs),correct=sum(r['correct'] is True for r in rs),six=sum(r['answer']==6 for r in rs),abstain=sum(r['answer'] is None and r['status']=='ok' for r in rs),errors=sum(r['status']!='ok' for r in rs)))
        for baseline,treatment in [('control','marked'),('original','marked'),('marked','ignore')]:
            aa={(r['exam'],r['question']):r for r in records if r['route']==route and r['condition']==baseline}
            bb={(r['exam'],r['question']):r for r in records if r['route']==route and r['condition']==treatment}
            usable=[k for k in sorted(aa) if aa[k]['status']==bb[k]['status']=='ok']
            diffs=[int(bb[k]['correct'])-int(aa[k]['correct']) for k in usable]
            losses=sum(aa[k]['correct'] and not bb[k]['correct'] for k in usable);gains=sum(not aa[k]['correct'] and bb[k]['correct'] for k in usable)
            stats=paired_cluster(diffs,[aa[k]['cluster'] for k in usable])
            contrasts.append(dict(route=route,baseline=baseline,treatment=treatment,losses=losses,gains=gains,mcnemar_p=mcnemar_exact(losses,gains),**stats))
    primary=[c for c in contrasts if c['baseline']=='control']
    adjusted=holm([c['sign_flip_p'] for c in primary])
    for c,p in zip(primary,adjusted):c['holm_primary_p']=p
    result=dict(groups=groups,contrasts=contrasts,questions=records,sources=load(out/'sources.json'),pixel_audit=load(out/'pixel_audit.json'),key_audit=load(out/'key_audit.json'),run=load(out/'run_config.json'),seal=load(out/'seal.json'),amendment=load(out/'amendment.json'))
    write(PUBLIC/'external_validity.json',result)
    fig,ax=plt.subplots(figsize=(9,5),layout='constrained')
    for i,c in enumerate(contrasts):
        ax.errorbar(c['mean']*100,i,xerr=[[max(0,(c['mean']-c['ci95'][0])*100)],[max(0,(c['ci95'][1]-c['mean'])*100)]],fmt='o',color='black')
    ax.axvline(0,color='gray',linestyle='--');ax.set_yticks(range(len(contrasts)),[c['route']+': '+c['baseline']+' → '+c['treatment'] for c in contrasts]);ax.set_xlabel('Accuracy change (percentage points), cluster bootstrap 95% CI')
    fig.savefig(IMAGES/'external_validity_forest.png',dpi=170);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(9,4),layout='constrained')
    for ax,route in zip(axs,('ocr','vision')):
        a={(r['exam'],r['question']):r for r in records if r['route']==route and r['condition']=='control'}
        b={(r['exam'],r['question']):r for r in records if r['route']==route and r['condition']=='marked'}
        mat=np.zeros((2,2),int)
        for k in a:
            if a[k]['correct'] is not None and b[k]['correct'] is not None:mat[int(a[k]['correct']),int(b[k]['correct'])]+=1
        ax.imshow(mat,cmap='Greys',vmin=0,vmax=84)
        for y in range(2):
            for x in range(2):ax.text(x,y,str(mat[y,x]),ha='center',va='center',color='red',fontsize=20)
        ax.set_xticks([0,1],['Incorrect','Correct']);ax.set_yticks([0,1],['Incorrect','Correct']);ax.set(xlabel='Marked',ylabel='Layout control',title=route)
    fig.savefig(IMAGES/'external_validity_transitions.png',dpi=170);plt.close(fig)
    return result

def clear_answers():
    out=ROOT/'outputs/clear_answer_probe'
    if not (out/'COMPLETE.json').exists():return None
    rows=[load(p) for p in sorted((out/'raw').glob('*.json'))];assert len(rows)==240
    summary=[];contrasts=[]
    for route in ('ocr','vision'):
        for ignore in (False,True):
            for cond in ('original','neutral','marked'):
                rs=[r for r in rows if r['route']==route and r['ignore']==ignore and r['condition']==cond]
                summary.append(dict(route=route,ignore=ignore,condition=cond,n=len(rs),correct=sum(r['answer']==r['key'] and r['status']=='ok' for r in rs),six=sum(r['answer']==6 for r in rs),errors=sum(r['status']!='ok' for r in rs)))
            aa={r['i']:r for r in rows if r['route']==route and r['ignore']==ignore and r['condition']=='neutral'}
            bb={r['i']:r for r in rows if r['route']==route and r['ignore']==ignore and r['condition']=='marked'}
            ids=[i for i in sorted(aa) if aa[i]['status']==bb[i]['status']=='ok']
            diffs=[int(bb[i]['answer']==bb[i]['key'])-int(aa[i]['answer']==aa[i]['key']) for i in ids]
            contrasts.append(dict(route=route,ignore=ignore,comparison='marked-neutral',**paired_cluster(diffs,ids)))
    result=dict(summary=summary,contrasts=contrasts,plan=load(out/'plan.json'),rows=rows)
    write(PUBLIC/'clear_answer_probe.json',result)
    return result

if __name__=='__main__':
    print('calibration groups',len(historical()))
    print('measurement',measurement())
    c=clear_answers();print('clear answers',c['summary'] if c else 'pending')
    r=external();print('external',r['groups'] if r else 'pending')
