# Simulator v2.1-running: 수치·근거 사전등록부

상태: **parameter 후보 사전등록; 구현·데이터 생성·본 실험 전**  
작성일: 2026-09-21  
상위 문서: [`SIMULATOR_V21_RUNNING_PROTOCOL.md`](SIMULATOR_V21_RUNNING_PROTOCOL.md), SHA-256 `4594babf1e5cef0fc69a2879d7bb5b0a374bfde4abefd1661f4de9fb87aba129`  
범위: 러닝만. 기존 Simulator v2의 parameter·결과는 승계하거나 수정하지 않음.

## 읽는 규칙

* `EMPIRICAL_REFERENCE`는 현재 PMData의 소수 비군집단에서 계산 가능한 **참고 분포**이다. 군 장병 population estimate나 개인의 실측 CS/D′가 아니다. `LITERATURE_CONSTRAINT`는 구조·방향·대략적 규모의 제약이며 타 연구의 평균을 현재 인원에게 대입하지 않는다. `SIMULATION_ASSUMPTION`은 결과 확인 전에 정한 민감도 제안이며 생리학적 참값이 아니다. `UNKNOWN`은 숫자를 정당화할 자료 또는 작동 정의가 부족한 항목이다.
* 표의 LOW/BASE/HIGH는 **parameter 값의 순서**다. `RPE reliability` 행만 가독성을 위해 신뢰도 LOW/BASE/HIGH 순서로 기록한다. 실제 실험 시에는 BASE와 critical family별 LOW/HIGH를 모두 보고하고, 좋은 결과가 나온 조건만 선택하지 않는다. 여러 family의 동시 변화는 이 파일만으로 사전등록되지 않았다.
* 개별 5 km 기준속도 `v5_i = 5000/(60 × 기록_분)` m/s. `CS_like_i = rho_i × v5_i`이며 `rho_i`는 별도 합성 가정이다. `v5_i`와 `CS_like_i`는 같은 변수가 아니다. `Dprime_like_i`도 단일 5 km 기록에서 역산하지 않는다.
* 속도·시간·거리·심박의 측정 정의를 섞지 않는다. 현재 러닝 HR은 **session 평균 HR**이다. 이것을 즉시 post-HR 또는 특정 속도 구간의 steady-state HR로 간주하지 않는다.
* 완주한 러닝 기록 64건의 `speed/v5` 중앙값은 0.684, 5–95백분위는 0.541–0.841이다. 따라서 경험적 러닝 session 대부분은 아래의 CS-like 후보보다 낮은 속도일 수 있다. 그 경우 reserve 소진·D′의 예측 기여가 작게 나와도 결과로 보존한다. supra-threshold 사례를 늘리기 위해 입력 속도나 `rho`를 사후 변경하지 않는다.

## Parameter register

`같음`은 세 민감도 조건 모두 같은 경험적 기준값이라는 뜻이다. 분위수는 표본 분위수이며 정규분포의 모수로 오인하지 않는다. `critical`은 연구 결론·history/OOD 효과를 바꿀 수 있는 가정이다.

