# Simulator v2.2-multi-activity parameter register — pre-generator

상태: **근거 분류 완료; 수치 미동결 항목 존재; generator STOP**  
작성일: 2026-09-28  
원칙: v2.1 값을 자동 승계하지 않으며, 원하는 history 효과나 성능을 만들기 위한 수치 선택을 금지한다.

| ID | 항목 | 단위 | 분류 | 현재 결정 | 구현 전 필요사항 | critical |
|---|---|---|---|---|---|---|
| C01 | 안정 HR 기준선 | bpm | EMPIRICAL_REFERENCE | 기존 PMData 소수 참여자의 분포는 참고 가능 | 군 장병·최종 스테이션 반복자료 필요 | 예 |
| C02 | 활동 전후·회복 HR의 개인 내 변동 | bpm | UNKNOWN/NEEDS_SOURCE | 미정 | 활동별 반복 측정 | 예 |
| C03 | SpO₂·체온·혈압·ECG 측정오차·결측·artifact | 각 장치 단위 | UNKNOWN/NEEDS_SOURCE | 미정 | 최종 부품과 reference 비교 | 예 |
| C04 | burden/fatigue/condition 보고 bias·occasion error | 0–10점 | UNKNOWN/NEEDS_SOURCE | 미정 | 동일 질문·시점의 반복 자기보고 | 예 |
| C05 | 공통 recovery 상태의 활동 간 전이 | 시간·무차원 | SIMULATION_ASSUMPTION 후보 | 미정 | 독립 LOW/BASE/HIGH와 단조식 사전등록 | 예 |
| R01 | 독립 3 km 수행기록 | 거리·분 | UNKNOWN/NEEDS_SOURCE | 현재 자료 없음 | 개인별 측정일·시간·완료여부 | 예 |
| R02 | 러닝 거리·속도·시간 | km·km/h·분 | EMPIRICAL_REFERENCE | PMData 지원범위 감사 가능 | 3 km 군 자료와 분리 보고 | 예 |
| R03 | CS/D′ 구조 | m/s·m | LITERATURE_CONSTRAINED | 강도–지속시간 구조만 사용 가능 | 실제 값으로 간주 금지 | 예 |
| R04 | RUN capacity/reserve 분포 | m/s·m | SIMULATION_ASSUMPTION 또는 UNKNOWN | v2.1 자동 승계 금지 | 3 km만으로 두 값을 동시 식별 금지 | 예 |
| M01 | 이동속도·수행시간·거리 | km/h·분·km | OBSERVED_SCHEMA | 직접 기록하도록 확정 | 실제 군장 행군 자료 필요 | 예 |
| M02 | 군장 무게·체중 | kg | LITERATURE_CONSTRAINED + NEEDS_SOURCE | 부담 방향은 문헌으로 제한 | 현재 대상자의 실측 분포 필요 | 예 |
| M03 | 경사·지형·환경 효과 | %·범주·환경단위 | LITERATURE_CONSTRAINED + NEEDS_SOURCE | 영향 방향만 제한 | 조건별 실측 또는 사전 sensitivity | 예 |
| M04 | 행군 외부부하→잠재 strain 함수 | 무차원 | SIMULATION_ASSUMPTION | 미정 | 단조·bounded 함수와 LOW/BASE/HIGH 잠금 | 예 |
| M05 | 행군 완료/중단 행동과 censoring | 분·범주 | UNKNOWN/NEEDS_SOURCE | 실제 중단만 관측 | 자발·안전·의학·행정 사유 자료 | 예 |
| B01 | 종목·순서 | 범주 | OBSERVED_SCHEMA | 직접 기록하도록 확정 | 표준화 protocol 필요 | 예 |
| B02 | 계획/실제 반복·세트 | 회·세트 | OBSERVED_SCHEMA | 직접 기록하도록 확정 | 실제 수행자료 필요 | 예 |
| B03 | 작업·휴식시간 | 초 | OBSERVED_SCHEMA | 직접 기록하도록 확정 | 실제 수행자료 필요 | 예 |
| B04 | 외부 중량·체중부하 표현 | kg·범주 | UNKNOWN/NEEDS_SOURCE | 맨몸과 외부중량을 구분 | 종목별 기록규칙 필요 | 예 |
| B05 | 순환식 부하→잠재 strain 함수 | 무차원 | SIMULATION_ASSUMPTION | 미정 | 종목을 임의 공통점수로 환산하지 않는 함수 필요 | 예 |
| B06 | 완료율·수정·중단 process | 비율·분·범주 | UNKNOWN/NEEDS_SOURCE | 실제 기록만 사용 | 반복 protocol과 중단사유 자료 | 예 |

## 사전 고정해야 할 민감도 family

수치 자료를 확보하지 못한 상태에서 합성 구현을 계속하려면 다음을 서로 독립적으로 LOW/BASE/HIGH에 등록한다.

1. `COMMON_RECOVERY_TRANSFER`: 앞선 활동이 다음 활동의 회복상태에 미치는 크기.
2. `MARCH_LOAD_COUPLING`: 군장 무게·속도·시간·경사와 잠재 strain의 결합.
3. `CIRCUIT_WORK_REST_COUPLING`: 실제 반복·작업시간·휴식시간과 잠재 strain의 결합.
4. `ACTIVITY_RESPONSE_HETEROGENEITY`: 같은 외부 조건에 대한 개인별 HR 반응 차이.
5. `REPORTING_RELIABILITY`: 활동별 자기보고 bias와 occasion error.

각 family는 별도 근거로 정하며, 개인 이력의 효과가 커지도록 coupling을 높이고 reporting noise를 낮추는 동시 조정을 금지한다.

## 현재 판정

- 입력 스키마 구현: `PASS`
- 자료 지원 감사: `PASS`, 단 RUN `PARTIAL`, LOADED_MARCH/BODYWEIGHT_CIRCUIT `STOP`
- parameter 숫자 동결: `STOP`
- generator 구현: `STOP`
- 본 실험: `STOP`

