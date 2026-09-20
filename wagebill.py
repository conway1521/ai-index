"""The wage bill by occupation, national and by state, from OEWS releases.

Employment times mean annual wage, in nominal dollars of the release year,
for detailed occupations only. Every layer of the index is expressed as a
share of this quantity, so its construction is checked before anything is
built on it: only rows BLS marks as detailed enter, so no major group or
economy-wide total is counted twice; the sum over states of a national
release is compared with the national file where both exist; and the
share of employment that joins the O*NET occupation list is reported for
each year rather than dropped silently.

BLS refuses automated requests, so the release files are fetched in a
browser and placed in ``aiindex/data/raw/oews/`` under the names BLS gives
them, ``oesm24nat.zip`` and ``oesm24st.zip`` and so on, or their unzipped
spreadsheets. The paper's reader in ``src.oews_history`` parses whichever
of the formats BLS was using that year, and this module reuses it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import checks, config
from .manifest import MANIFEST

sys.path.insert(0, str(config.REPO_ROOT))
from src import oews_history  # noqa: E402

OEWS_DIR = config.RAW_DIR / "oews"
OFFICIAL = "https://www.bls.gov/oes/tables.htm"
LAYER = "wagebill"


def _year_of(name: str) -> int | None:
    lowered = name.lower()
    inside = re.search(r"(?:state|national)_m(\d{4})", lowered)
    if inside:
        return int(inside.group(1))
    outside = re.search(r"oesm(\d{2})(?:st|nat)", lowered)
    return 2000 + int(outside.group(1)) if outside else None


def _scope_of(name: str) -> str | None:
    lowered = name.lower()
    if "nat" in lowered:
        return "national"
    if "st" in lowered or "state" in lowered:
        return "state"
    return None


def available_files(directory: Path = OEWS_DIR) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in directory.iterdir()
                  if p.suffix.lower() in oews_history.READABLE
                  and not p.name.startswith("."))


def read_release(path: Path) -> pd.DataFrame | None:
    """One release as state (or national) by occupation rows with a wage bill."""
    frame = oews_history.read_file(path)
    if frame is None:
        return None
    year, scope = _year_of(path.name), _scope_of(path.name)
    if year is None or scope is None:
        raise ValueError(f"cannot tell the year or scope of {path.name}; keep the BLS name")
    frame["vintage"] = year
    frame["scope"] = scope
    detailed = frame["soc_code"].str.match(r"^\d{2}-\d{4}$", na=False)
    frame = frame[detailed & ~frame["soc_code"].str.endswith("0000")].copy()
    frame["bill"] = frame["employment"] * frame["wage"]
    if scope == "national":
        frame["state_fips"] = "US"
    else:
        frame["state_fips"] = frame["state_fips"].astype(str).str.zfill(2)
    checks.nonnegative(frame["employment"], LAYER, f"employment {path.name}")
    checks.nonnegative(frame["wage"], LAYER, f"wage {path.name}")
    checks.unique_key(frame, ["vintage", "state_fips", "soc_code"], LAYER)
    return frame[["vintage", "scope", "state_fips", "soc_code",
                  "employment", "wage", "bill", "source_file"]]


def load(directory: Path = OEWS_DIR, grade: str = "real") -> pd.DataFrame:
    """Every release in the directory, with a manifest entry for each file."""
    frames = []
    for path in available_files(directory):
        frame = read_release(path)
        if frame is None:
            continue
        MANIFEST.record(f"oews:{path.name}", path, official_url=OFFICIAL, grade=grade,
                        source_url=None if grade == "real" else str(path),
                        notes="fetched in a browser; BLS refuses automated requests")
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["vintage", "scope", "state_fips", "soc_code",
                                     "employment", "wage", "bill", "source_file"])
    return pd.concat(frames, ignore_index=True)


def national(panel: pd.DataFrame) -> pd.DataFrame:
    """National wage bill by occupation and year.

    The national file is used where it exists. Otherwise the state file is
    summed, which undercounts because BLS suppresses some state cells, and
    the undercount is recorded as a check rather than hidden.
    """
    rows = []
    for year, block in panel.groupby("vintage"):
        nat = block[block["scope"] == "national"]
        st = block[block["scope"] == "state"]
        if len(nat):
            out = nat.groupby("soc_code", as_index=False).agg(
                employment=("employment", "sum"), bill=("bill", "sum"))
            out["basis"] = "national file"
            if len(st):
                summed = st.groupby("soc_code")["employment"].sum()
                common = out.set_index("soc_code")["employment"].index.intersection(summed.index)
                ratio = float(summed.loc[common].sum() / out.set_index("soc_code").loc[common, "employment"].sum())
                checks.note(LAYER, f"state sum over national employment {year}",
                            f"states cover {ratio:.1%} of national employment on common occupations",
                            ratio)
        else:
            out = st.groupby("soc_code", as_index=False).agg(
                employment=("employment", "sum"), bill=("bill", "sum"))
            out["basis"] = "sum of states"
        out["wage"] = out["bill"] / out["employment"]
        out["vintage"] = int(year)
        rows.append(out)
    national = pd.concat(rows, ignore_index=True)
    checks.unique_key(national, ["vintage", "soc_code"], LAYER)
    checks.nonnegative(national["bill"], LAYER, "national bill")
    for year, block in national.groupby("vintage"):
        checks.note(LAYER, f"national wage bill {year}",
                    f"{block['bill'].sum() / 1e12:.3f} trillion dollars over "
                    f"{len(block)} occupations, {block['employment'].sum() / 1e6:.1f} million jobs",
                    float(block["bill"].sum()))
    return national[["vintage", "soc_code", "employment", "wage", "bill", "basis"]]


def by_state(panel: pd.DataFrame) -> pd.DataFrame:
    states = panel[panel["scope"] == "state"].copy()
    checks.unique_key(states, ["vintage", "state_fips", "soc_code"], LAYER)
    return states[["vintage", "state_fips", "soc_code", "employment", "wage", "bill"]]


def onet_coverage(national: pd.DataFrame, known: set[str]) -> pd.DataFrame:
    """Share of each year's wage bill on occupations the skill layer knows."""
    joins = national["soc_code"].isin(known)
    grouped = national.assign(joins=joins).groupby("vintage")
    report = pd.DataFrame({
        "occupations": grouped["soc_code"].nunique(),
        "wage_bill_tn": grouped["bill"].sum() / 1e12,
        "share_of_bill_joining": grouped.apply(
            lambda b: b.loc[b["joins"], "bill"].sum() / b["bill"].sum(), include_groups=False),
    }).reset_index()
    for _, row in report.iterrows():
        checks.coverage(row["share_of_bill_joining"], 1.0, LAYER,
                        f"wage bill joining O*NET {int(row['vintage'])}", 0.85)
    return report


