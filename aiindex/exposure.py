"""Occupation-level exposure measures from their published files.

Two of the paper's measures are served from GitHub and load here without a
mirror: the Eloundou task ratings, which carry an O*NET task identifier and
an O*NET-SOC code on every row, and the Felten ability-based scores by
six-digit SOC. The Anthropic observed-exposure table joins when its release
is in hand. Each measure is reduced to one number per six-digit SOC on a
stated rule, and the rule is the only place a judgement enters: the
Eloundou beta is averaged over an occupation's tasks with equal weights,
which is what the authors do, and the Felten score is used as published.

The point of carrying more than one measure is the finding in the exposure
paper that the choice of measure is a choice of instrument. Every table the
index writes under an exposure cut is written once per measure.
"""

from __future__ import annotations

import pandas as pd

from . import checks, fetch

LAYER = "exposure"

ELOUNDOU_OFFICIAL = "https://github.com/openai/GPTs-are-GPTs/archive/refs/heads/main.zip"
ELOUNDOU_RAW = "https://raw.githubusercontent.com/openai/GPTs-are-GPTs/main/data/full_labelset.tsv"
FELTEN_OFFICIAL = "https://github.com/AIOE-Data/AIOE/archive/refs/heads/main.zip"
FELTEN_RAW = "https://raw.githubusercontent.com/AIOE-Data/AIOE/main/AIOE_DataAppendix.xlsx"


def eloundou_tasks() -> pd.DataFrame:
    """Task by task ratings, with the task identifier as a string key."""
    path, _ = fetch.get("eloundou_full_labelset", "eloundou_full_labelset.tsv",
                        ELOUNDOU_RAW, mirrors=(),
                        notes=f"published archive at {ELOUNDOU_OFFICIAL}")
    frame = pd.read_csv(path, sep="\t")
    frame = frame.dropna(subset=["Task ID"])
    frame["task_id"] = frame["Task ID"].astype("int64").astype(str)
    frame["onetsoc_code"] = frame["O*NET-SOC Code"].astype(str).str.strip()
    frame["soc_code"] = frame["onetsoc_code"].str.slice(0, 7)
    for column in ("alpha", "beta", "gamma"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    checks.within(frame["beta"].dropna(), 0.0, 1.0, LAYER, "eloundou beta")
    checks.unique_key(frame, ["task_id", "onetsoc_code"], LAYER)
    return frame[["task_id", "onetsoc_code", "soc_code", "Task", "alpha", "beta", "gamma"]]


def eloundou_by_occupation() -> pd.Series:
    """Mean beta over an occupation's rated tasks, keyed on six-digit SOC."""
    tasks = eloundou_tasks()
    by_soc = tasks.dropna(subset=["beta"]).groupby("soc_code")["beta"].mean()
    by_soc.name = "eloundou_beta"
    checks.within(by_soc, 0.0, 1.0, LAYER, "eloundou beta by occupation")
    return by_soc


def felten_by_occupation() -> pd.DataFrame:
    """The AIOE score by SOC, and the language-modelling application score."""
    path, _ = fetch.get("felten_aioe", "felten_aioe_data_appendix.xlsx", FELTEN_RAW,
                        notes=f"published archive at {FELTEN_OFFICIAL}")
    sheets = pd.read_excel(path, sheet_name=None)
    name = next(s for s in sheets if "A" in s.split()[-1:] or "occupation" in s.lower())
    frame = sheets[name]
    code_col = next(c for c in frame.columns if "soc" in str(c).lower())
    score_col = next(c for c in frame.columns if str(c).strip().upper() == "AIOE")
    out = pd.DataFrame({
        "soc_code": frame[code_col].astype(str).str.strip().str.slice(0, 7),
        "felten_aioe": pd.to_numeric(frame[score_col], errors="coerce"),
    }).dropna()
    out = out.groupby("soc_code", as_index=False)["felten_aioe"].mean()
    checks.unique_key(out, ["soc_code"], LAYER)
    return out.set_index("soc_code")


def table(anthropic: pd.Series | None = None) -> pd.DataFrame:
    """All measures side by side, one row per six-digit SOC, NaN where absent."""
    frame = pd.concat([eloundou_by_occupation(), felten_by_occupation()], axis=1)
    if anthropic is None:
        anthropic = anthropic_observed()
    if anthropic is not None:
        frame = frame.join(anthropic.rename("anthropic_observed"), how="outer")
    frame.index.name = "soc_code"
    return frame


def terciles(measure: pd.Series, weights: pd.Series) -> pd.Series:
    """Employment-weighted terciles of an exposure measure, 1 low to 3 high.

    Weighted so that each tercile holds a third of jobs rather than a third
    of occupation codes, which is the split the young-worker gauge needs.
    """
    aligned = pd.concat([measure.rename("m"), weights.rename("w")], axis=1, join="inner").dropna()
    aligned = aligned.sort_values("m")
    cumulative = aligned["w"].cumsum() / aligned["w"].sum()
    tercile = pd.Series(1, index=aligned.index)
    tercile[cumulative > 1 / 3] = 2
    tercile[cumulative > 2 / 3] = 3
    return tercile.rename("tercile")


ANTHROPIC_NAME = "job_exposure.csv"


def anthropic_observed() -> pd.Series | None:
    """Anthropic's observed exposure by six-digit SOC 2018, from the labor market tables."""
    from . import sources
    official, mirrors, note = sources.AEI_LABOR_MARKET[ANTHROPIC_NAME]
    try:
        path, _ = fetch.get(f"aei_labor:{ANTHROPIC_NAME}", f"aei_labor_market/{ANTHROPIC_NAME}", official,
                            mirrors=mirrors, notes=note)
    except ConnectionError:
        return None
    frame = pd.read_csv(path, dtype=str)
    cols = {c.lower(): c for c in frame.columns}
    code = next(cols[c] for c in cols if "occ" in c or "soc" in c)
    score = next(cols[c] for c in cols if "exposure" in c)
    out = pd.DataFrame({"soc_code": frame[code].str.strip().str.slice(0, 7),
                        "anthropic_observed": pd.to_numeric(frame[score], errors="coerce")}).dropna()
    out = out.groupby("soc_code")["anthropic_observed"].mean()
    checks.within(out, 0.0, 1.0, LAYER, "anthropic observed exposure")
    return out
