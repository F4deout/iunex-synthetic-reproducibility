# RQ1 longitudinal v2 parameter amendment 02

## 1. 작성 이유

잠긴 최종 parameter를 구현 표현식으로 변환하는 과정에서 중복 오차 적용과 시간변화 반영 방식이 명시되지 않은 부분을 확인하였다. 본 amendment는 생성 결과를 보기 전에 구현식을 고정하며, 기존 수치를 변경하지 않는다.

## 2. 중복 적용 방지

1. HR의 `physiology_sd_bpm`은 true HR의 세션별 생리 변동에만 적용한다.
2. 관측 HR의 측정오차는 `measurement_process.hr_sd_bpm=2.5`만 적용한다. `physiology.measurement_sd_bpm`은 v2-minimal에서 재적용하지 않는다.
3. WEAK/BASE/STRONG·fatigue·condition 결합식은 noiseless target을 생성한다.
4. 관측 자기보고에는 `reporting_process`의 안정 편향·드리프트·드문 기준변화·세션 오차만 적용한다. `targets.personal_bias_sd_points`와 `targets.occasion_error_sd_points`를 두 번째로 적용하지 않는다.

## 3. 시간변화식

관측 간격을 `d` 일, 30일당 파라미터를 `sigma`, `p`로 두면 지속 변화는 다음과 같이 적용한다.

`delta_continuous ~ Normal(0, sigma^2 * d/30)`

드문 변화사건의 구간 발생확률은 다음과 같다.

`p_interval = 1 - (1-p)^(d/30)`

사건이 발생하면 동결된 `event_magnitude_sd` 정규분포에서 한 번 추출한다. 수행능력 변화는 log 공간에서, 보고 편향 변화는 0–10 점수 공간에서 적용한다. 대상자별 사건시점은 평가창과 무관하게 추출한다.

## 4. 유산소 수행능력과 예비량

1. PMData 5 km 기록의 속도 `v5` 자체는 predictor에 제공 가능한 선행 관측값이다.
2. 유산소 합성 capacity는 `v5 × normalized aerobic factor` km/h로 정의한다. normalized factor는 기존 v2.3의 동결 NHANES 참조분포에서 추출한다.
3. 유산소 외부 요구량은 `u × v5` km/h이며 `u∈{0.70,0.90,1.10}`이다. 따라서 생성기 내 상대 요구량은 `u/normalized aerobic factor`이다.
4. 이 capacity는 실제 CS·VO₂max·군 수행능력 측정치가 아닌 synthetic construct이다.
5. 유산소·하중 이동·순환운동의 수행 예비량 개인차는 v2.3의 동결 가정을 추가한다: task-specific log SD LOW/BASE/HIGH = 0.15/0.30/0.45, capacity–tolerance correlation = 0/0.25/0.50. 이 값은 기존 v2.3의 누락 없이 구현을 위한 재명시이며 실증치가 아니다.

## 5. 체온·SpO₂ 공통원인 경로

v2-minimal은 중립 환경에서 다음 공통원인 경로만 구현한다.

- `true_temperature = subject_baseline + 0.28*relative_demand_term + Normal(0,0.08)`
- `true_SpO2 = subject_baseline - 0.25*relative_demand_term + Normal(0,0.20)`

계수와 생리 변동은 기존 `simulator_rq1_state_mixture.py`의 정상 활동 경로를 재사용한 simulation assumption이다. 이 관측값은 target을 직접 생성하지 않고, 공통 잠재 요구량의 별도 생리 관측으로만 사용한다.

## 6. 이력 경계

각 평가 세션의 history는 `timestamp < current_timestamp`인 동일 대상자 관측만 포함한다. 현재·미래 target, true physiology, latent capacity·reserve·debt·reporting bias는 history feature에 포함하지 않는다. 이 수정은 구현 누락을 막기 위한 경계 명시이며 특징 추가·성능 조정이 아니다.
