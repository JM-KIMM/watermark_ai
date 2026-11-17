"""Export audited scores without source text, local paths, QR URLs or IP records."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
NAMES={'original':'원본','layout_control':'동일 배치 대조군','current_choices':'현재 문제 보기','qr_only':'URL QR만','command_only':'비풀이 명령만','other_page':'다른 페이지 원문'}
EXAMS={'exam01':'세무사 1교시','exam02':'세무사 2교시·민법','exam03':'세무사 2교시·상법','exam04':'세무사 2교시·행정소송법','exam05':'수능 국어','exam08':'수능 수학','exam09':'수능 영어'}


def unit_label(exam,unit):
    if unit=='questions_1_40':return '재정학' if exam=='exam01' else '회계학개론'
    if unit=='questions_41_80':return {'exam01':'세법학개론','exam02':'민법','exam03':'상법','exam04':'행정소송법'}[exam]
    form='홀수' if unit.startswith('odd') else '짝수'
    if unit in ('odd','even'):return form+' · 읽기'
    return form+' · 공통+'+{'speech':'화법과 작문','language':'언어와 매체','probability':'확률과 통계','calculus':'미적분','geometry':'기하'}[unit.split('_',1)[1]]


def read(p):return json.loads(Path(p).read_text(encoding='utf8'))


def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')


def export(out):
    audit=read(out/'independent_audit.json');plan=read(out/'plan.json');qr=read(out/'qr_verification.json');layout=read(out/'layout_verification.json');ocr=read(out/'ocr_region_diagnostics.json')
    destination=ROOT/'docs/evaluation';destination.mkdir(exist_ok=True)
    write(destination/'strict_audit.json',audit);write(destination/'strict_questions.json',read(out/'audited_questions.json'))
    write(destination/'strict_input_hashes.json',read(out/'input_seal.json'))
    write(destination/'strict_protocol.json',{k:v for k,v in plan.items() if k not in ('qr',)})
    # Protocol contains only model metadata, public question IDs and hashes;
    # no source PDFs/OCR/capture text, collector URL or issuance registry.
    write(destination/'strict_qr.json',qr)
    write(destination/'strict_ocr_regions.json',ocr)
    write(destination/'strict_scoring_validation.json',read(out/'scoring_validation.json'))
    if (out/'context_preflight.json').exists():write(destination/'strict_context.json',read(out/'context_preflight.json'))
    write(destination/'strict_layout.json',dict(total_pages=layout['total_pages'],total_qr=layout['total_qr'],total_boxes=layout['total_boxes'],
          scored_questions_have_qr=layout['scored_questions_have_qr'],
          maximum_unmasked_pixel_delta=max(p['body_max_delta'] for e in layout['exams'] for p in e['pages'])))
    text=['# 보기 원문 구성의 엄격 캡처 평가','',
          '이 결과는 `source-choices-url-qr-v4`의 측정입니다. 과거 v3의 86→100 결과와 조건·모델·프롬프트가 다르므로 버전 간 숫자를 직접 빼서 효과로 해석하지 않습니다.','',
          f"실험 ID: `{audit['identity']}`. 보고서 생성(UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}.",'',
          '## 전체 객관식 결과','',
          '7개 원본 PDF의 554문항 노출을 채점했습니다. 듣기·서술형·수학 단답형은 제외했습니다. 같은 문제의 짝수형·공통 회계 등 반복을 묶으면 357문항군입니다. 촬영 실물 사진이 아닌 200dpi PDF 페이지 PNG 캡처를 사용했습니다.','',
          '| 입력 경로 | 조건 | 정답 / 응답 확정 | 정확도 | 답을 낸 수 | 미해결 오류 |','|---|---|---:|---:|---:|---:|']
    if (out/'interpretation.md').exists():text[6:6]=[(out/'interpretation.md').read_text(encoding='utf8').strip(),'']
    for backend,details in audit['backends'].items():
        label='Qwen2.5-VL 7B' if backend=='vision' else 'Tesseract + Qwen2.5 7B'
        for c,m in details['primary'].items():
            text.append(f"| {label} | {NAMES[c]} | {m['correct']} / {m['resolved']} | {m['percent']:.2f}% | {m['answered']} | {m['total']-m['resolved']} |")
    text += ['', '오류는 오답으로 조용히 합산하지 않습니다. 답이 확정된 수에는 명시적 무응답·거부를 포함하며 정답은 0점입니다. 조건부 정확도와 오류 유형은 JSON에 따로 제공합니다. 오류율이 1%를 넘으면 사전 계획의 품질 기준을 만족하지 못합니다. 미해결 응답을 모두 정답 또는 모두 오답으로 가정한 전체 범위도 JSON에 공개합니다. 아래 차이는 두 조건 모두 응답이 확정된 쌍에서 계산합니다.','',
             '## 같은 문항의 변화와 불확실성','',
             '| 입력 경로 | 비교 | 정답→비정답 | 비정답→정답 | 변화(%p) | 문항군 bootstrap 95% 구간 |','|---|---|---:|---:|---:|---|']
    for backend,details in audit['backends'].items():
        for comparison in details['primary_comparisons']:
            a,b=comparison['conditions'];lo,hi=comparison['cluster_bootstrap_95']
            text.append(f"| {backend} | {NAMES[a]} → {NAMES[b]} | {comparison['correct_to_wrong']} | {comparison['wrong_to_correct']} | {comparison['delta_percentage_points']:+.2f} | [{lo:+.2f}, {hi:+.2f}] |")
    text += ['', '음수는 정확도 감소, 양수는 증가입니다. 비정답에는 명시적인 답안 없음도 포함합니다. 정답에서 잘못된 보기로 바뀐 수와 답안 없음으로 바뀐 수는 JSON에 따로 제공합니다. 사전 계획의 신뢰구간은 중복 문항군을 단위로 재표집합니다. 554회를 독립 표본으로 가정하지 않습니다. 중복 횟수의 영향을 줄인 문항군 평균 차이도 JSON에 함께 기록합니다. 개별 95% 구간이며 다중 비교 보정은 하지 않았습니다.','',
             '같은 지문·이미지 묶음에 속한 문항의 추가 의존성을 보기 위해 실행 도중 보조 분석을 추가했습니다. 같은 문맥 페이지를 공유하는 요청의 문항들을 전이적으로 묶고 중복 문항의 연결도 유지합니다. 다음 표는 사전 분석을 대체하지 않는 탐색적 민감도 검사입니다.','',
             '| 경로 | 비교 | 공유 문맥 묶음 수 | 추가 bootstrap 95% 구간(%p) |','|---|---|---:|---|']
    for backend,details in audit['backends'].items():
        for comparison in details['supplementary_shared_context_comparisons']:
            a,b=comparison['conditions'];lo,hi=comparison['cluster_bootstrap_95']
            text.append(f"| {backend} | {NAMES[a]} → {NAMES[b]} | {comparison['clusters']} | [{lo:+.2f}, {hi:+.2f}] |")
    text += ['',
             '## 진단 조건과 반복','',
             '아래는 결과를 보기 전에 고정한 서로 다른 70문항군입니다. 다른 페이지 원문과 현재 보기 원문을 직접 비교하는 범위는 이 표본에 한정됩니다. 전체 결과와 반복 seed를 합쳐 표본 수를 늘리지 않습니다.','',
             '| 경로 | seed | 조건 | 정답 / 응답 확정 | 정확도 | 미해결 | 품질 |','|---|---:|---|---:|---:|---:|---|']
    for backend,details in audit['backends'].items():
        for seed,conditions in details['pilot'].items():
            for c,m in conditions.items():text.append(f"| {backend} | {seed} | {NAMES[c]} | {m['correct']} / {m['resolved']} | {m['percent']:.2f}% | {m['total']-m['resolved']} | {'통과' if m['quality_valid'] else '기준 미달'} |")
    text += ['', '## 시험지별 전체 결과','', '| 경로 | 시험지 ID | 조건 | 정답 / 응답 확정 | 정확도 |','|---|---|---|---:|---:|']
    for backend,details in audit['backends'].items():
        for exam,conditions in details['exams'].items():
            for c,m in conditions.items():text.append(f"| {backend} | {EXAMS[exam]} ({exam}) | {NAMES[c]} | {m['correct']} / {m['resolved']} | {m['percent']:.2f}% |")
    text += ['', '시험지 ID와 객관식 범위는 [기존 공개 목록](evaluation/capture_inventory.json)을 참조하세요.','',
             '## 과목·선택과목별 배점 점수','',
             '고정 목록의 영어·세무사 1점은 정답 개수 단위였습니다. 아래는 [배점 구분과 보충 집계](SCORING_CLARIFICATION.md)를 적용한 별도 표입니다. 국어는 공통+선택 하나, 수학은 객관식만 공통+선택 하나를 합칩니다. 영어는 듣기를 제외한 63점 만점입니다. 세무사는 각 40문항 묶음의 100점 환산입니다. 다른 선택과목을 동시에 더하거나 빠진 듣기·단답형을 0점으로 더하지 않습니다. 미해결 문항이 있으면 모두 틀렸거나 모두 맞았다고 가정한 점수 범위를 표시합니다.','',
             '| 경로 | 시험지 / 응시 단위 | 만점 | 원본 | 동일 배치 대조군 | 현재 보기 | 미해결 수(원본/대조/보기) |',
             '|---|---|---:|---:|---:|---:|---|']
    for backend,units in audit['supplementary_subject_scores'].items():
        lookup={}
        for u in units:lookup.setdefault((u['exam'],u['unit']),{})[u['condition']]=u
        for (exam,unit),d in sorted(lookup.items()):
            conditions=[d[c] for c in ('original','layout_control','current_choices')]
            points=' | '.join(f"{v['possible_points_range'][0]:g}~{v['possible_points_range'][1]:g}" if v['unresolved'] else f"{v['points']:g}" for v in conditions)
            errors='/'.join(str(v['unresolved']) for v in conditions)
            text.append(f"| {backend} | {EXAMS[exam]} / {unit_label(exam,unit)} | {conditions[0]['max_points']:g} | {points} | {errors} |")
    text += ['',
             '## OCR이 실제로 읽은 표식 영역','',
             '| 조건 | OCR 쪽 수 | 바깥 테두리 단어/쪽 | 지문 테두리 단어/쪽 | 비풀이 명령 정확 인식 쪽 수 |',
             '|---|---:|---:|---:|---:|']
    for c,d in ocr['conditions'].items():
        text.append(f"| {NAMES[c]} | {d['pages']} | {d['regions']['border']['mean_tokens_per_page']:.1f} | {d['regions']['passage']['mean_tokens_per_page']:.1f} | {d['pages_with_exact_non_solving_phrase']} |")
    text += ['', 'OCR 단어의 위치가 해당 표식 영역과 50% 이상 겹칠 때 집계합니다. 작은 글자의 인식 실패와 지시 불이행을 구분하기 위한 기술 진단이며, 표식 단어 수만으로 점수 변화의 원인을 확정하지 않습니다. 현재 보기는 전체 쪽, 나머지는 진단 표본 쪽이므로 합계나 인식 비율을 직접 비교하면 안 됩니다. 명령의 정확 문자열 일치는 보수적인 기준입니다.','',
             '## 검증과 해석 한계','',
             '- 원시 최종 JSON을 추론 파서와 별도의 코드로 다시 채점했습니다. 설명 속 숫자는 답으로 추정하지 않았고 복수 정답을 적용했습니다. 배점 점수는 별도 구분한 표를 확인하세요.',
             f"- 캡처 {audit['capture_count']}개의 해시와 PDF·OCR 입력 해시, 고정 구현·계획 해시를 검사했습니다.",
             f"- {layout['total_pages']}쪽, QR {layout['total_qr']}개, 교체 지문 테두리 {layout['total_boxes']}개를 검사했습니다. 의도한 표식 영역 밖의 원본 크기 본문은 동일 배치 대조군과 픽셀 비교했습니다.",
             '- QR 해독 결과는 [전체 검증 JSON](evaluation/strict_qr.json)에 있습니다. 래스터 해독은 실제 카메라 판독이나 모델의 URL 방문을 뜻하지 않습니다.',
             '- 원본 정확도가 낮거나 한 번호로 답이 쏠리면 차단 성능의 근거로 삼을 수 없습니다. 응답 분포·거부·오류·과목별 점수를 함께 확인해야 합니다.',
             '- 공식 정답표에서 다섯 선택지가 모두 정답인 문항을 제외한 보조 정확도와 복수 정답을 반영한 균등 무작위 선택의 기대 정확도도 JSON에 제공합니다. 이 자료에서 무작위 선택 기대값을 무조건 20%로 고정하지 않습니다.',
             '- 알려진 시험지를 재사용한 실험이며 손대지 않은 외부 검증 세트가 아닙니다. 사람의 가독성·시험 점수·실제 AI 안경은 측정하지 않았습니다.',
             '- 원본·캡처·실제 QR 발급 정보는 로컬 보관합니다. 새 발급 토큰은 QR 무늬를 바꾸므로 공개 코드와 모델 seed만으로 바이트 단위 동일 재현을 보장하지 않습니다. 동일 실행의 조건 사이에서는 QR 토큰을 공유합니다.',
             '- 두 로컬 백엔드는 서로 다른 모델과 입력 경로입니다. 차이를 순수한 OCR 효과라고 해석하지 않습니다. temperature 0에서 seed 반복이 같은 답을 낼 수 있으며 독립 표본으로 취급하지 않습니다.',
             '- 테두리를 채우는 원문 길이가 달라 명령문 반복 횟수와 글자 밀도도 완전히 같지는 않습니다. C·D·E는 실제 생성 구성의 비교이며 선택지 의미만의 순수한 인과 효과를 분리한 실험은 아닙니다.',
             '- 상용 API 평가는 실행하지 않았습니다. LAN 접속·영구 CSV·재시작 복구는 별도의 기능 시험이며 IP만으로 개인 신원이나 부정행위를 확정하지 않습니다.','',
             '[사전 계획](STRICT_EXPERIMENT_PLAN.md) · [실행 방법](STRICT_RUN.md) · [독립 감사 및 신뢰구간](evaluation/strict_audit.json) · [문항별 정오](evaluation/strict_questions.json) · [QR 대시보드](QR_DASHBOARD.md)']
    report=ROOT/'docs/STRICT_RESULTS_2026-11-17.md';report.write_text('\n'.join(text)+'\n',encoding='utf8');print(report)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);export(p.parse_args().output.resolve())
