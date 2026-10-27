# Simulator v2.2-multi-activity Amendment 05 — Phase 1 분석 규칙

상태: **결과 확인 전 사전 고정**  
작성일: 2026-09-28  
적용 범위: LOADED_MARCH와 BODYWEIGHT_CIRCUIT의 완료된 평가 세션에 대한 합성 0–10 상태점수 예측

## 1. 연구 질문과 자료

- 질문: 현재 세션의 관측 가능한 운동조건과 활동 전·후 HR을 알고 있을 때, 과거 calibration 기록이 burden·fatigue·condition 예측에 추가 정보를 제공하는가.
- seed는 잠긴 `110, 220, 330, 440, 550`을 사용한다.
- 각 seed에서 subject-level `72/24/24` train/validation/ID-test를 유지한다.
- `k=0,1,3,5,10,20`을 비교하며, 같은 seed의 모든 k는 같은 완료 평가 세션을 사용한다.
- 중단 평가 세션의 0–10 target은 Phase 1 점수예측에서 제외한다. 중단시간 분석은 별도 protocol 없이는 수행하지 않는다.

## 2. 예측 시점과 현재 세션 입력

예측 시점은 활동 종료 후 상태 확인 시점이다. 현재 세션에서 다음 observed 정보만 사용한다.

- 활동종류
- 계획·실제 수행시간, 완료 여부
- 회복간격
- 활동 전·후 관측 HR
- 군장행군: 속도, 체중 대비 군장 비율, 경사
- 맨몸 순환운동: 작업시간, 휴식시간, 작업밀도

개인의 latent capacity·strain·debt·true HR·난수·noiseless target은 금지한다. 현재 또는 과거 target 값도 predictor에 넣지 않는다.

## 3. 이력 선택

- common history: 현재 평가 세션 이전의 calibration 기록 중 시간상 가장 가까운 `k`건. 활동종류를 구분하지 않고 공통 HR·수행·회복 특징을 계산한다.
- activity-specific history: 현재 평가 세션과 같은 활동의 이전 calibration 기록 중 가장 가까운 `k`건. 활동별 운동조건 특징을 계산한다.
- k가 보유 기록보다 크면 실제 존재하는 기록만 사용하고 `history_count`를 함께 제공한다.
- 완료 세션에는 가상의 중단시간을 만들지 않는다. 중단 세션에는 실제 관측된 수행시간과 완료 여부만 사용한다.

## 4. 고정 history feature

### 공통 특징

- 기록 수, 완료율
- 활동 전 HR 평균
- 활동 후 HR 평균
- HR 변화량 평균·표준편차
- 실제 수행시간 평균·표준편차
- 회복간격 평균
- 가장 최근 HR 변화량과 가장 최근 완료 여부

### 활동별 특징

- 공통 특징과 동일한 활동별 요약
- 군장행군: 속도·군장비율·경사의 평균
- 맨몸 순환운동: 작업시간·휴식시간·작업밀도의 평균

과거 burden·fatigue·condition은 사용하지 않는다. target 평균을 직접 알려 주는 특징을 만들지 않는다.

## 5. 결측과 전처리

- k=0 모델에는 history 열 자체를 넣지 않는다.
- k>0에서 계산할 수 없는 통계는 train fold 중앙값으로 대체하고 결측 indicator를 둔다.
- 상수열은 제거한다.
- 표준화의 평균·표준편차는 train에만 적합한다.

## 6. 모델과 비교

- 기준 모델: Ridge.
- alpha 후보: `0.1, 1, 10`; validation MAE로만 선택한다.
- 선택 후 train+validation으로 재학습하고 ID-test는 한 번 평가한다.
- pooled 모델은 활동 indicator와 활동별 raw feature slot을 사용한다.
- activity-specific 모델은 각 활동 자료만 사용한다.
- 서로 다른 활동의 절대 MAE를 우열로 해석하지 않는다.

Target은 `burden_WEAK`, `burden_BASE`, `burden_STRONG`, `fatigue`, `condition`이다. WEAK/BASE/STRONG은 결과 등급이 아니라 잠긴 target coupling 민감도 조건이다.

## 7. 보고 지표

- seed별 MAE, RMSE, R²
- 5-seed mean±SD와 t(4)=2.776을 사용한 기술적 95% CI
- k=0 대비 seed-paired MAE difference와 95% CI
- seed별 개선 방향
- 활동별 모델과 pooled 모델을 각각 보고

5개 합성 seed의 구간은 실제 사람 모집단의 신뢰구간이 아니다.

## 8. 해석 규칙

- history가 개선되지 않거나 악화되어도 생성기·parameter·특징을 수정하지 않는다.
- 활동별 결과는 해당 합성 활동조건에 한정한다.
- pooled 모델이 우세하더라도 활동 간 공통 척도의 임상적 타당성이 확인된 것으로 해석하지 않는다.
- 실제 장병·실제 센서·군 임무수행능력에 대한 성능으로 일반화하지 않는다.
