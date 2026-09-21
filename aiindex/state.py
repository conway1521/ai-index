"""The state layer, at annual cadence, in three columns that are never added.

Exposure: the share of a state's wage bill on occupations above a cut of
each exposure measure, from the OEWS state files, one table per measure.
This is a composition of a national score with a state's occupational mix
and it is precise. Adoption: the Census Bureau's biweekly share of firms
using AI in production, by state, averaged to the calendar year. Usage:
the Anthropic index's state usage where the release carries it. Change:
the state's realised wage-bill and employment change on exposed against
unexposed occupations between OEWS years, which is where the noise the
paper found in state cells lives, so it is written with the number of
occupation cells behind it and is not the headline of this layer.

No composite is written. A state gets three or four numbers in their own
units, each traceable to its file.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import checks, config

LAYER = "state"


def exposure_by_state(state_bill: pd.DataFrame, measures: pd.DataFrame,
                      cut_quantile: float = 2 / 3) -> pd.DataFrame:
    """Share of each state's wage bill above the national employment-weighted cut."""
    latest = state_bill[state_bill["vintage"] == state_bill["vintage"].max()]
    rows = []
    for measure in measures.columns:
        score = measures[measure].dropna()
        national = latest.groupby("soc_code")["employment"].sum()
        aligned = pd.concat([score.rename("m"), national.rename("w")], axis=1, join="inner").sort_values("m")
        cumulative = aligned["w"].cumsum() / aligned["w"].sum()
        cut = float(aligned.loc[cumulative > cut_quantile, "m"].iloc[0])
        exposed = set(aligned.index[aligned["m"] >= cut])
        for (year, state), block in state_bill.groupby(["vintage", "state_fips"]):
            scored = block["soc_code"].isin(score.index)
            covered = float(block.loc[scored, "bill"].sum())
            total = float(block["bill"].sum())
            above = float(block.loc[block["soc_code"].isin(exposed), "bill"].sum())
            rows.append({"vintage": int(year), "state_fips": state, "measure": measure,
                         "cut": cut, "wage_bill_usd": total,
                         "share_of_bill_scored": covered / total if total else np.nan,
                         "share_of_bill_exposed": above / covered if covered else np.nan,
                         "occupations": int(len(block))})
    out = pd.DataFrame(rows)
    checks.within(out["share_of_bill_exposed"].dropna(), 0.0, 1.0, LAYER, "share of bill exposed")
    checks.unique_key(out, ["vintage", "state_fips", "measure"], LAYER)
    for measure, block in out.groupby("measure"):
        checks.coverage(float(block["share_of_bill_scored"].median()), 1.0, LAYER,
                        f"median state wage bill scored, {measure}", 0.8)
    return out


