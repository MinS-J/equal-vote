from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from paths import CODE_DIR, DATA_DIR, RESULTS_DIR


CONVERT_STEPS = [
    ["convert_pres.py"],
    ["convert_assembly.py"],
    ["convert_nec_2022.py"],
    ["convert_nec_2026.py"],
]

DETECT_STEPS = [
    ["detect_equal.py"],
    ["pair_counts.py"],
    ["organize_equal.py"],
]

SIMULATE_SMOKE_STEPS = [
    [
        "simulate_equal_candidate_pairs.py",
        "--dataset",
        "2026",
        "--sheet",
        "시·도지사",
        "--rows",
        "advance",
        "--pair-scope",
        "same_sigungu",
        "--model-scope",
        "same_sigungu",
        "--prob-model",
        "group",
        "--iters",
        "50",
        "--seed",
        "20260609",
    ],
    [
        "simulate_joint_events.py",
        "--dataset",
        "2026",
        "--sheet",
        "시·도지사",
        "--rows",
        "advance",
        "--prob-model",
        "row_shrink",
        "--iters",
        "50",
        "--seed",
        "20260610",
    ],
]

CONVERT_OUTPUTS = [
    DATA_DIR / "assembly_rows.pkl",
    DATA_DIR / "pres_rows.pkl",
    DATA_DIR / "nec_2022_advance_rows.pkl",
    DATA_DIR / "nec_2026_advance_rows.pkl",
]

DETECT_OUTPUTS = [
    DATA_DIR / "equal_pair_counts.csv",
    DATA_DIR / "equal_pairs_detail.csv",
    DATA_DIR / "pair_counts.csv",
    DATA_DIR / "동일득표_정리.csv",
]


def run_step(args: list[str]) -> None:
    command = [sys.executable, *args]
    print("$ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=CODE_DIR, check=True)


def require_outputs(paths: list[Path]) -> None:
    missing = [path for path in paths if not path.exists()]
    if missing:
        formatted = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"Expected output files were not created:\n{formatted}")


def stage_convert() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for step in CONVERT_STEPS:
        run_step(step)
    require_outputs(CONVERT_OUTPUTS)


def stage_detect() -> None:
    for step in DETECT_STEPS:
        run_step(step)
    require_outputs(DETECT_OUTPUTS)


def stage_simulate_smoke() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    before = set(RESULTS_DIR.glob("*.json"))
    for step in SIMULATE_SMOKE_STEPS:
        run_step(step)
    after = set(RESULTS_DIR.glob("*.json"))
    created = sorted(after - before)
    if created:
        print("Created smoke result files:")
        for path in created:
            print(f"- {path}")
    else:
        print("Smoke simulations completed; result filenames may have overwritten existing files.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run reproducible election equal-vote analysis stages.")
    parser.add_argument(
        "--stage",
        choices=["convert", "detect", "simulate-smoke", "all-smoke"],
        required=True,
        help="Pipeline stage to run.",
    )
    args = parser.parse_args()

    if args.stage == "convert":
        stage_convert()
    elif args.stage == "detect":
        stage_detect()
    elif args.stage == "simulate-smoke":
        stage_simulate_smoke()
    elif args.stage == "all-smoke":
        stage_convert()
        stage_detect()
        stage_simulate_smoke()
    else:
        raise ValueError(f"Unknown stage: {args.stage}")


if __name__ == "__main__":
    main()