def ensure_files() -> list[tuple[Path, str]]:
    """Fetch every OEWS release listed in sources, official host first."""
    from . import fetch, sources

    got = []
    for year, (name, official, mirrors) in sorted(sources.OEWS_NATIONAL.items()):
        path, grade = fetch.get(f"oews_national_{year}", f"oews/{name}", official, mirrors=mirrors,
                                notes="BLS refuses automated requests; a committed copy of the release workbook")
        got.append((path, grade))
    for year, (name, official, mirrors) in sorted(sources.OEWS_STATE.items()):
        path, grade = fetch.get(f"oews_state_{year}", f"oews/{name}", official, mirrors=mirrors,
                                notes="BLS refuses automated requests; a committed copy of the release workbook")
        got.append((path, grade))
    return got


def harmonise(panel: pd.DataFrame, first_2018_year: int = 2019) -> pd.DataFrame:
    """Carry years on the 2010 SOC onto the 2018 coding, one-to-one codes only.

    OEWS moved to the 2018 classification with the May 2019 release. A 2010
    code that maps to exactly one 2018 code is relabelled; a code that
    splits is dropped, and the share of each early year's wage bill dropped
    is recorded rather than patched, as the paper does.
    """
    from . import spine

    early = panel[panel["vintage"] < first_2018_year]
    late = panel[panel["vintage"] >= first_2018_year]
    if early.empty:
        return panel
    crosswalk = spine.soc_2010_to_2018()
    one_to_one = crosswalk[crosswalk["targets"] == 1][["soc_2010", "soc_2018"]]
    # Codes unchanged between the classifications map to themselves.
    unchanged = pd.DataFrame({"soc_2010": late["soc_code"].unique()})
    unchanged["soc_2018"] = unchanged["soc_2010"]
    mapping = pd.concat([one_to_one, unchanged[~unchanged["soc_2010"].isin(crosswalk["soc_2010"])]])
    mapping = mapping.drop_duplicates("soc_2010")
    mapped = early.merge(mapping, left_on="soc_code", right_on="soc_2010", how="left")
    for year, block in mapped.groupby("vintage"):
        kept = block["soc_2018"].notna()
        share = float(block.loc[kept, "bill"].sum() / block["bill"].sum())
        checks.note(LAYER, f"wage bill carried onto 2018 SOC {year}", f"{share:.1%} carried, the rest is codes that split", share)
    mapped = mapped[mapped["soc_2018"].notna()].copy()
    mapped["soc_code"] = mapped["soc_2018"]
    mapped = mapped.drop(columns=["soc_2010", "soc_2018"])
    mapped = mapped.groupby(["vintage", "scope", "state_fips", "soc_code"], as_index=False).agg(
        employment=("employment", "sum"), bill=("bill", "sum"), source_file=("source_file", "first"))
    mapped["wage"] = mapped["bill"] / mapped["employment"]
    return pd.concat([mapped[panel.columns], late], ignore_index=True)
