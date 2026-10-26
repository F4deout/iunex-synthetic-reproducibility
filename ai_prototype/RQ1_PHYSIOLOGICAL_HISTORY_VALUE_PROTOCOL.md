# RQ1 생리·수행 이력의 추가 정보가치 사전등록 프로토콜

상태: **DESIGN LOCKED / IMPLEMENTATION NOT STARTED**  
작성일: 2026-10-07  
적용 범위: 합성자료를 이용한 구조적 식별 가능성 및 민감도 연구

## 1. 연구 목적

과거 자기보고 점수를 사용하지 않은 상태에서, 개인의 과거 생체반응·운동조건·수행결과·회복정보가 현재 관측정보에 더하여 다음 결과를 예측하는 데 추가 정보를 제공하는지 평가한다.

1. 보고과정 적용 전 합성 생리상태 구성값
2. 예정 과업의 완료 여부, 관측 중단시간 및 회복지연
3. 별도 보조 결과인 관측 자기보고 점수

본 연구는 실제 장병의 생리상태, 임무수행 가능 여부 또는 의료적 판단의 정확도를 검증하지 않는다. 합성환경에서 어떤 종류의 과거 정보가 개인 변화와 과업결과를 식별할 수 있는지를 검토한다.

## 2. 기존 연구와의 관계

- PRETASK, v2.1, v2.3 및 RQ1 longitudinal v2의 protocol·generator·result artifact를 변경하지 않는다.
- 기존 자기보고 점수 개선은 `REPORTING_STYLE_DOMINANT` 결과로 보존한다.
- 기존 수행결과 개선은 합성환경 내부의 정보가치 결과로 보존한다.
- 본 프로토콜의 결과를 이용하여 기존 simulator parameter 또는 과거 결과를 사후 조정하지 않는다.
- 새 구현과 결과는 별도 파일·폴더·manifest·hash로 관리한다.

## 3. 연구질문

### 3.1 주 연구질문 RQ1-P

현재 생체정보와 현재 운동조건을 알고 있을 때, 과거 자기보고를 제외한 개인별 생체반응·운동·회복·수행 이력이 보고과정 적용 전 합성 생리상태 구성값의 예측오차를 줄이는가?

### 3.2 주 연구질문 RQ1-T

현재 생체정보와 예정 과업조건을 알고 있을 때, 과거 자기보고를 제외한 개인별 수행·중단·회복 이력이 예정 과업의 완료 여부, 관측 중단시간 및 회복지연 예측에 추가 정보를 제공하는가?

### 3.3 보조 연구질문 RQ1-S

관측 자기보고 점수의 개선 중 과거 자기보고가 담당하는 부분과 객관적 이력이 담당하는 부분은 각각 어느 정도인가?

RQ1-S는 생리상태 개인화의 성공기준으로 사용하지 않는다.

## 4. 증거수준과 용어

- **객관적 이력:** 과거 시점에 관측 가능한 센서값, 운동조건, 실제 수행시간, 완료·중단, 중단시간 및 회복 관측
- **자기보고 이력:** 과거 피로·현재상태·운동부담 점수
- **합성 생리상태 구성값:** 보고편향과 보고오차가 적용되기 전의 simulator 내부 상태로, 실제 임상 정답이 아닌 구조 감사용 정답
- **관측 과업결과:** 합성환경에서 생성된 완료 여부, 관측 중단시간 및 회복지연
- **추가 정보가치:** 동일 평가표본에서 현재정보 모형보다 과거정보 모형의 사전등록 평가오차가 감소하는 현상

## 5. 자료군

### 5.1 공통 구성

- final seed: `110, 220, 330, 440, 550`
- seed별 합성대상자: 120명
- 대상자 분할: train 72명 / validation 24명 / ID-test 24명
- train·validation·ID-test 대상자 교집합: 0
- 동일 대상자의 모든 session 및 파생표본: 하나의 split에만 배정
- 최종 평가 session: 모든 입력조건과 이력 길이에서 동일하게 유지
- 기존 RQ1 longitudinal v2의 30개 최종 평가 session 구조를 유지

### 5.2 NATURALISTIC

