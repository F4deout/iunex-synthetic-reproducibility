# v2.1 Controlled calibration: 관측정보·잠재정보 감사

상태: **감사 전용. Phase 1 본 실험 중단·결과 보존.**  
작성일: 2026-09-21  
변경 범위: 이 문서와 `artifacts/synthetic_v21_running_observability_audit/quantitative_audit.json`만 추가. Generator, parameter, 잠긴 grid/split, history feature, Phase 1 결과는 변경하지 않음.

## 1. 분석 대상과 보존 증거

코드 기준: `build_v21_running_datasets.py`의 `controlled_schedule`, `build_controlled`, `observed_inputs`; `simulator_v21_running.py`의 `core`; `validate_simulator_v21_running.py`의 `OBSERVED_NAMES`, `history_features`; `run_v21_phase1_history.py`의 `feature_rows`와 parameter recovery. 5개 seed `110/220/330/440/550`를 기존 `split_manifest.json`의 생성 해시와 대조해 모두 일치시킨 **읽기 전용 재생성 감사**다. 새 모델 학습이나 target MAE 계산을 하지 않았다.

보존 확인: 기존 Phase 1 `summary.json` SHA-256 `14219415d70bfbcc4eee8406a523650a838aba39500ce10a97e5a6f5683d5753`, `seed_metrics.json` SHA-256 `0806cc391e85dd319ebacd230fa43d6ed471621ef48123b7effdaa24c32d8fe6`. Generator SHA-256 `d03b854edb53fa95955d440c58c71bf3e7a158c3104753841f073a20046cf586`. 이 감사는 위 파일을 쓰지 않는다.

## 2. 무엇이 실제 관측 가능하며 현재 history에 쓰이는가

여기서 **관측 가능**은 기록 장치와 절차가 마련될 경우 사람에게서 측정·기록할 수 있다는 뜻이다. 현재 합성 artifact에 실제 포함됐다는 뜻과 구별한다. `observed_hr`는 현재 generator가 제공하는 **session당 HR 요약 1개**다. 별도의 pre/post/recovery HR 시계열은 생성되지 않는다. 검열된 bout의 `actual_minutes`는 중단까지 실제 수행한 시간이고 `limit_minutes`와 같아서 관측 가능한 stop time으로 볼 수 있다. 완료된 bout의 `limit_minutes`는 계획시간을 넘는 생성기 계산값이며 실제 관측값이 아니다.

| Event | 실제 기록 가능한 항목 및 현재 artifact | 잠재/직접 측정 불가 항목 | 현 history feature 처리 |
|---|---|---|---|
| R1·R2 안정 관측 | 지정 속도 0, 관측 시각·간격, 안정 시 `observed_hr` 1개. R2에는 이전 운동의 잔여 영향 가능 | 순수 `baseline_hr`, 잔여 slow debt·strain | HR 평균/SD와 speed 평균에 일반 event처럼 혼합. 안정 event 표시·별도 baseline 추정치 없음 |
| G1–G4 아래/근처 임계 러닝 | 지시·실제 속도, 계획·실제 시간, 완료, session HR, event 순서와 72시간 간격 | 참 CS/D′, 상대강도 `x`, q·strain·debt, 참 HR | 과거 speed·HR의 평균/SD·선형 기울기만 사용. 과거 duration·완료·순서·gap·event cell은 버림 |
| G5·G6 위 임계 러닝 | 지시 속도, 계획시간, 완료/중단, **중단 시 실제 time-to-limit**, HR, 간격 | 참 CS/D′, 시작/종료 q, 생성기 계산식의 반사실적 한계시간 | speed·HR 통계에만 포함. 중단시간·검열 여부·두 속도의 paired 수행결과를 사용하지 않음 |
| F1–F3 선행 bout·probe | 두 bout의 지시 속도·시간·완료/중단, probe 중단시간, 중간 1/4/16분 간격, HR | 참 q, `tau_fast`, 정확한 fast reserve 재충전량 | speed·HR 통계에만 포함. 선행→gap→probe 짝, gap, 중단시간·완료 여부를 사용하지 않음 |
| S1–S3 선행 bout·probe | 두 속도·시간·완료 여부, 중간 6/24/72시간 간격, session HR | 참 `tau_slow`, prior debt·strain, 비관측 피로 상태 | speed·HR 통계에만 포함. 각 pair와 과거 gap·duration을 사용하지 않음. 현재 합성 HR 차이는 잡음보다 작음 |

