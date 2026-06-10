# -*- coding: utf-8 -*-
"""총선 지역구 18~22대 정규화: 본투표/사전투표(관내) 분리, 읍면동 단위.

출력: work/data/assembly_rows.pkl / .csv
컬럼: dae, sido, sigungu, district(선거구), eupmyeondong, votetype(본투표/사전투표),
      electors, votes, dem, ppp, other
사전투표(관내사전)는 20·21·22대에만 존재.
"""
from __future__ import annotations
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np
import pandas as pd
from pathlib import Path

from paths import DATA_DIR, INPUTS_DIR

B = INPUTS_DIR / "총선"
OUT = DATA_DIR
OUT.mkdir(parents=True, exist_ok=True)

DEM = {18: "통합민주당", 19: "민주통합당", 20: "더불어민주당", 21: "더불어민주당", 22: "더불어민주당"}
PPP = {18: "한나라당", 19: "새누리당", 20: "새누리당", 21: "미래통합당", 22: "국민의힘"}

SIDO_SHORT = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북",
    "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주",
}


def sido_short(s):
    s = ct(s)
    return SIDO_SHORT.get(s, s)

SPECIAL = {"합계", "계", "거소·선상투표", "거소투표", "관외사전투표", "국외부재자투표",
           "국외부재자투표(공관)", "국내부재자투표", "부재자", "부재자투표",
           "잘못 투입·구분된 투표지", "잘못투입·구분된투표지", "소계", "관내사전투표", ""}


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


def clean_sigungu(name: str) -> str:
    """선거구명 -> 구시군. 갑/을/병/정 및 숫자 제거, 괄호 처리."""
    t = ct(name)
    m = re.search(r"\(([^)]+)\)\s*$", t)  # "동해시삼척시(동해시)" -> 동해시
    if m:
        t = m.group(1)
    t = re.sub(r"[0-9]+$", "", t)
    t = re.sub(r"[갑을병정무기]$", "", t)
    return t.strip()


def party_of(cell: str) -> str:
    """'더불어민주당\\n곽상언' -> '더불어민주당'."""
    return ct(cell).split("\n")[0].strip()


rows = []


def emit(dae, sido, district, emd, votetype, electors, votes, dem, ppp, other, sigungu=None):
    rows.append({
        "dae": dae, "sido": sido.strip(),
        "sigungu": (ct(sigungu) if sigungu else clean_sigungu(district)),
        "district": district.strip(), "eupmyeondong": ct(emd),
        "votetype": votetype, "electors": electors, "votes": votes,
        "dem": dem, "ppp": ppp, "other": other,
    })


# ---------- Family A: 22대 (전국 단일) ----------
def conv22(emd2gu):
    f = B / "국회의원선거 개표결과(제22대)/1. 개표단위별 개표결과(지역구) -전국.xlsx"
    raw = pd.read_excel(f, header=None, skiprows=4)
    cur_sido = cur_dist = cur_emd = cur_gu = None
    dem_c = ppp_c = None; cand_cols = []
    sub = {}; adv = {}  # (sido,dist,emd) -> tuple(el,votes,dem,ppp,other)
    for _, r in raw.iterrows():
        c = r.tolist()
        sido, dist, emd, vtype = ct(c[0]), ct(c[1]), ct(c[3]), ct(c[4])
        is_name = dist and not emd and any("당" in ct(c[i]) for i in range(7, len(c)))
        if is_name:
            cur_sido = sido or cur_sido; cur_dist = dist; cur_emd = None
            if ct(c[2]):
                cur_gu = ct(c[2])  # 구시군명 (갑/을은 병합셀이라 첫 선거구에만; ffill)
            cand_cols = [i for i in range(7, len(c)) if ct(c[i])]
            dem_c = next((i for i in cand_cols if party_of(c[i]) == DEM[22]), None)
            ppp_c = next((i for i in cand_cols if party_of(c[i]) == PPP[22]), None)
            continue
        if not cand_cols:
            continue
        if emd in SPECIAL and vtype not in ("소계", "관내사전투표"):
            continue  # 선거구 상단 합계/거소/관외/국외
        electors, votes = ci(c[5]), ci(c[6])
        dem = ci(c[dem_c]) if dem_c is not None else 0
        ppp = ci(c[ppp_c]) if ppp_c is not None else 0
        other = sum(ci(c[i]) for i in cand_cols) - dem - ppp
        if vtype == "소계":
            cur_emd = emd
            sub[(cur_sido, cur_dist, cur_emd)] = (electors, votes, dem, ppp, other, cur_gu or cur_dist)
        elif vtype == "관내사전투표" and cur_emd:
            adv[(cur_sido, cur_dist, cur_emd)] = (electors, votes, dem, ppp, other, cur_gu or cur_dist)
    for key, s in sub.items():
        a = adv.get(key, (0, 0, 0, 0, 0, s[5]))
        sido, dist, emd = key
        # 구시군: 20·21대 (시도,읍면동)->구시군 맵 우선, 없으면 col2 ffill, 없으면 선거구
        gusigun = emd2gu.get((sido_short(sido), emd)) or s[5]
        bt = tuple(s[i] - a[i] for i in range(5))
        if bt[1] > 0 or bt[0] > 0:
            emit(22, sido, dist, emd, "본투표", *bt, sigungu=gusigun)
        if a[1] > 0 or a[0] > 0:
            emit(22, sido, dist, emd, "사전투표", *a[:5], sigungu=gusigun)
    print(f"  22대 본투표/사전 emit, total rows={len(rows)}")


