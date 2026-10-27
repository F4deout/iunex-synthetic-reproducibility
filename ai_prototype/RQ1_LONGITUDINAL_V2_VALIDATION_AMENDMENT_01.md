# RQ1 longitudinal v2 validation amendment 01

## 변경 이유

최초 dry-run 검증기는 사전등록된 trivial-recoverability 판정과 다르게 과거 자기보고 target 요약치를 observed model에 포함하고, 결정론적 latent oracle 대신 학습형 latent Ridge를 사용했으며, noise-free 검사에서 개인별 reporting bias까지 제거하였다. 이로 인해 generator의 직접 자기회수와 과거 자기보고를 통한 보고성향 복원이 구분되지 않았다.

## 변경 범위

시뮬레이터 수식, 고정 parameter, 자료분할, history 생성, target 정의는 변경하지 않는다. 최초 검증 파일과 결과도 보존한다. 다음 검증 정의만 교정한다.

1. Legacy trivial-recoverability observed model은 현재 관측값과 과거 관측 생체·맥락 정보만 사용하며 과거 target/self-report를 제외한다.
2. Latent oracle은 학습모형이 아니라 생성기의 noiseless target과 개인 reporting bias를 결합한 사전 정의 조건부 평균으로 계산한다.
3. Noise-free 검사는 session reporting noise만 제외하고 개인 reporting bias는 유지한다.
4. 과거 자기보고를 포함한 full-history model은 별도 정보경로 분석으로 보고하며 trivial-recoverability 비율에 사용하지 않는다.
5. Target/feature shuffle은 실제 최종 full-history predictor가 실패해야 할 때 실패하는지를 확인하는 반증시험으로 유지한다.

## 판정 원칙

- 위 변경은 결과를 개선하기 위한 generator·parameter tuning이 아닌 검증방법 교정임.
- 과거 자기보고에 따른 개선은 reporting-style personalization으로 해석하며 생리상태 개인화의 증거로 사용하지 않음.
- Core validation에 코드 또는 방법 문제가 없으면 본 실험 진행 가능으로 판정하되, 정보경로 제한을 결과에 명시함.