- 기존 동결 종단 생성기의 관측간격과 수행능력 변화 빈도를 그대로 유지
- 향상·안정·저하 사례의 비율을 결과에 맞춰 재배정하지 않음
- 변화사건 직후 표본이 적으면 그 자체를 support limitation으로 보고
- 전체평균과 변화사건 전·직후·재안정 구간을 분리하여 보고

### 5.3 CONTROLLED CHANGE

- 목적: 개인화 효과를 강제로 만드는 것이 아니라 변화 추적의 식별 가능성 확인
- seed별 120명을 향상 40명, 안정 40명, 저하 40명으로 사전 배정
- 각 split 내부 구성: train은 각 24명, validation과 ID-test는 각 8명
- 향상·저하 대상자는 사전 고정된 평가경계에서 한 번의 수행능력 변화사건을 갖고 안정 대상자는 변화사건을 갖지 않음
- 평가구간: 변화 전, 변화 직후 및 재안정 구간을 동일 규칙으로 구성
- 변화 크기의 LOW·BASE·HIGH 값은 구현 전 별도 parameter register에서 동결
- 통제조건의 결과를 자연발생 변화의 빈도나 실제 장병의 적응분포로 해석하지 않음

## 6. 입력조건

모든 조건은 현재 시점에서 관측 가능한 현재정보를 공통으로 사용한다. 현재 자기보고 정답, 미래자료 및 simulator latent는 입력하지 않는다.

| 조건 | 입력정보 | 역할 |
|---|---|---|
| C0 | train 기준 평균·비율 | 무정보 기준선 |
| C1 | 현재 센서·현재 운동조건·사전 허용 기본정보 | 개인 이력 없는 기준모형 |
| C2 | C1 + 과거 센서반응 | 센서 이력의 추가 가치 |
| C3 | C1 + 과거 운동조건·수행시간·완료·중단 | 수행 이력의 추가 가치 |
| C4 | C1 + 과거 회복간격·회복관측 | 회복 이력의 추가 가치 |
| C5 | C1 + C2~C4의 전체 객관적 이력 | 주 개인화 조건 |
| C6 | C5 + 과거 자기보고 | 보고성향을 포함한 보조조건 |
| C7 | C1 + 과거 자기보고만 | 자기보고 경로 대조조건 |

### 6.1 과거 센서반응

- 같은 측정상황의 안정 기준선
- 운동종류·외부 운동부하·지속시간에 조건화한 심박반응
- 활동 전후 체온·SpO₂ 변화와 품질·결측정보
- 개인 내 변동과 시간순 변화기울기

### 6.2 과거 수행정보

- 운동종류와 외부 운동부하
- 계획·실제 수행시간
- 완료·중단 여부와 관측 중단시간
- 실제 관측된 중단사유 범주
- 독립 선행 수행기록과 시간에 따른 변화

완료 session에서 관측되지 않은 가상 중단시간은 입력하지 않는다.

### 6.3 과거 회복정보

- 운동 종료 후 경과시간
- 사전 지정 회복시점의 관측 심박반응
- 다음 session 이전의 회복간격
- 관측 가능한 회복지연 기록

## 7. 금지 입력

- 현재 또는 미래 target과 그 산술변환
- 평가시점 이후의 센서·수행·자기보고 기록
- true 수행능력, 수행예비량, latent state, reserve, debt, strain
- true recovery parameter와 개인별 reporting bias
- 대상자 식별자 자체
- 전체자료에서 계산한 평균·결측대체값·표준화값
- 완료 session의 미관측 가상 중단시간

금지 입력은 audit artifact에는 보관할 수 있으나 predictor feature 목록에 포함하지 않는다.

## 8. 이력 길이와 시간순서

- 이력 길이: `k = 0, 5, 10, 20, 30, 50, 75, 100`
- 모든 k에서 동일 대상자와 동일 평가 session 사용
- 각 k에서 특징생성, train-only 전처리, validation 모델선택 및 재학습을 독립 수행
- 최근 k건 기본요약과 30일·90일 시간창 및 30일 반감기 요약을 사전등록 보조조건으로 유지
- 이력은 평가시점보다 앞선 기록만 포함
- 기록 수 증가가 성능향상을 만든다고 가정하지 않음

## 9. 예측대상

### 9.1 RQ1-P 주 대상

