"""Read Anthropic Economic Index releases into the usage schema.

The releases on Hugging Face have changed shape three times. The early
releases ship a task table with an O*NET task identifier and usage,
automation and augmentation percentages. The September 2025 release and
its successors ship one long table with a facet column, where the rows
whose facet is the O*NET task carry the task statement as the cluster
name and the share of usage as the value, with collaboration modes as
separate variables. The June 2026 release moved to calendar-month files
under a new filename convention with a geography level column.

This module reads whatever release files sit in ``data/raw/aei``, detects
which shape each has, and returns tables on the usage schema. Task
statements are joined to O*NET task identifiers through the task
statements file of the release in hand, and the share of usage whose
statement did not match is recorded. Nothing is downloaded here: the
Hugging Face host is fetched by ``ensure``, which records the release
directory it read.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from . import checks, config, onet_release
from .manifest import MANIFEST

LAYER = "aei"
AEI_DIR = config.RAW_DIR / "aei"
OFFICIAL = "https://huggingface.co/datasets/Anthropic/EconomicIndex"
PLATFORM = "anthropic"


def _normalise_text(text: pd.Series) -> pd.Series:
    return (text.astype(str).str.lower().str.replace(r"[^a-z0-9 ]", " ", regex=True)
            .str.replace(r"\s+", " ", regex=True).str.strip())


# Handa et al. (2025) group the collaboration modes: directive and feedback
# loop are automation, validation, task iteration and learning are
# augmentation. The remainder is unclassified and enters neither share.
AUTOMATION_MODES = {"directive", "feedback loop"}
AUGMENTATION_MODES = {"validation", "task iteration", "learning"}


def _release_statements(path: Path) -> pd.DataFrame | None:
    """The task statement list shipped with a release, which the classifier used."""
    candidates = [path.parent / "onet_task_statements.csv",
                  AEI_DIR / "release_2025_09_15" / "onet_task_statements.csv"]
    for candidate in candidates:
        if candidate.exists():
            frame = pd.read_csv(candidate, dtype=str)
            frame["key"] = _normalise_text(frame["Task"])
            frame["task_id"] = pd.to_numeric(frame["Task ID"], errors="coerce").dropna().astype("int64").astype(str)
            return frame.dropna(subset=["task_id"])[["key", "task_id"]].drop_duplicates("key")
    return None


def _task_lookup(path: Path | None = None) -> pd.DataFrame:
    """Task statement text to task identifier.

    The release's own statement list is preferred, because it is the list
    the classifier chose from, and the O*NET release in hand is the
    fallback. Identifiers are stable across O*NET releases.
    """
    shipped = _release_statements(path) if path is not None else None
    onet_release.activate()
    from src import onet
    tasks = onet.task_statements()
    tasks["key"] = _normalise_text(tasks["task_statement"])
    current = tasks[["key", "task_id"]].drop_duplicates("key")
    if shipped is None:
        return current
    return pd.concat([shipped, current[~current["key"].isin(shipped["key"])]], ignore_index=True)


def _release_of(path: Path) -> str:
    """The release directory's date when there is one, else a date in the file name."""
    for text in (path.parent.name, path.name):
        match = re.search(r"release[-_](20\d{2}[-_]\d{2}[-_]\d{2})", text) or \
            re.search(r"(20\d{2}[-_]\d{2}[-_]\d{2}|20\d{2}[-_]\d{2})", text)
        if match:
            return match.group(1).replace("_", "-")
    return path.parent.name


def _join_statements(table: pd.DataFrame, release: str, path: Path | None) -> pd.DataFrame:
    table = table.copy()
    table["key"] = _normalise_text(table["statement"])
    joined = table.merge(_task_lookup(path), on="key", how="left")
    matched = float(joined.loc[joined["task_id"].notna(), "usage_share"].sum() / joined["usage_share"].sum())
    checks.coverage(matched, 1.0, LAYER, f"usage on statements that match an O*NET task {release}", 0.9)
    joined = joined.dropna(subset=["task_id"])
    joined["platform"], joined["release"] = PLATFORM, release
    return joined[["platform", "release", "task_id", "usage_share", "automation_share", "augmentation_share"]]


