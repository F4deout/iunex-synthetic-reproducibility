# RQ1 longitudinal v2 change-segment amendment 03

## 목적

동결 generator의 audit record에는 수행능력 변화사건의 발생 여부가 저장되지 않아 사전등록된 변화구간 평가를 직접 수행할 수 없었다. 생성식과 난수 호출을 변경하지 않는 감사 전용 trace를 만들어 사건 flag만 기록한다.

## 동일성 조건

- 원본 generator와 trace generator의 observed rows는 직렬화 SHA-256이 완전히 같아야 한다.
- audit record에서 새 `capacity_event_occurred` 필드를 제외한 모든 값도 완전히 같아야 한다.
- 동일성 검사가 실패하면 구간 평가는 중단한다.

## 구간 정의

결과를 보기 전에 평가 session을 다음과 같이 고정 분류한다.

1. `NO_EVENT_SUBJECT`: 전체 130개 session 동안 수행능력 변화사건이 한 번도 없는 대상자
2. `PRE_EVENT`: 최근 사건 후 10회가 지난 안정상태에서 다음 사건까지 1~3 session인 관측
3. `IMMEDIATE_POST`: 변화사건이 발생한 session과 이후 2개 session
4. `RESTABILIZED`: 가장 최근 변화사건 이후 3~10개 session이며 그 사이 추가 사건이 없는 관측
5. `OTHER_STABLE`: 위 조건 이외의 관측

구간 label은 audit에만 사용하며 predictor 입력으로 제공하지 않는다. `PRE_EVENT` 정의에는 감사용 미래 사건 위치를 사용하지만 모델 입력에는 사용하지 않는다.

## 평가

- 동일한 final seed 5개와 ID-test session 사용
- k=0 current, k=20 self-report, k=20 full 비교
- 관측 자기보고와 audit-only noiseless state를 별도로 평가
- 구간별 표본 수, MAE 및 `k0−k20` 방향 보고
- 소표본 구간은 결과를 합치거나 확대해석하지 않고 support limitation으로 표시

