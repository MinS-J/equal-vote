"""Joint probability of two equal-vote-pair events within one simulation.

md outputs/equal_vote_probability_summary.md 13-2 단계 구현.

기존 simulate_equal_candidate_pairs.py 는 한 번의 실행에서 하나의 pair scope 만
카운트한다. 반면 다음 두 사건은 서로 독립이 아니다.

    A = 같은 읍면동 stem pair 에서 동일 득표쌍이 1개 이상 발생
    B = 광주+전남 통합 광역권 pair 에서 동일 득표쌍이 8개 이상 발생

stem pair 는 광역권 pair 집합의 부분집합이므로, 같은 시뮬레이션 반복 안에서
두 사건을 동시에 세야 P(A and B), P(B | A), P(A | B) 를 올바르게 얻는다.

이 스크립트는 매 반복마다 sim_a / sim_b 를 한 번만 생성한 뒤, 여러 pair scope
각각에 대해 동일 득표쌍 수를 세고 사건별 지시변수를 기록한다.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from simulate_equal_candidate_pairs import (
    DATA_DIR,
    RESULTS_DIR,
    apply_previous_turnout_prior,
    build_group_probabilities,
    build_row_centered_parameters,
    build_row_shrink_parameters,
    build_turnout_probabilities,
    count_equal_pairs,
    group_by_scope,
)


def load_dataframe(dataset: str, sheet: str, rows: str, min_n: int) -> pd.DataFrame:
    """simulate_equal_candidate_pairs.main 의 데이터 로딩과 동일한 절차.

    rows:
      advance       관내사전투표 row만
      election_day  선거일투표(본투표) row만
      regular       소계/계 + 관내사전 + 선거일 (혼합)
    """
    prefix = f"nec_{dataset}"
    source = DATA_DIR / (
        f"{prefix}_advance_rows.pkl" if rows == "advance" else f"{prefix}_regular_rows.pkl"
    )
    df = pd.read_pickle(source)
    df = df[df["sheet"] == sheet].copy()
    if rows == "election_day":
        df = df[df["gubun"] == "선거일투표"].copy()
    df["n"] = df["electors"].astype(int)
    if rows in {"advance", "election_day"}:
        total_source = pd.read_pickle(DATA_DIR / f"{prefix}_regular_rows.pkl")
        total = total_source[
            (total_source["sheet"] == sheet)
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
    df = df[(df["n"] >= min_n) & (df["other"] >= 0)].reset_index(drop=True)
    return df, str(source)


def draw_sample(rng, df, model_groups, probs, turnout_probs, prob_model, row_params, randomize_n):
    """한 번의 반복에 대한 sim_a, sim_b, key_base 생성.

    simulate_equal_candidate_pairs.simulate 의 반복 본문과 동일한 생성 모형.
    """
    total_electors = df["total_electors"].to_numpy(dtype=np.int64)
    observed_n = df["n"].to_numpy(dtype=np.int64)
    n = observed_n.copy()
    sim_a = np.zeros(len(df), dtype=np.int64)
    sim_b = np.zeros(len(df), dtype=np.int64)

    if prob_model in {"row_centered", "row_shrink"}:
        if randomize_n:
            q = rng.beta(row_params["q_alpha"], row_params["q_beta"])
            n = rng.binomial(total_electors, q)
        gamma = rng.gamma(row_params["dirichlet_alpha"], 1.0)
        p = gamma / gamma.sum(axis=1, keepdims=True)
        sim_a = rng.binomial(n, p[:, 0])
        remaining = n - sim_a
        b_given_not_a = np.clip(p[:, 1] / np.clip(1.0 - p[:, 0], 1e-15, None), 0.0, 1.0)
        sim_b = rng.binomial(remaining, b_given_not_a)
    else:
        for key, idx in model_groups:
            if randomize_n:
                n[idx] = rng.binomial(total_electors[idx], turnout_probs[key])
            p_a, p_b, _ = probs[key]
            a = rng.binomial(n[idx], p_a)
            remaining = n[idx] - a
            b_given_not_a = p_b / max(1e-15, 1.0 - p_a)
            b = rng.binomial(remaining, b_given_not_a)
            sim_a[idx] = a
            sim_b[idx] = b

    key_base = int(n.max()) + 2
    return sim_a, sim_b, key_base


def summarize_indicator(name, indicator):
    return {
        "event": name,
        "probability": float(np.mean(indicator)),
        "success_count": int(np.sum(indicator)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["2022", "2026"], default="2026")
    parser.add_argument("--sheet", default="시·도지사")
    parser.add_argument("--rows", choices=["regular", "advance"], default="advance")

    scopes = [
        "same_sigungu",
        "same_sido",
        "same_sido_gwangju_jeonnam",
        "same_eupmyeondong_stem",
        "all",
    ]
    # 사건 A
    parser.add_argument("--scope-a", choices=scopes, default="same_eupmyeondong_stem")
    parser.add_argument("--threshold-a", type=int, default=1)
    # 사건 B
    parser.add_argument("--scope-b", choices=scopes, default="same_sido_gwangju_jeonnam")
    parser.add_argument("--threshold-b", type=int, default=8)

    parser.add_argument("--model-scope", choices=scopes, default="same_sigungu")
    parser.add_argument("--prob-model", choices=["group", "row_centered", "row_shrink"], default="row_shrink")
    parser.add_argument("--iters", type=int, default=50_000)
    parser.add_argument("--seed", type=int, default=20260610)
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--kappa", type=float, default=500.0)
    parser.add_argument("--tau", type=float, default=500.0)
    parser.add_argument("--q-prior-weight", type=float, default=0.7)
    parser.add_argument("--p-prior-weight", type=float, default=0.7)
    parser.add_argument("--turnout-prior", choices=["current", "previous_2022"], default="current")
    parser.add_argument("--min-n", type=int, default=1)
    parser.add_argument("--randomize-n", action="store_true", default=True)
    parser.add_argument("--no-randomize-n", dest="randomize_n", action="store_false")
    args = parser.parse_args()

    df, source = load_dataframe(args.dataset, args.sheet, args.rows, args.min_n)

    groups_a = group_by_scope(df, args.scope_a)
    groups_b = group_by_scope(df, args.scope_b)
    model_groups = group_by_scope(df, args.model_scope)

    probs = build_group_probabilities(df, model_groups, args.alpha)
    turnout_probs = build_turnout_probabilities(df, model_groups, args.alpha)
    if args.prob_model == "row_shrink":
        row_params = build_row_shrink_parameters(
            df, model_groups, probs, turnout_probs,
            args.q_prior_weight, args.p_prior_weight, args.alpha,
        )
    else:
        row_params = build_row_centered_parameters(df, args.alpha, args.kappa, args.tau)
    if args.turnout_prior == "previous_2022":
        row_params = apply_previous_turnout_prior(df, row_params, args.alpha)

    # 관측치
    c1 = df["candidate_1"].to_numpy(dtype=np.int64)
    c2 = df["candidate_2"].to_numpy(dtype=np.int64)
    obs_base = int(df["n"].max()) + 2
    obs_a, _, _ = count_equal_pairs(c1, c2, groups_a, obs_base)
    obs_b, _, _ = count_equal_pairs(c1, c2, groups_b, obs_base)

    rng = np.random.default_rng(args.seed)
    counts_a = np.empty(args.iters, dtype=np.int64)
    counts_b = np.empty(args.iters, dtype=np.int64)

    for t in range(args.iters):
        sim_a, sim_b, key_base = draw_sample(
            rng, df, model_groups, probs, turnout_probs,
            args.prob_model, row_params, args.randomize_n,
        )
        pa, _, _ = count_equal_pairs(sim_a, sim_b, groups_a, key_base)
        pb, _, _ = count_equal_pairs(sim_a, sim_b, groups_b, key_base)
        counts_a[t] = pa
        counts_b[t] = pb

    ind_a = counts_a >= args.threshold_a
    ind_b = counts_b >= args.threshold_b
    p_a = float(np.mean(ind_a))
    p_b = float(np.mean(ind_b))
    p_ab = float(np.mean(ind_a & ind_b))
    p_a_or_b = float(np.mean(ind_a | ind_b))

    result = {
        "events": {
            "A": f"scope={args.scope_a}, equal_pair_count >= {args.threshold_a}",
            "B": f"scope={args.scope_b}, equal_pair_count >= {args.threshold_b}",
        },
        "observed": {
            "A_count": obs_a,
            "B_count": obs_b,
            "A_holds": bool(obs_a >= args.threshold_a),
            "B_holds": bool(obs_b >= args.threshold_b),
        },
        "joint": {
            "iterations": args.iters,
            "P_A": p_a,
            "P_B": p_b,
            "P_A_and_B": p_ab,
            "P_A_or_B": p_a_or_b,
            "P_B_given_A": (p_ab / p_a) if p_a > 0 else None,
            "P_A_given_B": (p_ab / p_b) if p_b > 0 else None,
            "P_A_times_P_B_if_independent": p_a * p_b,
            "independence_ratio_PAB_over_PAPB": (p_ab / (p_a * p_b)) if (p_a * p_b) > 0 else None,
            "success_count_A": int(np.sum(ind_a)),
            "success_count_B": int(np.sum(ind_b)),
            "success_count_A_and_B": int(np.sum(ind_a & ind_b)),
        },
        "config": vars(args),
        "data": {
            "source": source,
            "rows": int(len(df)),
            "scope_a_pair_groups": int(len(groups_a)),
            "scope_b_pair_groups": int(len(groups_b)),
            "scope_a_possible_pairs": int(sum(len(idx) * (len(idx) - 1) // 2 for _, idx in groups_a)),
            "scope_b_possible_pairs": int(sum(len(idx) * (len(idx) - 1) // 2 for _, idx in groups_b)),
        },
    }
    if args.turnout_prior == "previous_2022":
        result["data"]["previous_turnout_matched_rows"] = row_params.get("previous_turnout_match_count", 0)
        result["data"]["previous_turnout_unmatched_rows"] = row_params.get("previous_turnout_unmatched_count", 0)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / (
        f"joint_{args.dataset}_{args.sheet}_{args.rows}"
        f"_A-{args.scope_a}-ge{args.threshold_a}_B-{args.scope_b}-ge{args.threshold_b}"
        f"_model-{args.prob_model}-{args.model_scope}"
        f"_qw{args.q_prior_weight:g}_pw{args.p_prior_weight:g}"
        f"_turnout-{args.turnout_prior}_{args.iters}.json"
    )
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved={out}")


if __name__ == "__main__":
    main()
