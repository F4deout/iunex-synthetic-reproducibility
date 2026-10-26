# Simulator v2.1 `DEPLOYABLE_CONTROLLED` 사전등록 설계안

상태: **새 설계만 동결 예정; 미구현·미생성·본 실험 미실행**  
작성일: 2026-09-21  
시점: `ORACLE_CONTROLLED` dry run·Phase 1 및 관측정보 감사 결과를 본 **이후** 작성. 따라서 이 설계를 이전 Phase 1의 사전등록으로 소급하지 않는다. 아래 숫자와 분석 규칙은 첫 `DEPLOYABLE_CONTROLLED` 결과를 보기 **전에** 고정하며, 이후 변경은 원문 수정이 아니라 dated amendment에 이유와 결과 열람 여부를 남긴다.

기존 `simulator_v21_running.py`, parameter register·amendment, `SIMULATOR_V21_RUNNING_DATASET_PROTOCOL.md`, `SIMULATOR_V21_RUNNING_EVALUATION_AMENDMENT_01.md`, `ORACLE_CONTROLLED`와 Phase 1 코드·산출물·해시는 변경하지 않는다. 새로운 dataset ID를 `DEPLOYABLE_CONTROLLED_V1`로 두고 별도 디렉터리에만 생성한다. 이 명칭의 **deployable**은 배정 규칙에 실제로 확보할 수 있는 선행 정보만 사용한다는 뜻이지, 아래 러닝 일정 전체가 실제 장병용으로 안전하거나 검증됐다는 뜻이 아니다.

## 1. Workload 배정: 외부 5 km 기록만 사용

각 synthetic subject의 **첫 calibration 이전**에 날짜가 확인된 독립 5 km 수행기록으로 `v5_i = 5 km / 기록시간`(km/h)을 계산한다. 현재 프로젝트의 `v5_kmh`는 경험적 capacity **anchor**이고 실제 개인 CS 측정값이 아니다. 원본 5 km 기록의 제공자·날짜·시간·단위를 manifest에 고정한다. 기록이 없거나 calibration 이후에 측정됐거나 값·시각이 검증되지 않으면 해당 subject의 이 배정 절차는 **STOP**한다. `true CS`, `rho=CS/v5`, `D′`, `q`, `tau_fast/tau_slow`, strain/debt, 미래 HR·완료/중단·target은 workload 배정 함수의 인자와 조회 가능 저장소에서 모두 제외한다. 이전 calibration 결과에 따른 적응식 속도 변경도 이번 V1에는 넣지 않는다.

각 cell에 사전 지정한 무차원 anchor multiplier `u`에 대해 **commanded speed**를 `v_cmd_kmh = u × v5_kmh`로 정한다. `u=v_cmd/v5`일 뿐 `v/CS` 또는 physiological relative intensity가 아니다. 기존 generator는 일정속도 입력 하나만 받아 별도의 주행 순응도·speed measurement error를 만들지 않는다. V1 합성 구현에서는 `v_actual=v_cmd`라는 **기존 일정속도 근사**를 명시하고, 두 이름을 기록하되 독립적인 실측 일치 검증으로 표현하지 않는다. 향후 장치 자료에서는 지시속도와 실제 속도를 별도 관측값으로 보관해야 한다. Generator는 **결과 생성 단계에서만** 기존 참 CS/D′/q를 사용하며 그 식·parameter·noise를 바꾸지 않는다.

`v5`와 `CS_like`는 현재 잠긴 simulator에서 `CS_like=rho_i×v5_i`로 관련되므로 v5는 **정당한 선행 예측정보**일 수 있다. 그러나 `rho_i`가 미관측이므로 `v_cmd=u×v5`는 참 CS를 결정적으로 암호화하지 않아야 한다. 이 주장은 생성 전의 대수 검증 및 생성 후의 별도 누수 감사로 확인하며, 높은 CS 예측 R²만으로 자동 PASS하지 않는다.

## 2. 고정 calibration·evaluation grid

`ORACLE_CONTROLLED`의 **20 calibration event + 4 evaluation event**, duration·gap·순환 순서·subject split을 유지한다. 단, 아래 숫자는 모두 `u=v/v5`로 재정의한다. 같은 숫자라도 각 개인의 참 `v/CS=u/rho_i`는 다르며, 특정 cell이 실제로 임계 아래/위라는 보장은 없다. ORACLE의 “아래/위 임계” 명칭을 B의 결과 분류로 전용하지 않는다. 이 grid는 **합성 식별성 비교용 고정 시험조건**이고 사람에게 그대로 수행시키는 운동 처방이 아니다.

