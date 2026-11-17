"""Export verified numerical evidence, without exams or private access records."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repository root
import json
from pathlib import Path
import shutil
from collections import Counter
from corpus_evaluation import OUT,ASSETS,ROOT


def main():
    scores=json.loads((OUT/'scores.json').read_text(encoding='utf-8'))
    verified=json.loads((OUT/'verification.json').read_text(encoding='utf-8'))
    questions=json.loads((OUT/'questions.json').read_text(encoding='utf-8'))
    inventory=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))
    protocol=json.loads((OUT/'protocol.json').read_text(encoding='utf-8'))
    assert len(scores['exams'])==7 and scores['total_exposures']==554 and len(questions)==554
    assert len({(r['exam'],r['section'],r['question']) for r in questions})==554
    assert verified['status']=='grading_passed' and verified['totals']==scores['totals']
    dest=ROOT/'docs/evaluation';dest.mkdir(parents=True,exist_ok=True)
    for source,target in [('scores.json','corpus_scores.json'),('questions.json','corpus_questions.json'),
                          ('inventory.json','corpus_inventory.json'),('protocol.json','corpus_protocol.json'),('verification.json','corpus_verification.json')]:
        shutil.copy2(OUT/source,dest/target)
    lines=['# 전체 객관식 시험지 실측 — 2026-11-16','',
        '보유 PDF 11개를 조사하고 객관식이 있는 7개 파일을 전부 평가했다. 서술형 4개 파일, 수학 단답형, 영어 듣기 1~17번은 제외했다.',
        '수능 홀수·짝수형과 모든 선택과목을 구분해 평가했다. 아래 %는 선택된 객관식 정답률이며 공식 시험 전체 원점수·표준점수·등급이 아니다.','',
        '| 시험지 | 문항 노출 수 | 원본 정답 | 2단계 정답 |',
        '|---|---:|---:|---:|']
    for exam in scores['exams']:
        n=exam['total'];cells=[f"{exam[c]['correct']}/{n} ({exam[c]['accuracy']:.2f}%)" for c in ('original','level2')]
        lines.append('| '+exam['exam']+' | '+str(n)+' | '+' | '.join(cells)+' |')
    totals=scores['totals']
    lines+=['| **합계** | **554** | '+' | '.join(f"**{totals[c]}/554 ({100*totals[c]/554:.2f}%)**" for c in ('original','level2'))+' |','',
        '**554는 독립적인 고유 문항 수가 아닌 파일·형별 노출 수다.** 세무사 2교시 3파일에 공통 회계학개론 40문항이 반복되고 수능 홀수·짝수형도 내용을 공유한다. 이 합계로 독립 표본 유의성이나 일반화된 차단 효과를 주장하지 않는다.','',
        '## 입력','',
        'Qwen2.5-VL 3B Q4_K_M 로컬 모델, 150dpi PDF 이미지, temperature 0, seed 42, 문맥 16384, 출력 상한 1024, 1~5 선택지 JSON schema를 사용했다. 수식·분수·지수·도형은 원본 렌더링으로 입력했으며 깨진 PDF 추출 문자를 수식 대신 제공하지 않았다. 국어는 공유 지문 페이지를 양쪽 조건에 동일하게 추가했다.',
        '워터마크는 원본 글자 모양 재사용, 6pt, 농도 0.45, 크기 ±25%, 테두리 20pt, QR 36pt다. QR은 CLI 기본값이며 웹 초기값 40pt와 구분한다.','',
        '## 검산과 한계','',
        f"- 본문·수식 렌더링: 의도적 QR 영역을 제외한 {verified['body_page_condition_checks']}개 페이지×조건을 비교했다. 채널 최대 차이 2 또는 평균 차이 0.001이라는 엄격한 기준에서 벗어난 조건은 {len(verified['render_strict_limit_flags'])}개다. 원본과 완전한 픽셀 일치를 주장하지 않으며 위치·최대·평균 차이를 검산 JSON에 공개한다.",
        '- 객관식 554노출 건의 유효 원문 JSON을 다시 파싱하고, 유효 답안이 없는 경우는 추론 실패 상태로 구분해 번호·문항 집합·정답·합계를 독립 검산했다. 임의의 답을 생성하지 않았다.',
        '- 24개 자동 테스트 통과. 전체 범위 매핑, 듣기·단답형 제외, 국어 지문 컨텍스트, QR 안내의 본문 비중첩 검사를 포함한다.',
        '- 작은 모델의 원본 풀이 능력, 강제 JSON 출력, 고정 조건 순서, 반복·워밍업 통제 부재가 한계다. 정답률 변화의 원인을 워터마크 지시 수행으로 단정하지 않는다.',
        '- 초기 한 시험지 결과와 이번 결과는 프롬프트·컨텍스트·출력 상한 등이 달라 직접 합산하지 않는다. 소요 시간은 캐시의 영향이 있어 우열을 주장하지 않는다.','',
        '### 원본 모델의 선택지 분포','',
        '원본 응답의 번호 편향도 함께 공개한다. 편향 자체가 채점 오류를 뜻하지는 않으며 모델의 시험 풀이 품질을 진단하는 자료다.','',
        '| 선택지 | 원본 응답 수 |','|---|---:|']
    frequencies=Counter(str(r['original']) for r in questions)
    lines += [f'| {i} | {frequencies[str(i)]} |' for i in range(1,6)]
    lines+=['','## 공개 근거','',
        '- [전체 문항별 정답·모델 답·정오 JSON](evaluation/corpus_questions.json)',
        '- [시험지별 집계 JSON](evaluation/corpus_scores.json)',
        '- [입력 파일 해시·제외 목록·선택과목·정답 매핑](evaluation/corpus_inventory.json)',
        '- [모델 digest·실행 조건](evaluation/corpus_protocol.json)',
        '- [독립 검산 결과](evaluation/corpus_verification.json)',
        '- [평가 범위·공식 정답 출처·재현 방법](CORPUS_EVALUATION.md)','',
        f'원본 시험지·지문·생성 PDF·모델 파일·IP 및 사건 기록은 공개 저장소에 포함하지 않는다. 원문 응답·생성물은 로컬 `outputs/{OUT.name}`와 `outputs/{ASSETS.name}`에 보존한다.','']
    if protocol.get('version')==6:
        lines+=['## QR 안내 배치','', '| 시험지 | 안내 배치 | 공간 부족 생략 |','|---|---:|---:|']
        for exam in inventory:
            if exam['status']!='included':continue
            m=json.loads((ASSETS/exam['id']/'level2.manifest.json').read_text(encoding='utf-8'))
            marks=[q for p in m['pages'] for q in p['question_marks'] if q['qr_status']=='placed']
            placed=sum(q.get('label_status')=='placed' for q in marks)
            lines.append(f"| {exam['source']} | {placed}/{len(marks)} | {len(marks)-placed} |")
        lines+=['','## 유효 응답과 추론 실패','',
            '서버가 빈 응답·잘못된 출력 문법을 반환하면 동일 설정으로 제한적으로 재시도하고 실패 원문을 보존했다. 숫자 문자열은 같은 선택지 숫자로만 정규화한다. 끝내 유효 응답이 없으면 선택지를 만들지 않고 미응답·추론 실패로 기록한다. 전체 문항 기준 정답률에서는 정답으로 인정하지 않으며, 학업적 오답과 구분한다. 일부 진단 요청에서 반복 토큰 한도에 의한 예측 중단도 관찰했다. 이를 워터마크의 인과 효과로 확정하지 않는다.','',
            '| 시험지 | 원본 실패 | 2단계 실패 |','|---|---:|---:|']
        for exam in scores['exams']:
            lines.append('| '+exam['exam']+' | '+' | '.join(str(exam[c].get('inference_failures',0)) for c in ('original','level2'))+' |')
    (ROOT/'docs/CORPUS_RESULTS_2026-11-16.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Exported verified numerical report only.')


if __name__=='__main__':main()
