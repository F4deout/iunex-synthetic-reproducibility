# RQ1 생리·수행 이력 연구 변수 대응 및 관측가능성 감사

상태: **CROSSWALK COMPLETE / IMPLEMENTATION NOT STARTED**  
기준 프로토콜: `RQ1_PHYSIOLOGICAL_HISTORY_VALUE_PROTOCOL.md`  
기준 매개변수: `RQ1_PHYSIOLOGICAL_HISTORY_VALUE_PARAMETERS.json`

## 1. 감사 목적

기존 `PRETASK`와 `RQ1 longitudinal v2`의 변수 중 새 연구의 predictor에 사용할 수 있는 실제 관측정보와 audit에만 사용할 latent 정보를 구분한다. 같은 의미의 변수를 하나로 정리하고, 참값·현재정답·미래정보가 이력특징으로 유입되는 경로를 구현 전에 차단한다.

## 2. 데이터 구조의 기준 선택

| 구성요소 | 채택 기준 | 이유 |
|---|---|---|
| 활동 전 상태와 예정 과업결과 | PRETASK | 활동 전 센서로 이후 완료·중단·회복을 예측하는 현재 연구목적과 일치 |
| 종단 관측간격·이력 길이 | RQ1 longitudinal v2 | 실제 경과시간과 0~100건 이력 비교구조 보유 |
| 자연적 수행능력 변화 | RQ1 longitudinal v2 | 연속변화와 드문 사건을 분리한 동결 구조 보유 |
| 통제 변화조건 | 신규 사전등록 | 자연조건에서 변화 직후 표본이 부족했던 식별 문제 보완 |
| 과업·수행결과 | PRETASK | 완료·관측 중단시간·회복지연 target 보유 |
| 자기보고 과정 | RQ1 longitudinal v2 | 안정편향·시간이동·기준변화를 분리하여 보조분석 가능 |
| 측정오차·결측 | PRETASK BASE와 사전고정 민감도 | 활동 전 연구모형과 단위 일치 |

## 3. 대상자 수준 변수

| 기존 변수 | 의미 | 새 연구 역할 | Predictor 허용 | 처리 |
|---|---|---|---|---|
| `subject_id` | 합성 대상자 식별자 | split·이력 연결 | 금지 | 행 연결과 누수검사에만 사용 |
| `fold` | train/validation/test | 자료분할 | 금지 | 학습절차 제어에만 사용 |
| `observed_anchor` | 과업배정 전에 알려진 독립 수행기록 | 모든 k의 공통 개인 기준정보 | 허용 | C1~C7에 동일 제공 |
| `base_capacity` / `capacity` | 과업별 참 수행능력 | 생성·audit | 금지 | parameter recovery와 counterfactual 감사에만 사용 |
| `tolerance` / `tolerance_minutes` | 참 수행예비량 | 생성·audit | 금지 | predictor 입력 차단 |
| `recovery_hours`, `tau_fast`, `tau_slow` | 참 회복특성 | 생성·audit | 금지 | predictor 입력 차단 |
| `hr_baseline` | 참 개인 심박 기준선 | 센서 생성 | 금지 | 과거 관측 HR로만 추정 |
| `temp_baseline`, `spo2_baseline` | 참 개인 기준선 | 센서 생성 | 금지 | 과거 관측값으로만 추정 |
| `hr_response_delta` | 참 과업별 심박반응 | 생성·audit | 금지 | workload-conditioned observed HR로만 추정 |
| `reporting_bias`, `perception_slopes` | 개인 점수부여 성향 | 보조 감사 | 금지 | C6·C7도 과거 관측점수만 사용 |

## 4. 현재 session 관측변수

