# v1.1.0 — 두 핵심 실험의 기존 결과 추가

이 버전은 **기존 결과의 보관 범위를 확장**한다. 새 실험·재학습·생성·parameter 조정을 수행하지 않았다. `v1.0.0` 태그, 릴리스 첨부파일, 최초 118개 고정 파일은 그대로 보존한다.

## 1. 운동 중단시간의 검열·실제 관측시간 보정

- 결과: `ai_prototype/artifacts/v23_survival_time_correction_20260929/`
- 실행 코드: `ai_prototype/run_v23_survival_time_correction.py`
- 고정 방법: `ai_prototype/SIMULATOR_V23_SURVIVAL_TIME_AMENDMENT_20260929.md`
- seed 110·220·330·440·550, k=0·1·3·5·10·20, pooled·하중행군·맨몸 순환운동, 시간구간 1·2.5·5·10분의 **360조건**.
- 구간별 지수위험모형에서 실제 노출시간과 계획시간의 우측 검열을 반영한 별도 방법론 보정이다. 이전 logistic-hazard 결과를 대체하거나 덮어쓰지 않는다.
- `runs.json`: seed별 집계 성능·선택 설정·모형 계수. `summary.json`: 평균·SD·95% 기술구간·짝지은 차이. `validation.json`, `unit_validation.json`, `feature_access_audit.json`: 당시 검증 기록. `data_hashes.json`: 생성자료 동일성 식별자.
- Brier·AUC·C-index·RMST 및 중단 사례만의 RMST 오차를 구분한다. 중단 사례 오차를 전체 인원의 운동 중단시간 정확도로 바꾸어 해석하지 않는다.

## 2. 개인 운동 이력 길이 비교 — 자기보고 특징 누락 교정본

- 결과: `ai_prototype/artifacts/rq1_longitudinal_v2_phase1_corrected/`
- 실행 코드: `ai_prototype/run_rq1_longitudinal_v2_phase1.py`
- 정보경로 감사: `ai_prototype/audit_rq1_longitudinal_v2_phase1_information_path.py`
- 고정 교정: `ai_prototype/RQ1_LONGITUDINAL_V2_ANALYSIS_AMENDMENT_02.md`
- seed 110·220·330·440·550, 120명/72·24·24 개인 분할, k=0·5·10·20·30·50·75·100, 5개 예측대상·5개 정보군. `summary.csv`에는 **200개 집계 행**이 있다.
- 부담 WEAK/STRONG에 빠졌던 과거 자기보고 특징을 동일하게 적용한 교정본이다. 생성기·모수·분할·평가 세션·모형 grid를 결과에 맞춰 변경한 실험이 아니다.
- `results.json`, `summary.csv`: 전체·seed별 지표, 95% 구간, k=0 대비 차이. `information_path_audit.json`: 보고 성향을 제외한 내부 상태에 대한 별도 집계. `REPORT.md`: 당시 해석과 제한.
- 전체 이력의 이득과 생체·활동 이력만의 이득을 구분한다. 자기보고 점수의 개선을 내부 생리 상태의 동일한 개선으로 간주하지 않는다.
- 이 보관 묶음은 **BASE 기록 건수 비교 교정본**이다. 변화사건 직후의 최근 5건 대 100건 우위를 검증한 별도 후속 분석이나 전 사전등록 계획의 완료 선언이 아니다. 후속 추가 실험 전체가 포함됐다고 해석하지 않는다.

## 보존·개인정보 처리

`reproducibility/supplement_v1.1.0.json`에 추가 원본의 SHA-256과 제외 파일 이름을 기록했다. 추가한 코드·설정·집계 결과는 원본 바이트 그대로다. 개별 예측값, 개인·세션 배정표, 원자료, 참가자별 보정값은 넣지 않았다. source의 `p05` 같은 표기는 백분위 기호이며 참가자 식별자가 아니다.

포함된 프로토콜·freeze 문서는 **작성 당시 기록**이다. ‘미실행’, ‘보류’ 등 당시 상태를 사후 편집하지 않았으며, 그 문구를 저장소 전체의 현재 실행 상태로 읽지 않는다. 다른 실험을 참조하는 코드 의존성과 고정 문서도 함께 보존하지만 그 실험의 모든 결과를 추가한 것은 아니다.

## 검증과 재현의 구분

저장소 루트에서 `python tools/verify_release.py`, `python tools/verify_supplement.py`, `python tools/test_release_tools.py`로 원자료 없는 무결성 검증을 수행할 수 있다. 이 검증은 연구 코드를 import하거나 학습을 실행하지 않는다.

전체 재실행에는 기존 제외 입력 외에도 원시 PMData/`participant-overview.xlsx`, private calibration, 과거 lock 입력과 이전 결과가 필요하다. 현재 집계 calibration만으로 빠진 원본을 재구성하지 말고, lock 검사를 우회하지 않는다. source 실행기는 원래 출력 경로에 쓰므로 원 연구의 별도 복사본에서 입력·경로를 확인한 뒤 실행해야 한다. 이 버전은 단독 재실행 환경을 보증하지 않는다.

`requirements.txt`는 최초 배포 당시 확인한 환경 기록이다. 새 코드에는 `openpyxl`도 필요하며, 당시 모든 실행환경을 입증한 추가 version pin은 만들지 않았다. 무결성 검증은 Python 표준 라이브러리만 사용한다.