모든 event에서 추가로 기록 가능한 시각, 실제 거리·속도 궤적, 중단 사유, 측정 품질, 운동 직전·직후·회복 중 HR, 자기보고 RPE는 **현재 v2.1 Controlled artifact에는 없거나 history에 사용되지 않는다.** 속도 궤적·별도 HR 시계열·품질값·중단 사유는 현 generator가 만들지 않으므로 지금 즉시 feature만 추가할 수 없다. 자기보고 0–10 burden/fatigue/condition은 현 합성 label이며, 과거 label 평균을 입력으로 쓰지 않는 잠금 원칙을 유지한다.

현재 E1–E3 점수 predictor 입력은 `speed_kmh`, **현재** `actual_minutes`, **현재** `observed_hr`, **현재** `gap_h`, 그리고 `history_n`, 과거 HR 평균, 과거 speed 평균, 과거 speed–HR 선형 기울기, 과거 HR SD의 총 9개다. 과거 duration·완료/검열·time-to-limit·gap·시각 순서는 history에 없다. Parameter recovery용 predictor는 마지막 5개 history 요약만 사용했다. 잠재 `CS`, `D′`, q, `tau_fast/tau_slow`, strain/debt, `true_hr`, `x`는 모델 입력에 직접 들어가지 않았다. **다만 속도를 배정할 때 참 CS를 사용했으므로 observed speed가 잠재 CS의 결정적 대리변수다.**

## 3. CS-like design-induced leakage: 정량 판정

잠긴 일정의 마지막 calibration event는 회전 순서와 관계없이 **마지막 S 블록의 probe**이며 `v=0.70×CS_like`다. 블록 번호는 S1/S2/S3 중 하나일 수 있다. 단위가 km/h인 기록 속도에서

`CS_like (m/s) = history_speed_mean(k=1) / (3.6×0.70)`.

20개 calibration event는 모든 사람에게 같은 상대강도 목록을 한 번씩 배치하고 안정 event 2개를 포함하므로 평균 상대강도가 **0.86**이다. 따라서

`CS_like (m/s) = history_speed_mean(k=20) / (3.6×0.86)`.

완료된 E1–E3도 각 cell의 계획 duration이 서로 달라 E1/E2/E3을 구분할 수 있고, `current speed / (3.6×해당 cell의 0.70/0.90/1.05)`로 CS를 직접 역산할 수 있다. 5개 seed의 **600명**에서 k=1 속도만의 CS 복원 R²=1.000, 최대 절대오차 `8.9×10⁻¹⁶ m/s`; k=20은 R²=1.000, 최대오차 `1.8×10⁻¹⁵ m/s`였다. E1–E3의 **1,800건**에서도 R²=1.000, 최대오차 `8.9×10⁻¹⁶ m/s`였다. Phase 1 Ridge k=20 CS R²≈0.999는 정규화·ridge penalty 아래의 값이지 독립적인 생리 식별 성과가 아니다. **판정: design-induced latent proxy leakage 확정.** 직접 latent column 유출은 없지만, 참 CS를 사용하는 workload 배정이 관측 속도에 참값을 실었다.

## 4. D′/fast recovery: 구조적 식별성과 feature 실패의 차이

잠긴 core의 위 임계 `q` 소진과 72시간 선행 휴식 아래, G5/G6의 **서로 다른 지시 속도와 실제 중단시간**으로 두 식 `v=CS + D′/t`를 풀 수 있다. 현재 5개 seed에서 G5/G6 paired stop time이 **600/600명** 존재했고 이전 dry-run과 같은 수치 정밀도 수준으로 CS/D′를 역산할 수 있었다. F1–F3은 선행 bout의 속도·실제시간, 분 단위 gap, probe의 속도·중단시간을 짝지어 fast reserve의 감소와 회복을 역산할 수 있다. probe stop-time 역산 가능 기록은 **1,800/1,800건**이었다. 이 결과는 정확한 합성 stop time 및 현재 생성식이 주어진 구조적 upper bound이며 현실 측정오차·중단 의사결정 불확실성은 평가하지 않는다.