def realised_change(state_bill: pd.DataFrame, measures: pd.DataFrame,
                    start: int, end: int, measure: str,
                    cut_quantile: float = 2 / 3) -> pd.DataFrame:
    """Exposed against unexposed wage and employment growth by state, with cell counts."""
    score = measures[measure].dropna()
    a = state_bill[state_bill["vintage"] == start].set_index(["state_fips", "soc_code"])
    b = state_bill[state_bill["vintage"] == end].set_index(["state_fips", "soc_code"])
    common = a.index.intersection(b.index)
    a, b = a.loc[common], b.loc[common]
    frame = pd.DataFrame({
        "state_fips": [i[0] for i in common], "soc_code": [i[1] for i in common],
        "emp_a": a["employment"].to_numpy(), "emp_b": b["employment"].to_numpy(),
        "wage_a": a["wage"].to_numpy(), "wage_b": b["wage"].to_numpy(),
    })
    frame["score"] = frame["soc_code"].map(score)
    frame = frame.dropna(subset=["score"])
    national = frame.groupby("soc_code")["emp_a"].sum()
    aligned = pd.concat([score.rename("m"), national.rename("w")], axis=1, join="inner").sort_values("m")
    cumulative = aligned["w"].cumsum() / aligned["w"].sum()
    cut = float(aligned.loc[cumulative > cut_quantile, "m"].iloc[0])
    frame["exposed"] = frame["score"] >= cut
    rows = []
    for state, block in frame.groupby("state_fips"):
        row = {"state_fips": state, "start": start, "end": end, "measure": measure,
               "cells_exposed": int(block["exposed"].sum()), "cells_unexposed": int((~block["exposed"]).sum())}
        for label, sub in (("exposed", block[block["exposed"]]), ("unexposed", block[~block["exposed"]])):
            if len(sub) == 0:
                row[f"employment_growth_{label}"] = np.nan
                row[f"wage_growth_{label}"] = np.nan
                continue
            row[f"employment_growth_{label}"] = float(np.log(sub["emp_b"].sum() / sub["emp_a"].sum()) / (end - start))
            w = sub["emp_a"].to_numpy()
            growth = np.log(sub["wage_b"].to_numpy() / sub["wage_a"].to_numpy()) / (end - start)
            row[f"wage_growth_{label}"] = float(np.average(growth, weights=w))
            row[f"wage_growth_{label}_se"] = float(np.sqrt(np.average((growth - row[f"wage_growth_{label}"]) ** 2, weights=w) / max(len(sub) - 1, 1)))
        row["employment_growth_gap"] = row["employment_growth_exposed"] - row["employment_growth_unexposed"]
        row["wage_growth_gap"] = row["wage_growth_exposed"] - row["wage_growth_unexposed"]
        rows.append(row)
    out = pd.DataFrame(rows)
    checks.unique_key(out, ["state_fips", "start", "end", "measure"], LAYER)
    checks.note(LAYER, f"realised change cells {start}-{end} {measure}",
                f"median exposed cells per state {out['cells_exposed'].median():.0f}, "
                f"median unexposed {out['cells_unexposed'].median():.0f}")
    return out


def btos_annual(btos: pd.DataFrame) -> pd.DataFrame:
    """Biweekly BTOS state shares of firms using AI, averaged to the calendar year.

    The input schema is state_fips, period_end (a date), share_using_ai in
    percent, as reshaped from the Census download; the reshape lives with the
    ingestion because the Census files are wide with one column per period.
    """
    frame = btos.copy()
    frame["period_end"] = pd.to_datetime(frame["period_end"])
    frame["year"] = frame["period_end"].dt.year
    checks.within(frame["share_using_ai"], 0.0, 100.0, LAYER, "BTOS share using AI")
    out = (frame.groupby(["state_fips", "year"], as_index=False)
           .agg(share_using_ai=("share_using_ai", "mean"), periods=("period_end", "nunique")))
    checks.unique_key(out, ["state_fips", "year"], LAYER)
    return out


def anthropic_state(usage_state: pd.DataFrame) -> pd.DataFrame:
    """Per-capita usage by state from the Anthropic release, passed through with a check.

    Schema: release, state_fips, usage_share (share of US usage), population_share,
    from the release's geographic table; the ratio is the index Anthropic publishes.
    """
    frame = usage_state.copy()
    frame["usage_per_capita_index"] = frame["usage_share"] / frame["population_share"]
    checks.nonnegative(frame["usage_per_capita_index"], LAYER, "usage per capita index")
    checks.unique_key(frame, ["release", "state_fips"], LAYER)
    return frame


# Postal abbreviation to FIPS, so that BTOS (abbreviations) and OEWS (FIPS)
# key on the same state column.
STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10",
    "DC": "11", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35",
    "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56", "PR": "72", "GU": "66", "VI": "78",
}


def with_fips(frame: pd.DataFrame, column: str = "state_abbr") -> pd.DataFrame:
    out = frame.copy()
    out["state_fips"] = out[column].map(STATE_FIPS)
    unmapped = out.loc[out["state_fips"].isna(), column].unique().tolist()
    checks.note(LAYER, "state abbreviations without a FIPS code", f"{unmapped}", len(unmapped))
    return out
