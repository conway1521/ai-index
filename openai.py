"""Read OpenAI Signals work-related message shares into the usage schema.

Signals publishes the share of work-related ChatGPT messages by O*NET
intermediate work activity and month for US consumer accounts. The
activity is coarser than the task: an intermediate work activity holds
several detailed activities and each of those several tasks. The share is
carried down to tasks by the allocation rule in the usage module, dollars
by default, and the release label carries the month and the rule so that
the two allocations can be compared side by side.
"""

from __future__ import annotations

import pandas as pd

from . import checks, config, fetch, sources, usage

LAYER = "openai"
PLATFORM = "openai"


def activity_shares(month: str | None = None,
                    name: str = "usa_share_of_work_related_messages_by_onet_iwa_month.csv") -> pd.DataFrame:
    official, mirrors, note = sources.OPENAI_FILES[name]
    path, _ = fetch.get(f"openai:{name}", f"openai/{name}", official, mirrors=mirrors, notes=note)
    frame = pd.read_csv(path, dtype=str)
    cols = {c.lower(): c for c in frame.columns}
    month_col, iwa_col, share_col = cols["month"], cols["iwa_cleaned"], cols["share_of_messages"]
    frame["month"] = frame[month_col].astype(str).str.slice(0, 7)
    frame["iwa_id"] = frame[iwa_col].astype(str).str.strip()
    frame["activity_share"] = pd.to_numeric(frame[share_col], errors="coerce")
    frame = frame.dropna(subset=["activity_share"])
    chosen = month or frame["month"].max()
    block = frame[frame["month"].eq(chosen)].copy()
    total = float(block["activity_share"].sum())
    if total > 1.5:
        block["activity_share"] = block["activity_share"] / 100
    block["activity_share"] = block["activity_share"] / block["activity_share"].sum()
    checks.note(LAYER, f"activity shares {chosen}", f"{len(block)} activities, raw total {total:.3f} before normalising", total)
    block["month"] = chosen
    return block[["month", "iwa_id", "activity_share"]]


def usage_table(values: pd.DataFrame, month: str | None = None, rule: str = "dollar") -> pd.DataFrame:
    shares = activity_shares(month)
    allocated = usage.allocate_activity_shares(shares[["iwa_id", "activity_share"]], values, rule)
    allocated["platform"] = PLATFORM
    allocated["release"] = f"{shares['month'].iloc[0]} ({rule} allocation)"
    allocated["automation_share"] = float("nan")
    allocated["augmentation_share"] = float("nan")
    return allocated[["platform", "release", "task_id", "usage_share", "automation_share", "augmentation_share"]]
