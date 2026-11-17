"""Analyze all candidate conditions and the fixed holdout without cherry-picking."""
import json
import hashlib
import re
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from research_statistics import mean,paired_cluster,mcnemar_exact,holm
from candidate_probe import item
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/candidate_probe_20261118'
REAL=ROOT/'outputs/candidate_real_20261118'
PUBLIC=ROOT/'docs/evaluation'

def load(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
def correct(r):return r['status']=='ok' and r['answer']==r['key']

def synthetic():
    assert (OUT/'COMPLETE.json').exists()
    rows=[load(p) for p in sorted((OUT/'raw').rglob('*.json'))];assert len(rows)==640
    selection=load(OUT/'selection.json');selected=selection['selected'];groups=[];comparisons=[]
    for split in ('development','holdout'):
        conditions=('original','neutral','six','valid','remap') if split=='development' else ('original','neutral',selected)
        for route in ('ocr','vision'):
            for ignore in (False,True):
                for condition in conditions:
                    rs=[r for r in rows if r['split']==split and r['route']==route and r['ignore']==ignore and r['condition']==condition]
                    assert len(rs)==20
                    groups.append(dict(split=split,route=route,ignore=ignore,condition=condition,n=20,resolved=sum(r['status']=='ok' for r in rs),correct=sum(correct(r) for r in rs),abstain=sum(r['status']=='ok' and r['answer'] is None for r in rs),errors=sum(r['status']!='ok' for r in rs),answer6=sum(r['answer']==6 for r in rs),other_invalid=sum(r['answer'] is not None and r['answer'] not in range(1,7) for r in rs),target_is_gold=sum(r['target']==r['key'] for r in rs) if condition=='valid' else None,target_selected=sum(r['answer']==r['target'] for r in rs) if condition=='valid' else None))
                if split=='holdout':
                    a={r['i']:r for r in rows if r['split']==split and r['route']==route and r['ignore']==ignore and r['condition']=='neutral'}
                    b={r['i']:r for r in rows if r['split']==split and r['route']==route and r['ignore']==ignore and r['condition']==selected}
                    ids=[i for i in sorted(a) if a[i]['status']==b[i]['status']=='ok']
                    loss=sum(correct(a[i]) and not correct(b[i]) for i in ids);gain=sum(not correct(a[i]) and correct(b[i]) for i in ids)
                    stats=paired_cluster([int(correct(b[i]))-int(correct(a[i])) for i in ids],ids)
                    comparisons.append(dict(route=route,ignore=ignore,losses=loss,gains=gain,mcnemar_p=mcnemar_exact(loss,gain),**stats))
    for c,p in zip(comparisons,holm([c['mcnemar_p'] for c in comparisons])):c['holm_p']=p
    eligible=all(c['n']==20 and c['mean']<=-.1 and c['holm_p']<.05 for c in comparisons)
    ocr_diagnostics=[]
    for condition in ('original','neutral',selected):
        rs=[r for r in rows if r['split']=='holdout' and r['route']=='ocr' and not r['ignore'] and r['condition']==condition]
        details=[]
        for r in rs:
            a,b,_,_,_=item(r['i'])
            extracted=re.search(r'(\d+)\s*\+\s*(\d+)',r['ocr'])
            numbers=list(map(int,extracted.groups())) if extracted else None
            details.append(dict(i=r['i'],expected=[a,b],extracted=numbers,exact=numbers==[a,b],correct=correct(r)))
        ocr_diagnostics.append(dict(condition=condition,n=len(details),operands_exact=sum(d['exact'] for d in details),details=details))
    key_strata=[]
    for route in ('ocr','vision'):
        for ignore in (False,True):
            for key in range(1,6):
                rs=[r for r in rows if r['split']=='holdout' and r['route']==route and r['ignore']==ignore and r['condition']==selected and r['key']==key]
                key_strata.append(dict(route=route,ignore=ignore,key=key,n=len(rs),correct=sum(correct(r) for r in rs),cyclic_target_selected=sum(r['answer']==key%5+1 for r in rs)))
    result=dict(selection=selection,groups=groups,comparisons=comparisons,key_strata=key_strata,ocr_operand_diagnostics=ocr_diagnostics,passes_preregistered_synthetic_gate=eligible,
        config=load(OUT/'config.json'),rows=[{k:v for k,v in r.items() if k!='attempts'} for r in rows],
        raw_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((OUT/'raw').rglob('*.json'))})
    write(PUBLIC/'candidate_probe_20261118.json',result)
    fig,axs=plt.subplots(2,2,figsize=(11,7),layout='constrained')
    for ax,(route,ignore) in zip(axs.flat,[(r,i) for r in ('ocr','vision') for i in (False,True)]):
        gs=[g for g in groups if g['split']=='development' and g['route']==route and g['ignore']==ignore]
        ax.bar([g['condition'] for g in gs],[g['correct']/20 for g in gs],color=['#bbb','#999','#777','#555','#111'])
        ax.set(ylim=(0,1.05),ylabel='Final-answer accuracy',title=f'Development: {route}, ignore={ignore}')
        for i,g in enumerate(gs):ax.text(i,g['correct']/20+.015,f"{g['correct']}/20",ha='center',fontsize=9)
    fig.savefig(ROOT/'docs/images/candidate_development_20261118.png',dpi=160);plt.close(fig)
    return result

