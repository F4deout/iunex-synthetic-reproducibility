# Simulator v2.1-personalization: 러닝 한정 사전등록 프로토콜

상태: **설계 사전등록; 수치 parameter 미동결; 구현·실험 금지**  
기반: `SIMULATOR_V21_PERSONALIZATION_DESIGN.md`  
독립성: Simulator v2의 코드·config·parameter·Phase 1/감사 산출물은 동결·보존. v2.1은 새 이름, 새 parameter register, 새 artifact로만 구현 가능. 기존 v2의 생리·측정·label 숫자는 **자동 승계하지 않음**.

## 1. 연구 질문과 자료 범위

러닝의 외부 활동 요구는 **running speed** `v(u)`(m/s)이며 HR이나 RPE로 강도를 대체하지 않는다. 한 session의 `duration`은 초 단위로 기록하고, 가능하면 시각이 있는 속도 궤적을 사용한다. 평균 속도만 있으면 구간별 가감속·위 CS 시간은 식별되지 않으므로 **일정 속도라는 simulation assumption**을 별도로 표시한다. 야외 경사·노면·하중은 속도만으로 동등한 workload가 되지 않으므로, 최초 v2.1은 평지·비하중·동일 조건 러닝 범위로 제한하거나 해당 차이를 미관측 요인으로 명시한다. 군 전체 활동, 행군, 근무, 의학적 안전판정으로 일반화하지 않는다.

세 target은 기존과 동일한 0–10 **합성 자기보고** 구성개념이다: 완료한 러닝 session의 주관적 운동부담 `burden`, 측정 시점의 주관적 피로 `fatigue`, 합성 현재상태 양호도 `condition`. `burden`은 실제 Critical Speed, D′, 최대지속시간 또는 임무수행능력의 측정값이 아니다. 실제 자료의 PMData perceived exertion은 RPE 유사 target 참고자료이며, 외부 speed/사전 강도 feature로 재사용하지 않는다. 관측 시점과 질문 문구가 다른 RPE 척도를 동일한 target으로 합치지 않는다.

## 2. 근거의 사용 범위

