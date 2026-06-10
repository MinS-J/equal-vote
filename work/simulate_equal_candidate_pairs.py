from __future__ import annotations

import argparse
import json
import re
from collections import Counter

import numpy as np
import pandas as pd

from paths import DATA_DIR, RESULTS_DIR


def eupmyeondong_stem(name: str):
    text = str(name).strip()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"제?\d+(?=동$)", "", text)
    text = re.sub(r"[一二三四五六七八九十]+(?=동$)", "", text)
    return text


def group_by_scope(df: pd.DataFrame, scope: str):
    if scope == "same_sigungu":
        cols = ["sido_or_district", "sigungu"]
    elif scope == "same_sido":
        cols = ["sido_or_district"]
    elif scope == "same_sido_gwangju_jeonnam":
        df = df.copy()
        df["_sido_gj_jn"] = df["sido_or_district"].replace(
            {"광주광역시": "광주전남", "전라남도": "광주전남"}
        )
        cols = ["_sido_gj_jn"]
    elif scope == "same_eupmyeondong_stem":
        df = df.copy()
        df["_eupmyeondong_stem"] = df["eupmyeondong"].map(eupmyeondong_stem)
        cols = ["sido_or_district", "sigungu", "_eupmyeondong_stem"]
    elif scope == "all":
        df = df.copy()
        df["_all"] = "all"
        cols = ["_all"]
    else:
        raise ValueError(f"Unknown scope: {scope}")

    groups = []
    for key, sub in df.groupby(cols, sort=False, dropna=False):
        if len(sub) >= 2:
            groups.append((key, sub.index.to_numpy()))
    return groups