Phase 1 parameter recovery는 이 정보 대신 과거 speed·HR 평균/기울기/SD만 사용했다. k=20의 D′ R²≈−0.144, fast recovery R²≈−0.145는 **필요한 정당한 관측 수행정보가 feature에 없었던 것**과 부합한다. 이 감사는 정보 추가 후 모델이 반드시 성공할 것이라고 주장하지 않는다. 별도 관측 feature 시험 전까지 성능 개선량은 `UNKNOWN`이다. Slow recovery는 S1–S3 gap이 artifact에 있어도 현재 session HR 차이가 noise보다 작아 기존 `NOT_IDENTIFIABLE` 판정을 유지한다.

## 5. 두 Controlled 개념의 분리

| 구분 | `ORACLE_CONTROLLED` (현재) | `DEPLOYABLE_CONTROLLED` (미설계·미실험) |
|---|---|---|
| Workload 배정 | `v=x×true CS_like`. 참 CS는 generator와 감사자만 안다 | 배정 시점 이전에 실제 확보한 정보만 사용. 참 CS/D′/q/회복상수 사용 금지 |
| 용도 | 합성 구조에서 위·아래 임계, 검열, parameter 역산의 **identifiability upper bound**. 동일 조건 반사실적 구조 확인 | 실제 초기 개인 calibration이 미래 관측/정답에 주는 정보 증가 검증 후보 |
| 해석 한계 | 관측 speed가 latent CS를 encode. k=0 현재 speed도 CS 대리변수. CS 회복과 history MAE 부재를 일반적 개인화의 성공/실패로 주장 불가 | 아직 grid·절차·안전성·실제 표본이 정해지지 않아 효과 주장 불가 |

`DEPLOYABLE_CONTROLLED` 설계 **요구사항만** 제시한다. (1) workload 결정에 독립 5 km 기록, 고정 절대속도, **그 시점 이전** calibration의 관측 결과처럼 획득·시각이 검증된 정보만 허용한다. 5 km 기록은 속도 계획의 anchor일 뿐 CS/D′ 확정값이 아니다. (2) 배정 정책의 입력·계산 규칙을 첫 생성/실험 전에 동결하고, train/validation/test에서 미래 성능이나 latent 값을 참조하지 못하게 한다. (3) commanded speed와 실제 speed·duration·중단·회복 간격·HR의 timestamp/품질을 별도 기록한다. 완료 bout의 미관측 한계시간은 right-censored로 다룬다. (4) 같은 평가 session에서 k=0과 history 조건을 비교하며, workload 배정 경로가 참 parameter의 대리변수를 만드는지 먼저 감사한다. (5) CS/D′나 fast recovery의 실사용 식별을 주장하려면 중단시간 또는 그에 준하는 **독립적이고 안전한 수행정보**의 실제 수집·오차모형·중단 기준이 필요하다. (6) 실제 배포 절차에는 현 합성의 소진 유도 grid를 그대로 전용하지 않고 별도 안전·타당성 검토를 거친다. **이번 감사에서는 B의 speed/duration/recovery grid를 정하거나 생성하지 않는다.**

## 6. Phase 1 해석의 보존·제한

**유지:** 잠긴 `ORACLE_CONTROLLED`와 현재 9개 observed feature를 사용한 Ridge에서는 E1–E3 burden/fatigue/condition에 대해 k 증가의 안정적인 MAE 개선을 확인하지 못했다. Naturalistic에서도 지원 범위 내 반복 이력이 일관된 개선을 보이지 않았다. E4의 완료 label 없음, 느린 회복 비식별, 자연발생 자료의 임계 이상 지원 부족도 유지한다.

**철회/보류:** k=20 CS R²≈0.999를 관측 생체신호에서 개인 capacity를 발견했다는 주장으로 사용하지 않는다. 현재 Controlled의 낮은 history 이득을 “개인화 자체가 무효” 또는 “표준화 calibration이 정보가 없다”는 결론으로 확대하지 않는다. D′/fast recovery의 낮은 history R²를 생성기에서 해당 정보가 없다는 뜻으로 해석하지 않는다. 참 CS 기반 속도 배정과 현재 feature 누락이 각각 독립적인 원인이다.

**다음 단계 권고:** 본 실험 추가는 계속 보류한다. 먼저 `ORACLE_CONTROLLED` 결과를 구조 upper-bound로 분리 표기하고, 새로운 `DEPLOYABLE_CONTROLLED`의 workload 배정·관측/검열·측정오차·안전 경계를 **결과 열람 전 사전등록**한다. 같은 결과를 보고 현 generator·parameter나 잠긴 Phase 1 산출물을 수정하지 않는다.
