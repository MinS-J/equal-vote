# Vercel Dashboard Deploy Guide

이 사이트는 빌드가 필요 없는 정적 사이트다. `outputs/site` 폴더 전체가 배포 루트다.

## Option A: Vercel CLI

로컬에 Node/npm과 Vercel CLI가 있다면 가장 간단하다.

```powershell
cd <this-site-folder>
npm i -g vercel
vercel login
python tools\check_site.py
vercel --prod
```

## Option B: Git Repository Import

1. `outputs/site` 안의 파일들을 새 Git repository 루트에 둔다.
2. Vercel Dashboard에서 `Add New...` -> `Project`를 선택한다.
3. 해당 repository를 Import한다.
4. Framework Preset은 `Other` 또는 정적 사이트 설정을 사용한다.
5. Build Command는 비워둔다.
6. Output Directory도 비워두거나 `.`로 둔다.
7. Deploy를 실행한다.

## Option C: Manual Upload

Vercel 계정에서 수동 업로드가 가능한 흐름을 쓰는 경우, 상위 `outputs` 폴더의
`election-equal-vote-site.zip`을 사용한다. 압축 내부의 루트에 `index.html`이 있어야 한다.

## After Deploy

배포 후 반드시 확인한다.

- 프로덕션 URL에서 첫 화면 제목이 보이는가
- 차트 이미지가 로딩되는가
- `전국데이터` 표 필터가 동작하는가
- `자료와 재현성` 링크가 열리는가
- 공유 미리보기 제목이 `후보별 동일득표 분석`으로 잡히는가

가능하면 로컬에서 다음 명령으로도 확인한다.

```powershell
python tools\check_production_url.py --base-url https://your-project.vercel.app
```
