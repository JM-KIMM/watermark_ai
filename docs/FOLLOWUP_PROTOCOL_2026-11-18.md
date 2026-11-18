# 후속 실험: 생성 워터마크와 입력 방해의 구분

2026-11-18. 추론 실행 전에 조건, 표본, 선택 규칙을 고정한다. 탐색 연구이며 등록기관에 사전등록한 연구는 아니다. 앞선 시험의 문구나 점수를 숨기지 않고 별도 실행 폴더를 사용한다.

## 질문과 문헌 검토 범위

시험지를 이미지로 받는 Qwen2.5-VL 7B와 OCR→Qwen2.5 7B에서, 본문을 유지한 채 여백의 지시로 최종 정답률을 줄일 수 있는가? Google/DeepMind 공식 문서, Google Research, arXiv, CVF의 원문을 대상으로 2017–2026년 기술을 범위 검토했다. 검색은 2026-11-18, 영어 검색어를 사용했다. 검색 결과 수는 검색엔진의 전체 모집단이 아니므로 PRISMA 체계적 문헌고찰로 부르지 않는다.

검색어: `site.deepmind.google SynthID text watermark Nature token probability`; `site:research.google adversarial examples physical world eyeglasses typographic multimodal`; `visual prompt injection watermark exam multiple choice adversarial typography paper`; `site:research.google "Adversarial Patch"`; `site:arxiv.org "Typographic" "Multimodal" "prompt" attack 2025 2026`; `site:openaccess.thecvf.com SceneTAP 2025 typographic`.

