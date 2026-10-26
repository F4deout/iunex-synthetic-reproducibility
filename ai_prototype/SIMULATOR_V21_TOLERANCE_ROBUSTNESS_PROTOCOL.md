# v2.1 E4 중단시간 관측·행동 불확실성 robustness protocol

상태: **설계안; 구현·생성·학습·실험 미실행**  
작성일: 2026-09-21

## 연구 질문과 동결 경계

독립 5 km 기록 `v5`를 이미 알고 있을 때, 과거 실제 중단시간 정보가 새로운 E4 중단시간 예측에 주는 추가 이점이 반복 session 변동, 생리적 한계 이전의 자발적 중단, 시간 기록 오차에도 남는가? 이는 이미 결과를 본 후 설계한 **별도 합성 robustness 분석**이며 독립적인 사전등록 임상·군 검증이 아니다. 기존 `TOLERANCE_PREDICTION` Phase 1과 information ablation의 protocol, prediction, split, 결과 및 생성기·parameter·history schema는 읽기 전용으로 보존한다. 새 결과는 별도 artifact 경로에 기록한다.

현 core가 계산한 잠재 생리적 한계 `T_phys`는 그대로 둔다. 새 관측 과정은 `T_phys`를 진짜 관측 중단시간과 동일시하지 않는다. 기존 CS-like, D′-like, reserve `q`, recovery, workload, label noise 계수는 승계하되 변경하지 않는다. 새로운 세 불확실성의 난수는 개인 CS/D′/q/recovery 및 기존 생성 난수와 독립된, `(seed, subject, event, process)` 키의 난수열로 생성한다. 세 과정끼리도 독립이다. 실제 사람에게서 독립이라는 경험적 주장은 아니고 원인 분리용 simulation assumption이다.

## 추가 관측·행동 과정

각 calibration 및 E4 event에서 기존 수식으로 주어진 시작 상태와 속도에 대한 `T_phys`를 먼저 계산한다. threshold 이하 등 core가 유한한 q=0 시각을 주지 않는 event에서는 `T_phys=∞`로 둔다. 계획시간 `C`는 기존 grid 그대로다.

1. **Session-to-session tolerance variation:** event마다 `U_tol∼Uniform(0,1)`, `T_tol=(1−a_tol U_tol)T_phys`. 유한한 `T_phys`에만 적용하고 `a_tol`은 `0≤a_tol<1`이다. 이는 개인 capacity/D′ 자체의 변화가 아니라 같은 잠재 한계에 대한 session 실행 변동을 조기 중단 방향으로만 표현한다. `T_phys`보다 늦은 수행을 표현하지 못하는 보수적 상한 모델이라는 제한을 함께 보고한다.
2. **Voluntary stopping:** `B_vol∼Bernoulli(p_vol)`. `B_vol=1`이면 `U_vol∼Uniform(0,1)`, `T_vol=(0.75+0.25U_vol)T_phys`; 아니면 `T_vol=∞`. 유한한 `T_phys`가 없을 때에는 `T_vol=(0.75+0.25U_vol)C`로 정의한다. 자발적 중단은 생리적 q=0 사건과 다른 원인으로 기록하고, 주 endpoint에서는 실제 관측된 **모든 원인 중단**에 포함한다. 실제 한계 추정으로 해석할 때 자발적 중단을 생리적 사건으로 오인하지 않는다.
3. **Timing error:** 실제 종료 `T_stop=min(T_phys,T_tol,T_vol,C)`를 정한 다음, 사건 여부와 원인은 실제 시간으로 확정한다. 독립된 `ε_clock∼Uniform(−d_clock,+d_clock)`초를 기록시각에만 더하고 1초 격자로 반올림한다. 중단 사건의 기록시각이 계획시간 경계에 닿으면 사건 indicator를 유지하면서 기록시각을 `C−1초`로 표기하고 boundary adjustment 수·크기를 별도 보고한다. 완료 event는 기록시간 `C`, `event_observed=0`으로 둔다. 음수 또는 0으로 내려가는 드문 값도 `1초`로 제한하고 별도 보고한다. 이 error는 latent state나 운동 수행시간을 바꾸지 않는다.

`T_actual=min(T_phys,T_tol,T_vol,C)`에서 계획시간 전 종료면 `event_observed=1`, `observed_stop_minutes`는 기록시각이다. 계획시간까지 완료하면 `event_observed=0`, 관측시간은 `C`이며 미관측 hypothetical limit을 만들지 않는다. 서로 같은 시각이면 `physiological → tolerance → voluntary` 우선순위로 원인만 결정한다. 기존 `censored` 필드는 점수 label에 관한 의미가 달라 생존분석의 right-censoring 표지로 재사용하지 않고, 별도 `event_observed`를 둔다. 완료 사례는 **all-cause time-to-stop**의 우측 검열이다. 자발적 중단을 제외한 physiological-limit endpoint를 별도 분석한다면 competing event 방법이 필요하며 이번 주 분석에서는 수행하지 않는다.

