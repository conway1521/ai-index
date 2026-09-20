"""The training pipeline: enrolment and completions by the exposure of the field.

A field of study is scored by the exposure of the occupations its
graduates enter. Two links are available. The NCES crosswalk from CIP to
SOC states where a programme is intended to lead and is many-to-many; the
ACS field-of-degree record shows where graduates of a field actually work
and is the link this programme prefers, since it measures rather than
declares. The crosswalk is used when the ACS extract is not in hand, and
the table says which link produced it.

Enrolment comes from the National Student Clearinghouse's major field
appendix, published twice a year by their own field groupings, which are
mapped to two-digit CIP by a small table committed here. Completions come
from the IPEDS completions file by six-digit CIP and institution, joined to
the institution's state. Enrolment is therefore national and completions
are by state, and both are annual in effect.

The pipeline is the small channel. The capacity layer sizes it against
arrivals from other occupations; this layer only measures it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import checks, spine

LAYER = "pipeline"

# The Clearinghouse's major field labels against two-digit CIP families.
# Kept as data so a change in their labelling is a one-line edit.
NSC_FIELD_TO_CIP2 = {
    "Agriculture": ["01"], "Architecture": ["04"], "Area, Ethnic, Cultural, Gender Studies": ["05"],
    "Biological and Biomedical Sciences": ["26"], "Business": ["52"],
    "Communication and Journalism": ["09"], "Computer and Information Sciences": ["11"],
    "Education": ["13"], "Engineering": ["14"], "Engineering Technologies": ["15"],
    "English Language and Literature": ["23"], "Family and Consumer Sciences": ["19"],
    "Foreign Languages": ["16"], "Health Professions": ["51"], "History": ["54"],
    "Homeland Security, Law Enforcement": ["43"], "Legal Professions": ["22"],
    "Liberal Arts and Sciences, General Studies": ["24"], "Mathematics and Statistics": ["27"],
    "Multi/Interdisciplinary Studies": ["30"], "Natural Resources and Conservation": ["03"],
    "Parks, Recreation, Leisure, Fitness": ["31"], "Personal and Culinary Services": ["12"],
    "Philosophy and Religious Studies": ["38"], "Physical Sciences": ["40"],
    "Precision Production": ["48"], "Psychology": ["42"], "Public Administration and Social Services": ["44"],
    "Social Sciences": ["45"], "Theology and Religious Vocations": ["39"],
    "Transportation and Materials Moving": ["49"], "Visual and Performing Arts": ["50"],
    "Mechanic and Repair Technologies": ["47"], "Construction Trades": ["46"],
    "Science Technologies": ["41"], "Military Technologies": ["29"],
    "Communications Technologies": ["10"], "Library Science": ["25"],
}


def field_exposure_from_crosswalk(measures: pd.DataFrame, employment: pd.Series,
                                  crosswalk: pd.DataFrame | None = None) -> pd.DataFrame:
    """Exposure per six-digit CIP: employment-weighted mean over its SOC destinations."""
    pairs = crosswalk if crosswalk is not None else spine.cip_to_soc()
    joined = pairs.merge(measures, left_on="soc_code", right_index=True, how="left")
    joined["employment"] = joined["soc_code"].map(employment)
    rows = []
    for cip, block in joined.groupby("cip_code"):
        row = {"cip_code": cip, "destinations": int(block["soc_code"].nunique()), "link": "nces_crosswalk"}
        w = block["employment"].fillna(block["employment"].median() if block["employment"].notna().any() else 1.0)
        for measure in measures.columns:
            scored = block[measure].notna()
            row[measure] = float(np.average(block.loc[scored, measure], weights=w[scored])) if scored.any() else np.nan
        rows.append(row)
    out = pd.DataFrame(rows)
    checks.unique_key(out, ["cip_code"], LAYER)
    for measure in measures.columns:
        checks.coverage(int(out[measure].notna().sum()), len(out), LAYER, f"CIP codes scored on {measure}", 0.8)
    return out


def field_exposure_from_acs(fod_occ: pd.DataFrame, measures: pd.DataFrame) -> pd.DataFrame:
    """Exposure per field of degree from where graduates work.

    Schema of fod_occ: fod_code (the ACS field-of-degree code), soc_code,
    weight (persons). The weighted mean of each measure over the graduates'
    occupations is the field's exposure, and the persons on a scored
    occupation are reported.
    """
    joined = fod_occ.merge(measures, left_on="soc_code", right_index=True, how="left")
    rows = []
    for fod, block in joined.groupby("fod_code"):
        row = {"fod_code": fod, "persons": float(block["weight"].sum()), "link": "acs_field_of_degree"}
        for measure in measures.columns:
            scored = block[measure].notna()
            row[measure] = float(np.average(block.loc[scored, measure], weights=block.loc[scored, "weight"])) if scored.any() else np.nan
            row[f"{measure}_persons_scored"] = float(block.loc[scored, "weight"].sum())
        rows.append(row)
    out = pd.DataFrame(rows)
    checks.unique_key(out, ["fod_code"], LAYER)
    return out


def enrolment_by_exposure(nsc: pd.DataFrame, field_exposure: pd.DataFrame,
                          measure: str, cut_quantile: float = 2 / 3) -> pd.DataFrame:
    """Clearinghouse enrolment by term, split by the exposure of the field.

    Schema of nsc: term (e.g. "Spring 2026"), major_field (their label),
    enrolment (headcount). Fields are mapped to two-digit CIP and scored by
    the completions-weighted mean of their six-digit members when the
    exposure table is at six digits, or used as given at two digits.
    """
    fx = field_exposure.copy()
    fx["cip2"] = fx["cip_code"].str.slice(0, 2)
    by2 = fx.groupby("cip2")[measure].mean()
    cut = float(by2.quantile(cut_quantile))
    rows = []
    unmapped = set()
    for _, row in nsc.iterrows():
        cips = NSC_FIELD_TO_CIP2.get(row["major_field"])
        if not cips:
            unmapped.add(row["major_field"])
            continue
        score = float(np.nanmean([by2.get(c, np.nan) for c in cips]))
        rows.append({"term": row["term"], "major_field": row["major_field"], "cip2": ",".join(cips),
                     "enrolment": float(row["enrolment"]), measure: score,
                     "exposed": bool(score >= cut) if not np.isnan(score) else None})
    out = pd.DataFrame(rows)
    checks.note(LAYER, "Clearinghouse fields without a CIP mapping",
                f"{len(unmapped)} labels unmapped: {sorted(unmapped)[:8]}", len(unmapped))
    checks.nonnegative(out["enrolment"], LAYER, "enrolment")
    summary = (out.dropna(subset=["exposed"]).groupby(["term", "exposed"])["enrolment"].sum()
               .unstack("exposed").rename(columns={True: "enrolment_exposed", False: "enrolment_unexposed"}))
    summary["share_exposed"] = summary["enrolment_exposed"] / (summary["enrolment_exposed"] + summary["enrolment_unexposed"])
    checks.within(summary["share_exposed"], 0.0, 1.0, LAYER, "share of enrolment in exposed fields")
    return summary.reset_index()


def completions_by_state(ipeds: pd.DataFrame, institutions: pd.DataFrame,
                         field_exposure: pd.DataFrame, measure: str,
                         cut_quantile: float = 2 / 3) -> pd.DataFrame:
    """IPEDS awards by state and award year, split by field exposure.

    Schema of ipeds: unitid, cip_code (six digits, "11.0101"), award_level,
    awards (count), year. Schema of institutions: unitid, state (two-letter).
    Only the total-across-demographics rows should be passed in.
    """
    fx = field_exposure.set_index("cip_code")[measure]
    cut = float(fx.quantile(cut_quantile))
    frame = ipeds.merge(institutions[["unitid", "state"]], on="unitid", how="left")
    missing_state = frame["state"].isna().mean()
    checks.coverage(1 - float(missing_state), 1.0, LAYER, "awards with an institution state", 0.98)
    frame["score"] = frame["cip_code"].map(fx)
    scored = frame["score"].notna()
    checks.coverage(float(frame.loc[scored, "awards"].sum()), float(frame["awards"].sum()), LAYER,
                    "awards on a scored CIP", 0.8)
    frame = frame[scored].copy()
    frame["exposed"] = frame["score"] >= cut
    out = (frame.groupby(["year", "state", "award_level", "exposed"])["awards"].sum()
           .unstack("exposed").rename(columns={True: "awards_exposed", False: "awards_unexposed"})
           .fillna(0.0).reset_index())
    out["share_exposed"] = out["awards_exposed"] / (out["awards_exposed"] + out["awards_unexposed"])
    checks.within(out["share_exposed"].dropna(), 0.0, 1.0, LAYER, "share of awards in exposed fields")
    checks.nonnegative(out["awards_exposed"], LAYER, "awards")
    return out
