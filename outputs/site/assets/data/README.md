# 선거 동일득표 분석 재현 가이드

이 폴더는 선거 개표 원자료를 정규화하고, 후보별 동일득표 쌍을 집계한 뒤, 관측된 동일득표 사건의 발생 확률을 시뮬레이션으로 점검하는 작업 공간이다.

## Folder Layout

- `inputs/`: 원본 선거 데이터
  - `대선/`
  - `총선/`
  - `지방선거/`
- `work/`: Python 코드, 중간 데이터, 시뮬레이션 결과
  - `work/data/`: 정규화된 `.pkl`/`.csv`와 동일득표 집계
  - `work/results/`: 시뮬레이션 JSON 결과
- `outputs/`: 요약 문서와 발표자료 산출물

경로 기준은 이 README가 있는 폴더다. 코드 내부에서는 `work/paths.py`가 `inputs/`, `work/data/`, `work/results/`, `outputs/`의 위치를 공통으로 정의한다.

## Requirements

확인된 실행 환경:

- Python 3.11
- pandas
- numpy
- openpyxl
- scipy

오래된 `.xls` 원본을 새로 변환하려면 `xlrd`가 추가로 필요할 수 있다.

## Rebuild Commands

아래 명령은 `work/` 코드 폴더에서 실행한다.

```powershell
cd C:\Users\minse\Documents\Codex\2026-06-10\goal-1\work\work
python -m compileall .
python run_pipeline.py --stage convert
python run_pipeline.py --stage detect
python run_pipeline.py --stage simulate-smoke
```

한 번에 기본 재현 점검을 수행하려면:

```powershell
python run_pipeline.py --stage all-smoke
```

## Pipeline Stages

- `convert`: 원본 데이터를 정규화해 `work/data`에 저장한다.
  - `pres_rows.pkl`
  - `assembly_rows.pkl`
  - `nec_2022_advance_rows.pkl`
  - `nec_2026_advance_rows.pkl`
- `detect`: 정규화 데이터를 사용해 동일득표 쌍과 비교 가능한 pair 수를 집계한다.
  - `equal_pair_counts.csv`
  - `equal_pairs_detail.csv`
  - `pair_counts.csv`
  - `동일득표_정리.csv`
- `simulate-smoke`: 낮은 반복 수로 시뮬레이션 코드와 결과 저장 경로만 검증한다.
- `all-smoke`: `convert`, `detect`, `simulate-smoke`를 순서대로 실행한다.

## Full Simulation Notes

`simulate-smoke`는 재현성 점검용이라 반복 수를 50회로 낮춘다. 보고서 수치를 재생성하려면 기존 분석에서 사용한 50,000회 또는 200,000회 설정으로 `simulate_equal_candidate_pairs.py`와 `simulate_joint_events.py`를 직접 실행한다.

예:

```powershell
python simulate_joint_events.py --dataset 2026 --sheet 시·도지사 --rows advance --prob-model row_shrink --q-prior-weight 0.7 --p-prior-weight 0.7 --iters 50000
```

정밀 시뮬레이션은 시간이 오래 걸리므로 기본 파이프라인에는 포함하지 않는다.

## Public Reproducibility Package

공개 저장소와 다운로드 묶음은 아래 위치에 있다.

- GitHub 저장소: https://github.com/MinS-J/equal-vote
- GitHub Release: https://github.com/MinS-J/equal-vote/releases/tag/v2026-06-10

Release 파일:

- `equal-vote-code.zip`: 분석 코드와 사이트 소스
- `equal-vote-inputs.zip`: 처음부터 재현할 때 필요한 원본 선거 데이터
- `equal-vote-precomputed.zip`: 빠른 검증용 중간 데이터와 시뮬레이션 결과
- `SHA256SUMS.txt`: ZIP 파일 체크섬
