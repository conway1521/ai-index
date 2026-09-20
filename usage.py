"""Where AI usage lands in the wage bill, by skill bundle and by platform.

Inputs are usage tables on a common schema, one per platform: an O*NET
task identifier, the share of the platform's work-related usage that maps
to that task, and where the platform publishes it, the split of that usage
between automation and augmentation. The Anthropic index publishes this
at the task level. OpenAI publishes shares by intermediate work activity,
which are allocated down to tasks by a stated rule. The open WildChat
index publishes task counts.

The wage bill enters through the paper's own decomposition. An occupation's
wage bill is split across its tasks by frequency-weighted task shares, so
every task carries a value in dollars and the task values of an occupation
add up to its wage bill exactly. Each task's labour input is split across
the 161 descriptors by gamma, whose rows sum to one, and the descriptors
roll up to O*NET's 25 named bundles. So a task's dollars fall on bundles
without loss, and a platform's usage falls on bundles without loss.

Three readings follow, each a share of the same wage bill:

- Reach: dollars in tasks that appear in the platform's usage at all.
- Delegated reach: the same, with each task's dollars scaled by the share
  of its usage the platform classes as automation.
- Landing: the distribution of usage over bundles, compared with the
  distribution of the wage bill over bundles, so a ratio above one means
  usage concentrates on a bundle beyond its weight in pay.

The usage of one platform is a selected sample of the workforce, which is
why all three platforms are carried and the readings are written once per
platform. The tables say where usage lands and nothing about where AI is.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import checks, config

sys.path.insert(0, str(config.REPO_ROOT))
from src import bundles as bundle_module, gamma as gamma_module, onet, task_values  # noqa: E402

LAYER = "usage"

USAGE_COLUMNS = ["platform", "release", "task_id", "usage_share", "automation_share", "augmentation_share"]


def validate_usage(table: pd.DataFrame) -> pd.DataFrame:
    """Normalise a platform's usage table to the common schema and check it."""
    missing = [c for c in USAGE_COLUMNS if c not in table.columns]
    if missing:
        raise ValueError(f"usage table lacks {missing}; schema is {USAGE_COLUMNS}")
    out = table[USAGE_COLUMNS].copy()
    out["task_id"] = out["task_id"].astype(str)
    # Two statements can carry one identifier when a statement was reworded
    # between O*NET releases, so the modes are averaged with usage weights.
    for column in ("automation_share", "augmentation_share"):
        out[f"_{column}_w"] = out[column].notna() * out["usage_share"]
        out[f"_{column}_x"] = out[column].fillna(0.0) * out["usage_share"]
    grouped = out.groupby(["platform", "release", "task_id"], as_index=False).sum(numeric_only=True)
    for column in ("automation_share", "augmentation_share"):
        weight = grouped[f"_{column}_w"]
        grouped[column] = (grouped[f"_{column}_x"] / weight.replace(0.0, np.nan))
    out = grouped[["platform", "release", "task_id", "usage_share", "automation_share", "augmentation_share"]].copy()
    checks.nonnegative(out["usage_share"], LAYER, "usage share")
    totals = out.groupby(["platform", "release"])["usage_share"].transform("sum")
    out["usage_share"] = out["usage_share"] / totals
    checks.shares_sum_to_one(out, ["platform", "release"], "usage_share", LAYER)
    mode = out[["automation_share", "augmentation_share"]].dropna(how="all")
    if len(mode):
        # The source percentages are rounded, so the two modes can sum a
        # hundredth over one; anything beyond that is a schema error.
        checks.within(mode.fillna(0.0).sum(axis=1), 0.0, 1.0 + 1e-2, LAYER,
                      "automation plus augmentation")
    return out


def task_values_table(wage_bill: pd.Series) -> pd.DataFrame:
    """Dollars per task: the occupation's wage bill times the task's frequency share.

    Tasks are keyed on the six-digit SOC; where several O*NET-SOC codes share
    a six-digit code the paper's task_shares averages them, so the shares
    are renormalised to sum to one within the six-digit occupation here.
    """
    shares = task_values.task_shares()
    shares["task_id"] = shares["task_id"].astype(str)
    total = shares.groupby("soc_code")["share_frequency"].transform("sum")
    shares["share"] = shares["share_frequency"] / total
    shares["bill"] = shares["soc_code"].map(wage_bill)
    shares = shares.dropna(subset=["bill"])
    shares["value"] = shares["share"] * shares["bill"]
    checks.shares_sum_to_one(shares, ["soc_code"], "share", LAYER)
    joined = float(shares.groupby("soc_code")["bill"].first().sum())
    checks.coverage(joined, float(wage_bill.sum()), LAYER, "wage bill with task shares", 0.85)
    checks.close(float(shares["value"].sum()), joined, 1e-9, LAYER, "task values add to the joined wage bill")
    return shares[["soc_code", "task_id", "share", "value"]]


