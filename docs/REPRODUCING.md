# 재현 절차와 실행 상태

## 1. 배포 파일 확인

```sh
python tools/verify_release.py
python tools/verify_release.py --check-inputs
```

첫 명령은 저장된 원본의 해시·문법·일부 집계 수치 확인입니다. 두 번째는 원자료와 제외 입력의 준비 상태를 함께 확인하며, 입력이 없으면 종료코드 2로 중단합니다. 학습은 실행하지 않습니다.

## 2. 수치 계산 환경 준비

Python 3.12 환경에서 다음을 사용합니다.

```sh
python -m venv .venv
# Windows PowerShell: .venv/Scripts/Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

requirements는 준비 시 확인한 로컬 수치 환경의 버전입니다. 역사적 모든 실험의 환경이 같았다는 증명은 아닙니다. 라이브러리·BLAS·운영체제가 달라지면 부동소수 오차가 생길 수 있으므로 원 결과를 변경해 맞추지 말고 차이를 보고합니다. 동봉된 `ai_prototype/vendor` 디렉터리는 없습니다.

## 3. 기존 실행기의 순서

아래는 원 실행기와 의존 관계 안내이며, 이 배포를 만들면서 실행하지 않았습니다.

| 경로 | 원 실행기 | 추가 전제 |
|---|---|---|
| PRETASK 초기 비교 | `run_pretask_model.py` | 고정 protocol/config/lock |
| 120/240/480명·30회 | `run_scale_stability.py` | 원 RQ2 입력 및 과거 lock 결과 |
| 후속 C1~C7 | `run_rq1_physiological_history_value_phase1.py` | 집계 cadence calibration, 사전등록/수정 lock |
| 단순 기준 비교 | `run_review_simple_baselines_20261026.py` | 기존 규모/후속 원 결과와 관련 lock |
| 당일 상태 | `run_e4_daily_state_20261026.py` | PMData, 원 RQ2, 제외 calibration, 과거 lock |
| 센서 점수 비교 | `run_review_sensor_ablation_20261026.py` | 기존 PRETASK·당일상태 결과 |
| 이상신호 비교 | `run_redflag_sensor_experiment_20261026.py` | 기존 분할·고정 보존 파일 목록 등 |

실행기는 `ai_prototype/`를 기준으로 경로를 찾습니다. 예시 명령의 형태는 `python ai_prototype/run_....py`입니다.

일부 원 실행기는 동결 당시의 전체 프로젝트 보존 목록까지 검사합니다. 이 공개 후보 subset에는 그 모든 과거 파일·원 예측행이 없습니다. `--check-inputs` 통과는 모든 역사적 lock의 완비나 재실행 성공을 보증하지 않습니다. 파일이 없거나 hash가 다르면 정지한 이유를 확인하며 원 protocol·잠금·parameter를 수정하거나 검사 코드를 우회하지 않습니다.

## 4. 결과 덮어쓰기 방지

저장된 집계 결과는 이 배포의 증거 자료입니다. 원 실행기 중 `run_pretask_model.py`처럼 기존 경로에 쓰는 것도 있습니다. 전체 재실행은 원 연구 프로젝트의 별도 복사본 또는 새로운 작업 경로에서 수행하고 원 코드·설정·원 결과를 보존하세요. 새로운 결과를 원래 결과 파일에 합치지 않습니다.

## 이번 배포에서 수행한 검증

원본 hash, Python syntax compilation, JSON parsing, 문서/데이터 제외 확인, 일부 논문 수치 대조를 수행합니다. 대규모 실험, 재학습, parameter 조정, 실제 장병/장비 검증은 하지 않습니다.
