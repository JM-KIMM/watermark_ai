"""Build the paper-style report only after every required analysis is complete."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'docs';E=D/'evaluation'
def load(name):return json.loads((E/name).read_text(encoding='utf8'))

def main():
    ext=load('external_validity.json');measurement=load('measurement_validity.json');clear=load('clear_answer_probe.json');cal=load('validity_calibration.json');occ=load('occlusion_controls.json')
    lines=['# 시험지 테두리 텍스트는 AI 풀이를 방해하는가?',
        '## 토큰 확률, 최종 답안, 입력 경로와 평가 설계의 타당성에 관한 통제 실험', '',
        '**연구 단계의 재현 가능한 실험 보고서 · 2026-11-17 · 동료심사 및 현장 검증 전**', '',
        '저자·프로젝트: JM-KIMM / watermark_ai. 구현·분석에는 AI 코딩 도구를 사용했다. 이 문서는 성공 사례 홍보가 아니라 관측 결과, 반증, 방법론적 한계를 함께 기록한다.', '',
        '## 초록', '',
        '시험지의 테두리 문구가 OCR 또는 시각언어모델의 풀이를 방해한다는 가설을 검토했다. 기존 56문항 확률 자료와 20문항 합성 자료를 재분석하고, 새로운 실제 영어 시험지 세 회분의 독해 84문항에서 원본·동일 배치 대조군·현재 워터마크·무시 지시를 비교했다. 합성 측정 타당성 검사 120회와 명확한 최종 답안 방식의 후속 요인 실험 240회를 추가했다. 첫 토큰 확률 측정에서 낮았던 합성 원본 정확도는 명확한 보기 번호 요청 및 짧은 풀이 생성 후 두 경로 모두 20/20으로 회복했다. 같은 방식에서 방해 테두리는 OCR+LLM 19/20, 멀티모달 20/20이었고, OCR+LLM도 무시 지시 후 20/20이었다. 따라서 첫 토큰 확률 이동은 실제 최종 오답의 충분조건이 아니다. 실제 시험지에 대한 효과 크기와 불확실성은 아래 사전 고정 비교로 보고하며, 일반적인 AI 부정행위 예방 효과나 사람 가독성을 입증하지 않는다.', '',
        '**핵심어:** 문서 기반 프롬프트 주입, OCR, 시각언어모델, 측정 타당성, 짝지은 실험, 보정, 설명 가능성', '',
        '## 1. 연구 질문', '',
        'RQ1: 입력의 테두리 텍스트는 답안 숫자 토큰의 확률을 이동시키는가? RQ2: 그 변화는 최종 보기 선택의 오류로 이어지는가? RQ3: OCR 인식, LLM 지시 이행, 멀티모달 풀이를 구분할 때 어느 단계에서 효과가 나타나는가? RQ4: 입력 배치·프롬프트·보기 순서·시각화 방법을 통제한 뒤에도 결론이 유지되는가?', '',
        '성공 기준은 단순한 확률 변화가 아니라, 같은 문제 내용과 배치를 유지한 대조군에 비해 실제 최종 정답률이 낮아지고 그 효과가 다른 입력 경로와 시험에서도 재현되는 것이다. "무시"라는 단어가 인코딩된다는 사실을 모델이 그 내용을 따르거나 상상한다는 주장과 동일시하지 않는다.', '',
        '## 2. 관련 연구와 분석법 선택', '',
        'Wang 등[1]은 첫 토큰 기반 평가와 생성된 최종 답안의 불일치를 보여준다. 이에 확률 실험을 최종 성적과 분리하고 명확한 최종 번호 응답으로 재검사했다. Pezeshkpour와 Hruschka[2]의 보기 순서 민감도 연구에 따라 보기 순환 검사를 추가했다. Guo 등[3]을 참고해 confidence와 정답의 일치를 Brier score·log loss·ECE로 측정하되, calibration이 인과성이나 모델 이해의 증거라고 해석하지 않았다.', '',
        'Grad-CAM[4]은 gradient를 사용한 합성곱 특징맵 설명이다. Qwen2.5-VL[5]은 ViT 기반이므로 접근하지 않은 CNN 내부 활성화를 측정했다고 주장할 수 없다. Attention의 설명 가능성 논쟁[6,7], RISE[8], saliency sanity check[9], ROAR[10]는 시각화에 출력 개입·음성 대조군·분포 변화 검토가 필요함을 뒷받침한다. 본 실험은 고정 영역 제거와 픽셀 동일성 검사만 수행했으며 RISE·Grad-CAM·ROAR를 구현했다고 부르지 않는다. 부정문 처리 연구[11] 및 간접 주입 평가[12]는 무시 지시 실패를 검사할 동기를 주지만, 이 시험지의 효과를 대신 입증하지 않는다.', '',
        '## 3. 자료와 실험 설계', '',
        '### 3.1 자료 수집과 출처', '',
        '새 자료는 2023년 9월, 2024년 9월, 2025년 6월 시행 고3 모의평가 영어 문제지와 정답·해설이다. 학년도와 시행 연도를 구별했다. 각 8쪽, 총 24쪽을 확보했다. 1~17번 듣기를 제외하고 18~45번 독해 객관식 28문항씩 총 84문항을 사용했다. 세 시험 모두 영어이므로 새 과목 모집단을 대표하지 않는다. 기존 수학·국어·세무사 자료의 결과는 별도 과거 연구로 유지한다.', '',
        'KICE CDN 두 주소는 404여서 공개 미러와 EBS에서 제작기관 표기가 있는 PDF를 수집했다. URL·파일 크기·SHA256을 공개하고 실제 PDF는 로컬에만 저장했다. 정답표 파싱 결과를 별도 전사 84개와 대조했으며 모두 일치했다. 2024/2025 자료는 공개 정답 목록과도 대조했다. 공개 시험지이므로 모델 사전학습 오염을 배제할 수 없다.', '',
        '| 시험 ID | 시행 시점 | 독해 객관식 | 원문 쪽수 |', '|---|---|---:|---:|',
        '| eng_202309 | 2023-09 | 28 | 8 |','| eng_202409 | 2024-09 | 28 | 8 |','| eng_202506 | 2025-06 | 28 | 8 |', '',
        '### 3.2 조건과 모델', '',
        '| 조건 | 입력 | 해석 |','|---|---|---|',
        '| A: original | 원본 200dpi 렌더 | 총 구성 변화의 기준 |',
        '| B: control | 원본에 QR용 행과 페이지 확장만 적용 | 같은 배치의 대조군 |',
        '| C: marked | 현재 생성기 frames/labelled/absent, 6번 문구·테두리·QR | 실제 생성 구성 |',
        '| D: ignore | C + 시스템 수준 무시 지시 | 입력은 같고 풀이 지시만 변화 |', '',
        'B와 C의 페이지 크기는 같으며 200dpi에서 선언된 테두리·프레임·QR/캡션 영역 밖의 픽셀 차이는 24쪽 모두 0이었다. 그러나 C−B는 QR과 여러 문구가 함께 추가되는 구성 효과다. 6번 문장만의 순수 효과가 아니다. QR은 이 실험에서 도구 접근이 없는 모델의 시각 요소이며 실제 방문 추적을 평가하지 않았다.', '',
        'OCR 경로는 Tesseract kor+eng PSM 3 → Qwen2.5 7B Q4_K_M, 영상 경로는 Qwen2.5-VL 7B Q4_K_M이다. 서로 다른 모델이므로 두 경로 차이는 OCR 유무만의 인과 효과가 아니다. 문맥 32,768, 최대 출력 768토큰, temperature 0, seed 20261117로 고정했다. 한 페이지의 대상 문항을 묶되 공통 지문 페이지를 포함했다. 짧은 근거 뒤 보기 번호를 JSON으로 요청했고, 1~5만 허용하는 강제 grammar는 사용하지 않았다. 6번·null·형식 오류를 따로 기록한다.', '',
        '실행 전 계획 파일의 해시와 모델 digest를 저장했으나 공개 등록기관에 등록한 확증 연구는 아니다. 자료 선정과 설계는 기존 연구 결과를 알고 수행했다. 방해 효과를 확인한 문항만 골라 주 분석하지 않았다.', '',
        '### 3.3 측정 타당성 진단', '',
        '동일한 합성 산술 20문항에 대해 첫 토큰 응답 대신 보기 번호를 명시하고 짧은 계산 후 JSON 최종 답을 받았다. 앞의 10문항은 다섯 순환 보기 배치로 검사했다. 이 단계는 120응답이다. 이후 이 진단의 결과를 보고 합성 원본·중립·방해 × 무시 지시 유무 × 두 모델의 240응답 후속 실험을 설계했다. 이 후속 연구는 사후 탐색임을 명시한다. 출력 숫자 제한은 프롬프트에만 있고 강제 토큰 제약은 없다.', '',
        '## 4. 지표와 통계 분석', '',
        '주 비교는 C−B의 최종 정답률 차이이며 두 입력 경로를 하나의 검정 가족으로 Holm 보정한다[13]. A−C와 C−D는 보조 비교다. 실패 응답은 오답과 구분하고 조건별 분모 및 paired complete-case 수를 공개한다. 미해결을 모두 정답 또는 오답으로 두는 정확도 범위도 해석 시 확인한다.', '',
        '문항별 변화 dᵢ = correctness(Cᵢ) − correctness(Bᵢ)를 계산했다. 같은 문맥 페이지를 공유하는 요청을 연결한 묶음을 단위로 10,000회 bootstrap하여 95% 구간을 얻었다. 같은 묶음의 변화 부호를 함께 뒤집는 10,000회 permutation 검정도 수행했다. 부호 교환가능성 가정이 필요한 근사 검정이며 무작위 배정의 인과 보장은 없다. McNemar exact 검정은 정답→오답/오답→정답의 비대칭을 검사하는 보조 결과다. 문항 독립 가정이 약하므로 이 p값보다 묶음 분석을 우선한다.', '',
        '확률 재분석은 숫자 1~6과 나머지 어휘 질량의 7범주를 사용한다. Brier = mean Σₖ(pᵢₖ−1[yᵢ=k])², log loss = mean −log pᵢ,yᵢ, ECE = Σ_b(n_b/n)|accuracy_b−confidence_b|이다. ECE는 동일 폭 5개 bin을 사용했고 빈 bin은 제외했다. log loss의 수치 하한은 10⁻¹²이다. 첫 토큰의 의미 있는 최종 답안 신뢰도를 직접 측정하는 지표는 아니다. top-20에 없는 토큰의 확률은 잔여 질량에 들어가므로 해당 자료의 calibration은 근사·민감도 분석이다.', '',
        '기존 1~6 조건부 확률은 문항별 숫자 질량을 곱해 원래 관측 숫자 질량으로 환산했다. 평균끼리 곱하지 않았다. JSD·엔트로피는 분포 이동/집중을 설명하며, 이해 또는 정답률 감소를 단독으로 입증하지 않는다. 단일 문항 4×4 영역 제거의 음성 대조군은 픽셀상 동일한 입력이 되는 빈 영역이다.', '',
        '### 4.1 정밀도와 표본 크기', '',
        '84문항 및 세 시험은 편의상 확보한 표본이며 효과를 보면서 늘린 표본이 아니다. 독립 문항·불일치율 0.3·양측 5%·80% power라는 낙관적 근사에서도 감지 가능한 차이는 약 17%p 수준이다. 묶음 의존성은 정밀도를 더 낮출 수 있다. 따라서 유의하지 않음은 작은 효과가 없다는 증거가 아니며, 세 시험만으로 시험 모집단의 안정적 random-effects 추정도 주장하지 않는다.', '',
        '## 5. 결과', '',
        '### 5.1 측정 프롬프트와 보기 순서', '',
        '| 경로 | 기존 첫 토큰 정답/20 | 명확한 최종 답 정답/20 | 번호 불일치/20 | 5순환 모두 일관된 문항/10 |', '|---|---:|---:|---:|---:|']
    for r in measurement['summary']:lines.append(f"| {r['route']} | {r['original_first_token_correct']} | {r['clear_final_correct']} | {r['first_final_mismatch']} | {r['order_invariant']} |")
    lines+=['','![보기 순서 검사](images/validity_order.png)', '',
        '두 경로 모두 명확한 최종 답 방식에서 원본 20/20이었다. 기존 원본 성적 저하를 산술 능력 부족으로 설명할 수 없다. 다만 요청 문구·풀이 생성·출력 길이를 함께 바꿨으므로 어느 한 요소가 유일한 원인이라고 할 수 없다. 쉬운 10문항에서 순서 민감도가 나타나지 않았다는 결과를 실제 독해 문항에 일반화하지 않는다.', '',
        '### 5.2 명확한 최종 답 방식의 합성 후속 실험', '',
        '| 경로 | 무시 지시 | 원본 정답/20 | 중립 정답/20 | 방해 정답/20 | 방해의 6번 선택 |', '|---|---|---:|---:|---:|---:|']
    for route in ('ocr','vision'):
        for ignore in (False,True):
            gs={r['condition']:r for r in clear['summary'] if r['route']==route and r['ignore']==ignore}
            lines.append(f"| {route} | {ignore} | {gs['original']['correct']} | {gs['neutral']['correct']} | {gs['marked']['correct']} | {gs['marked']['six']} |")
    lines+=['','방해 문구가 보이는 조건에서도 대부분 올바르게 풀었다. 무시 지시가 없을 때 OCR 경로의 한 문항에서만 6번이 나왔으며 무시 지시에서는 사라졌다. 첫 토큰 분포 변화의 방향을 그대로 최종 오답률의 크기로 해석하는 주장은 이 실험에서 유지되지 않는다.', '',
        '### 5.3 추가 실제 시험지 전체 결과', '',
        '| 경로 | 조건 | 정답 | 응답 확정 | 예정 문항 | 6번 | null | 처리 오류 |', '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in ext['groups']:
        if r['exam']=='all':lines.append(f"| {r['route']} | {r['condition']} | {r['correct']} | {r['resolved']} | {r['n']} | {r['six']} | {r['abstain']} | {r['errors']} |")
    lines+=['','| 경로 | 비교(후−전) | 변화 %p | 묶음 95% 구간 %p | 정답 손실 | 정답 회복 | cluster permutation p | 주 비교 Holm p |', '|---|---|---:|---|---:|---:|---:|---:|']
    for c in ext['contrasts']:
        lines.append(f"| {c['route']} | {c['treatment']}−{c['baseline']} | {c['mean']*100:+.2f} | [{c['ci95'][0]*100:+.2f}, {c['ci95'][1]*100:+.2f}] | {c['losses']} | {c['gains']} | {c['sign_flip_p']:.4f} | {c.get('holm_primary_p','보조 비교')} |")
    lines+=['','![효과 크기](images/external_validity_forest.png)','','![정오 전이](images/external_validity_transitions.png)', '',
        '### 5.4 시험별 이질성', '', '| 경로 | 시험 | 원본 | 배치 대조 | 워터마크 | 무시 지시 |','|---|---|---:|---:|---:|---:|']
    for route in ('ocr','vision'):
        for exam in ('eng_202309','eng_202409','eng_202506'):
            gs={r['condition']:r for r in ext['groups'] if r['route']==route and r['exam']==exam}
            lines.append('| '+route+' | '+exam+' | '+' | '.join(f"{gs[c]['correct']}/{gs[c]['resolved']}" for c in ('original','control','marked','ignore'))+' |')
    lines+=['','### 5.5 확률 보정과 시각화의 타당성', '',
        '| 자료 | 경로/지시 | 조건 | Brier | log loss | ECE(5 bins) |', '|---|---|---|---:|---:|---:|']
    for r in cal['results']:
        lines.append(f"| {r['study']} | {r.get('route','A.X')} / {r.get('ignore','기존')} | {r['condition']} | {r['brier']:.4f} | {r['nll']:.4f} | {r['ece']:.4f} |")
    lines+=['','![신뢰도 도표](images/validity_calibration.png)', '',
        f"기존 영역 제거 측정의 픽셀 동일 음성 대조는 {occ['negative_controls']}개였다. 동일 입력에서도 정답 숫자 확률이 최대 {occ['max_identical_input_delta_correct']:.6f}, 6번 확률이 최대 {occ['max_identical_input_delta_p6']:.6f} 달라졌다. 실행 순서·캐시·수치 계산에 따른 변동 가능성이 있으므로 이 정도 크기의 히트맵 차이를 독립적인 인과 효과로 보지 않는다. 이는 통계적 검정 임계값 추정이 아니라 관측된 반복성 한계다.", '',
        '## 6. 논의', '',
        '이 프로젝트의 핵심 실패 위험은 확률 이동, OCR 인식, 최종 오답, 실제 부정행위 예방을 하나의 지표처럼 취급하는 것이다. 본 연구에서는 단계마다 다른 검사가 필요함을 확인했다. OCR에서 문구가 살아남았다는 사실은 언어모델이 그 지시를 따라야 한다는 뜻이 아니다. 입력 영역을 처리했다는 사실도 의미적 혼동이나 인간의 사고 억제 현상을 입증하지 않는다.', '',
        '현재 생성기와 동일 배치 대조군의 차이는 문구·QR·프레임을 함께 포함한다. 실제 시험지에서 차이가 있더라도 6번 문장의 순수 효과라고 부를 수 없다. 반대로 확률 차이가 명확하더라도 최종 풀이에서 회복할 수 있다. 짧은 토큰 응답에 대한 취약성을 실제 사용자의 풀이 요청에 대한 견고한 방어로 홍보해서는 안 된다.', '',
        '처음부터 원본 정답률이 낮은 경로에서는 바닥 효과와 OCR 손실이 큰 비중을 차지한다. 원본에서 맞힌 문항만 보고하는 분석은 사후 선택 편향을 만들 수 있어 주 분석에 사용하지 않았다. 분석법을 많이 나열하는 대신 각 방법이 배제할 수 있는 대안 설명을 명시했다.', '',
        '## 7. 타당성 위협과 한계', '',
        '- 구성 타당성: 첫 토큰·digit-event calibration·최종 답안·실제 부정행위는 서로 다르다. 하나를 다른 것의 대용 지표로 자동 간주하지 않는다.',
        '- 내부 타당성: 본문 픽셀 일치는 확인했지만 QR/문구/프레임을 한꺼번에 비교했다. 무시 조건의 시스템 지시는 원본 조건에 교차하지 않은 실제 시험지 설계이므로 일반적인 지시 효과와 상호작용을 완전히 분리하지 못한다.',
        '- 외적 타당성: 추가 자료는 영어 세 회분, 로컬 두 7B 경로뿐이다. 실제 카메라·스마트 안경·상용 모델·고해상도 crop·OCR 전처리 방어·새 과목으로 일반화할 수 없다. 공개 시험지의 학습 오염을 배제하지 못한다.',
        '- 통계 타당성: 같은 지문/페이지의 상관을 묶음으로 반영했으나 시험 수준의 모집단은 세 개뿐이다. 여러 보조 분석은 탐색적이며 주 비교 두 개만 Holm 보정했다. bootstrap의 coverage가 작은 묶음 수에서 완벽하다고 보장할 수 없다.',
        '- 사람 영향: 가독성·접근성·풀이 시간·정답률의 인간 대상 비열등성 연구를 수행하지 않았다. AI만 방해한다는 주장은 아직 근거가 없다.',
        '- 설명 가능성: 내부 attention·gradient·model randomization을 측정하지 않았다. 고정 한 문항 occlusion을 보편적인 주목 지도라고 하지 않는다. 본문 제거는 결손 입력을 만든다.',
        '- 재현성: 온도 0도 완전 결정성을 보장하지 않는다. 모델 digest·파일 해시·원시 응답·실행 설정을 보존했으나 다른 하드웨어의 bitwise 재현을 보장하지 않는다.', '',
        '## 8. 결론', '',
        '문구로 토큰 분포를 이동시킬 수 있다는 관측은 유지되지만, 그것만으로 AI 풀이 방해의 실용적 타당성이 확보되지는 않는다. 특히 명확한 최종 답안 검사에서 합성 방해 효과가 대부분 사라진 결과는 강한 반증이다. 실제 시험지의 결과는 표의 효과 크기·신뢰구간·실패율과 함께 읽어야 한다. 현 단계에서 본 시스템은 연구용 프로토타입이며 일반적 부정행위 차단 수단으로 검증되지 않았다.', '',
        '다음 확증 연구에는 모델/프롬프트/도메인을 고정한 외부 등록 계획, 더 많은 독립 시험, 실제 촬영·부분 crop, 사람 가독성 비열등성, 강한 상용 모델과 다중 OCR 엔진이 필요하다. 결과를 본 뒤 유리한 조건을 골라 동일 평가셋에서 반복 최적화하면 확증 연구가 되지 않는다.', '',
        '## 9. 재현·자료 공개·변경 이력', '',
        '새 실제 시험지 84문항 × 4조건 × 2경로 = 672개 문항 응답(21페이지 요청 × 8 = 168개 모델 호출 묶음), 측정 진단 120응답, 합성 후속 240응답을 새로 실행했다. 재시도는 원시 기록에 별도로 남아 있으며 표본 수를 늘리지 않는다. 기존 56문항 분포 및 304개 기전 응답은 재분석 자료로 구분했다.', '',
        '```powershell',
        'python -m pip install -r requirements-research.txt',
        'python evaluation/collect_external_exams.py',
        'python evaluation/external_validity.py prepare',
        'python evaluation/validate_external_inputs.py',
        'python evaluation/verify_external_keys.py',
        'python evaluation/external_validity.py infer',
        'python evaluation/measurement_validity.py',
        'python evaluation/clear_answer_probe.py',
        'python evaluation/audit_occlusion_controls.py',
        'python evaluation/analyze_validity.py',
        'python evaluation/write_research_paper.py', '```', '',
        '기존 Windows 가상환경에 Pillow/PyMuPDF/NumPy/Matplotlib가 필요하고 Tesseract kor+eng 및 Ollama 두 모델을 설치해야 한다. 과거 자료 재분석 파일은 저장소에 포함된다. 캐시는 고정 실행에만 재사용하며 설정 변경 시 새 출력 디렉터리를 사용한다. 모델을 동시에 여러 프로세스에서 실행하지 않는다.', '',
        '[사전 계획](EXTERNAL_VALIDITY_PROTOCOL.md) · [실제 시험지 문항별 결과/출처/해시](evaluation/external_validity.json) · [측정 타당성](evaluation/measurement_validity.json) · [명확한 답안 후속 실험](evaluation/clear_answer_probe.json) · [확률 보정](evaluation/validity_calibration.json) · [시각화 음성 대조](evaluation/occlusion_controls.json)', '',
        '### 해석 변경 기록', '',
        '이전 보고서의 첫 토큰 확률은 실제 관측값으로 남긴다. 그러나 낮은 합성 원본 성적을 모델 능력의 한계로 해석하거나 그 확률 이동을 최종 오답 효과로 확대하는 설명은 이번 진단으로 수정한다. 이 문서가 최신 해석이며 이전 기록은 감사 가능성을 위해 삭제하지 않는다.', '',
        '## 참고문헌', '',
        '1. Wang et al. (2024). “My Answer is C”: First-Token Probabilities Do Not Match Text Answers in Instruction-Tuned Language Models. Findings of ACL. https://aclanthology.org/2024.findings-acl.441/',
        '2. Pezeshkpour & Hruschka (2024). Large Language Models Sensitivity to The Order of Options in Multiple-Choice Questions. Findings of NAACL. https://aclanthology.org/2024.findings-naacl.130/',
        '3. Guo et al. (2017). On Calibration of Modern Neural Networks. ICML. https://proceedings.mlr.press/v70/guo17a.html',
        '4. Selvaraju et al. (2017). Grad-CAM. ICCV. https://arxiv.org/abs/1610.02391',
        '5. Bai et al. (2025). Qwen2.5-VL Technical Report. Preprint. https://arxiv.org/abs/2502.13923',
        '6. Jain & Wallace (2019). Attention is not Explanation. NAACL. https://aclanthology.org/N19-1357/',
        '7. Wiegreffe & Pinter (2019). Attention is not not Explanation. EMNLP. https://aclanthology.org/D19-1002/',
        '8. Petsiuk et al. (2018). RISE: Randomized Input Sampling for Explanation of Black-box Models. BMVC. https://arxiv.org/abs/1806.07421',
        '9. Adebayo et al. (2018). Sanity Checks for Saliency Maps. NeurIPS. https://proceedings.neurips.cc/paper/2018/hash/294a8ed24b1ad22ec2e7efea049b8737-Abstract.html',
        '10. Hooker et al. (2019). A Benchmark for Interpretability Methods in Deep Neural Networks. NeurIPS. https://proceedings.neurips.cc/paper_files/paper/2019/file/fe4b8556000d0f0cae99daa5c5c5a410-Paper.pdf',
        '11. Truong et al. (2023). Language models are not naysayers. *SEM. https://aclanthology.org/2023.starsem-1.10/',
        '12. Yi et al. (2025). Benchmarking and Defending Against Indirect Prompt Injection Attacks on Large Language Models (BIPIA). KDD 2025; arXiv v4. https://arxiv.org/abs/2312.14197',
        '13. Holm (1979). A Simple Sequentially Rejective Multiple Test Procedure. Scandinavian Journal of Statistics 6:65–70. https://doi.org/10.2307/4615733', '',
        '검색일: 2026-11-17. 공식 학회/저자 원문 중심의 범위 탐색이며 PRISMA 기반 체계적 문헌고찰은 아니다. 각 분석은 해당 논문의 전체 재현이 아니라 위에서 명시한 제한된 방법 적용이다.',
    ]
    pos=next(i for i,s in enumerate(lines) if s.startswith('**핵심어:**'))
    lines[pos:pos]=['추가 실제 시험지의 최종 정답은 OCR 경로에서 A/B/C/D 각각 23/22/21/23개, 영상 경로에서 37/36/33/39개였다(각 84문항). 주 비교 C−B는 OCR −1.19%p(95% CI −12.22~+9.64), 영상 −3.57%p(−12.05~+4.71)였고, 두 경로 모두 Holm 보정 p=1.0으로 감소를 확정하지 못했다.', '']
    pos=lines.index('### 5.4 시험별 이질성')
    lines[pos:pos]=['OCR 경로의 C는 6번을 29/84번 선택했지만 B 대비 정답 손실 9개와 회복 8개가 상쇄됐다. "유인 번호를 골랐다"는 지표가 커져도 실제 추가 오답은 작을 수 있다. D에서도 6번이 28번 나와 실제 독해 자료에서는 무시 지시가 이 현상을 거의 제거하지 못했다. 영상 경로는 C에서 6번을 한 번도 선택하지 않았고, D에서 정답 수는 33→39로 회복 방향이었다. 그러나 보조 비교의 묶음 permutation p=0.1553이므로 일반적인 개선 효과로 확정하지 않는다.', '']
    position=lines.index('### 3.3 측정 타당성 진단')
    lines[position:position]=[
        '초기 v1에서는 구조 예시의 `question` 키 복사·중복 키·장문 전사로 오류가 반복됐다. 중단 시 OCR 84개 요청 중 8개, 영상 23개 요청 중 23개가 형식 실패였다. 이를 방해에 의한 오답으로 계산하지 않았다. v1의 코드·원시 응답·계획을 보존하고 v2에서 두 경로의 전체 조건을 재실행했다. v2는 JSON 구조와 문항 키만 schema로 강제하고 답안은 제한 없는 integer/null로 받았다. 이 실행 중 수정은 결과 관측 이후이며 독립된 사전 등록이라고 주장하지 않는다.', '',
    ]
    lines += ['', '## 검증 기록', '',
              '독립 감사에서 141개 입력 파일 해시, 168개 원시 응답 묶음, 672개 문항을 재검사했고 공개 점수와 모두 일치했다. 중복 JSON 키도 별도로 검사했다. 최종 v2 형식 오류는 0개였다. 코드 테스트는 68개 실행 중 67개 통과, 1개 건너뜀이다.', '',
              '[독립 감사 결과](evaluation/external_independent_audit.json) · [실행 환경](evaluation/research_environment.json) · [인쇄용 HTML](RESEARCH_PAPER.html)']
    (D/'RESEARCH_PAPER.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print('Wrote',D/'RESEARCH_PAPER.md')
if __name__=='__main__':main()