# ---------- Family B: 20·21대 (시군별) ----------
def conv_bfile(f: Path, dae: int, sido: str):
    raw = pd.read_excel(f, header=None)
    # find header row (col0=='읍면동명')
    hr = None
    for i in range(min(8, len(raw))):
        if ct(raw.iloc[i, 0]) == "읍면동명":
            hr = i; break
    if hr is None:
        return
    cand_row = raw.iloc[hr + 1].tolist()
    cand_cols = [i for i in range(4, len(cand_row)) if ct(cand_row[i]) and ("당" in ct(cand_row[i]) or "무소속" in ct(cand_row[i]))]
    dem_c = next((i for i in cand_cols if party_of(cand_row[i]) == DEM[dae]), None)
    ppp_c = next((i for i in cand_cols if party_of(cand_row[i]) == PPP[dae]), None)
    # district from filename
    stem = f.stem.replace("개표상황(투표구별)_", "")
    district = stem.split("_")[-1] if "_" in stem else stem
    data = raw.iloc[hr + 2:]
    cur_emd = None
    acc = {}
    def flush():
        for emd, d in acc.items():
            if d["v"] > 0 or d["e"] > 0:
                emit(dae, sido, district, emd, "본투표", d["e"], d["v"], d["dem"], d["ppp"], d["o"])
        acc.clear()
    for _, r in data.iterrows():
        c = r.tolist()
        col0, col1 = ct(c[0]), ct(c[1])
        if col0 and col0 not in SPECIAL:
            cur_emd = col0
        electors, votes = ci(c[2]), ci(c[3])
        dem = ci(c[dem_c]) if dem_c is not None else 0
        ppp = ci(c[ppp_c]) if ppp_c is not None else 0
        other = sum(ci(c[i]) for i in cand_cols) - dem - ppp
        label = col1 if col1 else col0
        if col0 in SPECIAL and not col1:  # 선거구 상단 특수행 (거소/관외/국외)
            continue
        if label == "관내사전투표":
            emit(dae, sido, district, cur_emd, "사전투표", electors, votes, dem, ppp, other)
        elif label == "소계":
            continue
        else:  # 투표구 -> 본투표 누적
            a = acc.setdefault(cur_emd, {"e": 0, "v": 0, "dem": 0, "ppp": 0, "o": 0})
            a["e"] += electors; a["v"] += votes; a["dem"] += dem; a["ppp"] += ppp; a["o"] += other
    flush()


def conv_b(dae, base):
    files = sorted(base.glob("**/*.xlsx"))
    sido_map = {}
    for f in files:
        # sido from parent folder name (e.g. '10강원')
        sido = re.sub(r"^[0-9]+", "", f.parent.name)
        conv_bfile(f, dae, sido)
    print(f"  {dae}대 files={len(files)} total rows={len(rows)}")


# ---------- Family C: 19대 (선거구별, col offset +1) ----------
def conv19():
    base = B / "제19대 국회의원선거/제19대 국회의원선거(지역구)"
    files = sorted(base.glob("**/*.xls"))
    for f in files:
        try:
            raw = pd.read_excel(f, sheet_name=0, header=None)
        except Exception:
            continue
        # header row where some col == '읍면동명'
        hr = None; off = 0
        for i in range(min(8, len(raw))):
            rowvals = [ct(x) for x in raw.iloc[i].tolist()]
            if "읍면동명" in rowvals:
                hr = i; off = rowvals.index("읍면동명"); break
        if hr is None:
            continue
        cand_row = raw.iloc[hr + 1].tolist()
        cstart = off + 4
        cand_cols = [i for i in range(cstart, len(cand_row)) if ct(cand_row[i]) and ("당" in ct(cand_row[i]) or "무소속" in ct(cand_row[i]))]
        dem_c = next((i for i in cand_cols if party_of(cand_row[i]) == DEM[19]), None)
        ppp_c = next((i for i in cand_cols if party_of(cand_row[i]) == PPP[19]), None)
        # geography from filename: ..._시도_선거구.xls
        parts = f.stem.split("_")
        sido = parts[1] if len(parts) >= 3 else f.parent.name
        district = parts[-1]
        cur_emd = None; acc = {}
        for _, r in raw.iloc[hr + 2:].iterrows():
            c = r.tolist()
            col_emd, col_gu = ct(c[off]), ct(c[off + 1])
            if col_emd and col_emd not in SPECIAL:
                cur_emd = col_emd
            electors, votes = ci(c[off + 2]), ci(c[off + 3])
            dem = ci(c[dem_c]) if dem_c is not None else 0
            ppp = ci(c[ppp_c]) if ppp_c is not None else 0
            other = sum(ci(c[i]) for i in cand_cols) - dem - ppp
            label = col_gu if col_gu else col_emd
            if col_emd in SPECIAL and not col_gu:
                continue
            if label == "소계":
                continue
            if label in SPECIAL:
                continue
            a = acc.setdefault(cur_emd, {"e": 0, "v": 0, "dem": 0, "ppp": 0, "o": 0})
            a["e"] += electors; a["v"] += votes; a["dem"] += dem; a["ppp"] += ppp; a["o"] += other
        for emd, d in acc.items():
            if d["v"] > 0 or d["e"] > 0:
                emit(19, sido, district, emd, "본투표", d["e"], d["v"], d["dem"], d["ppp"], d["o"])
    print(f"  19대 files={len(files)} total rows={len(rows)}")