러닝의 거리–시간 관계로 CS와 D′를 추정하는 framework 및 반복 수행시험이 필요하다는 점은 [Kordi, Menzies & Galbraith (2019)](https://pubmed.ncbi.nlm.nih.gov/30427230/)와 [de Aguiar 등(2018)](https://www.sciencedirect.com/science/article/pii/S0101328915300482)에서 확인된다. 후자는 3분 전력 러닝 시험의 CS 추정과 D′ 추정이 같은 정확도를 보장하지 않음을 보여준다. `speed = CS + D′/time`이라는 속도–시간 표현과 CS 경계의 의미는 [러닝 실험 연구](https://pmc.ncbi.nlm.nih.gov/articles/PMC6381309/)에 제시돼 있다. 간헐 러닝에서 빠른 reserve 재구성의 시간상수는 회복 강도에 따라 달라질 수 있지만, [간헐 러닝 연구](https://pubmed.ncbi.nlm.nih.gov/31776696/)는 over-ground **power/W′** 모형을 평가한 것이므로 그 수치를 speed/D′ 시간상수로 그대로 이식하지 않는다. 반복 0–10 session-RPE의 신뢰성을 조사한 [Herman 등(2006)](https://journals.assaf.org.za/index.php/sajsm/en/article/view/247)은 별도 표본·과업의 결과이며 현재 프로젝트의 label-noise SD가 아니다.

이 문헌은 **구조와 적용 한계**의 근거다. 아래 `CS_like_i`(m/s), `Dprime_like_i`(m), reserve·회복 상태는 CS/D′ framework를 참고한 **합성 구성개념**이며 현재 PMData 참여자의 실측 CS·D′나 군 장병 population estimate가 아니다. 현재 보유한 5 km 기준속도 한 개로 두 parameter를 동시에 식별하거나 `5 km speed = CS`로 둘 수 없다.

## 3. 사전 정의한 생성 구조

`i`: 개인, `s`: session, `u`: session 내부 경과초. `v_s(u)`는 외부에서 기록한 속도이다. 아래의 함수 형태는 고정할 후보 구조이며 계수·개인 분포의 숫자는 아직 **UNKNOWN**이다.

```text
개인 고정 잠재량:
  CS_like_i > 0                 # synthetic running capacity, m/s
  Dprime_like_i > 0             # synthetic finite above-threshold distance reserve, m
  g_i(relative_intensity, state) # workload-conditioned typical physiological response
  HR_baseline_i, sigma_within_i
  tau_fast_i(recovery_speed), tau_slow_i

상대 강도와 fast reserve:
  x_i,s(u) = v_s(u) / CS_like_i
  q_i,s(u) ∈ [0, Dprime_like_i]  # session 중 남은 reserve, m
  if v_s(u) > CS_like_i:
      dq/du = -(v_s(u) - CS_like_i)              # m/s; D′-like 기본 후보
  if v_s(u) < CS_like_i:
      dq/du = recharge(q, Dprime_like_i, recovery_speed, tau_fast_i)
  if v_s(u) = CS_like_i:
      dq/du = 0                                 # 경계 관례; 별도 민감도 검토 가능

slow recovery/fatigue debt:
  debt_pre_i,s = decay(debt_after_i,s-1, rest_interval, tau_slow_i)
  debt_after_i,s = debt_pre_i,s + accumulate(x trajectory, duration,
                                              reserve_depletion, heat, unobserved_state)
  # fast q의 회복과 slow debt의 감소는 다른 상태·다른 시간상수

acute strain과 생리 관측:
  strain_i,s = f(x trajectory, q trajectory, debt_pre_i,s,
                 individual_response_i, environment, unobserved_state)
  true_HR_i,s(u) = HR_baseline_i + g_i(x_i,s(u), strain_i,s, debt_pre_i,s)
                   + physiological_variation_i,s(u)
  observed_HR = measurement(true_HR, sensor_bias, noise, artifact, missing, quality)
  # temperature/SpO2 역시 자기 잠재상태에서 관측; HR은 x, q, debt의 원인이 아님

합성 target:
  latent_burden_i,s = F_b(relative_demand, fraction_reserve_depleted,
                         acute_strain, debt_pre, unobserved_factor)
  latent_fatigue_i,s = F_f(debt_pre/after, reserve_state, acute_strain,
                          unobserved_wellness)
  latent_condition_i,s = F_c(reserve_state, debt_pre/after, acute/thermal/oxygen_state,
                            unobserved_wellness)   # 높을수록 양호
  label_i,s,target = clip_0_10(score_map_target(latent_target)
                              + reporting_bias_i,target
                              + occasion_error_i,s,target)
```

위 threshold 이하는 **fast reserve가 감소하지 않는 안정상태 가능 구간**이지, 피로·느린 debt·HR drift가 절대 발생하지 않는 구간이 아니다. `q=0`은 해당 합성 과업의 예측된 한계 상태다. 그 뒤에도 같은 상한 초과 속도로 계획된 session을 끝까지 생성해 성공한 러닝으로 취급하지 않고 **완료 불가/검열**로 표시한다. 이를 부상·실제 탈진·의학적 중단 판단으로 해석하지 않는다. 회복 속도 아래의 `recharge` 형태 및 `tau_fast`는 문헌에서 보편 숫자를 복사하지 않고 새 근거 또는 사전 등록 가정으로 고정한다.

`F_b`의 다섯 생리·상황 입력은 양의 부담 방향으로 사전 정의하되, 각각의 **점수 계수**, 상호작용, clipping, 개인차와 독립 reporting process는 별도 근거/가정으로 정한다. 현재 관측 HR이나 과거 RPE label을 target 부모로 넣지 않는다. `F_f`/`F_c` 역시 burden label의 산술식으로 만들지 않는다. 같은 HR에서 부담 차이를 얻기 위해 `F_b` 계수를 크게 만들거나 label noise를 작게 만들지 않는다.

## 4. History와 평가 격리

History는 현재 시점 이전의 같은 개인에 대한 안정 HR, 시각이 있는 러닝 speed·duration, 전후 및 가능하면 운동 중 HR, 활동 후 여러 회복 시점, 동일 조건의 반복 변동을 사용한다. 목표 추정량은 `HR_baseline_i`, speed 조건부 전형 HR 반응 `g_i`, fast/slow recovery 특징, within-person variability와 각각의 불확실성이다. **CS-like와 D′-like 자체는 단순 pre/post HR history만으로 식별된다고 가정하지 않는다.** 여러 속도·지속시간에서의 독립 수행 결과나 상한 초과/회복 구간이 없으면 parameter 복원은 `NOT_IDENTIFIABLE`로 기록한다.

현재·미래 관측, target label의 과거 평균, 생성기 참 parameter, subject ID는 observed predictor 입력에서 제외한다. cold-start의 population prior는 train에서만 추정한다. `k=0/1/3/5/10/20`마다 feature·모델 선택·재학습을 독립적으로 수행하고 같은 평가 session을 사용한다. Subject-level train/validation/ID-test 분리, train-only preprocessing, validation-only 선택, ID-test 일회 사용을 적용한다. v2의 과거 결과와 직접 혼합하지 않고 v2.1 전용 manifest를 만든다. 개인 parameter 복원 성능과 target MAE 개선은 **서로 다른 질문**으로 보고하며, history 효과의 부재·악화를 그대로 보존한다.

## 5. Parameter register: 근거 유형과 수치 확정 상태

한 항목이 실제자료에서 **관측 가능**한 것과 핵심 잠재 parameter로 **식별 가능**한 것은 다르다. 아래 범주는 v2 값을 승계한다는 뜻이 아니다. 문헌의 연구 표본 평균을 현재 가상 population 평균으로 사용하지 않는다.

| ID·항목 | 분류 | 현재 가능한 것 / 구현 전 남는 것 |
|---|---|---|
| E01 running speed `v`(m/s), duration, distance, session 간격 | **1 현재 실제자료로 보정 가능** | PMData의 날짜·거리·시간이 명확히 맞는 러닝 session에서 평균속도와 시간·간격 분포 추출 가능. 초 단위 속도 궤적·경사/노면은 별도 확인 필요. |
| E02 안정 HR baseline과 개인 내 일상 변동 | **1 현재 실제자료로 보정 가능** | PMData 소수 참여자의 반복 resting HR로 empirical reference 추출 가능. 군 population 및 같은 스테이션 HR 값이 아님. |
| E03 러닝 평균 HR 대 speed의 관측 연관 | **1 현재 실제자료로 제한적 보정 가능** | 시각 매칭된 평균 HR·speed만 활용 가능. 즉시 post-HR/운동 중 HR 곡선 `g_i`의 직접 보정값은 아님. |
| E04 관측 0–10 RPE 분포 | **1 현재 실제자료로 제한적 보정 가능** | PMData 주관적 보고의 marginal 분포 확인 가능. 동일 조건 반복 신뢰도, 개인 bias, v2.1 burden 계수는 식별 불가. |
| E05 날짜가 확인된 5 km 기준속도 | **1 현재 실제자료로 제한적 보정 가능** | 소수 러너의 독립 수행속도 참고값은 계산 가능. CS-like 또는 D′-like 값으로 동일시하거나 두 값을 역산하지 않음. |
| L01 CS/D′-like 임계 구조, 단위, supra-threshold 소진 방향 | **2 문헌으로 범위·구조 제한 가능** | CS·D′의 속도–시간 관계는 위 연구의 구조 참고. 숫자/분산을 현재 인원에게 이식하지 않음. |
| L02 안정영역/심한 강도 영역의 구분, 위 임계 지속 한계 | **2 문헌으로 범위·구조 제한 가능** | threshold 아래 fast reserve 비소진과 위 임계 한계 구조를 제한. 개인별 정확한 경계·지속시간은 미확인. |
| L03 fast reserve 재구성의 recovery-speed 의존성, RPE 측정 프로토콜 | **2 문헌으로 범위·구조 제한 가능** | 회복 강도·RPE 질문/시점이 결과에 영향을 줄 수 있음. 문헌 시간상수나 신뢰도를 현재 집단 SD로 바로 사용하지 않음. |
| S01 speed 궤적 부재 시 일정속도 근사, 미관측 경사·노면 효율 | **3 simulation assumption** | 식의 형태와 범위를 결과 전 선택하고 실제 평균속도 해석의 한계를 표시. |
| S02 `recharge` 함수형, fast reserve와 slow debt의 결합 방식 | **3 simulation assumption** | 질량·단위 일관성, 경계와 단조성을 사전 검증. 개인별 빠른 회복 수치는 U03. |
| S03 acute strain·HR response·fatigue/condition의 함수형, 미관측 상태 분포 | **3 simulation assumption** | 원인 방향만 설계. 계수·분포는 근거 또는 사전 sensitivity 등록 전까지 미정. |
| S04 CS-like, D′-like, HR baseline/response, 회복의 상관구조 | **3 simulation assumption** | 자료가 없으면 독립 또는 상관 시나리오를 결과 전에 병렬 등록; 원하는 history 효과를 만드는 상관 선택 금지. |
| U01 개인 CS-like 속도 분포와 개인 D′-like 거리 분포·공분산 | **4 UNKNOWN/추가 자료 필요** | 서로 다른 거리/시간의 독립 최대 수행시험 등이 필요. 단일 5 km 기록은 CS와 D′ 둘을 동시에 결정하지 못함. |
| U02 speed·상태별 개인 HR response 및 within-person process SD | **4 UNKNOWN/추가 자료 필요** | 동기화된 speed–HR 시계열과 동일 조건 반복 측정 필요. |
| U03 fast reserve recovery 시간상수 및 recovery speed 효과 | **4 UNKNOWN/추가 자료 필요** | 개인별 반복 상한 초과–회복 간헐 러닝 기록 필요. W′/power 연구 숫자를 D′/speed로 치환 금지. |
| U04 slow recovery/fatigue debt의 시간상수·개인차 | **4 UNKNOWN/추가 자료 필요** | 러닝 종료 후 여러 시점의 반응, 휴식시간, 다음날 상태의 종단 측정 필요. |
| U05 RPE test–retest reliability, 개인 reporting bias, occasion label noise | **4 UNKNOWN/추가 자료 필요** | 같은 정의·속도·시간·질문시점의 반복 RPE 수집 필요. 단일 RPE 분포의 SD와 측정오차 SD는 다름. |
| U06 burden/fatigue/condition의 latent→0–10 coupling·절편·상호작용 | **4 UNKNOWN/추가 자료 필요** | 세 구성개념의 독립 반복 label과 관련 과업/상태 측정 필요. 특히 fatigue/condition 실제 0–10 대응자료 부재. |
| U07 최종 장치 HR·체온·SpO₂ measurement error/artifact/SQI | **4 UNKNOWN/추가 자료 필요** | 선택 장치와 측정부위의 reference 비교 필요. 공식 정확도 범위를 Gaussian SD로 간주 금지. |

E01–E05는 **경험적 보정 참고값**으로 수치화할 수 있지만 군 장병의 CS·D′·RPE 신뢰도를 제공하지 않는다. L01–L03은 물리·방향·절차의 제약이고 population parameter 표가 아니다. S01–S04는 가정임을 끝까지 표시한다. U01–U07은 `UNKNOWN`으로 유지한다. 실제 자료를 확보하지 못하면 사전 고정한 simulation scenario로만 구현할 수 있고, 각 scenario는 실측 생리 모형이라는 주장을 할 수 없다.

**독립 결정 원칙:** CS-like capacity, D′-like reserve, HR response, fast/slow recovery, RPE reliability, target coupling과 label noise는 각각 해당 독립 자료·문헌 제약·사전 가정으로 정한다. 개인화 차이를 크게 보이게 하거나 history MAE를 개선하려는 목적으로 어느 계수도 조정하지 않는다. 특히 target coupling을 올리고 label noise를 동시에 내리는 식의 사후 조합을 금지한다. 근거 부족으로 sensitivity가 필요하면 LOW/BASE/HIGH의 의미·값·source·모든 결과 보고 규칙을 **첫 v2.1 데이터 생성 전** 별도 잠금 parameter register에 기록한다. 이번 문서에서는 임의 숫자를 넣지 않는다.

## 6. 사전등록 counterfactual audit

모든 비교에서 생성기의 외생 난수, 환경, 센서오차, reporting bias와 occasion error를 공통으로 고정해 **조건부 기대 정답**과 noisy label을 나란히 보고한다. 단일 사례를 골라 결론 내리지 않고 전체 설정과 대상자 분포를 보고한다. 숫자 효과의 성공 기준을 결과를 보고 정하지 않는다. 겹침·관측 가능성이 부족하면 `INCONCLUSIVE`로 남긴다.

| 시험 | 고정할 것 / 바꿀 것 | 사전 보고항목과 반증 조건 |
|---|---|---|
| CF1 동일 절대속도 | 같은 `v(u)`, duration, 날씨, 이전 상태; CS-like·D′-like 개인 특성을 교차 | 상대강도, reserve 잔량, HR, burden의 paired 차이·분포. 같은 속도인데 capacity 경로가 정답에 전혀 영향을 주지 않으면 구조 실패. |
| CF2 동일 상대강도 | `v_i(u)/CS_like_i`가 같도록 개인별 절대속도만 설정; D′-like·response·recovery 차이는 보존 | 위/아래 threshold별 reserve 소진속도, 완료 가능 시간, HR와 burden. 같은 상대강도라도 D′가 달라 지속시간이 달라지는지 검증. |
| CF3 동일/유사 HR | CF1과 동일 외부 조건의 자연 생성 HR 중 pre-registered `118–122 bpm` overlap 쌍만 매칭. HR을 점수식에 넣거나 HR을 맞추려 latent/noise를 역조정하지 않음 | 매칭 수·capacity/D′/debt 차이·noisefree 및 noisy burden 차이. 겹침이 부족하면 `INCONCLUSIVE`; 기대 방향을 얻으려 parameter 변경 금지. |
| CF4 duration 변화 | 같은 개인·속도·초기 reserve·이전 debt·환경에서 실행시간만 변화; 사전 기간 grid는 실제 speed/duration 지원범위에서 잠금 | threshold 아래 fast reserve는 안정, 위에서는 적분된 `(v-CS)_+`에 따라 감소하는지, 느린 debt/부담 궤적과 완료 불가율. 한계 이후 성공한 post label 생성 금지. |
| CF5 recovery interval 변화 | 같은 선행 러닝과 다음 러닝, 그 사이 휴식 시간만 변화; active recovery라면 회복 speed 별도 고정 | fast q와 slow debt의 서로 다른 시간 궤적, 다음 session HR·burden. 하나의 tau로 두 상태가 사실상 동일해지면 구조 실패. |
| CF6 history→개인 parameter 복원 | 동일 평가 session, `k=0/1/3/5/10/20`; history는 과거 센서·speed·시간만 사용 | 개인별 baseline, speed-conditioned response, fast/slow recovery, within-person variability의 held-out subject R²/상관·오차·식별 가능 비율. CS/D′는 수행정보 부족 시 `NOT_IDENTIFIABLE`; target MAE와 별도로 보고. |

CF1/CF2/CF4/CF5는 **개입 비교**, CF3은 **선택된 HR overlap의 조건부 비교**라서 동일한 인과 효과로 해석하지 않는다. 검열된 session 수와 잔여 reserve 경계값도 보고한다. CF6에서 history가 개인 parameter를 복원해도 target 개선을 보장하지 않는다.

## 7. 평가·잠금·시작 조건

수치 parameter와 속도 입력 추출 규칙을 별도 `v2.1-running-parameters` artifact로 기록하기 전에는 generator 코드를 작성하거나 v2.1 데이터를 생성하지 않는다. 최소 필요 기록은 값·단위·출처/가정·적용 집단·LOW/BASE/HIGH·critical 여부·해시이다. Split의 대상자/세션 교집합 0, 미래 history 차단, train-only preprocessing, target shuffle/feature shuffle, true-physiology·latent oracle, trivial recoverability, 센서/label 분포 sanity check를 v2.1 전용 검증계획으로 고정한다. ID-test는 모델·parameter 선택에 사용하지 않는다. 기존 v2 숫자나 Phase 1 성능을 v2.1의 목표치로 삼지 않는다.

이 문서의 구조가 확정되면 SHA-256으로 보존하고 뒤의 변경은 원문 덮어쓰기가 아니라 dated amendment에 이유·변경 전 해시·결과 열람 여부를 적는다. **현재 시작 판정은 `STOP`**: E01–E05 일부만 실제 수치화 가능하며 U01–U07의 핵심 수치와 가정 sensitivity 범위가 독립적으로 잠기지 않았다. 코드는 이론상 구현 가능하지만 지금 구현하면 결과를 보고 자유롭게 숫자를 정할 여지를 남긴다.
