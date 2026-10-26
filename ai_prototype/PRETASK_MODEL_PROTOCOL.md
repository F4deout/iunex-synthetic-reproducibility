# PRETASK v1-minimal preregistration protocol

## 연구질문

임무 전(T0) 생체정보·개인 기준선·최근 회복이력과 예정 과업 요구량을 이용할 때, 개인 이력이 현재 자기보고 상태와 이후 과업 결과 예측에 추가 정보를 제공하는지를 합성환경에서 평가한다.

## 시점

- T0: 예측 입력
- T1: 실제 수행·완료·중단 기록
- T2: 직후 생체정보와 부담 자기보고
- T3: 회복 후 측정과 회복지연
- 현재 세션의 T1~T3는 T0 predictor 입력 금지

## 대상과 분할

- seed당 120명
- train/validation/test 72/24/24명
- final seed 110, 220, 330, 440, 550
- 대상자별 100개 calibration session과 30개 evaluation session
- 동일 대상자의 모든 session은 하나의 split에만 배치

## 과업

- 유산소 운동
- 하중이 있는 이동
- 맨몸 순환운동
- 과업 요구량은 관측 가능한 공통 anchor와 계획 강도·시간에서 결정
- latent capacity를 workload 배정에 사용하지 않음

## 입력조건

1. T0 현재정보만
2. T0 + 최근 20개 생체·활동 이력
3. T0 + 최근 20개 자기보고 이력
4. T0 + 최근 20개 수행·중단 이력
5. T0 + 전체 legitimate history

## 예측대상

- T0 피로 자기보고 0~10
- T0 현재상태 자기보고 0~10
- T1 완료 여부
- 미완료 session의 관측 중단시간(분)
- T2 운동부담 자기보고 0~10
- T3 회복지연(시간)

## 모델

- 연속 target: Ridge, alpha 1·10·100
- 완료 여부: L2 logistic regression, alpha 0.1·1·10
- 전처리: train only
- 선택: validation only
- test: 최종 평가에만 사용

## 평가

- 연속 target: MAE, RMSE, R²
- 완료 여부: Brier score, accuracy, sensitivity, specificity, AUROC
- k=0 대비 paired MAE/Brier difference와 5-seed 기술적 95% CI
- 실제 사람 모집단 성능으로 해석하지 않음

## 누수통제

- 현재·미래 T1~T3 입력 금지
- latent capacity·fatigue·debt·tolerance·perception·reporting bias 입력 금지
- history는 현재 T0보다 앞선 session만 사용
- subject-disjoint split
- target/feature shuffle과 history identity destruction 수행

## 판정

- 현재상태 target과 과업결과 target을 별도 판정
- 자기보고 개선은 개인별 체감 민감도와 보고편향 복원을 분리하여 audit
- 완료·중단 예측은 의료적 적합성 또는 임무수행 명령으로 해석하지 않음

