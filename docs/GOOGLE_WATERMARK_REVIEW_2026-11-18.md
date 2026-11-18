# Google 워터마크와 시험지 방해 연구의 차이

2026-11-18 범위 검토. [고정 실험 계획](FOLLOWUP_PROTOCOL_2026-11-18.md)의 검색 이후 발견한 논문은 이 보충 문서에 기록한다. 실행 중인 조건이나 선택 규칙을 바꾸지 않았다.

## 무엇을 통제하는가

| 기술 | 조작하는 곳 | 필요한 접근 | 촬영 시험지에 대한 근거 |
|---|---|---|---|
| Google SynthID-Text | 생성 시 토큰 선택 | 생성기·샘플러 | 출처 식별용. 외부 모델의 풀이 방해 기술로 바로 전용할 수 없음 |
| Google Adversarial Patch | 입력 이미지의 패치 | 표적/대리 모델과 최적화 | 분류기에 물리 공격 가능성을 보인 연구. 시험 풀이로의 전이는 별도 검증 필요 |
| Integrity Shield | PDF 파서가 읽는 비가시적 채널 | 시험지 PDF·스키마·일부 정답 정보 | 직접 PDF 업로드 조건. 숨은 텍스트가 인쇄·캡처에 남는 것은 아님 |
| 수동 가시 워터마크 | 페이지의 문자·위치·면적 | 입력 이미지만 | 일부 문서 이해 연구에서 저하. 모델·배치 의존 |
| AR-AWM | 글자 모양 영역 안의 최적화 픽셀 | 미분 가능한 시각 인코더 | Qwen2.5-VL 문서 작업에 직접 관련. 다른 모델·촬영·OCR 전이에 제약 |

[Google 공식 SynthID 설명](https://deepmind.google/models/synthid/)은 콘텐츠 생성 시 워터마크를 넣는다고 설명한다. [Nature 논문](https://www.nature.com/articles/s41586-024-08025-4)의 주제도 생성물 식별이다. 토큰 확률을 바꾼다는 표현만으로, 인쇄한 문구가 제3자 모델의 샘플러를 제어한다고 볼 수 없다. [Google Research의 Adversarial Patch](https://research.google/pubs/adversarial-patch/)는 다른 계열의 연구다.

## 더 직접적인 논문과 제한

1. **[Integrity Shield, EACL 2026 demo](https://aclanthology.org/2026.eacl-demo.29/)**. [공식 최종 PDF](https://aclanthology.org/2026.eacl-demo.29.pdf)까지 확인했다. 숨은 텍스트, CMap, 화면 밖 요소 등을 이용하는 PDF 파싱 경로의 연구다. 논문이 제시한 시험 단위 차단률은 문항별 정답률 감소와 다른 지표다. arXiv v1의 초록30/한계절10이라는 표본 서술 차이는 최종본에서30개 시험으로 정리되어 있다. 최종본 한계 절은 rasterization·PDF 변환·정화 도구에 대한 강건성을 평가하지 않았다고 명시한다. 그 수치를 우리 캡처 실험의 기대 효과로 사용하지 않는다. 워터마크와 답안의 일치도만으로 부정행위를 확정하지 않는다고 저자들도 명시한다.
2. **[How does Watermarking Affect Visual Language Models in Document Understanding?, 2025 preprint](https://arxiv.org/html/2504.01048v1)**. 분산 배치와 의미 있는 문자, 단순 기호·가림을 비교한다. 최대 36%는 원래 정확도에 대한 상대 감소율(PDR)로, 36%p 감소와 다르다. 평가의 워터마크 면적은 넓은 범위(10–80%)이고, 작은 시험지 테두리만의 효과로 옮겨 쓰면 안 된다. 사람 가독성도 우리 조건에서 별도 측정해야 한다.
3. **[Visually Legible but Adversarial / AR-AWM, 2026 preprint](https://arxiv.org/html/2610.15728v1)**. Qwen2.5-VL-7B의 시각 인코더에 대해 글자 모양 지지 영역 안의 픽셀을 최적화한다. 같은 영역의 단순 워터마크·무작위 교란보다 최적화된 교란이 강하다고 보고한다. 저자는 다른 모델로의 전이가 약하며, 별도 OCR 경로와 폐쇄 API는 검증 범위 밖이라고 명시한다. 정답이나 질문을 이용하지 않는 표현 교란이라는 점은 우리 목적과 관련 있지만, 검은 글씨를 더 많이 넣는 것과 같은 방법은 아니다. 이 논문의 gradient 최적화를 이번 실행에서 재현했다고 주장하지 않는다.

추가 검색어: `site:research.google watermark adversarial OCR text recognition`; `adversarial watermark prevent vision language models exam solving paper watermark`; `site:arxiv.org "watermark" "exam" "adversarial"`; `site:arxiv.org document protection OCR adversarial perturbations human readable`. 2차 요약 사이트에서 발견한 논문은 반드시 위 원문으로 다시 확인했다.

## 입력 채널 확인 실험

합성 PDF에 보이지 않는 텍스트(render mode 3)를 추가하고 원본과 200dpi 렌더링을 비교했다. PDF 텍스트 추출에는 추가 지시가 나타나지만 렌더링 픽셀 차이는 0, PNG hash와 OCR 결과도 동일했다. 이는 **한 종류의 숨은 텍스트가 캡처에서 사라짐**을 확인한 실험이며, Integrity Shield 전체의 성능 재현이나 공격이 아니다. 모델 호출 없이 입력 채널을 확인한 것이다.

[실측 JSON](evaluation/pdf_channel_probe_20261118.json), 재현: `python evaluation/pdf_channel_probe.py`.

## 이번 실행과 후속 방향

현재는 문장형 번호 순환과 시험 중 답안 중단 안내를 기존 화살표 방식과 비교한다. 전사 텍스트·OCR·멀티모달을 분리하여, 인식 문제인지 지시 이행 문제인지 검사한다. 이것은 비용이 낮은 블랙박스 가설 검사다.

더 강한 방법을 탐색하려면 모델별 시각 인코더 최적화가 문헌상 더 직접적인 후보다. 다만 같은 모양의 비최적화 워터마크·무작위 픽셀 대조군, 다른 모델, 이미지 축소·JPEG·실제 촬영, 사람 정답률을 함께 검사해야 한다. 현재 Ollama 양자화 추론 경로만으로 입력 gradient를 얻었다고 할 수 없으며, 재현에는 미분 가능한 체크포인트와 전처리 일치 검증이 필요하다. 이 준비가 없는 상태에서 임의의 노이즈를 AR-AWM 재현이라고 부르지 않는다.