| 원문 | 확인한 내용 | 이번 과제에의 적용 한계 |
|---|---|---|
| [Google SynthID](https://deepmind.google/models/synthid/) / [Dathathri et al., Nature 2024](https://www.nature.com/articles/s41586-024-08025-4) | 생성 과정에서 출처 식별 신호를 넣으며 텍스트는 토큰 선택에 관여 | 생성기를 통제하는 기술. 종이 여백으로 타인의 모델 logits를 직접 바꾸는 방법이 아니다. Nature 본문 직접 열기는 리디렉션 오류였고 공식 소개와 검색에서 확인한 초록 수준을 구분한다. |
| [Brown et al., Adversarial Patch, 2017](https://research.google/pubs/adversarial-patch/) | 다양한 변환을 견디는 표적 이미지 패치를 인쇄·촬영해 분류기를 오도 | 분류기 대상. LLM 객관식 점수 감소나 OCR 방해를 증명한 논문이 아니다. 이번 코드는 gradient 기반 패치 재현이 아니다. |
| [Cao et al., SceneTAP, CVPR 2025](https://openaccess.thecvf.com/content/CVPR2025/html/Cao_SceneTAP_Scene-Coherent_Typographic_Adversarial_Planner_against_Vision-Language_Models_in_Real-World_CVPR_2025_paper.html) | 내용·위치·장면 적합성을 고려한 typographic 공격; 물리 배치도 검사 | 이번에는 시험 안내라는 문맥과 명료한 표현만 가설에 반영한다. 논문의 agent/diffusion 최적화를 재현하지 않는다. 사람에게도 혼동을 줄 수 있다. |
| [Guo et al., 2025 preprint](https://arxiv.org/html/2508.13214v1) | 산술 PDF의 주입 공격과 추론·방어 지시를 함께 비교 | 본문은 screenshot을 제외한다고 명시한다. 흰색 숨은 텍스트 효과를 촬영 효과로 인용하지 않는다. 방어 지시에서 효과가 줄어드는 결과도 있다. |
| [Zhang et al., Render Before Reading, 2026 preprint](https://arxiv.org/abs/2609.36121) | 텍스트와 영상으로 전달된 지시의 효과 차이를 연구 | 초록 수준 검토. 이 연구의 방향은 방어이며 시험지 점수의 직접 근거가 아니다. 텍스트/영상 경로를 따로 검사하는 근거다. |
| [Li et al., AgentTypo, 2025 preprint](https://arxiv.org/abs/2510.04257) | 웹 이미지의 문구·배치 최적화 | 에이전트 웹 벤치마크로 시험 점수와 다르다. 이번에는 적응 최적화를 수행하지 않는다. |

동일 arXiv ID 및 동일 논문의 HTML/PDF는 하나로 묶었다. 언론·Reddit·2차 자동 요약, 이미지 생성 모델의 jailbreak 논문은 성능 근거에서 제외했다. 논문들의 공격 성공률을 합치거나 우리 모델에 대입하지 않는다.

## 고정 설계

새 합성 산술 40문항(seed 2026111802), 개발10/검증30. 각 집합에서 정답 위치 균등, 위치 순서는 고정 seed로 섞는다. 덧셈·뺄셈·곱셈을 섞으며 본문은 숫자 뒤 한국어 조사 OCR 오류를 피하도록 영어 ASCII로 렌더링한다. 이는 이전과 다른 자료이므로 이전 총점과 직접 비교하지 않는다. 원래 본문·보기 픽셀은 모든 조건에서 동일하다.

조건 O 원본, N 중립 문구, A 이전 화살표 순환, P 자연어 순환, E 시험 중 답안 제공 중단 안내. P/E는 이번의 새 후보이며 정답표를 문구 생성에 사용하지 않는다. 같은 자리·글꼴·색·줄 간격을 사용하지만 문구 길이까지 같지는 않다. 모든 조건은 실제로 그려지는 텍스트 그대로 공개한다. 사람이 무시할 수 있도록 AI 검사 전용 표시를 유지한다. 실제 시험에 적용하기 전 사람 대상 검사가 필요하다.

개발: 10×5조건×2경로(정확한 전사 텍스트→LLM, 이미지→VL)×2지시(일반/무시)=200응답. 새 후보 P/E 중 네 조합의 평균 정답 수가 낮은 하나를 선택하며 동률이면 P. 선택 JSON을 검증 전에 고정한다. 정확한 전사는 OCR 오류를 제거한 기전 대조이며 OCR 모델 실측치라고 부르지 않는다.

검증: 30×3조건(O/N/선정 후보)×3경로(전사, Tesseract, VL)×2지시=540응답. 총740. 최종 JSON을 파싱하며 정수/null 모두 허용, 보기 enum으로 후보 효과를 막지 않는다. null은 미응답, 파싱/서버 실패는 별도 집계한다. 온도0, seed2026111802, 문맥8192, 출력256, 최대3회 재시도. 모델 태그·실행 코드·계획 hash를 기록한다.

주 비교는 N→선정 후보의 정답 변화, 짝지은 bootstrap 10000, exact McNemar 및 여섯 검정 Holm 보정. 정답→오답, 오답→정답, null, 범위 밖 답, 원문 파싱 실패를 따로 공개한다. 여섯 조합 모두 10%p 감소 및 Holm p<.05가 되어야 실제 시험 확증 후보로 추천한다. 미달이어도 결과를 공개한다. 개발에서 가장 낮은 숫자만 성공으로 제시하지 않는다.

기존 영어 3회분84문항에도 선정 후보를 새로 적용한다: 같은 배치 대조/후보/후보+무시 × OCR/VL, 126요청=504문항 응답. 이전에 본 자료이므로 독립 검증이 아닌 탐색적 전이 검사다. 위·아래 20pt 띠에만 문구를 추가하고 띠 밖 픽셀 동일성을 확인한다. 두 경로의 주 비교에 문맥 중복 페이지 묶음 bootstrap/sign-flip 및 Holm을 사용한다. 합성 결과가 약해도 전이 검사를 생략하지 않는다.

카메라 실물 촬영, gradient 패치 최적화, 상용 모델, 사람 가독성 실험은 이번 실행 범위에 포함하지 않는다. 문구를 잘라내면 입력에서 사라지는 한계도 유지된다. 점수가 줄지 않으면 기본 생성기를 바꾸지 않는다.
