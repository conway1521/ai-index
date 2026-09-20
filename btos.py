"""Firm adoption from the Census Bureau's Business Trends and Outlook Survey.

The download workbooks are wide: one row per geography, question and
answer, one column per biweekly collection cycle, values as percent
strings with "S" for a suppressed cell and "." for a cycle in which the
question was not asked. This module reshapes them to long form, keeps the
AI question's "Yes" share, and dates each cycle by the reference period
from the workbook's own calendar sheet. The question wording changed in
November 2025, from AI "in producing goods or services" to AI "in any of
its business functions", and the two wordings are kept as separate series
because they are not the same quantity.
"""

from __future__ import annotations

import pandas as pd

from . import checks, config, fetch, sources

LAYER = "btos"
BTOS_DIR = config.RAW_DIR / "btos"

AI_QUESTIONS = {
    "In the last two weeks, did this business use Artificial Intelligence (AI) in producing goods or services?": "ai_in_production",
}


def _classify(question: str) -> str | None:
    q = str(question).lower()
    if "artificial intelligence" not in q or "last two weeks" not in q:
        return None
    if "producing goods or services" in q:
        return "ai_in_production"
    if "business functions" in q:
        return "ai_in_any_function"
    return None


def load(name: str = "State.xlsx") -> pd.DataFrame:
    official, mirrors = sources.BTOS[name]
    path, _ = fetch.get(f"btos_{name}", f"btos/{name}", official, mirrors=mirrors,
                        notes="Census download workbook, biweekly cycles as columns")
    estimates = pd.read_excel(path, sheet_name="Response Estimates", dtype=str)
    errors = pd.read_excel(path, sheet_name="Response Standard Errors", dtype=str)
    dates = pd.read_excel(path, sheet_name="Collection and Reference Dates", dtype=str)
    dates["Smpdt"] = dates["Smpdt"].astype(str)
    calendar = dates.set_index("Smpdt")

    by = estimates.columns[0]
    cycles = [c for c in estimates.columns if str(c).isdigit()]
    estimates["series"] = estimates["Question"].map(_classify)
    keep = estimates[estimates["series"].notna() & estimates["Answer"].eq("Yes")]
    long = keep.melt(id_vars=[by, "series"], value_vars=cycles, var_name="cycle", value_name="value")
    long["share_using_ai"] = pd.to_numeric(long["value"].str.rstrip("%"), errors="coerce")
    long["suppressed"] = long["value"].eq("S")
    long = long[long["value"].ne(".")].copy()

    errors["series"] = errors["Question"].map(_classify)
    err = errors[errors["series"].notna() & errors["Answer"].eq("Yes")]
    err_long = err.melt(id_vars=[by, "series"], value_vars=cycles, var_name="cycle", value_name="se")
    err_long["se"] = pd.to_numeric(err_long["se"].astype(str).str.rstrip("%"), errors="coerce")
    err_long = err_long.dropna(subset=["se"]).drop_duplicates([by, "series", "cycle"])
    long = long.merge(err_long[[by, "series", "cycle", "se"]], on=[by, "series", "cycle"], how="left")

    long["ref_start"] = pd.to_datetime(long["cycle"].map(calendar["Ref Start"]), errors="coerce")
    long["ref_end"] = pd.to_datetime(long["cycle"].map(calendar["Ref End"]), errors="coerce")
    long = long.rename(columns={by: by.lower()})
    checks.within(long["share_using_ai"].dropna(), 0.0, 100.0, LAYER, "share using AI")
    checks.coverage(int(long["ref_end"].notna().sum()), len(long), LAYER, "cycles with a reference date", 0.99)
    checks.unique_key(long, [by.lower(), "series", "cycle"], LAYER)
    out = long[[by.lower(), "series", "cycle", "ref_start", "ref_end", "share_using_ai", "se", "suppressed"]]
    return out.sort_values([by.lower(), "series", "cycle"]).reset_index(drop=True)


def state_series() -> pd.DataFrame:
    frame = load("State.xlsx")
    frame = frame.rename(columns={"state": "state_abbr"})
    return frame


def national_series() -> pd.DataFrame:
    return load("National.xlsx")
