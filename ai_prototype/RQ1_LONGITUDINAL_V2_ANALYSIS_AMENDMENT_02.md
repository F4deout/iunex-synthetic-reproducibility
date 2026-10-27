# RQ1 longitudinal v2 analysis amendment 02

## 발견 사항

Phase 1 최초 실행 전용 코드에서 simulator의 기존 history helper가 `burden_BASE`, `fatigue`, `condition`의 과거 자기보고만 요약하였다. 사전등록된 예측대상에는 `burden_WEAK`과 `burden_STRONG`도 포함되므로, 두 조건의 self-report/full-history model에는 과거 자기보고 특징이 존재하지 않았다.

## 교정

- 모든 등록 target에 동일한 과거 자기보고 `mean`과 `last` 특징을 생성한다.
- 현재 세션보다 앞선 최근 k개 관측만 사용한다.
- generator 수식, parameter, target 값, subject split, 평가 session, 모델 및 alpha grid는 변경하지 않는다.
- 불완전 최초 실행 artifact는 `rq1_longitudinal_v2_phase1_superseded_missing_burden_history`로 보존한다.

이 변경은 결과에 따른 성능조정이 아니라 사전등록된 정보군 비교를 모든 target에 동일하게 적용하기 위한 구현 교정이다.
