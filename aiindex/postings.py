"""What employers ask for: the task composition of job ads, from the NLx aggregates.

Meisenbacher, Nestorov and Norlander published monthly aggregates of the job
ads in the National Labor Exchange (doi:10.5281/zenodo.22219027, MIT licence):
for each detailed occupation and month from September 2015, the number of
active jobs and, for each O*NET task their toolkit matched, the number of
those jobs that mention it. Each occupation-month lists only its fifty most
frequent tasks, so a list is complete only where fewer than fifty appear.

Two readings are built from them. The first is for the page: the average
exposure of the tasks employers name, each task weighted by the number of
ads naming it and scored on the Eloundou task measure, computed within each
occupation whose task list is complete in every month and present in every
month, and averaged across those occupations with fixed weights, so that the
reading moves only when what employers ask for within a job moves and not
when the mix of jobs advertised moves. The second is the formal test of the
paper's Appendix B, run by the paper's own code: the gradient of a task's share
of its occupation's ads on its exposure, by quarter against 2019, and the step
at the release of language models against the sixteen months before it, with
the same step placed at every earlier month as its reference.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import checks, config
from .manifest import MANIFEST

sys.path.insert(0, str(config.PAPER_ROOT))
from src import ai_measures, postings_test  # noqa: E402

LAYER = "postings"
NLX_DIR = config.RAW_DIR / "nlx"
OFFICIAL = "https://doi.org/10.5281/zenodo.22219027"
FILES = ("job_tasks_Occ8.tsv", "job_info_Occ8.tsv")


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    for name in FILES:
        path = NLX_DIR / name
        if not path.exists():
            raise FileNotFoundError(f"{path} is not in place; see COLLECT.md")
        MANIFEST.record(f"nlx:{name}", path, official_url=OFFICIAL, grade="real",
                        notes="aggregates of NLx job ads, Meisenbacher, Nestorov and Norlander, MIT licence")
    tasks = pd.read_csv(NLX_DIR / FILES[0], sep="\t", dtype={"task_id": str, "occ8": str})
    info = pd.read_csv(NLX_DIR / FILES[1], sep="\t", dtype={"occ8": str})
    rated = ai_measures.eloundou_tasks().dropna(subset=["beta"])
    beta = rated.groupby("task_id")["beta"].mean()
    checks.note(LAYER, "job-ad task rows", f"{len(tasks):,} rows, {tasks['occ8'].nunique()} occupations, "
                f"{tasks['month_id'].nunique()} months", len(tasks))
    return tasks, info, beta


def period(month_id: pd.Series) -> pd.Series:
    """The files number months as (year - 2000) * 12 + month."""
    return pd.PeriodIndex.from_fields(year=2000 + (month_id - 1) // 12, month=(month_id - 1) % 12 + 1, freq="M")


def asked_exposure(tasks: pd.DataFrame, info: pd.DataFrame, beta: pd.Series) -> tuple[pd.DataFrame, int]:
    """Monthly average exposure of the tasks named in ads, within a fixed set of occupations."""
    months = tasks["month_id"].nunique()
    capped = set(tasks.loc[tasks["task_rank"] >= postings_test.CAP, "occ8"])
    present = info.groupby("occ8")["month_id"].nunique()
    keep = sorted(set(present[present == months].index) - capped)
    rows = tasks[tasks["occ8"].isin(keep) & tasks["task_id"].isin(beta.index)].copy()
    rows["x"] = rows["task_id"].map(beta)
    rows["wx"] = rows["task_num_jobs"] * rows["x"]
    per = rows.groupby(["occ8", "month_id"])[["wx", "task_num_jobs"]].sum()
    per["exposure"] = per["wx"] / per["task_num_jobs"]
    weights = info[info["occ8"].isin(keep)].groupby("occ8")["num_jobs"].mean()
    per = per.reset_index()
    per["w"] = per["occ8"].map(weights)
    series = per.groupby("month_id").apply(lambda g: np.average(g["exposure"], weights=g["w"]), include_groups=False)
    out = pd.DataFrame({"month_id": series.index, "asked_exposure": series.to_numpy()})
    out["period"] = period(out["month_id"]).astype(str)
    checks.within(out["asked_exposure"], 0.0, 1.0, LAYER, "average exposure of tasks named in ads")
    checks.note(LAYER, "occupations in the asked-exposure reading",
                f"{len(keep)} occupations with complete task lists in all {months} months", len(keep))
    return out[["period", "month_id", "asked_exposure"]], len(keep)


def step_statistic(frame: pd.DataFrame, sxx: pd.Series, half: int = postings_test.HALF_WINDOW) -> dict:
    """The step at the release in standard errors, and the size the same step reaches at earlier months.

    Read in the projected direction, a fall in the share of exposed tasks, so
    that it sits beside the pay and employment readings: a statistic and the
    level only the most extreme twentieth of earlier windows reached.
    """
    fit = lambda p: postings_test.estimate(frame, sxx, brk=p, start=p - half, end=p + half - 1, local=True)
    observed = fit(postings_test.RELEASE)
    statistic = -observed["theta_zero"] / observed["se_zero"]
    first = int(frame.index.get_level_values(1).min()) + half
    reference = np.array([-(e["theta_zero"] / e["se_zero"]) for e in map(fit, range(first, postings_test.RELEASE - half + 1))])
    return {"statistic": float(statistic), "threshold_95": float(np.quantile(reference, 0.95)),
            "earlier_windows": int(len(reference)), "earlier_at_least": int((reference >= statistic).sum()),
            "theta": observed["theta_zero"], "se": observed["se_zero"]}


def build() -> dict:
    tasks, info, beta = load()
    asked, occupations = asked_exposure(tasks, info, beta)
    frame, sxx = postings_test.series(tasks, info, beta)
    never = set(info["occ8"]) - set(tasks.loc[tasks["task_rank"] >= postings_test.CAP, "occ8"])
    complete = frame[frame.index.get_level_values(0).isin(never)]
    quarterly = pd.concat({"all": postings_test.quarterly(frame, sxx),
                           "complete_lists": postings_test.quarterly(complete, sxx)}, axis=1)
    quarterly.columns = [f"{a}_{b}" for a, b in quarterly.columns]
    step = pd.DataFrame([{"sample": "all occupations", **postings_test.release_bound(frame, sxx)},
                         {"sample": "complete task lists", **postings_test.release_bound(complete, sxx)}])
    reading = step_statistic(frame, sxx)
    specified = postings_test.estimate(frame, sxx)
    specified.update(postings_test.placebo_rank(frame, sxx, specified))
    checks.note(LAYER, "step at the release against the sixteen months before",
                f"{step.iloc[0]['theta']:.4f} with standard error {step.iloc[0]['se']:.4f}; "
                f"{step.iloc[0]['share_of_reference_at_least_as_negative']:.0%} of earlier windows as negative",
                float(step.iloc[0]["theta"]))
    return {"reading": pd.DataFrame([reading]), "asked": asked, "occupations": occupations, "quarterly": quarterly.reset_index(names="quarter"),
            "step": step, "specified": pd.DataFrame([specified])}