def _from_task_table(frame: pd.DataFrame, release: str) -> pd.DataFrame:
    """A table that already carries an O*NET task identifier."""
    cols = {c.lower(): c for c in frame.columns}
    task_col = next(cols[c] for c in cols if "task_id" in c or c == "task id")
    usage_col = next((cols[c] for c in cols if "usage" in c and "pct" in c), None) or \
        next(cols[c] for c in cols if "pct" in c or "share" in c or "percent" in c)
    auto_col = next((cols[c] for c in cols if "automation" in c), None)
    aug_col = next((cols[c] for c in cols if "augmentation" in c), None)
    out = pd.DataFrame({
        "platform": PLATFORM, "release": release,
        "task_id": pd.to_numeric(frame[task_col], errors="coerce").dropna().astype("int64").astype(str).reindex(frame.index),
        "usage_share": pd.to_numeric(frame[usage_col], errors="coerce"),
        "automation_share": pd.to_numeric(frame[auto_col], errors="coerce") / 100 if auto_col else float("nan"),
        "augmentation_share": pd.to_numeric(frame[aug_col], errors="coerce") / 100 if aug_col else float("nan"),
    }).dropna(subset=["task_id", "usage_share"])
    return out


def _from_text_table(frame: pd.DataFrame, release: str, path: Path) -> pd.DataFrame:
    """A two-column slice, task text and share, as the monthly release is often redistributed."""
    cols = {c.lower(): c for c in frame.columns}
    text_col = next(cols[c] for c in cols if "task" in c)
    share_col = next(cols[c] for c in cols if "pct" in c or "share" in c)
    table = pd.DataFrame({"statement": frame[text_col].astype(str),
                          "usage_share": pd.to_numeric(frame[share_col], errors="coerce"),
                          "automation_share": float("nan"), "augmentation_share": float("nan")}).dropna(subset=["usage_share"])
    # A monthly release is redistributed one month per file, so the month in
    # the file name is part of the release label.
    month = re.search(r"(20\d{2}-\d{2})(?!-\d{2})", path.stem)
    if month and month.group(1) not in release:
        release = f"{release} ({month.group(1)})"
    return _join_statements(table, release, path)


def _from_long_table(frame: pd.DataFrame, release: str, path: Path, geography: str = "GLOBAL") -> pd.DataFrame:
    """The long facet table of the September 2025 and later releases."""
    cols = {c.lower(): c for c in frame.columns}
    facet, variable, name, value = cols["facet"], cols["variable"], cols["cluster_name"], cols["value"]
    block = frame[frame[cols["geo_id"]].astype(str).eq(geography)] if "geo_id" in cols else frame
    if "platform_and_product" in cols:
        products = block[cols["platform_and_product"]].astype(str)
        consumer = products.str.contains("claude ai", case=False) | products.str.contains("claude_ai", case=False)
        if consumer.any():
            block = block[consumer]
    if "date_start" in cols:
        latest = block[cols["date_start"]].astype(str).max()
        block = block[block[cols["date_start"]].astype(str).eq(latest)]
        release = f"{release} ({latest})"
    block = block.assign(value=pd.to_numeric(block[value], errors="coerce"))

    usage = block[block[facet].eq("onet_task") & block[variable].eq("onet_task_pct")]
    usage = usage.groupby(name)["value"].sum() / 100
    modes = block[block[facet].eq("onet_task::collaboration") & block[variable].eq("onet_task_collaboration_pct")].copy()
    split = modes[name].astype(str).str.rsplit("::", n=1, expand=True)
    modes["statement"], modes["mode"] = split[0], split[1].str.strip().str.lower()
    auto = modes[modes["mode"].isin(AUTOMATION_MODES)].groupby("statement")["value"].sum() / 100
    aug = modes[modes["mode"].isin(AUGMENTATION_MODES)].groupby("statement")["value"].sum() / 100
    table = pd.DataFrame({"usage_share": usage})
    table["automation_share"] = auto.reindex(table.index)
    table["augmentation_share"] = aug.reindex(table.index)
    table.index.name = "statement"
    checks.close(float(table["usage_share"].sum()), 1.0, 1e-6, LAYER, f"task usage shares sum to one {release}")
    return _join_statements(table.reset_index(), release, path)


def state_usage(path: Path) -> pd.DataFrame | None:
    """Usage share by US state from a long-table release, where it carries one."""
    frame = pd.read_csv(path, low_memory=False)
    cols = {c.lower(): c for c in frame.columns}
    if "facet" not in cols:
        return None
    block = frame[frame[cols["facet"]].isin(["state_us", "country-state", "country_state"])
                  & frame[cols["variable"]].eq("usage_pct")].copy()
    if block.empty:
        return None
    geo = block[cols["geo_id"]].astype(str)
    block["state_abbr"] = geo.str.replace(r"^US[-_]", "", regex=True)
    block = block[block["state_abbr"].str.fullmatch(r"[A-Z]{2}")]
    block["usage_share"] = pd.to_numeric(block[cols["value"]], errors="coerce") / 100
    out = block.groupby("state_abbr", as_index=False)["usage_share"].sum()
    out["release"] = _release_of(path)
    checks.close(float(out["usage_share"].sum()), 1.0, 0.02, LAYER, f"state usage shares sum to one {out['release'].iloc[0]}")
    return out[["release", "state_abbr", "usage_share"]]


