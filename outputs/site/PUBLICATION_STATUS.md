# Publication Status

Date: 2026-06-10

## Current State

The static explainer site is ready for Vercel upload from this folder:

```text
outputs/site
```

The latest packaged upload artifact is:

```text
outputs/election-equal-vote-site.zip
```

## Completed

- Reproducible data pipeline prepared for the election equal-vote analysis.
- Static public explainer site built with:
  - issue framing
  - Songdo case table
  - scope and post-search explanation
  - nationwide election summary table
  - simulation interpretation
  - public interpretation limits
  - chart gallery
  - source and reproducibility links
- Public data included:
  - `assets/data/equal_pair_counts.csv`
  - `assets/data/pair_counts.csv`
  - `assets/data/site-data.js`
  - `assets/data/DATA_DICTIONARY.md`
  - `assets/data/integrity-manifest.json`
- Pre-deploy QA script added and passing:
  - `python tools/check_site.py`
- Production URL verification script added:
  - `python tools/check_production_url.py --base-url <production-url>`
- Vercel CLI and dashboard deployment instructions documented.
- Final deployment handoff is documented in `DEPLOYMENT_REQUEST.md`.

## Remaining

- Upload or import the site into Vercel.
- Obtain the production URL.
- Run:

```powershell
python tools\configure_public_url.py --base-url <production-url>
python tools\check_site.py
vercel --prod
python tools\check_production_url.py --base-url <production-url>
```

If deploying through the Vercel Dashboard rather than CLI, run `configure_public_url.py`, re-zip the folder, upload again, then run `check_production_url.py` from a local environment with network access.

## Reason Deployment Is Not Yet Complete Here

The current shell environment does not provide `vercel`, `npm`, or `npx`, and no Vercel deployment API tool is exposed in this thread. The site package is prepared, but final remote registration and live URL verification require one of those deployment paths.
