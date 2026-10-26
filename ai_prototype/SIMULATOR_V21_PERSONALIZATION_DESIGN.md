# Simulator v2.1-personalization 설계안

상태: **설계 초안만 작성; 미구현·미실험**  
작성 근거: 동결된 `SIMULATOR_V2_PROTOCOL.md`, `SIMULATOR_V2_PARAMETERS_AMENDMENT_06.json`, `simulator_v2.py`, Phase 1 및 개인화 구조 감사  
버전 관계: v2.1은 v2를 덮어쓰는 수정이 아닌 별도 후보 설계. v2 코드·parameter·config·모든 결과는 변경하거나 재해석하지 않음.

## 1. 설계 목적과 의미 경계

목적은 history MAE를 낮추는 것이 아니라, **같은 관측 HR·체온·SpO₂가 개인의 평소 상태, 외부 활동능력, 지속 가능 자원, 회복 상태에 따라 서로 다른 부담과 자기보고 상태에 대응할 수 있는 생성 구조**를 만드는 것이다. HR은 workload·탈진의 원인이 아닌 잠재 생리상태에서 나온 *관측값*이다. 운동부담도 `HR→점수`로 생성하지 않는다. 같은 잠재 원인이 HR과 부담에 각각 영향을 주며, 부담에는 HR로 완전히 알 수 없는 개인 capacity·reserve·회복 debt가 별도로 영향을 준다.

Target 의미는 v2와 동일하게 유지한다. `burden`은 완료한 활동에 대한 0–10 주관적 운동부담, `fatigue`는 측정 시점의 0–10 주관적 피로, `condition`은 0–10 합성 현재상태 자기보고 양호도이다. 어느 것도 질병 진단, 군 임무수행능력, 의학적 readiness 또는 실제 탈진 시간을 의미하지 않는다. `tolerance reserve`는 새로운 **잠재 설명변수**이지 측정된 임상량이나 검증된 체력등급이 아니다.

## 2. 제안 생성 그래프

```text
개인 baseline b_i ───────────────────────────────→ true HR·체온·SpO₂ → 센서/품질/결측 → observed values
개인 capacity C_i ──┐
외부 활동요구 W_t ──┼→ relative demand x_i,t(u) ──→ acute strain S_i,t(u) ─────┬→ 생리신호
미관측 과업오차 ────┘                     │                       └→ burden/fatigue/condition 잠재 구성
개인 typical response g_i ────────────────┘                                   │
개인 tolerance 특성 T_i ─→ reserve R_i,t(u) ← 강도×지속시간 ────────────────────┤
개인 recovery 특성 τ_i ─→ 이전 recovery debt D_i,t ────────────────────────────┤
수면·스트레스 등 미관측 상태 U_i,t ─────────────────────────────────────────────┤
                                                                              ↓
                                                          target-specific reporting process
                                                                              ↓
                                                                     관측 0–10 label

과거 센서/활동/시간 정보 → baseline·typical response·recovery·개인내 변동 추정 → 예측 모델
과거·현재 target label → history 입력 금지
```

`W`는 HR이 아니다. 속도·파워·거리/시간·표준화된 과업 강도 같은 **독립적인 외부 활동 요구**를 뜻한다. 현재 v2 자료에는 대다수 활동에서 이를 직접 확인할 기록이 없다. v2.1에서 `W`를 단순히 RPE/운동부담 target으로 대체하면 target leakage이므로 금지한다. 외부 workload를 확보하지 못한 활동은 미관측 강도와 관측 활동종류·시간을 구분해 표시하고, 해당 활동의 capacity·reserve 추정 가능성을 제한해야 한다.

## 3. 최소 구조의 생성식 초안

다음 식은 **변수 관계 제안**이며 계수·분포·강도 함수의 수치 확정이 아니다. `u`는 한 활동 안의 경과시간, `t`는 session이다. 운동 중 연속 파형이 없는 경우 `W_t(u)`를 구간별 일정하다고 가정할 수 있으나 이는 별도 simulation assumption이다.

