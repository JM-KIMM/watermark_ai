"""Analyze frozen follow-up, real transfer, and the separate layout pilot."""
import hashlib
import json
import re
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from research_statistics import paired_cluster,mcnemar_exact,holm
import followup_probe as f
import layout_pilot as lp
import notice_recovery as nr
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'docs/evaluation'
REAL=ROOT/'outputs/followup_real_20261118'

def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def correct(r):return r['status']=='ok' and r['answer']==r['key']

def summarize(rs):
    ok=[r for r in rs if r['status']=='ok'];answers=[r for r in ok if r['answer'] in range(1,6)]
    return dict(n=len(rs),resolved=len(ok),correct=sum(correct(r) for r in ok),
                abstain=sum(r['answer'] is None for r in ok),invalid=sum(r['answer'] is not None and r['answer'] not in range(1,6) for r in ok),
                failed=len(rs)-len(ok),accuracy_among_valid_answers=sum(correct(r) for r in answers)/len(answers) if answers else None)

def compare(rows,before,after,identity,cluster=None):
    a={identity(r):r for r in rows if r['condition']==before};b={identity(r):r for r in rows if r['condition']==after}
    assert set(a)==set(b)
    ids=[i for i in sorted(a) if a[i]['status']==b[i]['status']=='ok']
    losses=sum(correct(a[i]) and not correct(b[i]) for i in ids);gains=sum(not correct(a[i]) and correct(b[i]) for i in ids)
    return dict(before=before,after=after,planned=len(a),losses=losses,gains=gains,mcnemar_p=mcnemar_exact(losses,gains),
                **paired_cluster([int(correct(b[i]))-int(correct(a[i])) for i in ids],[cluster(a[i]) if cluster else i for i in ids]))

def synthetic():
    assert (f.OUT/'COMPLETE.json').exists()
    paths=sorted((f.OUT/'raw').rglob('*.json'));rows=[read(p) for p in paths];assert len(rows)==740
    selection=read(f.OUT/'selection.json');chosen=selection['selected'];groups=[];comparisons=[];ocr=[]
    for split,routes,conds in [('development',('transcript','vision'),('original','neutral','arrows','prose','notice')),
                               ('holdout',('transcript','ocr','vision'),('original','neutral',chosen))]:
        for route in routes:
            for ignore in (False,True):
                rs=[r for r in rows if r['split']==split and r['route']==route and r['ignore']==ignore]
                for c in conds:groups.append(dict(split=split,route=route,ignore=ignore,condition=c,**summarize([r for r in rs if r['condition']==c])))
                if split=='holdout':comparisons.append(dict(route=route,ignore=ignore,**compare(rs,'neutral',chosen,lambda r:r['i'])))
    for c,p in zip(comparisons,holm([c['mcnemar_p'] for c in comparisons])):c['holm_p']=p
    for c in ('original','neutral',chosen):
        details=[]
        for r in rows:
            if r['route']!='ocr' or r['ignore'] or r['condition']!=c:continue
            a,b,op,_,_=f.item(r['i']);m=re.search(r'Calculate\s+(\d+)\s*([+*xX×\-])\s*(\d+)',r['input_text'])
            got=[int(m[1]),'*' if m[2] in 'xX×' else m[2],int(m[3])] if m else None
            details.append(dict(i=r['i'],expected=[a,op,b],extracted=got,exact=got==[a,op,b]))
        ocr.append(dict(condition=c,n=len(details),exact=sum(d['exact'] for d in details),details=details))
    result=dict(selection=selection,groups=groups,comparisons=comparisons,ocr_expression_audit=ocr,
                gate=all(c['n']==30 and c['mean']<=-.1 and c['holm_p']<.05 for c in comparisons),config=read(f.OUT/'config.json'),
                rows=[{k:v for k,v in r.items() if k!='attempts'} for r in rows],raw_hashes={str(p.relative_to(ROOT)):sha(p) for p in paths})
    write(PUBLIC/'followup_20261118.json',result);return result