| Event | `u=v_cmd/v5` | 계획 duration | 직전 event·동일 블록 내 gap | 역할 |
|---|---:|---:|---|---|
| R1 | 0 | 0분 | 시작 전 | 안정 HR 첫 관측 |
| G1 | 0.70 | 6분 | 72시간 | 낮은 anchor 속도 |
| G2 | 0.90 | 12분 | 72시간 | 중간 anchor 속도·지속 |
| G3 | 1.00 | 6분 | 72시간 | anchor 근처 속도 |
| G4 | 1.05 | 3분 | 72시간 | 높은 anchor 속도·짧은 지속 |
| G5 | 1.05 | 20분 | 72시간 | 같은 속도의 긴 지속·완료/중단 |
| G6 | 1.10 | 12분 | 72시간 | 다른 높은 속도·완료/중단 |
| F1a → F1b | 1.10 → 1.10 | 3분 → 12분 | **1분** | 짧은 회복 probe |
| F2a → F2b | 1.10 → 1.10 | 3분 → 12분 | **4분** | 중간 회복 probe |
| F3a → F3b | 1.10 → 1.10 | 3분 → 12분 | **16분** | 긴 회복 probe |
| R2 | 0 | 0분 | 앞 블록 후 72시간 | 회복 뒤 안정 HR 재관측; 잔여 상태 가능 |
| S1a → S1b | 0.90 → 0.70 | 12분 → 6분 | **6시간** | 느린 회복 probe |
| S2a → S2b | 0.90 → 0.70 | 12분 → 6분 | **24시간** | 느린 회복 probe |
| S3a → S3b | 0.90 → 0.70 | 12분 → 6분 | **72시간** | 느린 회복 probe |

R1+G 6+F 6+R2+S 6 = **20 calibration event**. G 단일 bout 사이, F 블록 사이, S 블록 사이의 72시간 간격을 유지한다. G/F/S 블록의 순환 이동은 기존 `SHA256(UTF-8(subject_id+"|"+letter))` 정수의 `mod 6/3/3` 규칙을 그대로 쓴다. 선행 bout→gap→probe 순서는 바꾸지 않는다. 어떤 bout가 일찍 중단돼도 이후 grid·순서를 결과에 맞춰 조정하지 않고, 불가능해진 뒤의 label·상태를 기존 core 규칙대로 기록한다.

Evaluation은 calibration 뒤 각 72시간 간격으로 `E1=(u=.70,6분)`, `E2=(.90,12분)`, `E3=(1.05,3분)`, `E4=(1.10,12분)`을 두고, E 순서는 기존 hash rotation `mod 4`를 유지한다. `E1–E3`은 **실제로 완료된 session에 한해** 0–10 burden `WEAK/BASE/STRONG`, fatigue, condition 예측에 사용한다. 검열은 모든 k에서 동일하게 제외하고 cell·fold·seed별 완료/중단률을 반드시 보고한다. `E4`는 완료 여부와 관측 중단시간 또는 완료 시 `time-to-limit > 12분`이라는 **검열된 하한**을 보고하는 tolerance endpoint로 고정한다. E4가 B에서 완료되더라도 0–10 예측 cell로 사후 이동하지 않는다. 어느 cell의 완료 label이 없으면 해당 점수 metric은 `NOT_EVALUABLE`로 보존하고 다른 cell로 대체하지 않는다.

Train/validation/ID-test 합성 subject는 기존 72/24/24 분할 규칙을 유지하며, 동일 subject·session이 fold를 넘지 않는다. B에는 PMData running workout template를 재사용하지 않는다. `v5`가 소수 원본 제공자의 기록에서 왔다는 사실 및 fold 사이 source person/anchor 공유는 manifest의 제한으로 보고한다. Naturalistic과 ORACLE의 산출물은 읽기 전용이다. B 내부 `k=0/1/3/5/10/20`는 같은 E1–E3 subject/session 집합에서 비교하며, k 증가가 개선을 보장한다는 성공 가정을 두지 않는다.

## 3. 관측 event log와 history feature

각 calibration event의 **관측 경계**를 다음 고정 schema로 설계한다: `subject_id`, `event_id`, `event_order`, `pair_id`(없으면 null), `rest_flag`, `planned_start/actual_start/end`, `v5_record_id/date`, `u`, `commanded_speed_kmh`, `actual_speed_kmh`, `planned_minutes`, `actual_minutes`, `completed`, `censored`, `observed_stop_minutes`(중단했을 때만), `gap_minutes_or_hours`(직전 event 종료→현재 시작), `observed_session_mean_hr`, HR 품질/결측 flag(기기가 실제 제공할 때만). `u`와 event ID는 **관측 가능한 지시 protocol metadata**이며 참 `v/CS`가 아니다. 현 합성 core에는 start/end 실측시각·별도 품질 모형·속도 순응도 모형이 없으므로 합성 일정의 예정 시각/간격과 품질 `UNKNOWN`을 구분해서 저장한다. 실측 pre/post/recovery HR은 기록 가능하지만 현재 core가 생성하지 않으므로 V1 predictor에 값이 있는 것처럼 채우지 않는다. 과거 합성 target label도 history 입력으로 쓰지 않는다.

