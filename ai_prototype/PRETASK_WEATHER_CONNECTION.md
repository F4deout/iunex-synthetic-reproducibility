# 활동 전 분석 화면의 날씨·환경 분석 연결

2026-10-14. 기존 PRETASK 예측 모형을 유지하고 환경 분석만 연결함.

- `start_pretask_dashboard.ps1` 또는 `python app.py --path /pretask-dashboard --open`으로 실행.
- 측정 지역 선택 시 기온·습도·풍속을 조회하고, 기존 저장 온열 모형으로 온열 감각·쾌적함을 자동 추정.
- 기온·습도는 환경 AI에 사용하고 풍속은 참고값으로 표시. 기존 컨디션·피로·운동 결과 예측의 입력과 점수는 바뀌지 않음.
- 10분마다 갱신. 실패·결측·오래된 기상자료에서는 환경 추정을 생략하고 기존 활동 전 분석을 계속 제공.
- 분석 시점의 지역·날씨·환경 결과를 원본 응답의 `environment`에 사본으로 포함. `affects_pretask_scores=false`로 구분.
- 환경 추정은 지역 기상값을 이용한 실외 온열 감각·쾌적함 추정이며, 개인 피로 점수나 운동 부담 점수로 합산하지 않음.

모형·시뮬레이터 재학습이나 parameter 변경 없음. 기존 학습/실험 artifact 보존.

검증: `python -m unittest test_weather test_thermal_state test_pretask_weather`.
