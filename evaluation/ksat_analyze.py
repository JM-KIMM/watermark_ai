"""Official-key scoring, benchmark-policy sensitivity, and paired KSAT analysis."""
import json
import re
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from ksat_paired import ROOT,OUT,UP,load,sha,CONDITIONS
from research_statistics import paired_cluster,mcnemar_exact,holm
PUBLIC=ROOT/'docs/evaluation'

def correct(r,benchmark=False):
    accepted=[4,5] if benchmark and r['id']=='2026-english-english-q37' else [r['key']]
    return r['status']=='ok' and r['answer'] in accepted

def summary(rows,benchmark=False):
    return dict(n=len(rows),resolved=sum(r['status']=='ok' for r in rows),correct=sum(correct(r,benchmark) for r in rows),
                score=sum(r['points'] for r in rows if correct(r,benchmark)),max_score=sum(r['points'] for r in rows),
                abstain=sum(r['status']=='ok' and r['answer'] is None for r in rows),invalid=sum(r['status']=='ok' and r['answer'] is not None and r['answer'] not in range(1,6) for r in rows),six=sum(r['status']=='ok' and r['answer']==6 for r in rows),failed=sum(r['status']!='ok' for r in rows))

def main():
    assert (OUT/'COMPLETE.json').exists()
    provenance=load(OUT/'provenance.json');batches=load(OUT/'batches.json');rows=[];groups=[];exams=[];comparisons=[]
    parent=list(range(len(batches)))
    def find(i):
        while parent[i]!=i:i=parent[i]
        return i
    for i,b in enumerate(batches):
        for j,a in enumerate(batches[:i]):
            if a['subject']==b['subject'] and set(a['context'])&set(b['context']):parent[find(i)]=find(j)
    clusters={b['id']:str(find(i)) for i,b in enumerate(batches)}
    rawpaths=[];rawchecked=0;failures=0;inference_stats=[]
    for route in ('ocr','vision'):
        for c in CONDITIONS:
            for b in batches:
                path=OUT/'responses'/route/c/(b['id']+'.json');rawpaths.append(path);r=load(path)
                if r['status']=='ok':
                    raw=next(a['message']['content'] for a in reversed(r['attempts']) if 'message' in a)
                    assert json.loads(raw)['answers']==r['answers'];rawchecked+=1
                    last=next(a for a in reversed(r['attempts']) if 'message' in a)
                    inference_stats.append(dict(route=route,condition=c,batch=b['id'],prompt_tokens=last.get('prompt_eval_count'),output_tokens=last.get('eval_count'),done_reason=last.get('done_reason')))
                else:failures+=1
                for q in b['questions']:rows.append(dict(route=route,condition=c,id=q['id'],subject=q['subject'],section=q['section'],number=q['number'],points=q['points'],key=q['correct_answer'],answer=r['answers'].get(str(q['number'])),status=r['status'],cluster=clusters[b['id']]))
            for subject in ('all','korean','math','english'):
                rs=[r for r in rows if r['route']==route and r['condition']==c and (subject=='all' or r['subject']==subject)]
                groups.append(dict(route=route,condition=c,subject=subject,official=summary(rs),benchmark=summary(rs,True)))
            for exam in provenance['exams']:
                rs=[r for r in rows if r['route']==route and r['condition']==c and r['id'] in exam['question_ids']]
                exams.append(dict(route=route,condition=c,exam=exam['id'],title=exam['title'],official=summary(rs),benchmark=summary(rs,True)))
        for before,after in [('original','product'),('control','product'),('control','notice')]:
            a={r['id']:r for r in rows if r['route']==route and r['condition']==before};b={r['id']:r for r in rows if r['route']==route and r['condition']==after}
            ids=[i for i in a if a[i]['status']==b[i]['status']=='ok'];loss=sum(correct(a[i]) and not correct(b[i]) for i in ids);gain=sum(not correct(a[i]) and correct(b[i]) for i in ids)
            stats=paired_cluster([int(correct(b[i]))-int(correct(a[i])) for i in ids],[a[i]['cluster'] for i in ids])
            comparisons.append(dict(route=route,before=before,after=after,losses=loss,gains=gain,mcnemar_p=mcnemar_exact(loss,gain),**stats))
    primary=[c for c in comparisons if c['before']=='control' and c['after']=='product']
    for c,p in zip(primary,holm([c['sign_flip_p'] for c in primary])):c['holm_p']=p
    assert len(rows)==936 and len({r['id'] for r in rows})==117
    keys={q['id']:q for q in load(OUT/'key_audit.json')}
    for r in rows:assert (r['key'],r['points'])==(keys[r['id']]['answer'],keys[r['id']]['points'])
    conf=load(OUT/'config.json');assert conf['code_sha256']==sha(ROOT/'evaluation/ksat_paired.py') and conf['protocol_sha256']==sha(ROOT/'docs/KSAT_PROTOCOL_2026-11-18.md')
    assert conf['input_manifest_sha256']==sha(OUT/'inputs.json') and conf['batches_sha256']==sha(OUT/'batches.json')
    for name,digest in conf['dependency_hashes'].items():assert sha(ROOT/name)==digest
    checked=0
    for subject in load(OUT/'inputs.json').values():
        for condition in subject.values():
            for p in condition.values():
                for k in ('image','text'):assert sha(ROOT/p[k])==p[k+'_sha256'];checked+=1
    pixels=load(OUT/'pixel_audit.json');assert all(p['body_max_delta']==0 for p in pixels)
    result=dict(source=dict(url='https://github.com/roboco-io/KSAT-AI-Benchmark',commit=provenance['upstream_commit'],dataset_sha256=provenance['dataset_sha256'],metadata_license='CC BY-NC 4.0 applies to derived question IDs, official keys and points; upstream PDFs/full datasets are not redistributed here'),config=conf,groups=groups,exams=exams,comparisons=comparisons,rows=rows,pixel_audit=pixels,
                audit=dict(raw_batches_reparsed=rawchecked,failed_batches=failures,item_answers_checked=len(rows),pdf_key_entries_verified=len(keys),input_files_hashed=checked,frozen_hashes_match=True),inference_stats=inference_stats,raw_hashes={str(p.relative_to(ROOT)):sha(p) for p in rawpaths})
    if (OUT/'environment.json').exists():result['environment']=load(OUT/'environment.json')
    (PUBLIC/'ksat_paired_20261118.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    fig,axs=plt.subplots(1,2,figsize=(12,4.6),layout='constrained')
    for ax,route in zip(axs,('ocr','vision')):
        for j,c in enumerate(CONDITIONS):
            gs=[next(g['official'] for g in groups if g['route']==route and g['condition']==c and g['subject']==s) for s in ('korean','math','english')]
            bars=ax.bar(np.arange(3)+(j-1.5)*.2,[g['correct']/g['n'] for g in gs],.2,label=c,color=['#ddd','#aaa','#333','#777'][j]);ax.bar_label(bars,labels=[str(g['correct']) for g in gs],fontsize=8,padding=3)
        ax.set_xticks(range(3),['Korean (56)','Math MC (33)','English reading (28)']);ax.set(ylim=(0,1.05),ylabel='Official-key accuracy',title=route+' — labels are correct counts');ax.legend(fontsize=8)
    fig.savefig(ROOT/'docs/images/ksat_paired_20261118.png',dpi=160);plt.close(fig)
    t=['# 공개 수능 벤치마크: 원본과 우리 시험지 비교','', '2026-11-18. 2026학년도 수능 홀수형(2025-11-13 시행)을 기존 로컬 두 모델로 새로 풀게 한 결과다.', '',
       '[KSAT AI Benchmark](https://github.com/roboco-io/KSAT-AI-Benchmark)의 공개 문항·공식 배점을 사용했다. upstream commit: `'+provenance['upstream_commit']+'`. 원 자료 라이선스는 CC BY-NC 4.0이며, 원본 시험지는 재배포하지 않는다. upstream 코드를 복제하지 않고 독립 평가기를 작성했다.', '',
       '전체147개 중 영어 듣기17, 수학 단답형13을 제외한117개 고유 객관식 문항 전부를 평가했다. 국어56/수학33/영어28이며 공통 문항은 전체 집계에서 한 번만 센다. 같은 모델·요청·문항의 네 조건을 비교한936문항 응답이다. 통계적 독립 표본936개라는 뜻은 아니다.', '',
       '- original: 원본 홀수형.', '- control: QR 자리와 바깥 띠만 만든 배치 대조군.', '- product: 현재 웹 생성기의 기본 워터마크·문항 QR·지문 프레임 처리.', '- notice: 배치 대조군에 답안 중단 안내만 넣은 별도 실험용 후보. 제품 기본값이 아니다.', '',
       '![과목별 정답 수](images/ksat_paired_20261118.png)', '', '## 공식 정답 기준', '', '| 모델 경로 | 과목 | 조건 | 정답/문항 | 배점 점수/평가 만점 | null | 범위 밖 | 실패 |','|---|---|---|---:|---:|---:|---:|---:|']
    for g in groups:
        z=g['official'];t.append(f"| {g['route']} | {g['subject']} | {g['condition']} | {z['correct']}/{z['n']} | {z['score']}/{z['max_score']} | {z['abstain']} | {z['invalid']} | {z['failed']} |")
    t+=['','전체291점은 모든 선택과목의 고유 문항을 합친 연구용 분모다. 실제 수험자의 한 시험 총점으로 해석하지 않는다. null·범위 밖은 비정답, 실행·형식 실패는 별도 공개하며 통계의 complete-case 쌍에서는 제외한다.', '',
        '## 선택과목별 점수', '', '| 경로 | 선택 조합 | 조건 | 정답/문항 | 공식 배점 점수/평가 만점 |','|---|---|---|---:|---:|']
    for e in exams:
        z=e['official'];t.append(f"| {e['route']} | {e['title']} | {e['condition']} | {z['correct']}/{z['n']} | {z['score']}/{z['max_score']} |")
    t+=['','국어는45문항100점, 수학은객관식21문항68점, 영어는독해28문항63점이다. 제외 문항을0점으로 넣거나100점으로 환산하지 않았다. 선택 조합별 표에는 공통 문항이 반복되므로 표의 행들을 합산하면 안 된다.', '',
        '## 짝지은 비교', '', '| 경로 | 비교 | 정답률 변화 %p | 문맥 묶음95% 구간 %p | 손실/회복 | 주 비교 Holm p |','|---|---|---:|---|---|---|']
    for c in comparisons:t.append(f"| {c['route']} | {c['before']}→{c['after']} | {100*c['mean']:+.2f} | [{100*c['ci95'][0]:+.2f}, {100*c['ci95'][1]:+.2f}] | {c['losses']}/{c['gains']} | {c.get('holm_p','보조')} |")
    t+=['','## 벤치마크 채점 정책 민감도', '', '공식 정답표에서 영어37은⑤다. upstream 운영 정책은④도 추가 인정한다. 이는 공식 복수정답 변경이 아니다. 두 정책을 섞지 않고 영어 점수를 나란히 공개한다.', '',
        '| 경로 | 조건 | 공식 점수/63 | upstream 추가 인정 점수/63 |','|---|---|---:|---:|']
    for g in groups:
        if g['subject']=='english':t.append(f"| {g['route']} | {g['condition']} | {g['official']['score']}/63 | {g['benchmark']['score']}/63 |")
    t+=['','## 검증과 한계', '', f"원문/입력 감사: `{result['audit']}`.", '',
        '공식 PDF 정답표에서 번호·원형 숫자·배점을 별도 추출하여 객관식134문항의 메타데이터를 검증한 후 듣기17개를 제외했다. 국어·수학 선택과목의 반복 번호는 고유 ID로 분리했다. 정답표·배점·정답 메타데이터는 모델 입력에 넣지 않았다.', '',
        '모델은 Qwen2.5 7B와 Qwen2.5-VL 7B다. OCR은 같은 렌더링에 Tesseract kor+eng PSM3을 적용했다. 수학 수식·도형은 이미지에 보존했지만 OCR 모델이 이를 정확하게 전사한다는 뜻은 아니다. 두 경로는 모델 자체도 다르므로 경로 간 차이를 OCR 하나의 인과 효과로 해석하지 않는다.', '',
        '200dpi 렌더링 이미지이며 실제 카메라 촬영이 아니다. 로컬 문맥 길이 때문에 과목 전체 대신 페이지 묶음으로 평가했다. 국어·영어는 인접 페이지를 포함하고 공유 문맥의 연결 성분을 묶어 통계 처리했다. upstream 리더보드와 모델·프롬프트·입력 묶음·제외 문항이 다르므로 공식 리더보드 재현이나 상용 모델 성능이라고 부르지 않는다.', '',
        '수식·도형 원본과 표시 영역 밖 픽셀을 보존했지만 선언된 프레임 안의 사람 가독성·부분 crop·상용 모델·다중seed는 검증하지 않았다. 한 회차의 자료이고 학습 오염이 완전히 없음을 보장하지 않는다. notice의 낮은 점수를 product의 성능으로 바꿔 쓰지 않는다.', '',
        '## 재현', '', 'upstream 저장소를 outputs/upstream_ksat에 해당 commit으로 준비한 뒤:', '', '```powershell','python evaluation/ksat_paired.py','python evaluation/ksat_analyze.py','python evaluation/export_research_html.py docs/KSAT_RESULTS_2026-11-18.md','```', '',
        '[실험 계획](KSAT_PROTOCOL_2026-11-18.md) · [문항별 결과·설정·해시](evaluation/ksat_paired_20261118.json)']
    overview=['## 원본과 현재 제품', '', '| 경로 | 원본 정답/117 | 제품 정답/117 | 정답률 변화 | 원본/제품의 6번 응답 |', '|---|---:|---:|---:|---:|']
    for route in ('ocr','vision'):
        zs={g['condition']:g['official'] for g in groups if g['route']==route and g['subject']=='all'}
        a,b=zs['original'],zs['product']
        overview.append(f"| {route} | {a['correct']} | {b['correct']} | {100*(b['correct']-a['correct'])/117:+.2f}%p | {a['six']}/{b['six']} |")
    overview+=['', '아래 선택과목별 표가 실제 배점 비교다. 117문항 합계는 모든 선택과목을 합친 연구용 정답 수이며 한 수험생의 응시 조합이 아니다. 원본 성능이 낮은 7B 모델이므로, 감소가 있더라도 고성능 상용 AI에 대한 효과로 일반화할 수 없다. 균등한 5지선다 무작위 선택의 기대 정답률은20%다. 범위 밖 숫자는 요청한 보기 번호로 해석할 수 없으므로 그대로 비정답 처리하며, 정답 계산값을 임의로 보기 번호로 변환하지 않았다.', '']
    for c in primary:
        overview.append(f"배치 대조군→제품의 {c['route']} 정답률 변화는 {100*c['mean']:+.2f}%p, 19개 공유 문맥 묶음의 95% 구간은 [{100*c['ci95'][0]:+.2f}, {100*c['ci95'][1]:+.2f}]%p, 두 주 비교에 대한 Holm p={c['holm_p']:.4f}다.")
    overview+=['', '이는 한 회차·한 seed·두 로컬 모델·고정 입력 방식에서 관측한 결과다. 서로 다른 과목의 문맥 묶음을 합친 불확실성 추정이며, 새 시험 회차나 새 모델에서의 재현성을 보장하지 않는다. 제품과 notice의 숫자를 혼합하거나 가장 낮은 조건만 골라 제품 성능으로 부르지 않는다.', '']
    t[4:4]=overview
    t+=['', '## 실행 기록', '', '입력 준비 후 첫 모델 호출 전에 파일 경로 결합 오타로 중단되어 수정 후 `--infer-only`로 재개했다. 당시 모델 응답은 없었으며 문항·조건·채점 계획은 변경하지 않았다. 이후 고정 코드와 입력 해시를 검사했다. 모델의 짧은 풀이·최종 번호 형식을 동일하게 유지했으며, 긴 추론을 사용하는 상용 모델의 능력으로 일반화하지 않는다.', '', '추가 표시 영역 밖의 본문 픽셀 비교 84건에서 최대 차이는 모두 0이었다. 국어·수학 생성 이미지도 눈으로 점검했다. 이 검사는 표시 영역 내부의 가독성이나 사람의 시험 성적을 보장하지 않는다.', '', '공개 결과 JSON에 포함한 문항 ID·공식정답·배점은 upstream CC BY-NC 4.0 메타데이터에서 파생한 필드다. 이 메타데이터의 이용 조건과 독립 작성한 평가 코드의 라이선스는 구분한다.']
    (ROOT/'docs/KSAT_RESULTS_2026-11-18.md').write_text('\n'.join(t)+'\n',encoding='utf8')
    print('TOTAL',[g for g in groups if g['subject']=='all']);print('COMPARISONS',comparisons);print('AUDIT',result['audit'])

if __name__=='__main__':main()
