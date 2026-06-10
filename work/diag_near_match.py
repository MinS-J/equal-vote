"""near-match 보정 검사 (파라미터화).

전국 광역권 합계(광주+전남은 한 권역으로 통합) scope에서,
두 행의 (candidate_1, candidate_2) 득표수가 |Δ1|<=d 이고 |Δ2|<=d 인
쌍 수를 d=0,1,2,3 에 대해 센다. 실제값 vs 시뮬평균을 비교.

d=0 만 어긋나면 정확일치 초과, 곡선 전체가 어긋나면 모델 미보정.
"""

from __future__ import annotations
import argparse
from collections import Counter
import numpy as np

from simulate_joint_events import load_dataframe, draw_sample
from simulate_equal_candidate_pairs import (
    group_by_scope, build_group_probabilities, build_turnout_probabilities,
    build_row_shrink_parameters,
)

DS = list(range(0, 4))


def near_counts(c1, c2, groups):
    out = np.zeros(len(DS), dtype=np.int64)
    for _, idx in groups:
        cnt = Counter(zip(c1[idx].tolist(), c2[idx].tolist()))
        N = len(idx)
        for di, d in enumerate(DS):
            ordered = 0
            for (a, b), m in cnt.items():
                s = 0
                for da in range(-d, d + 1):
                    for db in range(-d, d + 1):
                        s += cnt.get((a + da, b + db), 0)
                ordered += m * s
            out[di] += (ordered - N) // 2
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="2026")
    ap.add_argument("--sheet", default="시·도지사")
    ap.add_argument("--rows", choices=["advance", "election_day"], default="advance")
    ap.add_argument("--qw", type=float, default=0.7)
    ap.add_argument("--iters", type=int, default=500)
    ap.add_argument("--seed", type=int, default=20260613)
    a = ap.parse_args()

    df, _ = load_dataframe(a.dataset, a.sheet, a.rows, 1)
    gb = group_by_scope(df, "same_sido_gwangju_jeonnam")
    mg = group_by_scope(df, "same_sigungu")
    pr = build_group_probabilities(df, mg, 0.5)
    tp = build_turnout_probabilities(df, mg, 0.5)
    rp = build_row_shrink_parameters(df, mg, pr, tp, a.qw, a.qw, 0.5)

    obs = near_counts(df["candidate_1"].to_numpy(np.int64),
                      df["candidate_2"].to_numpy(np.int64), gb)

    rng = np.random.default_rng(a.seed)
    acc = np.zeros((a.iters, len(DS)), dtype=np.int64)
    for t in range(a.iters):
        sa, sb, _ = draw_sample(rng, df, mg, pr, tp, "row_shrink", rp, True)
        acc[t] = near_counts(sa, sb, gb)

    mean = acc.mean(0)
    q025 = np.quantile(acc, 0.025, 0)
    q975 = np.quantile(acc, 0.975, 0)
    label = {"advance": "관내사전", "election_day": "본투표(선거일)"}[a.rows]
    med_n = int(df["n"].median())
    med_c2 = int(df["candidate_2"].median())
    print(f"[{a.dataset} {a.sheet} {label}] model=row_shrink w={a.qw}, iters={a.iters}, "
          f"rows={len(df)}, 광역권그룹={len(gb)}, 중앙값 n={med_n}, 중앙값 국힘={med_c2}")
    print(f"{'d(표차)':<8}{'실제':>8}{'시뮬평균':>12}{'시뮬95%CI':>18}")
    for i, d in enumerate(DS):
        ci = f"[{q025[i]:.0f}, {q975[i]:.0f}]"
        print(f"{d:<8}{obs[i]:>8}{mean[i]:>12.1f}{ci:>18}")


if __name__ == "__main__":
    main()
