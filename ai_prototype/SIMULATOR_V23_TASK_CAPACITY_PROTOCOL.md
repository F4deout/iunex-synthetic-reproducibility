# Simulator v2.3 task-capacity personalization protocol

상태: **사전등록 완료·generator 미구현·본 실험 미실행**  
작성일: 2026-09-28  
선행 결과: v2.2와 Phase 1 및 모든 artifact는 동결·보존한다.

## 1. 연구 목적

v2.3의 목적은 동일한 운동조건에서도 개인의 수행능력·종목별 지속능력·회복특성에 따라 상대적 요구량과 결과가 달라지는 구조를 명시적으로 표현하는 것이다. 개인 이력의 예측효과를 크게 만드는 것이 목적이 아니다. 다음 두 질문을 분리한다.

1. 개인차가 generator 안에 실제로 존재하는가?
2. 관측 가능한 과거 기록이 그 개인차를 복원하여 새로운 세션 예측에 추가 정보를 제공하는가?

첫 번째 질문이 충족되지 않으면 두 번째 질문의 음성 결과를 개인화의 무효로 해석하지 않는다.

## 2. v2.2 감사에서 확인된 수정 필요성

- PMData 5 km 기록은 15명에서 18.78–47.47분으로 넓었지만 v2.2 수행능력 보정에 사용되지 않았다.
- NHANES 추정 VO₂max 8,324명의 중앙값 정규화 10–90백분위 범위는 0.759–1.342였고 5–95백분위는 0.701–1.476이었다. 이는 일반 인구의 심폐체력 참고분포이며 군 장병 또는 종목별 수행능력 분포가 아니다.
- v2.2의 종목별 capacity는 동일한 0.8–1.2 삼각분포 가정이었다.
- 고정 난수 반사실 감사에서 capacity 0.8 대 1.2는 평가세션 완료율과 운동 후 HR을 뚜렷하게 바꾸었지만 피로와 현재상태 점수의 평균 차이는 각각 약 0.10점과 0.08점에 그쳤다.

판정은 `CAPACITY_HETEROGENEITY_UNDERSPECIFIED` 및 `CAPACITY_EFFECT_PRESENT_BUT_TARGET_EFFECT_SMALL`이다.

## 3. 근거 수준

| 근거 | 허용되는 사용 | 금지되는 사용 |
|---|---|---|
| PMData 5 km 기록 | 보유 자료에서 개인 수행기록의 이질성이 존재한다는 경험적 참고 | 행군·순환운동 capacity 또는 실제 CS로 변환 |
| NHANES 추정 VO₂max | 공통 유산소 체력 참고분포와 민감도 범위 | 군 장병 모집단 추정 또는 종목별 capacity로 직접 대입 |
| 군 하중운반 연구 | 속도·하중·경사·개인 체력의 방향과 상대부하 해석 | 현재 합성 대상자의 정확한 행군 계수로 대입 |
| critical power/load 문헌 | threshold와 유한 예비량을 구분하는 구조적 참고 | 실제 측정하지 않은 CP·W′·critical load를 합성 인원의 실측값으로 표현 |
| 순환훈련 문헌 | work/rest와 실제 반복량이 수행·피로 해석에 필요하다는 방향 | 특정 연구의 집단평균을 현재 개인분포로 복사 |

주요 근거는 CDC NHANES cardiovascular fitness documentation, Jones et al. (2016)의 critical-power review, Bergstrom et al. (2021)의 critical-load review, Pal et al. (2017)의 군 하중운반 연구 및 현재 프로젝트의 PMData 원자료다.

## 4. 개인 특성 구조

### 가. 공통 유산소 참고요인

`aerobic_reference`는 NHANES 추정 VO₂max의 중앙 90%를 중앙값으로 정규화한 경험적 참고분포에서 재표집한다. 이는 실제 대상자의 VO₂max도, 군 장병의 모집단 분포도 아니다. 극단 추정값은 공식 자료의 측정 한계를 고려하여 사용하지 않는다.