`k`는 평가 event보다 **앞선 최근 k개 calibration event** 수이며 안정 event도 센다. 평가 E1–E4의 관측/label은 다른 E의 history에 넣지 않는다. 각 k마다 동일한 train/validation/test 평가 key를 사용한다. 다음 표는 기존 단순 평균 feature를 대체하는 **고정 feature schema**다. 모든 통계는 window 안의 관측값만으로 계산한다. 최소 건수 미달이면 숫자를 만들어 넣지 않고 null과 `available=0`을 남기며 결측 보정은 train에만 fit한다. 결과를 보고 표의 열을 추가·삭제하지 않는다.

| 표현 목적 | 관측값으로 계산할 feature와 유효 조건 |
|---|---|
| Window 규모·안정 baseline | `n_events`, `n_rest`, `rest_hr_mean`(R1/R2 중 window에 있는 안정 관측 HR), `rest_hr_last`; R2가 완전 회복 baseline이라는 가정 금지 |
| Speed-conditioned HR response | 러닝 event의 `actual_speed_kmh`–`observed_session_mean_hr` 단순 OLS 기울기·절편·잔차 SD와 관측 speed 범위. 서로 다른 속도 ≥3개일 때만 계산; duration·이전 상태의 혼란을 제거한 생리계수라고 주장 금지 |
| Completion/tolerance | window의 완료 수·중단 수, 완료된 bout의 `max(planned_minutes)`와 해당 속도(동률이면 먼저 기록된 event), 중단된 bout의 `median(observed_stop_minutes)`와 `mean(actual_speed_kmh)`, G5/G6의 **두 실제 중단시간**이 모두 존재할 때만 관측 속도–시간 두 점에서 구한 `CS_pair_candidate`·`Dprime_pair_candidate` 및 유효 flag. 이 두 값은 noisy performance proxy이며 생성기 참값이 아님 |
| Fast recovery probe | window에 lead·probe가 모두 있는 F pair 수; 각 1/4/16분 gap의 실제 lead 시간·완료, probe 완료·중단시간, probe HR−lead HR. 관측 중단시간이 ≥2개 gap에 있으면 `stop_minutes` 대 `log(gap_minutes)` 기울기와 유효 flag; 모두 완료되면 한계시간을 추정하지 않음 |
| Slow recovery probe | window에 lead·probe가 모두 있는 S pair 수; 6/24/72시간별 probe HR−lead HR 및 완료·중단 상태. ≥2개 gap에서만 HR 차이 대 `log(gap_hours)` 기울기 계산. 기존 session-average HR의 낮은 식별력을 결과로 보존 |
| 시간·품질 | 마지막 관측 이후 경과시간, window의 gap 요약, 관측 HR 수와 실제 제공된 품질/결측 수. 합성 V1에서 존재하지 않는 SQI를 임의 생성하지 않음 |

`CS_pair_candidate`의 이상적 두 점 식은 `v_j = c + d/t_j`이며 두 **실제** 중단시간 `t_j`와 실제 수행속도가 있을 때만 계산한다. 관측 q/회복이 불완전하거나 조건이 다르면 `c,d`가 참 CS/D′와 다를 수 있고, 유효 flag는 **대수 계산 가능성**만 나타낸다. 두 중단시간 차이가 **1.0분 미만**이거나 계산값이 비유한·`c≤0`·`d≤0`이면 후보를 null과 실패 이유로 기록한다. 1.0분은 수치적으로 가까운 두 점의 불안정한 역산을 피하기 위한 **사전등록 분석 가정**이며 실측 생리 기준이 아니다. 참 latent 값으로 결측을 메우지 않는다. 성능을 보고 feature를 추가·제거하지 않는다.

## 4. Censoring, 누수 차단과 평가 전 audit

중단된 event의 `observed_stop_minutes=actual_minutes`만 정확한 중단시간으로 취급한다. 완료된 event의 생성기 `limit_minutes`는 **금지 latent/반사실적 값**이며 observed log에는 null; 관측된 사실은 `time-to-limit > planned_minutes`라는 하한뿐이다. 중단 후의 0–10 label을 임의 생성·대입하지 않는다. 예정시간을 채웠지만 다른 이유로 중단한 실제 자료는 사유와 measurement status를 별도로 기록해야 하며 현 합성에는 그 모델이 없다고 표시한다. 전처리·feature 선택·모델/alpha 선택은 train과 validation만 사용하고 ID-test는 최종 평가 전 열지 않는다.