| ID·parameter | 값/분포·단위 | LOW | BASE | HIGH | provenance·근거 | critical |
|---|---|---:|---:|---:|---|---|
| E01 독립 5 km 기준속도 `v5` | 날짜가 확인된 13명 경험분포, km/h | 같음: Q05 7.66 | 중앙값 10.15 | 같음: Q95 15.54 | **EMPIRICAL_REFERENCE**: PMData `participant-overview.xlsx`; 전체 범위 6.32–15.97. CS로 동일시 금지 | 예: 개인 capacity anchor |
| E02 완료 러닝 속도 `v` | 64개 시각 매칭 session 경험분포, km/h | 같음: Q05 6.98 | 중앙값 9.52 | 같음: Q95 11.21 | **EMPIRICAL_REFERENCE**: Fitbit 거리÷시간; 전체 범위 1.69–11.65. 1.69는 검토 대상 극단값으로 숨기지 않음 | 예: threshold 초과 빈도 |
| E03 러닝 지속시간 | 같은 64개 session 경험분포, 분 | 같음: Q05 25.65 | 중앙값 51.34 | 같음: Q95 105.19 | **EMPIRICAL_REFERENCE**: Fitbit duration. 전체 15.93–148.33 | 예: reserve·debt 누적 |
| E04 같은 인원의 러닝 간격 | 57개 날짜 차이, 일 | 같음: Q05 1 | 중앙값 6 | 같음: Q95 27.2 | **EMPIRICAL_REFERENCE**: 64개 매칭 기록의 같은 인원 연속 러닝; 전체 1–97일. 야간·수면·그 사이 타 활동은 미포착 | 예: slow debt |
| E05 안정 HR 기준 | 14명의 일별 resting-HR 개인 중앙값 경험분포, bpm | 같음: Q05 49.32 | 중앙값 59.40 | 같음: Q95 69.01 | **EMPIRICAL_REFERENCE**: 동결된 P01 calibration. 러닝 직전 HR 아님 | 예: 개인 baseline |
| E06 완료 러닝 평균 HR | 매칭 64건 경험분포, bpm | 같음: Q05 134.3 | 중앙값 148 | 같음: Q95 163 | **EMPIRICAL_REFERENCE**: Fitbit session 평균; 전체 128–180. 단독으로 speed→HR 함수 식별 불가 | 예: HR sanity anchor |
| E07 운동부담 참고 RPE | 매칭 64건 0–10 자기보고, 점 | 같음: Q05 4 | 중앙값 6 | 같음: Q95 8 | **EMPIRICAL_REFERENCE**: PMData `perceived_exertion`; 평균 6.125, 표본 SD 1.397. 이 SD는 재검사 오차가 아님 | 예: label 주변분포 |
| S01 `rho = CS_like/v5` 중심 | 합성 개인 capacity 비율, 무차원; 각 중심 주위 대칭 삼각분포 폭 ±0.03 | 0.90 | 0.97 | 1.05 | **SIMULATION_ASSUMPTION**. 25명 레크리에이션 러너의 집단 평균 CS 12.1, 5 km 평균속도 12.0 km/h였지만 개인 비율 범위·현재 인원 CS는 제공하지 않음. 세 값은 문헌상 집단 유사성 주변의 보수적 민감도 제안; BASE에서도 `v5=CS`로 놓지 않음 | **예** |
| S02 `Dprime_like` 중심 | 합성 supra-threshold 거리 예비량, m; 각 중심의 0.8/1.0/1.2을 꼭짓점으로 한 대칭 삼각분포 | 80 | 130 | 200 | **SIMULATION_ASSUMPTION**. 전력시험을 반복한 훈련 러너 문헌의 D′ 123.3±57.7 m는 규모 참고만 가능. 현재 집단 직접 자료 없음; 분포 끝점은 64–240 m이며 실측 범위 주장 금지 | **예** |
| S03 `q` 소진율 | `v>CS_like`에서 `dq/du = -(v−CS_like)`, m/s | 같음: 1 | 1 | 같음: 1 | **LITERATURE_CONSTRAINT/STRUCTURE**: 거리–시간 CS/D′ 모형의 차원과 방향. `v≤CS_like`에서는 fast 소진 0; slow fatigue까지 0이라는 뜻 아님 | 예: 생성 구조 |
| S04 fast reserve 회복 `tau_fast` | 지수형 회복 후보의 시간상수, 분; `v<CS_like`일 때만 적용 | 2 | 4 | 6 | **SIMULATION_ASSUMPTION**. 간헐 운동의 W′/power 회복은 분 단위·회복강도 의존성이 보고되지만 D′/speed의 τ로 직접 전용 불가. 실제 개인 τ는 UNKNOWN | **예** |
| S05 slow fatigue/debt 회복 `tau_slow` | session 간 지수감쇠 후보의 시간상수, 시간 | 12 | 24 | 48 | **SIMULATION_ASSUMPTION**. fast reserve와 분리하려는 시간척도 시나리오일 뿐, 현재 자료의 추정치나 문헌 확정값이 아님 | **예** |
| S06 개인별 speed→HR 반응 편차 | 같은 상대속도 `x=0.70`에서 subject 반응의 영평균 SD 후보, bpm; 한 개인 안에서 고정 | 5 | 10 | 15 | **SIMULATION_ASSUMPTION**, **방향의 문헌 제약**. 217명 점증 트레드밀 연구에서 개인별 회귀가 pooled 회귀보다 오차가 작았지만 그 연구의 회귀오차는 개인 계수 SD가 아님. 현재 64건은 속도 범위·상황이 달라 개인 기울기를 안정적으로 보정하지 못함 | **예** |
| S07 개인 내 HR 생리 변동 | 동일 speed·상태에서 occasion variation SD 후보, bpm | 3 | 5 | 8 | **SIMULATION_ASSUMPTION**. S06과 별도; 문헌의 개인별 회귀 적합오차를 센서/생리 noise SD로 등치하지 않음. 선형 또는 비선형 평균반응 함수 자체는 U01 | 예: history·HR 비교 |
| S08 RPE reporting occasion error — **신뢰도 LOW/BASE/HIGH** | 잠재 점수에 독립적으로 더할 오차 SD의 시험 시나리오, 0–10 점 | 1.2 (LOW 신뢰도) | 0.8 | 0.4 (HIGH 신뢰도) | **SIMULATION_ASSUMPTION**. 0–10 session-RPE 반복상관 0.88은 별도 과업의 값. 6–20 점증운동에서는 강도별 ICC 0.75–0.82. 어느 결과도 현 0–10 점수의 Gaussian SD 또는 CV→SD 변환값이 아님. 이 SD가 특정 ICC를 보장한다는 주장 금지 | **예** |
| S09 개인 reporting bias | subject별 영평균 bias SD 후보, 0–10 점 | 0.3 | 0.5 | 0.8 | **SIMULATION_ASSUMPTION**. 개인별 반복 RPE가 없어 측정 불가. S08의 session 오차와 독립 결정 | **예** |
| S10 속도 궤적 | session 평균속도를 전 구간 일정한 속도로 사용하는 후보 | 같음: 일정 | 일정 | 같음: 일정 | **SIMULATION_ASSUMPTION**. 현재 맞춘 64건은 구간별 속도 궤적이 없음. 가감속·경사·하중의 영향은 재현 불가 | 예: threshold 위 체류시간 |
| U01 population mean speed→HR 함수와 개인 slope | `g_i(x,state)`의 기준 기울기·곡률·state 항, bpm/상대강도 | UNKNOWN | UNKNOWN | UNKNOWN | **UNKNOWN/NEEDS_SOURCE**. PMData의 러닝 *평균* speed–HR만 있고 단계별 동기화 HR, 직전 안정값, 같은 speed 반복/회복자료 부재. S06은 편차 규모일 뿐 함수 평균을 정의하지 않음 | **예** |
| U02 recovery-speed 의존성과 fast 개인차 | `tau_fast_i(v_recovery)` 형태·개인 분산 | UNKNOWN | UNKNOWN | UNKNOWN | **UNKNOWN/NEEDS_SOURCE**. S04는 단일 지수 회복 시간척도 시나리오; 반복 supra-threshold–회복 러닝 자료가 없음 | **예** |
| U03 slow debt 생성량·개인차 | `debt_after−debt_pre`의 intensity·duration·reserve 계수 및 척도, 정의 전 | UNKNOWN | UNKNOWN | UNKNOWN | **UNKNOWN/NEEDS_SOURCE**. 일별 간격만으로 회복 debt의 잠재 척도나 속도 의존량을 식별할 수 없음. S05는 감쇠 시간만 지정 | **예** |
| U04 acute strain 구성 | 상대강도·reserve·debt·환경→strain 함수와 정규화 범위 | UNKNOWN | UNKNOWN | UNKNOWN | **UNKNOWN/NEEDS_SOURCE**. strain의 단위·측정 가능한 준거가 아직 없음 | **예** |
| U05 burden coupling | relative demand, reserve depletion, acute strain, prior debt, 미관측 요인의 0–10 target 계수·절편 | UNKNOWN | UNKNOWN | UNKNOWN | **SIMULATION_ASSUMPTION 미결정**. 각 항의 부담 방향은 생리학적 구조로 제한되나 정확한 크기는 문헌으로 확정 불가. RPE 주변분포를 맞춰 history 성능이 좋아지도록 역조정 금지 | **예** |
| U06 fatigue·condition coupling | 별도의 0–10 자기보고 계수·절편·보고오차 | UNKNOWN | UNKNOWN | UNKNOWN | **UNKNOWN/NEEDS_SOURCE**. 현재 자료에는 같은 정의의 0–10 fatigue/condition 반복 label이 없음. burden label의 산술변환 금지 | **예** |
| U07 선택 센서의 측정과정 | HR·체온·SpO₂ bias, error, artifact, missing, SQI | UNKNOWN | UNKNOWN | UNKNOWN | **UNKNOWN/NEEDS_SOURCE**. 장치·측정부위·공식 사양·reference 비교가 아직 결정되지 않음. 정확도 범위를 Gaussian SD로 직접 치환 금지 | **예** |
| U08 speed/5 km 자료의 모집단 외삽 | 군 인원 분포와 러닝 조건, 경사·하중·열노출 | UNKNOWN | UNKNOWN | UNKNOWN | **UNKNOWN/NEEDS_SOURCE**. PMData 표본과 군 인원은 동일 모집단이 아님. 평지·비하중 범위 밖 일반화 금지 | 예: 외적 타당성 |

