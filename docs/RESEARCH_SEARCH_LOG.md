# 추가 분석법 검색·선정 기록

검색일 2026-11-17(KST). 범위 탐색이며 PRISMA 전수 검색이 아니다. 검색 엔진이 전체 결과 수를 고정 제공하지 않아 전체 hit 수·정량적 제외 흐름은 보고하지 않는다. 학회·저자·기관의 원문을 우선 사용했다. 블로그 해설은 방법론의 근거로 인용하지 않았다.

| 검색식/대상 | 채택한 1차 연구 | 선택 이유 | 적용 범위 |
|---|---|---|---|
| `site.aclanthology.org multiple choice language model evaluation answer order bias calibration` | Wang et al. 2024, first-token mismatch | 기존 첫 토큰 평가의 구성 타당성 | 명확한 최종 답안 재검사 |
| 같은 검색식 | Pezeshkpour & Hruschka 2024 | 보기 순서의 교란 가능성 | 고정 10문항 × 5개 순환 |
| `site.proceedings.mlr.press calibration modern neural networks Guo 2017` | Guo et al. 2017 | 확률과 정답의 불일치 | reliability diagram, ECE; temperature fitting은 수행하지 않음 |
| `site.arxiv.org sanity checks saliency maps Adebayo 2018` | Adebayo et al. 2018 | 시각화의 그럴듯함과 타당성을 구분 | 픽셀 동일 음성 대조; 내부 가중치 무작위화는 미실시 |
| `site.proceedings.neurips.cc remove and retrain ROAR evaluating feature importance 2019` | Hooker et al. 2019 | 입력 제거에 따른 분포 이동 | 한계 평가; 재학습 실험은 미실시 |
| `site.aclanthology.org prompt injection benchmark benchmark indirect prompt injection BIPIA` | Yi et al., KDD 2025 | 정보·지시 구분과 명시적 경계의 효과 | 시스템 무시 지시 대조 |
| `Holm simple sequentially rejective multiple test procedure 1979` | Holm 1979, DOI 10.2307/4615733 | 여러 경로 주 비교의 오류율 통제 | 두 cluster permutation p값의 Holm 보정 |

이전 턴에서 확인한 Grad-CAM, Qwen2.5-VL 보고서, Attention is/is not Explanation, RISE, 부정문 처리 연구도 최신 보고서에 연결했다. 동일 논문의 arXiv/학회판은 별도 연구로 중복 집계하지 않았다. BIPIA의 현재 arXiv v4가 KDD 2025 채택임을 확인하고 서지를 수정했다.

시험지 검색은 연구 논문 검색과 분리했다. 2023-09/2024-09/2025-06 영어 문제와 정답·해설을 확보했다. KICE CDN의 두 오래된 index 주소가 404여서 공개 미러와 EBS 원문을 사용했다. 문서 내부 제작기관·시험 학년도 및 정답을 확인했으며 상세 URL·해시는 [자료 목록](evaluation/external_validity.json)에 있다. 시험 원문을 재배포하지 않는다.

## 방법론을 적용했다고 말하는 기준

코드로 실행하고 수치·원시 자료·매개변수를 남긴 방법만 수행한 분석이라고 표현한다. 논문을 읽은 것만으로 Grad-CAM, RISE, ROAR, 모델 무작위화, 인간 대상 평가를 수행했다고 하지 않는다. 탐색적 자료에 대한 유의성, 재등록하지 않은 실행 중 수정, 전체 결과를 본 뒤 만든 후속 실험을 명시한다.
