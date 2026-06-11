from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "data" / "integrity-manifest.json"

INCLUDED_FILES = [
    "index.html",
    "docs.html",
    "styles.css",
    "app.js",
    "docs.js",
    "assets/chart1_scope.png",
    "assets/chart2_calibration.png",
    "assets/data/README.md",
    "assets/data/equal_pair_counts.csv",
    "assets/data/pair_counts.csv",
    "assets/data/site-data.js",
    "assets/data/DATA_DICTIONARY.md",
    "QA_REPORT.md",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    entries = []
    for relative in INCLUDED_FILES:
        path = ROOT / relative
        if not path.exists():
            raise FileNotFoundError(path)
        entries.append(
            {
                "path": relative.replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    payload = {
        "generatedAt": "2026-06-10",
        "algorithm": "sha256",
        "files": entries,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
