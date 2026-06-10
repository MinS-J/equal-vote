# Static Site QA Report

Date: 2026-06-10

## Verified

- Static site files are self-contained under `outputs/site`.
- Public data files are included under `assets/data`.
- `site-data.js` is generated from `equal_pair_counts.csv` and `pair_counts.csv` using `tools/build_site_data.py`.
- Public data columns are documented in `assets/data/DATA_DICTIONARY.md`.
- Public data and chart file hashes are recorded in `assets/data/integrity-manifest.json`.
- Canonical URL, Open Graph URL, robots sitemap entry, and `sitemap.xml` can be configured after deploy with `tools/configure_public_url.py`.
- Live production availability can be checked after deploy with `tools/check_production_url.py`.
- The highlighted 2026 local-election advance-vote row is sourced from CSV data:
  - stem: 1
  - same sigungu: 1
  - same sido: 7
  - Gwangju+Jeonnam combined: 8
  - national: 10
- Main static assets resolve under local HTTP serving:
  - `/`
  - `/styles.css`
  - `/app.js`
  - `/assets/chart1_scope.png`
- `/assets/data/equal_pair_counts.csv`
- `/assets/data/DATA_DICTIONARY.md`

## Known Limits

- In-app browser visual verification could not run in this environment because the browser runtime failed to start under the Windows sandbox.
- Vercel deployment was not executed because `vercel`, `npm`, and `npx` are not installed in the current shell environment.
- The site is ready for static deployment, but final production URL verification remains pending until Vercel CLI or dashboard upload is available.
- Dashboard deployment fallback steps are documented in `VERCEL_DASHBOARD_DEPLOY.md`.
- Production URL metadata remains unset until the final Vercel URL is known.
- Current publication state is summarized in `PUBLICATION_STATUS.md`.