def task_bundle_matrix(build: gamma_module.GammaBuild) -> pd.DataFrame:
    """Tasks by 25 bundles, rows summing to one, from gamma over 161 descriptors."""
    descriptors = build.descriptors.copy()
    descriptors["bundle_id"] = descriptors["element_id"].map(bundle_module._group_id)
    incidence = pd.get_dummies(descriptors["bundle_id"]).to_numpy(dtype=float)
    matrix = build.matrix @ incidence
    frame = pd.DataFrame(matrix, columns=sorted(descriptors["bundle_id"].unique()))
    frame.insert(0, "task_id", build.tasks["task_id"].astype(str).to_numpy())
    frame.insert(1, "soc_code", build.tasks["soc_code"].to_numpy())
    frame = frame.groupby(["task_id", "soc_code"], as_index=False).mean()
    bundle_cols = [c for c in frame.columns if c not in ("task_id", "soc_code")]
    row_sums = frame[bundle_cols].sum(axis=1)
    checks.close(float(row_sums.min()), 1.0, 1e-6, LAYER, "task bundle rows sum to one (min)")
    checks.close(float(row_sums.max()), 1.0, 1e-6, LAYER, "task bundle rows sum to one (max)")
    return frame


def readings(usage: pd.DataFrame, values: pd.DataFrame, task_bundles: pd.DataFrame,
             names: dict[str, str]) -> dict[str, pd.DataFrame]:
    """Reach, delegated reach and landing, per platform and release."""
    bundle_cols = [c for c in task_bundles.columns if c not in ("task_id", "soc_code")]
    tasks = values.merge(task_bundles, on=["task_id", "soc_code"], how="inner")
    total_bill = float(values["value"].sum())
    checks.coverage(float(tasks["value"].sum()), total_bill, LAYER, "task values with a gamma row", 0.95)

    bill_by_bundle = (tasks[bundle_cols].multiply(tasks["value"], axis=0)).sum()
    bill_share = bill_by_bundle / bill_by_bundle.sum()

    reach_rows, landing_rows, occupation_rows = [], [], []
    for (platform, release), block in usage.groupby(["platform", "release"]):
        joined = tasks.merge(block, on="task_id", how="left")
        used = joined["usage_share"].fillna(0.0) > 0
        tasks_used = int(joined.loc[used, "task_id"].nunique())
        reached = float(joined.loc[used, "value"].sum())
        auto = joined["automation_share"].fillna(0.0)
        aug = joined["augmentation_share"].fillna(0.0)
        delegated = float((joined["value"] * auto * used).sum())
        augmented = float((joined["value"] * aug * used).sum())
        checks.bounded_by(pd.Series([reached, delegated, augmented]), pd.Series([total_bill] * 3),
                          LAYER, f"reach {platform} {release}")
        matched_usage = float(block.loc[block["task_id"].isin(tasks["task_id"]), "usage_share"].sum())
        checks.note(LAYER, f"usage matched to a valued task {platform} {release}",
                    f"{matched_usage:.1%} of usage share lands on tasks with a value", matched_usage)
        reach_rows.append({
            "platform": platform, "release": release,
            "tasks_used": tasks_used, "tasks_valued": int(tasks["task_id"].nunique()),
            "wage_bill_usd": total_bill,
            "reach_usd": reached, "reach_share": reached / total_bill,
            "delegated_usd": delegated, "delegated_share": delegated / total_bill,
            "augmented_usd": augmented, "augmented_share": augmented / total_bill,
            "usage_share_matched": matched_usage,
        })
        # Landing: usage distributed over bundles, against the wage bill's distribution.
        weights = joined["usage_share"].fillna(0.0).to_numpy()
        landing = (joined[bundle_cols].multiply(weights, axis=0)).sum()
        landing = landing / landing.sum() if landing.sum() > 0 else landing
        reach_by_bundle = (joined.loc[used, bundle_cols].multiply(joined.loc[used, "value"], axis=0)).sum()
        for bundle in bundle_cols:
            landing_rows.append({
                "platform": platform, "release": release,
                "bundle_id": bundle, "bundle": names.get(bundle, bundle),
                "usage_share_on_bundle": float(landing[bundle]),
                "wage_bill_share_on_bundle": float(bill_share[bundle]),
                "concentration": float(landing[bundle] / bill_share[bundle]) if bill_share[bundle] else np.nan,
                "reach_usd_on_bundle": float(reach_by_bundle[bundle]),
                "reach_share_of_bundle_bill": float(reach_by_bundle[bundle] / bill_by_bundle[bundle]) if bill_by_bundle[bundle] else np.nan,
            })
        by_occ = joined.assign(reached=joined["value"] * used, delegated=joined["value"] * auto * used)
        occ = by_occ.groupby("soc_code").agg(bill=("value", "sum"), reached=("reached", "sum"),
                                              delegated=("delegated", "sum")).reset_index()
        occ["platform"], occ["release"] = platform, release
        occ["reach_share"] = occ["reached"] / occ["bill"]
        occ["delegated_share"] = occ["delegated"] / occ["bill"]
        occupation_rows.append(occ)

    landing_frame = pd.DataFrame(landing_rows)
    if len(landing_frame):
        checks.shares_sum_to_one(landing_frame, ["platform", "release"], "usage_share_on_bundle", LAYER, tol=1e-6)
        checks.within(landing_frame["reach_share_of_bundle_bill"].dropna(), 0.0, 1.0 + 1e-9, LAYER,
                      "reach share of bundle bill")
    return {
        "reach": pd.DataFrame(reach_rows),
        "landing": landing_frame,
        "by_occupation": pd.concat(occupation_rows, ignore_index=True) if occupation_rows else pd.DataFrame(),
    }