**구현 전 대수 누수 감사 사전등록:** (1) 배정 함수의 데이터 접근 경계를 코드 검사해 `v_cmd=u×v5` 외의 latent·현재/미래 결과 의존이 있으면 `FAIL`; (2) 각 cell에서 `v_cmd/u=v5`를 수치오차 이내 확인하고, 이 식에서 `rho=CS/v5` 또는 CS가 단일 값으로 풀리면 `FAIL`; (3) 같은 v5를 가진 합성 subject 사이에 rho·CS의 조건부 변동이 남는지 확인한다. 같은 v5 group에 비교 대상이 없으면 정량 판정은 `INCONCLUSIVE`; (4) `v5`만으로 train에서 추정한 CS와 `v5+commanded speed+u/event`로 추정한 CS를 held-out subject에서 비교한다. 지시속도가 v5의 결정함수라면 추가 정보 이득을 **설계 누수로 해석하기 전에** 모델 형식과 수치오차를 분리 검토한다. (5) k=0의 현재 E 지시속도·계획시간에서도 같은 감사를 수행한다. v5의 정당한 capacity 연관을 0으로 만들 필요는 없지만 ORACLE처럼 `CS=speed/(고정배율)`이 정확히 성립하면 B 설계는 `FAIL`이다. 결과 확인 뒤 배정 배율·rho 분포를 수정하지 않는다.

**생성 후 정량 보고 항목:** v5와 CS의 관계, `rho=CS/v5`의 전체·v5별 분산, assignment-only CS 재구성 R²·절대오차, commanded-speed 추가정보 조건부 검사, G/F/S/E의 완료/중단 support, window별 유효 feature 수, subject/session 교집합 0, history 현재/미래 관측·label 누수 0. 실측 physiology와 중단시간이 얻어지지 않으면 parameter 식별을 억지로 주장하지 않는다.

## 5. 식별 가능성·실제 시스템으로의 이전 경계

| 개인 특성 | `DEPLOYABLE_CONTROLLED`에서의 조건부 식별 가능성 |
|---|---|
| 안정 HR baseline | R1/R2의 실제 안정 HR 반복이 있을 때 부분 추정. R2의 잔여 회복 영향을 분리할 자료가 없으면 불확실성 유지 |
| Speed-conditioned HR response | 서로 다른 실제 속도에서 반복 HR과 시간·상태 기록이 있을 때 관측 관계 추정. 참 CS와 생리 반응 편차의 분리는 별도 수행정보 없이 보장 안 됨 |
| CS-like·D′-like | v5만으로는 **둘 다 식별 불가**. 서로 다른 절대속도의 독립적 실제 중단시간 ≥2개와 시작 reserve/회복 조건의 근거가 있어야 후보 추정 가능. 완료만 있으면 bounds/`NOT_IDENTIFIABLE` |
| Fast recovery | 비슷한 선행 부하·서로 다른 짧은 gap·정보가 있는 probe 중단/완료 기록이 있을 때만 부분 추정. 모든 probe가 완료되거나 초기 q가 불명확하면 미식별 가능 |
| Slow recovery | 현재 단일 session-average HR 수준에서는 이전 `NOT_IDENTIFIABLE` 우려 유지. 독립적인 반복 fatigue/condition·회복 측정 없이는 성공 가정 금지 |

실제 군 시스템에 옮길 수 있는 요소는 선행 체력기록의 출처·시각 확인, 안정 관측 반복, 기록 가능한 지시/실제 속도·시간·HR·회복간격의 구조화, 관측 실패·검열의 정직한 표시, 개인 이력과 후속 확인의 분리다. **옮길 수 없는 요소**는 참 CS/D′/q를 아는 가상 배정, 합성 q=0을 목표로 하는 G/F의 소진 시험, 생성기 내부의 정확한 한계시간, 합성 target을 의학적 readiness로 해석하는 것이다. 실제 대상자에 대한 강도·중단 기준·의료적 안전성은 별도 검토 대상이며 이 문서가 처방하지 않는다.

## 6. 구현 시작 판정

**`PASS` — 별도 synthetic `DEPLOYABLE_CONTROLLED_V1` builder·관측경계·누수 감사 구현에 한정.** 20+4 event, `v5` 기반 배정, censoring/null 규칙, 고정 history schema와 실패 처리, 동일 E 평가표본의 원칙을 결과 전에 지정했다. 구현은 v5 기록의 결측/날짜/단위 검증을 **생성 전** 수행해야 한다. 참 latent를 참조하는 배정 또는 관측값 위장, v5 출처 불명, 기존 ORACLE/Phase 1 파일 변경은 즉시 `STOP`이다. 본 판정은 데이터 생성·예측 모델 본 실험의 승인이나 실제 사람에게 이 grid를 적용할 안전 승인으로 해석하지 않는다.
