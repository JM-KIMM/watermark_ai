"""Publish compact, source-free score and validation artifacts for a completed run."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import argparse
from collections import Counter
import json
from audit_capture_results import audit

ROOT=Path(__file__).resolve().parent.parent
LABELS={'original':'원본','watermarked':'수정본','layout_control':'같은 배치·표식 없는 대조군'}


def export(out):
    checked=audit(out)
    score=json.loads((out/'scores.json').read_text(encoding='utf8'))
    rows=json.loads((out/'questions.json').read_text(encoding='utf8'))
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf8'))
    verification=json.loads((out/'layout_verification.json').read_text(encoding='utf8'))
    selected=[r for r in rows if not r['section'].startswith('even')
              and not (('상법' in r['exam'] or '행정소송법' in r['exam']) and int(r['question'])<=40)]
    score['repeated_form_and_tax_common_excluded']={c:dict(correct=sum(r[c+'_correct'] for r in selected),total=len(selected)) for c in LABELS}
    response_files=list((out/'responses').glob('*/*/*.json'))
    score['inference_seconds']={c:sum(json.loads(p.read_text(encoding='utf8'))['seconds'] for p in response_files if p.name.startswith(c+'-')) for c in LABELS}
    score['audit']=checked
    score['choice_distribution']={c:dict(Counter(str(r[c]) for r in rows if r[c] is not None)) for c in LABELS}
    dest=ROOT/'docs/evaluation';dest.mkdir(exist_ok=True)
    def write(name,v):
        (dest/name).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
    write('capture_scores.json',score);write('capture_questions.json',rows)
    write('capture_protocol.json',protocol);write('capture_verification.json',verification)
    write('capture_audit.json',checked)
    inventory=json.loads((out/'inventory.json').read_text(encoding='utf8'))
    write('capture_inventory.json',[{k:e[k] for k in ('id','source','source_sha256','status','sections','capture_input_sha256') if k in e} for e in inventory])
    if (out/'qr_decode_check.json').exists():write('capture_qr_check.json',json.loads((out/'qr_decode_check.json').read_text(encoding='utf8')))
    qr_all=json.loads((out/'qr_decode_all.json').read_text(encoding='utf8')) if (out/'qr_decode_all.json').exists() else None
    if qr_all:write('capture_qr_all.json',qr_all)
    original=score['scores']['original'];marked=score['scores']['watermarked'];control=score['scores']['layout_control']
    lines=['# 문제 끝 QR · 페이지 캡처 기반 로컬 비전 평가 (2026-11-16)','',
        f"**원본 {original['correct']}/554 → 수정본 {marked['correct']}/554. 같은 배치의 표식 없는 대조군은 {control['correct']}/554입니다.**",'',
        '정답 수 감소를 확인하지 못했습니다.' if marked['correct']>=original['correct'] else '이번 실행에서는 원본보다 수정본의 정답 수가 적었습니다. 배치 대조군 결과와 함께 해석해야 합니다.',
        '', '## 입력과 채점','',
        '- 보유 시험지 11종 중 객관식이 있는 7종 전체를 포함했습니다. 서술형 4종, 영어 듣기 1~17번, 수학 단답형은 평가에서 제외했습니다. 총 554문항 노출이며 반복형·공통 문항이 포함됩니다.',
        '- PDF 페이지를 150dpi PNG로 캡처하고 그 이미지 바이트를 로컬 Qwen2.5-VL 3B(Q4_K_M)에 직접 전달했습니다. OCR 결과나 PDF 추출 텍스트, 정답은 모델 프롬프트에 넣지 않았습니다. 실제 카메라 촬영·AI 안경 실측은 아닙니다.',
        '- 국어 공통 지문은 필요한 연속 페이지를 함께 제공합니다. 세 조건의 문항·문맥 페이지·프롬프트·seed 42·temperature 0·context 16384·최대 출력 1024 토큰을 동일하게 했고 순서를 순환했습니다. 이전 평가 응답은 재사용하지 않았습니다.',
        '- 대조군은 수정본과 페이지 크기·QR용 빈 행·본문 이동이 같지만 QR과 워터마크는 없습니다. 입력 이미지 크기와 배치 차이의 영향을 구분하기 위한 조건입니다. QR만·테두리만의 효과는 이번 실행에서 분리하지 않았습니다.',
        '- 공식 답안의 복수 정답을 허용하고, 응답 실패는 null로 보존해 별도 집계했습니다. 기존 비전 평가 코드의 영어 짝수형 44번 오기(④)를 공식 답안 이미지의 ③으로 수정했습니다. 과거 문서의 숫자는 당시 기록이며 이번 표와 섞지 않습니다.',
        '- 원시 응답의 마지막 JSON을 다시 읽어 정답 수를 독립적으로 재계산하고, 사용한 PNG의 SHA256·문맥 페이지·문항 매핑을 검증했습니다.',
        '', '## 전체 결과','', '| 조건 | 정답 수 / 객관식 수 | 정답률 | 추론 실패 |','|---|---:|---:|---:|']
    for c,label in LABELS.items():
        s=score['scores'][c];lines.append(f"| {label} | {s['correct']} / {s['total']} | {s['percent']:.2f}% | {s['inference_failures']} |")
    lines+=['','## 시험지별 결과','','| 시험지 | 문항 수 | 원본 정답 | 수정본 정답 | 배치 대조군 정답 |','|---|---:|---:|---:|---:|']
    for e in score['exams']:
        s=e['scores'];lines.append(f"| {e['exam']} | {s['original']['total']} | {s['original']['correct']} | {s['watermarked']['correct']} | {s['layout_control']['correct']} |")
    lines+=['','짝수형과 세무사 2교시의 반복 회계학 40문항을 제외한 보조 집계(357문항):','']
    for c,label in LABELS.items():lines.append(f"- {label}: {score['repeated_form_and_tax_common_excluded'][c]['correct']} / {len(selected)}")
    lines+=['','## 배치·내용 보존 검사','',
        f"- 시험지 전체 221쪽에 문제 끝 QR {verification['total_qr']}개를 넣었으며 평가 대상 554문항 모두에 대응하는 QR이 있습니다. 생성은 듣기·단답형에도 적용되지만 성능 채점에서 제외합니다.",
        f"- 지문 테두리 {verification['total_boxes']}개를 교체했습니다. 표 격자·독립 도형·글자와 충돌하는 테두리는 보존하며 PDF 처리 기록의 passage_box_audit에 이유를 남깁니다.",
        '- 동일 배치의 수정본과 대조군은 테두리·QR·안내·박스 교체 영역을 제외한 픽셀 차이가 221쪽 모두 0입니다.',
        '- 원본과 배치 대조군의 본문 비교에서는 국어·수학·영어가 픽셀 차이 0, 세무사는 PDF 글꼴 재렌더링 차이가 최대 17/255였습니다. 두 단으로 나뉘어 렌더링되는 상단 로고에는 별도 이미지 보간 차이가 있어 본문 검사에서 분리했습니다.',
        f"- QR 영역을 300dpi로 렌더링한 OpenCV 해독 점검: {qr_all['decoded']} / {qr_all['total']}개 정상 해독." if qr_all else '- QR의 300dpi 해독 점검은 각 시험지 처음·마지막 QR을 표본으로 사용합니다.',
        '- 캡처 평가의 비전 모델에는 별도 QR 해독기를 연결하지 않았습니다.',
        '- 문제 끝 QR 행 때문에 페이지 높이가 늘어납니다. 본문 자체 배율은 유지하지만 A4 맞춤 인쇄를 하면 축소됩니다.',
        '', '## 해석의 범위','',
        '소형 모델 하나의 1회 결과입니다. 기준선이 낮고 반복 문항도 있으므로 일반적인 부정행위 방지 성능으로 해석할 수 없습니다. AI 안경의 크롭·QR 가리기·실제 사진의 원근과 조명·사람의 풀이 시간은 이 실험에 포함하지 않았습니다. 현장 감독이 필요합니다.',
        '',
        f"원본 응답의 선택지 분포는 {score['choice_distribution']['original']}입니다. 특정 번호에 치우치는 응답은 낮은 기준선의 한 원인이며, 이를 채점 오류나 성공적인 차단으로 간주하지 않습니다.",
        '', '## 재현','', '동일 시험지 원본과 공식 답안 자료가 로컬에 필요합니다. 로컬 Ollama에 qwen2.5vl:3b가 설치되어 실행 중인 환경에서:', '', '```powershell',
        'python evaluation/capture_evaluation.py --output outputs/capture_eval_v9',
        'python evaluation/verify_capture_layout.py outputs/capture_eval_v9',
        'python evaluation/audit_capture_results.py outputs/capture_eval_v9',
        'python evaluation/export_capture_report.py outputs/capture_eval_v9','```','',
        'PNG 캡처와 원시 모델 응답은 로컬 outputs/capture_eval_v9에 보존합니다. GitHub에는 시험지·캡처·모델·접속 기록을 올리지 않고 문항별 정오표와 점수·프로토콜·검증 기록만 포함합니다.', '',
        '[점수](evaluation/capture_scores.json) · [문항별 정오표](evaluation/capture_questions.json) · [프로토콜](evaluation/capture_protocol.json) · [독립 채점 감사](evaluation/capture_audit.json)']
    report=ROOT/'docs/CAPTURE_RESULTS_2026-11-16.md';report.write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(report);return score


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args();export(args.output.resolve())