```text
개인 고정 특성:
  b_i = (평소 HR·체온·SpO₂ 기준과 생리 반응 기준)
  C_i,a = 활동 a에 대한 독립 성능검사 기반 외부 workload capacity
  g_i,a(x) = 활동 a, 상대 요구량 x에서의 전형적인 생리 반응 함수
  T_i,a = 기준 상대 강도에서의 지속/소진 특성
  τ_i = 회복 속도; σ_i = 개인내 생리 변동

활동 요구와 잠재상태:
  x_i,t(u) = external_workload_t(u) / C_i,a × task_efficiency_i,t(u)
  R_i,t(0) = function(previous_reserve, rest_gap, τ_i, prior_debt)
  dR_i,t(u)/du = - κ_i × φ(x_i,t(u))   (활동 중; φ는 강도에 따라 증가)
  reserve_depletion_i,t = R_i,t(0) - R_i,t(end)
  prior_debt_i,t = decay(previous_debt_i,t-1, rest_gap, τ_i)
  acute_strain_i,t = f(x_i,t, R_i,t, prior_debt_i,t, g_i,a, heat_i,t, U_i,t)
  after_debt_i,t = h(prior_debt_i,t, integrated_relative_demand, reserve_depletion, heat, U_i,t)

생리 관측 생성:
  true_pre_HR_i,t = baseline_HR_i + effect(prior_debt_i,t) + process_variation
  true_post_HR_i,t = true_pre_HR_i,t + g_i,a(x_i,t, acute_strain_i,t) + process_variation
  true_temperature/SpO₂ = 별도 잠재 열·산소 상태와 개인 기준에서 생성
  observed signal = true physiology → 고정 센서 bias·측정오차·artifact·결측·quality

정답 생성:
  latent_burden_i,t = F_b(relative_demand, reserve_depletion, acute_strain,
                        prior_debt, unobserved_task_or_wellness)
  latent_fatigue_i,t = F_f(prior_debt, remaining_reserve, acute_strain,
                         unobserved_wellness)
  latent_condition_i,t = F_c(remaining_reserve, prior_debt, acute_strain,
                           thermal/oxygen strain, unobserved_wellness)
  observed_label_i,t,target = clip_0_10(
      scale_target(latent_target)
      + independently specified reporting_bias_i,target
      + independently specified occasion_error_i,t,target)
```

`F_b`는 relative demand, reserve depletion, acute strain, prior debt, 미관측 요인 각각의 의미를 유지하는 단조성·상호작용 후보를 결과 전에 등록한다. 모든 항을 더한 뒤 임의로 점수를 크게 만들지 않는다. `F_f`와 `F_c`는 burden label을 입력으로 쓰지 않는다. 피로는 회복 부족과 현재 소진에, 현재상태는 양호도 방향으로 남은 reserve·회복 상태·급성 반응과 비관측 상태에 연결하되 세 target은 서로 다른 자기보고 구성개념으로 유지한다. 일상·근무 전 확인에서는 당일 활동이 없을 수 있으므로 `burden`을 억지로 생성하지 않고 fatigue/condition만 평가한다.

개인 기준 대비 반응은 **생성식의 HR 원인으로 역투입하지 않는다.** 모델의 observed feature에서만 다음과 같이 표현한다.

```text
relative_HR_response = (current_post_HR - estimated_baseline_HR_i)
                       / estimated_typical_response_i(activity, external_workload)
response_residual = current_HR_response - estimated_typical_response_i(...)
```

분모가 충분히 식별되지 않았거나 history가 짧으면 비율을 강제로 계산하지 않고 불확실성·cold-start를 표시한다. HR 절대값도 함께 보존해 정보 소실을 막는다. 체온·SpO₂의 개인 기준 대비 변동도 근거가 있는 측정 위치와 반복 기록이 있을 때만 사용한다.

## 4. History가 추정해야 할 것과 누수 차단

| 과거 정보로 추정할 개인 특성 | 필요한 과거 기록 | v2.1에서의 역할 | 불확실성 처리 |
|---|---|---|---|
| Baseline | 동일 측정 조건의 안정 시 HR·체온·SpO₂ | 현재값을 개인 기준과 비교 | 기록 수·측정 품질·개인내 분산을 함께 보존 |
| Typical response | 외부 workload와 시간, 활동 전후 센서 쌍 | 같은 활동 요구에서 예상되는 HR/열 반응 추정 | workload 범위 밖 외삽 표시; 활동별 자료 부족 시 population prior 사용 |
| Recovery | 활동 종료 후 시간표가 있는 반복 측정 및 다음 session 상태 | 회복 곡선·잔여 debt 추정 | 측정 간격이 없으면 tau 추정 불가로 표시 |
| Within-person variability | 반복된 동일 조건 관측 | 의미 있는 변화와 평소 흔들림 구분 | 평균만 사용하지 않고 분산·유효 표본수 제공 |

History는 해당 예측 시점 **이전**의 같은 subject 기록만 사용한다. 현재·미래 관측, 과거 target·target 평균, 생성기의 참 latent/개인 parameter를 observed 모델에 넣지 않는다. 휴식·활동·측정 위치를 섞어 하나의 baseline으로 만들지 않는다. `k=0`은 population prior와 불확실성을 갖는 cold-start이며, `k` 증가가 언제나 성능 개선을 낳아야 한다고 가정하지 않는다. 과거 기록이 실제로 `C_i`, `T_i`, `τ_i`를 식별할 수 있는지는 별도 복원 감사를 먼저 해야 한다.

