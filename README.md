# IUNEX Synthetic Research Reproducibility Materials

군 생체정보·개인 운동 이력 분석 논문의 **고정 코드, 생성 설정, 집계 결과와 재현 안내**를 정리한 저장소입니다.

현재 배포 묶음 버전은 **v1.1.0**입니다. 최초 **v1.0.0**은 그대로 보존합니다. 이 버전 번호는 저장소 스냅샷의 버전이며 기존 simulator 버전을 바꾸지 않습니다. 최초 저장소는 **비공개**로 생성했습니다.

## 바로 확인하기

Python 3.12에서 저장소 루트 기준으로 실행합니다. 아래 검증에는 추가 패키지·네트워크·원자료가 필요 없습니다.

```sh
python tools/verify_release.py
```

검증은 고정 파일 SHA-256, Python 문법, JSON 읽기, 일부 논문 수치, 제외 대상 파일을 확인합니다. **학습·생성·추론·parameter tuning은 실행하지 않습니다.**

## 논문과 파일의 연결

| 분석 | 설정 | 기존 코드 | 저장 결과 |
|---|---|---|---|
| RQ1 활동 전 상태·예정 운동 | `ai_prototype/PRETASK_MODEL_PARAMETERS.json` | `ai_prototype/simulator_pretask_model.py`, `run_scale_stability.py` | `artifacts/scale_stability_20261006/summary.json` |
| 원 RQ2 고강도 중단시간 | `SIMULATOR_V21_RUNNING_PARAMETERS*.md` | `simulator_v21_running.py`, `run_v21_tolerance_prediction.py` | scale stability 및 기존 tolerance 관련 요약 |
| 자기보고 제외 C1~C7 | `RQ1_PHYSIOLOGICAL_HISTORY_VALUE_PARAMETERS.json` | `simulator_rq1_physiological_history_value.py`, `run_rq1_physiological_history_value_phase1.py` | `artifacts/rq1_physiological_history_value_phase1/summary.csv` |
| 별도 당일 상태 | `E4_DAILY_STATE_PARAMETERS_20261026.json` | `simulator_e4_daily_state_20261026.py`, `run_e4_daily_state_20261026.py` | `artifacts/e4_daily_state_20261026/` |
| 별도 이상신호 관측 | `REDFLAG_SENSOR_PROTOCOL_20261026.json` | `run_redflag_sensor_experiment_20261026.py` | `artifacts/redflag_sensor_experiment_20261026/` |
| 개인평균·최근값 등 기준 | `REVIEW_SIMPLE_BASELINES_PROTOCOL_20261026.json` | `run_review_simple_baselines_20261026.py` | `artifacts/review_simple_baselines_20261026/` |
| 심박수 단독/세 신호 점수 | `REVIEW_SENSOR_ABLATION_PROTOCOL_20261026.json` | `run_review_sensor_ablation_20261026.py` | `artifacts/review_sensor_ablation_20261026/` |

별도 경로가 생략된 파일은 `ai_prototype/` 아래에 있습니다. 상세 목록은 [재현 절차](docs/REPRODUCING.md)와 [데이터 준비](docs/DATA.md)를 확인하세요.

## v1.1.0 추가 결과

- 운동 중단시간의 실제 노출시간·검열 보정: `ai_prototype/artifacts/v23_survival_time_correction_20260929/`
- 개인 운동 이력 길이 비교의 자기보고 특징 누락 교정본: `ai_prototype/artifacts/rq1_longitudinal_v2_phase1_corrected/`

두 실험의 원본 코드·고정 설정·집계 결과만 추가했습니다. 개별 예측값과 개인·세션 배정표는 제외했습니다. 기존 결과·v1.0.0은 변경하지 않았습니다. 범위·당시 해석·재실행 제한은 [추가 자료 안내](docs/SUPPLEMENT_v1.1.0.md)를 참조하세요. 새로 추가한 자료는 `python tools/verify_supplement.py`로 검증합니다.

## 포함 범위

- 이전에 고정한 생성기·학습/평가 소스·프로토콜·모수·해시 파일을 **바이트 그대로 보존**했습니다.
- 기존 집계 결과를 복사했으며 저장소를 만들면서 새 실험을 실행하지 않았습니다.
- 원 논문, 심사평, 발표자료, 녹음, 인증정보, 원시 PMData 및 참가자별 보정 자료는 포함하지 않았습니다.
- PMData에서 유도한 일부 집단 수준 보정 통계는 실증 모집단 추정이 아닌 기존 reference로 수록했습니다.
- `reproducibility/frozen_files.json`은 이 배포에 포함한 원본 파일의 해시를 기록합니다. 이전 protocol/lock 파일은 당시의 기록이며 최신 저장소 전체의 상태 선언은 아닙니다.

## 실행 범위의 구분

1. **저장 자료의 독립 검증:** 위 `verify_release.py`로 바로 가능합니다.
2. **전체 실험 재실행:** 원시 PMData, 제외한 보정 파일, 일부 과거 잠금 산출물·원 예측행 및 일치하는 실행환경이 필요합니다. 이 저장소만 내려받아 모든 실험이 한 번에 재실행된다고 주장하지 않습니다.

고정 스크립트는 기존 결과 경로에 쓰거나 이미 존재하는 출력 때문에 중단할 수 있습니다. 추적 중인 원본 결과를 덮어쓰지 않도록 [재실행 안내](docs/REPRODUCING.md)를 먼저 읽으세요.

## 버전과 인용

논문에는 저장소 주소와 **사용한 `v1.0.0` 또는 `v1.1.0` 태그와 해당 commit SHA**를 함께 명시합니다. [인용 안내](docs/CITATION.md)를 참고하세요.

배포 라이선스는 현재 지정하지 않았습니다. 공개 전환은 별도 결정 사항이며, 이 스냅샷은 공개 저장소라고 논문에 기재하지 않습니다.
