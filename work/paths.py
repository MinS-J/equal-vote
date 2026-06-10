from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUTS_DIR = PROJECT_ROOT / "inputs"
CODE_DIR = PROJECT_ROOT / "work"
DATA_DIR = CODE_DIR / "data"
RESULTS_DIR = CODE_DIR / "results"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
