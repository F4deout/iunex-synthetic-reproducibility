# Simulator v2.2-multi-activity 사전등록 프로토콜

상태: **설계·입력 스키마 사전등록; generator·예측 본 실험 미실행**  
작성일: 2026-09-28  
선행 설계: `SIMULATOR_V22_MULTI_ACTIVITY_DESIGN.md`

## 1. 보존 규칙

`simulator_v21_running.py`, v2.1 protocol·parameter·dataset·evaluation amendment, DEPLOYABLE/ORACLE 결과와 모든 artifact는 변경하지 않는다. v2.2 파일과 결과는 `v22_multi_activity` 이름 아래 별도 생성한다. 기존 러닝 결과를 3 km, 행군 또는 순환식 훈련 결과로 재명명하지 않는다.

## 2. 구현 단계

1. `SCHEMA`: 활동별 observed 입력과 금지 latent 검증. 현재 단계에서 구현 가능.
2. `SUPPORT_AUDIT`: 보유 자료에서 활동별 필수변수의 존재·단위·고유 ID·결측을 감사.
3. `PARAMETER_REGISTER`: 실제자료 보정값, 문헌 제한값, simulation assumption, UNKNOWN을 구분하고 hash로 잠금.
4. `GENERATOR_DRY_RUN`: 공통 상태와 세 activity adapter 구현 후 누수·재현성·분포 검사.
5. `PHASE_1`: dry run이 `EXPERIMENT_READY`일 때만 활동별 예측 실험.

현재 승인 범위는 1단계까지다. 2단계 감사 결과 없이 행군·순환식 target 식을 만들지 않는다.

## 3. 활동별 최소 관측변수

| 활동 | workload 배정 전 정보 | 세션 중·후 기록 | 필수 외부자료 |
|---|---|---|---|
| RUN | 독립 수행기록, 계획 거리/시간 또는 속도 | 실제 거리·시간, 완료/중단, 중단시간·사유, pre/post/recovery HR | 군 대상 3 km 기록은 `NEEDS_SOURCE` |
| LOADED_MARCH | 계획 거리·속도·시간, 군장 무게, 체중, 경사/지형 | 실제 거리·시간, 완료/중단·사유, pre/post/recovery HR | 군장 무게·지형·속도 결합자료 `NEEDS_SOURCE` |
| BODYWEIGHT_CIRCUIT | 종목 순서, 계획 반복·세트, work/rest time, 외부 중량 | 실제 반복·세트·시간, 수정/중단·사유, pre/post/recovery HR | 구조화된 세트·반복·휴식자료 `NEEDS_SOURCE` |

완료된 세션의 hypothetical limit는 생성하거나 predictor에 넣지 않는다. 중단시간은 실제로 관측된 경우에만 사용한다.

## 4. 공통 predictor 조건

- `k=0`에도 workload 배정 전에 이미 알려진 독립 기준기록을 제공한다.
- `k>0`에는 현재 세션 이전의 legitimate observed history만 추가한다.
- 현재 세션의 post/recovery 측정값은 사후 상태점수 예측에는 사용할 수 있으나, 수행 전 중단시간 예측에는 사용할 수 없다.
- target별 prediction time을 manifest에 기록한다.
- 활동종류를 feature로 명시한다. activity-specific 모델과 pooled 모델을 별도로 평가한다.
- subject ID는 split key일 뿐 predictor가 아니다.

## 5. endpoint와 평가

### E-A: 활동 후 상태점수

완료된 세션의 burden/fatigue/condition 0–10을 활동별로 평가한다. 같은 target 정의와 질문시점이 확인되지 않은 자료를 합치지 않는다. 주 지표는 MAE, 보조지표는 RMSE/R²다.

### E-B: 관측 수행결과

- RUN·LOADED_MARCH: 관측 중단시간과 완료/right-censoring.
- BODYWEIGHT_CIRCUIT: 완료율 또는 관측 중단시간. 두 endpoint를 하나로 합치지 않는다.

