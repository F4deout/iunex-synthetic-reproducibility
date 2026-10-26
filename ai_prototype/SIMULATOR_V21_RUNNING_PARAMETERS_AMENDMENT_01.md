# v2.1-running parameter amendment 01 — 최소 생성식 잠금

작성일: 2026-09-21  
상태: **사전등록; v2.1 generator 미구현·미실험**  
수정 방식: [`SIMULATOR_V21_RUNNING_PROTOCOL.md`](SIMULATOR_V21_RUNNING_PROTOCOL.md)와 [`SIMULATOR_V21_RUNNING_PARAMETERS.md`](SIMULATOR_V21_RUNNING_PARAMETERS.md)는 수정하지 않는다. 이 문서는 해당 파일의 `U01`, `U03`–`U07`과 핵심 범위에 대한 **별도 보충·우선 적용 결정**이다.  
입력 해시: protocol `4594babf1e5cef0fc69a2879d7bb5b0a374bfde4abefd1661f4de9fb87aba129`; parameters `be7eed3eae78a3a2e56fa3e07ee7101afa5780ba753b13bde0ba28f07bb99823`.  
결과 열람 여부: **기존 v2 결과와 v2.1 설계 이전 감사 결과는 알려져 있음; v2.1 생성·모델 성능 결과는 없음.** 이 결정은 과거 v2 history 효과를 회복하거나 예측 MAE를 맞추기 위한 재조정이 아니다.

## 1. 최소 범위와 공통 규칙

완료한 **평지·비하중 러닝 session의 평균속도, 지속시간, 평균 HR**을 v2.1-running core의 관측 범위로 둔다. 활동 직후의 합성 burden·fatigue·condition은 모두 0–10의 **자기보고 구성개념**이다. 이는 실측 탈진, 의학적 안전성, 군 임무수행능력이 아니다. HR은 상대 요구량·개인 반응·상태가 만든 **생리 관측**이고 어느 target 생성식의 입력도 아니다. 세 target은 서로의 *label*을 사용하지 않는다. `RPE/perceived_exertion`은 burden의 실제자료 참고값·label일 뿐 speed나 intensity 입력이 아니다.

외부 러닝 입력은 앞선 parameter 등록부 E01–E04의 경험적 기준을 유지한다. `CS_like/v5`의 S01, `Dprime_like`의 S02, 빠른/느린 회복 시간척도의 S04/S05, 개인 HR 편차 S06, 개인 내 HR 변동 S07, burden 보고오차 S08과 bias S09는 **그대로 적용**한다. 64개 매칭 기록의 `speed/v5` 중앙값 0.684를 유지하므로 다수의 경험적 러닝이 CS-like 아래에 있을 수 있다. 위 임계 session을 재표집·증식하거나 speed/CS 비율을 결과에 맞춰 바꾸지 않는다. 평균속도 일정 가정(S10) 때문에 구간별 가속·경사·실제 상한 초과 시간은 알 수 없다. 종료 전 예비량이 0이 되면 protocol대로 완료 label을 생성하지 않고 검열한다.

기호: 개인 `i`, session `s`; `v`와 `CS_i`는 m/s, `T`는 분, `gap`은 시간. `x=v/CS_i`; `q`는 m 단위 남은 fast reserve; `D_i`는 D′-like m. `d=max(0,(q_start-q_end)/D_i)`는 **현재 session에서 새로 소진한 비율**이고, 종료 시 총 잔량은 별도로 `q_end/D_i`이다. `q_start`는 이전 q의 휴식 회복을 반영하며, 첫 session은 `D_i`. 아래 함수는 **측정된 생리 법칙이 아니라 SIMULATION_ASSUMPTION**이다. 모든 난수 stream은 개인 특성·session 교란·보고과정·센서과정으로 분리하고, coupling scenario를 바꿔도 같은 외생 draw를 사용한다.

```text
r(x) = x / (1+x)                                  # [0,1), 상대 요구 요약
t(T) = T / (T+60 min)                             # [0,1), 지속시간 요약
if v > CS_i: q_end = max(0, q_start - 60*T*(v-CS_i))
if v < CS_i: q_end = D_i-(D_i-q_start)*exp[-T/tau_fast_i]
if v = CS_i: q_end = q_start
d = max(0, (q_start-q_end)/D_i)                    # [0,1], 이번 session 소진만
debt_pre = debt_previous_after * exp(-gap/tau_slow_i)
```

