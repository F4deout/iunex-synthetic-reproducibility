# PRETASK 초기 사용자·입력 스트레스 시험

- 동결 생성기·모형 parameter 유지
- seed 110·220·330·440·550 유지
- 이력 길이 0·1·3·5·10·20회별 독립 재학습
- 모든 이력 길이에서 동일한 평가 세션 사용
- 연속 target은 MAE, 완료 여부는 Brier score 사용
- 위험 측정값은 점수보다 `SAFETY_HOLD` 우선
- 전체 생체정보 누락은 `ABSTAIN_MISSING`
- 일부 누락은 학습 시 정한 결측 대체 후 출력하되 결측 사실 유지
- 학습자료의 관측 범위를 벗어난 현재·과업 입력은 `ABSTAIN_OUT_OF_DISTRIBUTION`
- 품질값은 0–1 범위를 벗어나면 입력 오류로 보류하고, 범위 안의 낮은 품질은 별도 성능 층화 대상으로 유지
- 결과에 따른 생성기·parameter·history feature 조정 금지
