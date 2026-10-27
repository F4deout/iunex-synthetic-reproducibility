# Simulator v2.3 Phase 1 method amendment 01

상태: **결과 확인 후 방법론 보정 사전등록·simulator/parameter/history 변경 없음**  
작성일: 2026-09-28

## 1. 보정 사유

초기 Phase 1에서 log-normal AFT는 검열자료를 처리했지만 관측범위 11.25–90분에 대해 예측 중앙값의 중앙값이 약 223분, 95백분위가 약 966분으로 나타났다. C-index는 상대적 순위를 나타낼 수 있었으나 절대시간 보정이 부적절했다. 또한 중단 비율이 약 7.5%여서 완료·중단 분류에 ROC-AUC와 Brier score만 사용하는 것은 불충분했다.

이 amendment는 결과를 좋게 만들기 위한 simulator 수정이 아니다. v2.3 generator, capacity/tolerance/recovery, workload grid, history feature 및 seed/split은 변경하지 않는다. 기존 AFT 결과는 보존하되 절대시간 결론에서 제외한다.

## 2. 완료·중단 분류 보완

- 기존 L2 logistic regression과 C grid 0.1/1/10을 유지한다.
- validation log loss로 C를 선택한다.
- test 지표: Brier score, log loss, ROC-AUC, average precision(PR-AUC), balanced accuracy, 예측 중단확률 평균, 실제 중단률 및 10-bin ECE.
- balanced-accuracy threshold는 validation에서 0.05–0.95, 0.05 간격 중 선택한다.
- train 중단률을 모든 test session에 부여하는 prevalence-only baseline의 Brier와 log loss를 함께 보고한다.

## 3. 검열시간 모델 교체

log-normal AFT를 최종 시간모델에서 제외하고 **5분 간격 이산시간 hazard logistic model**을 사용한다.

- 시간범위: 0–90분
- interval endpoint: 5, 10, …, 90분
- 중단 session: 관측 중단시간을 포함하는 interval에서 event=1
- 완료 session: 계획시간까지 event=0으로 제공하고 해당 시점에서 right-censored
- 각 interval 입력: 사전등록된 session 시작 전 observed feature + interval endpoint/90 + log(1+endpoint)/log(91)
- 현재/미래 post HR, 실제 수행시간, 완료 여부, target 및 latent는 session feature에서 금지한다.
- L2 logistic C grid 0.1/1/10, validation interval negative log likelihood로 선택한다.

## 4. 생존모델 평가

- session의 계획시간까지 누적한 predicted stop probability로 Brier, log loss, ROC-AUC 및 PR-AUC를 계산한다.
- Harrell C-index로 관측 가능한 순위 일치도를 계산한다.
- 0–90분 restricted mean survival time(RMST)을 산출한다. RMST는 90분을 넘지 않는다.
- 중단 session의 RMST 기반 MAE는 설명용 보조지표이며 개인별 실제 중단시간 정확도로 일반화하지 않는다.
- 완료 session 이후의 가상 중단시간을 정답으로 생성하지 않는다.

## 5. 보존되는 분석

- Ridge 상태점수 결과는 재계산하지 않고 기존 동결 결과를 유지한다.
- seed 110/220/330/440/550, k=0/1/3/5/10/20, subject split 72/24/24, 동일 evaluation session 및 train-only preprocessing을 유지한다.
- pooled, LOADED_MARCH, BODYWEIGHT_CIRCUIT을 분리한다.
- 기존 AFT artifact를 덮어쓰지 않고 `v23_phase1_methodfix`에 별도 저장한다.

## 6. 판정

다음이 모두 충족되어야 `METHOD_VALIDATED`다.

1. 모든 예측확률이 0–1이고 모든 RMST가 0–90분
2. 동일 k의 test session 일치
3. current/future/latent leakage 0
4. prevalence baseline 동시 보고
5. 5개 seed 전체 보고

성능이 개선되지 않아도 모델·feature·parameter를 변경하지 않는다.