`q_end` 식은 session 안의 속도가 일정한 **완료 후보**에만 적용한다. 이전 session과 현재 session 사이에는 `q_start=D_i-(D_i-q_previous_end)exp[-60*gap/tau_fast_i]`로 수동 회복을 적용한다(`gap` 시간, `tau_fast_i` 분). session 내부 속도 변화·active recovery는 v2.1-running core에 생성하지 않는다. `v=CS_i`에서 fast 소진은 0이다. `q=0`의 검열은 label의 높고 낮음으로 대체하지 않는다.

## 2. U01·U03·U04 생성식

### U01 — 단조 population speed→HR와 개인 반응

```text
true_session_average_HR_i,s
  = baseline_HR_i + beta*x + delta_i*(x/0.70)
    + c_strain*strain_i,s + c_debt*debt_pre_i,s
    + epsilon_physiology_i,s

delta_i ~ Normal(0, sigma_between_response^2), once per subject
epsilon_physiology_i,s ~ Normal(0, sigma_within_HR^2), once per session
```

`baseline_HR_i`는 E05 개인 안정 HR 참고분포에서 가져오며 *session 직전 측정값*으로 재해석하지 않는다. `beta>0`이므로 `x`에 대한 평균 HR은 단조 증가한다. S06의 개인 반응 편차는 `x=0.70`에서 정확히 `sigma_between_response` bpm의 SD를 갖는다. 편차가 큰 극단적 개인에서 기울기가 역전될 수 있는 무한 정규꼬리는 구현 단계에서 **기울기 양수 조건부 분포**로 정의한다. 정규 draw가 `beta+delta_i/0.70≤0`이면 해당 개인 계수만 재추출하며, 재추출률을 보고하고 값을 조정하지 않는다. `epsilon_physiology`는 S07로서 센서오차와 별개다.

`beta=120 bpm/상대강도`, `c_strain=c_debt=5 bpm`은 생리학적 실측 회귀계수가 아닌 **고정 합성 가정**이다. E05 중앙값 59.4 bpm, E06 러닝 평균 148 bpm 및 경험적 속도 비율은 생성 후 *sanity anchor*로만 비교한다. PMData 평균속도/평균 HR 쌍으로 점증 트레드밀의 순간 속도–HR 곡선이나 개인별 기울기를 직접 보정했다고 주장하지 않는다. 관측 HR 40–220 bpm 범위 밖 비율은 보고하되 이 기준으로 parameter를 재조정하지 않는다. 등록부의 population 대 subject-specific speed→HR 비교도 그대로 수행한다.

### U03 — 느린 debt 누적

```text
exposure = x * T/60 min                         # 무차원; 1시간 상대강도 1이 1
debt_after = 1 - (1-debt_pre)*exp[-lambda_debt*(exposure+d)]
```

`debt_pre`, `debt_after`는 0–1의 합성 느린 피로 debt다. `lambda_debt=0.5`는 **고정 SIMULATION_ASSUMPTION**이고 실측 시간상수 S05와 혼동하지 않는다. 식은 상대강도·지속시간·예비량 소진·이전 debt에 단조적이며 0–1을 벗어나지 않는다. 휴식 중 감쇠에는 S05를 사용한다. 경험적 러닝 간격 중앙값이 6일이므로 다음 session의 `debt_pre`가 자주 작아져도 결과로 보존한다.

### U04 — 급성 strain

```text
strain = [r(x) + t(T) + d + debt_pre] / 4        # 무차원, [0,1]
```

네 항은 같은 0–1 범위에서 동일 가중하는 **고정 SIMULATION_ASSUMPTION**이다. 상대강도·시간·예비량 소진·이전 debt 중 어느 하나가 증가해도 strain이 감소하지 않는다. 기온/습도·경사·하중은 core에서 중립으로 고정하며, 실제 노출 효과를 0이라고 결론 내리지 않는다. strain은 HR과 target의 공통 잠재원인이지 HR로부터 역산한 변수가 아니다.

## 3. U05·U06: 독립 target과 보고과정

