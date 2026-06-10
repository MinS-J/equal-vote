# Equal Vote Reproducibility Release

## Files

- `equal-vote-code.zip`: analysis README, Python scripts, requirements file, and site source.
- `equal-vote-inputs.zip`: original election input files. Unzip this beside `work/`.
- `equal-vote-precomputed.zip`: generated `work/data` and `work/results` files for quick verification.
- `SHA256SUMS.txt`: SHA256 checksums for the ZIP files.

## Rebuild

Unzip `equal-vote-code.zip`, then unzip `equal-vote-inputs.zip` into the same folder so that `inputs/` sits beside `work/`.

```powershell
cd work
python -m pip install -r requirements.txt
python -m compileall .
python run_pipeline.py --stage all-smoke
```

For quick comparison without rerunning every expensive simulation, unzip `equal-vote-precomputed.zip` into the same folder.

## Suggested GitHub Release Text

This release provides the reproducibility bundle for the election equal-vote analysis.

To reproduce from original data, download `equal-vote-code.zip` and `equal-vote-inputs.zip`, unzip both into the same folder, install `work/requirements.txt`, then run `python run_pipeline.py --stage all-smoke` inside `work/`.

The `equal-vote-precomputed.zip` file contains generated intermediate data and simulation result JSON files for faster verification. Full 50,000 or 200,000 iteration simulations may take substantially longer than the smoke run.
