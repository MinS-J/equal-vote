"""광역권별 동일득표쌍 초과확률 계산.

2026 시·도지사 관내사전투표에서 광역권별 관측 동일득표쌍 수를 구하고,
모델 2(row_shrink) 반복 시뮬레이션 안에서 각 광역권이 n쌍 이상을 만들
확률을 계산한다.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

import numpy as np

from simulate_equal_candidate_pairs import (
    RESULTS_DIR,
    build_group_probabilities,
    build_row_shrink_parameters,
    build_turnout_probabilities,
    count_equal_pairs,
    group_by_scope,
)
from simulate_joint_events import draw_sample, load_dataframe


def region_name(value: str) -> str:
    if value in {"광주광역시", "전라남도"}:
        return "광주·전남"
    if value == "전북특별자치도":
        return "전북"
    if value.endswith("특별시"):
        return value.removesuffix("특별시")
    if value.endswith("광역시"):
        return value.removesuffix("광역시")
    if value.endswith("특별자치도"):
        return value.removesuffix("특별자치도")
    if value.endswith("도"):
        return value.removesuffix("도")
    return value


def build_region_groups(df):
    buckets: dict[str, list[int]] = defaultdict(list)
    for idx, sido in enumerate(df["sido_or_district"].astype(str)):
        buckets[region_name(sido)].append(idx)
    groups = []
    for name, idx in sorted(buckets.items()):
        if len(idx) >= 2:
            groups.append((name, np.array(idx, dtype=np.int64)))
    return groups


def summarize(
    dataset: str,
    sheet: str,
    rows: str,
    weight: float,
    iters: int,
    seed: int,
    thresholds: list[int],
):
    df, source = load_dataframe(dataset, sheet, rows, min_n=1)
    region_groups = build_region_groups(df)
    model_groups = group_by_scope(df, "same_sigungu")
    probs = build_group_probabilities(df, model_groups, alpha=0.5)
    turnout_probs = build_turnout_probabilities(df, model_groups, alpha=0.5)
    row_params = build_row_shrink_parameters(
        df,
        model_groups,
        probs,
        turnout_probs,
        q_prior_weight=weight,
        p_prior_weight=weight,
        alpha=0.5,
    )

    c1 = df["candidate_1"].to_numpy(dtype=np.int64)
    c2 = df["candidate_2"].to_numpy(dtype=np.int64)
    key_base = int(df["n"].max()) + 2

    observed = {}
    for name, idx in region_groups:
        pairs, _, _ = count_equal_pairs(c1, c2, [(name, idx)], key_base)
        possible = len(idx) * (len(idx) - 1) // 2
        observed[name] = {
            "region": name,
            "observed_equal_pairs": int(pairs),
            "possible_pairs": int(possible),
            "polling_places": int(len(idx)),
        }

    rng = np.random.default_rng(seed)
    sim_counts = {name: np.zeros(iters, dtype=np.int64) for name, _ in region_groups}
    for t in range(iters):
        sim_a, sim_b, sim_base = draw_sample(
            rng,
            df,
            model_groups,
            probs,
            turnout_probs,
            "row_shrink",
            row_params,
            randomize_n=True,
        )
        for name, idx in region_groups:
            pairs, _, _ = count_equal_pairs(sim_a, sim_b, [(name, idx)], sim_base)
            sim_counts[name][t] = pairs

    regions = []
    for name in sorted(observed):
        threshold = observed[name]["observed_equal_pairs"]
        counts = sim_counts[name]
        if threshold > 0:
            p_ge_observed = float(np.mean(counts >= threshold))
        else:
            p_ge_observed = None
        regions.append(
            {
                **observed[name],
                "threshold": int(threshold),
                "mean_equal_pairs": float(np.mean(counts)),
                "p_ge_observed": p_ge_observed,
                "p_at_least_one": float(np.mean(counts >= 1)),
                "threshold_probabilities": {
                    str(n): float(np.mean(counts >= n)) for n in thresholds
                },
                "q95_equal_pairs": float(np.quantile(counts, 0.95)),
            }
        )

    return {
        "config": {
            "dataset": dataset,
            "sheet": sheet,
            "rows": rows,
            "model": "모델 2(Model 2)",
            "prob_model": "row_shrink",
            "weight": weight,
            "iters": iters,
            "seed": seed,
            "thresholds": thresholds,
            "source": source,
        },
        "regions": regions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["2026"], default="2026")
    parser.add_argument("--sheet", default="시·도지사")
    parser.add_argument("--rows", choices=["advance"], default="advance")
    parser.add_argument("--iters", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260610)
    parser.add_argument("--weights", nargs="+", type=float, default=[0.7])
    parser.add_argument("--thresholds", nargs="+", type=int, default=list(range(1, 11)))
    args = parser.parse_args()

    payload = {
        "generatedAt": "2026-06-10",
        "analyses": [
            summarize(
                args.dataset,
                args.sheet,
                args.rows,
                weight,
                args.iters,
                args.seed + int(weight * 100),
                args.thresholds,
            )
            for weight in args.weights
        ],
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    weights = "-".join(f"{w:g}" for w in args.weights)
    out = RESULTS_DIR / f"regional_thresholds_{args.dataset}_{args.sheet}_{args.rows}_w{weights}_{args.iters}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"saved={out}")


if __name__ == "__main__":
    main()