### 나. 종목별 수행능력

각 개인은 다음을 별도로 가진다.

- `march_capacity`: 주어진 속도·하중·경사 조건을 감당하는 합성 행군능력
- `circuit_capacity`: 주어진 work/rest·운동시간 조건을 감당하는 합성 순환운동능력
- `march_tolerance`: 임계 수준을 넘는 행군 요구를 감당하는 합성 유한 예비량
- `circuit_tolerance`: 임계 수준을 넘는 순환운동 요구를 감당하는 합성 유한 예비량

종목별 capacity는 공통 유산소 참고요인과 종목별 비관측 수행요인을 결합하되 완전히 같게 만들지 않는다. 두 종목의 상관은 실측값이 없으므로 LOW/BASE/HIGH 민감도 가정으로 처리한다.

### 다. 회복특성

`fast_recovery`는 짧은 휴식 뒤 종목별 예비량이 회복되는 성분이고, `slow_recovery`는 이전 활동의 누적 피로·부채가 감소하는 성분이다. 정확한 시간상수는 실측값이 없어 독립적인 민감도 가정으로 둔다.

## 5. 생성구조

```text
공통 유산소 참고요인 + 종목별 수행요인 + 이전 상태
                       + 외부 운동조건 + 회복간격
                                  ↓
                    상대적 요구량과 예비량 소진
                                  ↓
                         잠재 생리·피로 상태
                         ↙                 ↘
             true physiology             noiseless target state
                    ↓                              ↓
          sensor measurement              independent reporting process
                    ↓                              ↓
          observed physiology               observed 0–10 target
```

HR은 운동부담의 직접 원인이 아니라 잠재 생리상태에서 생성되는 관측값이다. capacity 또는 HR을 target에 직접 더하지 않는다. capacity는 동일한 외부 운동조건이 개인에게 주는 상대적 요구량과 예비량 소진을 통해서만 target에 영향을 준다.

## 6. 운동조건과 상대적 요구량

### 가. 행군

행군 외부요구량은 속도, 체중 대비 하중, 경사 및 수행시간으로 구성한다. 기존 v2.2 grid를 변경하지 않되, `relative_demand = external_demand / march_capacity`로 개인화한다. 하중과 속도의 정확한 상호작용은 문헌에서 현재 대상자 계수로 확정할 수 없으므로 잠긴 민감도 가정을 사용한다.

### 나. 순환운동

순환운동 외부요구량은 작업시간, 휴식시간, 전체 지속시간 및 실제 완료량으로 구성한다. 현재 자료에 종목별 반복·세트 원자료가 없으므로 v2.2의 시간기반 grid를 유지하며, 이를 실제 군 체력검사나 특정 종목 수행량으로 표현하지 않는다. `relative_demand = external_demand / circuit_capacity`를 사용한다.

## 7. 예비량과 누적상태

- 임계 이하에서는 예비량 소진을 0으로 허용한다.
- 임계 초과에서는 초과 상대요구량×실제 지속시간에 따라 종목별 예비량이 단조롭게 감소한다.
- 중단은 예비량 소진만으로 결정하지 않고 독립적인 session tolerance와 행동·관측 과정을 분리할 수 있도록 한다.
- 활동 뒤 fast reserve와 slow debt를 별도로 갱신한다.
- 완료 세션의 가상 중단시간은 observed history에 저장하지 않는다.

## 8. target의 조작적 정의

### 가. 운동부담

합성 운동부담 0–10점은 상대적 요구량, 예비량 소진, 급성 strain, 이전 회복부채, 비관측 세션요인 및 독립 보고과정에서 생성한다.

### 나. 피로

합성 피로 0–10점은 예비량 소진, 누적 노출, 급성 strain, 이전 회복부채, 비관측 세션요인 및 독립 보고과정에서 생성한다. capacity를 직접 입력하지 않는다.

### 다. 현재상태

합성 현재상태 0–10점은 남은 예비량, 낮은 급성 strain, 낮은 회복부채, 비관측 현재상태 요인 및 독립 보고과정에서 생성한다. 군 임무수행능력, 질병진단 또는 의학적 readiness가 아니다.

