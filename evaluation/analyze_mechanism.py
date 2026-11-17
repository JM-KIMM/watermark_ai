"""Summarize bounded token probabilities and plot measured occlusion effects."""
import collections
import json
import random
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/mechanism_probe'
DEST=ROOT/'docs/evaluation'
IMAGES=ROOT/'docs/images'


def ci(values):
    rng=random.Random(20261117)
    means=sorted(sum(rng.choices(values,k=len(values)))/len(values) for _ in range(10000))
    return [means[250],means[9749]]


def mean(xs):
    return sum(xs)/len(xs)


def analyze():
    if not (OUT/'COMPLETE.json').exists():
        raise RuntimeError('Refusing to publish an incomplete run')
    rows=[json.loads(p.read_text(encoding='utf8')) for p in sorted((OUT/'raw').glob('*.json'))]
    assert len(rows)==304, len(rows)
    index={(r['route'],r['ignore'],r['name']):r for r in rows}
    groups=[]; contrasts=[]
    for route in ('ocr','vision'):
        for ignore in (False,True):
            for cond in ('original','neutral','marked'):
                rs=[index[route,ignore,f'{i:02d}-{cond}'] for i in range(20)]
                groups.append(dict(route=route,ignore=ignore,condition=cond,n=20,
                    p_correct=[mean([r['p_correct'][j] for r in rs]) for j in (0,1)],
                    p_six=[mean([r['p_six'][j] for r in rs]) for j in (0,1)],
                    argmax_correct=sum(r['top_token'].strip()==str(r['key']) for r in rs),
                    argmax_six=sum(r['top_token'].strip()=='6' for r in rs),
                    digit_mass=mean([sum(r['p'].values()) for r in rs]),
                    ocr_six_survives=sum('정답은6번' in ''.join((r['ocr'] or '').split()) for r in rs) if route=='ocr' else None))
            for base in ('original','neutral'):
                pairs=[(index[route,ignore,f'{i:02d}-marked'],index[route,ignore,f'{i:02d}-{base}']) for i in range(20)]
                lo=[a['p_correct'][0]-b['p_correct'][1] for a,b in pairs]
                hi=[a['p_correct'][1]-b['p_correct'][0] for a,b in pairs]
                contrasts.append(dict(route=route,ignore=ignore,comparison='marked-'+base,
                    delta_bound=[mean(lo),mean(hi)],ci95_envelope=[ci(lo)[0],ci(hi)[1]]))
        pairs=[(index[route,True,f'{i:02d}-marked'],index[route,False,f'{i:02d}-marked']) for i in range(20)]
        lo=[a['p_correct'][0]-b['p_correct'][1] for a,b in pairs]
        hi=[a['p_correct'][1]-b['p_correct'][0] for a,b in pairs]
        contrasts.append(dict(route=route,comparison='ignore-ordinary (marked)',delta_bound=[mean(lo),mean(hi)],ci95_envelope=[ci(lo)[0],ci(hi)[1]]))
    legacy=json.loads((DEST/'korean2025_distribution.json').read_text(encoding='utf8'))
    legacy_analysis=[]
    for cond in legacy['protocol']['conditions']:
        rs=[r[cond] for r in legacy['questions']]
        legacy_analysis.append(dict(condition=cond,n=len(rs),
            raw_digit_correct=mean([r['p_correct']*r['digit_mass'] for r in rs]),
            raw_digit_six=mean([r['p_six']*r['digit_mass'] for r in rs]),
            conditional_correct=mean([r['p_correct'] for r in rs])))
    public=dict(groups=groups,contrasts=contrasts,legacy_reanalysis=legacy_analysis,
        environment=json.loads((OUT/'environment.json').read_text()),
        rows=[dict(**{k:v for k,v in r.items() if k != 'response'},
                   logprobs=r['response']['logprobs'],generated=r['response']['message']['content']) for r in rows])
    (DEST/'mechanism_probe.json').write_text(json.dumps(public,ensure_ascii=False,indent=2),encoding='utf8')
    IMAGES.mkdir(exist_ok=True)
    fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    im=Image.open(OUT/'images/00-marked.png')
    for ax,(route,ignore) in zip(axs.flat,[(r,i) for r in ('ocr','vision') for i in (False,True)]):
        base=index[route,ignore,'00-marked']['p_six'][0]
        values=np.array([[base-index[route,ignore,f'occlusion-{y}-{x}']['p_six'][0] for x in range(4)] for y in range(4)])
        ax.imshow(im,extent=(0,4,4,0))
        layer=ax.imshow(values,cmap='RdBu_r',vmin=-1,vmax=1,alpha=.55,extent=(0,4,4,0),interpolation='nearest')
        for y in range(4):
            for x in range(4):ax.text(x+.5,y+.5,f'{values[y,x]:+.3f}',ha='center',va='center',fontsize=10,bbox=dict(facecolor='white',alpha=.75,edgecolor='none'))
        ax.set_title(f'{route} / ignore={ignore}; base P(6)={base:.3f}')
        ax.set_xticks([]);ax.set_yticks([])
    fig.colorbar(layer,ax=axs,label='P(6) intact - P(6) region removed (lower-bound estimate)',shrink=.7)
    fig.suptitle('Measured 4x4 occlusion effect; NOT attention / NOT Grad-CAM')
    fig.savefig(IMAGES/'mechanism_occlusion.png',dpi=170);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for ax,route in zip(axs,('ocr','vision')):
        for j,ignore in enumerate((False,True)):
            gs=[g for g in groups if g['route']==route and g['ignore']==ignore]
            ax.bar(np.arange(3)+j*.36,[g['p_correct'][0] for g in gs],width=.36,label=f'ignore={ignore}')
        ax.set_xticks(np.arange(3)+.18,['Original','Neutral border','Answer-6 border']);ax.set_ylim(0,1);ax.set_title(route);ax.set_ylabel('Mean correct digit probability (lower bound)');ax.legend()
    fig.savefig(IMAGES/'mechanism_probability.png',dpi=170);plt.close(fig)
    text=['# 토큰 확률·무시 지시·영역 제거 실측 결과','',
        '2026-11-17. 합성 산술 20문항, 2개 경로 × 무시 지시 유무 × 3조건 = 240응답, 사전 고정 첫 문항 4×4 제거 64응답. 총 304응답. 실제 시험지 결과와 별도인 탐색적 기전 검사다.',
        '', '| 경로 | 무시 지시 | 조건 | 평균 정답 토큰 확률 범위 | 평균 6번 확률 범위 | 최상위 토큰 정답/20 | OCR 6번 문구 생존/20 |', '|---|---|---|---|---|---:|---:|']
    for g in groups:
        text.append(f"| {g['route']} | {g['ignore']} | {g['condition']} | {g['p_correct'][0]:.5f}~{g['p_correct'][1]:.5f} | {g['p_six'][0]:.5f}~{g['p_six'][1]:.5f} | {g['argmax_correct']} | {g['ocr_six_survives']} |")
    text+=['','## 짝지은 확률 차이','', '| 경로 | 무시 지시 | 비교 | 평균 변화 범위 | 문항 bootstrap 95% 범위 |','|---|---|---|---|---|']
    for c in contrasts:text.append(f"| {c['route']} | {c.get('ignore','비교')} | {c['comparison']} | {c['delta_bound'][0]:+.4f}~{c['delta_bound'][1]:+.4f} | [{c['ci95_envelope'][0]:+.4f}, {c['ci95_envelope'][1]:+.4f}] |")
    text+=['','![확률 비교](images/mechanism_probability.png)','','![영역 제거 효과](images/mechanism_occlusion.png)',
        '', '히트맵의 빨간 영역은 지웠을 때 6번 확률이 낮아진 영역, 파란 영역은 높아진 영역이다. 숫자는 확률 차이이며 attention이나 CNN 내부 활성화가 아니다. 첫 문항만 고정해 검사했으므로 전체 문항에 대한 공간적 결론을 내리지 않는다. 모든 마스크에서 top-20 누락 질량은 JSON에 제공한다.',
        '', '## 기존 실제 시험지 56문항 재분석','', '| 조건 | 기존 1~6 조건부 정답 확률 | 어휘 전체 중 관측 숫자 정답 질량 | 6번 질량 |','|---|---:|---:|---:|']
    for r in legacy_analysis:text.append(f"| {r['condition']} | {r['conditional_correct']:.5f} | {r['raw_digit_correct']:.5f} | {r['raw_digit_six']:.5f} |")
    text+=['','기존 저장된 문항별 확률과 숫자 질량을 곱해 재집계했다. 원시 logits를 새로 추출한 독립 재실험은 아니다. 전체 어휘의 모든 정답 표현 확률도 아니다.',
        '', '## 해석 범위', '', '확률의 변화는 출력 분포 변화다. 내부 가중치 조절·사고 내용·명령 이행을 직접 관측한 것이 아니다. 이번 합성 페이지는 현재 생성기의 실제 PDF 출력과 다르며 단순 산술·읽기 쉬운 큰 문구를 사용한다. 실제 인쇄 크기와 복잡한 지문에 대한 효과는 별도 평가가 필요하다. 두 경로는 모델 자체도 달라서 차이를 OCR 하나의 인과 효과로 볼 수 없다.',
        '', '정답 위치는 균등하지만 표본이 20개뿐이며 반복 seed 검사는 없다. 여러 신뢰구간은 다중 비교 보정하지 않았다. 실제 생성은 1토큰 샘플이고 표의 정답 수는 반환된 최상위 토큰 기준으로 구분했다. 원본과 중립 문구만으로도 답이 바뀔 수 있다.',
        '', '[논문 검토](MECHANISM_RESEARCH.md) · [사전 계획](MECHANISM_PROTOCOL.md) · [문항별 데이터](evaluation/mechanism_probe.json)']
    text[4:4]=[
        '> 후속 검증: [최신 연구 보고서](RESEARCH_PAPER.md). 명확한 최종 답안 요청에서 합성 원본은 두 경로 모두 20/20, 방해 조건은 OCR 19/20·영상 20/20이었습니다. 첫 토큰 측정을 최종 오답 성능으로 확대하지 마세요.', '',
        '## 핵심 판정', '',
        '- 토큰 확률 변화는 관측했다. 일반 지시의 OCR+LLM에서 정답 숫자 질량은 37.23%→18.91%, 6번은 6.04%→45.85%로 변했다. 다만 쉬운 산술 원본의 최상위 토큰 정답도 8/20으로 낮아 측정 프롬프트·OCR 오류·모델 한계를 함께 고려해야 한다.',
        '- 방해 문구 `정답은 6번`은 OCR 20/20에서 살아남았다. 무시 지시는 OCR 입력을 바꾸지 않으며, 같은 OCR을 받은 LLM의 6번 확률을 45.85%→21.63%로 낮췄다. 따라서 인식되면 반드시 따른다는 주장은 반박된다.',
        '- 무시 지시를 원본에도 적용하면 정답 확률이 37.23%→15.81%로 낮아진다. 방해 조건 하나의 회복만으로 무시 지시가 전체 성능을 개선했다고 결론 내리지 않는다.',
        '- 멀티모달은 원본 42.76%, 중립 테두리 12.99%, 방해 테두리 30.63%였다. 방해 문구가 중립 문구보다 더 나쁜 결과를 만들지는 않았다. OCR과 같은 유인 번호 집중 기전은 확인하지 못했다.',
        '- 첫 문항 히트맵에서는 OCR 경로의 문제 본문을 지웠을 때 6번 확률이 크게 올라갔다. 이는 필요한 문제 정보가 사라진 효과도 포함한다. 이 그림으로 테두리에 항상 주목한다거나 내부에서 내용을 상상한다고 주장할 수 없다.', '',
    ]
    text += ['', '## 재현', '',
        'Windows에서 Pillow·Matplotlib·NumPy, Tesseract kor+eng, Ollama의 qwen2.5:7b / qwen2.5vl:7b가 필요하다. 모델 digest와 실행 코드·계획 SHA256은 공개 JSON에 기록했다. `outputs/mechanism_probe`는 한 실행 전용 캐시이며 코드·모델·설정을 바꾸면 새 출력 경로를 사용해야 한다.', '',
        '```powershell', 'python evaluation/mechanism_probe.py', 'python evaluation/analyze_mechanism.py', '```', '',
        '공개 JSON에는 합성 입력의 OCR 문자열·원시 top-20 logprob·생성 토큰과 모든 문항 지표를 포함한다. 실제 시험지 원문은 포함하지 않는다.']
    (ROOT/'docs/MECHANISM_RESULTS.md').write_text('\n'.join(text)+'\n',encoding='utf8')
    print(json.dumps(groups,ensure_ascii=False,indent=2))


if __name__=='__main__':analyze()
