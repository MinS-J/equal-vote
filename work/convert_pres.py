# -*- coding: utf-8 -*-
"""대선 14~21대 정규화: 본투표/사전투표(관내) 분리, 읍면동 단위.
후보가 전국 동일이므로 후보명으로 민주/보수 식별.
사전투표(관내사전)는 19·20·21대만 존재.
출력: work/data/pres_rows.pkl / .csv
컬럼: dae, sido, sigungu, eupmyeondong, votetype, electors, votes, dem, ppp, other
"""
from __future__ import annotations
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np
import pandas as pd
from pathlib import Path

from paths import DATA_DIR, INPUTS_DIR

B = INPUTS_DIR / "대선"
OUT = DATA_DIR

# (민주계열 후보, 보수계열 후보)
NAMES = {14: ("김대중", "김영삼"), 15: ("김대중", "이회창"), 16: ("노무현", "이회창"),
         17: ("정동영", "이명박"), 18: ("문재인", "박근혜"), 19: ("문재인", "홍준표"),
         20: ("이재명", "윤석열"), 21: ("이재명", "김문수")}
HAS_ADV = {19, 20, 21}
TOTAL_LABELS = {"소계", "합계"}
SKIP_EMD = {"소계", "합계", "부재자", "부재자투표", "재외투표", "재외투표(공관)",
            "거소·선상투표", "거소투표", "관외사전투표", "국외부재자투표", "국외부재자투표(공관)",
            "잘못 투입·구분된 투표지", "잘못투입·구분된투표지", "계", ""}
END_LABELS = {"계", "유효투표수", "무효투표수", "무표투표수", "기권수"}

rows = []


def ci(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return 0
    if isinstance(v, (int, float)):
        return int(round(v))
    t = str(v).replace(",", "").strip()
    if t in ("", "-", "nan"):
        return 0
    try:
        return int(round(float(t)))
    except ValueError:
        return 0


def ct(v):
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v).strip()


def emit(dae, sido, sigungu, emd, vt, el, votes, dem, ppp, other):
    rows.append({"dae": dae, "sido": ct(sido), "sigungu": re.sub(r"[\[\]]", "", ct(sigungu)),
                 "eupmyeondong": ct(emd), "votetype": vt, "electors": el, "votes": votes,
                 "dem": dem, "ppp": ppp, "other": max(0, other)})


def find_col(hdr_rows, label_set):
    for ri, hr in enumerate(hdr_rows):
        for ci_, v in enumerate(hr):
            if ct(v) in label_set:
                return ci_
    return None


# ---------- 14·15대 ----------
def conv_1415(dae):
    f = B / f"제{dae}대 대통령선거 개표자료.xls"
    raw = pd.read_excel(f, header=None)
    cand_row = raw.iloc[3].tolist()  # 후보명 행
    dem_name, ppp_name = NAMES[dae]
    cand_cols = [i for i in range(7, len(cand_row)) if ct(cand_row[i])]
    dem_c = next((i for i in cand_cols if dem_name in ct(cand_row[i])), None)
    ppp_c = next((i for i in cand_cols if ppp_name in ct(cand_row[i])), None)
    for _, r in raw.iloc[4:].iterrows():
        c = r.tolist()
        sido, gu, emd = ct(c[0]), ct(c[1]), ct(c[2])
        if not emd or emd in SKIP_EMD or gu in ("합계",) or sido in ("전국",):
            continue
        el, votes = ci(c[3]), ci(c[5])
        dem = ci(c[dem_c]) if dem_c is not None else 0
        ppp = ci(c[ppp_c]) if ppp_c is not None else 0
        other = sum(ci(c[i]) for i in cand_cols) - dem - ppp
        emit(dae, sido, gu, emd, "본투표", el, votes, dem, ppp, other)


# ---------- 16대 ----------
def conv_16():
    f = B / "제16대 대통령선거 개표자료.xls"
    xl = pd.ExcelFile(f)
    # 위원회->시도 map (부재자 시트)
    fb = xl.parse(xl.sheet_names[1], header=None)
    gu2sido = {}
    cur = None
    for _, r in fb.iloc[1:].iterrows():
        sido, wi = ct(r.iloc[0]), ct(r.iloc[1])
        if sido and sido not in ("합계",):
            cur = sido
        if wi and wi not in ("소계",):
            gu2sido[re.sub(r"[\[\]]", "", wi)] = cur
    raw = xl.parse(xl.sheet_names[0], header=None)
    hdr = raw.iloc[0].tolist()
    dem_c = next((i for i, v in enumerate(hdr) if ct(v) == "노무현"), None)
    ppp_c = next((i for i, v in enumerate(hdr) if ct(v) == "이회창"), None)
    cand_cols = [i for i in range(5, len(hdr)) if ct(hdr[i]) and ct(hdr[i]) not in END_LABELS]
    cur_emd = None
    for _, r in raw.iloc[1:].iterrows():
        c = r.tolist()
        gu, emd, tp = ct(c[0]), ct(c[1]), ct(c[2])
        if emd and emd not in SKIP_EMD:
            cur_emd = emd
        if tp != "소계":
            continue
        guc = re.sub(r"[\[\]]", "", gu)
        el, votes = ci(c[3]), ci(c[4])
        dem = ci(c[dem_c]); ppp = ci(c[ppp_c])
        other = sum(ci(c[i]) for i in cand_cols) - dem - ppp
        emit(16, gu2sido.get(guc, ""), guc, cur_emd, "본투표", el, votes, dem, ppp, other)


