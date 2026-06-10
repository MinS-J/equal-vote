from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from paths import DATA_DIR, INPUTS_DIR

SOURCE = (
    INPUTS_DIR
    / "지방선거"
    / "중앙선거관리위원회_제9회 전국동시지방선거 개표결과_2026.csv"
)
OUT_DIR = DATA_DIR

REGULAR_GUBUN = {"계", "관내사전투표", "선거일투표"}
SPECIAL_EUPMYEONDONG = {
    "",
    "합계",
    "거소투표",
    "관외사전투표",
    "잘못 투입·구분된 투표지",
}


def clean_int_series(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace("", "0")
        .astype(int)
    )


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(SOURCE, encoding="utf-8-sig", dtype=str)
    raw = raw.fillna("")

    for col in ["선거인수", "투표수", "득표수", "후보자득표수계", "무효투표수", "기권자수"]:
        raw[col] = clean_int_series(raw[col])

    keys = ["시도", "구시군", "읍면동명", "구분", "선거인수", "투표수", "후보자득표수계", "무효투표수", "기권자수"]

    grouped = (
        raw.groupby(keys, dropna=False)
        .apply(
            lambda g: pd.Series(
                {
                    "candidate_1": int(g.loc[g["정당명"] == "더불어민주당", "득표수"].sum()),
                    "candidate_2": int(g.loc[g["정당명"] == "국민의힘", "득표수"].sum()),
                    "other_candidates": int(
                        g.loc[~g["정당명"].isin(["더불어민주당", "국민의힘"]), "득표수"].sum()
                    ),
                    "candidate_count": int(len(g)),
                }
            )
        )
        .reset_index()
    )

    normalized = grouped.rename(
        columns={
            "시도": "sido_or_district",
            "구시군": "sigungu",
            "읍면동명": "eupmyeondong",
            "구분": "gubun",
            "선거인수": "electors",
            "투표수": "votes",
            "후보자득표수계": "valid_total",
            "무효투표수": "invalid",
            "기권자수": "abstain",
        }
    )
    normalized.insert(0, "sheet", "시·도지사")
    normalized.insert(3, "district", "")

    regular = normalized[
        normalized["gubun"].isin(REGULAR_GUBUN)
        & ~normalized["eupmyeondong"].isin(SPECIAL_EUPMYEONDONG)
    ].copy()
    advance = regular[regular["gubun"] == "관내사전투표"].copy()

    normalized.to_pickle(OUT_DIR / "nec_2026_normalized.pkl")
    normalized.to_csv(OUT_DIR / "nec_2026_normalized.csv", index=False, encoding="utf-8-sig")
    regular.to_pickle(OUT_DIR / "nec_2026_regular_rows.pkl")
    regular.to_csv(OUT_DIR / "nec_2026_regular_rows.csv", index=False, encoding="utf-8-sig")
    advance.to_pickle(OUT_DIR / "nec_2026_advance_rows.pkl")
    advance.to_csv(OUT_DIR / "nec_2026_advance_rows.csv", index=False, encoding="utf-8-sig")

    summary = {
        "source": str(SOURCE),
        "raw_rows": int(len(raw)),
        "normalized_rows": int(len(normalized)),
        "regular_rows": int(len(regular)),
        "advance_rows": int(len(advance)),
        "outputs": [
            str(OUT_DIR / "nec_2026_normalized.pkl"),
            str(OUT_DIR / "nec_2026_regular_rows.pkl"),
            str(OUT_DIR / "nec_2026_advance_rows.pkl"),
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