### 수치 선택의 경계

S01의 `rho`는 5 km 속도가 개인 CS라는 식별을 피하기 위한 **독립적인 시나리오**다. 레크리에이션 러너의 집단 평균이 비슷했다는 연구는 개인별 `0.90/0.97/1.05`를 검증하지 않는다. S02도 훈련된 러너의 D′ 규모와 겹치는 후보일 뿐 현재 사람들의 분포 추정이 아니다. S04·S05는 fast/slow를 다른 상태와 시간척도로 분리한다는 구조적 목적을 갖지만 특정 개인의 회복시간을 뜻하지 않는다. S06·S07·S08·S09는 서로 별도 원인으로 둔다. 개인차 크기와 label noise를 같은 결과 목표에 맞춰 공동 조정하지 않는다.

## 구현 전에 잠가야 할 검사

1. **속도–HR sanity check:** 생성기의 동일 subject/session split 안에서 속도 범위가 있는 개인만 평가한다. 학습 session으로 (a) 전체 공통 speed→HR 관계와 (b) subject별 보정 관계를 각각 적합하고, 동일한 held-out session 평균 HR에서 MAE·개인별 잔차·양의 기울기 비율을 비교한다. 두 모델의 feature·평가 session·측정오차 조건은 같다. 최소 5개 학습 session, 서로 다른 속도 3수준이 없으면 그 인원은 `NOT_IDENTIFIABLE`로 기록한다. 평가 가능한 인원의 과반에서 속도–HR 기울기가 0 이하이거나, S06에 지정한 subject별 반응 편차가 생성식에서 실제로 0이면 구조 `WARNING`이다. 개인별 모델의 성능이 더 좋지 않더라도 결과로 보존한다. 원하는 효과가 나오도록 S01·S06·U01을 변경하지 않는다.
2. **CS/D′ 물리 검증:** 단위 일치, `q∈[0,Dprime_like]`, supra-threshold 적분 소진, threshold 이하 fast reserve 비소진, `q=0` 뒤 완료 session label 생성 금지. 실제 완료 러닝 분포와 `q=0` 검열률을 함께 보고하고 비율이 높아도 결과를 보고한다.
3. **보고 신뢰도 검증:** 동일한 잠재 burden과 동일 개인 bias에서 occasion error만 다시 뽑은 반복 0–10 rating의 실제 test–retest 상관·일치도·경계질량을 LOW/BASE/HIGH 모두 보고한다. S08의 SD 숫자를 ICC 또는 CV라고 표기하지 않는다.
4. **근거·변경 관리:** 이 파일의 SHA-256을 최초 구현 전 별도 manifest에 기록한다. 이후 변경은 덮어쓰지 않고 dated amendment에 이전 hash·수정 이유·결과 열람 여부를 기록한다. `UNKNOWN`을 조용히 기본값으로 대체하지 않는다.

