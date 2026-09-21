"""The occupational spine: every classification the index joins on.

Wages are keyed on six-digit 2018 SOC. O*NET rates eight-digit O*NET-SOC
2019 codes, the CPS records four-digit Census 2018 occupation codes, the
education files carry six-digit CIP 2020 codes, and OEWS before May 2019
used the 2010 SOC. Each crosswalk here is loaded from its published file,
reduced to the pair of codes the index needs, and reported on: how many
source codes map, how many map to more than one target, and how many are
left unmapped. A many-to-one map is applied as such; a one-to-many map is
never split by a rule the file does not give, and the affected codes are
listed so the reader can see what was left out.
"""

from __future__ import annotations

import pandas as pd

from . import checks, config, fetch

LAYER = "spine"
XW_DIR = config.RAW_DIR / "crosswalks"

ONETSOC_OFFICIAL = "https://www.onetcenter.org/taxonomy/2019/soc/2019_to_SOC_Crosswalk.csv"
ONETSOC_MIRRORS = (
    "https://raw.githubusercontent.com/ApprenticeshipStandardsDotOrg/ApprenticeshipStandardsDotOrg/main/lib/tasks/files/2019_to_SOC_Crosswalk.csv",
)
CENSUS_OFFICIAL = "https://www2.census.gov/programs-surveys/demo/guidance/industry-occupation/2018-occupation-code-list-and-crosswalk.xlsx"
CIP_OFFICIAL = "https://nces.ed.gov/ipeds/cipcode/Files/CIP2020_SOC2018_Crosswalk.xlsx"
SOC2010_OFFICIAL = "https://www.bls.gov/soc/2018/soc_2010_to_2018_crosswalk.xlsx"


def _report(pairs: pd.DataFrame, source: str, target: str, name: str) -> pd.DataFrame:
    per_source = pairs.groupby(source)[target].nunique()
    one_to_many = per_source[per_source > 1]
    checks.note(LAYER, f"{name}: source codes", f"{len(per_source)} distinct {source} codes", len(per_source))
    checks.note(LAYER, f"{name}: one-to-many", f"{len(one_to_many)} {source} codes map to several {target}",
                len(one_to_many))
    checks.unique_key(pairs, [source, target], LAYER)
    return pairs


def onetsoc_to_soc() -> pd.DataFrame:
    """O*NET-SOC 2019 (eight digits) to 2018 SOC (six digits)."""
    path, _ = fetch.get("crosswalk_onetsoc_2019_to_soc_2018", "crosswalks/onetsoc_2019_to_soc_2018.csv",
                        ONETSOC_OFFICIAL, mirrors=ONETSOC_MIRRORS)
    raw = pd.read_csv(path, dtype=str)
    code = next(c for c in raw.columns if "O*NET-SOC" in c and "Code" in c)
    soc = next(c for c in raw.columns if c.startswith("2018 SOC Code"))
    pairs = pd.DataFrame({"onetsoc_code": raw[code].str.strip(), "soc_code": raw[soc].str.strip()}).drop_duplicates()
    # Every eight-digit code's first seven characters are its six-digit SOC,
    # which the file confirms; the check catches a file that is not this one.
    agree = (pairs["onetsoc_code"].str.slice(0, 7) == pairs["soc_code"]).mean()
    checks.close(float(agree), 1.0, 0.0, LAYER, "O*NET-SOC prefix equals SOC")
    return _report(pairs, "onetsoc_code", "soc_code", "O*NET-SOC to SOC")


def census_to_soc(path=None, soc_universe: pd.Series | None = None) -> pd.DataFrame:
    """Census 2018 occupation code (four digits) to 2018 SOC, one row per pair.

    The Census list gives one SOC entry per Census code. Where a Census code
    gathers several detailed occupations the entry is written with X
    placeholders, "13-20XX" for every detailed code beginning 13-20, and
    those are expanded against the list of detailed 2018 SOC codes from the
    O*NET-SOC crosswalk. Two Census codes carry no SOC equivalent and are
    reported as unmapped. The CPS module weights the SOC exposures within a
    Census code by employment.
    """
    if path is None:
        path, _ = fetch.get("crosswalk_census_2018_to_soc", "crosswalks/census_2018_occupation_crosswalk.xlsx",
                            CENSUS_OFFICIAL, fixture="census_2018_occupation_crosswalk.csv")
    if str(path).endswith(".csv"):
        raw = pd.read_csv(path, dtype=str)
        raw.columns = ["title", "census_code", "soc_entry"][: len(raw.columns)]
    else:
        raw = _read_census_workbook(path)
    raw = raw[raw["census_code"].astype(str).str.fullmatch(r"\d{4}")].copy()
    raw["soc_entry"] = raw["soc_entry"].astype(str).str.strip()
    universe = soc_universe if soc_universe is not None else onetsoc_to_soc()["soc_code"].drop_duplicates()
    universe = pd.Series(sorted(set(universe)))

    rows, unmapped = [], []
    for _, row in raw.iterrows():
        entry = row["soc_entry"]
        if not entry or entry.lower() == "none" or entry == "nan":
            unmapped.append(row["census_code"])
            continue
        for token in [t.strip() for t in entry.replace(";", ",").split(",") if t.strip()]:
            if "X" in token.upper():
                prefix = token.upper().split("X")[0]
                matches = universe[universe.str.startswith(prefix)]
                if matches.empty:
                    unmapped.append(row["census_code"])
                for soc in matches:
                    rows.append((row["census_code"], soc))
            elif token[:7] in set(universe):
                rows.append((row["census_code"], token[:7]))
            elif token.endswith("0") and len(token) == 7:
                # A broad SOC code, ending in zero, stands for its detailed members.
                matches = universe[universe.str.startswith(token[:6])]
                for soc in matches:
                    rows.append((row["census_code"], soc))
            else:
                unmapped.append(row["census_code"])
    pairs = pd.DataFrame(rows, columns=["census_code", "soc_code"]).drop_duplicates()
    checks.note(LAYER, "Census to SOC: unmapped Census codes",
                f"{len(set(unmapped))} Census codes without a detailed SOC match: {sorted(set(unmapped))[:10]}",
                len(set(unmapped)))
    checks.coverage(pairs["census_code"].nunique(), raw["census_code"].nunique(), LAYER,
                    "Census codes mapped to SOC", 0.97)
    return _report(pairs, "census_code", "soc_code", "Census to SOC")