def observed_exposure(by_occupation: pd.DataFrame, platform: str) -> pd.Series:
    """Reach share by occupation for one platform, the observed-exposure measure."""
    block = by_occupation[by_occupation["platform"] == platform]
    latest = block[block["release"] == block["release"].max()]
    return latest.set_index("soc_code")["reach_share"].rename(f"observed_{platform}")


def allocate_activity_shares(activity_shares: pd.DataFrame, values: pd.DataFrame,
                             rule: str = "dollar") -> pd.DataFrame:
    """Shares by intermediate work activity, allocated to tasks.

    Tasks map to detailed work activities and those to intermediate ones.
    A task in several activities is given to each with equal weight. Within
    an activity the share is allocated to its tasks in proportion to task
    dollars ("dollar") or equally ("equal"). The rule is an assumption and
    both are run so the difference is visible.
    """
    if rule not in ("dollar", "equal"):
        raise ValueError("rule must be 'dollar' or 'equal'")
    crosswalk = onet.tasks_to_dwas()[["task_id", "dwa_id"]].drop_duplicates()
    rollup = onet.dwa_rollup()[["dwa_id", "iwa_id"]].drop_duplicates()
    task_iwa = crosswalk.merge(rollup, on="dwa_id", how="inner")[["task_id", "iwa_id"]].drop_duplicates()
    task_iwa["task_id"] = task_iwa["task_id"].astype(str)
    task_iwa["weight_in_task"] = 1.0 / task_iwa.groupby("task_id")["iwa_id"].transform("size")
    task_value = values.groupby("task_id")["value"].sum()
    task_iwa["value"] = task_iwa["task_id"].map(task_value).fillna(0.0) * task_iwa["weight_in_task"]
    if rule == "equal":
        task_iwa["value"] = task_iwa["weight_in_task"]
    within = task_iwa.groupby("iwa_id")["value"].transform("sum")
    task_iwa["allocation"] = task_iwa["value"] / within.replace(0.0, np.nan)
    merged = task_iwa.merge(activity_shares, on="iwa_id", how="inner")
    merged["usage_share"] = merged["allocation"] * merged["activity_share"]
    matched = float(activity_shares.loc[activity_shares["iwa_id"].isin(task_iwa["iwa_id"]), "activity_share"].sum())
    checks.coverage(matched, float(activity_shares["activity_share"].sum()), LAYER,
                    "activity shares with tasks to receive them", 0.9)
    return merged.groupby("task_id", as_index=False)["usage_share"].sum()