| 기존 변수 | 새 표준명 | 관측시점 | Predictor 허용 | 비고 |
|---|---|---:|---|---|
| `task_type` / `activity_type` | `current_task_type` | 배정 시점 | 허용 | 범주형 처리 |
| `planned_demand`, `external_demand`, `workload` | `current_external_workload` | 배정 시점 | 허용 | 과업별 단위와 구성요소를 보존 |
| `planned_duration` | `current_planned_duration_min` | 배정 시점 | 허용 | 실제 수행시간과 구분 |
| `observed_anchor` / `v5_kmh` | `independent_performance_anchor` | 사전 기록 | 허용 | 모든 k에 동일 제공, 잠재능력과 동일시 금지 |
| `gap_days` / `recovery_interval_days` | `time_since_previous_session_days` | 배정 시점 | 허용 | 생리적 회복시간과 동일시 금지 |
| `t0_hr` / `hr_bpm` | `current_hr_bpm` | 과업 전 | 허용 | 측정오차·품질·결측 적용값만 사용 |
| `t0_temperature` / `temperature_c` | `current_temperature_c` | 과업 전 | 허용 | 측정오차·품질·결측 적용값만 사용 |
| `t0_spo2` / `spo2_pct` | `current_spo2_pct` | 과업 전 | 허용 | 측정오차·품질·결측 적용값만 사용 |
| quality fields | `current_*_quality` | 과업 전 | 허용 | target proxy 여부 별도 감사 |
| `safety_gate` | `current_safety_hold` | 과업 전 | 제한 | 규칙 기반 안전층 출력으로만 사용, 학습특징 제외 |

## 5. 과거 session에서 사용할 수 있는 이력

| 정보군 | 원자료 | 사용 조건 | 파생특징 예시 |
|---|---|---|---|
| 센서 기준선 | 과거 과업 전 HR·체온·SpO₂ | 현재보다 이전이고 측정과정 적용 완료 | 평균·SD·최근값·시간기울기 |
| 과업별 생리반응 | 과거 외부부하와 측정된 운동 후 HR | 같은 과업·부하정보 존재 | 부하조건별 반응 평균·기울기·개인 내 변동 |
| 회복반응 | 측정된 운동 후·회복시점 HR | 실제 측정시각과 회복간격 존재 | 회복량·회복속도 대리특징·유효 관측 수 |
| 수행정보 | 실제 수행시간·완료·중단 | 실제 관측값만 사용 | 과업별 완료율·수행시간·최근값·추세 |
| 중단정보 | 실제 관측 중단시간·사유 | 중단 session만 사용 | 과업·부하조건별 중단시간 요약 |
| 회복결과 | 실제 관측 회복지연 | 이전 session에서 확정된 뒤 사용 | 최근값·평균·변동·추세 |
| 독립 수행기록 | 당시 관측 가능한 수행기록 | 기록시각 이후 session에만 사용 | 최근값·변화기울기 |
| 자기보고 | 과거 피로·현재상태·운동부담 | C6·C7 보조조건에만 사용 | 평균·최근값·변동·시간기울기 |

## 6. Predictor에서 금지할 latent·미래정보

| 기존 변수 | 금지 이유 | 허용 용도 |
|---|---|---|
| `effective_capacity`, `capacity_log_change` | 참 수행능력·변화량 | audit-only parameter recovery |
| `relative_demand` | 참 capacity를 분모로 사용 | 생성·counterfactual 감사 |
| `reserve_pre`, `reserve_after`, `depletion` | 참 수행예비량 상태 | 생성·경로감사 |
| `debt_pre`, `debt_after` | 잠재 회복부채 | 생성·경로감사 |
| `strain`, `pre_fatigue_latent`, `burden_latent` | target 생성 잠재상태 | 합성 생리상태 target 또는 경로감사 |
| `true_hr`, `true_temperature`, `true_spo2` | 측정 전 생리 참값 | measurement oracle 감사 |
| `latent_limit` | 참 생리적 제한시간 | 생성·tolerance oracle 감사 |
| `reporting_bias`, `noiseless_targets` | 보고과정 내부값·audit target | 보조 target·경로감사 |
| 현재 session의 `actual_duration`, `completed`, `stop_time`, `recovery_delay` | 예정 과업결과 예측시점 이후 정보 | 해당 session target으로만 사용 |
| 평가시점 이후의 모든 기록 | 미래정보 | 사용 금지 |

## 7. 발견된 구현상 차단 필요 항목

### 7.1 운동 후·회복 HR의 참값 노출

기존 `simulator_pretask_model.py`의 `history_observable.t2_hr`와 `t3_hr`는 `true_hr`에서 직접 계산되며, 현재 센서와 같은 측정오차·artifact·missingness·quality 과정을 거치지 않는다. 이름은 observable이지만 실제 장치 관측값과 동일한 증거수준이 아니다.

**처리 결정**

- 새 predictor에서 기존 `t2_hr`, `t3_hr` 직접 사용 금지
- 새 builder에서 운동 후·회복 HR을 생성한 뒤 공통 측정과정을 적용
- 측정값, 품질, 결측 및 측정시각이 모두 존재할 때만 legitimate observed history로 사용
- 기존 PRETASK 결과와 코드는 수정하지 않음