def _read_census_workbook(path) -> pd.DataFrame:
    """The Census list sheet has no header row: title, Census code, SOC entry."""
    sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
    name = next(n for n in sheets if "census occ code list" in n.lower())
    frame = sheets[name].iloc[:, 1:4].copy()
    frame.columns = ["title", "census_code", "soc_entry"]
    return frame.reset_index(drop=True)


def cip_to_soc(path=None) -> pd.DataFrame:
    """CIP 2020 (six digits) to 2018 SOC, the NCES statement of intended destinations."""
    if path is None:
        path, _ = fetch.get("crosswalk_cip_2020_to_soc_2018", "crosswalks/cip_2020_soc_2018.xlsx",
                            CIP_OFFICIAL, fixture="cip_2020_soc_2018.csv")
    if str(path).endswith(".csv"):
        raw = pd.read_csv(path, dtype=str)
    else:
        sheets = pd.read_excel(path, sheet_name=None, dtype=str)
        name = next((n for n in sheets if n.replace(" ", "").upper() == "CIP-SOC"), None)
        raw = sheets[name] if name else pd.concat(sheets.values())
    lowered = {c: str(c).strip().lower() for c in raw.columns}
    cip_col = next(c for c, l in lowered.items() if l.startswith("cip") and "code" in l)
    soc_col = next(c for c, l in lowered.items() if l.startswith("soc") and "code" in l)
    pairs = pd.DataFrame({"cip_code": raw[cip_col].astype(str).str.strip().str.replace(r"[^\d.]", "", regex=True),
                          "soc_code": raw[soc_col].astype(str).str.strip().str.slice(0, 7)})
    pairs = pairs[pairs["cip_code"].str.fullmatch(r"\d{2}\.\d{4}") & pairs["soc_code"].str.match(r"^\d{2}-\d{4}$")]
    pairs = pairs.drop_duplicates()
    return _report(pairs, "cip_code", "soc_code", "CIP to SOC")


def cip_two_digit(cip_code: pd.Series) -> pd.Series:
    return cip_code.str.slice(0, 2)


def soc_2010_to_2018(path=None) -> pd.DataFrame:
    """2010 SOC to 2018 SOC, from the Census Bureau's occupation crosswalk sheet.

    The sheet lists 2010 and 2018 codes side by side, with a split written
    as a 2010 row followed by 2018 rows carrying no 2010 code. Each 2018
    row is attached to the nearest 2010 code above it, which recovers the
    many-to-many pairs. A 2010 code with several 2018 targets is reported
    and, by default, not carried across, since the split of its employment
    is not in the file.
    """
    if path is None:
        path, _ = fetch.get("crosswalk_census_2018_to_soc", "crosswalks/census_2018_occupation_crosswalk.xlsx",
                            CENSUS_OFFICIAL, fixture="census_2018_occupation_crosswalk.csv")
    sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
    name = next(n for n in sheets if "2010 to 2018" in n)
    frame = sheets[name].iloc[:, [0, 3]].copy()
    frame.columns = ["soc_2010", "soc_2018"]
    frame["soc_2010"] = frame["soc_2010"].where(frame["soc_2010"].astype(str).str.match(r"^\d{2}-\d{4}$")).ffill()
    frame = frame[frame["soc_2018"].astype(str).str.match(r"^\d{2}-\d{4}$")]
    pairs = frame.dropna().drop_duplicates()
    pairs = pairs[~pairs["soc_2010"].str.endswith("0000") & ~pairs["soc_2018"].str.endswith("0000")]
    pairs["targets"] = pairs.groupby("soc_2010")["soc_2018"].transform("nunique")
    return _report(pairs, "soc_2010", "soc_2018", "SOC 2010 to 2018")