# ---------- 17~21대 공통 (현대형) ----------
def conv_modern(f, dae, sido_param=None):
    raw = pd.read_excel(f, sheet_name=0, header=None)
    # 헤더행: '읍면동명' 포함 행
    hr = None
    for i in range(min(10, len(raw))):
        if "읍면동명" in [ct(x) for x in raw.iloc[i].tolist()]:
            hr = i; break
    if hr is None:
        return
    H = raw.iloc[hr].tolist()
    lab = {ct(v): i for i, v in enumerate(H)}
    c_sido = lab.get("시도명", lab.get("시도"))
    c_gu = lab.get("구시군명", lab.get("구시군"))
    c_emd = lab.get("읍면동명")
    c_tp = lab.get("투표구명")
    c_el = lab.get("선거인수")
    c_vt = lab.get("투표수")
    dem_name, ppp_name = NAMES[dae]
    start = c_vt + 1
    # 후보명 행 탐색: hr~hr+2 중 dem_name 들어있는 행
    name_row = None; name_idx = None
    for k in range(hr, min(hr + 3, len(raw))):
        rr = raw.iloc[k].tolist()
        if any(dem_name in ct(x) for x in rr):
            name_row = rr; name_idx = k; break
    if name_row is None:
        return
    dem_c = next((i for i in range(start, len(name_row)) if dem_name in ct(name_row[i])), None)
    ppp_c = next((i for i in range(start, len(name_row)) if ppp_name in ct(name_row[i])), None)
    cand_cols = []
    for i in range(start, len(name_row)):
        L = ct(name_row[i])
        if not L:
            continue
        if L in END_LABELS:
            break
        cand_cols.append(i)
    cur_sido = sido_param or ""; cur_gu = ""; cur_emd = None
    tot = {}; adv = {}
    for _, r in raw.iloc[name_idx + 1:].iterrows():
        c = r.tolist()
        sido = ct(c[c_sido]) if c_sido is not None else ""
        gu = ct(c[c_gu]) if c_gu is not None else ""
        emd = ct(c[c_emd]) if c_emd is not None else ""
        tp = ct(c[c_tp]) if c_tp is not None else ""
        if sido and sido != "전국":
            cur_sido = sido
        if gu and not gu.startswith("합계"):
            cur_gu = gu
        if emd and emd not in SKIP_EMD:
            cur_emd = emd
        if not cur_emd or tp not in (TOTAL_LABELS | {"관내사전투표"}):
            continue
        el, votes = ci(c[c_el]), ci(c[c_vt])
        dem = ci(c[dem_c]) if dem_c is not None else 0
        ppp = ci(c[ppp_c]) if ppp_c is not None else 0
        other = sum(ci(c[i]) for i in cand_cols) - dem - ppp
        key = (cur_sido, cur_gu, cur_emd)
        if tp in TOTAL_LABELS:
            tot[key] = (el, votes, dem, ppp, other)
        elif tp == "관내사전투표":
            adv[key] = (el, votes, dem, ppp, other)
    for key, t in tot.items():
        sido, gu, emd = key
        a = adv.get(key, (0, 0, 0, 0, 0))
        if dae in HAS_ADV:
            bt = tuple(t[i] - a[i] for i in range(5))
            emit(dae, sido, gu, emd, "본투표", *bt)
            if a[1] > 0 or a[0] > 0:
                emit(dae, sido, gu, emd, "사전투표", *a)
        else:
            emit(dae, sido, gu, emd, "본투표", *t)


if __name__ == "__main__":
    print("converting 대선...")
    conv_1415(14); conv_1415(15)
    conv_16()
    # 17대: 시도별
    for f in sorted((B / "제17대 대통령선거 개표자료").glob("*.xls")):
        sido = re.sub(r"\.xls$", "", f.name).split("_")[-1]
        conv_modern(f, 17, sido_param=sido)
    conv_modern(B / "제18대 대통령선거 개표자료.xls", 18)
    conv_modern(B / "제19대 대통령선거 개표자료.xlsx", 19)
    conv_modern(B / "제20대_대통령선거_개표결과.xlsx", 20)
    conv_modern(B / "제21대_대통령선거_개표결과.xlsx", 21)

    df = pd.DataFrame(rows)
    # 갑/을 같은 중복은 대선엔 없으나, 동일 읍면동 중복 합산(안전)
    df = (df.groupby(["dae", "votetype", "sido", "sigungu", "eupmyeondong"], as_index=False)
            .agg({"electors": "sum", "votes": "sum", "dem": "sum", "ppp": "sum", "other": "sum"}))
    df.to_pickle(OUT / "pres_rows.pkl")
    df.to_csv(OUT / "pres_rows.csv", index=False, encoding="utf-8-sig")
    print("\n=== 대선 정리 결과 (행 수) ===")
    print(df.groupby(["dae", "votetype"]).size().to_string())
    print("\n=== 정당매핑 점검 (dem==0 비율) ===")
    for d in sorted(df.dae.unique()):
        s = df[df.dae == d]
        print(f"{d}대: rows={len(s)}, dem0 {100*(s.dem==0).mean():.1f}%, ppp0 {100*(s.ppp==0).mean():.1f}%, sido빈칸 {(s.sido=='').sum()}")
    print("saved:", OUT / "pres_rows.pkl")
