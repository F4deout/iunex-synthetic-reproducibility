# Simulator v2.1-running dataset protocol — NATURALISTIC / CONTROLLED_PERSONALIZATION

상태: **데이터·평가 설계 사전등록; 미구현·미생성·본 실험 미실행**  
작성일: 2026-09-21  
기존 잠금 유지: `SIMULATOR_V21_RUNNING_PROTOCOL.md` (`4594babf1e5cef0fc69a2879d7bb5b0a374bfde4abefd1661f4de9fb87aba129`), `SIMULATOR_V21_RUNNING_PARAMETERS.md` (`be7eed3eae78a3a2e56fa3e07ee7101afa5780ba753b13bde0ba28f07bb99823`), `SIMULATOR_V21_RUNNING_PARAMETERS_AMENDMENT_01.md` (`1e135e799dd3b776838b78b26b160fdc43d380878287899b99d8fd345cf21540`). `simulator_v21_running.py`, v2 코드·parameter·모든 결과도 변경하지 않는다. 이 문서는 **generator parameter amendment가 아니다**.

## 1. 설계 동기와 비교 질문

이미 열람한 v2.1 dry run(`artifacts/synthetic_v21_running_dryrun/validation.json`)은 2,880 session 중 임계 이하 98.3%, 임계 이상 1.7%, 완료된 임계 이상 0건이었다. 또한 동일 PMData workout template가 train/validation/test에 재사용되었다. 이 결과와 원래 artifact는 **보존**한다. 여기서 생성식의 계수·burden coupling·label noise를 바꾸지 않고, **입력 설계가 식별 가능성을 어떻게 제한하는지** 두 dataset으로 구분한다.

1. `NATURALISTIC`: 현재 소규모 PMData-like 러닝의 speed–duration–5 km anchor 관계 및 낮은 supra-threshold 비율을 그대로 둔 관측 설계. 자연발생 자료만으로 개인 parameter를 식별할 수 있는지 확인.
2. `CONTROLLED_PERSONALIZATION`: 같은 합성 subject의 잠재특성·같은 잠긴 생성식에 **사전 고정된 외부 workload 일정표**를 적용한 식별성 시험. calibration 이력을 추가하면 복원 가능성이 달라지는지 확인. 좋은 결과를 강제하는 자료가 아니며, 실제 인간에게 이 일정표를 수행시키라는 지침이 아님.

두 dataset은 같은 120개 합성 subject profile, 동일한 72/24/24 subject fold, 동일한 generator parameter와 burden WEAK/BASE/STRONG, 같은 label-noise 설정을 쓴다. workload 일정만 다르다. 기존 dry run의 subject/row를 사후 재배치해 새 결과인 것처럼 쓰지 않고 **새 dataset version과 manifest**를 만든다. 본 문서 이후 grid·분할 규칙·검열 처리의 변경은 별도 dated amendment와 결과 열람 여부를 기록해야 한다.

## 2. NATURALISTIC: 원자료 지원범위 보존

PMData의 시각 매칭 러닝 **64개 workout, 7명 제공자**를 현재 생성기의 경험적 입력 pool로 유지한다. 각 원본의 `source_subject`, 날짜, 5 km 기준속도, `speed_kmh`, `duration_minutes`, 이전 러닝 간격을 함께 보존한다. 원본 speed나 duration에 jitter·보간·상향 재가중을 하지 않는다. 개인 내 workout 선택은 현재처럼 해당 원본 제공자의 실제 workout만 대상으로 하며, 제공자 선택의 원본 workout 수 비례 규칙을 유지한다. 모든 원본 workout은 출처와 값이 동일하게 pool에 남는다. **구현 후 실현된 fold별 분포가 다를 수 있으므로** 전체·fold별 속도/시간/`speed/v5` 분위수, source 제공자 수, 임계 이상 비율을 보고한다. 분포 차이를 없애려고 위험 강도 session을 추가하거나 재추출하지 않는다.

원본에서는 완료한 러닝이더라도 잠긴 합성 q 모형이 계획 duration 전에 0이 되면 합성 label은 검열하고 `empirical_completed_but_simulator_censored`로 센다. 원본 완료 사실과 모델의 합성 한계가 충돌한 비율을 삭제·수정하지 않고 보고한다. 이 dataset은 D′ 경로가 사실상 관측되지 않으면 `NOT_IDENTIFIABLE`이라는 결과를 허용한다. 기존 dry-run 수치와 파일은 그대로 두고, 새 분할 적용분은 `NATURALISTIC_GROUPED_V1`로만 저장한다.

## 3. CONTROLLED_PERSONALIZATION: 잠긴 20개 calibration event

