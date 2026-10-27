# Simulator v2.3 evaluation-support amendment 01

상태: **평가 지원범위 보완 사전등록·parameter/생성식 변경 없음·예측 본 실험 미실행**  
작성일: 2026-09-28

## 1. 변경 이유

잠긴 v2.3 생성기의 첫 dry run에서 capacity·tolerance·recovery·duration 및 matched-HR 방향성 검사는 모두 통과했다. 그러나 기존 v2.2에서 승계한 evaluation grid의 완료율이 행군 100%, 순환운동 99.84%여서 완료/중단 또는 관측 중단시간 endpoint를 평가하기에는 지원범위가 부족했다.

이는 수행능력 parameter나 target 식을 결과에 맞춰 조정할 이유가 아니다. 본 amendment는 generator parameter와 생성식을 그대로 유지하고, **고정된 외부 운동조건을 사용하는 별도 합성 평가 지원자료**만 정의한다.

## 2. 정보 접근 제한

- workload 배정은 모든 합성 개인에게 동일한 절대조건을 사용한다.
- true capacity, tolerance, reserve, recovery, strain 및 debt를 조건 배정에 사용하지 않는다.
- 개인별 완료 가능성을 미리 계산하여 조건을 바꾸지 않는다.
- 기존 calibration, v2.2/v2.3 결과 및 workload grid는 변경하지 않는다.
- 아래 조건은 실제 장병에게 적용할 안전한 검사 protocol이 아니다.

## 3. 고정 평가 grid

### 가. LOADED_MARCH

| ID | 속도(km/h) | 체중 대비 하중 | 경사(%) | 계획시간(분) | 목적 |
|---|---:|---:|---:|---:|---|
| MS1 | 4.5 | 0.20 | 0 | 20 | 중간 외부요구·기준 지속시간 |
| MS2 | 5.5 | 0.40 | 5 | 20 | 높은 외부요구·기준 지속시간 |
| MS3 | 5.5 | 0.40 | 5 | 45 | 같은 높은 외부요구의 중간 지속시간 |
| MS4 | 5.5 | 0.40 | 5 | 90 | 같은 높은 외부요구의 긴 지속시간 |

### 나. BODYWEIGHT_CIRCUIT

| ID | work(초) | rest(초) | 계획시간(분) | 목적 |
|---|---:|---:|---:|---|
| BS1 | 20 | 20 | 14 | 중간 work/rest·기준 지속시간 |
| BS2 | 30 | 5 | 14 | 높은 work density·기준 지속시간 |
| BS3 | 30 | 5 | 45 | 같은 높은 work density의 중간 지속시간 |
| BS4 | 30 | 5 | 90 | 같은 높은 work density의 긴 지속시간 |

시간수준은 현재 demand·threshold·reserve 식의 차원분석에 따라 threshold 이하와 초과 조건을 모두 포함하도록 결과 전에 고정했다. 실제 사람의 권장 운동시간 또는 군 체력검사 기준이 아니다.

## 4. 평가 시점과 상태

- 각 event 간격은 72시간으로 고정하여 이전 event의 누적상태를 평가조건의 주된 결정요인으로 만들지 않는다.
- 모든 subject가 같은 8개 조건을 같은 ID 집합으로 받되 순서는 subject hash parity로 역전한다.
- 현재 event의 완료·실제 수행시간·중단 여부는 predictor 입력이 아니라 endpoint다.
- 완료 event에는 hypothetical stop time을 기록하지 않는다.
- 중단 event에는 실제 합성 stop time만 기록한다.

## 5. 지원범위 판정

각 활동에서 다음을 확인한다.

1. 적어도 한 조건에서 완료와 중단이 모두 존재
2. 모든 조건이 전원 완료 또는 전원 중단으로만 구성되지 않음
3. capacity·tolerance 수준에 따른 완료율 방향성
4. 완료 event에서 가상 한계시간의 observed 누출 0
5. subject/session split 교집합 0
6. 동일 seed/config 재현

조건 1이 충족되면 해당 활동의 completion/observed stop-time support는 `SUPPORTED`다. 조건 1이 충족되지 않아도 parameter나 grid를 결과에 맞춰 재조정하지 않고 `NOT_SUPPORTED`로 보존한다.

## 6. 해석 제한

이 평가는 개인 능력과 고정 외부조건의 관계가 합성 endpoint에서 식별 가능한지 확인한다. 실제 장병의 운동 지속시간, 생리적 한계, 안전한 중단기준 또는 현장 적용성을 검증하지 않는다. 이후 예측실험이 가능하더라도 all-cause synthetic stopping-time 또는 synthetic completion으로만 표현한다.