- 보고과정 적용 전 피로 구성값
- 보고과정 적용 전 현재상태 구성값
- 활동 후 운동부담 구성값

이는 simulator 내부의 합성 구조 감사용 target이며 실제 시스템의 직접 출력이나 실제 장병의 객관적 생리상태로 간주하지 않는다.

### 9.2 RQ1-T 주 대상

- 예정 과업 완료 여부
- 미완료 과업의 관측 중단시간
- 사전 정의한 회복 기준까지의 회복지연

완료 session이 포함되면 관측 중단시간 분석에서 right-censoring 구조를 별도로 적용한다. 단순 회귀는 중단시간이 실제로 관측된 session에만 사용한다.

### 9.3 RQ1-S 보조 대상

- 관측 피로 자기보고 점수
- 관측 현재상태 자기보고 점수
- 관측 운동부담 자기보고 점수

## 10. 모형과 모델 선택

### 10.1 주 모형

- 연속 target: Ridge 회귀
- 완료 여부: 정규화 로지스틱 회귀
- Ridge 및 로지스틱 규제강도 후보는 train·validation에서만 선택
- 기존 동결 후보군을 승계하며 정확한 후보값은 구현 manifest에 기록

### 10.2 기준모형

- 연속 target: train mean 또는 train median
- 완료 여부: train 완료율
- C1 현재정보 모형
- 단순 개인 최근값 및 최근평균은 자기보고 보조분석에만 사용

### 10.3 비선형 probe

- 정보 존재 여부를 확인하기 위한 사전 고정 비선형 모형 1종만 audit-only로 허용
- 비선형 probe가 개선되어도 주 Ridge 결과를 대체하지 않음
- 과도한 hyperparameter tuning 금지

## 11. 학습·검증·시험 절차

- preprocessing fit: train only
- hyperparameter 선택: validation only
- ID-test: 최종 평가에만 사용
- 모든 입력조건과 k는 같은 ID-test 평가 session 사용
- 결과 확인 후 feature, generator, target coupling, noise 또는 변화빈도 수정 금지
- NATURALISTIC과 CONTROLLED CHANGE의 절대성능을 직접 우열로 비교하지 않고 각 자료군 내부의 추가 정보가치를 비교

## 12. 평가 지표

### 12.1 연속 target

- MAE
- RMSE
- R²
- 동일 seed·동일 평가표본의 paired error difference

### 12.2 완료 여부

- Brier score
- calibration error
- 필요 시 AUROC를 보조지표로만 보고

### 12.3 보고단위

- seed별 결과
- 5개 seed mean±SD
- paired difference의 기술적 95% CI
- 개선방향이 일치한 seed 수

5개 합성 seed의 구간을 실제 사람 모집단의 신뢰구간이나 통계적 유의성으로 표현하지 않는다.

## 13. 변화 추적 평가

다음 구간을 전체평균과 별도로 보고한다.

1. 변화사건 이전 안정구간
2. 변화 직후 구간
3. 변화 이후 재안정 구간
4. 변화사건이 없는 대상자

CONTROLLED CHANGE에서는 향상·저하 방향을 분리한다. NATURALISTIC에서 구간별 표본이 부족하면 효과 없음으로 대체하지 않고 `SUPPORT_LIMITATION`으로 판정한다.

## 14. 사전등록 반증시험

1. target shuffle
2. 핵심 feature shuffle
3. history subject identity destruction
4. history time-order destruction
5. 과거 자기보고 제거
6. 센서 이력 제거
7. 수행 이력 제거
8. 회복 이력 제거
9. 변화사건 방향 label permutation 감사

모델이 실패해야 할 조건에서 성능이 붕괴하지 않으면 해당 결과를 해석하지 않는다.

## 15. 필수 누수·재현성 검사

- train·validation·ID-test subject 교집합 0
- 동일 대상자 session의 split 간 교차 0
- 현재·미래 history 포함 0
- target 파생값 입력 0
- latent 입력 0
- preprocessing의 validation·test fit 0
- 모든 k의 평가 session identity 일치
- 동일 seed·config의 자료·예측·평가 완전 재현
- assignment metadata만으로 latent 수행능력을 거의 완전 복원할 경우 design-induced proxy leakage 경고