MONTHLY_COLUMNS = {"date_start", "geo_id", "geo_level", "category_name", "hierarchy_level",
                   "metric_id", "value", "node_external_id"}


def _from_monthly_table(frame: pd.DataFrame, release: str, geography: str = "GLOBAL") -> pd.DataFrame:
    """The calendar-month schema of the June 2026 release and after.

    Rows whose category is the O*NET hierarchy at level zero carry the
    numeric task identifier in node_external_id, so no text join is
    needed. Each month in the file becomes its own release label. The
    metric names are matched by content: a share of usage, and the
    automation and augmentation buckets of the collaboration split.
    """
    cols = {c.lower(): c for c in frame.columns}
    block = frame[frame[cols["category_name"]].astype(str).str.lower().eq("onet")
                  & pd.to_numeric(frame[cols["hierarchy_level"]], errors="coerce").eq(0)].copy()
    if "geo_id" in cols:
        geo = block[cols["geo_id"]].astype(str).str.upper()
        block = block[geo.eq(geography) | geo.eq("GLOBAL") | geo.eq("WORLD")] if geography == "GLOBAL" else block[geo.eq(geography)]
    block["metric"] = block[cols["metric_id"]].astype(str).str.lower()
    block["value"] = pd.to_numeric(block[cols["value"]], errors="coerce")
    block["task_id"] = pd.to_numeric(block[cols["node_external_id"]], errors="coerce")
    block = block.dropna(subset=["task_id"])
    block["task_id"] = block["task_id"].astype("int64").astype(str)
    block["month"] = block[cols["date_start"]].astype(str).str.slice(0, 7)
    tables = []
    for month, part in block.groupby("month"):
        usage = part[part["metric"].isin(["pct", "usage_pct", "onet_task_pct"])].groupby("task_id")["value"].sum()
        auto = part[part["metric"].str.contains("automation")].groupby("task_id")["value"].sum()
        aug = part[part["metric"].str.contains("augmentation")].groupby("task_id")["value"].sum()
        scale = 100.0 if usage.sum() > 1.5 else 1.0
        table = pd.DataFrame({"usage_share": usage / scale})
        table["automation_share"] = (auto / 100.0).reindex(table.index)
        table["augmentation_share"] = (aug / 100.0).reindex(table.index)
        table = table.reset_index()
        table["platform"], table["release"] = PLATFORM, f"{release} ({month})"
        checks.close(float(table["usage_share"].sum()), 1.0, 1e-2, LAYER, f"task usage shares sum to one {release} {month}")
        tables.append(table[["platform", "release", "task_id", "usage_share", "automation_share", "augmentation_share"]])
    return pd.concat(tables, ignore_index=True)


def read_release_file(path: Path) -> pd.DataFrame | None:
    frame = pd.read_csv(path, low_memory=False)
    lowered = {c.lower() for c in frame.columns}
    release = _release_of(path)
    if MONTHLY_COLUMNS <= lowered:
        return _from_monthly_table(frame, release)
    if any("task_id" in c or c == "task id" for c in lowered) and not {"facet", "variable"} <= lowered:
        return _from_task_table(frame, release)
    if {"facet", "variable", "cluster_name", "value"} <= lowered:
        return _from_long_table(frame, release, path)
    if any("task" in c for c in lowered) and any("pct" in c or "share" in c for c in lowered) and len(lowered) <= 3:
        return _from_text_table(frame, release, path)
    return None


def usage_tables() -> list[pd.DataFrame] | None:
    AEI_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in AEI_DIR.rglob("*.csv")
                   if not p.name.startswith(".") and "onet_task_statements" not in p.name)
    tables = []
    for path in files:
        table = read_release_file(path)
        if table is None or table.empty:
            continue
        sidecar = path.with_suffix(path.suffix + ".source")
        grade, source = ("real", OFFICIAL)
        if sidecar.exists():
            grade, source = sidecar.read_text().split("\n")[:2]
        MANIFEST.record(f"aei:{path.relative_to(AEI_DIR)}", path, official_url=OFFICIAL, grade=grade,
                        source_url=source)
        tables.append(table)
    return tables or None
