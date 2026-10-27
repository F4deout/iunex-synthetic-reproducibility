# v2.2-multi-activity Amendment 02 — 중단과 시간순서의 구현 전 확정

작성일: 2026-09-28  
결과 열람 상태: **v2.2 데이터·예측 결과 미생성·미열람**  
변경 이유: Amendment 01의 정적 구현 검토에서 all-cause stop의 session variation 분포와 두 활동 block의 시간순서가 수치로 닫혀 있지 않음을 확인함. 성능 또는 생성분포를 본 뒤 수정한 사항이 아님.

## 1. all-cause synthetic stopping process

```text
planned_exposure = relative_demand * planned_minutes/reference_duration
session_multiplier = exp(Normal(-sigma²/2, sigma²))
stop_threshold = tolerance_multiplier * session_multiplier

if planned_exposure <= stop_threshold:
    completed = True
    actual_minutes = planned_minutes
else:
    completed = False
    actual_minutes = stop_threshold * reference_duration/relative_demand
```

`session_multiplier`의 기대값은 1이다. `sigma` LOW/BASE/HIGH는 `0.05/0.15/0.30 log-SD`로 고정한다. `tolerance_multiplier` LOW/BASE/HIGH `0.8/1.0/1.2`와 독립 family로 실행한다. 중단은 생리적 소진이 아니라 합성 all-cause stopping event다. 완료 세션은 계획시간에서 right-censored이며 가상 limit를 observed 파일에 저장하지 않는다.

## 2. 시간순서와 공통 debt

개인별 `SHA256("v22-block-order|"+subject_id)`의 첫 바이트가 짝수이면 행군 12개 뒤 순환식 12개, 홀수이면 반대 순서다. 각 block 내부 ID 순서는 고정한다. 기본 event 간격은 72시간이며, `C09–C12`의 직전 event 간격만 parameter JSON의 `5/15/60/1440분`을 사용한다. block 전환과 calibration→evaluation 사이는 72시간이다.

평가 순서는 `ME1, CE1, ME2, CE2, ME3, CE3, ME4, CE4`를 기본으로 하고 같은 hash parity가 홀수이면 각 쌍 안에서 `CE→ME`로 뒤집는다. 결과·target·HR·중단 여부는 순서 결정에 사용하지 않는다. slow debt는 활동 사이에 공통으로 전달하지만 활동별 capacity는 공유하지 않는다.

## 3. 관측값과 audit 정보

Observed 파일에는 계획·실제 조건, 완료/중단, 실제 중단시간, gap, pre/post HR 및 보고점수만 저장한다. 개인 capacity, relative demand, strain, debt, true HR, threshold와 hypothetical limit는 audit-only 파일에 분리한다. 순환식 종목별 반복속도 근거가 없으므로 실제 반복수는 생성하지 않고 `null`로 둔다. 이를 완료율 예측 결과로 해석하지 않는다.

## 4. dry-run recoverability 기준

동일 subject split에서 mean, observed Ridge, true-HR oracle, latent-state oracle와 target shuffle을 비교한다. 이 검사는 본 실험 성능이 아니다.

- `FAIL`: observed Ridge의 test R²가 0.80 이상이면서 MAE가 latent oracle MAE의 1.10배 이내.
- `WARNING`: observed MAE가 latent oracle의 1.25배 이내이거나 observed test R²가 0.75 이상.
- `PASS`: 위 조건에 해당하지 않고 target shuffle MAE가 정상 observed MAE보다 최소 20% 악화.
- shuffle 악화가 20% 미만이면 별도 `WARNING`; 정상 observed가 mean보다 낫지 않으면 shuffle 판정은 `INCONCLUSIVE`로 보존.

분포가 기대와 달라도 parameter를 바꾸지 않는다. 구조·누수·코드 문제만 수정 대상으로 분류한다.

## 5. 판정

미결정 구현값이 닫혔으므로 generator와 dry run 구현은 `PASS`다. 본 실험은 여전히 금지한다.

