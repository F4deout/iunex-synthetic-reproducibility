# RQ1 생리·수행 이력 연구 사전등록 Amendment 01

작성일: 2026-10-07  
작성시점: generator 구현 전, dry run 및 결과 확인 전

## 변경 사유

변수 대응 감사에서 기존 PRETASK의 운동 후·회복 심박이 측정과정을 거치지 않은 참값에서 직접 계산된 사실을 확인하였다. 새 연구에서 이를 실제 관측 가능한 이력으로 사용하려면 측정시점을 사전에 고정하고, 각 시점의 값에 센서 측정오차·artifact·missingness·quality 과정을 적용해야 한다.

## 추가 방법 선택

- 운동 후 심박 측정시점: 과업 종료 직후
- 회복 심박 측정시점: 과업 종료 10분 후
- 두 측정값 모두 현재 심박과 같은 sensitivity별 측정오차·artifact·missingness·quality 과정 적용
- 실제 측정값과 품질값이 생성된 경우에만 predictor history에 포함
- 기존 `history_observable.t2_hr` 및 `t3_hr` 참값 직접 사용 금지

## 근거수준

- 분류: `METHOD_CHOICE / SIMULATION_ASSUMPTION`
- 10분은 실제 장병의 최적 회복평가 시점, 의료기준 또는 배치 프로토콜로 해석하지 않음
- 결과에 맞춰 시점을 변경하지 않음

## 영향범위

- 새 builder와 dry run에만 적용
- 기존 PRETASK generator, frozen result 및 논문 수치를 변경하지 않음
- target 생성식, capacity dynamics, reporting process 및 과업조건 변경 없음
