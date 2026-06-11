"""Joint probability for edge-adjacent equal-vote pairs and a wider scope.

This complements simulate_joint_events.py.  The existing joint script handles
group-defined scopes such as same_eupmyeondong_stem or same_sido_gwangju_jeonnam.
Edge adjacency is different: it is an explicit pair list derived from SGIS
boundary polygons.  This script counts that explicit pair event and a regular
scope event in the same Monte Carlo repetition.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

from analyze_geo_adjacent_observed import (
    load_dong_zip_boundary,
    matched_pairs_for_dataset,
    parse_boundary_zip,
)
from file_names import sheet_slug
from paths import INPUTS_DIR, RESULTS_DIR
from simulate_adjacent_pairs import (
    build_adjacent_shape_pairs,
    default_adm_code_file,
    extract_zip,
    load_adm_code_map,
    load_boundary_records_and_shapes,
    normalize_key,
    pair_details,
    record_admin_key,
)
from simulate_equal_candidate_pairs import (
    apply_previous_turnout_prior,
    build_group_probabilities,
    build_row_centered_parameters,
    build_row_shrink_parameters,
    build_turnout_probabilities,
    count_equal_pairs,
    group_by_scope,
)
from simulate_joint_events import draw_sample, load_dataframe


def count_explicit_equal_pairs_fast(
    candidate_1: np.ndarray,
    candidate_2: np.ndarray,
    pair_left: np.ndarray,
    pair_right: np.ndarray,
) -> int:
    if len(pair_left) == 0:
        return 0
    same = (candidate_1[pair_left] == candidate_1[pair_right]) & (
        candidate_2[pair_left] == candidate_2[pair_right]
    )
    return int(np.count_nonzero(same))


def count_explicit_equal_pairs_batch(
    candidate_1: np.ndarray,
    candidate_2: np.ndarray,
    pair_left: np.ndarray,
    pair_right: np.ndarray,
) -> np.ndarray:
    if len(pair_left) == 0:
        return np.zeros(candidate_1.shape[0], dtype=np.int64)
    same = (candidate_1[:, pair_left] == candidate_1[:, pair_right]) & (
        candidate_2[:, pair_left] == candidate_2[:, pair_right]
    )
    return np.count_nonzero(same, axis=1).astype(np.int64)


def count_equal_pairs_batch(
    candidate_1: np.ndarray,
    candidate_2: np.ndarray,
    groups,
    key_base: int,
) -> np.ndarray:
    batch_size = candidate_1.shape[0]
    totals = np.zeros(batch_size, dtype=np.int64)
    row_ids = np.arange(batch_size, dtype=np.int64)[:, None]
    key_offset = key_base * key_base + key_base + 1

    for _, idx in groups:
        keys = candidate_1[:, idx].astype(np.int64) * key_base + candidate_2[:, idx].astype(np.int64)
        composite = keys + row_ids * key_offset
        unique, counts = np.unique(composite.ravel(), return_counts=True)
        duplicate_mask = counts >= 2
        if not np.any(duplicate_mask):
            continue
        sims = (unique[duplicate_mask] // key_offset).astype(np.int64)
        pairs = (counts[duplicate_mask] * (counts[duplicate_mask] - 1) // 2).astype(np.int64)
        contribution = np.zeros(batch_size, dtype=np.int64)
        np.add.at(contribution, sims, pairs)
        totals += contribution

    return totals


def draw_sample_batch(
    rng,
    df,
    model_groups,
    probs,
    turnout_probs,
    prob_model,
    row_params,
    randomize_n,
    batch_size: int,
):
    total_electors = df["total_electors"].to_numpy(dtype=np.int64)
    observed_n = df["n"].to_numpy(dtype=np.int64)
    row_count = len(df)

    if randomize_n:
        n = np.empty((batch_size, row_count), dtype=np.int64)
    else:
        n = np.broadcast_to(observed_n, (batch_size, row_count)).copy()
    sim_a = np.zeros((batch_size, row_count), dtype=np.int64)
    sim_b = np.zeros((batch_size, row_count), dtype=np.int64)

    if prob_model in {"row_centered", "row_shrink"}:
        if randomize_n:
            q = rng.beta(row_params["q_alpha"], row_params["q_beta"], size=(batch_size, row_count))
            n = rng.binomial(total_electors[None, :], q)
        gamma = rng.gamma(row_params["dirichlet_alpha"], 1.0, size=(batch_size, row_count, 3))
        p = gamma / gamma.sum(axis=2, keepdims=True)
        sim_a = rng.binomial(n, p[:, :, 0])
        remaining = n - sim_a
        b_given_not_a = np.clip(p[:, :, 1] / np.clip(1.0 - p[:, :, 0], 1e-15, None), 0.0, 1.0)
        sim_b = rng.binomial(remaining, b_given_not_a)
    else:
        if not randomize_n:
            n = np.broadcast_to(observed_n, (batch_size, row_count)).copy()
        for key, idx in model_groups:
            if randomize_n:
                n[:, idx] = rng.binomial(total_electors[idx][None, :], turnout_probs[key])
            p_a, p_b, _ = probs[key]
            a = rng.binomial(n[:, idx], p_a)
            remaining = n[:, idx] - a
            b_given_not_a = p_b / max(1e-15, 1.0 - p_a)
            b = rng.binomial(remaining, b_given_not_a)
            sim_a[:, idx] = a
            sim_b[:, idx] = b

    return sim_a, sim_b


def build_same_sigungu_adjacent_pairs(args, df, boundary_root: Path) -> dict:
    if args.pair_cache:
        cache_path = Path(args.pair_cache)
        if cache_path.exists() and not args.refresh_pair_cache:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            payload["pairs"] = [tuple(pair) for pair in payload.get("pairs", [])]
            return payload

    boundary_zip = Path(args.boundary)
    spec = parse_boundary_zip(boundary_zip) if boundary_zip.suffix.lower() == ".zip" else None
    if spec:
        boundary = load_dong_zip_boundary(spec, args)
        work = df[
            ["sido_or_district", "sigungu", "eupmyeondong", "candidate_1", "candidate_2"]
        ].rename(
            columns={
                "sido_or_district": "sido",
                "candidate_1": "vote_a",
                "candidate_2": "vote_b",
            }
        ).reset_index(drop=True)
        shape_to_row, all_pairs, same_sigungu_pairs, duplicate_rows = matched_pairs_for_dataset(
            work,
            boundary,
        )
        payload = {
            "boundary_source": str(boundary_zip),
            "pairs": sorted(same_sigungu_pairs),
            "boundary_records": int(boundary["record_count"]),
            "matched_boundary_records": int(len(set(shape_to_row.values()))),
            "raw_adjacent_shape_pairs": int(len(boundary["raw_edge_pairs"])),
            "skipped_adjacent_pairs_not_matched": int(
                len(boundary["raw_edge_pairs"]) - len(all_pairs)
            ),
            "skipped_adjacent_pairs_cross_sigungu": int(len(all_pairs) - len(same_sigungu_pairs)),
            "duplicate_election_keys": int(duplicate_rows),
            "unmatched_election_rows": int(len(work) - len(set(shape_to_row.values()))),
            "unmatched_boundary_records": int(boundary["record_count"] - len(shape_to_row)),
            "unmatched_election_examples": [],
            "unmatched_boundary_examples": [],
            "parsed_boundary_field_names": [],
            "adm_code_map_size": None,
        }
        if args.pair_cache:
            cache_path = Path(args.pair_cache)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    records, shapes, boundary_source = load_boundary_records_and_shapes(args, boundary_root)
    adm_code_map = load_adm_code_map(default_adm_code_file(args), args.adm_code_sheet)

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

    unmatched_election = sorted(set(election_keys) - {parsed_keys[i] for i in shape_to_election})
    unmatched_boundary = [key for key in parsed_keys if key and key not in election_keys]
    payload = {
        "boundary_source": boundary_source,
        "pairs": sorted(adjacent_pairs),
        "boundary_records": int(len(records)),
        "matched_boundary_records": int(len(shape_to_election)),
        "raw_adjacent_shape_pairs": int(len(raw_adjacent_pairs)),
        "skipped_adjacent_pairs_not_matched": int(skipped_not_matched),
        "skipped_adjacent_pairs_cross_sigungu": int(skipped_cross_sigungu),
        "duplicate_election_keys": int(len(duplicates)),
        "unmatched_election_rows": int(len(unmatched_election)),
        "unmatched_boundary_records": int(len(unmatched_boundary)),
        "unmatched_election_examples": [" ".join(key) for key in unmatched_election[:20]],
        "unmatched_boundary_examples": [" ".join(key) for key in unmatched_boundary[:20]],
        "parsed_boundary_field_names": list(records[0].keys()) if records else [],
        "adm_code_map_size": int(len(adm_code_map)),
    }
    if args.pair_cache:
        cache_path = Path(args.pair_cache)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def model_label(config: dict) -> str:
    if config.get("prob_model") == "group":
        return "model1"
    return f"model2-w{config.get('q_prior_weight'):g}"


def run(args, boundary_root: Path) -> dict:
    df, election_source = load_dataframe(args.dataset, args.sheet, args.rows, args.min_n)
    adjacent = build_same_sigungu_adjacent_pairs(args, df, boundary_root)
    pair_list = adjacent["pairs"]
    pair_left = np.array([i for i, _ in pair_list], dtype=np.int64)
    pair_right = np.array([j for _, j in pair_list], dtype=np.int64)

    groups_b = group_by_scope(df, args.scope_b)
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

    c1 = df["candidate_1"].to_numpy(dtype=np.int64)
    c2 = df["candidate_2"].to_numpy(dtype=np.int64)
    obs_base = int(df["n"].max()) + 2
    obs_a = count_explicit_equal_pairs_fast(c1, c2, pair_left, pair_right)
    obs_b, _, _ = count_equal_pairs(c1, c2, groups_b, obs_base)

    threshold_a = obs_a if args.threshold_a == "observed" else int(args.threshold_a)
    if threshold_a <= 0:
        threshold_a = 1

    rng = np.random.default_rng(args.seed)
    counts_a = np.empty(args.iters, dtype=np.int64)
    counts_b = np.empty(args.iters, dtype=np.int64)
    sim_key_base = int(df["total_electors"].max()) + 2

    done = 0
    while done < args.iters:
        batch_size = min(args.batch_size, args.iters - done)
        sim_a, sim_b = draw_sample_batch(
            rng, df, model_groups, probs, turnout_probs, args.prob_model, row_params,
            args.randomize_n, batch_size,
        )
        end = done + batch_size
        counts_a[done:end] = count_explicit_equal_pairs_batch(sim_a, sim_b, pair_left, pair_right)
        counts_b[done:end] = count_equal_pairs_batch(sim_a, sim_b, groups_b, sim_key_base)
        done = end
        if args.progress_every and done % args.progress_every == 0:
            print(f"completed {done:,}/{args.iters:,}", file=sys.stderr)

    ind_a = counts_a >= threshold_a
    ind_b = counts_b >= args.threshold_b
    p_a = float(np.mean(ind_a))
    p_b = float(np.mean(ind_b))
    p_ab = float(np.mean(ind_a & ind_b))
    result = {
        "events": {
            "A": f"scope=edge_adjacent_same_sigungu, equal_pair_count >= {threshold_a}",
            "B": f"scope={args.scope_b}, equal_pair_count >= {args.threshold_b}",
        },
        "eventLabels": {
            "A": "경계 인접 1쌍 이상" if threshold_a == 1 else f"경계 인접 {threshold_a}쌍 이상",
            "B": "광역권 8쌍 이상"
            if args.scope_b == "same_sido_gwangju_jeonnam" and args.threshold_b == 8
            else f"{args.scope_b} {args.threshold_b}쌍 이상",
        },
        "observed": {
            "A_count": int(obs_a),
            "B_count": int(obs_b),
            "A_holds": bool(obs_a >= threshold_a),
            "B_holds": bool(obs_b >= args.threshold_b),
            "A_equal_pairs": pair_details(df, pair_list),
        },
        "joint": {
            "iterations": int(args.iters),
            "P_A": p_a,
            "P_B": p_b,
            "P_A_and_B": p_ab,
            "P_A_or_B": float(np.mean(ind_a | ind_b)),
            "P_B_given_A": (p_ab / p_a) if p_a > 0 else None,
            "P_A_given_B": (p_ab / p_b) if p_b > 0 else None,
            "P_A_times_P_B_if_independent": p_a * p_b,
            "independence_ratio_PAB_over_PAPB": (p_ab / (p_a * p_b)) if (p_a * p_b) > 0 else None,
            "success_count_A": int(np.sum(ind_a)),
            "success_count_B": int(np.sum(ind_b)),
            "success_count_A_and_B": int(np.sum(ind_a & ind_b)),
            "mean_A_equal_pairs": float(np.mean(counts_a)),
            "mean_B_equal_pairs": float(np.mean(counts_b)),
            "max_A_equal_pairs": int(np.max(counts_a)),
            "max_B_equal_pairs": int(np.max(counts_b)),
        },
        "config": vars(args),
        "data": {
            "election_source": election_source,
            "rows": int(len(df)),
            "scope_a_possible_pairs": int(len(pair_list)),
            "scope_b_pair_groups": int(len(groups_b)),
            "scope_b_possible_pairs": int(sum(len(idx) * (len(idx) - 1) // 2 for _, idx in groups_b)),
            "simulation_key_base": int(sim_key_base),
            **{key: value for key, value in adjacent.items() if key != "pairs"},
        },
    }
    if args.turnout_prior == "previous_2022":
        result["data"]["previous_turnout_matched_rows"] = row_params.get("previous_turnout_match_count", 0)
        result["data"]["previous_turnout_unmatched_rows"] = row_params.get("previous_turnout_unmatched_count", 0)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary", default=str(INPUTS_DIR / "sgis" / "bnd_dong_00_2025_2Q.zip"))
    parser.add_argument("--dbf-encoding", default="cp949")
    parser.add_argument("--full-name-field", default="")
    parser.add_argument("--sido-field", default="")
    parser.add_argument("--sigungu-field", default="")
    parser.add_argument("--emd-field", default="")
    parser.add_argument("--adm-code-file", default="")
    parser.add_argument("--adm-code-sheet", default="")
    parser.add_argument("--coord-precision", type=int, default=3)
    parser.add_argument("--api-source", action="store_true")
    parser.add_argument("--api-base-url", default="https://sgisapi.mods.go.kr/OpenAPI3")
    parser.add_argument("--api-year", default="2025")
    parser.add_argument("--api-low-search", default="1")
    parser.add_argument("--api-access-token", default="")
    parser.add_argument("--api-consumer-key", default="")
    parser.add_argument("--api-consumer-secret", default="")
    parser.add_argument("--api-sigungu-codes", default="")
    parser.add_argument("--api-cache", default="")
    parser.add_argument("--api-sleep", type=float, default=0.05)
    parser.add_argument("--api-strict", action="store_true")
    parser.add_argument(
        "--pair-cache",
        default=str(RESULTS_DIR / "edge_adjacent_pairs_2026_advance_2025_2Q.json"),
        help="JSON cache for matched same-sigungu edge-adjacent election row pairs.",
    )
    parser.add_argument("--refresh-pair-cache", action="store_true")

    parser.add_argument("--dataset", choices=["2022", "2026"], default="2026")
    parser.add_argument("--sheet", default="시·도지사")
    parser.add_argument("--rows", choices=["regular", "advance"], default="advance")
    parser.add_argument("--threshold-a", default="1", help="'observed' or integer threshold")
    parser.add_argument("--scope-b", default="same_sido_gwangju_jeonnam")
    parser.add_argument("--threshold-b", type=int, default=8)
    parser.add_argument("--model-scope", default="same_sigungu")
    parser.add_argument("--prob-model", choices=["group", "row_centered", "row_shrink"], default="row_shrink")
    parser.add_argument("--iters", type=int, default=50_000)
    parser.add_argument("--seed", type=int, default=20260610)
    parser.add_argument("--min-n", type=int, default=1)
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--kappa", type=float, default=500.0)
    parser.add_argument("--tau", type=float, default=500.0)
    parser.add_argument("--q-prior-weight", type=float, default=0.7)
    parser.add_argument("--p-prior-weight", type=float, default=0.7)
    parser.add_argument("--turnout-prior", choices=["current", "previous_2022"], default="current")
    parser.add_argument("--randomize-n", action="store_true", default=True)
    parser.add_argument("--no-randomize-n", dest="randomize_n", action="store_false")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--progress-every", type=int, default=0)
    args = parser.parse_args()

    boundary = Path(args.boundary)
    if not args.api_source and not boundary.exists():
        raise FileNotFoundError(
            f"Boundary file not found: {boundary}. Put the SGIS eupmyeondong SHP zip under inputs/sgis."
        )

    if not args.api_source and boundary.suffix.lower() == ".zip" and not parse_boundary_zip(boundary):
        with tempfile.TemporaryDirectory() as temp:
            boundary_root = extract_zip(boundary, Path(temp))
            result = run(args, boundary_root)
    else:
        result = run(args, boundary)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sheet_part = sheet_slug(args.sheet)
    out = RESULTS_DIR / (
        f"joint_adjacent_{args.dataset}_{sheet_part}_{args.rows}"
        f"_Aedge{result['events']['A'].rsplit('>= ', 1)[-1]}_Bgjjn{args.threshold_b}"
        f"_{args.prob_model}_{args.model_scope}"
        f"_qw{args.q_prior_weight:g}_pw{args.p_prior_weight:g}"
        f"_{args.turnout_prior}_{args.iters}.json"
    )
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved={out}")


if __name__ == "__main__":
    main()
