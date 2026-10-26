# Simulator v2.1 `TOLERANCE_PREDICTION` 후속 연구 프로토콜

상태: **설계 동결 대상; 구현·재학습·예측 실험 미실행**  
작성일: 2026-09-21  
연구 질문: **독립 5 km 기록(`v5`)을 이미 알고 있는 상태에서 합법적인 calibration history가 새로운 고강도 러닝 E4의 개인별 지속가능시간 예측을 개선하는가?**

이 질문은 `DEPLOYABLE_CONTROLLED_V1` Phase 1의 E1–E3 점수예측 실패와 E4 tolerance 감사 결과를 **본 뒤** 설정했다. 따라서 이전 결과에 소급하는 사전등록이나 독립적인 군 장병 검증으로 부르지 않는다. 향후 구현에서는 아래 분석·중단 규칙을 결과를 보기 전에 고정하며, 수정이 필요하면 원문을 덮어쓰지 않고 변경 시점과 결과 열람 여부를 기록한 amendment를 만든다. 기존 Phase 1, 원인 감사, generator, parameter, workload grid, history schema, coupling, noise와 split은 읽기 전용으로 보존한다.

## 1. Prediction target과 시점

**예측 시점은 E4 시작 직전**이다. 참 잠재 지속가능시간을 `T*`(분), 계획된 E4 상한을 `C=12분`으로 정의한다. 분석용 관측치는 `time=min(T*, C)`와 `event_observed=1[T*<C]`의 쌍이다. `event_observed=1`에는 중단 시 실제 기록한 `observed_stop_minutes`만 사용한다. `event_observed=0`에는 **관측시간 12분과 `T*>12분`이라는 하한만** 사용하며, 완료한 운동의 가상 한계시간을 생성기에서 읽어와 정답으로 채우지 않는다. 실제 사람에게서는 계획시간 이전의 장비고장·부상·지시 중단 등으로 끝난 사례가 생리적 지속한계 도달과 다르므로 중단 사유를 별도로 기록하고, 사유가 불명확하면 이 endpoint의 관측 사건으로 간주하지 않는다. 현 synthetic core에는 그런 경쟁 중단 사유가 없음을 명시한다.