def real():
    assert (REAL/'COMPLETE.json').exists()
    inv=read(ROOT/'outputs/external_validity/inventory.json');rows=[];groups=[];comparisons=[];clusters={}
    for e in inv:
        bs=e['batches'];parent=list(range(len(bs)))
        def find(i):
            while parent[i]!=i:i=parent[i]
            return i
        for i,b in enumerate(bs):
            for j,a in enumerate(bs[:i]):
                if set(a['context'])&set(b['context']):parent[find(i)]=find(j)
        for i,b in enumerate(bs):clusters[b['id']]=e['exam']+'-'+str(find(i))
    for route in ('ocr','vision'):
        for c in ('control','candidate','ignore'):
            for e in inv:
                for b in e['batches']:
                    r=read(REAL/'responses'/route/c/(b['id']+'.json'))
                    for q,key in b['answers'].items():rows.append(dict(route=route,condition=c,exam=e['exam'],question=q,key=key,answer=r['answers'].get(q),status=r['status'],cluster=clusters[b['id']]))
            for exam in ['all']+[e['exam'] for e in inv]:groups.append(dict(route=route,condition=c,exam=exam,**summarize([r for r in rows if r['route']==route and r['condition']==c and (exam=='all' or r['exam']==exam)])))
        rs=[r for r in rows if r['route']==route]
        for a,b in [('control','candidate'),('candidate','ignore')]:comparisons.append(dict(route=route,**compare(rs,a,b,lambda r:(r['exam'],r['question']),lambda r:r['cluster'])))
    primary=[c for c in comparisons if c['before']=='control']
    for c,p in zip(primary,holm([c['sign_flip_p'] for c in primary])):c['holm_p']=p
    paths=sorted((REAL/'responses').rglob('*.json'));assert len(paths)==126 and len(rows)==504
    result=dict(config=read(REAL/'config.json'),pixel_audit=read(REAL/'pixel_audit.json'),groups=groups,comparisons=comparisons,rows=rows,raw_hashes={str(p.relative_to(ROOT)):sha(p) for p in paths})
    write(PUBLIC/'followup_real_20261118.json',result);return result

def layout():
    assert (lp.OUT/'COMPLETE.json').exists()
    paths=sorted((lp.OUT/'raw').glob('*.json'));rows=[read(p) for p in paths];assert len(rows)==80
    groups=[];comparisons=[]
    for ignore in (False,True):
        rs=[r for r in rows if r['ignore']==ignore]
        for c in ('original','symbols','distributed','concentrated'):groups.append(dict(ignore=ignore,condition=c,**summarize([r for r in rs if r['condition']==c])))
        for c in ('original','symbols','concentrated'):comparisons.append(dict(ignore=ignore,**compare(rs,c,'distributed',lambda r:r['i'])))
    for c,p in zip(comparisons,holm([c['mcnemar_p'] for c in comparisons])):c['holm_p']=p
    result=dict(groups=groups,comparisons=comparisons,config=read(lp.OUT/'config.json'),rows=[{k:v for k,v in r.items() if k!='attempts'} for r in rows],raw_hashes={str(p.relative_to(ROOT)):sha(p) for p in paths})
    write(PUBLIC/'layout_pilot_20261118.json',result);return result

def audit(s,r,l):
    counts={};failed={}
    for out,code,protocol,keyfunc in [(f.OUT,'followup_probe.py','FOLLOWUP_PROTOCOL_2026-11-18.md',lambda i:f.item(i)[3]),
                                      (lp.OUT,'layout_pilot.py','LAYOUT_PILOT_PROTOCOL_2026-11-18.md',lambda i:lp.item(i)[2]),
                                      (REAL,'followup_real.py','FOLLOWUP_PROTOCOL_2026-11-18.md',None),
                                      (nr.OUT,'notice_recovery.py','NOTICE_RECOVERY_PROTOCOL_2026-11-18.md',lambda i:f.item(i)[3])]:
        conf=read(out/'config.json');assert conf['code_sha256']==sha(ROOT/'evaluation'/code) and conf['protocol_sha256']==sha(ROOT/'docs'/protocol)
        paths=list((out/('raw' if keyfunc else 'responses')).rglob('*.json'));counts[code]=0;failed[code]=0
        for p in paths:
            row=read(p)
            if row['status']!='ok':failed[code]+=1;continue
            raw=next(a['message']['content'] for a in reversed(row['attempts']) if 'message' in a)
            obj=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip()))
            if keyfunc:
                v=obj['answer']
                if isinstance(v,str) and v.strip().isdigit():v=int(v.strip())
                assert v==row['answer'] and row['key']==keyfunc(row['i'])
                if code=='notice_recovery.py':assert row['source_sha256']==sha(f.OUT/'raw/holdout'/f"ocr-1-{row['i']:02d}-notice.json")
                else:assert row['image_sha256']==sha(out/'images'/f"{row['i']:02d}-{row['condition']}.png")
            else:assert obj['answers']==row['answers']
            counts[code]+=1
    keys={e['exam']:e['keys'] for e in read(ROOT/'outputs/external_validity/inventory.json')}
    actual={}
    for p in (REAL/'responses').rglob('*.json'):
        raw=read(p)
        for q in raw['questions']:actual[(raw['route'],raw['condition'],raw['exam'],str(q))]=(raw['answers'].get(str(q)),raw['status'])
    for row in r['rows']:
        assert row['key']==keys[row['exam']][row['question']]
        assert (row['answer'],row['status'])==actual[(row['route'],row['condition'],row['exam'],row['question'])]
    for p in r['pixel_audit']:
        assert p['body_max_delta']==0
        for c in ('control','candidate'):assert p[c+'_sha256']==sha(REAL/'inputs'/p['exam']/f"{c}-{p['page']}.png")
    result=dict(raw_reparsed=counts,failed_batches_or_items=failed,real_keys_and_answers_checked=len(r['rows']),real_body_pages_identical=len(r['pixel_audit']),frozen_hashes_match=True)
    write(PUBLIC/'followup_audit_20261118.json',result);return result

