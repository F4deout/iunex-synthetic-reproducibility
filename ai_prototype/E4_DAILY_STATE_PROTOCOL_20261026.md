# E4 당일상태 공통원인 추가 실험

작성: 2026-10-26. 기존 논문 및 단순 기준 비교 결과를 본 뒤 설계한 보완 실험이다. 새 결과를 보기 전에 본 문서와 parameter JSON을 SHA-256으로 동결한다. 독립 확인실험이나 실제 생리상태 검증으로 부르지 않는다.

## 목적과 보존

기존 E4/G6 동일조건의 중단시간이 반복되는 현상을 보완하고, 관측 가능한 당일 상태가 있을 때 단순 과거기록과 학습모형을 비교한다. 기존 v2.1 코드·설정·결과·논문·PRETASK/후속 연구를 변경하지 않는다. 별도 generator와 별도 artifact만 생성한다. 기존 480명(독립 120명 블록 4개), 30 final seed, 288/96/96 split, 20 calibration+4 evaluation 일정, 선행 5km 수행기준과 고정 부하 배정을 그대로 사용한다. 과거 이력은 평가 이전 calibration 20개로 고정하며 앞선 evaluation은 추가하지 않는다.

## 생성 구조

개인 특성 + 이전 reserve fraction/회복부채 + 처방 운동 + 당일 잠재상태 + 관측 불가능 수행변동 → 실제 수행예비량/생리과정 → 운동 중단까지 걸린 시간.

당일 잠재상태 → 운동 전 실제 HR/체온/SpO2 → 독립 센서 측정과정 → 모형 입력.

관측 센서값으로 target을 직접 계산하지 않는다. 현재 운동 후 HR, 현재 실제 수행시간, 완료 여부, latent state는 일반 모형의 입력이 아니다. 현재 센서는 outcome 계산 전에 생성한다. 품질과 결측·artifact 발생은 잠재상태·target과 독립이다.

## 당일 상태와 수행식

`z`는 표준화된 합성 당일 상태 저하 요인이다. 클수록 더 불리하다. 수면시간·질병·임무수행 적합성을 직접 뜻하지 않는다.

```
rho_t = exp(-gap_hours / state_tau_hours)
z_t = rho_t*z_prev + sqrt(1-rho_t^2)*epsilon_t; epsilon_t~N(0,1)
s_t = tanh(z_t/2)                 # bounded signed state, -1<s<1
u_t = tanh(eta_t/2); eta_t~N(0,1) # sensor에서 보이지 않는 수행변동
D_day = D_subject * exp(-a*s_t + b*u_t)
previous_q_day = previous_reserve_fraction * D_day
```

위 D_day/previous_q_day와 기존 CS, 회복상수, 처방 속도·시간을 기존 순수 core에 전달한다. 종료 reserve fraction을 다음 session으로 전달한다. 따라서 절대 reserve의 당일 변화와 회복의 비율 상태를 혼동하지 않는다. CS 자체는 새 실험에서 변동시키지 않는다. 현재 target에 독립 난수만 더하는 방식으로 문제를 어렵게 만들지 않는다.

중단 기록은 기존 robustness BASE와 같은 ±3초 균등 시계오차와 1초 반올림을 적용한다. 예정시간 완료 사례는 우측 검열로 남기고 중단시간을 임의 부여하지 않는다. 평가시간 MAE는 동일한 실제 중단 사례에서 계산하며, 완료/중단 수를 별도 보고한다. 특정 조건의 완료/중단 구성에 맞춰 분포를 바꾸지 않는다.

## 현재 센서 측정

HR 개인 baseline은 기존 E4 profile을 사용한다. 체온·SpO2 개인 baseline과 측정 SD는 기존 PRETASK 설정을 참고하며 이 이전 설정 역시 주로 합성 가정이다. 체온은 N(36.65,0.18^2), SpO2는 N(97.5,0.7^2)을 94~99.5의 조건부 분포로 생성한다. 임의 절삭 대신 baseline만 조건부 재추출한다.

```
true_pre_HR   = subject_HR_baseline + coupling*15*s + N(0,1.3^2)
true_pre_temp = subject_temp_baseline + coupling*.25*s + N(0,.04^2)
true_pre_SpO2 = subject_spo2_baseline - .5*tanh(coupling*s) + N(0,.15^2)
```

SpO2의 과정오차는 true 값이 (0,100) 안에 있도록 조건부 재추출하고 횟수를 기록한다. 관측 SpO2는 true mean을 갖는 Beta 분포로 생성한다. concentration은 97.5%에서 nominal SD가 .6%p가 되도록 정하며 다른 mean에서 variance가 달라짐을 명시한다. artifact와 sensitivity에 따라 SD scale을 바꾸되 true mean은 유지한다. 측정범위 때문에 양의 오차를 재추출하거나 hard clipping하지 않는다. 수치적 endpoint는 nextafter로 처리하고 횟수를 보고한다. HR·체온은 additive Gaussian. nominal 측정 SD는 3 bpm/.12 C/.6 %p; missing .04, artifact .06, artifact SD multiplier=4. quality=clip(.94-.55*artifact+N(0,.035^2),0,1). 이 값은 장치 공식 정확도가 아니라 기존 합성 측정 가정의 상속이다.

관측불가 state와 센서 특이 과정잡음, 기기 측정잡음을 분리한다. 부호의 의미와 고정 상태에서 센서·target의 단조성을 unit test한다. 위 센서 결합은 문헌에서 확인된 군 장병 피로 반응식이 아니며, 강도 변화의 결과 민감도를 반드시 보고한다.