시뮬레이터가 이미 가진 `CS_like_i`만 **workload 배정자에게** 사용해 `v=x×CS_like_i`의 절대속도(m/s)를 정한다. observed predictor에는 `CS_like_i`, `x`, `D′_like_i`, 생성기 난수, protocol cell의 latent 값이 들어가지 않는다. 실제 사람이 자신의 CS를 이미 알고 있다는 주장이 아니다. 환경은 잠긴 core와 같이 중립·평지·비하중이다. 속도와 duration 외의 생리·target 생성식은 변경하지 않는다. 각 bout는 현재 core의 일정속도 session이며, `q=0` 이후의 완료 label은 없다. 중단 시 `time_to_limit`, 계획시간, 실제시간, 완료/검열을 기록한다.

| calibration event | 속도 조건 `x=v/CS_like_i` | 계획 duration | 이전 event와의 간격 | 목적 |
|---|---:|---:|---|---|
| R1 | 0 (안정 관측) | 0분 | 시작 전 | HR baseline 관측; burden label 없음 |
| G1 | 0.70 | 6분 | 72시간 | 아래 임계 HR 반응 |
| G2 | 0.90 | 12분 | 72시간 | 아래 임계·시간 효과 |
| G3 | 1.00 | 6분 | 72시간 | 임계 근처 경계 |
| G4 | 1.05 | 3분 | 72시간 | 위 임계의 짧은 노출 |
| G5 | 1.05 | 20분 | 72시간 | 같은 속도의 duration/검열 |
| G6 | 1.10 | 12분 | 72시간 | 다른 위 임계 속도의 검열 |
| F1a/F1b | 1.10 / 1.10 | 3분 / 12분 | bout 사이 **1분** | fast reserve 회복 |
| F2a/F2b | 1.10 / 1.10 | 3분 / 12분 | bout 사이 **4분** | fast reserve 회복 |
| F3a/F3b | 1.10 / 1.10 | 3분 / 12분 | bout 사이 **16분** | fast reserve 회복 |
| R2 | 0 (안정 관측) | 0분 | 앞 블록 종료 후 72시간 | 회복 뒤 안정 HR 재확인; 잔여 debt 가능성을 기록, burden label 없음 |
| S1a/S1b | 0.90 / 0.70 | 12분 / 6분 | bout 사이 **6시간** | slow debt 회복 |
| S2a/S2b | 0.90 / 0.70 | 12분 / 6분 | bout 사이 **24시간** | slow debt 회복 |
| S3a/S3b | 0.90 / 0.70 | 12분 / 6분 | bout 사이 **72시간** | slow debt 회복 |

총 **20개 과거 event = 안정 관측 2 + 러닝 bout 18**이다. G1–G6, F1–F3, S1–S3 **블록 사이**는 72시간으로 고정한다. 순환 이동량은 `int(SHA256(UTF-8(subject_id + "|" + block_letter)).hexdigest(), 16) mod n`으로 계산한다. `block_letter`는 G/F/S/E이고 `n`은 각각 6/3/3/4다. G 여섯 조건과 F·S의 각 세 gap 블록을 이 값만큼 순환 이동한다. 각 블록 내부의 선행 bout→gap→probe 순서는 고정한다. 순서 결정에는 target·HR·검열 결과를 사용하지 않는다. 빠른 회복 gap `1/4/16분`은 잠긴 `tau_fast` 2/4/6분을 가로지르도록, 느린 gap `6/24/72시간`은 `tau_slow` 12/24/48시간을 가로지르도록 **결과 확인 전에 선택한 합성 시험 grid**다. 문헌에서 현재 인원에게 확정된 운동 처방값이 아니다.

held-out 평가 event는 calibration 후 72시간 간격으로 다음 **4개를 고정**한다: `E1=(0.70,6분)`, `E2=(0.90,12분)`, `E3=(1.05,3분)`, `E4=(1.10,12분)`. 이 네 조건에도 위의 E 순환 이동량을 적용한다. 각 `k=0/1/3/5/10/20`에서 같은 E1–E4의 완료 label만 target 평가에 쓰며, 검열된 E는 모든 k에서 동일하게 제외하고 그 수를 별도로 보고한다. 현재·미래 E 관측이나 label은 해당 E의 history에 넣지 않는다. `k`는 평가시점 이전의 최근 calibration **event 수**이고 안정 R1/R2도 센서 관측으로 센다. Naturalistic에서는 같은 `k`가 최근 러닝 event 수다. 두 종류의 event 의미 차이를 숨기지 않는다.