## 구현 시작 판정

**STOP.** 경험적 입력 분포와 핵심 sensitivity 후보는 등록했지만 U01의 speed→HR 평균함수, U03–U06의 잠재상태 및 target 결합, U07의 장치 측정과정이 비어 있다. 이 값들을 근거 없이 코드에 넣으면 같은 protocol 아래에서도 결과를 만든 뒤 조정할 수 있는 자유도가 남는다. 다음 단계는 코드가 아니라 이 항목들의 단위·함수형·독립 가정 및 LOW/BASE/HIGH를 결과 보기 전에 별도 amendment로 잠그는 것이다. 실측자료가 없으면 `simulation assumption`이라고 명시하여 잠글 수 있으나, 현재 파일은 그것을 이미 결정한 것처럼 쓰지 않는다.

## 근거

* PMData 소스: [`data/pmdata/capacity_provenance.json`](data/pmdata/capacity_provenance.json), [`capacity.py`](capacity.py), [`artifacts/simulator_v2_calibration_v1/calibration.json`](artifacts/simulator_v2_calibration_v1/calibration.json). E01–E07은 현재 파일의 읽기 전용 재계산값이며 v2 calibration artifact 자체는 변경하지 않았다.
* Figueiredo 등, [CS와 5 km 속도를 각각 측정한 25명 레크리에이션 러너 연구](https://pmc.ncbi.nlm.nih.gov/articles/PMC8291129/): CS 평균 12.1±1.4, 5 km 평균속도 12.0±1.3 km/h; 집단 평균 유사성은 개인 동일성의 증거가 아님.
* Kordi 등, [2/3개 전력시험에서 계산한 CS·D′ 비교](https://pubmed.ncbi.nlm.nih.gov/30427230/): 14명 훈련 러너, D′ 123.3±57.7 m(3시험); 다른 집단·과업의 분포를 현재 인원에게 이식하지 않음.
* Jang 등, [점증 트레드밀에서 speed–HR 개인/집단 모델 비교](https://pubmed.ncbi.nlm.nih.gov/28269462/): 개인별 보정의 필요성을 뒷받침. 보고된 회귀 적합오차를 S06/S07의 SD로 변환하지 않음.
* Herman 등, [0–10 session-RPE 반복 연구](https://journals.assaf.org.za/index.php/sajsm/en/article/view/247); Lamb 등, [6–20 점증운동 RPE 반복 연구](https://pubmed.ncbi.nlm.nih.gov/10522637/): 질문 시점·운동 protocol·척도에 따라 반복성이 달라짐. 현재 PMData의 occasion SD 제공 자료가 아님.
* [간헐 러닝의 W′/power 회복 연구](https://pubmed.ncbi.nlm.nih.gov/31776696/): 빠른 reserve 재구성의 시간척도·회복강도 의존성에 대한 구조 참고. W′ 시간상수를 D′ 시간상수로 직접 대입하지 않음.