기존 관측 로그의 `censored=true`는 **운동을 계획시간 전에 중단하여 0–10 점수 label을 만들지 않았다는 뜻**이다. 이것은 time-to-limit의 *right-censored*와 반대 방향이다. E4의 현재 다섯 seed에서 각 120/120, 총 600/600이 계획시간 전에 중단되었으므로 **time-to-limit 사건시간은 전부 관측**되었고 우측 검열은 0건이다. 기존 E4 0–10 burden/fatigue/condition label은 사용하지 않는다. 완료된 session의 관측시간·사건 indicator 구분은 [scikit-survival의 survival-data 정의](https://scikit-survival.readthedocs.io/en/stable/user_guide/00-introduction.html)와 일치한다.

## 2. 고정 데이터와 입력 경계

현 후속 분석의 데이터는 동결된 `DEPLOYABLE_CONTROLLED_V1`의 다섯 final seed `110, 220, 330, 440, 550`을 **같은 generator/config로 재현**한 E4만이다. 한 seed당 train/validation/ID-test subject 수는 `72/24/24`, 각 subject의 E4는 1건이다. 생성·분할·평가 session key의 hash는 동결 manifest와 일치해야 하며 기존 artifact를 덮어쓰지 않는다. E4의 `u=1.10`, commanded speed `u×v5`, 계획 12분, 20개 calibration event 및 E1–E4 순환 순서는 그대로 유지한다. 현재 E4 결과 분포와 latent 상관을 이미 열람했으므로 이 다섯 seed의 ID-test는 **모델 선택에는 사용하지 않더라도 연구 질문 선택에 대해 미열람 holdout은 아니다**. 모든 결과는 합성환경의 탐색적 후속 분석으로 표기한다.

모든 `k=0/1/3/5/10/20`에 동일하게 제공하는 **E4 시작 전 context**는 출처와 날짜가 검증된 `v5_kmh` 및 E4의 사전에 정해진 evaluation 순서다. `commanded_speed_kmh=1.10×v5_kmh`, `u=1.10`, 계획 12분, 예정 gap은 기록·검증하지만 이번 E4 전용 predictor에서는 중복·상수이므로 별도의 자유 feature로 넣지 않는다. `v5`가 이미 개인 capacity의 강한 prior라는 점을 유지한다. 현재 E4의 실제 속도, 실제 운동시간, 완료/중단 여부, 중단시간, session-average HR, E4에서 측정될 미래 pre/post/recovery HR은 **시작 전에는 알 수 없으므로 predictor 입력 금지**다. 현재 core는 별도 pre-E4 HR을 생성하지 않으므로 그 값을 만들어 넣지 않는다.

`k`는 E4 이전의 **최근 k개 calibration event** 수이며 안정 event도 센다. 기존 `build_v21_deployable_controlled.history_features`의 관측 가능한 고정 schema 전체를 그대로 사용한다: 안정 HR, 속도 조건부 평균 HR, 실제 완료/중단 및 관측 중단시간, G5/G6의 `CS_pair_candidate`·`Dprime_pair_candidate`와 유효 flag, F/S probe 및 gap별 회복 요약, 시간·품질의 실제 사용 가능한 항목. `v5`는 역사 feature와 별개로 모든 k에 한 번만 넣는다. 완료 calibration event의 hypothetical time-to-limit은 계속 null이다. E1–E3가 E4보다 먼저 실행되었더라도 **평가 event의 관측값·label은 모두 E4 history에서 제외**한다. 기존 k-window와 누수 검사, null/available flag를 변경하지 않는다.

금지 입력: 참 `CS-like`, `D′-like`, `rho`, `q_start/q_end`, `tau_fast/tau_slow`, strain, debt, 상대강도 `speed/true_CS`, 생성기 `limit_minutes`, 비관측 `u_b/u_w`, 보고 bias/noise, subject ID 또는 source-person ID를 인코딩한 proxy, E4의 현재·미래 결과. 참값은 **구조 감사 파일에만** 존재할 수 있고 predictor용 feature matrix 생성 함수에서 접근 불가해야 한다. 배정함수 역시 `u×v5` 외 latent를 조회하지 않는다.

## 3. 기준선, 모델, 평가

현재 E4는 모든 사건시간이 실제 관측되어 있으므로 **우선 단순 양의 시간 회귀를 사용**한다. 우측 검열 0건에서 검열을 가정한 생존모델이 필수는 아니다. `log(T)`을 target으로 한 Ridge를 기준 모델로 고정하고 예측시간은 `exp(predicted log(T))`분으로 되돌린다. 이는 양의 예측시간을 보장하기 위한 사전 결정이며 성능을 보고 직접시간/로그시간 중 좋은 것을 고르지 않는다. 비교 모델을 추가하지 않는다.

- **무정보 기준선:** train subject의 관측 E4 stop time 중앙값(분)을 모든 validation/test subject에 동일하게 예측. ID-test 중앙값은 사용하지 않음.
- **주 비교 기준선 `k=0`:** 모든 k와 동일한 `v5_kmh`와 E4 evaluation 순서만 사용하는 log-time Ridge.
- **History 조건:** k별 고정 history schema를 위 k=0 context에 추가한 동일 계열 Ridge. k마다 feature 생성, train-only median imputation·결측 indicator·표준화, validation에서 alpha `{1,10,100}` 중 **분 단위 MAE 최소** 선택, train+validation 재학습을 독립 수행. ID-test는 선택에 사용하지 않음.

**주 지표**는 ID-test의 관측 중단시간 MAE(분)와 같은 seed·같은 24명 E4의 paired `MAE(k=0)−MAE(k)`이다. 양수는 history 이득이다. RMSE(분), R², seed별 효과 방향을 함께 보고한다. 각 target은 E4 time-to-limit 하나이며 0–10 score는 없다. 다섯 seed의 각 metric과 paired difference에 대해 평균±표본 SD, 자유도 4의 양측 Student-t 95% CI를 보고한다. 모든 k에서 test subject/session key와 target이 정확히 같아야 하고, 결측·완료 support 및 prediction 범위도 seed별로 저장한다. 이력을 늘리면 개선된다는 성공 기준은 두지 않는다. 절대 MAE의 작은 차이만으로 실제 사용 가치를 주장하지 않고, 효과 크기·CI·seed 방향을 함께 해석한다. 원시 예측, split/config/code/protocol hash를 새 artifact에 저장한다.

`k=20`에서 G5/G6 실제 중단시간으로 구성한 CS/D′ 후보가 유효하다는 사실을 별도로 병기한다. `k=10→20` 변화가 이 후보·F probe 추가와 동반되는지 기술하되, 후보를 사후 삭제하거나 검열되지 않은 정확한 합성 중단시간의 구조적 역산을 실제 장치 식별성으로 해석하지 않는다. 이번 목적은 이들 legitimate observed history의 **현재 합성 E4에 대한 추가정보** 확인이지 실제 사람의 CS/D′ 진단이 아니다.

## 4. 향후 완료 사례가 생기는 데이터의 검열 대응

새 dataset에서 계획시간까지 완료한 사례가 생기면 그 사례의 진짜 `T*`는 알 수 없다. **완료자만의 가상시간을 사용하거나 중단자만 남겨 MAE를 주 지표로 계산하지 않는다.** 그때는 결과를 보고 현재 모델을 임의 전환하는 대신 별도 사전등록 amendment와 독립 평가를 마련한다. 위 `time,event_observed` schema와 동일한 baseline/history 경계로 right-censored likelihood를 사용하는 **log-normal AFT**를 최소 후보로 둔다. 훈련 fold 안에서만 검열·시간 분포와 전처리를 추정하고 validation에서 미리 고정한 소규모 규제 grid를 선택한다. AFT는 양의 event time에 대한 예측 중앙값과 생존함수를 제공하며, 완료 관측의 likelihood는 `P(T*>C)`로 반영한다. AFT와 우측 검열 자료를 다루는 방법은 [lifelines의 공식 설명](https://lifelines.readthedocs.io/en/latest/Survival%20Regression.html)을 따른다. 분포 적합성과 event/censoring support가 불충분하면 그 조건을 `NOT_EVALUABLE`로 보고하며 완료자를 임의 label로 바꾸지 않는다.

검열이 있는 별도 연구의 주 평가는 사전에 고정한 시간 범위에서 **검열 보정 integrated Brier score**(예측 생존확률의 정확도·보정), 보조로 IPCW concordance(순위)를 사용한다. 예측 중앙값의 MAE는 실제 중단시간이 관측된 사례에 대한 보조 기술값으로만 두고 전체 집단의 주 지표로 사용하지 않는다. 시간 범위는 훈련 자료의 검열 지원 범위 안에서 새 프로토콜에 고정한다. IPCW는 검열 과정에 대한 가정과 지원 범위가 필요하며, 단순 concordance만으로 시간 예측의 보정 상태를 판정하지 않는다. 지표의 정의와 검열 시 주의점은 [scikit-survival 공식 평가 안내](https://scikit-survival.readthedocs.io/en/stable/user_guide/evaluating-survival-models.html)를 따른다. 현재 E4에는 우측 검열이 없으므로 이 AFT/검열 지표를 **이번 본 실험에 끼워 넣지 않는다**.

## 5. 해석 범위와 실행 전 PASS/STOP

현재 E4로 검증 가능한 주장은 **독립 5 km 기록과 고정된 고강도 E4 workload가 주어진 합성환경에서, 과거 20개 calibration event가 같은 생성기의 새 E4 중단시간 예측에 추가 정보를 제공하는지**에 한정된다. E4가 모두 중단된 지원 구간의 시간 오차만 평가한다. 12분을 넘겨 완료하는 사람의 실제 한계시간, 안전한 운동 처방, 군 임무수행능력, 일상 피로, 장치 센서의 성능은 검증하지 못한다. 현재 generator는 q=0을 정확한 중단으로 만들고 G/F calibration에서도 이상화된 실제 중단시간을 제공한다. 실제 사람의 자발적 종료, 동기·노면·경사·하중·기온, 측정오차, 시간별 속도 변화 및 반복검사 신뢰도는 여기서 입증되지 않는다. 참 CS/D′를 쓰지 않는 배정만 실제 시스템에 이전 가능한 설계 요소이며, **현 G/F 소진 grid를 실제 장병에게 그대로 적용하는 안전 승인으로 해석하지 않는다**.

**구현 시작 `PASS` — 새 감사/예측 runner를 별도 경로에 만드는 데 한정.** 조건은 (1) 위 동결 hash와 생성·분할 hash 일치, (2) E4의 현재/미래 변수와 모든 latent의 predictor 입력 0건, (3) `v5`가 모든 k에 동일하게 존재, (4) calibration-only history와 동일 E4 평가 key, (5) 현 다섯 seed에서 event_observed 600/600 확인, (6) 전처리·alpha 선택은 train/validation만 사용, (7) 기존 파일 무변경이다. 하나라도 실패하면 예측 학습 전에 `STOP`하고 원인을 보고한다. 이 `PASS`는 실험 결과가 좋을 것이라는 판정이 아니며, 이번 요청에서는 **구현·데이터 생성·예측 실험을 실행하지 않는다**.

### 이 프로토콜의 입력 동결 해시(SHA-256)

| 읽기 전용 입력 | SHA-256 |
|---|---|
| `SIMULATOR_V21_DEPLOYABLE_CONTROLLED_PROTOCOL.md` | `b8052bacf424a845ccec128b1416deb108007b0b34db9d19cd020329becd1479` |
| `build_v21_deployable_controlled.py` | `f24bde126cce71a63b83bdefaf5835292a1726409d3a05327f6337e0cce156b1` |
| `simulator_v21_running.py` | `d03b854edb53fa95955d440c58c71bf3e7a158c3104753841f073a20046cf586` |
| `artifacts/synthetic_v21_deployable_phase1/summary.json` | `02798a13bbf6c6fe8d7c8158a6c3e72ea58abb3555db2883e03bdd4762615101` |
| `artifacts/synthetic_v21_deployable_phase1/artifact_manifest.json` | `3cd3be330e776951de355818ef4c5f3877207d8206bd27a8f870689079f307ac` |
| `artifacts/synthetic_v21_deployable_history_cause_audit/summary.json` | `d4e7b422d5cc6077e0b8e9a1959a62d255ab645e001cff09e5511a08b6ebf343` |
| `artifacts/synthetic_v21_deployable_history_cause_audit/artifact_manifest.json` | `e3fd3a0e16e161e8ca5968c3d6e0bb739f76051e1e3d595d7ce2393fe65dacdb` |