모든 점수는 먼저 0–1 구성요소의 **양의 가중평균**으로 만들고 `latent_score=2+6*z`를 적용한다. 따라서 보고오차 이전 latent 점수는 **2–8점**으로 제한되고 큰 계수 합계나 hard clipping으로 점수를 만들지 않는다. 이는 0–10 척도의 내부에 여유를 두는 합성 설계 가정이며 PMData 점수를 맞춘 회귀가 아니다. 보고 후 경계 clipping은 아래처럼 별도로 추적한다.

### U05 — burden coupling의 세 사전등록 시나리오

`u_b ~ Uniform(0,1)`은 매 session 독립인 비관측 burden 요인. 아래 순서의 다섯 계수는 각각 `r(x)`, `d`, `strain`, `debt_pre`, `u_b`에 곱한다. **각 행의 합은 1**, 모든 계수는 0 이상이다. 정확한 coupling 계수는 문헌에서 관측되지 않았으므로 세 행 전체가 `SIMULATION_ASSUMPTION`이다.

| Coupling | 상대 요구 `r` | 예비량 소진 `d` | strain | 이전 debt | 미관측 `u_b` | 직접 개인화 항 `r+d` |
|---|---:|---:|---:|---:|---:|---:|
| **WEAK** | 0.10 | 0.05 | 0.20 | 0.15 | 0.50 | 0.15 |
| **BASE** | 0.20 | 0.15 | 0.25 | 0.15 | 0.25 | 0.35 |
| **STRONG** | 0.30 | 0.25 | 0.25 | 0.10 | 0.10 | 0.55 |

이 비교는 **개인화 경로와 비관측 경로의 상대 결합 강도**를 바꾼다. `strain`에도 상대강도·소진·debt가 들어 있으므로 마지막 열은 총 개인화 효과가 아니라 **직접 항의 계수 합**이다. 각 scenario마다 동일 seed·외생 draw·입력속도·개인 parameter·label-noise 분포를 사용하고, 세 결과를 빠짐없이 보고한다. STRONG에서 history 이점이 없거나 WEAK에서 더 커도 그대로 보존한다. 특정 결과를 얻으려고 S01/S02/S06/S08을 함께 바꾸지 않는다.

### U06 — fatigue와 condition

`u_w ~ Uniform(0,1)`은 session의 독립 비관측 wellness로, 높을수록 더 양호하다. `u_w`는 `u_b`와 독립이며 개인 내부에서도 session마다 독립이다. `fatigue`는 클수록 피로가 크고, `condition`은 클수록 현재 자기보고 상태가 양호하다.

```text
fatigue_z   = 0.50*debt_after + 0.25*strain + 0.25*(1-u_w)
condition_z = 0.30*(1-debt_pre) + 0.25*(q_end/D_i)
              + 0.25*(1-strain) + 0.20*u_w
latent_fatigue   = 2 + 6*fatigue_z
latent_condition = 2 + 6*condition_z
```

두 식은 합성 **고정 가정**이며 각 가중치 합 1, latent 점수 범위 2–8이다. condition은 burden label의 역산도 fatigue label의 단순 보수도 아니다. `fatigue_z`는 session 후 debt를, `condition_z`는 사전 debt와 종료 reserve를 사용하므로 서로 다른 구성개념이다. 원래 연구의 열·산소 상태는 측정 자료와 선택 장치가 없어서 core에서 생성하지 않는다. 이 omission은 일상·근무·의학적 상태 추정으로 확장할 근거가 아님을 보고한다.

```text
reported_target = clip_0_10(latent_target
                            + bias_i,target + occasion_error_i,s,target)
```

각 target의 bias와 occasion error는 서로 독립 추출한다. burden에는 S09/S08의 사전등록 값을 적용한다. fatigue/condition 각각은 별도 `bias~Normal(0,0.5²) 점`, `occasion_error~Normal(0,0.8²) 점`을 **고정 SIMULATION_ASSUMPTION**으로 사용하며, 두 값은 fatigue/condition의 실측 신뢰도 또는 burden RPE의 재사용 추정치가 아니다. 세 label의 0/10 경계질량·clipping 비율을 사전 보고한다. 2–8 latent 범위는 경계질량을 작게 만들기 위한 설계지만 실제 비율을 확인하기 전에 `PASS`를 선언하지 않는다.

## 4. U07 — 핵심 개인화 검증의 측정 범위

