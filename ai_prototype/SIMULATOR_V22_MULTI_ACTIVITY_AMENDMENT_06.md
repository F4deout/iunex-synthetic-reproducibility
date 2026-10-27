# Simulator v2.2 Amendment 06 — 반복 자기보고 보정 후속평가

상태: **결과 확인 전 사전 고정**  
작성일: 2026-09-28  
성격: 기존 Phase 1을 대체하지 않는 후속 분석

## 1. 연구 질문

현재 세션보다 앞서 수집된 동일 문항의 반복 자기보고가 개인별 응답 기준을 보정하여, 군장행군·맨몸 순환운동의 새로운 완료 세션 상태점수 예측에 추가 정보를 제공하는가.

## 2. 보존 규칙

- v2.2 generator·parameter·target 식·noise·workload grid를 변경하지 않는다.
- 기존 Phase 1과 원인감사 결과를 덮어쓰지 않는다.
- seed `110, 220, 330, 440, 550`, subject split `72/24/24`, 완료 평가 세션과 Ridge alpha grid를 유지한다.
- 현재 또는 미래 evaluation target은 predictor에 사용하지 않는다.

## 3. 보정에 허용하는 정보

각 target은 같은 target의 과거 calibration 응답만 사용한다. 예를 들어 fatigue 보정에는 과거 fatigue만 사용하며 burden이나 condition 정답을 섞지 않는다.

`k=1,3,5,10,20`에서 다음을 계산한다.

- common history: 가장 가까운 과거 calibration k건의 응답 수·평균·표준편차·최근값·workload-cell 보정 평균잔차
- activity-specific history: 현재 활동과 같은 과거 calibration k건의 응답 수·평균·표준편차·최근값·workload-cell 보정 평균잔차

`k=0`에는 자기보고 보정 특징을 넣지 않는다.

## 4. workload-cell 보정과 누수 방지

- event code별 기준평균은 train subject의 calibration target에서만 계산한다.
- validation·ID-test subject의 잔차는 train 기준평균과의 차이로 계산한다.
- train subject의 잔차는 해당 subject를 제외한 train subject 평균을 사용한다.
- 완료 evaluation target과 evaluation event 평균은 기준평균 계산에 사용하지 않는다.
- 과거 calibration 응답이 없는 완료 세션의 가상 응답을 만들지 않는다.

이 잔차는 동일하게 배정된 calibration workload에서 개인이 평균보다 높거나 낮게 응답하는 경향을 나타내는 감사용 보정 특징이다. 실제 임상 척도의 안정된 개인편향으로 간주하지 않는다.

## 5. 비교 조건

- 기존 `k=0`: 현재 세션 observed 입력만 사용
- 기존 `k=20`: 수행·HR history만 사용
- `CALIBRATED k=1/3/5/10/20`: 기존 k history에 반복 자기보고 보정 특징 추가

pooled 및 활동별 모델을 모두 평가한다. Target은 burden WEAK/BASE/STRONG, fatigue, condition이다.

## 6. 분석방법

- 각 k에서 특징 생성·train-only 전처리·validation-only alpha 선택·재학습을 독립 수행한다.
- 모든 조건은 동일한 ID-test 완료 평가 세션을 사용한다.
- 주 지표 MAE, 보조지표 RMSE·R².
- 5-seed mean±SD, t(4) 기술적 95% CI, 기존 k=0 대비 paired MAE difference와 seed별 방향을 보고한다.
- 5개 합성 seed의 구간을 실제 사람 모집단의 신뢰구간으로 해석하지 않는다.

## 7. 해석 제한

- 개선되더라도 합성 generator에 고정된 개인별 reporting bias를 반복 자기보고가 복원한 결과일 수 있다.
- 실제 장병에서 자기보고 기준이 안정적이라는 증거가 아니다.
- 반복 자기보고 보정은 질병 진단, 의학적 readiness 또는 임무수행능력 검증이 아니다.
- 결과에 맞춰 k, 특징, target 식 또는 개인편향 분포를 변경하지 않는다.
