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


def iwa_crosswalk() -> dict[str, str]:
    """Signals' intermediate activity codes, from O*NET 30.2, onto the codes of the release in use.

    Release 30.3 renumbered the intermediate and detailed work activities. The
    detailed activity titles did not change, so each 30.2 detailed activity is
    matched to its 30.3 namesake by title, and a 30.2 intermediate activity
    takes the 30.3 intermediate activity its detailed activities fall under.
    Under 30.2 itself the map is empty and the codes pass through.
    """
    from . import onet_release  # noqa: F401  (configures src.onet for the release on disk)
    import sys
    sys.path.insert(0, str(config.PAPER_ROOT))
    from src import onet
    if onet.ONET_RELEASE <= "30_2":
        return {}
    official, mirrors = sources.ONET_30_2_DWA
    path, _ = fetch.get("onet_30_2_dwa_reference", "crosswalks/onet_30_2_dwa_reference.txt", official, mirrors=mirrors,
                        notes="O*NET 30.2 DWA Reference, kept to translate Signals activity codes")
    old = pd.read_csv(path, sep="\t", dtype=str)
    new = onet.read_file("GWAs to IWAs to DWAs.txt")
    norm = lambda s: s.str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.strip()
    old["key"], new["key"] = norm(old["DWA Title"]), norm(new["DWA Element Name"])
    joined = old.merge(new[["key", "IWA Element ID"]], on="key", how="inner")
    checks.coverage(float(joined["DWA ID"].nunique()), float(old["DWA ID"].nunique()), LAYER,
                    "30.2 detailed activities found by title in the release in use", minimum=0.95)
    ambiguous = int((joined.groupby("IWA ID")["IWA Element ID"].nunique() > 1).sum())
    checks.note(LAYER, "30.2 intermediate activities spanning several new ones", f"{ambiguous}", ambiguous)
    return joined.groupby("IWA ID")["IWA Element ID"].agg(lambda s: s.value_counts().index[0]).to_dict()


def usage_table(values: pd.DataFrame, month: str | None = None, rule: str = "dollar") -> pd.DataFrame:
    shares = activity_shares(month)
    crosswalk = iwa_crosswalk()
    if crosswalk:
        shares["iwa_id"] = shares["iwa_id"].map(crosswalk).fillna(shares["iwa_id"])
    allocated = usage.allocate_activity_shares(shares[["iwa_id", "activity_share"]], values, rule)
    allocated["platform"] = PLATFORM
    allocated["release"] = f"{shares['month'].iloc[0]} ({rule} allocation)"
    allocated["automation_share"] = float("nan")
    allocated["augmentation_share"] = float("nan")
    return allocated[["platform", "release", "task_id", "usage_share", "automation_share", "augmentation_share"]]
