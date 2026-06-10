# -*- coding: utf-8 -*-
"""동일득표 쌍을 선거종류 -> 연도 -> 지역으로 정리 (strict: 민주>0 & 국힘>0).
출력: work/data/동일득표_정리.csv  + 콘솔 요약(선거종류/연도/지역별 건수)
"""
from __future__ import annotations
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import pandas as pd
from itertools import combinations
from pathlib import Path

from paths import DATA_DIR

OUT = DATA_DIR

YEAR = {("대선", 14): 1992, ("대선", 15): 1997, ("대선", 16): 2002, ("대선", 17): 2007,
        ("대선", 18): 2012, ("대선", 19): 2017, ("대선", 20): 2022, ("대선", 21): 2025,
        ("총선", 18): 2008, ("총선", 19): 2012, ("총선", 20): 2016, ("총선", 21): 2020,
        ("총선", 22): 2024, ("지선", 8): 2022, ("지선", 9): 2026}

SIDO_SHORT = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
              "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
              "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북",
              "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
              "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주"}


def short(s):
    return SIDO_SHORT.get(str(s), str(s))


def stem(name):
    t = re.sub(r"\s+", "", str(name)); t = re.sub(r"제?\d+(?=동$)", "", t)
    return re.sub(r"[一二三四五六七八九十]+(?=동$)", "", t)


def pairs_of(df):
    d = df[(df.dem > 0) & (df.ppp > 0)].copy()
    out = []
    for (dem, ppp), idx in d.groupby(["dem", "ppp"]).groups.items():
        sub = d.loc[idx]
        if len(sub) < 2:
            continue
        for a, b in combinations(sub.to_dict("records"), 2):
            s1, s2 = short(a["sido"]), short(b["sido"])
            same = s1 == s2
            if same and a["sigungu"] == b["sigungu"] and stem(a["eupmyeondong"]) == stem(b["eupmyeondong"]):
                tight = "같은stem"
            elif same and a["sigungu"] == b["sigungu"]:
                tight = "같은구시군"
            elif same:
                tight = "같은시도"
            else:
                tight = "시도교차"
            region = s1 if same else "↔".join(sorted([s1, s2]))
            out.append({"지역구분": "같은시도" if same else "시도교차", "지역": region, "tightness": tight,
                        "민주": dem, "국힘": ppp,
                        "지역1": f"{a['sido']} {a['sigungu']} {a['eupmyeondong']}",
                        "지역2": f"{b['sido']} {b['sigungu']} {b['eupmyeondong']}"})
    return out


def loaders():
    asm = pd.read_pickle(OUT / "assembly_rows.pkl")
    for (dae, vt), g in asm.groupby(["dae", "votetype"]):
        yield "총선", dae, vt, g[["sido", "sigungu", "eupmyeondong", "dem", "ppp"]]
    pr = pd.read_pickle(OUT / "pres_rows.pkl")
    for (dae, vt), g in pr.groupby(["dae", "votetype"]):
        yield "대선", dae, vt, g[["sido", "sigungu", "eupmyeondong", "dem", "ppp"]]
    for yr, dae in [("2022", 8), ("2026", 9)]:
        reg = pd.read_pickle(OUT / f"nec_{yr}_regular_rows.pkl")
        reg = reg[reg["sheet"] == "시·도지사"].rename(
            columns={"sido_or_district": "sido", "candidate_1": "dem", "candidate_2": "ppp"})
        for vt, gub in [("본투표", "선거일투표"), ("사전투표", "관내사전투표")]:
            g = reg[reg["gubun"] == gub][["sido", "sigungu", "eupmyeondong", "dem", "ppp"]].copy()
            g["dem"] = g["dem"].astype(int); g["ppp"] = g["ppp"].astype(int)
            yield "지선", dae, vt, g


def main():
    recs = []
    all_keys = []  # 0쌍 포함 모든 (선거×연도×투표)
    for kind, dae, vt, g in loaders():
        yr = YEAR.get((kind, dae))
        all_keys.append((kind, yr, dae, vt))
        for p in pairs_of(g):
            recs.append({"선거종류": kind, "연도": yr, "대수": dae, "투표": vt, **p})
    df = pd.DataFrame(recs)
    df = df[["선거종류", "연도", "대수", "투표", "지역구분", "지역", "tightness", "민주", "국힘", "지역1", "지역2"]]
    df.to_csv(OUT / "동일득표_정리.csv", index=False, encoding="utf-8-sig")

    # 콘솔: 선거종류>연도>투표 별, 0쌍 포함. 광주<->전남 교차는 따로 표기.
    kind_order = {"대선": 0, "총선": 1, "지선": 2}
    print("기준: 전국 strict(민주>0 & 국힘>0) 일치쌍. 시도 단위(광주·전남 분리), 광주↔전남 교차는 별도 표기.")
    for kind in ["대선", "총선", "지선"]:
        keys = sorted({k for k in all_keys if k[0] == kind}, key=lambda k: (k[1], k[3]))
        print(f"\n{'='*78}\n[{kind}]")
        print(f"  {'연도':<6}{'투표':<6}{'전국':>5}{'같은시도':>7}{'광주↔전남':>9}{'기타교차':>7}   같은시도 지역분포")
        for kind2, yr, dae, vt in keys:
            g = df[(df.선거종류 == kind) & (df.연도 == yr) & (df.투표 == vt)]
            same = g[g.지역구분 == "같은시도"]
            gj = g[(g.지역구분 == "시도교차") & (g.지역.apply(lambda r: set(str(r).split("↔")) == {"광주", "전남"}))]
            other = g[(g.지역구분 == "시도교차") & (~g.index.isin(gj.index))]
            same_by = same.지역.value_counts().to_dict()
            same_str = " ".join(f"{k}{v}" for k, v in same_by.items()) if same_by else "-"
            print(f"  {yr:<6}{vt:<6}{len(g):>5}{len(same):>7}{len(gj):>9}{len(other):>7}   {same_str}")
    print(f"\n전체 {len(df)}쌍 -> {OUT/'동일득표_정리.csv'}")


if __name__ == "__main__":
    main()
