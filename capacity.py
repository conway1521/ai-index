"""Transition capacity: what refills an exposed occupation and where its people go.

The flow account establishes that arrivals from other occupations run
four to twelve times arrivals from education, so a capacity measure built
on completions counts the small channel. The measure here is built on the
large one and carries the small one beside it at its measured size.

Two readings per exposed occupation, each in its own units:

- Exit share: of the people observed leaving occupation i for another
  occupation, the share whose destination sits below the exposure cut,
  weighted by the flow. A share, in [0, 1].
- Absorption: the number of people the low-exposure destinations of i take
  in a year at the observed transition rate, each destination capped at the
  largest inflow from i on record, which is the shortage-arithmetic rule.
  A headcount per year.

Both need the bilateral transition matrix, year by age band by origin by
destination, which the flows repository has built and not yet published.
This module defines the schema that matrix has to satisfy and validates
whatever file is supplied against it, so the sibling repository's export
drops in without a code change. Until it does, the module runs on a
fixture and every table it writes is graded as such.

Transition rates are national and annual. Applied to a state's stock of an
occupation they give a state capacity on the stated assumption that a
state's workers move between occupations at the national rate.
"""

from __future__ import annotations

import pandas as pd

from . import checks

LAYER = "capacity"

MATRIX_COLUMNS = {
    "year": "int64",
    "age_band": "object",        # e.g. "16-24", "25-34", ..., "65+", or "all"
    "origin": "object",          # occupation code on the flows account's coding
    "destination": "object",
    "flow": "float64",           # weighted persons moving origin -> destination in the year
    "se": "float64",             # replicate-weight standard error of the flow
}

ARRIVALS_COLUMNS = {
    "year": "int64",
    "occupation": "object",
    "from_education": "float64",
    "from_other_occupations": "float64",
    "from_outside_work": "float64",
    "stock": "float64",
}


def validate_matrix(matrix: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in MATRIX_COLUMNS if c not in matrix.columns]
    if missing:
        raise ValueError(f"transition matrix lacks columns {missing}; "
                         f"the schema is {list(MATRIX_COLUMNS)}")
    out = matrix[list(MATRIX_COLUMNS)].copy()
    for column, dtype in MATRIX_COLUMNS.items():
        out[column] = out[column].astype(dtype)
    out = out[out["origin"] != out["destination"]]
    checks.nonnegative(out["flow"], LAYER, "transition flow")
    checks.nonnegative(out["se"], LAYER, "transition flow se")
    checks.unique_key(out, ["year", "age_band", "origin", "destination"], LAYER)
    return out


def validate_arrivals(arrivals: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in ARRIVALS_COLUMNS if c not in arrivals.columns]
    if missing:
        raise ValueError(f"arrivals table lacks columns {missing}")
    out = arrivals[list(ARRIVALS_COLUMNS)].copy()
    for column in ("from_education", "from_other_occupations", "from_outside_work", "stock"):
        checks.nonnegative(out[column], LAYER, column)
    checks.unique_key(out, ["year", "occupation"], LAYER)
    return out


def exit_share(matrix: pd.DataFrame, exposure: pd.Series, cut: float,
               age_band: str = "all") -> pd.DataFrame:
    """Share of each origin's outflow that lands below the exposure cut."""
    block = matrix[matrix["age_band"] == age_band]
    block = block.assign(low=block["destination"].map(exposure) < cut)
    known = block["destination"].isin(exposure.index)
    checks.coverage(float(block.loc[known, "flow"].sum()), float(block["flow"].sum()),
                    LAYER, "outflow to destinations with an exposure score", 0.8)
    block = block[known]
    grouped = block.groupby(["year", "origin"])
    out = pd.DataFrame({
        "outflow": grouped["flow"].sum(),
        "outflow_low_exposure": grouped.apply(lambda b: b.loc[b["low"], "flow"].sum(),
                                              include_groups=False),
    }).reset_index()
    out["exit_share_low_exposure"] = out["outflow_low_exposure"] / out["outflow"]
    checks.within(out["exit_share_low_exposure"].dropna(), 0.0, 1.0, LAYER, "exit share")
    return out


def absorption(matrix: pd.DataFrame, stocks: pd.Series, exposure: pd.Series,
               cut: float, year: int, age_band: str = "all") -> pd.DataFrame:
    """Persons per year the low-exposure destinations of i absorb, capped by history.

    The rate is the mean over years of flow(i -> j) divided by the stock of
    i, the cap is the largest flow(i -> j) on record, and the stock is the
    one supplied, which may be a state's rather than the nation's.
    """
    block = matrix[matrix["age_band"] == age_band]
    history = block.groupby(["origin", "destination"])["flow"].agg(["mean", "max"]).reset_index()
    history["rate"] = history["mean"] / history["origin"].map(stocks)
    history = history[history["destination"].map(exposure) < cut].dropna(subset=["rate"])
    history["absorbed"] = (history["rate"] * history["origin"].map(stocks)).clip(upper=history["max"])
    checks.bounded_by(history["absorbed"], history["max"], LAYER, "absorption against cap")
    out = history.groupby("origin", as_index=False)["absorbed"].sum()
    out["year"] = year
    out["stock"] = out["origin"].map(stocks)
    out["absorbed_share_of_stock"] = out["absorbed"] / out["stock"]
    checks.within(out["absorbed_share_of_stock"], 0.0, 1.0, LAYER, "absorbed share of stock")
    return out


def education_channel(arrivals: pd.DataFrame) -> pd.DataFrame:
    """Arrivals from education as a share of stock and of lateral arrivals."""
    out = arrivals.copy()
    out["education_share_of_stock"] = out["from_education"] / out["stock"]
    out["lateral_over_education"] = out["from_other_occupations"] / out["from_education"].replace(0, float("nan"))
    checks.within(out["education_share_of_stock"], 0.0, 1.0, LAYER, "education arrivals over stock")
    return out
