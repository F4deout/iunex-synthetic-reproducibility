# RQ1 longitudinal v2 global sensitivity amendment 04

## 해석 단위

동결 generator의 `LOW`, `BASE`, `HIGH` 인수는 관측간격, 개인차, 수행능력 변화, 회복, 생리반응, 부채 및 보고과정의 여러 가정을 함께 변경한다. 따라서 LOW/HIGH는 각 parameter family의 독립 효과를 추정하는 조건이 아니라 사전고정된 통합 민감도 시나리오이다.

## 실행 범위

- final seed 110, 220, 330, 440, 550
- history k=0, 5, 10, 20, 30, 50, 75, 100
- Burden WEAK/BASE/STRONG, Fatigue, Condition
- current, sensor-context, self-report, full-history Ridge
- 관측 자기보고와 audit-only noiseless subjective state 분리
- 각 시나리오 내부에서 k=0 대비 history 효과 평가

## 제한

- LOW와 HIGH의 차이를 특정 parameter의 인과효과로 해석하지 않음
- BASE 결과에 맞춰 parameter를 변경하지 않음
- 기존 BASE 결과와 generator·parameter hash를 변경하지 않음
- 보고과정만의 효과는 별도 shadow sensitivity 결과를 사용함

