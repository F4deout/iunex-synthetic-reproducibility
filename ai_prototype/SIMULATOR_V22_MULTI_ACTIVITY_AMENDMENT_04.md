# v2.2-multi-activity Amendment 04 — 합성 행군 기록의 체중 표시값

작성일: 2026-09-28  
결과 열람 상태: **v2.2 데이터·예측 결과 미생성·미열람**  
변경 이유: 입력 스키마와 generator 출력 연결 점검에서 군장/체중 비율을 kg 단위 관측필드로 변환할 표시용 체중값이 필요함을 확인함.

합성 행군 기록의 표시용 체중을 **75 kg 고정**으로 둔다. 군장 무게는 protocol의 군장/체중 비율에 75 kg을 곱해 기록한다. demand 식은 비율만 사용하므로 이 값은 target·HR·중단·성능에 영향을 주지 않는다. 75 kg은 실제 장병 평균 또는 모집단 추정치가 아닌 `SIMULATION_ASSUMPTION`이다.

순환식 station은 시간기반으로만 생성한다. 실제 반복수를 뒷받침하는 자료가 없으므로 `planned_reps=actual_reps=0`으로 기록하고 반복수 endpoint로 사용하지 않는다.

generator 구현 `PASS`를 유지한다.

