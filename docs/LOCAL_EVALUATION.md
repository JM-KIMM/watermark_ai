# 로컬 모델 실측과 연구 설계

실험 대상: 2026년 제63회 세무사 1차 1교시 A형, 32쪽·80문항. 1~40은 재정학, 41~80은 세법학개론이다. 주관식 시험은 채점 기준과 독립적인 평가자가 추가로 필요하므로 이번 객관식 실험과 섞지 않는다.

공식 정답: [Q-Net 최종 정답](https://www.q-net.or.kr/cst003.do?artlSeq=5272129&boardId=Q004&gId=22&gSite=L&id=cst00302&menuType=cst00310). 공식 PDF를 `outputs/official_answers.pdf`로 내려받고 첫 페이지 표를 직접 확인해 입력했다. 14번은 3·5 복수 정답, 53번은 전항 정답이다. 정답은 모델 프롬프트에 넣지 않는다.

## 실행

독립 실행형 Ollama는 `outputs/runtime/ollama`에 있다. 서버는 `127.0.0.1:11434`만 사용한다. 모델은 `qwen2.5vl:3b`이며 실제 모델 digest와 양자화 정보는 각 실험 폴더의 `experiment.json`에 기록한다. 모델 파일은 Ollama 기본 저장 위치인 사용자 폴더 `.ollama/models`에 저장된다.

```powershell
outputs/runtime/ollama/ollama.exe serve
outputs/runtime/ollama/ollama.exe pull qwen2.5vl:3b
.venv/Scripts/python.exe evaluation/prepare_benchmark.py
$examSource = Get-Content -Encoding UTF8 outputs/benchmark_input/source_path.txt
.venv/Scripts/python.exe evaluation/benchmark_local.py --source "$examSource" --marked outputs/benchmark_input/level2.pdf --key outputs/benchmark_input/key.json --model qwen2.5vl:3b --output outputs/eval_level2
```

3단계(구분선 무늬)는 2026-11-17에 삭제해 더 이상 생성하지 않는다. `--limit 2`는 앞 2쪽 예비 실험이며 전체 시험 점수와 구분한다.

페이지별로 원본과 처리본을 각각 새 대화에 입력한다. 동일한 150dpi, temperature 0, seed 42, 문맥 길이 8192, 출력 상한 2048을 적용한다. 쪽마다 먼저 처리하는 조건을 교대한다. 각 응답·소요 시간·출력 토큰 수를 별도 JSON으로 저장해 중단 후 이어서 실행한다. 파일·정답·모델·옵션이 바뀌면 새 폴더를 사용해야 한다.

`scores.json`은 정답 수, 응답 수, 전체 문항 수, 100점 환산 점수, 처리본−원본 점수 차이를 기록한다. 미응답과 형식 오류는 오답으로 센다. 모델 오류나 HTTP 실패는 실행을 중단하고, 실제 응답 없는 가짜 점수를 생성하지 않는다. 동일 시드도 GPU의 완전한 결정성을 보장하지 않는다.

## 해석과 다음 단계

현재 구현은 JSON schema로 선택지 정수만 허용한다. 따라서 이 실험은 구조화된 응답을 사용하는 풀이 모델의 정답률 비교이며, 출력 언어 변경 성공률을 측정하는 실험이 아니다. 초기 `outputs/eval_level2`는 형식 진단용 중단 기록이다. 최종 점수는 `outputs/eval_level2_v2`, `outputs/eval_level3_v2`, `outputs/eval_blank_border_v2`만 사용한다. 캐시와 워밍업을 통제하지 않았으므로 소요 시간을 조건 간 성능 지표로 비교하지 않는다.

- 한 모델의 한 시험 결과는 일반적 방어 성능이 아니다. 특히 소형 모델의 원본 점수가 낮으면 추가 하락 여지가 작아지는 바닥 효과가 있다.
- 모델이 내부적으로 이미지를 축소하므로 150dpi 입력이 그대로 처리된다고 가정하지 않는다. 테두리 추가에 따른 본문 축소 효과와 명령 문구 효과를 분리하려면 같은 크기의 빈 테두리 대조군도 필요하다.
- 다음 실험은 원본, QR만, 빈 테두리, QR+문구, QR+문구+선의 요소별 비교다. 이때 모델·시드·시험·채점표를 고정한다.
- 전체 이미지, 테두리 크롭, 문제별 크롭, PDF 텍스트 추출을 별도 입력 경로로 비교한다. 텍스트 추출 결과를 이용한 실험을 시각 OCR 실험이라고 부르지 않는다.
- 최소 세 시드와 두 개 이상의 모델에서 반복하고 문항별 정오 변화, 신뢰구간, 사람의 가독성과 필기 시간을 확인한다.
- QR 접속 서버를 쓰지 않는 실험이므로 QR 읽기/외부 URL 방문 여부는 이번 정답률 결과로 추정할 수 없다.

## 논문을 반영한 개선 방향

1. [OCRBench (2023, 2024 개정)](https://arxiv.org/abs/2305.07895): 문자 인식, 문서 질의응답, 수식 인식 등 다른 능력을 구분한다. 우리 실험도 QR 디코딩률, 본문 OCR 문자 오류율, 최종 시험 정답률을 분리한다.
2. [OCRBench v2, NeurIPS 2025](https://papers.nips.cc/paper_files/paper/2025/hash/8c2e6bb15be1894b8fb4e0f9bcad1739-Abstract-Datasets_and_Benchmarks_Track.html): 위치·배치·복합 요소·추론을 포함해 평가한다. 우리 시험지의 표, 그래프, 수식, 한국어 장문을 층별로 평가하는 근거가 된다. 해당 벤치마크 점수를 이 시험지의 성능으로 옮겨 쓰지 않는다.
3. [VisInject (2026 preprint)](https://arxiv.org/abs/2605.01449): 출력에 영향을 준 현상과 목표 지시가 실제로 수행된 현상을 구분한다. 베트남어 출력 여부와 정답률 하락을 각각 집계해야 한다.
4. [MMPIBench (2026 preprint)](https://arxiv.org/abs/2609.09404): QR을 포함한 시각적 전달 수단에서 인지, 계획, 실행을 구분한다. QR이 복원됐다고 AI가 주소에 방문하거나 명령을 따랐다고 판단하면 안 된다.

위 연구는 실험 설계의 근거다. 우리 워터마크가 효과 있다는 실증 근거는 별도로 생성한 실제 모델 응답과 공식 채점 결과다.
