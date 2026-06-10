"""(b) 개별 pair 법의학 분석.

1. 2026 관내사전 전국 광역권(광주+전남 통합)에서 정확일치 pair를 모두 추출.
2. 각 pair에 대해, 사전투표자수 n_i, n_j 를 조건으로 고정하고 지역(구시군)
   득표율 p 를 공통으로 두었을 때, 두 행의 민주·국힘 득표수가 *동시에* 같을
   조건부 확률을 정확히 계산. -> 어느 쌍이 '쉬운 우연'이고 어느 쌍이 '진짜 드문'지.
3. 송도1/송도2 는 2022 관내사전 값과 직접 비교.

per-pair 확률 모형:
  (민주, 국힘, 기타)_i ~ Multinomial(n_i, p),  p = 두 행이 속한 구시군 평균 득표율
  P_match = Σ_{a,b} P_i(민주=a,국힘=b) · P_j(민주=a,국힘=b)
  (n_i != n_j 이면 기타가 차이를 흡수; 합산식이 자동 반영)
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import binom

from simulate_joint_events import load_dataframe

REGION_MAP = {"광주광역시": "광주전남", "전라남도": "광주전남"}


def match_prob(ni, nj, pa, pb):
    """P(민주_i=민주_j and 국힘_i=국힘_j | n_i, n_j, p) 정확 계산."""
    if pa <= 0 or pb <= 0 or pa + pb >= 1:
        return float("nan")
    amax = max(ni, nj)
    asd = np.sqrt(amax * pa * (1 - pa))
    alo = max(0, int((ni + nj) / 2 * pa - 8 * asd))
    ahi = int((ni + nj) / 2 * pa + 8 * asd) + 1
    a = np.arange(alo, ahi)
    pai = binom.pmf(a, ni, pa)
    paj = binom.pmf(a, nj, pa)
    pbp = pb / (1 - pa)
    bsd = np.sqrt(amax * pb * (1 - pb))
    blo = max(0, int((ni + nj) / 2 * pb - 8 * bsd))
    bhi = int((ni + nj) / 2 * pb + 8 * bsd) + 1
    b = np.arange(blo, bhi)
    total = 0.0
    for k, av in enumerate(a):
        nbi, nbj = ni - av, nj - av
        if nbi < 0 or nbj < 0:
            continue
        bb = b[b <= min(nbi, nbj)]
        if bb.size == 0:
            continue
        total += pai[k] * paj[k] * float(np.dot(binom.pmf(bb, nbi, pbp), binom.pmf(bb, nbj, pbp)))
    return total


def sigungu_shares(df):
    g = df.groupby(["sido_or_district", "sigungu"], sort=False)[["candidate_1", "candidate_2", "n"]].sum()
    out = {}
    for key, r in g.iterrows():
        if r["n"] > 0:
            out[key] = (r["candidate_1"] / r["n"], r["candidate_2"] / r["n"])
    return out


def main():
    df, _ = load_dataframe("2026", "시·도지사", "advance", 1)
    df["region"] = df["sido_or_district"].replace(REGION_MAP)
    shares = sigungu_shares(df)

    # 정확일치 pair 추출 (광역권 내 동일 (민주,국힘))
    pairs = []
    for region, sub in df.groupby("region", sort=False):
        for (c1, c2), grp in sub.groupby(["candidate_1", "candidate_2"]):
            if len(grp) >= 2:
                rows = grp.to_dict("records")
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        pairs.append((region, rows[i], rows[j]))

    print(f"=== 2026 관내사전 전국 광역권(광주+전남 통합) 정확일치 pair: {len(pairs)}개 ===\n")
    results = []
    for region, r1, r2 in pairs:
        n1, n2 = int(r1["n"]), int(r2["n"])
        s1 = shares.get((r1["sido_or_district"], r1["sigungu"]))
        s2 = shares.get((r2["sido_or_district"], r2["sigungu"]))
        pa = (s1[0] + s2[0]) / 2
        pb = (s1[1] + s2[1]) / 2
        p = match_prob(n1, n2, pa, pb)
        results.append((p, region, r1, r2, n1, n2, pa, pb))

    results.sort(key=lambda x: (x[0] if x[0] == x[0] else 1e9))
    for p, region, r1, r2, n1, n2, pa, pb in results:
        inv = (1 / p) if (p and p == p and p > 0) else float("inf")
        loc1 = f'{r1["sido_or_district"]} {r1["sigungu"]} {r1["eupmyeondong"]}'
        loc2 = f'{r2["sido_or_district"]} {r2["sigungu"]} {r2["eupmyeondong"]}'
        o1 = n1 - int(r1["candidate_1"]) - int(r1["candidate_2"])
        o2 = n2 - int(r2["candidate_1"]) - int(r2["candidate_2"])
        print(f"[{region}] 민주={int(r1['candidate_1'])} 국힘={int(r1['candidate_2'])}")
        print(f"   {loc1}  (n={n1}, 기타={o1})")
        print(f"   {loc2}  (n={n2}, 기타={o2})  | n차이={abs(n1-n2)}")
        print(f"   지역 p=(민주 {pa:.3f}, 국힘 {pb:.3f}) -> 개별 일치확률 ≈ {p:.3e}  (약 1/{inv:,.0f})\n")

    # ---- 송도 2022 vs 2026 ----
    print("=== 송도1동 / 송도2동 관내사전: 2022 vs 2026 ===")
    for yr in ["2022", "2026"]:
        d, _ = load_dataframe(yr, "시·도지사", "advance", 1)
        sd = d[(d["sigungu"] == "연수구") & (d["eupmyeondong"].isin(["송도1동", "송도2동"]))]
        print(f"\n[{yr}]")
        if sd.empty:
            print("  (송도 row 없음)")
            continue
        for _, r in sd.iterrows():
            n = int(r["n"]); c1 = int(r["candidate_1"]); c2 = int(r["candidate_2"])
            print(f"  {r['eupmyeondong']}: n(사전)={n}  민주={c1}  국힘={c2}  기타={n-c1-c2}")
        if len(sd) == 2:
            a, b = sd.iloc[0], sd.iloc[1]
            same = (a["candidate_1"] == b["candidate_1"]) and (a["candidate_2"] == b["candidate_2"])
            print(f"  -> 민주 일치={a['candidate_1']==b['candidate_1']}, 국힘 일치={a['candidate_2']==b['candidate_2']}, 동시일치={same}")


if __name__ == "__main__":
    main()
