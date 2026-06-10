# -*- coding: utf-8 -*-
"""범위별 '동일득표' 쌍 탐지 (관측값, 시뮬레이션 없음).

동일득표 쌍 = 같은 범위 그룹 안에서 민주 득표수가 같고 국민의힘 득표수도 같은 두 행.
범위: 같은 stem / 같은 구시군 / 같은 광역권(시도) / 광주+전남 통합 / 전국 전체.
(dem==0 & ppp==0 인 퇴화 일치는 제외하고 별도 표기)
출력: work/data/equal_pair_counts.csv, equal_pairs_detail.csv
"""
from __future__ import annotations
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pandas as pd
from itertools import combinations
from pathlib import Path

from paths import DATA_DIR

OUT = DATA_DIR


def emd_stem(name):
    t = re.sub(r"\s+", "", str(name))
    t = re.sub(r"제?\d+(?=동$)", "", t)
    t = re.sub(r"[一二三四五六七八九十]+(?=동$)", "", t)
    return t


def gj(sido):
    return "광주전남" if str(sido) in ("광주", "광주광역시", "전남", "전라남도") else str(sido)


def eqpairs(df, cols):
    """cols 범위 그룹 내 (dem,ppp) 동일 쌍 수."""
    g = df.groupby(cols + ["dem", "ppp"]).size()
    return int((g * (g - 1) // 2).sum())


def counts_for(df):
    # strict: 민주>0 & 국힘>0 (한 정당 후보 부재로 인한 0=0 trivial 매칭 제외)
    d = df[(df.dem > 0) & (df.ppp > 0)].copy()
    d["_stem"] = d["eupmyeondong"].map(emd_stem)
    d["_gj"] = d["sido"].map(gj)
    full = df.copy()
    full["_gj"] = full["sido"].map(gj)
    res = {}
    for name, cols in [("stem", ["sido", "sigungu", "_stem"]),
                       ("같은 구시군", ["sido", "sigungu"]),
                       ("광역권(시도)", ["sido"]),
                       ("광주+전남 통합", ["_gj"]),
                       ("전국 전체", ["_all"])]:
        if name == "전국 전체":
            d["_all"] = 0; full["_all"] = 0
        res[name] = eqpairs(d, cols if name != "전국 전체" else ["_all"])
    # 참고: 한 정당 0 포함(0,0 제외) 전국 카운트
    full = full[~((full.dem == 0) & (full.ppp == 0))]
    res["전국_loose"] = eqpairs(full, ["_all"])
    return res


def detail_pairs(label, df):
    """광주+전남 통합 범위 내 일치쌍을 행 단위로 나열 (0,0 제외)."""
    d = df[(df.dem > 0) & (df.ppp > 0)].copy()
    d["_stem"] = d["eupmyeondong"].map(emd_stem)
    d["_gj"] = d["sido"].map(gj)
    out = []
    for (reg, dem, ppp), idx in d.groupby(["_gj", "dem", "ppp"]).groups.items():
        sub = d.loc[idx]
        if len(sub) < 2:
            continue
        recs = sub.to_dict("records")
        for a, b in combinations(recs, 2):
            if a["sido"] == b["sido"] and a["sigungu"] == b["sigungu"] and a["_stem"] == b["_stem"]:
                tight = "같은stem"
            elif a["sido"] == b["sido"] and a["sigungu"] == b["sigungu"]:
                tight = "같은구시군"
            elif a["sido"] == b["sido"]:
                tight = "같은시도"
            else:
                tight = "광주전남교차"
            out.append({"dataset": label, "권역": reg, "tightness": tight, "민주": dem, "국힘": ppp,
                        "지역1": f"{a['sido']} {a['sigungu']} {a['eupmyeondong']}",
                        "지역2": f"{b['sido']} {b['sigungu']} {b['eupmyeondong']}"})
    return out


def norm_assembly():
    df = pd.read_pickle(OUT / "assembly_rows.pkl")
    for (dae, vt), g in df.groupby(["dae", "votetype"]):
        yield f"총선 {dae}대·{vt}", g[["sido", "sigungu", "eupmyeondong", "dem", "ppp"]]


def norm_pres():
    df = pd.read_pickle(OUT / "pres_rows.pkl")
    for (dae, vt), g in df.groupby(["dae", "votetype"]):
        yield f"대선 {dae}대·{vt}", g[["sido", "sigungu", "eupmyeondong", "dem", "ppp"]]


def norm_jiseon():
    for yr, lab in [("2022", "지선8회(2022)"), ("2026", "지선9회(2026)")]:
        reg = pd.read_pickle(OUT / f"nec_{yr}_regular_rows.pkl")
        reg = reg[reg["sheet"] == "시·도지사"].rename(
            columns={"sido_or_district": "sido", "candidate_1": "dem", "candidate_2": "ppp"})
        for vt, gub in [("본투표", "선거일투표"), ("사전투표", "관내사전투표")]:
            g = reg[reg["gubun"] == gub][["sido", "sigungu", "eupmyeondong", "dem", "ppp"]].copy()
            g["dem"] = g["dem"].astype(int); g["ppp"] = g["ppp"].astype(int)
            yield f"{lab}·{vt}", g


def main():
    order, data = [], {}
    for src in (norm_pres, norm_assembly, norm_jiseon):
        for name, g in src():
            data[name] = g; order.append(name)
    order.sort()

    scopes = ["stem", "같은 구시군", "광역권(시도)", "광주+전남 통합", "전국 전체"]
    print("[strict: 민주>0 & 국힘>0 동일득표 쌍]")
    print(f"{'데이터셋':<22}" + "".join(f"{s:>15}" for s in scopes) + f"{'(참고)전국loose':>15}")
    print("-" * (22 + 15 * (len(scopes) + 1)))
    rows, detail = [], []
    for name in order:
        c = counts_for(data[name])
        print(f"{name:<22}" + "".join(f"{c[s]:>15,}" for s in scopes) + f"{c['전국_loose']:>15,}")
        rows.append({"dataset": name, **{s: c[s] for s in scopes}, "전국_loose(한정당0포함)": c["전국_loose"]})
        detail += detail_pairs(name, data[name])
    pd.DataFrame(rows).to_csv(OUT / "equal_pair_counts.csv", index=False, encoding="utf-8-sig")
    dd = pd.DataFrame(detail)
    dd.to_csv(OUT / "equal_pairs_detail.csv", index=False, encoding="utf-8-sig")
    print(f"\n일치쌍 상세(광주전남 통합 범위 이내): {len(dd)}건 -> equal_pairs_detail.csv")
    print("saved: equal_pair_counts.csv")


if __name__ == "__main__":
    main()
