# 보기 원문 구성의 캡처 평가 실행

실험 가설·조건·제외 기준은 [고정 실험계획](STRICT_EXPERIMENT_PLAN.md)을 먼저 확인하세요. 과거 결과에 맞춰 조건을 고르는 평가가 아닙니다. 원본 시험지와 모델은 저장소에 포함하지 않습니다.

## 환경

- Python 개발 의존성: `python -m pip install -r requirements-dev.txt`
- 로컬 Ollama 서버: `http://127.0.0.1:11434`
- `ollama pull qwen2.5vl:7b` 및 `ollama pull qwen2.5:7b`
- Tesseract 5.5, `kor`·`eng` 언어 자료. 기본 실행 파일 경로는 `C:/Program Files/Tesseract-OCR/tesseract.exe`이며 `TESSERACT_EXE`로 변경할 수 있습니다.
- `docs/evaluation/capture_inventory.json`에 기록된 원본 PDF를 같은 상대 경로에 준비합니다. SHA-256이 다르면 중단합니다.

웹 앱을 켜 두면 실험용 발급 QR도 같은 LAN 수집기에서 응답합니다. 실험용 발급 대상은 `EXPERIMENT`로 구분합니다. 모델 클라이언트 자체에는 URL 접속 도구가 없으므로 모델 실행만으로 QR 방문이 발생하지 않습니다.

## 실행과 재개

```powershell
python evaluation/strict_evaluation.py --output outputs/strict_eval_v2 --stage all
python evaluation/verify_strict_qr.py outputs/strict_eval_v2
python evaluation/analyze_strict_ocr.py outputs/strict_eval_v2
python evaluation/audit_strict_evaluation.py outputs/strict_eval_v2
python evaluation/export_strict_report.py outputs/strict_eval_v2
```

`all`은 PDF 준비, PNG 캡처, 실제 OCR, 비전 모델, OCR+LLM 순서로 실행합니다. OCR 작업은 비전 추론과 겹쳐 진행합니다. 추론 응답은 한 요청씩 원자적으로 저장합니다. 중단 후 같은 명령으로 재개하면 이미 완료된 추론을 재사용합니다. 코드를 수정하거나 모델·프롬프트·계획을 변경한 경우 기존 실험 디렉터리를 재사용할 수 없습니다. 새 출력 디렉터리를 지정하세요.

원본·동일 배치 대조군·현재 보기 구성은 554문항 전체를 평가합니다. 추가 조건과 반복 seed는 사전 고정한 70개 문항군의 진단 분석에 사용합니다. 같은 페이지 묶음의 기존 응답을 재사용하므로 진단 표본을 따로 다시 풀어 전체 결과와 섞지 않습니다. 현재 계획은 백엔드당 1,207개 페이지 묶음 요청이며, 요청 실패 시 동일 요청을 최대 세 번 시도합니다.

## 검증과 출력

| 파일 | 의미 |
|---|---|
| `plan.json` | 모델 digest·OCR 자료·설정·구현·계획 해시 |
| `input_seal.json` | 생성 PDF와 캡처 이미지 해시 |
| `layout_verification.json` | QR 위치와 워터마크 영역 밖 픽셀 보존 검사 |
| `responses/` | 조건·seed별 원시 응답, 상태, 최종 답, 입력 해시 |
| `ocr/` | 실제 OCR 원문·TSV와 원문 해시 |
| `vision_scores.json`, `ocr_llm_scores.json` | 백엔드별 전체·과목·진단 표본 점수 |
| `qr_verification.json` | 전체 URL QR의 200·300dpi 래스터 해독. HTTP 방문은 하지 않음 |
| `independent_audit.json` | 원시 최종 답 독립 재채점, 입력 해시 검증, 문항군 단위 신뢰구간 |

채점 오류·출력 오류·통신 오류·무응답을 구분합니다. 독립 재채점은 추론 클라이언트의 파서를 재사용하지 않습니다. 답변 설명의 숫자를 정답으로 추정하지 않습니다. 원본 정확도가 낮거나 특정 번호로 응답이 쏠리면 차단 성능을 입증한 것으로 해석하지 마세요. 전체 554회 노출과 중복을 묶은 357문항군을 구분합니다.

상용 API는 별도 연결 대상으로 남아 있습니다. `strict_model_client.py`의 HTTPS Chat Completions 어댑터는 있지만, 현재 실행 드라이버는 두 로컬 백엔드만 실행합니다. 키가 없거나 상용 호출을 실행하지 않은 상태를 상용 모델 결과로 기록하지 않습니다.

`outputs/` 전체와 `data/`에는 원본 내용·캡처·실제 QR URL·IP 등이 있을 수 있습니다. 공개 저장소에는 원문과 접속 정보를 제외한 요약·검증 결과만 선별해 올립니다.