## 5. 동결 v2와 제안 v2.1의 관계

| 영역 | 동결 v2 | v2.1 제안 | 처리 |
|---|---|---|---|
| Subject-level 분할·세션 격리·test 미사용 | 72/24/24, 시간 선행 history | 동일 원칙 유지; v2.1 전용 split manifest/사전등록 | **유지** |
| 실제 자료의 경험적 참고값 | PMData 등 소규모·비군집단 참고 | 출처와 적용 범위를 유지하되 군 population estimate로 승격하지 않음 | **유지** |
| 센서 true→observed, 품질·결측·artifact | 센서별 측정과정 분리 | 원칙 유지; 선정 장치의 오차 분포는 별도 근거 필요 | **유지** |
| 날씨·미관측 노출 | station weather와 local exposure 분리 | 원칙 유지; 임무/복장 노출은 별도 근거 전까지 미관측 | **유지** |
| Target 의미와 보고과정 | 세 개의 0–10 자기보고 합성 target; bias/noise 분리 | 동일 의미를 유지하고 noise 근거를 독립 확보 | **유지·명료화** |
| 활동 입력 | 활동시간·종류 관측, task 강도 대부분 잠재 | HR/RPE와 독립된 외부 workload를 정의; 없으면 미관측으로 표시 | **변경 필요** |
| 개인 capacity | dimensionless lognormal 배율로 `duration/capacity` | 활동/과업별 검증 가능한 외부 수행능력 기준 `C_i,a` | **재정의** |
| 개인 반응 | response 배율이 post_cv 등에 작용 | 동일 workload에서의 전형 반응 함수와 개인내 변동을 분리 | **재정의** |
| 지속 능력 | 별도 reserve·최대 지속 개념 없음 | 강도×시간에 따른 `tolerance reserve` 상태와 소진 경로 | **신규** |
| 회복 | session 간 `tau_i`로 이전 debt 감쇠 | rest interval·반복 측정에 맞춘 reserve 회복과 느린 debt 회복을 구별 | **확장** |
| 운동부담 정답 | dose·CV·이전 debt 중심 | relative demand + reserve depletion + acute strain + prior debt + 미관측 요인 + 보고과정 | **변경 필요** |
| 피로·현재상태 정답 | debt·급성 생리상태·비관측 상태 | reserve/회복 궤적과 연결하되 별도 자기보고 target 유지 | **재검토** |
| History feature | 과거 센서의 robust center와 과거 HR 반응/시간 요약 | baseline, workload-조건부 반응, 회복, 개인내 변동과 추정 불확실성 | **변경 필요** |
| v2 결과 | Phase 1 및 감사 artifact 동결 | v2.1 결과는 새 이름·새 protocol·새 artifact로만 생성 | **보존** |

## 6. Parameter 근거 등록 초안

여기서는 **필요 자료와 근거 유형만 정의한다. 수치·LOW/BASE/HIGH를 확정하지 않는다.** 기존 v2 값을 관성적으로 복사하지 않는다.

| Parameter 또는 parameter family | 구현 전 근거 | 현재 상태 |
|---|---|---|
| 활동별 external workload의 단위·측정시점·강도 궤적 | 독립 기록(속도/거리/파워/과업 기준)과 동기화된 센서·자기보고 | **NEEDS_SOURCE**; 현재 다수 활동에서 관측 강도 부재 |
| 개인 capacity `C_i,a`의 정의·분포·활동 간 전이 | 독립 성능검사와 반복 과업 기록; 날짜·활동 대응 확인 | **NEEDS_SOURCE**; 현 5 km 자료는 제한적 running 참고값만 제공 |
| 개인 baseline·typical response·개인내 변동 | 동일 센서·측정조건에서 반복된 안정/활동 전후 관측 | **PARTIAL EMPIRICAL REFERENCE**; 군 population 값은 미확인 |
| 상대 강도별 지속 가능 시간 및 reserve 감소 곡선 | 고정 또는 표준화 강도에서의 반복 지속/중단 기록, 동기화된 생리·RPE | **NEEDS_SOURCE**; 현재 자료로 식별 불가 |
| 휴식 간격별 HR/상태/수행 회복 곡선 | 여러 post-activity 시점과 다음 session의 반복 측정 | **NEEDS_SOURCE**; v2 tau는 실증 추정값 아님 |
| burden·fatigue·condition 구성개념 및 0–10 척도 사용 | 각 target의 명확한 설문·시점·반복 측정; 가능하면 개인별 재검사 | burden RPE만 제한적 참고; fatigue/condition은 **NEEDS_SOURCE** |
| 개인별 reporting bias와 session별 label noise | 동일 조건 반복 라벨·반복 평가자·검사-재검사 자료 | **NEEDS_SOURCE**; 현재 v2 수치 승계 불가 |
| 완성 장치의 HR·체온·SpO₂ 오차·artifact·SQI | 선정 기기/측정부위의 공식 사양과 독립 reference 비교 | **NEEDS_SOURCE**; 사양의 accuracy bound를 Gaussian SD로 치환 금지 |
| reserve의 함수형 `φ`, 상태 경계, reserve/debt 상호작용 | 특정 반복 과업 자료가 없으면 구조 가정 | **SIMULATION ASSUMPTION** |
| 급성 strain→각 생리신호 및 target의 연결 함수 | 적합한 동일 과업/인구/측정시점 자료 없으면 구조 가정 | **SIMULATION ASSUMPTION**, 가능한 문헌은 sanity constraint로만 사용 |
| 활동 간 공통 capacity 계층·효율의 개인차·미관측 과업 요인 | 여러 활동을 같은 인원에게 반복한 자료 없으면 구조 가정 | **SIMULATION ASSUMPTION** |
| 미관측 wellness/task 분포와 시간상관 | 독립 종단자료가 없으면 구조 가정 | **SIMULATION ASSUMPTION** |
| 군 장병 population 분포와 임무 맥락 | 해당 집단의 실측 자료 | **UNKNOWN**; PMData를 군 추정값으로 대체 금지 |