관측 중단이 앞당겨지면 이후 reserve/debt/HR 상태도 실제 운동시간에서 이어져야 한다. 따라서 새 builder는 **동결된 core 수식을 그대로 재호출**하여 `T_actual` 시점의 상태를 계산하고 다음 event에 전달한다. 사후 로그의 중단시간만 바꾸고 원래 q=0 상태를 다음 session에 전달하는 지름길은 금지한다. 기존 core가 임의의 조기 종료를 같은 수식으로 계산·전파할 수 없으면 구현을 중단한다. 별도 상태전파 때문에 새 dataset의 후속 latent trajectory는 기존 dataset과 달라질 수 있으나 수식과 parameter는 동일하다. Timing error는 상태전파에 반영하지 않는다.

## 결과 열람 전 고정할 sensitivity register

아래 수치는 사람의 분포 추정치가 아니라 **SIMULATION_ASSUMPTION**이다. `LOW/BASE/HIGH`는 불확실성의 크기 순서이지 현실 빈도의 신뢰구간이 아니다. 기존 결과나 새 모델 성능에 맞춰 바꾸지 않는다.

| 과정 | parameter 및 단위 | LOW | BASE | HIGH | provenance / 근거 상태 |
|---|---:|---:|---:|---:|---|
| 반복 tolerance | `a_tol`, `T_phys`에 대한 최대 조기 종료 비율 | 0.02 | 0.08 | 0.16 | SIMULATION_ASSUMPTION; 실제 E4의 개인 내 반복 분포 없음 |
| 자발적 중단 | `p_vol`, event당 발생확률 | 0.02 | 0.10 | 0.20 | SIMULATION_ASSUMPTION; 실제 중단 사유별 빈도 없음 |
| 자발적 중단 시점 | `T_vol/T_phys` 또는 `T_vol/C`, 무차원 | `Uniform(0.75,1)` | 동일 | 동일 | SIMULATION_ASSUMPTION; 시점 분포 직접 자료 없음 |
| 시간 기록 | `d_clock`, 양측 최대 절대오차 초 | 1 | 3 | 10 | SIMULATION_ASSUMPTION; 선정 장치와 수동 조작 방식 미확정 |
| 출력 분해능 | 반올림 격자, 초 | 1 | 동일 | 동일 | SIMULATION_ASSUMPTION; 실제 장비 사양으로 대체 가능 |

전체 조합은 `LOW/BASE/HIGH`의 **3×3×3=27개**로 고정한다. 각 조합에서 동결된 다섯 final seed `110/220/330/440/550`, 동일 source-person/subject split과 동일 E4 평가 key를 쓴다. 동일 조합의 `k=0`, `k=20 full`, `k=20 no_stop_time`에 완전히 같은 새 관측 로그를 제공한다. 다른 조합도 process별 공통 uniform 난수를 사용해 변화 원인을 추적한다. `no_stop_time`의 제거 column/source 규칙은 동결된 information-ablation plan을 그대로 따른다. `v5`는 세 모델에 똑같이 들어간다. 나머지 k는 이번 핵심 비교에 포함하지 않는다. 27개 중 성능이 좋은 조합만 골라 본문에 쓰지 않고 전부 보고한다.

## 필요한 외부·현장 근거와 해석 한계