실제 평가 전에 G5/G6에서 각 개인의 `time_to_limit`가 둘 다 관측되는지, F probe가 gap별로 상태 차이를 보이는지, S probe의 상태 신호가 보고오차보다 구별되는지 **분포만** 확인한다. 어느 조건에서 식별이 실패해도 grid·parameter·noise를 바꾸지 않는다. G5/G6이 전부 완료되면 CS/D′에 대한 정확한 점 추정보다 bounds와 `NOT_IDENTIFIABLE`을 보고한다. F lead가 조기 검열되어도 그 사실과 q 상태를 보존하고 후속 probe 일정은 변경하지 않는다. 단순 반복시간에 따른 적응/훈련 효과는 현 core에 없으므로 실제 장기간 과업의 학습·체력 변화까지 재현한다는 주장을 하지 않는다.

## 4. source-template 누수 차단과 분할

`source_template_id = source_subject + ":" + Fitbit logId`로 원본 workout 단위를 고유화한다. **Fitbit logId가 없거나 동일 ID가 서로 다른 workout을 가리키면 추정 ID를 만들지 말고 STOP**한다. PMData 매칭 감사의 `log_id`와 원본 exercise를 읽어 별도 dataset builder가 ID를 붙인다. 기존 `capacity.py`와 generator를 수정하지 않는다.

64개 `source_template_id`를 `SHA256("v21-naturalistic-group-v1|"+source_template_id)` 오름차순으로 정렬하고 처음 **38개 train, 다음 13개 validation, 마지막 13개 ID-test**에 잠근다. fold를 정한 후 합성 인원 **72/24/24명**을 만든다. 각 합성 인원은 자신의 fold에 존재하는 하나의 `source_subject`만 선택하고, 그 제공자의 해당 fold에 배정된 템플릿에서만 20개 과거 workout 및 평가 session을 추출한다. 제공자 선택은 fold 내 원본 workout 수에 비례한다. 어느 `source_template_id`도 둘 이상의 fold에서 읽거나 복제하지 않는다. 동일 synthetic subject/session도 fold를 건너지 않는다. preprocessing·모델/feature 선택은 train/validation에만 의존하고 ID-test는 최종 일회 평가 전까지 열지 않는다.

**이 규칙은 source workout 중복을 없애지만 source 사람 중복까지 보장하지 않는다.** 7명 제공자의 서로 다른 workout이 여러 fold에 배정될 수 있으므로 `source_subject` 교집합과 5 km anchor의 공유를 별도 `WARNING`으로 기록하고, Naturalistic의 subject-generalization 성과를 독립 인원 실증이라고 부르지 않는다. 더 엄격한 source-person 단위 검증은 7개 독립 group만 남아 안정적인 72/24/24 평가가 어렵다. 이 자료만으로 군 집단 일반화 주장을 하지 않는다. Controlled에는 원본 workout template를 **하나도 사용하지 않는다**(`source_template_id=null`, `protocol_cell_id`만 저장). 두 dataset은 같은 합성 개인 latent profile과 fold를 공유하되, controlled workload는 위의 고정표에서만 생성한다.

검증 assertion: `train∩validation∩test`의 subject/session/template 각 쌍별 교집합은 모두 0; Controlled template 수는 0; profile·latent·`x`·현재/미래 label은 observed history에 없음. fold별 원본 제공자 수, template 수, 표본 속도·시간 support와 중복률을 모두 manifest에 기록한다. 원본 dry run을 덮어쓰지 않는다.

## 5. 무엇을 식별할 수 있는가

개인 특성 복원은 **train에서만 학습한 감사 전용 복원기**를 validation 합성 subject에 적용해 R²·상관·오차·식별 가능 비율로 보고한다. `k=0/1/3/5/10/20` 모두 같은 평가 subject와 E event를 사용한다. Naturalistic과 Controlled의 target MAE는 입력 분포가 달라 직접 우열로 해석하지 않고, **동일한 잠재 개인 parameter의 복원 가능성**과 각 dataset 내부에서의 history 효과를 분리 보고한다. 두 dataset의 대상자 프로필과 외생 난수 대응표는 감사용으로만 보관하며 observed predictor에 넘기지 않는다.