def count_equal_pairs(candidate_1: np.ndarray, candidate_2: np.ndarray, groups, key_base: int):
    total_pairs = 0
    matched_groups = 0
    max_pairs_in_group = 0

    for _, idx in groups:
        keys = candidate_1[idx].astype(np.int64) * key_base + candidate_2[idx].astype(np.int64)
        _, counts = np.unique(keys, return_counts=True)
        pairs = int(np.sum(counts * (counts - 1) // 2))
        if pairs:
            matched_groups += 1
            max_pairs_in_group = max(max_pairs_in_group, pairs)
        total_pairs += pairs

    return total_pairs, matched_groups, max_pairs_in_group


def build_group_probabilities(df: pd.DataFrame, groups, alpha: float):
    probs = {}
    for key, idx in groups:
        sub = df.loc[idx]
        n = sub["n"].sum()
        a = sub["candidate_1"].sum()
        b = sub["candidate_2"].sum()
        o = sub["other"].sum()
        denom = n + 3 * alpha
        probs[key] = np.array(
            [(a + alpha) / denom, (b + alpha) / denom, (o + alpha) / denom],
            dtype=float,
        )
    return probs


def build_turnout_probabilities(df: pd.DataFrame, groups, alpha: float):
    probs = {}
    for key, idx in groups:
        sub = df.loc[idx]
        electors = sub["total_electors"].sum()
        advance = sub["n"].sum()
        probs[key] = float((advance + alpha) / (electors + 2 * alpha))
    return probs


def build_row_centered_parameters(df: pd.DataFrame, alpha: float, kappa: float, tau: float):
    total = df["total_electors"].to_numpy(dtype=float)
    n = df["n"].to_numpy(dtype=float)
    q_center = (n + alpha) / (total + 2 * alpha)

    counts = df[["candidate_1", "candidate_2", "other"]].to_numpy(dtype=float)
    p_center = (counts + alpha) / (n[:, None] + 3 * alpha)

    return {
        "q_alpha": np.clip(q_center * kappa, 1e-9, None),
        "q_beta": np.clip((1.0 - q_center) * kappa, 1e-9, None),
        "dirichlet_alpha": np.clip(p_center * tau, 1e-9, None),
    }


def build_row_shrink_parameters(
    df: pd.DataFrame,
    model_groups,
    probs,
    turnout_probs,
    q_prior_weight: float,
    p_prior_weight: float,
    alpha: float,
):
    if not (0.0 <= q_prior_weight < 1.0):
        raise ValueError("--q-prior-weight must be in [0, 1).")
    if not (0.0 <= p_prior_weight < 1.0):
        raise ValueError("--p-prior-weight must be in [0, 1).")

    total = df["total_electors"].to_numpy(dtype=float)
    n = df["n"].to_numpy(dtype=float)
    counts = df[["candidate_1", "candidate_2", "other"]].to_numpy(dtype=float)

    q_alpha = np.zeros(len(df), dtype=float)
    q_beta = np.zeros(len(df), dtype=float)
    dirichlet_alpha = np.zeros((len(df), 3), dtype=float)

    q_multiplier = q_prior_weight / max(1e-15, 1.0 - q_prior_weight)
    p_multiplier = p_prior_weight / max(1e-15, 1.0 - p_prior_weight)

    for key, idx in model_groups:
        q_group = turnout_probs[key]
        p_group = probs[key]

        q_strength = q_multiplier * total[idx]
        p_strength = p_multiplier * n[idx]

        q_alpha[idx] = q_group * q_strength + n[idx] + alpha
        q_beta[idx] = (1.0 - q_group) * q_strength + (total[idx] - n[idx]) + alpha
        dirichlet_alpha[idx] = p_group * p_strength[:, None] + counts[idx] + alpha

    return {
        "q_alpha": np.clip(q_alpha, 1e-9, None),
        "q_beta": np.clip(q_beta, 1e-9, None),
        "dirichlet_alpha": np.clip(dirichlet_alpha, 1e-9, None),
    }


def apply_previous_turnout_prior(df: pd.DataFrame, row_params, alpha: float):
    prev_adv = pd.read_pickle(DATA_DIR / "nec_2022_advance_rows.pkl")
    prev_regular = pd.read_pickle(DATA_DIR / "nec_2022_regular_rows.pkl")

    prev_total = prev_regular[
        (prev_regular["sheet"] == "시·도지사") & (prev_regular["gubun"].isin(["소계", "계"]))
    ][["sido_or_district", "sigungu", "district", "eupmyeondong", "electors"]].rename(
        columns={"electors": "prev_total_electors"}
    )
    prev_adv = prev_adv[
        prev_adv["sheet"] == "시·도지사"
    ][["sido_or_district", "sigungu", "district", "eupmyeondong", "electors"]].rename(
        columns={"electors": "prev_advance_electors"}
    )

    prev = prev_adv.merge(
        prev_total,
        on=["sido_or_district", "sigungu", "district", "eupmyeondong"],
        how="left",
    )
    merged = df[["sido_or_district", "sigungu", "district", "eupmyeondong"]].merge(
        prev,
        on=["sido_or_district", "sigungu", "district", "eupmyeondong"],
        how="left",
    )

    matched = merged["prev_advance_electors"].notna() & merged["prev_total_electors"].notna()
    idx = matched.to_numpy()
    prev_advance = merged.loc[matched, "prev_advance_electors"].to_numpy(dtype=float)
    prev_total_electors = merged.loc[matched, "prev_total_electors"].to_numpy(dtype=float)

    q_alpha = row_params["q_alpha"].copy()
    q_beta = row_params["q_beta"].copy()
    q_alpha[idx] = prev_advance + alpha
    q_beta[idx] = (prev_total_electors - prev_advance) + alpha

    updated = dict(row_params)
    updated["q_alpha"] = np.clip(q_alpha, 1e-9, None)
    updated["q_beta"] = np.clip(q_beta, 1e-9, None)
    updated["previous_turnout_match_count"] = int(matched.sum())
    updated["previous_turnout_unmatched_count"] = int((~matched).sum())
    return updated


def simulate(
    df: pd.DataFrame,
    pair_groups,
    model_groups,
    probs,
    turnout_probs,
    randomize_n: bool,
    prob_model: str,
    row_params,
    iters: int,
    seed: int,
):
    rng = np.random.default_rng(seed)
    observed_n = df["n"].to_numpy(dtype=np.int64)
    total_electors = df["total_electors"].to_numpy(dtype=np.int64)
    n = observed_n.copy()
    key_base = int(n.max()) + 2

    candidate_1_obs = df["candidate_1"].to_numpy(dtype=np.int64)
    candidate_2_obs = df["candidate_2"].to_numpy(dtype=np.int64)
    observed_pairs, observed_groups, observed_max_pairs = count_equal_pairs(
        candidate_1_obs, candidate_2_obs, pair_groups, key_base
    )

    pair_counts = np.empty(iters, dtype=np.int64)
    group_counts = np.empty(iters, dtype=np.int64)

    sim_a = np.zeros(len(df), dtype=np.int64)
    sim_b = np.zeros(len(df), dtype=np.int64)

    for t in range(iters):
        if prob_model in {"row_centered", "row_shrink"}:
            if randomize_n:
                q = rng.beta(row_params["q_alpha"], row_params["q_beta"])
                n = rng.binomial(total_electors, q)
                key_base = max(key_base, int(n.max()) + 2)
            gamma = rng.gamma(row_params["dirichlet_alpha"], 1.0)
            p = gamma / gamma.sum(axis=1, keepdims=True)
            sim_a = rng.binomial(n, p[:, 0])
            remaining = n - sim_a
            b_given_not_a = p[:, 1] / np.clip(1.0 - p[:, 0], 1e-15, None)
            b_given_not_a = np.clip(b_given_not_a, 0.0, 1.0)
            sim_b = rng.binomial(remaining, b_given_not_a)
        else:
            for key, idx in model_groups:
                if randomize_n:
                    n[idx] = rng.binomial(total_electors[idx], turnout_probs[key])
                    key_base = max(key_base, int(n[idx].max()) + 2)
                p_a, p_b, _ = probs[key]
                a = rng.binomial(n[idx], p_a)
                remaining = n[idx] - a
                b_given_not_a = p_b / max(1e-15, 1.0 - p_a)
                b = rng.binomial(remaining, b_given_not_a)
                sim_a[idx] = a
                sim_b[idx] = b

        pairs, matched_groups, _ = count_equal_pairs(sim_a, sim_b, pair_groups, key_base)
        pair_counts[t] = pairs
        group_counts[t] = matched_groups

    return {
        "observed": {
            "equal_pair_count": observed_pairs,
            "matched_group_count": observed_groups,
            "max_equal_pairs_in_one_group": observed_max_pairs,
        },
        "simulation": {
            "iterations": iters,
            "p_at_least_one_equal_pair": float(np.mean(pair_counts >= 1)),
            "p_equal_pair_count_ge_observed": float(np.mean(pair_counts >= observed_pairs)),
            "mean_equal_pair_count": float(np.mean(pair_counts)),
            "median_equal_pair_count": float(np.median(pair_counts)),
            "quantiles_equal_pair_count": {
                "50%": float(np.quantile(pair_counts, 0.50)),
                "90%": float(np.quantile(pair_counts, 0.90)),
                "95%": float(np.quantile(pair_counts, 0.95)),
                "99%": float(np.quantile(pair_counts, 0.99)),
            },
            "pair_count_histogram": dict(Counter(pair_counts.tolist()).most_common(20)),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["2022", "2026"], default="2022")
    parser.add_argument("--sheet", default="시·도지사")
    parser.add_argument("--rows", choices=["regular", "advance"], default="advance")
    scopes = [
        "same_sigungu",
        "same_sido",
        "same_sido_gwangju_jeonnam",
        "same_eupmyeondong_stem",
        "all",
    ]
    parser.add_argument("--pair-scope", choices=scopes, default="same_sigungu")
    parser.add_argument("--model-scope", choices=scopes, default="same_sigungu")
    parser.add_argument("--iters", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=20260609)
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--prob-model", choices=["group", "row_centered", "row_shrink"], default="group")
    parser.add_argument("--kappa", type=float, default=500.0)
    parser.add_argument("--tau", type=float, default=500.0)
    parser.add_argument("--q-prior-weight", type=float, default=0.3)
    parser.add_argument("--p-prior-weight", type=float, default=0.3)
    parser.add_argument("--turnout-prior", choices=["current", "previous_2022"], default="current")
    parser.add_argument("--min-n", type=int, default=1)
    parser.add_argument("--randomize-n", action="store_true")
    args = parser.parse_args()

    prefix = f"nec_{args.dataset}"
    source = DATA_DIR / (f"{prefix}_advance_rows.pkl" if args.rows == "advance" else f"{prefix}_regular_rows.pkl")
    df = pd.read_pickle(source)
    df = df[df["sheet"] == args.sheet].copy()
    df["n"] = df["electors"].astype(int)
    if args.rows == "advance":
        total_source = pd.read_pickle(DATA_DIR / f"{prefix}_regular_rows.pkl")
        total = total_source[
            (total_source["sheet"] == args.sheet)
            & (total_source["gubun"].isin(["소계", "계"]))
        ][["sido_or_district", "sigungu", "district", "eupmyeondong", "electors"]].copy()
        total = total.rename(columns={"electors": "total_electors"})
        df = df.merge(
            total,
            on=["sido_or_district", "sigungu", "district", "eupmyeondong"],
            how="left",
        )
        df["total_electors"] = df["total_electors"].fillna(df["n"]).astype(int)
    else:
        df["total_electors"] = df["n"]
    df["other"] = df["n"] - df["candidate_1"].astype(int) - df["candidate_2"].astype(int)
    df = df[(df["n"] >= args.min_n) & (df["other"] >= 0)].reset_index(drop=True)

    pair_group_list = group_by_scope(df, args.pair_scope)
    model_group_list = group_by_scope(df, args.model_scope)
    probs = build_group_probabilities(df, model_group_list, args.alpha)
    turnout_probs = build_turnout_probabilities(df, model_group_list, args.alpha)
    if args.prob_model == "row_shrink":
        row_params = build_row_shrink_parameters(
            df,
            model_group_list,
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
    result = simulate(
        df,
        pair_group_list,
        model_group_list,
        probs,
        turnout_probs,
        args.randomize_n,
        args.prob_model,
        row_params,
        args.iters,
        args.seed,
    )

    possible_pairs = sum(len(idx) * (len(idx) - 1) // 2 for _, idx in pair_group_list)
    result["config"] = vars(args)
    result["data"] = {
        "source": str(source),
        "rows": int(len(df)),
        "pair_groups_with_at_least_two_rows": int(len(pair_group_list)),
        "model_groups_with_at_least_two_rows": int(len(model_group_list)),
        "possible_pairs": int(possible_pairs),
    }
    if args.turnout_prior == "previous_2022":
        result["data"]["previous_turnout_matched_rows"] = row_params.get("previous_turnout_match_count", 0)
        result["data"]["previous_turnout_unmatched_rows"] = row_params.get("previous_turnout_unmatched_count", 0)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / (
        f"simulation_{args.dataset}_{args.sheet}_{args.rows}_pair-{args.pair_scope}"
        f"_model-{args.prob_model}-{args.model_scope}_n-{'random' if args.randomize_n else 'fixed'}"
        f"_k{args.kappa:g}_t{args.tau:g}_qw{args.q_prior_weight:g}_pw{args.p_prior_weight:g}"
        f"_turnout-{args.turnout_prior}_{args.iters}.json"
    )
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved={out}")


if __name__ == "__main__":
    main()
