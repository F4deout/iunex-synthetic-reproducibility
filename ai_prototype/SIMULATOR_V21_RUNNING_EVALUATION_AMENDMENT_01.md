# Simulator v2.1-running evaluation protocol amendment 01

상태: **평가 endpoint 재분류만 확정; 예측 모델 본 실험 미실행**  
작성일: 2026-09-21  
변경 사유: 잠긴 dataset dry run을 확인한 뒤 `E4` 완료 label 0/120, Naturalistic validation·ID-test의 임계 이상 사례 0건, slow-recovery HR 신호의 비식별성을 확인하였다. **결과 확인 후 작성한 amendment**이며, 관찰된 실패를 숨기거나 dataset grid·생성식·parameter·coupling·label noise·split을 조정한 것이 아니다. 원래 endpoint와 이번 변경을 함께 보존한다.

## 1. 유지하는 잠금과 결과

| 파일 | 동결 SHA-256 |
|---|---|
| `SIMULATOR_V21_RUNNING_PROTOCOL.md` | `4594babf1e5cef0fc69a2879d7bb5b0a374bfde4abefd1661f4de9fb87aba129` |
| `SIMULATOR_V21_RUNNING_PARAMETERS.md` | `be7eed3eae78a3a2e56fa3e07ee7101afa5780ba753b13bde0ba28f07bb99823` |
| `SIMULATOR_V21_RUNNING_PARAMETERS_AMENDMENT_01.md` | `1e135e799dd3b776838b78b26b160fdc43d380878287899b99d8fd345cf21540` |
| `SIMULATOR_V21_RUNNING_DATASET_PROTOCOL.md` | `21c95ca62f4bb98f0ef93671fa68d506d7aa6dd7983c856dfc70039a05574100` |
| `simulator_v21_running.py` | `d03b854edb53fa95955d440c58c71bf3e7a158c3104753841f073a20046cf586` |
| `build_v21_running_datasets.py` | `353505e9741f0ccf713c24389132e066733b052778bdb1097e626158f41c9f9b` |

동일 dry-run seed `20260921`의 `artifacts/synthetic_v21_running_dataset_dryrun/` 결과를 그대로 평가 표본으로 사용한다. `validation.json` SHA-256은 `eae80ef7fcc45a25c108edd4920de8a0a2f5fdcf52c9f0f72c099c5ff108a2cb`, `controlled.json`은 `3f23224fb818352ec0db76071a8b2a07ffe5b43c344ac346254fcf280909a953`, `naturalistic.json`은 `558ef66b802996f7792e4a970d1b994d204419b53c418d649f45a64c848920cd`이다. `template_manifest.json`과 `subject_manifest.json`도 재배정하지 않는다. 기존 결과 파일을 덮어쓰지 않는다.

## 2. Controlled prediction endpoint: E1–E3

`E1=(0.70, 6분)`, `E2=(0.90, 12분)`, `E3=(1.05, 3분)`을 **완료된 session의 burden·fatigue·condition 0–10 점수 예측** endpoint로 유지한다. Burden은 기존 artifact의 `WEAK`/`BASE`/`STRONG` 세 coupling label을 **각각** 평가하며 하나의 `burden` 저장 키로 가정하지 않는다. 각 cell의 완료 건수와 누락/검열 건수를 항상 병기한다. 현 dry run에서는 각 cell 120/120 완료다. 각 `k=0/1/3/5/10/20`은 같은 E1–E3 subject/session에 대해 비교하며, 현재·미래 E 관측/label을 history에 넣지 않는다. train/validation/ID-test subject 및 source-template 분할, validation에서만 선택하고 ID-test는 최종 평가에만 사용하는 원칙은 잠긴 protocol대로 유지한다. 점수 예측 결과는 **합성 완료 구간**에만 적용한다.

## 3. Controlled tolerance/censoring endpoint: E4

`E4=(1.10, 12분)`의 속도·계획시간·event 순서·분할을 **그대로 유지**한다. 현 dry run에서 완료 0/120이므로 `WEAK`/`BASE`/`STRONG` burden·fatigue·condition 0–10 예측의 train/validation/test 정답과 MAE/RMSE/R² 분모에서 E4를 제외한다. 검열을 10점 또는 다른 임의 점수로 치환하지 않는다. E4를 `time-to-limit / censoring / tolerance` **감사 전용 endpoint**로 분류한다.