모두 중단이면 log-time 회귀를 사용할 수 있으나 완료 사례가 있으면 right-censoring을 처리하는 survival/AFT protocol을 별도 고정한다.

### 비교

- 활동 내부 `k=0/1/3/5/10/20` 비교
- 공통 이력 제거, 활동별 수행이력 제거, 생체반응 이력 제거 ablation
- activity-specific 대 pooled 모델 비교
- 서로 다른 활동·단위의 절대 MAE를 직접 우열 비교하지 않음

## 6. split과 누수 통제

- 합성 인원은 subject-level train/validation/ID-test `72/24/24`를 기본으로 한다.
- 원본 workout이 있으면 `source_template_id` group split을 적용한다.
- 동일 개인·세션·원본 template의 fold 교집합은 0이어야 한다.
- preprocessing은 train에만 fit하고 model/alpha 선택은 validation에만 의존한다.
- ID-test는 최종 평가 전에 사용하지 않는다.
- workload assignment가 true capacity·reserve의 deterministic proxy인지 활동별 algebraic audit를 수행한다.
- `target shuffle`, `feature shuffle`, `quality-only`, mean baseline을 보조 감사로 사용한다.

## 7. 활동별 금지된 확대해석

- RUN 결과를 행군·근력·군 임무 전반의 결과로 표현하지 않음.
- 군장 행군의 대사비용 예측식을 실제 장병 상태점수의 정답으로 사용하지 않음.
- 순환식 훈련의 반복 횟수를 활동 간 공통 생리부하로 직접 환산하지 않음.
- 평균 HR가 비슷하다는 이유로 서로 다른 활동의 부담을 같다고 보지 않음.
- 합성 결과를 실제 장병·실제 센서·안전한 운동검사 성능으로 표현하지 않음.

## 8. 구현 전 parameter 분류

각 parameter는 다음 중 하나로만 등록한다.

1. `EMPIRICAL_REFERENCE`: 현재 실제자료의 지원범위를 보여 주는 값. 군 모집단 추정치가 아님.
2. `LITERATURE_CONSTRAINED`: 방향·단위·범위를 제한할 수 있으나 현재 인원의 값은 아님.
3. `SIMULATION_ASSUMPTION`: 결과 전 LOW/BASE/HIGH 또는 고정값으로 잠그고 전 조건 보고.
4. `UNKNOWN/NEEDS_SOURCE`: 입력 또는 식에서 몰래 기본값을 만들지 않음.

특히 행군의 load×speed×grade 결합, 순환식 종목별 부하, 활동 간 공통 회복전이, 자기보고 coupling/noise는 결과를 원하는 방향으로 정하지 않는다.

## 9. 구현 전 검증 기준

다음을 모두 충족해야 generator 구현 `PASS`다.

- 각 활동의 필수 observed 입력과 단위 확정
- 활동별 target 정의와 관측시점 확정
- 행군·순환식 parameter register 잠금
- latent 접근 0 assertion
- 동일 seed/config 재현 규칙
- 활동별 counterfactual 정의
- completion/censoring 처리
- sensor/target measurement process 구분
- 기존 v2.1 hash 불변 확인

현재 판정은 **`SCHEMA_PASS / GENERATOR_STOP`**이다. 입력 스키마는 구현할 수 있으나 행군과 순환식 훈련의 생성계수·개인차·정답과 측정과정이 잠기지 않아 generator와 본 실험은 시작하지 않는다.

## 10. 다음 자료 수집의 최소 단위

- 공통: 익명 개인 ID, 시각, 활동 전·후·회복 생체정보, 측정품질, 날씨, 자기보고 질문문과 시점
- RUN: 3 km 또는 독립 거리기록, 거리, 실제시간, 완료/중단·사유
- LOADED_MARCH: 체중, 군장 무게, 거리, 속도, 경사/지형, 실제시간, 완료/중단·사유
- BODYWEIGHT_CIRCUIT: 종목, 계획/실제 반복과 세트, 작업/휴식시간, 외부중량, 수정/중단·사유

이 프로토콜의 변경은 원문 덮어쓰기가 아니라 dated amendment로만 기록한다.