개인화 효과 크기(`C`, typical response, reserve, recovery, target coupling)와 label noise·reporting bias는 **서로 독립된 자료·근거로 정한다.** 효과가 noise보다 작다는 이유로 효과 계수를 키우거나 noise를 줄이지 않는다. 근거가 없는 항목은 사전에 여러 sensitivity 시나리오로 등록하고 결과 전체를 보고한다. 실제 라벨 반복성이 없다면 noise는 `UNKNOWN`이며, 모델 MAE·history 이점으로 역산해 원하는 수치를 정하지 않는다. 구조·parameter·평가 기준을 고정한 뒤 결과를 보고, 이후 변경은 v2.1 amendment 및 새 artifact로만 기록한다.

## 7. 필수 반사실 가능성 및 구현 전 검증 기준

설계상 같은 외부 활동조건에서 A는 낮은 `C_A`·작은 초기 reserve·느린 회복, B는 높은 `C_B`·큰 reserve·빠른 회복을 가질 수 있다. A와 B의 개인 baseline·typical HR response·생리 교란이 달라서 **관측 post-HR가 둘 다 약 120 bpm**인 겹침 구간이 존재한다면, 잠재 원인 `relative demand`, `reserve depletion`, `prior debt`는 다를 수 있다. 따라서 A의 burden이 높고 B의 burden이 낮은 경우를 **HR을 target 원인으로 쓰지 않고** 생성할 수 있다. 동일한 상대 강도에서도 `T_i`가 다르면 reserve가 소진되는 시간과 휴식 후 회복 궤적이 달라질 수 있다.

이는 **구조적 표현 가능성**이지 실제 사람에서 그 차이의 크기나 빈도를 입증한 결과가 아니다. 구현 전 protocol에는 다음을 결과와 무관하게 명시해야 한다.

1. 같은 외부 workload·시간·날씨에서 개인 특성만 바꾸는 반사실; 다른 외생 추첨값·보고 편향은 고정.
2. 비슷한 HR(예: 사전 지정 구간)로 조건부 매칭했을 때 capacity·reserve·prior debt 차이와 burden 차이를 모두 보고. 겹치는 HR 사례가 적으면 **평가 불가**로 기록하고 생성 parameter를 맞추지 않음.
3. 같은 상대 강도에서 시간 경과별 reserve·acute strain·HR·burden trajectory와 회복 곡선을 비교. `T_i` 차이가 실제 생성 궤적에 나타나는지 확인.
4. 개인 parameter를 history가 얼마나 복원하는지와 target 예측에 추가 정보가 되는지를 분리 평가. `k=0`과 `k>0`이 같거나 history가 악화돼도 그대로 보고.
5. target shuffle, history 시간선행, subject/session 분리, train-only preprocessing, sensor→target 직접 경로 부재, 정답의 trivial recoverability 및 측정 분포를 검증.

**구현 시작 전 미결정 사항:** 외부 활동강도의 관측 정의, `capacity`와 `tolerance`를 구분해 측정할 독립 과업, 회복을 관측할 시간표, 세 자기보고 target의 수집 시점과 반복성, 장치별 실제 오차 자료, 근거 없는 구조 parameter의 사전 sensitivity 범위. 이들이 확정되기 전에는 v2.1 수치 config나 본 실험을 만들지 않는다.