def recovery():
    assert (nr.OUT/'COMPLETE.json').exists()
    paths=sorted((nr.OUT/'raw').glob('*.json'));rows=[read(p) for p in paths];assert len(rows)==30
    result=dict(config=read(nr.OUT/'config.json'),summary=summarize(rows),rows=[{k:v for k,v in r.items() if k!='attempts'} for r in rows],raw_hashes={str(p.relative_to(ROOT)):sha(p) for p in paths})
    write(PUBLIC/'notice_recovery_20261118.json',result);return result

def report(s,r,l,a,recovery_result):
    fig,axs=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    for ax,groups,conds,strata,n in [(axs[0],[g for g in s['groups'] if g['split']=='holdout'],('original','neutral',s['selection']['selected']),[(q,b) for q in ('transcript','ocr','vision') for b in (False,True)],30),
                                    (axs[1],[g for g in r['groups'] if g['exam']=='all'],('control','candidate','ignore'),[('ocr',None),('vision',None)],84)]:
        x=np.arange(len(strata));width=.24
        for j,c in enumerate(conds):
            vals=[next(g['correct'] for g in groups if g['route']==q and g['condition']==c and (b is None or g['ignore']==b)) for q,b in strata]
            bars=ax.bar(x+(j-1)*width,[v/n for v in vals],width,label=c,color=['#bbb','#777','#111'][j]);ax.bar_label(bars,labels=list(map(str,vals)),fontsize=7,padding=3)
        ax.set_xticks(x,[q+(' + ignore' if b else '') for q,b in strata],rotation=35,ha='right')
        ax.set(ylim=(0,1.18),ylabel='Final-answer accuracy',title=f'Labels: correct out of {n}');ax.legend(fontsize=8)
    fig.savefig(ROOT/'docs/images/followup_20261118.png',dpi=160);plt.close(fig)
    t=['# Google 워터마크 조사와 추가 방해 실험','', '2026-11-18. 성공을 전제로 하지 않은 로컬 실험. [문헌 검토](GOOGLE_WATERMARK_REVIEW_2026-11-18.md)에서 생성물 식별, PDF 파싱 교란, 시각 인코더 공격을 구분한다.', '',
       f"선정 후보: **{s['selection']['selected']}**. 사전 합성 검증 기준 통과: **{s['gate']}**. 개발 후보별 정답 수(각40응답): `{s['selection']['correct_counts']}`.", '',
       '핵심 관찰은 OCR 경로의 답안 중단이다. 새 합성 검증에서는 OCR/정확한 전사 경로가 안내문 뒤 모두 null을 출력했으나, 멀티모달은 모두 정답을 냈다. 실제 시험지의 정답 수도 감소했지만 두 경로의 주 비교 모두 다중검정 보정 기준을 통과하지 못했다. 이를 수학적 추론 능력 자체를 손상시켰다는 증거로 해석하지 않는다.', '',
       '주 실험은 새 산술40문항의 개발10/검증30, 총740응답이다. 정확한 전사 텍스트 경로는 OCR 오류를 제거한 대조이며 OCR 모델 측정값이 아니다. 실제 영어3회분84문항에서504문항 응답을 새로 수집했다. 실제 자료는 이전에 본 코퍼스로 독립 holdout이 아니다. 별도 배치 파일럿은 새10문항80응답이며 멀티모달만 평가했다. 사후 요청 변경 검사는30응답이다. 총1,354문항 응답으로, 1,354개의 독립 문제를 뜻하지 않는다.', '',
       '![최종 정답 수](images/followup_20261118.png)', '', '## 합성 검증', '',
       '| 경로 | 무시 | 조건 | 정답/전체 | null | 범위 밖 | 파싱·서버 실패 |','|---|---|---|---:|---:|---:|---:|']
    for g in s['groups']:
        if g['split']=='holdout':t.append(f"| {g['route']} | {g['ignore']} | {g['condition']} | {g['correct']}/{g['n']} | {g['abstain']} | {g['invalid']} | {g['failed']} |")
    t+=['','### 개발 조건 전체', '', '| 경로 | 무시 | 조건 | 정답/10 | null |','|---|---|---|---:|---:|']
    for g in s['groups']:
        if g['split']=='development':t.append(f"| {g['route']} | {g['ignore']} | {g['condition']} | {g['correct']}/10 | {g['abstain']} |")
    t+=['','| 경로 | 무시 | 후보−중립 %p | 95% 구간 %p | 정답 손실/회복 | Holm p |','|---|---|---:|---|---|---:|']
    for c in s['comparisons']:t.append(f"| {c['route']} | {c['ignore']} | {100*c['mean']:+.2f} | [{100*c['ci95'][0]:+.2f}, {100*c['ci95'][1]:+.2f}] | {c['losses']}/{c['gains']} | {c['holm_p']:.4f} |")
    t+=['','OCR 수식 추출 진단(일반 지시, 연산자와 두 피연산자 일치): '+', '.join(f"{d['condition']} {d['exact']}/{d['n']}" for d in s['ocr_expression_audit'])+'.', '',
        'null은 답안 중단이며 잘못된 보기를 선택한 것과 다르다. 파싱 실패는 주 비교에서 제외하고 별도 공개한다. 답을 낸 경우만의 정확도는 선택 편향이 있으므로 결과 JSON에 보조 지표로만 둔다. 검증 여섯 조합 모두 10%p 감소 및 Holm p<.05여야 사전 기준을 통과한다.', '',
        '## 실제 시험지', '', '| 경로 | 조건 | 정답/84 | null | 범위 밖 | 실패 |','|---|---|---:|---:|---:|---:|']
    for g in r['groups']:
        if g['exam']=='all':t.append(f"| {g['route']} | {g['condition']} | {g['correct']}/84 | {g['abstain']} | {g['invalid']} | {g['failed']} |")
    t+=['','| 경로 | 비교 | 변화 %p | 묶음95% 구간 %p | 손실/회복 | 주 비교 Holm p |','|---|---|---:|---|---|---|']
    for c in r['comparisons']:t.append(f"| {c['route']} | {c['before']}→{c['after']} | {100*c['mean']:+.2f} | [{100*c['ci95'][0]:+.2f}, {100*c['ci95'][1]:+.2f}] | {c['losses']}/{c['gains']} | {c.get('holm_p','보조')} |")
    t+=['','| 시험지 | 경로 | 조건 | 정답/28 | null |','|---|---|---|---:|---:|']
    for g in r['groups']:
        if g['exam']!='all':t.append(f"| {g['exam']} | {g['route']} | {g['condition']} | {g['correct']}/28 | {g['abstain']} |")
    t+=['','## 같은 보기 복제·분산 파일럿', '', '![분산 보기 복제의 합성 예시](images/layout_pilot_example_20261118.png)', '', '| 무시 | 조건 | 정답/10 | null | 실패 |','|---|---|---:|---:|---:|']
    for g in l['groups']:t.append(f"| {g['ignore']} | {g['condition']} | {g['correct']}/10 | {g['abstain']} | {g['failed']} |")
    t+=['','| 무시 | 비교 | 차이 %p | 95% 구간 %p | Holm p |','|---|---|---:|---|---:|']
    for c in l['comparisons']:t.append(f"| {c['ignore']} | {c['before']}→{c['after']} | {100*c['mean']:+.1f} | [{100*c['ci95'][0]:+.1f}, {100*c['ci95'][1]:+.1f}] | {c['holm_p']:.4f} |")
    t+=['','보기의 번호와 값을 그대로 다섯 번 복제했다. distributed와 concentrated는 문자열·글꼴·반복 횟수가 같고 위치만 다르다. symbols는 분산 위치에서 같은 문자 수의 기호를 사용한다. 본문 픽셀은 같다. 넓은 본문 위에 겹치는 워터마크나 gradient 최적화 공격의 재현은 아니다. 표본10의 음성 결과로 모든 배치가 무효라고 단정할 수 없다. 모든 관측 차이가0이면 경험적 bootstrap 구간도[0,0]이 되지만, 이는 모집단에서 효과가 없다는 증명이 아니다.','']
    g=recovery_result['summary']
    t+=['','## 요청 변경에 대한 사후 검사','',
        f"동일한 notice OCR 입력에 공개 연습문제라는 사용자 설명을 추가했을 때 정답 **{g['correct']}/30**, null **{g['abstain']}/30**, 실패 **{g['failed']}**였다. 결과를 본 뒤 추가한 검사이며 독립 검증이나 모든 우회에 대한 탐색은 아니다. 입력 문구는 수정하지 않았다. [고정 요청과 원문 해시](evaluation/notice_recovery_20261118.json).",'']
    t+=['',
        '## 재채점과 해석 제한', '', f'원문 재파싱 감사: `{a}`.', '',
        '실제 시험 본문21페이지의 추가 띠 밖 픽셀 차이를0으로 검증했다. 합성 본문 유지·정답 계산·정답 위치 균등을 단위 테스트했다. 모델별 양자화와 seed는 고정했지만 다중 seed 반복은 하지 않았다. 배치 순서는 고정이며, 문구 길이와 검은 픽셀 수까지 일치하지 않는다. 문맥을 공유하는 실제 문항은 묶음 통계로 처리했지만 시험지가 세 회분뿐이라 새 시험 전체로의 일반화는 제한된다.', '',
        'OCR 대조군 정답률 자체가 낮아 강한 시험 풀이 모델을 대표하지 못한다. 실제 주 비교는 OCR에서 감소 방향이지만 두 경로 보정 뒤 p<.05 기준에 미달한다. 보정하지 않은 bootstrap 구간과 Holm 보정 검정은 같은 판정 규칙이 아니므로, 구간이0을 제외한다는 이유로 사전 기준 통과로 바꾸지 않는다. 개발에서 선택한 안내가 전사/OCR에만 강하게 작용해도 전체 경로 통과라고 하지 않는다.', '',
        '합성은 큰 여백 문구, 실제 시험은 위·아래20pt 띠의5.5pt 문구를 사용하며 AI 검사 표시의 표현도 완전히 같지 않다. 실제 대조군은 기본 배치가 같고 추가 지시가 없는 PDF이므로 의미와 추가 문자 밀도의 효과를 완전히 분리하지 못한다. 합성→실제 총점 차이로 전이 효과의 크기를 계산하지 않는다. 실제 점수는 공식 배점 총점이 아닌 동일 가중 문항 정답 수다.', '',
        '시험 중 답안 중단 안내는 모델의 응답 행동을 바꾸는 가설이다. 실제 사람의 정답률·가독성, 상용 모델, 사진 촬영은 이번에 검사하지 않았다. 주 실험의 안내문과 배치 파일럿의 보기 복제를 혼합했을 때의 성능도 측정하지 않았다. 웹 생성기 기본값은 이번 자료만으로 바꾸지 않는다.', '',
        '## 재현 및 자료', '', '```powershell','python evaluation/followup_probe.py','python evaluation/followup_real.py','python evaluation/layout_pilot.py','python evaluation/notice_recovery.py','python evaluation/pdf_channel_probe.py','python evaluation/analyze_followup.py','python evaluation/export_research_html.py docs/FOLLOWUP_RESULTS_2026-11-18.md','```', '',
        'Windows 폰트, Tesseract, Ollama 두 모델과 기존 external_validity 입력 자료가 필요하다. 실제 시험지·원문 답변은 비공개 outputs에 남긴다. 공개 JSON에는 조건별 정오·미응답·hash가 있으며 실제 시험 지문은 없다.', '',
        '[주 계획](FOLLOWUP_PROTOCOL_2026-11-18.md) · [배치 계획](LAYOUT_PILOT_PROTOCOL_2026-11-18.md) · [합성 데이터](evaluation/followup_20261118.json) · [실제 문항별 결과](evaluation/followup_real_20261118.json) · [배치 파일럿](evaluation/layout_pilot_20261118.json) · [감사](evaluation/followup_audit_20261118.json)']
    (ROOT/'docs/FOLLOWUP_RESULTS_2026-11-18.md').write_text('\n'.join(t)+'\n',encoding='utf8')

if __name__=='__main__':
    s=synthetic();r=real();l=layout();rr=recovery();a=audit(s,r,l);report(s,r,l,a,rr)
    print('GATE',s['gate']);print('HOLDOUT',[g for g in s['groups'] if g['split']=='holdout']);print('REAL',[g for g in r['groups'] if g['exam']=='all']);print('LAYOUT',l['groups']);print('RECOVERY',rr['summary']);print('AUDIT',a)
