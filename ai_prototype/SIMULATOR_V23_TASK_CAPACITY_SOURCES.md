# Simulator v2.3 task-capacity evidence register

확인일: 2026-09-28

| 자료 | 확인한 내용 | v2.3 사용 범위 | 사용 금지 |
|---|---|---|---|
| CDC, NHANES 1999–2004 Cardiovascular Fitness | 12–49세 대상 submaximal treadmill, 연속 HR 및 추정 VO₂max 변수와 추정상태 코드 | 중앙 분포를 공통 유산소 이질성의 경험적 참고로 사용 | 군 장병 또는 종목별 능력의 모집단 추정 |
| 현재 PMData participant overview | 유효 5 km 기록 15명, 18.78–47.47분 | 보유 자료에서 개인 수행기록 차이가 존재한다는 참고 | 5 km speed를 CS·행군·순환운동 capacity와 동일시 |
| Tsai et al., CHIEF Heart Study | 군 남성 1,388명에서 elite/non-elite 집단의 3 km와 push-up 수행 차이 | 군 집단 내부 수행능력 이질성의 방향적 근거 | 개인수준 원자료 또는 한국군 모집단 분포로 사용 |
| Pal et al. (2017) | 군인의 하중·속도·고도 조건에 따라 HR, VO₂, 상대 운동부하 및 RPE가 달라짐 | 행군 외부부하 변수와 상대부하 방향 제한 | 현재 합성 대상자의 정확한 계수로 대입 |
| TNO load-carriage study | 23명 전투원에서 절대하중보다 개인 최대 하중능력 대비 비율이 지속시간을 더 잘 설명 | 행군의 개인 capacity 상대화 필요성 | 공개되지 않은 개인 원자료를 추정하여 생성 |
| Jones et al. (2016) | critical power와 W′가 threshold 및 유한 예비량을 구분하는 구조 | capacity와 tolerance를 분리하는 일반 이론 | 행군·순환운동의 실제 CP/W′ 측정치로 표현 |
| Bergstrom et al. (2021) | 동적 저항운동에서 critical load와 L′의 적용 가능성 검토 | 순환운동에서도 capacity와 유한 수행량을 구분할 수 있다는 구조적 참고 | 현재 합성 circuit parameter의 실측 근거로 사용 |
| Agudo-Ortega et al. (2026) | 14분 circuit에서 work/rest 조건과 반복량·수행특성 및 급성 피로 관측 | work/rest와 실제 완료량을 기록해야 한다는 방향적 근거 | 해당 표본의 값을 군 장병 분포로 복사 |

## 확인 URL

- NHANES documentation: https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2003/DataFiles/CVX_C.htm
- NHANES examination files: https://wwwn.cdc.gov/nchs/nhanes/Search/DataPage.aspx?Component=Examination
- CHIEF Heart Study: https://www.frontiersin.org/journals/cardiovascular-medicine/articles/10.3389/fcvm.2021.725852/full
- Pal et al.: https://pmc.ncbi.nlm.nih.gov/articles/PMC5316174/
- TNO load carriage: https://repository.tno.nl/SingleDoc?find=UID+57df98b4-5464-43aa-877f-0ca61f4a97cd
- Jones et al.: https://pubmed.ncbi.nlm.nih.gov/27031742/
- Bergstrom et al.: https://pubmed.ncbi.nlm.nih.gov/33494200/
- Agudo-Ortega et al.: https://pubmed.ncbi.nlm.nih.gov/41710093/

## 자료 공백

공개된 개인수준 자료 중 동일 인원에게 행군의 속도·하중·경사·완료/중단과 구조화된 순환운동의 종목·반복·세트·work/rest·회복을 함께 기록한 군 자료는 확인하지 못했다. 따라서 종목별 capacity, tolerance, 회복 및 target coupling의 정확한 분포는 `SIMULATION_ASSUMPTION`으로 유지한다.

