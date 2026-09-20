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


def _task_lookup() -> pd.DataFrame:
    """Task statement text to task identifier, for the release in hand."""
    onet_release.activate()
    from src import onet
    tasks = onet.task_statements()
    tasks["key"] = _normalise_text(tasks["task_statement"])
    return tasks[["key", "task_id"]].drop_duplicates("key")


def _release_of(path: Path) -> str:
    """The release directory's date when there is one, else a date in the file name."""
    for text in (path.parent.name, path.name):
        match = re.search(r"release[-_](20\d{2}[-_]\d{2}[-_]\d{2})", text) or \
            re.search(r"(20\d{2}[-_]\d{2}[-_]\d{2}|20\d{2}[-_]\d{2})", text)
        if match:
            return match.group(1).replace("_", "-")
    return path.parent.name


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


def _from_long_table(frame: pd.DataFrame, release: str, geography: str = "GLOBAL") -> pd.DataFrame:
    """The long facet table of the September 2025 and later releases."""
    cols = {c.lower(): c for c in frame.columns}
    facet, variable, name, value = cols["facet"], cols["variable"], cols["cluster_name"], cols["value"]
    block = frame[frame[facet].astype(str).str.lower().eq("onet_task")].copy()
    if "geo_id" in cols:
        geo = block[cols["geo_id"]].astype(str)
        chosen = geography if geography in set(geo) else geo.iloc[0]
        block = block[geo.eq(chosen)]
        checks.note(LAYER, f"geography used {release}", f"rows for geo_id {chosen}", None)
    if "platform_and_product" in cols:
        products = block[cols["platform_and_product"]].astype(str)
        consumer = products.str.contains("claude.ai", case=False) | products.str.contains("claude_ai", case=False)
        if consumer.any():
            block = block[consumer]
    if "date_start" in cols:
        latest = block[cols["date_start"]].astype(str).max()
        block = block[block[cols["date_start"]].astype(str).eq(latest)]
        release = f"{release} {latest}"
    block["value"] = pd.to_numeric(block[value], errors="coerce")
    block["var"] = block[variable].astype(str).str.lower()
    usage = block[block["var"].str.contains("pct") & ~block["var"].str.contains("automation|augmentation|collaboration")]
    usage = usage.groupby(name)["value"].sum()
    auto = block[block["var"].str.contains("automation")].groupby(name)["value"].sum()
    aug = block[block["var"].str.contains("augmentation")].groupby(name)["value"].sum()
    table = pd.DataFrame({"usage_share": usage, "automation_share": auto / 100, "augmentation_share": aug / 100})
    table.index.name = "statement"
    table = table.reset_index()
    table["key"] = _normalise_text(table["statement"])
    lookup = _task_lookup()
    joined = table.merge(lookup, on="key", how="left")
    matched = float(joined.loc[joined["task_id"].notna(), "usage_share"].sum() / joined["usage_share"].sum())
    checks.coverage(matched, 1.0, LAYER, f"usage on statements that match an O*NET task {release}", 0.9)
    joined = joined.dropna(subset=["task_id"])
    joined["platform"], joined["release"] = PLATFORM, release
    return joined[["platform", "release", "task_id", "usage_share", "automation_share", "augmentation_share"]]


def read_release_file(path: Path) -> pd.DataFrame | None:
    frame = pd.read_csv(path, low_memory=False)
    lowered = {c.lower() for c in frame.columns}
    release = _release_of(path)
    if any("task_id" in c for c in lowered):
        return _from_task_table(frame, release)
    if {"facet", "variable", "cluster_name", "value"} <= lowered:
        return _from_long_table(frame, release)
    return None


def usage_tables() -> list[pd.DataFrame] | None:
    AEI_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in AEI_DIR.rglob("*.csv") if not p.name.startswith("."))
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