본 실험 전부터 다음 요약을 고정한다: fold별·전체 `planned_minutes`, `actual_minutes=time_to_limit`(검열 시), `time_to_limit`의 n/평균/SD/5·50·95% 분위수, `time_to_limit / planned_minutes`, 완료/검열 수와 비율. E4의 개인별 `CS_like`, `D′_like`와 `time_to_limit`의 Pearson 및 Spearman 상관을 **latent-audit-only**로 보고하며, `D′_like/CS_like`와의 관계도 확인한다. 상관을 계산할 때 실제 중단시간이 관측된 검열 session만 사용하고 표본 수를 명시한다. 모든 사람이 검열되면 완료 여부는 상수이므로 binary discrimination/AUC를 계산하지 않는다. `time_to_limit`는 잠긴 `q` 식과, 잠재 CS를 이용한 `v=1.10×CS_like` 배정의 결과다. 따라서 이 상관·역산은 **생성기 내부의 구조적 확인**이며 독립적인 임상/군 임무수행 타당성 증거가 아니다. 평가 모델에 latent CS/D′를 입력하거나 결과를 이용해 E4 grid를 바꾸지 않는다.

## 4. Slow-recovery endpoint의 해석 한계

S1–S3의 `6/24/72시간` gap, 선행·probe bout, 순서와 원본 결과를 유지한다. 현재 session-average HR만으로 개인 `tau_slow`를 복원하는 목표는 `NOT_IDENTIFIABLE`이라는 **관찰 결과로 보존**한다. dry run의 6시간 대 72시간 평균 참 HR 차이 절댓값은 약 0.40 bpm, 관측 차이의 noise SD는 약 7.90 bpm이다. 이번 본 실험의 성공 endpoint에 slow-recovery 추정 성능을 넣지 않는다. slow debt 효과·HR noise는 조정하지 않는다. 향후 독립적인 fatigue/condition 반복 관측이나 다른 회복 측정을 갖춘 별도 자료·평가 설계가 필요한 연구과제로만 기술한다. 현재 합성 fatigue/condition label을 추가 실측 자료처럼 취급하지 않는다.

## 5. Naturalistic support limitation

잠긴 `source_template_id` 기준 38/13/13 원본 workout group split과 합성 subject 72/24/24 split을 그대로 유지한다. 현 dry run의 임계 이상 건수는 train 48, validation 0, ID-test 0이며 train의 48건도 모두 시뮬레이터 검열이다. 따라서 `NATURALISTIC`에서는 CS/D′·임계 이상 tolerance의 validation/ID-test 일반화 성능을 계산하거나 주장하지 않는다. 이를 `SUPPORT_LIMITATION`으로 표기한다. 완료된 지원 범위 내 0–10 점수 예측을 시행하더라도 **아래 임계 속도에 집중된 PMData-like 합성 구간**에 한정하여 해석한다. 원본 제공자 7명의 일부가 분할 간 공유되는 제한도 그대로 보고한다. split을 결과에 맞춰 재배정하거나 supra-threshold 세션을 추가하지 않는다.

## 6. 현재 개인 parameter 식별성 결과와 본 실험 범위

잠긴 dry-run 결과를 다음과 같이 보존한다: `CS-like IDENTIFIABLE`, `D′-like IDENTIFIABLE`, `HR response PARTIAL`, `fast recovery IDENTIFIABLE`, `slow recovery NOT_IDENTIFIABLE`. 앞의 `IDENTIFIABLE`은 잠긴 합성 generator가 제공한 정확한 중단시간과 workload 조건에서의 **구조적 역산 가능성**을 뜻한다. 실제 장병·측정 장치에서의 식별성이나 모든 downstream target의 예측 가능성을 뜻하지 않는다. HR response의 부분 식별과 느린 회복 비식별은 본 실험 결과 해석의 명시적 제한이다.

## 7. 평가 가능성 validation과 실행 경계

본 실험 전에 파일 hash, 38/13/13 source-template 교집합 0, 72/24/24 합성 subject 교집합 0, Controlled 원본 template 사용 0, 20 calibration+4 evaluation event, E1–E3 완료 label 존재, E4 완료 label 0 및 정확한 중단시간 존재, S-grid 유지, Naturalistic validation/test supra-threshold 0, history에 현재/미래 E 정보 없음, 모든 k에서 같은 evaluation session을 검사한다. 이 검사는 **기존 파일의 읽기 전용 검증**이며 target MAE나 모델 선택은 실행하지 않는다.

이 amendment의 범위에 맞춘 본 실험 진행 기준은 위 assertion 모두 PASS인 경우 `EXPERIMENT_READY`다. E4의 0–10 target이나 slow recovery/Naturalistic supra-threshold 일반화를 본 실험의 성과처럼 제시할 수 있다는 뜻은 아니다. 이후 평가 endpoint 변경은 이 문서를 덮어쓰지 않고 별도 amendment와 결과 열람 사실을 남긴다.