장치가 아직 선정되지 않았으므로 core observed predictor에는 **러닝 session 평균 HR 한 채널**만 둔다. 속도·지속시간·5 km 참고값은 외부 기록이며 생체센서 입력이 아니다. 체온·SpO₂, ECG, 혈압, SQI는 core에 생성하거나 입력하지 않는다. 이는 다중센서 제품 범위의 포기가 아니라 **러닝 개인화 생성 구조를 먼저 검증하기 위한 실험 범위 제한**이다. 따라서 이 core 결과로 센서 융합·품질 적응의 성능을 주장하지 않는다.

```text
observed_session_average_HR = true_session_average_HR
                              + epsilon_measurement
epsilon_measurement ~ Normal(0, sigma_sensor_HR²) bpm
```

실제 장치의 bias·artifact·결측·SQI는 `UNKNOWN`이며 **core에서는 고정 0 또는 미사용**한다: sensor bias 0 bpm, artifact 확률 0, 결측 확률 0, SQI 미생성. 이는 장치 정확도가 완벽하다는 주장이 아니다. 평균 HR 측정오차 SD `2/4/6 bpm`만 LOW/BASE/HIGH **SIMULATION_ASSUMPTION**으로 둔다. S07의 생리 변동과 별도 stream으로 생성한다. 선택된 장치의 공식 정확도 범위를 Gaussian SD로 간주하지 않는다. 이후 실제 센서/품질 실험은 장치 선정·독립 reference 자료·별도 amendment 후 진행한다.

## 5. 미결정 항목 전체 등록

아래 `fixed`는 모든 coupling scenario에서 같은 값이다. LOW/BASE/HIGH가 있는 행은 한 family씩 변경하며 **모든 조건을 보고**한다. 수치가 없는 `UNKNOWN`은 core 수식에 몰래 기본값을 넣지 않는다.

| ID | parameter / 함수 | 단위 | LOW | BASE / fixed | HIGH | provenance | critical |
|---|---|---|---:|---:|---:|---|---|
| U01-a | population HR 계수 `beta` | bpm/상대강도 1 | fixed | 120 | fixed | **SIMULATION_ASSUMPTION**; E05/E06은 사후 sanity anchor만 | **예** |
| U01-b | strain→HR `c_strain` | bpm/strain 1 | fixed | 5 | fixed | **SIMULATION_ASSUMPTION** | 예 |
| U01-c | 이전 debt→HR `c_debt` | bpm/debt 1 | fixed | 5 | fixed | **SIMULATION_ASSUMPTION** | 예 |
| U01-d | 개인 HR 편차·개인내 생리 변동 | bpm SD | 5 / 3 | 10 / 5 | 15 / 8 | 기존 S06 / S07 **SIMULATION_ASSUMPTION**; 재고정 아님 | **예** |
| U02-a | 수동 fast 회복의 개인 배율 | 무차원 삼각분포 min/mode/max | fixed | 0.75 / 1 / 1.25 | fixed | **SIMULATION_ASSUMPTION**; S04 τ에 곱함 | 예 |
| U03-a | slow 회복의 개인 배율 | 무차원 삼각분포 min/mode/max | fixed | 0.75 / 1 / 1.25 | fixed | **SIMULATION_ASSUMPTION**; S05 τ에 곱함 | 예 |
| U03-b | `lambda_debt` | 무차원/노출지수 | fixed | 0.5 | fixed | **SIMULATION_ASSUMPTION**; `exposure=x*T/60`, `d` 사용 | **예** |
| U04-a | `r(x)`, `t(T)` | 무차원 | fixed | `x/(1+x)`; `T/(T+60분)` | fixed | **SIMULATION_ASSUMPTION**; 단조·bounded | 예 |
| U04-b | strain 네 항 가중치 | 무차원 | fixed | 0.25 / 0.25 / 0.25 / 0.25 | fixed | **SIMULATION_ASSUMPTION**; 상대요구/시간/소진/이전 debt 순서 | **예** |
| U05-a | burden WEAK/BASE/STRONG 계수 | 무차원, 행 합 1 | WEAK 행 | BASE 행 | STRONG 행 | **SIMULATION_ASSUMPTION**; 위 표의 다섯 계수 모두 고정 | **예** |
| U05-b | 비관측 burden 요인 `u_b` | 무차원 | fixed | `Uniform(0,1)` | fixed | **SIMULATION_ASSUMPTION**; 개인·session 간 독립 | **예** |
| U06-a | fatigue 계수 | 무차원, 합 1 | fixed | 0.50 / 0.25 / 0.25 | fixed | **SIMULATION_ASSUMPTION**; after debt/strain/불양호 순서 | **예** |
| U06-b | condition 계수 | 무차원, 합 1 | fixed | 0.30 / 0.25 / 0.25 / 0.20 | fixed | **SIMULATION_ASSUMPTION**; 사전 무debt/남은 reserve/무strain/wellness 순서 | **예** |
| U06-c | wellness `u_w` | 무차원 | fixed | `Uniform(0,1)` | fixed | **SIMULATION_ASSUMPTION**; burden 요인과 독립 | 예 |
| U05/U06-d | latent score map | 점 | fixed | `2+6*z` | fixed | **SIMULATION_ASSUMPTION**; `z∈[0,1]`, reporting 전 2–8 | **예** |
| U06-e | fatigue/condition 개인 bias SD | 점 | fixed | 0.5 | fixed | **SIMULATION_ASSUMPTION**; target별 독립 | 예 |
| U06-f | fatigue/condition occasion SD | 점 | fixed | 0.8 | fixed | **SIMULATION_ASSUMPTION**; target별 독립 | **예** |
| U07-a | HR 센서 측정오차 SD | bpm | 2 | 4 | 6 | **SIMULATION_ASSUMPTION**; 장치 정확도 추정 아님 | **예** |
| U07-b | bias / artifact / missing | bpm / 확률 / 확률 | fixed | 0 / 0 / 0 | fixed | **core 범위 가정**; 실제 장치 값은 UNKNOWN | 예: 외적 타당성 |
| U07-c | SQI 및 체온·SpO₂ 측정과정 | 해당 없음 | fixed | core 미생성·미입력 | fixed | **core 범위 가정**; 실제 센서 검증은 별도 연구 | 예: 제품 확장 |

