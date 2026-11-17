# 확률 변화와 무시 지시: 문헌 검토

2026-11-17 범위 탐색. arXiv·ACL·CVF/BMVC 1차 문헌 중심. 검색 문자열과 포함 기준은 [사전 계획](MECHANISM_PROTOCOL.md)에 기록했다. 아래는 원문 초록과 공식 설명에 근거한 방법 선택이며 체계적 전수 검색은 아니다.

| 연구 | 근거와 적용 | 이 프로젝트에서 입증하지 않는 것 |
|---|---|---|
| [Grad-CAM, Selvaraju et al., ICCV 2017 / IJCV 2019](https://arxiv.org/abs/1610.02391) | 목표 출력의 gradient를 합성곱 특징맵에 반영해 영역 중요도를 시각화한다. | 단순 커널 활성화가 지시 이행이나 의미 이해라는 증거는 아니다. |
| [Attention is not Explanation, Jain & Wallace, NAACL 2019](https://aclanthology.org/N19-1357/) | NLP 모델의 attention 가중치를 출력 설명과 바로 동일시하는 데 문제를 제기한다. | 모든 attention 분석이 무의미하다는 정리가 아니다. |
| [Attention is not not Explanation, Wiegreffe & Pinter, EMNLP 2019](https://aclanthology.org/D19-1002/) | 설명의 정의와 대조 실험에 따라 attention의 해석이 달라진다고 반박한다. | 히트맵만으로 인과성을 확정할 수 있다는 뜻도 아니다. |
| [RISE, Petsiuk et al., BMVC 2018](https://arxiv.org/abs/1806.07421) | 입력 마스킹과 출력 확률로 블랙박스 중요도를 추정한다. | 이번 고정 4×4 제거 실험은 RISE의 무작위 마스크 알고리즘 재현이 아니다. |
| [Qwen2.5-VL Technical Report, Bai et al., 2025, preprint](https://arxiv.org/abs/2502.13923) | 동적 해상도 ViT와 window attention 기반 영상 인코더다. | CNN 최종 합성곱층 Grad-CAM을 그대로 가져와 그 모델의 커널 주목도라고 부를 수 없다. |
| [Language models are not naysayers, Truong et al., *SEM 2023](https://aclanthology.org/2023.starsem-1.10/) | GPT 계열 등의 부정문 처리 한계를 여러 벤치마크에서 검사한다. | 한국어 시험지 테두리에 대한 무시 지시가 반드시 실패한다는 근거는 아니다. |
| [AgentTypo, Li et al., arXiv v2 2026-11-02, preprint](https://arxiv.org/abs/2510.04257v2) | 웹 에이전트의 시각적 텍스트 주입을 위치·색·문맥 조건에서 평가한다. | 그 공격 성공률은 우리 시험지의 정답률 감소량이 아니다. |

## 검증 가능한 주장

입력이 달라지면 다음 토큰 분포가 달라질 수 있다. 이는 가중치를 바꾸거나 원하는 확률을 직접 설정하는 것과 다르다. 의도한 방향의 변화인지는 정답 확률·유인 번호 확률·대조군과의 차이를 실제 측정해야 한다.

OCR은 문자를 출력하는 단계이고, 그 문자를 지시로 취급할지는 후속 LLM의 처리다. Tesseract는 자연어 `무시` 프롬프트를 받는 모델이 아니다. 따라서 OCR 문구 생존율과 LLM 무시 지시의 효과를 별도로 측정한다.

`코끼리를 상상하지 마`라는 비유는 가설을 만드는 데 유용하지만 측정 결과를 대신하지 않는다. 워터마크가 영상 인코더에 들어갔거나 attention을 받았다는 사실은 그 명령을 따랐다는 뜻이 아니다. 정답 토큰 확률이 바뀌어도 원인은 시각 혼잡·OCR 읽기 순서·지시 내용 등이 될 수 있다. 중립 문구와 영역 제거 대조군이 필요하다.

## 기존 확률 실험 해석 보완

[기존 56문항 결과](DISTRIBUTION_EXPERIMENT.md)는 A.X-4.0-Light+EasyOCR, 고정 답안 접두사 뒤의 **숫자 1~6에 조건부인** 확률이다. 정답 평균 0.242→0.035, 6번 평균 0.0005→0.806은 이 범위의 측정이며 어휘 전체의 정답 생성 확률 또는 모든 모델의 변화로 표현하면 과장이다. raw digit mass가 함께 있어도 `E[P(correct | digit)] × E[P(digit)]`로 원래 평균 확률을 복원하면 안 된다. 문항별로 곱해야 한다.

기존 `수험생은 무시`는 그림 속 표시다. 시스템 메시지에서 모델에게 명시적으로 무시하라고 한 조건과 다르다. 또한 엔트로피가 작아지면 분포가 한쪽으로 쏠린 것이지 모델이 덜/더 이해했다는 직접 증거는 아니다. 이번 분석은 이를 분리한다.

## 실행 인터페이스

[Ollama 공식 chat API](https://docs.ollama.com/api/chat)의 `logprobs`를 로컬에서 직접 확인했다. 현 서버는 top_logprobs 최대 20개다. 반환 확률의 나머지 질량을 사용해 목표 확률을 구간으로 기록하며, 없는 토큰을 0으로 확정하지 않는다. 이 API 측정은 내부 전체 logits 직접 덤프와 구별한다.