WEAK/BASE/STRONG은 개인화 잠재상태와 target의 결합강도를 결과 전에 고정한 민감도 조건이다. 모델 성능등급이나 결과 후 선택 조건이 아니다. target coupling과 reporting noise는 서로 독립적으로 정하고 모든 지정 조합을 보고한다.

## 9. 관측 가능한 개인 이력

predictor에 허용되는 이력은 현재 세션 이전의 다음 정보뿐이다.

- 종목, 외부 운동조건, 계획·실제 수행시간
- 완료·수정·중단 여부와 실제 관측 중단시간
- 활동 전·후·회복 HR 및 품질
- 회복간격
- 동일 또는 유사 운동조건에서의 반복 반응
- 실제로 반복 수집한 자기보고가 있는 경우 과거 자기보고와 질문시점

금지 정보는 true capacity, true tolerance, reserve, strain, debt, recovery parameter, 현재·미래 target, 완료 세션의 가상 중단시간이다.

## 10. 사전등록 반사실 검증

같은 seed·개인·운동조건·비관측요인·보고오차를 고정하고 다음만 바꾼다.

1. `capacity LOW/BASE/HIGH`: capacity가 높아질수록 상대적 요구량·예비량 소진·운동 후 HR이 단조 감소하고 완료 가능성이 증가해야 한다.
2. `tolerance LOW/BASE/HIGH`: capacity와 HR 반응을 고정했을 때 tolerance가 높을수록 예비량 소진율이 낮고 지속시간이 증가해야 한다.
3. `recovery LOW/BASE/HIGH`: 앞선 운동을 고정했을 때 회복이 빠를수록 다음 세션의 부채가 감소해야 한다.
4. `matched-HR`: 유사 HR 구간에서도 capacity·tolerance가 다른 개인의 상대적 요구량·남은 예비량·target이 달라질 수 있어야 한다.
5. `duration`: 같은 상대적 요구량에서 지속시간 증가가 예비량 소진과 누적상태를 단조 증가시켜야 한다.

방향성은 필수 구조검사지만 target 차이의 최소 크기는 PASS 기준으로 사용하지 않는다. 대신 `counterfactual target difference / reporting-error SD`를 보고하여 개인화 신호의 상대적 크기를 WEAK(<0.25), MODEST(0.25–0.5), MATERIAL(>0.5)로 기술한다. 이 구간은 효과의 임상적 의미가 아니라 합성 신호대잡음 감사용이다.

## 11. 검증과 평가

- 동일 seed/config byte-level 재현
- subject/session 교집합 0
- history current/future leakage 0
- latent feature 접근 0
- train-only preprocessing과 validation-only model selection
- target/feature shuffle
- mean baseline, observed Ridge, true-physiology oracle, latent oracle
- capacity/tolerance/recovery oracle은 감사 전용
- k=0/1/3/5/10/20에서 동일 evaluation session 및 독립 재학습
- 활동별 결과와 pooled 결과 분리

개인 이력 효과가 없거나 악화되어도 parameter·target coupling·noise를 결과에 맞춰 변경하지 않는다.

## 12. 기존 결과와의 관계

v2.2 Phase 1, 원인감사 및 자기보고 보정 결과는 수정하거나 대체하지 않는다. v2.3은 `task-capacity heterogeneity`가 더 명시된 별도 후속 연구다. v2.2와 v2.3의 절대 MAE를 같은 데이터에서의 성능 향상처럼 직접 비교하지 않는다.

## 13. 구현 경계

`SIMULATOR_V23_TASK_CAPACITY_PARAMETERS.json`과 본 protocol의 hash를 잠근 뒤에만 generator를 작성한다. 첫 구현에서는 dry run과 구조검증만 수행하며 본 예측실험은 별도 승인 전 실행하지 않는다. 실제 군 장병·실제 센서·안전한 운동검사 성능을 주장하지 않는다.