### 7.2 독립 수행기록과 참 수행능력의 구분

`observed_anchor`와 `v5_kmh`는 과업배정 전에 관측 가능한 합성 수행기록이지만 true capacity가 아니다. 새 연구에서는 모든 k와 입력조건에 같은 기준정보로 제공하며, assignment metadata로 true capacity가 거의 완전히 복원되는지 별도 검사한다.

### 7.3 자기보고 이력의 주 분석 차단

기존 `full` history에는 과거 자기보고가 포함된다. 새 연구의 C5는 센서·수행·회복 이력만 포함하고, 자기보고가 포함된 C6과 C7은 보조 대조조건으로 분리한다.

### 7.4 현재 과업결과의 입력 차단

활동 전 예측에서는 현재 session의 실제 수행시간·완료·중단시간·운동 후 부담·회복지연을 입력할 수 없다. 이 값은 target으로만 보존한다.

## 8. Target 대응

| 새 target | 기존 원천 | 역할 | 단위·평가 |
|---|---|---|---|
| `pretask_fatigue_latent` | `pre_fatigue_latent` | RQ1-P 주 구조감사 target | 0~1, MAE/RMSE/R² |
| `pretask_condition_construct` | `1 - pre_fatigue_latent` 또는 별도 방향표기 | RQ1-P 보조 구조감사 target | 0~1, fatigue와 중복성 명시 |
| `posttask_burden_latent` | `burden_latent` | RQ1-P 활동 후 구조감사 target | 0~1, MAE/RMSE/R² |
| `observed_pre_fatigue` | `targets.pre_fatigue` | RQ1-S 보조 target | 0~10점 |
| `observed_pre_condition` | `targets.pre_condition` | RQ1-S 보조 target | 0~10점 |
| `observed_post_burden` | `targets.post_burden` | RQ1-S 보조 target | 0~10점 |
| `task_completed` | `targets.completed` | RQ1-T 주 target | Brier·calibration error |
| `observed_stop_time_min` | `targets.stop_time` | RQ1-T 주 target | 분, 중단 session 회귀 및 전체 AFT |
| `observed_recovery_delay_h` | `targets.recovery_delay` | RQ1-T 주 target | 시간, MAE/RMSE/R² |

`pretask_condition_construct`는 현재 생성구조에서 피로 구성값의 방향반전과 정보가 중복될 수 있으므로 독립 생리상태가 확인된 것처럼 해석하지 않는다.

## 9. 단위 대응

| 변수 | 표준 단위 |
|---|---|
| 심박수 | bpm |
| 체온 | °C |
| 산소포화도 | % |
| 운동·중단시간 | 분 |
| 회복지연 | 시간 |
| session 간격 | 일 |
| 외부 운동부하 | 과업별 원단위와 정규화 수준을 함께 보존 |
| 자기보고 | 0~10점 |
| 합성 생리상태 구성값 | 0~1 무차원 값 |

## 10. 구현 assertion

1. predictor 열 이름에 `capacity`, `tolerance`, `reserve`, `debt`, `strain`, `latent`, `true_`, `reporting_bias`, `noiseless` 포함 금지
2. 모든 history timestamp가 현재 평가 timestamp보다 작음
3. 현재 session 결과열의 feature 포함 0건
4. 과거 자기보고가 C1~C5에 포함된 열 0건
5. `observed_anchor`가 모든 k와 조건에 동일하게 존재
6. post/recovery HR이 measurement process를 거쳤다는 audit flag 확인
7. 완료 session의 미관측 가상 중단시간 feature 포함 0건
8. subject·session split 교집합 0
9. 전처리 fit 대상은 train만 포함
10. assignment-only true-capacity recovery를 정량화하고 거의 완전 복원 시 proxy-leakage 경고

## 11. 감사 판정

- 변수 의미와 단위 대응: **PASS**
- 현재·미래·latent 구분: **PASS AT DESIGN LEVEL**
- 기존 post/recovery HR의 직접 승계: **FAIL — NEW MEASUREMENT PROCESS REQUIRED**
- 과거 자기보고의 주 분석 분리: **PASS AT DESIGN LEVEL**
- 새 builder 구현 시작 조건: **PARAMETER LOCK 후 가능**

기존 파일을 수정하지 않고 새 builder에서 차단 조건을 구현해야 한다.
