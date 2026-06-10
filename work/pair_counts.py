# -*- coding: utf-8 -*-
"""분석 범위별 pair(쌍) 수 집계. 확률 계산 없음.

대상:
  총선 지역구 18~22대 (assembly_rows.pkl) : 본투표 / 사전투표(20~22)
  지선 시도지사 2022(8회)·2026(9회)        : 본투표 / 사전투표
범위(scope): 같은 stem / 같은 구시군 / 같은 광역권(시도) / 광주+전남 통합 / 전국
pair 수 = 각 그룹에서 nC2 의 합.
"""
from __future__ import annotations
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pandas as pd
from pathlib import Path

from paths import DATA_DIR

OUT = DATA_DIR


def emd_stem(name):
    t = re.sub(r"\s+", "", str(name))
    t = re.sub(r"제?\d+(?=동$)", "", t)
    t = re.sub(r"[一二三四五六七八九十]+(?=동$)", "", t)
    return t


def n_pairs(df, cols):
    s = df.groupby(cols, dropna=False).size()
    return int((s * (s - 1) // 2).sum())


def gwangju_jeonnam_region(sido):
    s = str(sido)
    if s in ("광주", "광주광역시", "전남", "전라남도"):
        return "광주전남"
    return s


def counts_for(df):
    """df: columns sido, sigungu, eupmyeondong. 반환: dict scope->pair수, rows."""
    d = df.copy()
    d["_stem"] = d["eupmyeondong"].map(emd_stem)
    d["_gj"] = d["sido"].map(gwangju_jeonnam_region)
    return {
        "rows": len(d),
        "stem(구시군+읍면동stem)": n_pairs(d, ["sido", "sigungu", "_stem"]),
        "같은 구시군": n_pairs(d, ["sido", "sigungu"]),
        "같은 광역권(시도)": n_pairs(d, ["sido"]),
        "광주+전남 통합": n_pairs(d, ["_gj"]),
        "전국 전체": len(d) * (len(d) - 1) // 2,
    }


def load_assembly():
    df = pd.read_pickle(OUT / "assembly_rows.pkl")
    out = {}
    for (dae, vt), g in df.groupby(["dae", "votetype"]):
        out[f"총선 {dae}대 · {vt}"] = g[["sido", "sigungu", "eupmyeondong"]]
    return out


def load_pres():
    df = pd.read_pickle(OUT / "pres_rows.pkl")
    out = {}
    for (dae, vt), g in df.groupby(["dae", "votetype"]):
        out[f"대선 {dae}대 · {vt}"] = g[["sido", "sigungu", "eupmyeondong"]]
    return out


def load_jiseon():
    out = {}
    for yr, label in [("2022", "지선 8회(2022)"), ("2026", "지선 9회(2026)")]:
        reg = pd.read_pickle(OUT / f"nec_{yr}_regular_rows.pkl")
        reg = reg[reg["sheet"] == "시·도지사"].copy()
        reg = reg.rename(columns={"sido_or_district": "sido"})
        adv = reg[reg["gubun"] == "관내사전투표"]
        bon = reg[reg["gubun"] == "선거일투표"]
        out[f"{label} · 본투표"] = bon[["sido", "sigungu", "eupmyeondong"]]
        out[f"{label} · 사전투표"] = adv[["sido", "sigungu", "eupmyeondong"]]
    return out


def main():
    datasets = {}
    datasets.update(load_jiseon())
    datasets.update(load_assembly())
    datasets.update(load_pres())

    scopes = ["stem(구시군+읍면동stem)", "같은 구시군", "같은 광역권(시도)", "광주+전남 통합", "전국 전체"]
    header = f"{'데이터셋':<22}{'행수':>8}" + "".join(f"{s:>20}" for s in scopes)
    print(header)
    print("-" * len(header))
    order = [
        "총선 18대 · 본투표", "총선 19대 · 본투표",
        "총선 20대 · 본투표", "총선 20대 · 사전투표",
        "총선 21대 · 본투표", "총선 21대 · 사전투표",
        "총선 22대 · 본투표", "총선 22대 · 사전투표",
        "지선 8회(2022) · 본투표", "지선 8회(2022) · 사전투표",
        "지선 9회(2026) · 본투표", "지선 9회(2026) · 사전투표",
        "대선 14대 · 본투표", "대선 15대 · 본투표", "대선 16대 · 본투표",
        "대선 17대 · 본투표", "대선 18대 · 본투표",
        "대선 19대 · 본투표", "대선 19대 · 사전투표",
        "대선 20대 · 본투표", "대선 20대 · 사전투표",
        "대선 21대 · 본투표", "대선 21대 · 사전투표",
    ]
    rows_out = []
    for name in order:
        if name not in datasets:
            continue
        c = counts_for(datasets[name])
        line = f"{name:<22}{c['rows']:>8,}" + "".join(f"{c[s]:>20,}" for s in scopes)
        print(line)
        rows_out.append({"dataset": name, "rows": c["rows"], **{s: c[s] for s in scopes}})
    pd.DataFrame(rows_out).to_csv(OUT / "pair_counts.csv", index=False, encoding="utf-8-sig")
    print("\nsaved:", OUT / "pair_counts.csv")


if __name__ == "__main__":
    main()
