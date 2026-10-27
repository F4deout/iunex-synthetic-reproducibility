# 데이터와 제외 파일

## Git에 포함하지 않은 자료

- 원시 PMData: `ai_prototype/data/pmdata/`
- 참가자별 보정 자료: `ai_prototype/artifacts/simulator_v2_calibration_v1/calibration.json`
- 위 보정 묶음의 원 manifest
- 원시 예측행 전체·개별 로그·전체 vendor 설치본

PMData 제공기관 소개 주소는 기존 프로젝트 기록의 <https://datasets.simula.no/pmdata/>입니다. 기존 다운로드 기록은 <https://datasets.simula.no/downloads/pmdata.zip>을 참조합니다. 저장소 준비 시 소개 페이지 원격 열기는 timeout이었으므로 현재 다운로드 가용성을 성공 확인한 것으로 표시하지 않습니다. 자료의 이용 조건은 제공기관에서 확인하며 원자료를 이 저장소로 재배포하지 않습니다.

원 코드는 PMData의 `participant-overview.xlsx` 및 `pXX/fitbit/`, `pXX/pmsys/` 구조를 사용합니다. 원본 코드의 `model.DATA` 경로는 `ai_prototype/data/pmdata`입니다.

## 기존 연구자 로컬 입력 준비

연구자 원본 프로젝트에 이미 있는, 제외한 두 파일만 복사할 수 있습니다.

```sh
python tools/stage_local_inputs.py --source /absolute/path/to/original/ai_prototype
```

- 미리 기록된 SHA-256과 일치하는 파일만 복사합니다.
- 기존 목적지 파일은 다른 내용이면 덮어쓰지 않습니다.
- 복사되는 경로는 `.gitignore`로 제외됩니다.
- 원자료·별도 역사적 lock 산출물 전체를 자동 수집하는 도구는 아닙니다.

없는 보정값을 임의로 만들거나 군 장병의 모집단 값으로 간주하지 않습니다. `python tools/verify_release.py --check-inputs`는 추가 입력 준비 상태를 별도로 표시합니다.


## v1.1.0 추가 안내

v1.1.0에서도 원자료·개별 예측값·개인/세션 배정표를 제외합니다. 추가 입력 제한은 [v1.1.0 추가 자료 안내](SUPPLEMENT_v1.1.0.md)를 참조하세요.
