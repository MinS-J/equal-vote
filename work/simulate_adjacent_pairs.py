"""Same-sigungu adjacent eupmyeondong equal-vote simulation.

This script expects an SGIS census administrative boundary SHP for eupmyeondong
or administrative-dong polygons. It builds edge-sharing adjacent pairs within
the same sigungu, matches them to the 2026 election rows, and reuses the
existing posterior predictive model to estimate how often the observed number
of equal-vote adjacent pairs is regenerated.

No geospatial dependency is required. The SHP/DBF readers below intentionally
cover only the polygon and text/numeric DBF subset needed for SGIS boundary
files.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import struct
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np

from paths import INPUTS_DIR, RESULTS_DIR
from simulate_equal_candidate_pairs import (
    apply_previous_turnout_prior,
    build_group_probabilities,
    build_row_centered_parameters,
    build_row_shrink_parameters,
    build_turnout_probabilities,
    group_by_scope,
)
from simulate_joint_events import draw_sample, load_dataframe


SIDO_ALIASES = {
    "서울": "서울특별시",
    "부산": "부산광역시",
    "대구": "대구광역시",
    "인천": "인천광역시",
    "광주": "광주광역시",
    "대전": "대전광역시",
    "울산": "울산광역시",
    "세종": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도",
    "강원도": "강원특별자치도",
    "충북": "충청북도",
    "충남": "충청남도",
    "전북": "전북특별자치도",
    "전라북도": "전북특별자치도",
    "전남": "전라남도",
    "경북": "경상북도",
    "경남": "경상남도",
    "제주": "제주특별자치도",
}


def norm_text(value) -> str:
    text = "" if value is None else str(value)
    return "".join(text.split())


def norm_sido(value) -> str:
    text = norm_text(value)
    return SIDO_ALIASES.get(text, text)


def norm_emd(value) -> str:
    text = norm_text(value)
    return re.sub(r"(?<!홍)(?<!거)제(?=[0-9])", "", text)


def normalize_key(sido: str, sigungu: str, emd: str) -> tuple[str, str, str]:
    sido_norm = norm_sido(sido)
    sigungu_norm = norm_text(sigungu)
    if sido_norm == "세종특별자치시" and not sigungu_norm:
        sigungu_norm = "세종특별자치시"
    return sido_norm, sigungu_norm, norm_emd(emd)


def decode_bytes(raw: bytes, encoding: str) -> str:
    raw = raw.rstrip(b"\x00 ")
    if not raw:
        return ""
    for enc in (encoding, "cp949", "utf-8", "euc-kr"):
        try:
            return raw.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode(encoding, errors="replace").strip()


def read_dbf(path: Path, encoding: str) -> list[dict[str, object]]:
    data = path.read_bytes()
    if len(data) < 32:
        raise ValueError(f"DBF header too short: {path}")

    record_count = struct.unpack("<I", data[4:8])[0]
    header_len = struct.unpack("<H", data[8:10])[0]
    record_len = struct.unpack("<H", data[10:12])[0]

    fields = []
    pos = 32
    while pos < header_len and data[pos] != 0x0D:
        desc = data[pos : pos + 32]
        name = desc[:11].split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
        field_type = chr(desc[11])
        length = desc[16]
        decimals = desc[17]
        fields.append((name, field_type, length, decimals))
        pos += 32

    records = []
    rec_pos = header_len
    for _ in range(record_count):
        record = data[rec_pos : rec_pos + record_len]
        rec_pos += record_len
        if not record or record[0:1] == b"*":
            continue
        offset = 1
        parsed = {}
        for name, field_type, length, decimals in fields:
            raw = record[offset : offset + length]
            offset += length
            text = decode_bytes(raw, encoding)
            if field_type in {"N", "F"} and text:
                try:
                    parsed[name] = float(text) if decimals else int(text)
                except ValueError:
                    parsed[name] = text
            else:
                parsed[name] = text
        records.append(parsed)
    return records


def read_shp_polygons(path: Path) -> list[list[list[tuple[float, float]]]]:
    data = path.read_bytes()
    if len(data) < 100:
        raise ValueError(f"SHP header too short: {path}")

    shapes: list[list[list[tuple[float, float]]]] = []
    pos = 100
    while pos + 8 <= len(data):
        _, content_words = struct.unpack(">2i", data[pos : pos + 8])
        pos += 8
        content_len = content_words * 2
        content = data[pos : pos + content_len]
        pos += content_len
        if len(content) < 4:
            continue
        shape_type = struct.unpack("<i", content[:4])[0]
        if shape_type == 0:
            shapes.append([])
            continue
        if shape_type not in {5, 15, 25, 31}:
            raise ValueError(f"Unsupported shape type {shape_type}; expected polygon SHP.")
        if len(content) < 44:
            shapes.append([])
            continue

        num_parts, num_points = struct.unpack("<2i", content[36:44])
        parts_start = 44
        points_start = parts_start + 4 * num_parts
        parts = list(struct.unpack(f"<{num_parts}i", content[parts_start:points_start]))
        point_bytes = content[points_start : points_start + 16 * num_points]
        points = [
            struct.unpack("<2d", point_bytes[i * 16 : i * 16 + 16])
            for i in range(num_points)
        ]
        rings = []
        for part_index, start in enumerate(parts):
            end = parts[part_index + 1] if part_index + 1 < len(parts) else num_points
            ring = points[start:end]
            if len(ring) >= 2:
                rings.append(ring)
        shapes.append(rings)
    return shapes


def find_shapefile(path: Path) -> tuple[Path, Path]:
    if path.is_dir():
        shp_files = sorted(path.rglob("*.shp"))
    else:
        shp_files = [path] if path.suffix.lower() == ".shp" else []
    if not shp_files:
        raise FileNotFoundError(f"No .shp found under {path}")
    shp = shp_files[0]
    dbf = shp.with_suffix(".dbf")
    if not dbf.exists():
        raise FileNotFoundError(f"Matching .dbf not found for {shp}")
    return shp, dbf


def extract_zip(zip_path: Path, target: Path) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(target)
    return target


def field_value(record: dict[str, object], candidates: list[str]) -> str:
    lower_map = {key.lower(): key for key in record}
    for candidate in candidates:
        key = lower_map.get(candidate.lower())
        if key is not None:
            value = record.get(key)
            if value not in {None, ""}:
                return str(value)
    return ""


def parse_full_name(full_name: str) -> tuple[str, str, str] | None:
    parts = [p for p in str(full_name).replace(",", " ").split() if p]
    if len(parts) < 2:
        return None
    if parts[0].startswith("세종특별자치시") and len(parts) >= 2:
        return parts[0], "세종특별자치시", parts[-1]
    if len(parts) >= 3:
        return parts[0], "".join(parts[1:-1]), parts[-1]
    return None


def read_adm_code_rows(path: Path, sheet: str | None) -> list[dict[str, str]]:
    import pandas as pd

    sheet_name = 0 if not sheet else sheet
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=str)
    if raw.shape[0] < 2 or raw.shape[1] < 6:
        raise ValueError(f"Unexpected adm_code.xls layout: {path}")

    df = raw.iloc[1:].copy()
    df.columns = ["sido_code", "sido_name", "sigungu_code", "sigungu_name", "emd_code", "emd_name"] + [
        f"extra_{i}" for i in range(max(0, raw.shape[1] - 6))
    ]

    rows = []
    for _, row in df.iterrows():
        if not row.get("sido_code") or row.get("sido_code") == "시도코드":
            continue
        rows.append(
            {
                "sido_code": str(row["sido_code"]).split(".")[0].zfill(2),
                "sido_name": str(row["sido_name"]),
                "sigungu_code": str(row["sigungu_code"]).split(".")[0].zfill(3),
                "sigungu_name": str(row["sigungu_name"]),
                "emd_code": str(row["emd_code"]).split(".")[0].zfill(3),
                "emd_name": str(row["emd_name"]),
            }
        )
    return rows


def load_adm_code_map(path: Path | None, sheet: str | None) -> dict[str, tuple[str, str, str]]:
    if path is None or not path.exists():
        return {}

    out = {}
    for row in read_adm_code_rows(path, sheet):
        sido_code = row["sido_code"]
        sigungu_code = row["sigungu_code"]
        emd_code = row["emd_code"]
        key = normalize_key(row["sido_name"], row["sigungu_name"], row["emd_name"])
        code8 = f"{sido_code}{sigungu_code}{emd_code}"
        out[code8] = key
        out[code8.rstrip("0")] = key
    return out


def record_admin_key(
    record: dict[str, object],
    args,
    adm_code_map: dict[str, tuple[str, str, str]],
) -> tuple[str, str, str] | None:
    if args.full_name_field:
        parsed = parse_full_name(str(record.get(args.full_name_field, "")))
        if parsed:
            return normalize_key(*parsed)

    if args.sido_field and args.sigungu_field and args.emd_field:
        return normalize_key(
            record.get(args.sido_field, ""),
            record.get(args.sigungu_field, ""),
            record.get(args.emd_field, ""),
        )

    full_candidates = [
        "ADM_NM",
        "ADM_DR_NM",
        "adm_nm",
        "adm_dr_nm",
        "FULL_NM",
        "full_nm",
        "HJD_NM",
        "hjd_nm",
    ]
    full = field_value(record, full_candidates)
    parsed = parse_full_name(full)
    if parsed:
        return normalize_key(*parsed)

    code = field_value(record, ["ADM_CD", "adm_cd", "ADM_DR_CD", "adm_dr_cd", "HJD_CD", "hjd_cd"])
    if code:
        code_norm = str(code).split(".")[0]
        if code_norm in adm_code_map:
            return adm_code_map[code_norm]
        code_digits = "".join(ch for ch in code_norm if ch.isdigit())
        if code_digits in adm_code_map:
            return adm_code_map[code_digits]

    sido = field_value(record, ["SIDO_NM", "sido_nm", "CTP_KOR_NM", "ctp_kor_nm", "SIDO"])
    sigungu = field_value(record, ["SIGUNGU_NM", "sigungu_nm", "SGG_NM", "sgg_nm", "SIG_KOR_NM"])
    emd = field_value(record, ["EMD_NM", "emd_nm", "DONG_NM", "dong_nm", "ADM_DR_NM", "adm_dr_nm"])
    if sido and emd:
        return normalize_key(sido, sigungu, emd)

    return None


def point_key(point: tuple[float, float], precision: int) -> tuple[float, float]:
    return round(point[0], precision), round(point[1], precision)


def polygon_edges(rings: list[list[tuple[float, float]]], precision: int):
    edges = set()
    for ring in rings:
        if len(ring) < 2:
            continue
        for a, b in zip(ring, ring[1:]):
            pa = point_key(a, precision)
            pb = point_key(b, precision)
            if pa == pb:
                continue
            edge = (pa, pb) if pa <= pb else (pb, pa)
            edges.add(edge)
    return edges


def build_adjacent_shape_pairs(shapes, precision: int) -> set[tuple[int, int]]:
    edge_to_shapes: dict[tuple[tuple[float, float], tuple[float, float]], list[int]] = defaultdict(list)
    for shape_index, rings in enumerate(shapes):
        for edge in polygon_edges(rings, precision):
            edge_to_shapes[edge].append(shape_index)

    pairs: set[tuple[int, int]] = set()
    for owners in edge_to_shapes.values():
        if len(owners) >= 2:
            for a, b in combinations(sorted(set(owners)), 2):
                pairs.add((a, b))
    return pairs


def count_explicit_equal_pairs(candidate_1: np.ndarray, candidate_2: np.ndarray, pairs) -> int:
    total = 0
    for i, j in pairs:
        if candidate_1[i] == candidate_1[j] and candidate_2[i] == candidate_2[j]:
            total += 1
    return total


def pair_details(df, pairs):
    rows = []
    for i, j in pairs:
        a = df.loc[i]
        b = df.loc[j]
        if int(a["candidate_1"]) == int(b["candidate_1"]) and int(a["candidate_2"]) == int(b["candidate_2"]):
            rows.append(
                {
                    "region1": f"{a['sido_or_district']} {a['sigungu']} {a['eupmyeondong']}",
                    "region2": f"{b['sido_or_district']} {b['sigungu']} {b['eupmyeondong']}",
                    "candidate_1": int(a["candidate_1"]),
                    "candidate_2": int(a["candidate_2"]),
                }
            )
    return rows


def percentile(values: np.ndarray, q: float) -> float:
    return float(np.percentile(values, q))


def geojson_to_shapes_and_records(payload: dict) -> tuple[list[dict[str, object]], list[list[list[tuple[float, float]]]]]:
    features = payload.get("features", [])
    records = []
    shapes = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        geom_type = geometry.get("type")
        coordinates = geometry.get("coordinates") or []
        rings = []
        if geom_type == "Polygon":
            rings.extend([[tuple(point[:2]) for point in ring] for ring in coordinates])
        elif geom_type == "MultiPolygon":
            for polygon in coordinates:
                rings.extend([[tuple(point[:2]) for point in ring] for ring in polygon])
        else:
            continue
        records.append(feature.get("properties") or {})
        shapes.append(rings)
    return records, shapes


def request_json(url: str, params: dict[str, object]) -> dict:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in {None, ""}})
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={
            "User-Agent": "equal-vote-adjacent-analysis/1.0",
            "Accept": "application/json, application/geo+json, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def get_sgis_access_token(args) -> str:
    access_token = args.api_access_token or os.environ.get("SGIS_ACCESS_TOKEN", "")
    if access_token:
        return access_token

    consumer_key = args.api_consumer_key or os.environ.get("SGIS_CONSUMER_KEY", "")
    consumer_secret = args.api_consumer_secret or os.environ.get("SGIS_CONSUMER_SECRET", "")
    if not consumer_key or not consumer_secret:
        return ""
    auth_url = args.api_base_url.rstrip("/") + "/auth/authentication.json"
    payload = request_json(
        auth_url,
        {
            "consumer_key": consumer_key,
            "consumer_secret": consumer_secret,
        },
    )
    result = payload.get("result") or payload
    return result.get("accessToken") or result.get("access_token") or ""


def api_sigungu_codes(args) -> list[str]:
    if args.api_sigungu_codes:
        return [code.strip() for code in args.api_sigungu_codes.split(",") if code.strip()]
    adm_code_file = Path(args.adm_code_file) if args.adm_code_file else INPUTS_DIR / "sgis" / "adm_code.xls"
    if not adm_code_file.exists():
        raise FileNotFoundError(
            "--api-source requires --adm-code-file or --api-sigungu-codes. "
            f"Checked adm_code_file={adm_code_file}"
        )
    rows = read_adm_code_rows(adm_code_file, args.adm_code_sheet)
    codes = {f"{row['sido_code']}{row['sigungu_code']}" for row in rows}
    return sorted(codes)


def default_adm_code_file(args) -> Path | None:
    if args.adm_code_file:
        return Path(args.adm_code_file)
    default_path = INPUTS_DIR / "sgis" / "adm_code.xls"
    return default_path if default_path.exists() else None


def load_api_boundaries(args) -> tuple[list[dict[str, object]], list[list[list[tuple[float, float]]]], str]:
    if args.api_cache and Path(args.api_cache).exists():
        payload = json.loads(Path(args.api_cache).read_text(encoding="utf-8"))
        metadata = payload.get("metadata", {})
        cache_year = str(metadata.get("year", ""))
        cache_low_search = str(metadata.get("low_search", ""))
        if cache_year == str(args.api_year) and cache_low_search == str(args.api_low_search):
            records, shapes = geojson_to_shapes_and_records(payload)
            return records, shapes, str(Path(args.api_cache))
        print(
            "warning: SGIS API cache year/low_search does not match request; refetching "
            f"(cache year={cache_year or 'unknown'}, low_search={cache_low_search or 'unknown'})",
            file=sys.stderr,
        )

    access_token = get_sgis_access_token(args)
    endpoint = args.api_base_url.rstrip("/") + "/boundary/hadmarea.geojson"
    all_features = []
    skipped_codes = []
    codes = api_sigungu_codes(args)
    for index, adm_cd in enumerate(codes, start=1):
        params = {
            "adm_cd": adm_cd,
            "year": args.api_year,
            "low_search": args.api_low_search,
        }
        if access_token:
            params["accessToken"] = access_token
        payload = request_json(endpoint, params)
        err_cd = str(payload.get("errCd", "0"))
        if err_cd not in {"0", "None"}:
            if err_cd == "-100" and not args.api_strict:
                skipped_codes.append(
                    {
                        "adm_cd": adm_cd,
                        "errCd": payload.get("errCd"),
                        "errMsg": payload.get("errMsg", ""),
                    }
                )
                print(
                    f"warning: SGIS boundary not found for adm_cd={adm_cd}; skipped",
                    file=sys.stderr,
                )
                continue
            raise RuntimeError(f"SGIS API failed for adm_cd={adm_cd}: {payload}")
        all_features.extend(payload.get("features", []))
        if args.api_sleep and index < len(codes):
            time.sleep(args.api_sleep)

    feature_collection = {
        "type": "FeatureCollection",
        "features": all_features,
        "metadata": {
            "source": endpoint,
            "year": args.api_year,
            "low_search": args.api_low_search,
            "requested_api_codes": len(codes),
            "skipped_api_codes": skipped_codes,
            "returned_feature_count": len(all_features),
        },
    }
    if args.api_cache:
        cache = Path(args.api_cache)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(feature_collection, ensure_ascii=False), encoding="utf-8")
    records, shapes = geojson_to_shapes_and_records(feature_collection)
    return records, shapes, endpoint


def load_boundary_records_and_shapes(args, boundary: Path):
    if args.api_source:
        return load_api_boundaries(args)

    if boundary.suffix.lower() in {".json", ".geojson"}:
        payload = json.loads(boundary.read_text(encoding="utf-8"))
        records, shapes = geojson_to_shapes_and_records(payload)
        return records, shapes, str(boundary)

    shp_path, dbf_path = find_shapefile(boundary)
    records = read_dbf(dbf_path, args.dbf_encoding)
    shapes = read_shp_polygons(shp_path)
    if len(records) != len(shapes):
        raise ValueError(f"SHP/DBF record count mismatch: {len(shapes)} vs {len(records)}")
    return records, shapes, f"{shp_path}|{dbf_path}"


def run(args, boundary_root: Path):
    records, shapes, boundary_source = load_boundary_records_and_shapes(args, boundary_root)
    adm_code_map = load_adm_code_map(default_adm_code_file(args), args.adm_code_sheet)

    df, election_source = load_dataframe(args.dataset, args.sheet, args.rows, args.min_n)
    election_keys = {}
    duplicates = []
    for idx, row in df.iterrows():
        key = normalize_key(row["sido_or_district"], row["sigungu"], row["eupmyeondong"])
        if key in election_keys:
            duplicates.append(key)
        election_keys[key] = int(idx)

    shape_to_election = {}
    parsed_keys = []
    for shape_index, record in enumerate(records):
        key = record_admin_key(record, args, adm_code_map)
        parsed_keys.append(key)
        if key in election_keys:
            shape_to_election[shape_index] = election_keys[key]

    raw_adjacent_pairs = build_adjacent_shape_pairs(shapes, args.coord_precision)
    adjacent_pairs = set()
    skipped_not_matched = 0
    skipped_cross_sigungu = 0
    for a, b in raw_adjacent_pairs:
        if a not in shape_to_election or b not in shape_to_election:
            skipped_not_matched += 1
            continue
        ia = shape_to_election[a]
        ib = shape_to_election[b]
        ra = df.loc[ia]
        rb = df.loc[ib]
        if (ra["sido_or_district"], ra["sigungu"]) != (rb["sido_or_district"], rb["sigungu"]):
            skipped_cross_sigungu += 1
            continue
        adjacent_pairs.add(tuple(sorted((ia, ib))))

    c1 = df["candidate_1"].to_numpy(dtype=np.int64)
    c2 = df["candidate_2"].to_numpy(dtype=np.int64)
    observed_count = count_explicit_equal_pairs(c1, c2, sorted(adjacent_pairs))
    threshold = observed_count if args.threshold == "observed" else int(args.threshold)
    if threshold <= 0:
        threshold = 1

    model_groups = group_by_scope(df, args.model_scope)
    probs = build_group_probabilities(df, model_groups, args.alpha)
    turnout_probs = build_turnout_probabilities(df, model_groups, args.alpha)
    if args.prob_model == "row_shrink":
        row_params = build_row_shrink_parameters(
            df,
            model_groups,
            probs,
            turnout_probs,
            args.q_prior_weight,
            args.p_prior_weight,
            args.alpha,
        )
    else:
        row_params = build_row_centered_parameters(df, args.alpha, args.kappa, args.tau)
    if args.turnout_prior == "previous_2022":
        row_params = apply_previous_turnout_prior(df, row_params, args.alpha)

    rng = np.random.default_rng(args.seed)
    counts = np.empty(args.iters, dtype=np.int64)
    pair_list = sorted(adjacent_pairs)
    for t in range(args.iters):
        sim_a, sim_b, _ = draw_sample(
            rng,
            df,
            model_groups,
            probs,
            turnout_probs,
            args.prob_model,
            row_params,
            args.randomize_n,
        )
        counts[t] = count_explicit_equal_pairs(sim_a, sim_b, pair_list)

    unmatched_election = sorted(set(election_keys) - {parsed_keys[i] for i in shape_to_election})
    unmatched_boundary = [key for key in parsed_keys if key and key not in election_keys]
    result = {
        "event": f"same-sigungu edge-adjacent eupmyeondong equal-pair count >= {threshold}",
        "observed": {
            "equal_pair_count": int(observed_count),
            "threshold": int(threshold),
            "equal_pairs": pair_details(df, pair_list),
        },
        "simulation": {
            "iterations": int(args.iters),
            "probability_ge_threshold": float(np.mean(counts >= threshold)),
            "success_count": int(np.sum(counts >= threshold)),
            "mean_equal_pairs": float(np.mean(counts)),
            "median_equal_pairs": percentile(counts, 50),
            "p95_equal_pairs": percentile(counts, 95),
            "max_equal_pairs": int(np.max(counts)),
        },
        "data": {
            "election_source": election_source,
            "boundary_source": boundary_source,
            "election_rows": int(len(df)),
            "boundary_records": int(len(records)),
            "matched_boundary_records": int(len(shape_to_election)),
            "unmatched_election_rows": int(len(unmatched_election)),
            "unmatched_boundary_records": int(len(unmatched_boundary)),
            "raw_adjacent_shape_pairs": int(len(raw_adjacent_pairs)),
            "adjacent_pairs_same_sigungu_matched": int(len(adjacent_pairs)),
            "skipped_adjacent_pairs_not_matched": int(skipped_not_matched),
            "skipped_adjacent_pairs_cross_sigungu": int(skipped_cross_sigungu),
            "duplicate_election_keys": int(len(duplicates)),
            "unmatched_election_examples": [
                " ".join(key) for key in unmatched_election[:20]
            ],
            "unmatched_boundary_examples": [
                " ".join(key) for key in unmatched_boundary[:20]
            ],
            "parsed_boundary_field_names": list(records[0].keys()) if records else [],
            "adm_code_map_size": int(len(adm_code_map)),
        },
        "config": vars(args),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / (
        f"adjacent_pairs_{args.dataset}_{args.sheet}_{args.rows}"
        f"_model-{args.prob_model}-{args.model_scope}"
        f"_qw{args.q_prior_weight:g}_pw{args.p_prior_weight:g}"
        f"_turnout-{args.turnout_prior}_{args.iters}.json"
    )
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved={out}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary", default=str(INPUTS_DIR / "sgis"), help="SGIS SHP directory, .shp file, or .zip")
    parser.add_argument("--dbf-encoding", default="cp949")
    parser.add_argument("--full-name-field", default="")
    parser.add_argument("--sido-field", default="")
    parser.add_argument("--sigungu-field", default="")
    parser.add_argument("--emd-field", default="")
    parser.add_argument(
        "--adm-code-file",
        default="",
        help="Optional SGIS adm_code.xls. Needed if the boundary DBF has only ADM_CD and not full names.",
    )
    parser.add_argument("--adm-code-sheet", default="", help="Optional adm_code.xls sheet name; defaults to first sheet.")
    parser.add_argument("--coord-precision", type=int, default=3)
    parser.add_argument("--api-source", action="store_true", help="Fetch SGIS hadmarea.geojson instead of reading local SHP/GeoJSON.")
    parser.add_argument("--api-base-url", default="https://sgisapi.mods.go.kr/OpenAPI3")
    parser.add_argument("--api-year", default="2025")
    parser.add_argument("--api-low-search", default="1")
    parser.add_argument("--api-access-token", default="")
    parser.add_argument("--api-consumer-key", default="")
    parser.add_argument("--api-consumer-secret", default="")
    parser.add_argument("--api-sigungu-codes", default="", help="Comma-separated SGIS sigungu adm_cd values; otherwise derived from adm_code.xls.")
    parser.add_argument("--api-cache", default="", help="Optional path to save/load combined GeoJSON API response.")
    parser.add_argument("--api-sleep", type=float, default=0.05)
    parser.add_argument("--api-strict", action="store_true", help="Fail instead of skipping SGIS API no-result codes.")

    parser.add_argument("--dataset", choices=["2022", "2026"], default="2026")
    parser.add_argument("--sheet", default="시·도지사")
    parser.add_argument("--rows", choices=["regular", "advance"], default="advance")
    parser.add_argument("--threshold", default="observed", help="'observed' or integer threshold")
    parser.add_argument("--iters", type=int, default=50_000)
    parser.add_argument("--seed", type=int, default=20260610)
    parser.add_argument("--min-n", type=int, default=1)

    scopes = [
        "same_sigungu",
        "same_sido",
        "same_sido_gwangju_jeonnam",
        "same_eupmyeondong_stem",
        "all",
    ]
    parser.add_argument("--model-scope", choices=scopes, default="same_sigungu")
    parser.add_argument("--prob-model", choices=["group", "row_centered", "row_shrink"], default="row_shrink")
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--kappa", type=float, default=500.0)
    parser.add_argument("--tau", type=float, default=500.0)
    parser.add_argument("--q-prior-weight", type=float, default=0.7)
    parser.add_argument("--p-prior-weight", type=float, default=0.7)
    parser.add_argument("--turnout-prior", choices=["current", "previous_2022"], default="current")
    parser.add_argument("--randomize-n", action="store_true", default=True)
    parser.add_argument("--no-randomize-n", dest="randomize_n", action="store_false")
    args = parser.parse_args()

    boundary = Path(args.boundary)
    if not args.api_source and not boundary.exists():
        raise FileNotFoundError(
            f"Boundary file not found: {boundary}. Put the SGIS eupmyeondong SHP zip or extracted SHP under inputs/sgis."
        )

    if not args.api_source and boundary.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as temp:
            extracted = extract_zip(boundary, Path(temp))
            run(args, extracted)
    else:
        run(args, boundary)


if __name__ == "__main__":
    main()
