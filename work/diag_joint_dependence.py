"""A와 B의 양의 상관 메커니즘을 수치로 진단.

질문: P(B|A) > P(B) 인 이유.
- E[B] vs E[B | A]  (A 성립 반복에서 B 기대값이 얼마나 커지는가)
- 상관계수
- containment 기여 분리: A를 성립시킨 stem 일치쌍은 B에도 포함되므로,
  B 합계에서 stem 일치쌍 수를 뺀 "stem 제외 광역권 합계" B' 로도 같은 비교.
  B' 에서도 조건부가 올라가면 그것은 순수한 공통요인(포함관계 아님) 효과.
"""

from __future__ import annotations

import numpy as np

from simulate_joint_events import load_dataframe, draw_sample
from simulate_equal_candidate_pairs import (
    group_by_scope,
    build_group_probabilities,
    build_turnout_probabilities,
    build_row_shrink_parameters,
    count_equal_pairs,
)

ITERS = 30000
SEED = 20260611
ALPHA = 0.5
QW = PW = 0.7

df, _ = load_dataframe("2026", "시·도지사", "advance", 1)
groups_a = group_by_scope(df, "same_eupmyeondong_stem")
groups_b = group_by_scope(df, "same_sido_gwangju_jeonnam")
model_groups = group_by_scope(df, "same_sigungu")
probs = build_group_probabilities(df, model_groups, ALPHA)
turnout = build_turnout_probabilities(df, model_groups, ALPHA)
row_params = build_row_shrink_parameters(df, model_groups, probs, turnout, QW, PW, ALPHA)

rng = np.random.default_rng(SEED)
ca = np.empty(ITERS, dtype=np.int64)
cb = np.empty(ITERS, dtype=np.int64)
for t in range(ITERS):
    sa, sb, kb = draw_sample(rng, df, model_groups, probs, turnout, "row_shrink", row_params, True)
    ca[t], _, _ = count_equal_pairs(sa, sb, groups_a, kb)
    cb[t], _, _ = count_equal_pairs(sa, sb, groups_b, kb)

A = ca >= 1
cb_excl = cb - ca  # 광역권 합계에서 stem 일치쌍 수를 제거 (containment 분리)

print(f"iters={ITERS}")
print(f"P(A)={A.mean():.4f}  P(B>=8)={(cb>=8).mean():.4f}  P(B>=8|A)={(cb[A]>=8).mean():.4f}")
print()
print(f"E[B]        = {cb.mean():.3f}")
print(f"E[B | A]    = {cb[A].mean():.3f}   (A 성립 반복: {A.sum()}개)")
print(f"E[B | ~A]   = {cb[~A].mean():.3f}")
print(f"corr(countA, countB) = {np.corrcoef(ca, cb)[0,1]:.3f}")
print()
print("--- containment 제거: B' = 광역권합계 - stem일치쌍수 ---")
print(f"E[B']       = {cb_excl.mean():.3f}")
print(f"E[B' | A]   = {cb_excl[A].mean():.3f}")
print(f"E[B' | ~A]  = {cb_excl[~A].mean():.3f}")
print(f"corr(countA, B') = {np.corrcoef(ca, cb_excl)[0,1]:.3f}")