def real():
    assert (REAL/'COMPLETE.json').exists()
    inventory=load(ROOT/'outputs/external_validity/inventory.json');records=[];groups=[];comparisons=[]
    selected=load(REAL/'config.json')['candidate'];targets=load(REAL/'targets.json')
    assert len(list((REAL/'responses').rglob('*.json')))==126
    # English common passages are contained in each saved page context here;
    # use merged context components rather than assume item independence.
    cluster={}
    for e in inventory:
        bs=e['batches'];parent=list(range(len(bs)))
        def find(i):
            while parent[i]!=i:i=parent[i]
            return i
        for i,b in enumerate(bs):
            for j,a in enumerate(bs[:i]):
                if set(a['context'])&set(b['context']):parent[find(i)]=find(j)
        for i,b in enumerate(bs):cluster[b['id']]=e['exam']+'-'+str(find(i))
    for route in ('ocr','vision'):
        for cond in ('control','candidate','ignore'):
            for e in inventory:
                for batch in e['batches']:
                    r=load(REAL/'responses'/route/cond/(batch['id']+'.json'))
                    for q,key in batch['answers'].items():
                        target=(key%5+1) if selected=='remap' else targets[e['exam']][q]
                        records.append(dict(route=route,condition=cond,exam=e['exam'],question=q,key=key,answer=r['answers'].get(q),status=r['status'],cluster=cluster[batch['id']],target=target))
            for exam in ['all']+[e['exam'] for e in inventory]:
                rs=[r for r in records if r['route']==route and r['condition']==cond and (exam=='all' or r['exam']==exam)]
                groups.append(dict(route=route,condition=cond,exam=exam,n=len(rs),resolved=sum(r['status']=='ok' for r in rs),correct=sum(correct(r) for r in rs),abstain=sum(r['status']=='ok' and r['answer'] is None for r in rs),errors=sum(r['status']!='ok' for r in rs),answer6=sum(r['answer']==6 for r in rs),other_invalid=sum(r['answer'] is not None and r['answer'] not in range(1,7) for r in rs),target_selected=sum(r['answer']==r['target'] for r in rs)))
        for before,after in [('control','candidate'),('candidate','ignore')]:
            a={(r['exam'],r['question']):r for r in records if r['route']==route and r['condition']==before}
            b={(r['exam'],r['question']):r for r in records if r['route']==route and r['condition']==after}
            ids=[i for i in sorted(a) if a[i]['status']==b[i]['status']=='ok']
            loss=sum(correct(a[i]) and not correct(b[i]) for i in ids);gain=sum(not correct(a[i]) and correct(b[i]) for i in ids)
            stats=paired_cluster([int(correct(b[i]))-int(correct(a[i])) for i in ids],[a[i]['cluster'] for i in ids])
            comparisons.append(dict(route=route,before=before,after=after,losses=loss,gains=gain,mcnemar_p=mcnemar_exact(loss,gain),**stats))
    primary=[c for c in comparisons if c['before']=='control']
    for c,p in zip(primary,holm([c['sign_flip_p'] for c in primary])):c['holm_p']=p
    result=dict(candidate=selected,groups=groups,comparisons=comparisons,rows=records,config=load(REAL/'config.json'),pixel_audit=load(REAL/'pixel_audit.json'),raw_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((REAL/'responses').rglob('*.json'))})
    write(PUBLIC/'candidate_real_20261118.json',result);return result

