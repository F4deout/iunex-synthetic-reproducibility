# Simulator v2.3 Phase 1 prediction protocol

상태: **분석 사전등록·본 실험 미실행**  
작성일: 2026-09-28

## 1. 연구 질문

1. `RQ-S`: 개인의 과거 행군·순환운동 관측기록이 새로운 완료 세션의 합성 운동부담·피로·현재상태 점수에 추가 예측정보를 제공하는가?
2. `RQ-T`: 개인의 과거 관측기록이 고정 외부조건에서 합성 완료/중단 및 all-cause synthetic stopping time에 추가 예측정보를 제공하는가?

개인 이력이 성능을 개선한다고 전제하지 않는다.

## 2. 동결 조건

- v2.2와 v2.3 protocol, parameter, generator 및 initial dry run을 변경하지 않는다.
- `SIMULATOR_V23_EVALUATION_SUPPORT_AMENDMENT_01.md`의 8개 평가조건을 사용한다.
- final seed는 110, 220, 330, 440, 550이다.
- k는 0, 1, 3, 5, 10, 20이다.
- 결과에 따라 parameter, workload grid, history schema, target coupling 또는 reporting noise를 변경하지 않는다.

## 3. 자료 구성

- 개인별 calibration history는 기존 24개 행군·순환운동 calibration event만 사용한다.
- evaluation은 MS1–MS4 및 BS1–BS4다.
- 모든 k에서 동일 evaluation session을 사용한다.
- evaluation event끼리는 서로의 history가 되지 않는다.
- subject-level train/validation/test 72/24/24를 유지한다.

## 4. 입력 특징

### k=0 공통정보

- 활동 종류
- 계획 지속시간
- 행군: 속도, 체중 대비 하중, 경사
- 순환운동: work time, rest time, work density
- evaluation 전 회복간격
- 활동 전 관측 HR

### k>0 과거 관측정보

현재 event 이전 calibration 중 최근 k개와 동일 활동 최근 k개를 각각 요약한다.

- 기록 수, 완료율
- 실제/계획 수행시간 비율 평균·변동
- 실제로 중단된 경우에만 관측 중단시간 평균
- 활동 전·후 HR 평균
- HR 변화량 평균·변동
- 회복간격 평균
- 마지막 완료 여부와 실제/계획 수행시간 비율
- 과거 외부 운동조건 평균

true capacity, tolerance, reserve, recovery parameter, strain, debt 및 noiseless target은 금지한다. 과거 자기보고 target은 Phase 1 입력에서 제외한다.

## 5. 상태점수 분석

- 완료된 evaluation session만 사용한다.
- current actual duration, completion 및 post HR은 활동 후 상태점수 예측시점에 관측 가능한 정보로 입력한다.
- target: burden WEAK/BASE/STRONG, fatigue, condition.
- 모델: Ridge.
- alpha grid: 0.1, 1, 10.
- preprocessing은 train에만 fit하며 alpha는 validation MAE로 선택한다.
- 지표: ID-test MAE/RMSE/R², 5-seed mean±SD, t(4)=2.776 기반 기술적 95% CI, k=0 대비 paired MAE difference와 방향.

## 6. 완료·중단 분석

- prediction time은 evaluation 시작 전이다.
- current actual duration, completion, post HR 및 target은 입력에서 금지한다.
- 보조 endpoint로 완료/중단을 L2 logistic regression으로 평가한다.
- C grid는 0.1, 1, 10이며 validation log loss로 선택한다.
- 지표는 ID-test Brier score, log loss 및 ROC-AUC다.

## 7. 관측 중단시간과 right-censoring

- 중단 세션은 실제 합성 중단시간을 event time으로 사용한다.
- 완료 세션은 계획시간에서 right-censored로 처리한다.
- 모델은 L2-regularized log-normal AFT다.
- alpha grid는 0.1, 1, 10이며 validation censored negative log-likelihood로 선택한다.
- 지표는 censored test NLL과 Harrell concordance index다.
- 중단 세션만의 분 단위 MAE는 설명용 보조지표이며 전체 모집단의 시간오차로 해석하지 않는다.

## 8. 분석 단위

- pooled, LOADED_MARCH, BODYWEIGHT_CIRCUIT을 별도 보고한다.
- 서로 다른 활동의 절대 성능을 직접 우열 비교하지 않는다.
- k=0 대비 k의 paired effect는 동일 seed·동일 test session에서 계산한다.

## 9. 해석 제한

모든 endpoint는 합성 결과다. 실제 장병 수행능력, 안전한 검사절차, 생리적 한계 또는 실제 센서 정확도를 뜻하지 않는다. 45분·90분 조건은 합성 식별성 grid이며 사람에게 권고하는 protocol이 아니다.

