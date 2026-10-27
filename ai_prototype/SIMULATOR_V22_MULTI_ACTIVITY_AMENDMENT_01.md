# v2.2-multi-activity Amendment 01 — 최소 생성구조와 민감도 수치 동결

작성일: 2026-09-28  
결과 열람 상태: **v2.2 데이터·예측 결과 미생성·미열람**  
대상: `SIMULATOR_V22_MULTI_ACTIVITY_DESIGN.md`, `SIMULATOR_V22_MULTI_ACTIVITY_PROTOCOL.md`, `SIMULATOR_V22_MULTI_ACTIVITY_PARAMETER_REGISTER.md`  
목적: 행군과 순환식 훈련의 generator 구현 전에 모든 필요한 함수·수치·grid를 사전 고정

## 1. 근거 사용 범위

군장 행군에서 속도·군장 무게·경사·지형이 생리적 요구에 영향을 준다는 방향은 군장 보행 연구가 지지한다. 그러나 기존 대사비용식은 조건에 따라 과소·과대 예측될 수 있으므로 현재 합성 target의 정답식으로 사용하지 않는다([Vine et al., 2022, PMID 32398631](https://pubmed.ncbi.nlm.nih.gov/32398631/)). 3.5–5.5 km/h, 약 20–31 kg, 평지와 5% 경사는 군 대상 실험에서 실제 사용된 조건의 범위 안에 있으나([Grenier et al., 2012, PMID 22215177](https://pubmed.ncbi.nlm.nih.gov/22215177/); [Chatterjee et al., 2018, PMID 30045754](https://pubmed.ncbi.nlm.nih.gov/30045754/)), 본 amendment의 grid는 안전 처방이나 군 장병 population estimate가 아니라 **합성 sensitivity grid**다.

순환식 훈련에서는 동일한 work:rest 비율에서도 절대 work/rest 길이에 따라 HR·대사·수행 반응이 달라질 수 있고, 같은 총 운동량에서도 휴식 구조가 반응을 바꿀 수 있다([PMID 41507409](https://pubmed.ncbi.nlm.nih.gov/41507409/); [Smith et al., 2025, PMID 40007896](https://pubmed.ncbi.nlm.nih.gov/40007896/)). 이 근거는 work time·rest time·총 duration을 별도 입력으로 보존해야 한다는 방향만 지원한다. 아래 결합계수는 모두 `SIMULATION_ASSUMPTION`이다.

## 2. 최소 공통 생성구조

활동 `a∈{LOADED_MARCH, BODYWEIGHT_CIRCUIT}`에 대해 개인별 활동능력 `capacity_i,a`는 양의 무차원 잠재량이다. workload 배정에는 이 잠재량을 사용하지 않는다.

```text
protocol_demand_a = bounded monotonic function(observed planned workload)
relative_demand_i,a = protocol_demand_a / capacity_i,a
duration_term = actual_duration / (actual_duration + activity_half_duration)

strain = 0.40 * relative_demand/(1+relative_demand)
       + 0.25 * duration_term
       + 0.20 * debt_pre
       + 0.15 * u_phys

debt_pre  = debt_previous * exp(-gap_hours/tau_slow_i)
exposure  = relative_demand * actual_duration/activity_reference_duration
debt_after = 1 - (1-debt_pre) * exp(-lambda_debt * exposure)

true_HR = HR_baseline_i
        + beta_HR * relative_demand/(1+relative_demand)
        + 10*strain + 5*debt_pre
        + within_session_physiology

observed_HR = true_HR + independent measurement error
```

`u_phys~Uniform(0,1)`은 predictor에 제공하지 않는 session별 생리 변동이다. HR은 workload나 target의 원인이 아니라 공통 잠재상태에서 생성되는 관측값이다. `capacity`, `strain`, `debt`는 audit-only이고 predictor에서 금지한다.

## 3. 군장 행군 demand

```text
s = clip((speed_kmh - 3.5)/(5.5-3.5), 0, 1)
l = clip(load/body_mass / 0.40, 0, 1)
g = clip(max(grade_pct,0)/5, 0, 1)
raw = 0.45*s + 0.35*l + 0.20*g + alpha_sl*s*l
protocol_demand_march = raw/(1+alpha_sl)
```

`alpha_sl` LOW/BASE/HIGH는 `0.00/0.15/0.30`이다. 속도–군장 상호작용의 정확한 계수가 아니며 결과 민감도 가정이다. 내리막·불규칙 지형·하중 위치는 core에서 생성하지 않고 `UNKNOWN`으로 보존한다.

### 사전 고정 행군 calibration 12개 cell

| ID | 속도 km/h | 군장/체중 | 경사 | 계획시간 |
|---|---:|---:|---:|---:|
| M01 | 3.5 | 0.20 | 0% | 6분 |
| M02 | 4.5 | 0.20 | 0% | 6분 |
| M03 | 5.5 | 0.20 | 0% | 6분 |
| M04 | 4.5 | 0.00 | 0% | 6분 |
| M05 | 4.5 | 0.40 | 0% | 6분 |
| M06 | 4.5 | 0.20 | 5% | 6분 |
| M07 | 3.5 | 0.20 | 0% | 20분 |
| M08 | 4.5 | 0.20 | 0% | 20분 |
| M09 | 5.5 | 0.20 | 0% | 20분 |
| M10 | 5.5 | 0.40 | 0% | 6분 |
| M11 | 4.5 | 0.40 | 5% | 6분 |
| M12 | 3.5 | 0.40 | 5% | 20분 |

held-out evaluation은 `ME1=(4.0,0.20,0%,12분)`, `ME2=(5.0,0.20,0%,12분)`, `ME3=(4.5,0.30,5%,12분)`, `ME4=(5.5,0.40,5%,20분)`으로 고정한다. 잠재 capacity를 이용해 조건을 배정하지 않는다. 이 grid를 실제 인원에게 실시하라는 지침으로 사용하지 않는다.

## 4. 순환식 훈련 demand

모든 session은 동일한 6개 추상 station 순서를 사용한다. station 이름은 기록 ID일 뿐 종목별 생리계수를 뜻하지 않는다. 종목 차이를 생성하려면 실제 반복·중량 자료와 별도 amendment가 필요하다.

```text
density = work_sec/(work_sec+rest_sec)
w = clip(work_sec/30, 0, 1)
t = clip(planned_total_minutes/14, 0, 1)
protocol_demand_circuit = wd*density + ww*w + wt*t
```

work-density coupling은 다음 세 행을 모두 실행하도록 잠근다.

| scenario | wd | ww | wt |
|---|---:|---:|---:|
| LOW | 0.35 | 0.30 | 0.35 |
| BASE | 0.50 | 0.25 | 0.25 |
| HIGH | 0.65 | 0.20 | 0.15 |

### 사전 고정 순환식 calibration 12개 cell

`C01–C04`: `10:10, 20:20, 30:30, 30:5초`, 총 7분.  
`C05–C08`: 같은 네 조건, 총 14분.  
`C09–C12`: `20:20초, 14분`의 같은 조건을 이전 session과 `5/15/60/1440분` 간격으로 반복.

held-out evaluation은 `CE1=(15:15초,7분)`, `CE2=(25:25초,14분)`, `CE3=(30:10초,7분)`, `CE4=(30:10초,14분)`이다. 반복수·완료율은 관측 결과로 저장하지만 protocol demand 식에 임의 종목 가중치를 넣지 않는다.

## 5. 개인차·회복·측정·보고 가정

모든 값은 실제 장병 추정치가 아닌 결과 전 sensitivity 가정이다.

| family | LOW | BASE | HIGH | 방향 |
|---|---:|---:|---:|---|
| activity capacity triangular 중심 | 0.90 | 1.00 | 1.10 | 중심 변화가 아니라 family 실행 시 전체 중심 |
| capacity spread (min/max, 중심 대비) | ±0.10 | ±0.20 | ±0.30 | 개인차 크기 |
| `beta_HR` | 60 | 80 | 100 bpm | 상대요구→HR 범위 |
| activity HR response SD | 5 | 10 | 15 bpm | 개인별 반응차 |
| physiology SD | 3 | 5 | 8 bpm | session 변동 |
| HR measurement SD | 2 | 4 | 6 bpm | 장치 사양값이 아님 |
| `tau_slow` | 12 | 24 | 48시간 | 느린 debt 회복 |
| `lambda_debt` | 0.30 | 0.50 | 0.70 | 노출→debt 누적 |
| target occasion error SD | 0.4 | 0.8 | 1.2점 | 보고 불확실성 |
| target personal bias SD | 0.3 | 0.5 | 0.8점 | 개인 보고차 |

한 번에 한 family만 LOW/BASE/HIGH로 바꾸고 나머지는 BASE에 둔다. activity capacity 중심은 population estimate가 아니므로 주분석에서는 BASE로 고정하며, 개인차 감사에서는 spread family만 변경한다.

## 6. target coupling

`r=relative_demand/(1+relative_demand)`, `t=duration_term`, `u_b~Uniform(0,1)`이다.

| burden scenario | r | t | strain | debt_pre | u_b |
|---|---:|---:|---:|---:|---:|
| WEAK | 0.10 | 0.10 | 0.20 | 0.15 | 0.45 |
| BASE | 0.20 | 0.15 | 0.25 | 0.15 | 0.25 |
| STRONG | 0.30 | 0.20 | 0.25 | 0.10 | 0.15 |

```text
fatigue_z   = 0.45*debt_after + 0.25*strain + 0.30*(1-u_w)
condition_z = 0.35*(1-debt_pre) + 0.35*(1-strain) + 0.30*u_w
latent_score = 2 + 6*z
reported_score = clip_0_10(latent_score + personal_bias + occasion_error)
```

`u_w~Uniform(0,1)`이고 `u_b`와 독립이다. 세 target은 서로의 label을 입력으로 사용하지 않는다. WEAK/BASE/STRONG은 성능등급이 아니라 coupling sensitivity이며 전부 보고한다.

## 7. 수행 중단·검열

행군·순환식 core는 현재 생리적 한계시간을 정답처럼 생성하지 않는다. session은 계획 종료 전 누적 exposure가 개인별 합성 tolerance threshold를 넘을 때 all-cause synthetic stop 후보가 되며, threshold는 `capacity`와 별도 session variation에서 생성한다. 정확한 threshold 분포는 `0.8/1.0/1.2` 배율 LOW/BASE/HIGH로 등록한다. 완료 session은 계획시간에서 right-censored이고 hypothetical stop-time을 저장하거나 predictor에 제공하지 않는다. 실제 안전중단·자발중단의 분리는 현 자료에 없으므로 core target은 `synthetic all-cause stop/completion`으로만 표현한다.

## 8. 사전 validation

구현 후 본 실험 전에 다음을 검사한다.

- 동일 seed/config 재현
- subject/session/protocol-cell split 교집합 0
- 현재·미래 target 및 latent 입력 0
- workload assignment의 latent 접근 0
- 활동별 workload 단조성
- 같은 외부 조건에서 capacity 차이에 따른 latent state 차이
- 같은 observed HR 구간에서 활동종류·capacity에 따른 target 차이
- target/feature shuffle
- mean/observed/true-state/latent oracle 비교
- completed/right-censored support
- HR와 0–10 target clipping·boundary mass
- 모든 coupling 및 sensitivity 조건 보고 가능성

## 9. 구현 판정

수식·수치·grid가 결과 열람 전에 고정되었으므로 **`GENERATOR_IMPLEMENTATION_PASS`**다. 이는 실제 타당성이나 본 실험 승인이 아니다. 구현 후 dry run에서 구조·분포·누수·recoverability를 평가하며, 결과가 나쁘더라도 parameter를 바꾸지 않는다.

