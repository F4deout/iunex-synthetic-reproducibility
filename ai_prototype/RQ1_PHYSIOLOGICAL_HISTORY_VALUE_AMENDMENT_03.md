# RQ1 생리·수행 이력 연구 사전등록 Amendment 03

작성일: 2026-10-08  
작성시점: Phase 1 결과 동결 후, 사전등록된 history destruction·민감도 결과 확인 전

## 1. 변경 사유

원 프로토콜은 `history subject identity destruction`, `history time-order destruction` 및 LOW·BASE·HIGH 민감도 분석을 사전등록했으나, 파괴시험에서 이력을 섞는 정확한 단위와 동결 generator의 민감도 수준을 보고하는 방식을 명시하지 않았다. Phase 1 결과와 생성식·parameter·feature를 변경하지 않고 후속 반증시험의 실행 규칙만 고정한다.

## 2. 분석범위

- 자료구조: NATURALISTIC, CONTROLLED_CHANGE
- 최종 시드: 110, 220, 330, 440, 550
- 주 이력 길이: k=20
- 기준 비교: C1 현재정보, C5 전체 객관적 이력
- 연속 target, 완료 여부, 관측 중단시간 Ridge 및 log-normal AFT를 동일 방식으로 평가
- Phase 1의 train·validation·test 분할, train-only 전처리 및 validation-only model selection 유지

## 3. 이력 대상 파괴

- C5에서 계산된 과거 이력 feature 전체를 같은 fold와 같은 evaluation session index에 속한 다른 대상자의 이력 feature로 치환
- 현재 관측값, 현재 운동조건, target 및 평가 session identity는 원 대상자 값 유지
- 대상자 정렬 후 seed·dataset·fold·session index로 결정한 1 이상 순환 이동을 사용하여 자기 이력이 다시 배정되는 경우 0건 보장
- train·validation·test 경계를 넘는 이력 교환 금지
- 목적: 이력의 주변분포와 결측 양상은 유지하면서 대상자 일치정보만 제거

## 4. 이력 시간순서 파괴

- 각 평가 session보다 엄격히 이전인 동일 대상자 기록만 후보로 사용
- seed·dataset·subject·current session으로 결정한 재현 가능한 순열을 생성하고 그중 k=20건을 선택
- 현재·미래 기록 사용 금지
- 선택한 기록으로 C5의 센서반응·수행·회복 이력 feature를 다시 계산
- 목적: 대상자 고유정보는 유지하면서 최근 기록이라는 시간순서·근접성 정보를 제거

## 5. 파괴시험 판정

- 정상 C5 개선량: C1 오차 − 정상 C5 오차
- 파괴 후 개선량: C1 오차 − 파괴조건 오차
- 개선 소실률: `(정상 C5 개선량 − 파괴 후 개선량) / 정상 C5 개선량`
- 정상 개선량이 0 이하인 target에는 소실률을 적용하지 않고 방향만 보고
- `PHYSIOLOGICAL_HISTORY_VALUE`의 반증조건은 identity 또는 time-order destruction에서 개선의 50% 이상 소실
- 모든 target과 5개 seed 결과를 선택 없이 보고

## 6. 민감도 분석

- 동결 generator가 정의한 LOW와 HIGH를 BASE와 함께 평가
- 각 수준은 수행능력 변화, 관측간격, 생리반응 이질성, 센서오차·결측, 회복 이질성 및 보조 자기보고 오차가 함께 변하는 공동 시나리오
- 개별 parameter family의 독립 인과효과로 해석하지 않음
- C1과 C5, k=20을 각 자료구조와 5개 seed에서 평가
- BASE는 동결 Phase 1 결과를 재사용하고 LOW·HIGH만 신규 생성
- LOW·BASE·HIGH 중 유리한 수준을 주 결과로 교체하지 않음

## 7. 변경하지 않는 항목

- simulator 생성식·동결 parameter·자료분할·target·history feature 정의
- Phase 1 결과와 raw prediction
- Ridge·logistic·AFT 후보와 평가방법
- 성공·제한 판정기준

