# v2.2-multi-activity Amendment 03 — 개인 회복차와 pre-HR 관측식

작성일: 2026-09-28  
결과 열람 상태: **v2.2 데이터·예측 결과 미생성·미열람**  
변경 이유: generator 함수 서명 점검에서 `tau_slow_i`의 개인차 분포와 활동 전 HR 관측식이 미정임을 확인함. 생성 또는 모델 결과를 본 뒤 변경한 사항이 아님.

## 1. 개인별 회복차

```text
recovery_multiplier_i ~ Triangular(0.75, 1.00, 1.25)
tau_slow_i = configured_tau_slow * recovery_multiplier_i
```

이 범위는 `SIMULATION_ASSUMPTION`이며 실제 장병 회복시간 분포가 아니다. 개인 이력 효과를 높이기 위해 조정하지 않는다. 동일 개인은 두 활동에서 같은 multiplier를 사용하여 공통 회복특성을 표현한다.

## 2. 활동 전 HR

```text
true_pre_HR = HR_baseline_i + 5*debt_pre
              + Normal(0, (physiology_SD/2)^2)
observed_pre_HR = true_pre_HR
                  + Normal(0, measurement_SD^2)
```

활동 후 HR식은 Amendment 01을 유지한다. pre/post 생리변동과 측정오차는 독립 stream이다. 회복 시점 HR은 이번 core에서 생성하지 않으며 `UNKNOWN`으로 유지한다.

## 3. 판정

추가 미결정 구현값이 없으므로 generator 구현 `PASS`를 유지한다.

