# Vercel Static Deploy

This folder is a static site. Deploy `outputs/site` as the Vercel project root.

If the Vercel CLI is not installed:

```powershell
npm i -g vercel
vercel login
```

Recommended production deploy command from this folder:

```powershell
vercel --prod
```

No build command is required. The entry file is `index.html`, with local assets in `assets/`.

When `equal_pair_counts.csv` or `pair_counts.csv` changes, regenerate the frontend data file before deploying:

```powershell
python tools\build_site_data.py
python tools\build_integrity_manifest.py
```

Pre-deploy local verification:

```powershell
python tools\check_site.py
```

If CLI deployment is unavailable, use `VERCEL_DASHBOARD_DEPLOY.md` for dashboard import or manual upload steps.

For a concise handoff to whoever will deploy, use `DEPLOYMENT_REQUEST.md`.

After the first production URL is known, configure canonical metadata and sitemap, then redeploy:

```powershell
python tools\configure_public_url.py --base-url https://your-project.vercel.app
python tools\build_integrity_manifest.py
python tools\check_site.py
vercel --prod
```

After deployment, verify the live site:

```powershell
python tools\check_production_url.py --base-url https://your-project.vercel.app
```