## 사전 고정 sensitivity

BASE + 각 family의 LOW/HIGH만 수행한다(11조건). 모든 조합 3^5를 실행한 것처럼 표현하지 않는다. 같은 seed/subject/session별 외생 난수를 공유한다.

| family | LOW | BASE | HIGH | 근거 및 역할 |
|---|---:|---:|---:|---|
| 상태→reserve log amplitude a | .075 | .15 | .30 | 새 critical simulation assumption, 시간 변동·현재 센서 가치에 직접 영향 |
| 상태→sensor coupling | .5 | 1 | 2 | 기존 PRETASK 반응계수를 배율화한 critical assumption, 센서 정보량에 직접 영향 |
| 관측불가 reserve amplitude b | .04 | .08 | .16 | 새 critical simulation assumption, 예측 불가능 변동 |
| measurement SD multiplier | .5 | 1 | 2 | 기존 측정 SD를 배율화한 critical assumption, 센서 정보량 영향 |
| state persistence tau, hour | 6 | 24 | 96 | 새 critical simulation assumption, 당일 상태의 시간 상관·이력 가치 영향 |

`a=.15`는 log perturbation의 계수이며 log SD .15가 아니다. s가 [-1,1]에 있으므로 관측불가 변동을 제외한 reserve multiplier 범위는 [exp(-a),exp(a)]이다. LOW는 약 .928~1.078, BASE .861~1.162, HIGH .741~1.350. 실제 분포는 tanh(N(0,1)/2)에 따라 더 중앙에 집중된다. 이 값들을 population estimate로 쓰지 않는다.

## 고정 비교군

1. 학습+검증 중단시간 평균/중앙값.
2. 개인 calibration 과거 중단시간 평균/최근값.
3. 같은 부하의 과거 중단시간 평균/최근값.
4. 부하·예정시간·gap이 같은 과거 중단시간 평균/최근값(직전 실험의 G6 복사 기준).
5. anchor log-Ridge: 선행 v5와 알려진 evaluation_order만.
6. history log-Ridge: 기존 legacy history features + 과거 운동 전 세 센서의 mean/SD/last/n. 현재 센서는 없음.
7. current log-Ridge: anchor + 현재 세 센서·quality만. 과거 이력 없음.
8. full log-Ridge: history + 현재 센서·quality.
9. state oracle log-Ridge: full + 현재 s_t. 감사용이며 일반 모형 성능으로 제시하지 않음. 관측불가 u_t는 주지 않음.

단순 기준에 해당 past stop이 없으면 학습+검증 stop mean으로 대체하고 횟수를 기록한다. history features의 과거 기록 중단시간은 새 시계오차가 적용된 관측값만 사용한다. 기존 observed mean HR도 새 상태에서 생성되며 과거에만 허용된다. 단순 복사와 full 모형은 같은 과거관측 자료에서 출발한다. 일반 모형은 현재에 추가로 측정한 센서가 있으며, 그 증분가치는 full vs history로 별도 비교한다.

모든 학습모형은 기존 log-Ridge 구조와 alpha=[1,10,100]를 사용한다. 학습만으로 전처리 fit, 검증 MAE로 alpha 선택, 학습+검증으로 전처리·모형을 재적합하고 test 평가한다. 새 신경망·interaction tuning·test 선택 없음. current/full이 불리해도 구조나 parameter를 바꾸지 않는다.

## 통계와 판정

seed가 분석 단위다. 모든 방법의 seed별 MAE/RMSE/R2, 평균±SD와 기술적 95% t 구간을 저장한다. 같은 test session에서 error difference=baseline MAE-full MAE(양수 full 유리)를 계산한다. 각 scenario의 full 대비 모든 일반 비교군을 한 family로 보정한 Bonferroni 구간도 제공한다. main contrast는 full vs exact_context_last(고정 G6 복사), full vs history(현재 센서 증분), full vs anchor다. 최저 오차의 baseline을 test를 보고 사전 기준으로 재명명하지 않는다.

성능의 목표값·승리 횟수 목표는 없다. 보정구간>0이면 해당 가정에서 full 우위, <0이면 비교군 우위, 나머지는 불확실로 보고한다. sensor가 있는 시뮬레이션에서 좋아져도 현실 타당성이나 임무수행능력 검증을 뜻하지 않는다.

## validation과 저장

프로토콜·parameter·코드 lock, 기존 source/artifact 해시 유지, subject/session split, 20건 과거 calibration 이력·현재/미래 차단, 입력 whitelist, train-only 전처리 선택과 final refit 경계를 검사한다. 같은 seed/config 생성 hash 재현, 상태 방향성, same-context 결과 차이, true/observed sensor 및 time 분포, 결측/artifact/품질, clipping/boundary mass를 저장한다. 첫 final seed BASE에서 target shuffle(학습/검증/최종fit target 무작위화), feature shuffle(각 split 내부 행 대응 파괴), quality-only predictor를 실행한다. 정상 모형이 mean 기준보다 개선되지 못하면 shuffle은 판정불가 RESULT_LIMITATION으로 남긴다. 반증시험은 성능 개선을 위한 tuning 근거로 쓰지 않는다.

원시 관측 자료와 감사용 latent는 분리 저장하고 prediction/split/history manifest/선택 alpha/최종 계수/전처리 상태/설정 및 코드 hash를 보존한다. 구현 오류는 원인·영향·수정 내역을 기록할 수 있으나 결과를 보고 parameter를 조정하지 않는다. 기존 논문을 수정하지 않는다.