| 개인 parameter | 필요한 관측 조건 | Naturalistic 예상 식별성 | Controlled 조건부 식별성 |
|---|---|---|---|
| HR baseline | 반복 안정 시 HR | 러닝 session 평균 HR만으로는 baseline과 운동반응 혼재 | R1/R2의 안정 HR 관측으로 추정 가능. R2에는 잔여 debt가 있을 수 있고 2회뿐이라 불확실성 큼 |
| CS-like capacity | 외부 속도가 다른 두 개 이상의 **위 임계 time-to-limit** 또는 독립 수행기록 | 현재 완료된 임계 이상 0건으로 `NOT_IDENTIFIABLE` 가능성 큼 | G5/G6의 서로 다른 절대속도에서 실제 중단시간이 둘 다 관측될 때 `distance = CS×time + D′`의 CS 후보 식별 가능. 완료만 기록되면 bounds만 가능 |
| D′-like reserve | CS와 독립적인 두 위 임계 속도·중단시간, 초기 q 상태 확인 | 임계 위 소진정보 부재로 `NOT_IDENTIFIABLE` | G5/G6의 **두** limit가 있으면 CS와 함께 조건부 식별; 한 속도만 censored이면 CS–D′ trade-off 잔존 |
| 개인 HR response | 알려진 외부속도의 다수 단계, 안정 HR, 반복 측정 | 좁은/불균형 속도 support에서 HR slope와 CS가 혼재 | G1–G4 및 반복 S probe로 개인 speed→HR 관계를 추정. **CS 미식별 시** HR 기울기와 CS를 따로 식별했다고 주장 금지 |
| fast reserve recovery | 고정된 선행 소진, 서로 다른 **분 단위** gap, 같은 위 임계 probe의 완료/limit | 하루 이상 간격이 대다수라 τ가 사실상 포화 | F1–F3의 1/4/16분 gap과 동일 probe로 조건부 추정. probe가 모두 같은 완료결과면 `NOT_IDENTIFIABLE` |
| slow fatigue/debt recovery | 같은 선행 load와 probe, **시간–일** 단위 gap, 반복 HR·독립 피로 보고 | 간격은 있으나 중간 관측/동일 조건 반복이 부족 | S1–S3의 6/24/72시간 gap으로 조건부 추정. 보고오차가 차이를 압도하면 결과는 불확실/무효 |

HR만으로 CS와 개인 반응을 동시에 식별할 수 없다는 점이 핵심이다. 잠긴 평균 HR식에서는 속도 기울기에 `(120 + delta_i/0.70)/CS_i`가 함께 들어간다. 이를 분리하려면 독립적인 수행한계 정보가 필요하다. `D′`와 fast τ도 q 자체가 관측되지 않으므로 completion/limit 정보가 약하면 높은 생성기 참값 복원 R²를 기대하지 않는다. History가 참 parameter를 복원해도 burden 예측 개선을 보장하지 않으며, 세 coupling 결과를 모두 보존한다.

## 6. 실제 군 시스템으로의 변환 범위

이 Controlled grid는 **합성 모델 식별성 연구용**이며, G5/G6이나 F probe의 `q=0`까지 러닝을 실제 장병에게 요구하는 초기 스테이션 절차가 아니다. 실제 초기 개인 calibration으로 옮길 수 있는 부분은 안정 HR 반복, 기록된 외부속도·시간의 짧은 표준화 subthreshold 러닝, 일정 시점의 재확인, 신호 품질·관측시각 기록이다. 실제 대상자의 CS를 모르므로 `x=0.70/0.90` 같은 조건을 직접 지시할 수 없다. 먼저 독립적 수행기록·안전한 외부속도 기준을 정하고, CS/D′는 별도의 적합한 검증 절차가 없는 한 `UNKNOWN`으로 유지해야 한다. 훈련/현장 적용 가능성은 실제 대상자·안전절차·장치 측정의 별도 연구 과제다.

## 7. 구현 시작 판정과 잠금

**`PASS` — 두 synthetic dataset builder와 split/누수 검사 구현에 한정.** 입력 template ID 무결성과 위 grid·20-event 순서·fold 분할을 코드에 그대로 옮길 수 있다. 기존 generator 수식·parameter를 변경하거나 본 실험을 실행해도 된다는 뜻은 아니다. `source_template_id`를 원본에서 신뢰성 있게 추출하지 못하면 Naturalistic builder는 즉시 `STOP`; 두 supra speed에서 limit 정보가 없으면 capacity/D′ 복원 분석은 `NOT_IDENTIFIABLE`. 첫 dry run 뒤 분포·식별성·누수를 확인하고 본 실험 진행 여부를 따로 판정한다.

이 문서를 SHA-256 sidecar `SIMULATOR_V21_RUNNING_DATASET_PROTOCOL.sha256`로 잠근다. 결과를 본 뒤 workload grid, template 배정 또는 검열 규칙을 바꾸려면 원문을 덮어쓰지 말고 변경 전 hash·열람 결과·이유가 있는 별도 amendment를 작성한다.

근거 범위: [Kordi 등(2019)의 반복 거리별 전력시험에 따른 CS/D′ 산출](https://pubmed.ncbi.nlm.nih.gov/30427230/), [Jang 등(2016)의 개인별 speed–HR 보정 비교](https://pubmed.ncbi.nlm.nih.gov/28269462/), [간헐 러닝에서 W′ 회복을 관측한 실험](https://pubmed.ncbi.nlm.nih.gov/31776696/). 이 연구들의 실측 평균·시간상수를 현재 군 인원이나 본 합성 grid의 정답으로 전용하지 않는다.
