# 선거 동일득표 분석 재현 패키지

이 저장소는 선거 개표 원자료에서 후보별 동일득표 쌍을 다시 집계하고, 관측된 동일득표 사건의 발생 가능성을 시뮬레이션으로 점검하기 위한 코드와 사이트 소스를 담고 있습니다.

## 구성

- `work/`: 분석 코드와 실행 파이프라인
- `outputs/site/`: 공개 설명 사이트 소스
- `README.repro.md`: 전체 재현 가이드
- `RELEASE_NOTES.md`: GitHub Release asset 설명

원본 선거 데이터와 큰 중간 산출물은 저장소에 직접 커밋하지 않고 GitHub Release asset으로 제공합니다.

## 다운로드할 파일

처음부터 재현하려면 Release에서 아래 파일을 받습니다.

- `equal-vote-code.zip`: 이 저장소의 코드와 사이트 소스 묶음
- `equal-vote-inputs.zip`: 원본 선거 입력 데이터
- `equal-vote-precomputed.zip`: 빠른 검증용 중간 데이터와 시뮬레이션 결과
- `SHA256SUMS.txt`: ZIP 파일 체크섬

## 빠른 재현

`equal-vote-code.zip`과 `equal-vote-inputs.zip`을 같은 폴더에 풀면 최상위에 `inputs/`, `work/`, `outputs/`가 생깁니다.

```powershell
cd work
python -m pip install -r requirements.txt
python -m compileall .
python run_pipeline.py --stage all-smoke
```

정밀 시뮬레이션은 시간이 오래 걸릴 수 있으므로 기본 명령은 낮은 반복 수의 smoke run만 실행합니다. 기존 결과를 빠르게 대조하려면 `equal-vote-precomputed.zip`도 같은 위치에 풀어 `work/data`와 `work/results`를 채웁니다.

## 사이트

정적 사이트 소스는 `outputs/site/`에 있습니다. 배포된 사이트에서는 재현성 문서를 Markdown 뷰어로 볼 수 있습니다.

- https://election-equal-vote-site.vercel.app

## 주의

이 분석은 공개 개표자료에서 관측된 동일득표 패턴의 희귀성과 재현성을 평가하는 작업입니다. 개표 절차, 원자료 진위, 법적 판단을 직접 판정하는 자료가 아닙니다.