## 16. 민감도 축

다음 parameter family를 결과 확인 전에 LOW·BASE·HIGH로 동결하고 선택 보고하지 않는다.

1. 수행능력 변화 크기
2. 수행능력 변화 빈도
3. 개인별 생리반응 이질성
4. 센서 측정오차와 결측
5. 회복속도 이질성
6. 자기보고 편향과 보고오차

- NATURALISTIC BASE를 주 조건으로 사용
- CONTROLLED CHANGE BASE를 식별 가능성 주 조건으로 사용
- LOW·HIGH는 민감도 결과로 모두 보고
- 정확한 값과 provenance는 구현 전 `RQ1_PHYSIOLOGICAL_HISTORY_VALUE_PARAMETERS.json`에 기록하고 hash로 동결
- 문헌 또는 현재 empirical reference로 정할 수 없는 값은 `SIMULATION_ASSUMPTION`으로 표시

## 17. 사전등록 판정

### 17.1 `PHYSIOLOGICAL_HISTORY_VALUE`

다음을 모두 충족하는 경우에만 적용한다.

- 과거 자기보고를 제외한 C5가 RQ1-P에서 C1보다 NATURALISTIC BASE와 CONTROLLED CHANGE BASE 모두 개선
- 5개 seed 중 5개에서 paired improvement 방향 일치
- paired 95% CI가 0을 포함하지 않음
- 평균 MAE 개선이 0.02점 이상
- identity 또는 time-order destruction에서 개선의 50% 이상 소실
- 결과가 C6의 과거 자기보고 추가에 의해서만 발생하지 않음

### 17.2 `TASK_HISTORY_VALUE`

- C5가 RQ1-T의 최소 한 target에서 C1과 무정보 기준선을 모두 개선
- 5개 seed 중 5개에서 방향 일치
- paired 95% CI가 0을 포함하지 않음
- 수행 또는 회복 이력 제거 시 개선이 감소

해당 판정은 합성 과업결과의 정보가치에만 적용한다.

### 17.3 `ASSUMPTION_DEPENDENT_VALUE`

- CONTROLLED CHANGE 또는 특정 민감도 조건에서만 개선되거나 NATURALISTIC support가 부족한 경우

### 17.4 `REPORTING_ONLY_VALUE`

- C6 또는 C7의 관측 자기보고는 개선되지만 C2~C5의 RQ1-P 개선이 확인되지 않는 경우

### 17.5 `NO_ADDITIONAL_VALUE`

- 객관적 이력조건이 C1과 기준모형을 일관되게 넘지 못하는 경우

target별 판정을 먼저 내리고 하나의 전체 판정으로 합치지 않는다.

## 18. 결과 보존과 변경관리

- protocol과 parameter register는 구현 전에 SHA-256으로 동결
- 이후 변경은 기존 파일을 덮어쓰지 않고 amendment로 기록
- amendment에는 변경 전·후 내용, 이유, 결과 확인 전·후 여부 및 재실험 범위를 명시
- 결과가 예상과 달라도 parameter·feature·모형을 조정하여 같은 Phase 결과를 다시 만들지 않음
- raw prediction, split manifest, config, protocol, code hash 및 validation 결과를 보존

## 19. 구현 전 남은 작업

1. 기존 longitudinal v2와 PRETASK generator의 변수·단위 crosswalk
2. LOW·BASE·HIGH parameter 값과 provenance 등록
3. CONTROLLED CHANGE의 정확한 사건크기와 구간경계 등록
4. 완료자료가 포함되는 관측 중단시간의 censoring 평가 명세 확정
5. audit-only 비선형 probe 1종과 소규모 고정 grid 확정

위 항목의 parameter register와 hash가 생성되기 전에는 generator를 구현하거나 본 실험을 실행하지 않는다.

## 20. 현재 진행판정

**`PROTOCOL_LOCK_READY / PARAMETER_REGISTER_REQUIRED`**

연구질문, 입력정보, 자료군, 누수통제, 평가방법 및 성공·제한 판정은 구현 전에 고정할 수 있다. 다음 단계는 신규 실험이 아니라 최종 parameter register 작성과 기존 변수 crosswalk 감사이다.
