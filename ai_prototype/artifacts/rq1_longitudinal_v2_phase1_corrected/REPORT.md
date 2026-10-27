# RQ1 longitudinal v2 Phase 1 — BASE 기록 수 실험

## 범위

- final seed: 110, 220, 330, 440, 550
- 합성인원: seed당 120명, subject-level 72/24/24 분할
- 이력 길이: k=0, 5, 10, 20, 30, 50, 75, 100
- 동일한 마지막 30개 session을 모든 k에서 평가
- Ridge alpha는 validation에서만 선택하고 전처리는 train에서만 적합
- generator·parameter 변경 없음

## 전체 이력모형 MAE

| Target | k=0 | k=5 | k=10 | k=20 | k=30 | k=50 | k=75 | k=100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Burden WEAK | 0.674 | 0.465 | 0.445 | 0.433 | 0.432 | 0.430 | 0.431 | 0.434 |
| Burden BASE | 0.646 | 0.396 | 0.377 | 0.371 | 0.372 | 0.372 | 0.378 | 0.380 |
| Burden STRONG | 0.608 | 0.390 | 0.371 | 0.367 | 0.365 | 0.366 | 0.368 | 0.373 |
| Fatigue | 0.612 | 0.347 | 0.335 | 0.329 | 0.329 | 0.332 | 0.333 | 0.338 |
| Condition | 0.614 | 0.349 | 0.338 | 0.336 | 0.336 | 0.338 | 0.342 | 0.345 |

모든 target에서 큰 변화는 k=0→5에서 발생했고 k=10~20 이후에는 포화되었다. 사전등록 판정은 모두 `PLATEAU`였다.

## k=20 핵심 비교

| Target | 현재 입력 k=0 | 생체·활동 이력 | 과거 자기보고 | 전체 이력 | 단순 과거평균 | k0−전체 (95% CI) |
|---|---:|---:|---:|---:|---:|---:|
| Burden WEAK | 0.674 | 0.687 | 0.432 | 0.433 | 0.435 | 0.241 [0.226, 0.256] |
| Burden BASE | 0.646 | 0.675 | 0.374 | 0.371 | 0.395 | 0.275 [0.160, 0.390] |
| Burden STRONG | 0.608 | 0.631 | 0.371 | 0.367 | 0.410 | 0.241 [0.166, 0.316] |
| Fatigue | 0.612 | 0.639 | 0.331 | 0.329 | 0.435 | 0.283 [0.186, 0.380] |
| Condition | 0.614 | 0.656 | 0.342 | 0.336 | 0.463 | 0.278 [0.173, 0.384] |

- 전체 이력은 모든 target에서 5/5 seed에서 k=0보다 낮은 MAE를 보였다.
- 생체·활동 이력만 사용한 모형은 k=0보다 개선되지 않았다.
- 과거 자기보고만 사용한 모형은 전체 이력과 거의 같은 성능을 보였다.
- Burden WEAK에서는 전체 이력이 단순 과거평균을 사실상 넘지 못했다. 다른 target에서는 전체 이력이 단순 과거평균보다 낮은 MAE를 보였다.

## 정보경로 감사

Reporting process를 제외한 noiseless subjective state의 k=20 결과는 다음과 같다.

| Target | k=0 current MAE | k=20 full MAE | k0−full (95% CI) | 개선 seed |
|---|---:|---:|---:|---:|
| Burden WEAK | 0.305 | 0.307 | -0.002 [-0.006, 0.002] | 1/5 |
| Burden BASE | 0.209 | 0.211 | -0.001 [-0.006, 0.003] | 1/5 |
| Burden STRONG | 0.217 | 0.218 | -0.001 [-0.006, 0.003] | 2/5 |
| Fatigue | 0.161 | 0.152 | 0.009 [0.006, 0.011] | 5/5 |
| Condition | 0.169 | 0.162 | 0.007 [0.004, 0.010] | 5/5 |

운동부담 세 조건의 관측점수 개선은 reporting-style recovery로 설명되며 noiseless state 개선은 확인되지 않았다. 피로와 현재상태에서는 작은 noiseless-state 신호가 남았지만 관측점수에서 나타난 약 0.28점 개선보다 훨씬 작았다.

## 판정

- Burden WEAK/BASE/STRONG: `REPORTING_STYLE_RECOVERY_ONLY`
- Fatigue/Condition: `REPORTING_STYLE_DOMINANT_WITH_WEAK_STATE_SIGNAL`
- 기록 수 패턴: `PLATEAU`
- BASE 기록 수 실험: 완료
- 전체 사전등록 결론: 아직 보류

아직 수행하지 않은 사전등록 항목은 30/90일·EWMA 최신성 비교, 변화사건 구간별 평가, reporting-process LOW/HIGH 민감도 및 history time-order destruction이다. 따라서 현 단계 결과만으로 `EVIDENCE_OF_ADDITIONAL_HISTORY_VALUE`를 최종 선언하지 않는다.

## 구현 교정 기록

최초 실행코드는 Burden WEAK/STRONG의 과거 자기보고 특징을 생성하지 않았다. 이 실행은 `rq1_longitudinal_v2_phase1_superseded_missing_burden_history`에 보존하였다. Amendment 02에 따라 모든 target에 동일한 mean/last history schema를 적용한 뒤 전체 실험을 처음부터 다시 수행하였다.

