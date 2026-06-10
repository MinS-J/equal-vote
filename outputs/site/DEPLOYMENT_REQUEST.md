# Deployment Request

## Goal

Publish this static site to Vercel so the public can access the Korean election equal-vote analysis.

## Site Root

Use this folder as the Vercel project root:

```text
outputs/site
```

The entry file is:

```text
index.html
```

No build command is required.

## Ready Artifact

If using manual upload, use:

```text
outputs/election-equal-vote-site.zip
```

The zip root contains `index.html`.

## Pre-Deploy Check

From the site root:

```powershell
python tools\build_site_data.py
python tools\build_integrity_manifest.py
python tools\check_site.py
```

Expected result:

```text
ok check_local_refs
ok check_no_local_paths
ok check_site_data
ok check_integrity_manifest
ok check_http_serving
```

## Vercel Settings

- Framework Preset: `Other`
- Build Command: leave empty
- Output Directory: leave empty or use `.`
- Install Command: leave empty

## After First Deploy

After Vercel provides the production URL, configure public metadata and redeploy:

```powershell
python tools\configure_public_url.py --base-url https://your-project.vercel.app
python tools\build_integrity_manifest.py
python tools\check_site.py
vercel --prod
```

If using dashboard/manual upload, re-create the zip after `configure_public_url.py` and upload again.

## Live Verification

After production deploy:

```powershell
python tools\check_production_url.py --base-url https://your-project.vercel.app
```

This checks the home page, JS, CSS, charts, public CSV files, data dictionary, manifest, and core text markers.

## Current Blocker in This Environment

Deployment was not executed here because this shell has no `vercel`, `npm`, or `npx`, no `.vercel` project link, and no Vercel token environment variable.
