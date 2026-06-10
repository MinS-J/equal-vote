"""Observed equal-vote pairs among SGIS edge-adjacent dong boundaries.

The preferred boundary source is local SGIS `bnd_dong_00_YYYY_QQ.zip` files
under inputs/sgis. Each election is matched to the closest available boundary
period. The script falls back to hadmarea_YYYY.geojson only when no dong ZIPs
are available or when explicitly requested.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import tempfile
from collections import Counter
from pathlib import Path

import pandas as pd

from paths import DATA_DIR, INPUTS_DIR, RESULTS_DIR
from simulate_adjacent_pairs import (
    build_adjacent_shape_pairs,
    default_adm_code_file,
    extract_zip,
    field_value,
    find_shapefile,
    geojson_to_shapes_and_records,
    load_adm_code_map,
    load_api_boundaries,
    normalize_key,
    read_dbf,
    read_shp_polygons,
    record_admin_key,
)


SHEET_GOVERNOR = "시·도지사"
PRESIDENTIAL_YEARS = {
    14: 1992,
    15: 1997,
    16: 2002,
    17: 2007,
    18: 2012,
    19: 2017,
    20: 2022,
    21: 2025,
}
PRESIDENTIAL_QUARTERS = {
    14: 4,
    15: 4,
    16: 4,
    17: 4,
    18: 4,
    19: 2,
    20: 1,
    21: 2,
}
ASSEMBLY_YEARS = {
    18: 2008,
    19: 2012,
    20: 2016,
    21: 2020,
    22: 2024,
}
SIDO_CODE_NAMES = {
    "11": "서울특별시",
    "21": "부산광역시",
    "22": "대구광역시",
    "23": "인천광역시",
    "24": "광주광역시",
    "25": "대전광역시",
    "26": "울산광역시",
    "29": "세종특별자치시",
    "31": "경기도",
    "32": "강원특별자치도",
    "33": "충청북도",
    "34": "충청남도",
    "35": "전북특별자치도",
    "36": "전라남도",
    "37": "경상북도",
    "38": "경상남도",
    "39": "제주특별자치도",
}


def quarter_number(label: str) -> int:
    return int(str(label).upper().replace("Q", ""))


def parse_boundary_zip(path: Path) -> dict[str, object] | None:
    match = re.match(r"bnd_dong_00_(\d{4})_([1-4]Q)\.zip$", path.name, re.IGNORECASE)
    if not match:
        return None
    return {
        "source": "dong-zip",
        "year": int(match.group(1)),
        "quarter": match.group(2).upper(),
        "path": path,
    }


def available_dong_boundaries(args) -> list[dict[str, object]]:
    root = Path(args.sgis_dir)
    out = []
    for path in sorted(root.glob("bnd_dong_00_*.zip")):
        parsed = parse_boundary_zip(path)
        if parsed:
            out.append(parsed)
    return out


def choose_closest_boundary(entry, args) -> dict[str, object]:
    if args.boundary_source in {"auto", "dong-zip"}:
        candidates = available_dong_boundaries(args)
        if candidates:
            target_year = int(args.fixed_boundary_year) if args.boundary_mode == "fixed" else int(entry["election_year"])
            target_quarter = int(entry.get("election_quarter", 2))
            if args.boundary_mode == "fixed":
                exact = [c for c in candidates if c["year"] == target_year]
                if not exact:
                    raise FileNotFoundError(f"No bnd_dong_00_{target_year}_*.zip under {args.sgis_dir}")
                candidates = exact
            return min(
                candidates,
                key=lambda c: (
                    abs(int(c["year"]) - target_year),
                    abs(quarter_number(str(c["quarter"])) - target_quarter),
                    int(c["year"]) > target_year,
                ),
            )
        if args.boundary_source == "dong-zip":
            raise FileNotFoundError(f"No bnd_dong_00_*.zip files under {args.sgis_dir}")

    year = int(args.fixed_boundary_year) if args.boundary_mode == "fixed" else int(entry["election_year"])
    return {
        "source": "geojson",
        "year": year,
        "quarter": "",
        "path": boundary_cache_path(year, args),
    }


def boundary_cache_path(year: int, args) -> Path:
    return Path(args.boundary_cache_template.format(year=year))


def make_boundary_args(args):
    return argparse.Namespace(
        adm_code_file=args.adm_code_file,
        adm_code_sheet=args.adm_code_sheet,
        full_name_field="",
        sido_field="",
        sigungu_field="",
        emd_field="",
    )


def make_api_args(year: int, cache_path: Path, args):
    return argparse.Namespace(
        adm_code_file=args.adm_code_file,
        adm_code_sheet=args.adm_code_sheet,
        api_cache=str(cache_path),
        api_year=str(year),
        api_low_search=args.api_low_search,
        api_base_url=args.api_base_url,
        api_access_token=args.api_access_token,
        api_consumer_key=args.api_consumer_key,
        api_consumer_secret=args.api_consumer_secret,
        api_sigungu_codes=args.api_sigungu_codes,
        api_sleep=args.api_sleep,
        api_strict=args.api_strict,
    )


def sigungu_zip_for(dong_zip: Path) -> Path | None:
    candidate = dong_zip.with_name(dong_zip.name.replace("bnd_dong_00_", "bnd_sigungu_00_"))
    return candidate if candidate.exists() else None


def detect_dbf_encoding(root: Path, default: str) -> str:
    cpg_files = sorted(root.rglob("*.cpg"))
    if not cpg_files:
        return default
    label = cpg_files[0].read_text(encoding="ascii", errors="ignore").strip().lower()
    if label in {"utf8", "utf-8", "65001"}:
        return "utf-8"
    if label in {"949", "cp949", "ms949"}:
        return "cp949"
    if label in {"euc-kr", "euckr", "ks_c_5601-1987"}:
        return "euc-kr"
    return default


def load_sigungu_code_map(dong_zip: Path, encoding: str) -> dict[str, tuple[str, str]]:
    sigungu_zip = sigungu_zip_for(dong_zip)
    if sigungu_zip is None:
        return {}
    with tempfile.TemporaryDirectory() as temp:
        root = extract_zip(sigungu_zip, Path(temp))
        _, dbf_path = find_shapefile(root)
        records = read_dbf(dbf_path, detect_dbf_encoding(root, encoding))
    out = {}
    for record in records:
        code = field_value(record, ["SIGUNGU_CD", "sigungu_cd", "SGG_CD", "sgg_cd"])
        name = field_value(record, ["SIGUNGU_NM", "sigungu_nm", "SGG_NM", "sgg_nm"])
        digits = "".join(ch for ch in str(code).split(".")[0] if ch.isdigit())
        if len(digits) >= 5 and name:
            out[digits[:5]] = (SIDO_CODE_NAMES.get(digits[:2], ""), name)
    return out


def dong_record_key(record: dict[str, object], sigungu_map, adm_code_map, boundary_args):
    code = field_value(record, ["ADM_CD", "adm_cd", "ADM_DR_CD", "adm_dr_cd", "HJD_CD", "hjd_cd"])
    name = field_value(record, ["ADM_NM", "adm_nm", "ADM_DR_NM", "adm_dr_nm", "DONG_NM", "dong_nm"])
    digits = "".join(ch for ch in str(code).split(".")[0] if ch.isdigit())
    if len(digits) >= 5 and name:
        sigungu = sigungu_map.get(digits[:5])
        if sigungu and sigungu[0]:
            return normalize_key(sigungu[0], sigungu[1], name)
    return record_admin_key(record, boundary_args, adm_code_map)


def load_dong_zip_boundary(spec, args):
    zip_path = Path(spec["path"])
    boundary_args = make_boundary_args(args)
    adm_code_file = Path(args.adm_code_file) if args.adm_code_file else default_adm_code_file(boundary_args)
    adm_code_map = load_adm_code_map(adm_code_file, args.adm_code_sheet)
    sigungu_map = load_sigungu_code_map(zip_path, args.dbf_encoding)

    with tempfile.TemporaryDirectory() as temp:
        root = extract_zip(zip_path, Path(temp))
        shp_path, dbf_path = find_shapefile(root)
        records = read_dbf(dbf_path, detect_dbf_encoding(root, args.dbf_encoding))
        shapes = read_shp_polygons(shp_path)

    if len(records) != len(shapes):
        raise ValueError(f"SHP/DBF record count mismatch for {zip_path}: {len(shapes)} vs {len(records)}")

    shape_keys = [
        dong_record_key(record, sigungu_map, adm_code_map, boundary_args)
        for record in records
    ]
    return {
        "year": int(spec["year"]),
        "quarter": str(spec["quarter"]),
        "source": "dong-zip",
        "path": str(zip_path),
        "record_count": len(records),
        "shape_keys": shape_keys,
        "raw_edge_pairs": build_adjacent_shape_pairs(shapes, args.coord_precision),
    }


def load_geojson_boundary(spec, args):
    year = int(spec["year"])
    cache_path = Path(spec["path"])
    if not cache_path.exists():
        if not args.fetch_missing:
            raise FileNotFoundError(
                f"SGIS boundary cache not found for {year}: {cache_path}\n"
                "Run again with --fetch-missing from a PowerShell session that has SGIS credentials, "
                "or provide bnd_dong_00_*.zip files."
            )
        load_api_boundaries(make_api_args(year, cache_path, args))

    feature_collection = json.loads(cache_path.read_text(encoding="utf-8"))
    records, shapes = geojson_to_shapes_and_records(feature_collection)
    boundary_args = make_boundary_args(args)
    adm_code_file = Path(args.adm_code_file) if args.adm_code_file else default_adm_code_file(boundary_args)
    adm_code_map = load_adm_code_map(adm_code_file, args.adm_code_sheet)

    return {
        "year": year,
        "quarter": "",
        "source": "geojson",
        "path": str(cache_path),
        "record_count": len(records),
        "shape_keys": [record_admin_key(record, boundary_args, adm_code_map) for record in records],
        "raw_edge_pairs": build_adjacent_shape_pairs(shapes, args.coord_precision),
    }


def load_boundary(spec, args):
    if spec["source"] == "dong-zip":
        return load_dong_zip_boundary(spec, args)
    return load_geojson_boundary(spec, args)


def normalized_rows() -> list[dict[str, object]]:
    out: list[dict[str, object]] = []

    pres = pd.read_pickle(DATA_DIR / "pres_rows.pkl")
    for (dae, votetype), group in pres.groupby(["dae", "votetype"], sort=True):
        dae_int = int(dae)
        df = group[["sido", "sigungu", "eupmyeondong", "dem", "ppp"]].copy()
        df["vote_a"] = df["dem"].astype(int)
        df["vote_b"] = df["ppp"].astype(int)
        out.append(
            {
                "dataset": f"대선 {dae_int}대·{votetype}",
                "kind": "대선",
                "election_year": PRESIDENTIAL_YEARS[dae_int],
                "election_quarter": PRESIDENTIAL_QUARTERS[dae_int],
                "df": df,
            }
        )

    assembly = pd.read_pickle(DATA_DIR / "assembly_rows.pkl")
    for (dae, votetype), group in assembly.groupby(["dae", "votetype"], sort=True):
        dae_int = int(dae)
        df = group[["sido", "sigungu", "eupmyeondong", "dem", "ppp"]].copy()
        df["vote_a"] = df["dem"].astype(int)
        df["vote_b"] = df["ppp"].astype(int)
        out.append(
            {
                "dataset": f"총선 {dae_int}대·{votetype}",
                "kind": "총선",
                "election_year": ASSEMBLY_YEARS[dae_int],
                "election_quarter": 2,
                "df": df,
            }
        )

    for year, label in [(2022, "지선8회(2022)"), (2026, "지선9회(2026)")]:
        local = pd.read_pickle(DATA_DIR / f"nec_{year}_regular_rows.pkl")
        local = local[local["sheet"] == SHEET_GOVERNOR].copy()
        local = local.rename(
            columns={
                "sido_or_district": "sido",
                "candidate_1": "vote_a",
                "candidate_2": "vote_b",
            }
        )
        for votetype, gubun in [("본투표", "선거일투표"), ("사전투표", "관내사전투표")]:
            group = local[local["gubun"] == gubun].copy()
            df = group[["sido", "sigungu", "eupmyeondong", "vote_a", "vote_b"]].copy()
            df["vote_a"] = df["vote_a"].astype(int)
            df["vote_b"] = df["vote_b"].astype(int)
            out.append(
                {
                    "dataset": f"{label}·{votetype}",
                    "kind": "지선",
                    "election_year": year,
                    "election_quarter": 2,
                    "df": df,
                }
            )

    return out


def region_text(row) -> str:
    return f"{row['sido']} {row['sigungu']} {row['eupmyeondong']}"


def build_election_mapping(df: pd.DataFrame):
    keys = [
        normalize_key(row["sido"], row["sigungu"], row["eupmyeondong"])
        for _, row in df.iterrows()
    ]
    counts = Counter(keys)
    key_to_index = {key: idx for idx, key in enumerate(keys) if counts[key] == 1}
    duplicate_rows = sum(count for count in counts.values() if count > 1)
    return key_to_index, duplicate_rows


def matched_pairs_for_dataset(df: pd.DataFrame, boundary):
    key_to_index, duplicate_rows = build_election_mapping(df)
    shape_to_row = {}
    for shape_index, key in enumerate(boundary["shape_keys"]):
        if key in key_to_index:
            shape_to_row[shape_index] = key_to_index[key]

    all_pairs = set()
    same_sigungu_pairs = set()
    for a, b in boundary["raw_edge_pairs"]:
        if a not in shape_to_row or b not in shape_to_row:
            continue
        ia, ib = shape_to_row[a], shape_to_row[b]
        if ia == ib:
            continue
        pair = tuple(sorted((ia, ib)))
        all_pairs.add(pair)
        ra = df.iloc[ia]
        rb = df.iloc[ib]
        if normalize_key(ra["sido"], ra["sigungu"], "")[:2] == normalize_key(rb["sido"], rb["sigungu"], "")[:2]:
            same_sigungu_pairs.add(pair)

    return shape_to_row, all_pairs, same_sigungu_pairs, duplicate_rows


def count_equal_pairs(df: pd.DataFrame, pairs, strict: bool):
    rows = []
    for ia, ib in sorted(pairs):
        a = df.iloc[ia]
        b = df.iloc[ib]
        va = int(a["vote_a"])
        vb = int(a["vote_b"])
        if strict and (va <= 0 or vb <= 0):
            continue
        if not strict and va == 0 and vb == 0:
            continue
        if va == int(b["vote_a"]) and vb == int(b["vote_b"]):
            rows.append((ia, ib, va, vb))
    return rows


def analyze_dataset(entry, boundary):
    work = entry["df"].reset_index(drop=True)
    shape_to_row, all_pairs, same_sigungu_pairs, duplicate_rows = matched_pairs_for_dataset(
        work,
        boundary,
    )
    strict_all = count_equal_pairs(work, all_pairs, strict=True)
    strict_same = count_equal_pairs(work, same_sigungu_pairs, strict=True)
    loose_all = count_equal_pairs(work, all_pairs, strict=False)
    loose_same = count_equal_pairs(work, same_sigungu_pairs, strict=False)

    matched_rows = len(set(shape_to_row.values()))
    summary = {
        "dataset": entry["dataset"],
        "kind": entry["kind"],
        "election_year": int(entry["election_year"]),
        "boundary_year": int(boundary["year"]),
        "boundary_quarter": boundary["quarter"],
        "boundary_source": boundary["source"],
        "rows": int(len(work)),
        "matched_rows": int(matched_rows),
        "match_rate": round(matched_rows / len(work), 6) if len(work) else 0,
        "duplicate_key_rows": int(duplicate_rows),
        "edge_pairs_all": int(len(all_pairs)),
        "edge_pairs_same_sigungu": int(len(same_sigungu_pairs)),
        "equal_edge_all": int(len(strict_all)),
        "equal_edge_same_sigungu": int(len(strict_same)),
        "equal_edge_all_loose": int(len(loose_all)),
        "equal_edge_same_sigungu_loose": int(len(loose_same)),
        "boundary_file": boundary["path"],
    }

    details = []
    for scope, pairs in [("전국 경계인접", strict_all), ("같은 시군구 경계인접", strict_same)]:
        for ia, ib, va, vb in pairs:
            a = work.iloc[ia]
            b = work.iloc[ib]
            details.append(
                {
                    "dataset": entry["dataset"],
                    "kind": entry["kind"],
                    "election_year": int(entry["election_year"]),
                    "boundary_year": int(boundary["year"]),
                    "boundary_quarter": boundary["quarter"],
                    "scope": scope,
                    "vote_a": va,
                    "vote_b": vb,
                    "region1": region_text(a),
                    "region2": region_text(b),
                }
            )

    return summary, details


def resolve_boundary_spec(entry, args) -> dict[str, object]:
    return choose_closest_boundary(entry, args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary-mode", choices=["matched-year", "fixed"], default="matched-year")
    parser.add_argument("--boundary-source", choices=["auto", "dong-zip", "geojson"], default="auto")
    parser.add_argument("--fixed-boundary-year", type=int, default=2025)
    parser.add_argument("--sgis-dir", default=str(INPUTS_DIR / "sgis"))
    parser.add_argument(
        "--boundary-cache-template",
        default=str(INPUTS_DIR / "sgis" / "hadmarea_{year}.geojson"),
    )
    parser.add_argument("--fetch-missing", action="store_true")
    parser.add_argument("--adm-code-file", default="")
    parser.add_argument("--adm-code-sheet", default="")
    parser.add_argument("--dbf-encoding", default="cp949")
    parser.add_argument("--coord-precision", type=int, default=3)
    parser.add_argument("--api-base-url", default="https://sgisapi.mods.go.kr/OpenAPI3")
    parser.add_argument("--api-low-search", default="1")
    parser.add_argument("--api-access-token", default="")
    parser.add_argument("--api-consumer-key", default="")
    parser.add_argument("--api-consumer-secret", default="")
    parser.add_argument("--api-sigungu-codes", default="")
    parser.add_argument("--api-sleep", type=float, default=0.05)
    parser.add_argument("--api-strict", action="store_true")
    args = parser.parse_args()

    entries = normalized_rows()
    specs_by_key = {}
    boundary_cache = {}
    summaries = []
    details = []
    for entry in entries:
        spec = resolve_boundary_spec(entry, args)
        key = (spec["source"], spec["year"], spec.get("quarter", ""), str(spec["path"]))
        specs_by_key[key] = spec
        if key not in boundary_cache:
            boundary_cache[key] = load_boundary(spec, args)
        summary, dataset_details = analyze_dataset(entry, boundary_cache[key])
        summaries.append(summary)
        details.extend(dataset_details)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    source = "dong_zip" if any(key[0] == "dong-zip" for key in specs_by_key) else "geojson"
    suffix = (
        f"{source}_matched_year"
        if args.boundary_mode == "matched-year"
        else f"{source}_fixed_{args.fixed_boundary_year}"
    )
    counts_path = RESULTS_DIR / f"geo_adjacent_observed_counts_{suffix}.csv"
    detail_path = RESULTS_DIR / f"geo_adjacent_observed_details_{suffix}.csv"
    pd.DataFrame(summaries).to_csv(counts_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(details).to_csv(detail_path, index=False, encoding="utf-8-sig")

    print(pd.DataFrame(summaries).to_string(index=False))
    print(f"saved={counts_path}")
    print(f"saved={detail_path}")


if __name__ == "__main__":
    main()