반복 tolerance의 범위를 실제 값으로 보정하려면 **동일 개인, 동일 절대속도·경사·계획시간·회복간격에서 반복한 time-to-stop**과 중단 사유가 필요하다. Running time-to-exhaustion 반복 변동은 프로토콜에 따라 다르다. 예를 들어 [Alghannam 등](https://pubmed.ncbi.nlm.nih.gov/26669250/)의 submaximal treadmill 연구는 약 5.4% CV를, [Laursen 등](https://pubmed.ncbi.nlm.nih.gov/17762371/)의 별도 고강도 treadmill 비교는 TTE 조건에서 약 13–15% typical error를 보고했다. 이 값은 현 E4의 `a_tol`이나 군 장병 분포에 직접 대입할 수 없다. 자발적 중단 빈도·시점은 동일 protocol에서 사유, 동기, 안전 중단, 계획 완료를 구분한 반복 기록이 필요하다. 운동 종료가 생리적 한계만으로 정해지지 않을 수 있다는 근거는 [실험 연구](https://doi.org/10.1152/japplphysiol.91324.2008)에서 얻지만 현 `p_vol` 수치를 제공하지 않는다. 시간오차는 채택 장치의 timestamp resolution/accuracy, 시작·종료 trigger 방식, 수동 기록자 간 비교가 필요하다. 현 프로젝트에는 세 항목을 함께 식별할 반복 E4 실측 자료와 장치 사양이 없으므로 수치와 독립성 가정은 모두 simulation assumption으로 남긴다. 총 반복 변동 CV를 세 원인의 개별 분산으로 임의 분해하지 않는다.

## 분석·검열·동결 비교

각 조합에서 기존 20 calibration event와 E4 모두 새 관측 과정으로 생성하되, 기존 workload와 split은 그대로 둔다. Calibration history는 **기록된** actual/stop time, completion, HR 등 잠긴 legitimate observed schema에서 재계산하며 완료자의 hypothetical time-to-limit은 null이다. `k=0`에는 `v5`와 기존 사전 context만, `k=20`에는 calibration-only history만 추가한다. E4 종료시간·사유·현재 HR은 predictor 입력 금지다. Train-only 전처리와 validation-only alpha 선택, 동일 E4 ID-test 및 seed별 paired comparison 규칙은 동결 protocol을 따른다. 관측 과정의 조기 중단 때문에 새 데이터의 HR·상태도 달라질 수 있으므로 원인별 event 수, physiological/tolerance/voluntary stop 비율, E4 완료율, boundary adjustment, observed-minus-physiological stop 분포를 먼저 보고한다. 조합별 종료 support가 없으면 점수를 억지로 산출하지 않고 `NOT_EVALUABLE`로 표시한다.

모든 E4가 중단되면 세 조건을 기존 **log-time Ridge**와 분 단위 MAE/RMSE/R²로 독립 재학습한다. 핵심 효과는 동일 seed·E4의 `MAE(k=0)−MAE(k=20 full)` 및 `MAE(k=20 no_stop_time)−MAE(k=20 full)`이다. 양수는 각각 전체 history 및 stop-time 정보의 추가 이점이다. seed별 방향, 평균±SD와 paired Student-t(df=4) 95% CI를 모두 보고한다. 두 효과의 CI가 0을 넘는지와 크기를 제시하되, 사후에 noise 수준·feature·model을 고르거나 유의성만으로 현실 타당성을 주장하지 않는다.

어느 조합에서든 E4 완료(right-censored)가 생기면 완료자의 `T_phys`를 label로 대체하거나 완료자 제외 MAE를 전체 성능으로 제시하지 않는다. 해당 조합의 세 조건 모두에 동일한, **별도 사전 고정 AFT 평가 명세**를 적용하고 검열 보정 지표를 사용해야 한다. AFT의 분포·규제 grid, 지표 시간 범위 및 최소 event support를 구현 전 amendment에 수치로 잠그지 못하면 그 조합은 `NOT_EVALUABLE`이다. 미검열 조합의 MAE와 검열 조합의 AFT 지표를 직접 비교하지 않는다. 생존 자료의 사건·검열 구분과 지표의 지원범위 제약은 [scikit-survival 공식 가이드](https://scikit-survival.readthedocs.io/en/stable/user_guide/evaluating-survival-models.html)를 따른다.

기존 동결 Phase 1 및 ablation의 MAE는 **idealized exact-stop reference**로 나란히 제시한다. 새 관측 endpoint가 달라졌으므로 기존 MAE와 새 MAE의 차이를 동일 정답에 대한 모델 성능 변화로 해석하지 않는다. 해석은 새 조합 **내부의** k=0/full/no-stop 간 paired 효과, 그리고 그 효과가 exact-stop reference 대비 어떻게 변했는지에 한정한다. 원인별 uncertainty를 따로 식별하려면 추후 실측 자료가 필요하다. 본 설계는 현장 안전 시험이나 군 장병 일반화를 제공하지 않는다.

## 구현 gate 및 변경 기록

**구현 시작 PASS(별도 builder/검증 코드에 한정).** 위 수치·함수·27개 조합을 결과 열람 전에 고정하고, 동결 입력 hash 불변, 기존 core 수식/parameter 불변, 조기 종료 시 같은 수식의 상태전파 가능, latent feature 접근 0, 완료자의 가상 한계시간 누출 0, 동일 평가 key와 train/validation 분리 검사를 구현 전·dry run에서 확인한다. 상태전파가 불가능하거나 검열 조합의 평가 명세가 사전에 잠기지 않으면 해당 예측 실험은 **STOP**이다. 이 PASS는 27개 본 실험을 실행하라는 뜻이 아니며 이번 단계에서는 코드·데이터·결과를 생성하지 않는다. 수치·수식 변경이 필요하면 이 원문을 덮어쓰지 않고 amendment에 변경 시점, 이유, 어떤 결과를 이미 보았는지, 새 SHA-256을 기록한다.

### 동결 입력의 SHA-256

| 읽기 전용 파일 | SHA-256 |
|---|---|
| `SIMULATOR_V21_TOLERANCE_PREDICTION_PROTOCOL.md` | `2b1d8e01176ef58d55979e04d6b137ccf35255540cb19ad78767690252beb588` |
| `SIMULATOR_V21_TOLERANCE_INFORMATION_ABLATION_PLAN.md` | `8202c25b54e56bbb0341dc8db35e1eefcbd8869ce4a54dadee7326b580a460bd` |
| `simulator_v21_running.py` | `d03b854edb53fa95955d440c58c71bf3e7a158c3104753841f073a20046cf586` |
| `artifacts/synthetic_v21_tolerance_prediction_phase1/summary.json` | `2aa7ea5d855567330c72600ad6f27bd1f505c929ed5e24f629e9eead9a9cb2ee` |
| `artifacts/synthetic_v21_tolerance_information_ablation/summary.json` | `8a948cd8a72ed8e24924a8c7c18d4be3e217d93de69e45e693f1ebf151c0cc49` |