# ---------- Family D: 18대 (시도 xls, sheet=선거구) ----------
def conv18():
    base = B / "제18대 국회의원선거/제18대 국회의원선거(지역구)"
    files = sorted(base.glob("*.xls"))
    for f in files:
        sido = f.stem
        xl = pd.ExcelFile(f)
        for sh in xl.sheet_names:
            raw = xl.parse(sh, header=None)
            if ct(raw.iloc[0, 0]) != "읍면동명":
                continue
            party_row = raw.iloc[1].tolist()
            # candidate cols: cols>=4 with a party name, until '계'
            cand_cols = []
            for i in range(4, len(party_row)):
                v = ct(party_row[i])
                if v == "계":
                    break
                if v:
                    cand_cols.append(i)
            dem_c = next((i for i in cand_cols if ct(party_row[i]) == DEM[18]), None)
            ppp_c = next((i for i in cand_cols if ct(party_row[i]) == PPP[18]), None)
            district = sh
            cur_emd = None; acc = {}
            for _, r in raw.iloc[3:].iterrows():
                c = r.tolist()
                col0, col1 = ct(c[0]), ct(c[1])
                if col0 and col0 not in SPECIAL:
                    cur_emd = col0
                electors, votes = ci(c[2]), ci(c[3])
                dem = ci(c[dem_c]) if dem_c is not None else 0
                ppp = ci(c[ppp_c]) if ppp_c is not None else 0
                other = sum(ci(c[i]) for i in cand_cols) - dem - ppp
                label = col1 if col1 else col0
                if col0 in SPECIAL and not col1:
                    continue
                if label == "소계":  # 읍면동 본투표 합 = 소계 사용
                    if cur_emd:
                        emit(18, sido, district, cur_emd, "본투표", electors, votes, dem, ppp, other)
                # 투표구 행은 무시(소계가 본투표 합)
            # (18대는 소계가 읍면동 본투표; 사전 없음)
    print(f"  18대 files={len(files)} total rows={len(rows)}")


if __name__ == "__main__":
    print("converting...")
    conv_b(21, B / "제21대 국회의원선거(재보궐 포함) 투표구별 개표결과/지역구")
    conv_b(20, B / "국회의원선거 개표결과(제20대)/지역구")
    # 20·21대 (시도,읍면동)->구시군 맵 (22대 농촌 통합선거구 분해용)
    tmp = {}
    for r in rows:
        if r["dae"] in (20, 21):
            tmp.setdefault((sido_short(r["sido"]), r["eupmyeondong"]), set()).add(r["sigungu"])
    emd2gu = {k: next(iter(v)) for k, v in tmp.items() if len(v) == 1}  # 유일 매핑만 신뢰
    print(f"  읍면동->구시군 유일맵 크기={len(emd2gu)} (충돌 제외 {sum(1 for v in tmp.values() if len(v)>1)})")
    conv22(emd2gu)
    conv19()
    conv18()
    df = pd.DataFrame(rows)
    df["other"] = df["other"].clip(lower=0)
    # 같은 읍면동이 갑/을 선거구로 쪼개진 경우 합산하여 읍면동 단위로 복원
    before = len(df)
    agg = (df.groupby(["dae", "votetype", "sido", "sigungu", "eupmyeondong"], as_index=False)
             .agg({"district": "first", "electors": "sum", "votes": "sum",
                   "dem": "sum", "ppp": "sum", "other": "sum"}))
    df = agg[["dae", "sido", "sigungu", "district", "eupmyeondong", "votetype",
              "electors", "votes", "dem", "ppp", "other"]]
    print(f"  dedupe(읍면동 합산): {before} -> {len(df)} 행")
    df.to_pickle(OUT / "assembly_rows.pkl")
    df.to_csv(OUT / "assembly_rows.csv", index=False, encoding="utf-8-sig")
    print("\n=== 정리 결과 (행 수) ===")
    print(df.groupby(["dae", "votetype"]).size().to_string())
    print("\nsaved:", OUT / "assembly_rows.pkl")
