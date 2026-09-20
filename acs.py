"""The field-of-degree to occupation link from ACS person records.

Each person with a bachelor's degree reports the field of the degree, and
each employed person reports an occupation in the Census 2018 coding. The
weighted count of persons by field and occupation is the observed link
between what people trained in and what they do, and it is the link the
pipeline layer prefers over the NCES statement of intended destinations.

The test file in hand is one state's one-year file. The national file is
fifty-one of them, or the national person file, on the same layout, so
the code runs unchanged when it arrives.

ACS field-of-degree codes are not CIP codes. Their first two digits name
a field family, and the table below carries each family to the CIP
two-digit family it corresponds to. It is a hand mapping and is marked as
such; it is used only to put ACS-based exposure beside Clearinghouse
enrolment, which the Clearinghouse reports by CIP family.
"""

from __future__ import annotations

import pandas as pd

from . import checks, config, fetch, sources, spine

LAYER = "acs"

FOD_FAMILY_TO_CIP2 = {
    "11": "01", "13": "03", "14": "04", "15": "05", "19": "09", "20": "10", "21": "11",
    "22": "12", "23": "13", "24": "14", "25": "15", "26": "16", "29": "19", "32": "22",
    "33": "23", "34": "24", "35": "25", "36": "26", "37": "27", "38": "29", "40": "30",
    "41": "31", "48": "38", "49": "39", "50": "40", "51": "41", "52": "42", "53": "43",
    "54": "44", "55": "45", "56": "46", "57": "47", "58": "48", "59": "49", "60": "50",
    "61": "51", "62": "52", "64": "54",
}


def person_file(path=None) -> pd.DataFrame:
    if path is None:
        official, mirrors = sources.ACS_PUMS_TEST
        path, _ = fetch.get("acs_pums_test_state", "acs/psam_p27_2022_1yr.csv", official, mirrors=mirrors,
                            notes="one state's one-year person file, a test of the join")
    usecols = ["ST", "PWGTP", "AGEP", "SCHL", "FOD1P", "OCCP", "ESR"]
    raw = pd.read_csv(path, usecols=lambda c: c in usecols, dtype=str)
    for c in ("PWGTP", "AGEP", "SCHL", "FOD1P", "OCCP", "ESR"):
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    checks.nonnegative(raw["PWGTP"], LAYER, "person weight")
    checks.note(LAYER, "weighted persons", f"{raw['PWGTP'].sum() / 1e6:.2f} million in state {raw['ST'].iloc[0]}",
                float(raw["PWGTP"].sum()))
    return raw


def field_occupation_link(persons: pd.DataFrame, pairs: pd.DataFrame | None = None) -> pd.DataFrame:
    """Weighted persons by field of degree and SOC, employed graduates only.

    A Census occupation that spans several SOC codes gives each an equal
    share of the person's weight; the CPS module weights by employment
    instead, and both rules are stated where they are used.
    """
    employed = persons[persons["ESR"].isin([1, 2, 4, 5]) & persons["FOD1P"].notna() & persons["OCCP"].notna()].copy()
    employed["census_code"] = employed["OCCP"].astype(int).astype(str).str.zfill(4)
    employed["fod_code"] = employed["FOD1P"].astype(int).astype(str).str.zfill(4)
    pairs = pairs if pairs is not None else spine.census_to_soc()
    pairs = pairs.assign(share=1.0 / pairs.groupby("census_code")["soc_code"].transform("size"))
    joined = employed.merge(pairs, on="census_code", how="inner")
    checks.coverage(float(joined.drop_duplicates(["fod_code", "census_code", "PWGTP"])["PWGTP"].sum()) if False else
                    float(employed.loc[employed["census_code"].isin(pairs["census_code"]), "PWGTP"].sum()),
                    float(employed["PWGTP"].sum()), LAYER, "graduates on an occupation that maps to SOC", 0.9)
    joined["weight"] = joined["PWGTP"] * joined["share"]
    link = joined.groupby(["fod_code", "soc_code"], as_index=False)["weight"].sum()
    link["fod_family"] = link["fod_code"].str.slice(0, 2)
    link["cip2"] = link["fod_family"].map(FOD_FAMILY_TO_CIP2)
    checks.coverage(int(link["cip2"].notna().sum()), len(link), LAYER, "field families with a CIP family", 0.95)
    checks.close(float(link["weight"].sum()), float(joined.drop_duplicates(subset=employed.columns.tolist())["PWGTP"].sum()) if False else float(employed.loc[employed["census_code"].isin(pairs["census_code"]), "PWGTP"].sum()), 1e-6, LAYER, "link weights add to the graduates they came from")
    return link