def report(s,r):
    fig,axs=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    for ax,result,conditions,strata,total in [
        (axs[0],s,('original','neutral',s['selection']['selected']),[(route,ignore) for route in ('ocr','vision') for ignore in (False,True)],20),
        (axs[1],r,('control','candidate','ignore'),[('ocr',None),('vision',None)],84),
    ]:
        xs=np.arange(len(strata));width=.24
        for j,condition in enumerate(conditions):
            counts=[]
            for route,ignore in strata:
                if total==20:g=next(g for g in result['groups'] if g['split']=='holdout' and g['route']==route and g['ignore']==ignore and g['condition']==condition)
                else:g=next(g for g in result['groups'] if g['exam']=='all' and g['route']==route and g['condition']==condition)
                counts.append(g['correct'])
            bars=ax.bar(xs+(j-1)*width,[n/total for n in counts],width,label=condition,color=['#bbb','#777','#111'][j])
            ax.bar_label(bars,labels=[str(n) for n in counts],fontsize=8,padding=3)
        ax.set_xticks(xs,[route+(' + ignore' if ignore else '') for route,ignore in strata],rotation=15)
        ax.set(ylim=(0,1.15),ylabel='Final-answer accuracy',title='Synthetic holdout (labels: correct / 20)' if total==20 else 'Real-exam transfer (labels: correct / 84)')
        ax.legend(fontsize=8,loc='upper right')
    fig.savefig(ROOT/'docs/images/candidate_validation_20261118.png',dpi=160);plt.close(fig)
    overview=[]
    for route in ('ocr','vision'):
        gs={g['condition']:g['correct'] for g in r['groups'] if g['exam']=='all' and g['route']==route}
        overview.append(f"{route}: 대조군 {gs['control']}/84 → 후보 {gs['candidate']}/84 → 후보+무시 {gs['ignore']}/84")
    text=['# 정답률 감소 후보의 개발·검증·실제 시험지 전이 검사','', '2026-11-18. 새 후보를 실제로 시험한 탐색 연구이며 성공을 전제하지 않았다.', '',
          '**사전 합성 검증 기준: '+('충족' if s['passes_preregistered_synthetic_gate'] else '미충족')+'**. 번호 순환은 후속 연구 가설이며 일반적인 부정행위 방지 효과가 입증됐다는 뜻이 아니다.', '',
          '; '.join(overview)+'.', '',
          '## 연구에서 추천한 후보', '',
          '유효 보기 번호 단정(valid)과 풀이 후 출력 번호 순환(remap)을 비교했다. 6번은 보기 밖이라 모델이 배제하기 쉬울 수 있고, 순환 방식은 풀이 자체보다 마지막 출력 단계에 개입한다는 가설이다. 둘 다 실제 시험 사용을 권장한다는 뜻은 아니다. 본문을 가리거나 읽기 어렵게 바꾸지 않았다.', '',
          '관련 연구: [단순 산술 PDF 주입](https://arxiv.org/abs/2508.13214), [ECCV2024 typographic 취약성 및 완화](https://arxiv.org/abs/2402.19150), [ECCV2026 Read-or-Ignore](https://arxiv.org/abs/2512.11899). 이 논문들의 공격 성공률을 우리 문항에 옮겨 쓰지 않았다.', '',
          '## 실행한 실험', '',
          '- 새 합성 40문항: 개발20 / 검증20. 개발400응답, 검증240응답. 개발 결과로 후보 하나만 고른 뒤 검증 문항을 실행했다.',
          '- 조건: original, neutral, six, valid, remap. 일반/무시 지시 × OCR+LLM/멀티모달. 명확한 보기 번호 요청·짧은 풀이·최종 JSON을 유지했다.',
          '- 실제 영어 3회분84문항: 대조군/선정후보/무시 지시를 새로 실행했다. 126요청,504문항 응답. 이미 본 시험지이므로 독립 holdout이 아닌 전이 검사다.',
          '- 유효 번호는 정답과 독립적인 ID hash, 순환 표는 모든 문항에 동일하다. 정답표는 문구 생성에 사용하지 않았다.', '',
          f"개발에서 선택한 후보: **{s['selection']['selected']}**. 선택 규칙은 네 경로/지시 조합의 정답 수가 더 낮은 후보, 동률이면 remap이었다. 합성 사전 통과 기준 충족: **{s['passes_preregistered_synthetic_gate']}**.", '',
          '![개발 결과](images/candidate_development_20261118.png)', '',
          '## 검증 집합 결과', '', '![검증 및 실제 전이](images/candidate_validation_20261118.png)', '', '| 경로 | 무시 지시 | 조건 | 정답/예정 | 확정 응답 | 오류 |', '|---|---|---|---:|---:|---:|']
    for g in s['groups']:
        if g['split']=='holdout':text.append(f"| {g['route']} | {g['ignore']} | {g['condition']} | {g['correct']}/{g['n']} | {g['resolved']} | {g['errors']} |")
    text+=['','| 경로 | 무시 지시 | 후보−중립 %p | 95% 구간 %p | 손실/회복 | Holm p |','|---|---|---:|---|---|---:|']
    for c in s['comparisons']:text.append(f"| {c['route']} | {c['ignore']} | {100*c['mean']:+.1f} | [{100*c['ci95'][0]:+.1f}, {100*c['ci95'][1]:+.1f}] | {c['losses']}/{c['gains']} | {c['holm_p']:.4f} |")
    text+=['','### OCR 오류를 명령 이행으로 오해하지 않기','',
          '사후 진단으로 OCR 텍스트에서 `숫자 + 숫자`를 추출해 실제 피연산자와 비교했다. 같은 본문 픽셀이어도 여백이 바뀌면 전체 페이지 OCR 결과가 달라졌다. 검증 문항 21의 `80 + 56의`가 중립 조건에서 `80 + 562]`로 인식됐다. 따라서 원본 대비 OCR 점수 하락 전부를 명령 주입 효과라고 할 수 없다. 이 진단은 후보 선택에 사용하지 않았다.',
          '', '| 조건 | 피연산자 둘 다 정확 / 20 |','|---|---:|']
    for d in s['ocr_operand_diagnostics']:text.append(f"| {d['condition']} | {d['operands_exact']}/20 |")
    text+=['','### 보기 위치별 사후 진단','',
          '같은 총점 감소가 다섯 보기에서 고르게 발생했는지 점검했다. 아래는 선택 후보의 멀티모달 검증 결과다. 문항별 짧은 풀이와 답이 서로 다를 수 있으므로 풀이 문장만으로 내부 추론을 단정하지 않는다.',
          '', '| 무시 지시 | 원래 정답 번호 | 정답 / 4 | 순환 표적 출력 / 4 |','|---|---:|---:|---:|']
    for k in s['key_strata']:
        if k['route']=='vision':text.append(f"| {k['ignore']} | {k['key']} | {k['correct']}/4 | {k['cyclic_target_selected']}/4 |")
    text+=['','### 유효 번호 후보가 정답을 돕는 위험','',
          '정답을 모르는 상태에서 고른 유효 번호는 우연히 정답과 같을 수 있다. 아래 개발 집합 수치를 함께 공개하며 그런 문항을 제외하지 않았다.',
          '', '| 경로 | 무시 지시 | 목표가 정답 / 20 | 목표 번호 출력 / 20 | 정답 / 20 |','|---|---|---:|---:|---:|']
    for g in s['groups']:
        if g['condition']=='valid':text.append(f"| {g['route']} | {g['ignore']} | {g['target_is_gold']} | {g['target_selected']} | {g['correct']} |")
    text+=['','## 실제 시험지 결과', '', '| 경로 | 조건 | 정답/예정 | 미응답 | 오류 | 번호6 / 기타 범위 밖 | 표적 번호 선택 |','|---|---|---:|---:|---:|---|---:|']
    for g in r['groups']:
        if g['exam']=='all':text.append(f"| {g['route']} | {g['condition']} | {g['correct']}/{g['n']} | {g['abstain']} | {g['errors']} | {g['answer6']} / {g['other_invalid']} | {g['target_selected']} |")
    text+=['','| 경로 | 비교 | 변화 %p | 묶음95% 구간 %p | 손실/회복 | Holm p(주비교) |','|---|---|---:|---|---|---|']
    for c in r['comparisons']:text.append(f"| {c['route']} | {c['before']}→{c['after']} | {100*c['mean']:+.2f} | [{100*c['ci95'][0]:+.2f}, {100*c['ci95'][1]:+.2f}] | {c['losses']}/{c['gains']} | {c.get('holm_p','보조')} |")
    text+=['','| 시험지 | 경로 | 조건 | 정답 / 28 |','|---|---|---|---:|']
    for g in r['groups']:
        if g['exam']!='all':text.append(f"| {g['exam']} | {g['route']} | {g['condition']} | {g['correct']}/28 |")
    text+=['','## 해석 제한과 결정', '',
          '합성 검증의 네 조합 모두 10%p 이상 감소하고 Holm p<.05라는 기준으로 추천 여부를 정했다. 통과하지 않은 후보를 가장 좋아 보이는 조건 하나만 골라 효과적이라고 부르지 않는다. 현재 웹 생성기의 기본값은 바꾸지 않았다.',
          '표적 번호 선택은 지시 이행의 간접 지표다. 특히 remap의 표적은 정답번호를 순환시킨 값이며, 실제 풀이에서 어떤 답을 얻은 뒤 변환했는지는 이 수치만으로 알 수 없다. 정답 손실과 회복을 함께 봐야 한다.',
          '실제 OCR 대조군에는 범위 밖 정수 16개와 null 4개가 있었다. 후보에서는 범위 밖 정수가 0개였다. 오답 유도뿐 아니라 응답 형식이 정상화되거나 원래 틀린 답이 맞아지는 변화도 함께 일어났으므로, 표적 번호 출력 증가만으로 방해 효과를 판단하지 않는다. 실제 점수는 문항당 동일 가중치이며 공식 배점 총점이 아니다.',
          '위·아래 띠 밖의 실제 시험지 본문 픽셀 차이를 검사했다. 글씨 크기·텍스트 길이·어휘·언어가 조건별로 완전히 같지 않으므로 순수 의미 효과로 단정하지 않는다. 사람 가독성, 인쇄/카메라 변환, 부분 crop, 상용 모델은 이번 검사에 포함하지 않았다. PDF의 숨은 텍스트만 바꾸는 방법은 캡처 경로에 남지 않으므로 후보에서 제외했다.',
          '이전 평가의 점수와 이번 점수를 서로 빼 효과라고 하지 않는다. 문구·배치·요청 및 실행 순서가 다르므로 같은 실행의 짝지은 대조군만 사용한다.', '',
          '합성 표본은 40개의 서로 다른 덧셈 문제이며 640개의 독립 문항이 아니다. 실제 자료도 84문항의 반복 조건이다. 공통 문맥이 겹치는 페이지는 묶어 재표집했지만 시험지는 세 회분뿐이므로 새 시험지 전체로의 일반화 불확실성은 더 크다. 조건 실행 순서는 고정이며 여러 seed 반복은 하지 않았다. bootstrap 구간과 exact 검정은 방법이 달라 경계에서 다르게 보일 수 있고, 판정은 사전에 정한 Holm 보정 검정을 따른다.', '',
          '## 재현', '', 'Windows Malgun Gothic, Tesseract kor+eng, Ollama의 qwen2.5:7b/qwen2.5vl:7b가 필요하다. 실제 전이 검사는 기존 external_validity inventory와 입력 PDF를 사용한다. 저작권 자료와 모델 원문 응답은 outputs에 보관하며 배포하지 않는다. 원 시험지 출처와 준비 방법은 [이전 보고서](RESEARCH_PAPER.md)를 따른다. 각 실행의 코드·계획·모델 digest와 원문 응답 hash는 결과 JSON에 있다.', '',
          '```powershell','python evaluation/candidate_probe.py','python evaluation/candidate_real_transfer.py','python evaluation/analyze_candidates.py','python evaluation/audit_candidates.py','python evaluation/export_research_html.py docs/CANDIDATE_RESULTS_2026-11-18.md','```', '',
          '[합성 계획](CANDIDATE_PROTOCOL_2026-11-18.md) · [실제 전이 계획](CANDIDATE_REAL_PROTOCOL_2026-11-18.md) · [합성 문항별 결과](evaluation/candidate_probe_20261118.json) · [실제 문항별 결과](evaluation/candidate_real_20261118.json) · [원문 재채점 감사](evaluation/candidate_audit_20261118.json)']
    (ROOT/'docs/CANDIDATE_RESULTS_2026-11-18.md').write_text('\n'.join(text)+'\n',encoding='utf8')

if __name__=='__main__':
    s=synthetic();r=real();report(s,r)
    print('SELECTION',s['selection'],'GATE',s['passes_preregistered_synthetic_gate'])
    print('HOLDOUT',[g for g in s['groups'] if g['split']=='holdout'])
    print('REAL',[g for g in r['groups'] if g['exam']=='all'])
