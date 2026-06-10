# Data Dictionary

이 폴더의 공개 데이터는 사이트 본문 수치를 재현하기 위한 최소 집계 파일이다.

## `equal_pair_counts.csv`

각 선거 데이터셋에서 주요 두 후보의 득표수가 동시에 같은 pair 수를 비교 범위별로 센 결과다.

- `dataset`: 선거 종류, 회차 또는 연도, 투표 구분
- `stem`: 같은 시도·구시군 안에서 읍면동명 숫자 표현을 제거했을 때 같은 이름이 되는 분할동 기준 pair 중 동일득표 pair 수. 사이트 화면에서는 `분할동`으로 표시한다.
- `같은 구시군`: 같은 시도·구시군 안의 pair 중 동일득표 pair 수
- `광역권(시도)`: 같은 시도 안의 pair 중 동일득표 pair 수
- `광주+전남 통합`: 광주와 전남을 하나의 권역으로 묶은 기준의 동일득표 pair 수. 사이트 화면에서는 이 기준을 `광역권`으로 표시한다.
- `전국 전체`: 전국 모든 pair 중 strict 기준 동일득표 pair 수
- `전국_loose(한정당0포함)`: 한쪽 주요 정당 득표가 0인 경우까지 포함한 참고 집계

Strict 기준은 민주계열 후보 득표수와 보수계열 후보 득표수가 모두 0보다 큰 행만 대상으로 한다.

## `pair_counts.csv`

각 데이터셋에서 비교 가능한 pair의 총수를 범위별로 센 결과다. 동일득표 pair 수의 분모로 사용한다.

- `dataset`: 선거 종류, 회차 또는 연도, 투표 구분
- `rows`: 해당 데이터셋의 분석 행 수
- `stem(구시군+읍면동stem)`: 분할동 기준 비교 가능한 pair 수
- `같은 구시군`: 같은 구시군 기준 비교 가능한 pair 수
- `같은 광역권(시도)`: 같은 시도 기준 비교 가능한 pair 수
- `광주+전남 통합`: 광주와 전남을 하나로 묶은 광역권 기준의 비교 가능한 pair 수
- `전국 전체`: 전국 전체 기준 비교 가능한 pair 수

사이트의 메인 표는 확률처럼 읽히는 인상을 줄이기 위해 동일득표 pair 수만 표시한다. 이 파일의 denominator와 rate 정보는 같은 수치를 검증하거나 다른 기준으로 재계산할 때 쓰는 보조 정보다.

## `site-data.js`

`tools/build_site_data.py`가 위 두 CSV에서 생성한 프론트엔드용 데이터 파일이다. 사이트의 핵심 표와 상단 지표는 이 파일에서 읽는다.

- `history[].denominators`: 각 범위별 비교 가능한 pair 수
- `history[].ratesPerMillion`: 동일득표 pair 수를 비교 가능한 pair 수로 나눈 뒤 백만 pair당 비율로 환산한 값
- `scopeItems`: 첫 화면과 비교범위 카드에 쓰는 2026 지선 사전투표 기준 핵심 지표
- `regionalObserved`: 2026년 시·도지사 관내사전투표에서 실제 관측된 동일득표 쌍을 광역권별로 묶은 값과 상세 지역 목록
- `regionalThresholds`: 모델 2(Model 2) w=0.7 기준 50,000회 광역권별 시뮬레이션 결과. 모든 광역권에 대해 `1개 이상`부터 `10개 이상` 동일득표 쌍이 나올 비율을 뜻한다.
- `nearMatch`: ±0, ±1, ±2, ±3표 이내 근접 일치에 대한 실제 관측값과 모델 2 예측 평균/구간
- `geoAdjacent`: SGIS `bnd_dong` 읍면동 경계로 실제 경계선을 공유하는 동만 골라 다시 센 관측 검산 결과. `equal_edge_same_sigungu`는 같은 시군구 안에서 실제 경계 인접인 pair 중 strict 동일득표 pair 수를 뜻한다.

## `geo_adjacent_observed_counts_dong_zip_matched_year.csv`

선거연도와 가장 가까운 SGIS 읍면동 경계 ZIP을 사용해, 실제 경계선을 공유하는 읍면동 pair에서 동일득표가 관측됐는지 집계한 결과다.

- `dataset`: 선거 종류, 회차 또는 연도, 투표 구분
- `boundary_year`, `boundary_quarter`: 사용한 SGIS 경계 기준시점
- `boundary_source`: 사용한 경계 자료 유형. 현재 사이트 표시값은 `dong-zip` 기준이다.
- `rows`: 해당 데이터셋의 분석 행 수
- `matched_rows`: SGIS 경계명과 선거 데이터명이 매칭된 분석 행 수
- `match_rate`: `matched_rows / rows`
- `edge_pairs_all`: 전국에서 실제 경계선을 공유하고 양쪽 모두 매칭된 pair 수
- `edge_pairs_same_sigungu`: 같은 시군구 안에서 실제 경계선을 공유하고 양쪽 모두 매칭된 pair 수
- `equal_edge_all`: `edge_pairs_all` 중 strict 동일득표 pair 수
- `equal_edge_same_sigungu`: `edge_pairs_same_sigungu` 중 strict 동일득표 pair 수

이 검산은 분할동 기준을 대체하는 것이 아니라, 이름 기반 분할동 기준이 실제 지리 인접 판정은 아니라는 한계를 보완하기 위한 별도 관측 집계다.