## 6. 해석 한계, 잠금, 시작 판정

WEAK/BASE/STRONG은 높은 성능을 고르기 위한 후보가 아니라 **결과 민감도 분석 축**이다. 특히 `S01 rho`, `S02 D′`, `U03 lambda_debt`, `U05 coupling`, `S08/ U06 reporting noise`는 효과 크기를 크게 흔들 수 있다. 이들은 서로 다른 근거로 사전 결정되며 결과를 본 뒤 함께 움직이지 않는다. `rho`와 경험적 speed가 만드는 아래-임계 비율·검열률, score 경계질량, true/observed HR 분포, 개인 speed→HR 적합도는 그대로 보고한다. 생성 data의 모양이나 history 성능을 보고 수치를 수정하지 않는다.

**core 구현 시작 `PASS`의 의미:** 위 수식만 사용하는 러닝 개인화 시뮬레이터의 *구현을 시작*할 수 있다는 뜻이다. 실증적 타당성이나 본 실험 `EXPERIMENT_READY` 판정은 아니다. 첫 생성 후 구조·분포·shuffle·누수·재현성 dry run을 통과하기 전에는 본 실험을 실행하지 않는다. 구현 중 수식에 없는 parameter가 필요하면 임의 기본값을 추가하지 말고 `STOP` 및 새 amendment로 돌아간다.

**여전히 UNKNOWN:** 실제 군 인원의 CS/D′ 및 분포, active-recovery speed 효과, 러닝 중 구간속도와 HR 곡선, 열·산소 생리, 선택 장치의 HR/체온/SpO₂ 오차·artifact·SQI, 실제 fatigue/condition 재검사 신뢰도, 군 population 및 임무 환경 일반화. 이 항목들은 **core에서 사용하지 않으므로** core 구현의 미결정 계수는 아니다. 센서 융합·현장 적용의 주장을 위해서는 별도 자료와 amendment가 필요하다.

이 파일은 SHA-256 sidecar `SIMULATOR_V21_RUNNING_PARAMETERS_AMENDMENT_01.sha256`로 잠근다. 원문을 덮어쓰지 않으며 후속 변경은 입력 해시와 결과 열람 여부를 명시한 `AMENDMENT_02` 이상으로만 기록한다.
