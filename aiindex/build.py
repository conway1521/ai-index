"""Run every layer, write the tables, the checks and the manifest.

Each layer runs when its inputs are on disk and is skipped, with a note in
the manifest, when they are not. Nothing here computes; the layers do. The
order is the order of dependence: the spine and the wage bill first,
exposure next, then the usage, outcome, state, pipeline and capacity
layers, which read from those.

Run as:  python -m aiindex.build
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import (acs, btos, capacity, checks, config, cps, exposure, ipeds, onet_release,
               openai, outcomes, pipeline, spine, state, usage, wagebill)
from .manifest import MANIFEST

sys.path.insert(0, str(config.PAPER_ROOT))

SKIPPED: dict[str, str] = {}


def _write(name: str, frame: pd.DataFrame) -> None:
    config.TABLE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(config.TABLE_DIR / f"{name}.csv", index=False)


def _step(label: str):
    def wrap(function):
        def run(*args, **kwargs):
            started = time.time()
            try:
                out = function(*args, **kwargs)
            except FileNotFoundError as error:
                SKIPPED[label] = str(error)
                print(f"  skipped {label}: {error}")
                return None
            print(f"  {label}: {time.time() - started:.0f}s")
            return out
        return run
    return wrap


@_step("spine")
def build_spine() -> dict:
    return {
        "onetsoc": spine.onetsoc_to_soc(),
        "census": spine.census_to_soc(),
        "cip": spine.cip_to_soc(),
        "soc2010": spine.soc_2010_to_2018(),
    }


@_step("wage bill")
def build_wagebill() -> dict:
    wagebill.ensure_files()
    panel = wagebill.harmonise(wagebill.load(grade="mirror"))
    national = wagebill.national(panel)
    states = wagebill.by_state(panel)
    _write("wagebill_national", national)
    _write("wagebill_state_latest", states[states["vintage"] == states["vintage"].max()])
    return {"panel": panel, "national": national, "state": states}


@_step("exposure")
def build_exposure(national: pd.DataFrame) -> pd.DataFrame:
    table = exposure.table()
    latest = national[national["vintage"] == national["vintage"].max()].set_index("soc_code")
    table["employment_latest"] = latest["employment"]
    table["wage_bill_latest"] = latest["bill"]
    _write("exposure_by_occupation", table.reset_index())
    return table


@_step("usage")
def build_usage(national: pd.DataFrame, names: dict[str, str]) -> dict | None:
    from . import aei
    tables = aei.usage_tables()
    if tables is None:
        raise FileNotFoundError("no Anthropic Economic Index release in data/raw/aei")
    from src import gamma as gamma_module
    build = gamma_module.build()
    latest = national[national["vintage"] == national["vintage"].max()].set_index("soc_code")["bill"]
    values = usage.task_values_table(latest)
    task_bundles = usage.task_bundle_matrix(build)
    for rule in ("dollar", "equal"):
        try:
            tables.append(openai.usage_table(values, rule=rule))
        except ConnectionError as error:
            SKIPPED[f"openai {rule}"] = str(error)
    validated = pd.concat([usage.validate_usage(t) for t in tables], ignore_index=True)
    out = usage.readings(validated, values, task_bundles, names)
    _write("usage_reach", out["reach"])
    _write("usage_landing", out["landing"])
    _write("usage_by_occupation", out["by_occupation"])
    return out


@_step("outcomes")
def build_outcomes(national: pd.DataFrame, bundles: pd.DataFrame) -> dict:
    panel = national.merge(bundles, left_on="soc_code", right_index=True, how="inner")
    out = outcomes.build(panel, list(bundles.columns))
    _write("outcomes_pay_series", out["pay"])
    _write("outcomes_quantity_series", out["quantity"])
    # The paper's construction: occupations present in every year.
    fixed = outcomes.build(outcomes.balanced(panel), list(bundles.columns))
    _write("outcomes_pay_series_balanced", fixed["pay"])
    _write("outcomes_quantity_series_balanced", fixed["quantity"])
    _write("outcomes_pay_changes", out["pay_changes"].reset_index().rename(columns={"index": "year"}))
    return out


@_step("state")
def build_state(states: pd.DataFrame, measures: pd.DataFrame) -> dict:
    panel = states[states["vintage"] >= 2019]
    ex = state.exposure_by_state(panel, measures[[c for c in ("eloundou_beta", "felten_aioe", "anthropic_observed") if c in measures.columns]])
    _write("state_exposure", ex)
    changes = []
    for measure in ("eloundou_beta", "felten_aioe", "anthropic_observed"):
        if measure in measures.columns:
            years = sorted(panel["vintage"].unique())
            changes.append(state.realised_change(panel, measures, int(years[-3]), int(years[-1]), measure))
    change = pd.concat(changes, ignore_index=True) if changes else pd.DataFrame()
    _write("state_realised_change", change)
    adoption = state.with_fips(btos.state_series()).dropna(subset=["share_using_ai", "state_fips"])
    annual = pd.concat([
        state.btos_annual(block.rename(columns={"ref_end": "period_end"})).assign(series=series)
        for series, block in adoption.groupby("series")], ignore_index=True)
    annual["state_abbr"] = annual["state_fips"].map({v: k for k, v in state.STATE_FIPS.items()})
    _write("state_adoption_btos", annual)
    _write("state_adoption_btos_biweekly", adoption)
    from . import aei
    usage_states = []
    for path in sorted(aei.AEI_DIR.rglob("aei_raw_claude_ai_*.csv")):
        table = aei.state_usage(path)
        if table is not None:
            usage_states.append(table)
    if usage_states:
        usage_state = state.with_fips(pd.concat(usage_states, ignore_index=True))
        latest = states[states["vintage"] == states["vintage"].max()]
        employment_share = latest.groupby("state_fips")["employment"].sum()
        employment_share = employment_share / employment_share.sum()
        usage_state["employment_share"] = usage_state["state_fips"].map(employment_share)
        usage_state["usage_per_worker_index"] = usage_state["usage_share"] / usage_state["employment_share"]
        _write("state_usage_anthropic", usage_state)
    return {"exposure": ex, "change": change, "adoption": annual}


@_step("pipeline")
def build_pipeline(measures: pd.DataFrame, national: pd.DataFrame) -> dict:
    latest = national[national["vintage"] == national["vintage"].max()].set_index("soc_code")["employment"]
    scored = measures[["eloundou_beta", "felten_aioe"]]
    field_xw = pipeline.field_exposure_from_crosswalk(scored, latest)
    _write("pipeline_field_exposure_crosswalk", field_xw)
    persons = acs.person_file()
    link = acs.field_occupation_link(persons)
    field_acs = pipeline.field_exposure_from_acs(link.rename(columns={"weight": "weight"}), scored)
    _write("pipeline_field_exposure_acs_test_state", field_acs)
    inst = ipeds.institutions(2023)
    frames = []
    for year in (2023, 2024):
        frames.append(ipeds.completions(year))
    awards = pd.concat(frames, ignore_index=True)
    by_state = pipeline.completions_by_state(awards, inst, field_xw, "eloundou_beta")
    _write("pipeline_completions_by_state", by_state)
    nsc_path = config.RAW_DIR / "nsc" / "major_field_appendix.csv"
    grade = "real"
    if not nsc_path.exists():
        # The Clearinghouse host is unreachable from some networks and no copy
        # of the appendix is committed anywhere public. A fixture in its shape
        # stands in, graded as such, so the table exists in its final form.
        nsc_path, grade = config.FIXTURE_DIR / "nsc_major_field_fixture.csv", "fixture"
    MANIFEST.record("nsc_major_field", nsc_path, grade=grade, source_url=str(nsc_path),
                    official_url="https://nscresearchcenter.org/current-term-enrollment-estimates/")
    nsc = pd.read_csv(nsc_path)
    enrolment = pipeline.enrolment_by_exposure(nsc, field_xw, "eloundou_beta")
    _write("pipeline_enrolment_by_exposure", enrolment)
    return {"field_crosswalk": field_xw, "field_acs": field_acs, "completions": by_state, "enrolment": enrolment}


@_step("capacity")
def build_capacity(measures: pd.Series) -> dict | None:
    path = config.RAW_DIR / "flows" / "transition_matrix.csv"
    arrivals_path = config.RAW_DIR / "flows" / "arrivals.csv"
    grade = "real"
    if not path.exists():
        # The flows repository has not published the matrix. The layer runs on
        # the schema fixture so that its tables exist, and the manifest says so.
        path = config.FIXTURE_DIR / "transition_matrix_fixture.csv"
        arrivals_path = config.FIXTURE_DIR / "arrivals_fixture.csv"
        grade = "fixture"
    MANIFEST.record("flows_transition_matrix", path, official_url="flows repository, unpublished",
                    grade=grade, source_url=str(path), notes="year by age band by origin by destination")
    matrix = capacity.validate_matrix(pd.read_csv(path, dtype={"origin": str, "destination": str}))
    cut = float(measures.quantile(2 / 3))
    exit_share = capacity.exit_share(matrix, measures, cut)
    _write("capacity_exit_share", exit_share)
    if arrivals_path.exists():
        MANIFEST.record("flows_arrivals", arrivals_path, official_url="flows repository, unpublished",
                        grade=grade, source_url=str(arrivals_path))
        arrivals = capacity.validate_arrivals(pd.read_csv(arrivals_path, dtype={"occupation": str}))
        _write("capacity_education_channel", capacity.education_channel(arrivals))
    return {"exit_share": exit_share}


@_step("cps gauge")
def build_cps(measures: pd.Series, employment: pd.Series) -> pd.DataFrame | None:
    months = sorted(cps.CPS_DIR.glob("*pub.dat*")) + sorted(cps.CPS_DIR.glob("*.zip"))
    grade = "real"
    if not months:
        # The Census host is unreachable from some networks. The gauge then runs
        # on synthetic months written on the real 2025 layout, so the tables
        # exist in their final shape, and every one of them is graded fixture.
        months = sorted((config.FIXTURE_DIR / "cps").glob("*pub.dat"))
        grade = "fixture"
        if not months:
            raise FileNotFoundError(f"no CPS basic monthly files in {cps.CPS_DIR} and no fixture months")
    for path in months:
        MANIFEST.record(f"cps:{path.name}", path, official_url=cps.OFFICIAL, grade=grade,
                        source_url=None if grade == "real" else str(path))
    layouts = {int(p.name[:4]): p for p in (cps.CPS_DIR / "layouts").glob("*Record_Layout*.txt")}
    for year, path in layouts.items():
        sidecar = path.with_suffix(path.suffix + ".source")
        lg, src = sidecar.read_text().split("\n")[:2] if sidecar.exists() else ("real", cps.OFFICIAL)
        MANIFEST.record(f"cps_layout_{year}", path, official_url=cps.OFFICIAL, grade=lg, source_url=src)
    pairs = spine.census_to_soc()
    scored = cps.score_census_codes(pairs, measures, employment)
    emp_by_census = pairs.assign(e=pairs["soc_code"].map(employment)).groupby("census_code")["e"].sum()
    scored.index = scored.index.astype(str)
    tercile = cps._tercile_of(scored, emp_by_census)
    tercile.index = tercile.index.astype(int)
    frames = []
    for path in months:
        year = 2000 + int(path.name[3:5]) if path.name[3:5].isdigit() else max(layouts)
        layout = layouts.get(year) or layouts[max(layouts)]
        positions = cps.parse_layout(layout.read_text(errors="replace"))
        frames.append(cps.read_month(path, positions))
    persons = pd.concat(frames, ignore_index=True)
    cells = cps.monthly_cells(persons, tercile)
    periods = sorted(cells["period"].unique())
    base = ("2022-01", "2022-12") if grade == "real" else (str(periods[0]), str(periods[min(2, len(periods) - 1)]))
    gauge = cps.gauge(cells, base=base, pooling=3 if grade == "real" else 2)
    _write("cps_young_worker_gauge", gauge)
    _write("cps_cells", cells.assign(period=cells["period"].astype(str)))
    return gauge


def main() -> None:
    started = time.time()
    checks.reset()
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("aiindex build")
    release = onet_release.activate() if onet_release.available() else None
    if release is None:
        onet_release.ensure()
        release = onet_release.activate()
    print(f"  O*NET release {release}")
    from src import bundles as bundle_module

    build_spine()
    wages = build_wagebill()
    measures = build_exposure(wages["national"])
    names = bundle_module.names()
    occupation_bundles = bundle_module.occupation_bundles()
    build_outcomes(wages["national"], occupation_bundles)
    build_usage(wages["national"], names)
    build_state(wages["state"], measures)
    build_pipeline(measures, wages["national"])
    latest = wages["national"][wages["national"]["vintage"] == wages["national"]["vintage"].max()].set_index("soc_code")
    build_capacity(measures["eloundou_beta"].dropna())
    build_cps(measures["eloundou_beta"].dropna(), latest["employment"])

    checks.write()
    MANIFEST.write()
    try:
        print(f"  site readings: {export_site()}")
    except FileNotFoundError as error:
        SKIPPED["site"] = str(error)
    report = {
        "seconds": round(time.time() - started),
        "onet_release": release,
        "grades": MANIFEST.grades(),
        "skipped": SKIPPED,
        "checks": {"passed": int(sum(r["ok"] for r in checks.ROWS)), "rows": len(checks.ROWS)},
    }
    (config.OUTPUT_DIR / "build_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "grades"}, indent=2))
    grades = pd.Series(report["grades"]).value_counts().to_dict()
    print(f"  input grades: {grades}")


if __name__ == "__main__":
    main()


_SMALL = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
          "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]


def _words(n: int) -> str:
    """Small counts in words, as they read in a sentence; larger ones as numerals."""
    return _SMALL[n] if 0 <= n < len(_SMALL) else str(n)


def _published(label: str) -> str:
    """A release label such as '2026-06-26 (2026-05)' as the month it was published, 'June 2026'."""
    return datetime.strptime(str(label).split(" ")[0][:7], "%Y-%m").strftime("%B %Y")


def _fraction(x: float) -> str:
    """A share as the plain fraction nearest to it, for a sentence that should not read like a table."""
    names = [(0.1, "a tenth"), (0.125, "an eighth"), (1 / 6, "a sixth"), (0.2, "a fifth"), (0.25, "a quarter"),
             (1 / 3, "a third"), (0.4, "two fifths"), (0.5, "half")]
    return min(names, key=lambda n: abs(n[0] - x))[1]


def _joined(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def export_site() -> Path:
    """Write the readings the front page shows, from the built tables.

    The page reads ``site/data/readings.json`` and shows what it carries: the
    opening sentence, the paragraphs under "What does this mean", each view's
    numbers with the sentence each one begins, the line on the drawing, and the
    notices the banner plane tows. Every number in them is a cell of a table in
    ``output/tables``, and every sentence is assembled here from those cells, so
    the page cannot say a number, or a claim about one, that the build did not
    write. The Pages workflow publishes the tables beside the page, under
    ``data/tables``, which is where the page's links point.
    """
    from src import bundles as bundle_module

    tables = config.TABLE_DIR
    names = {k: v for k, v in bundle_module.names().items()}
    name = lambda code: names.get(code, code).lower()
    reach = pd.read_csv(tables / "usage_reach.csv")
    anthropic = reach[reach["platform"] == "anthropic"].sort_values("release")
    latest, first = anthropic.iloc[-1], anthropic.iloc[0]
    # the monthly slices carry no collaboration split, so the delegated share comes from the last release that does
    split = anthropic[anthropic["delegated_share"] > 0].iloc[-1]
    landing = pd.read_csv(tables / "usage_landing.csv")
    here = landing[(landing["platform"] == "anthropic") & (landing["release"] == latest["release"])].sort_values("concentration")
    top, low = here.iloc[-1], here.iloc[0]
    pay_all = pd.read_csv(tables / "outcomes_pay_series_balanced.csv")
    qty_all = pd.read_csv(tables / "outcomes_quantity_series_balanced.csv")
    pay, qty = pay_all.iloc[-1], qty_all.iloc[-1]
    completions = pd.read_csv(tables / "pipeline_completions_by_state.csv")
    bach = completions[completions["award_level"] == 5].groupby("year")[["awards_exposed", "awards_unexposed"]].sum()
    share = bach["awards_exposed"] / bach.sum(axis=1)
    year = int(share.index.max())
    degrees, before = float(share.loc[year]) * 100, float(share.loc[year - 1]) * 100 if year - 1 in share.index else None

    wages = round(float(latest["reach_share"]) * 100)
    since = int(pay["first_transition"])
    pay_out = pay["largest_statistic"] >= pay["threshold_95"]
    qty_out = qty["largest_statistic"] >= qty["threshold_95"]
    qty_record = qty_out and int(qty["earlier_windows_at_least"]) == 0
    flagged = [int(y) for y, s_, t_ in zip(qty_all["year"], qty_all["largest_statistic"], qty_all["threshold_95"])
               if s_ > t_ and int(y) != int(qty["year"])]
    others = int(qty["consecutive_relabellings"]) - 1
    odds = round(1 / float(qty["p_largest_consecutive"])) if qty["p_largest_consecutive"] > 0 else None
    toward = "toward" if int(qty["largest_direction"]) > 0 else "away from"

    def further(row) -> str:
        n, of = int(row["earlier_windows_at_least"]), int(row["consecutive_relabellings"]) - 1
        return (f"and no earlier three-year stretch in that record moved as far" if n == 0 else
                f"and {_words(n)} of the {_words(of)} earlier three-year stretches in that record moved as far or further")

    pay_sentence = (f"standard errors is the largest change in pay across the twenty-five skill groups over the last three years, "
                    f"a {'rise' if int(pay['largest_direction']) > 0 else 'fall'} in the pay of {name(pay['largest_bundle'])}, "
                    f"where {pay['threshold_95']:.1f} would be needed to stand out from each group's own record since {since}, {further(pay)}.")
    if qty_out:
        qty_sentence = (f"standard errors is the largest shift in the mix of skills in employment over the last three years, "
                        f"{toward} work that draws on {name(qty['largest_bundle'])}, past the {qty['threshold_95']:.1f} needed to stand out"
                        + (f" and further than any of the {_words(others)} earlier three-year stretches since {since}" if qty_record else "")
                        + (f", although a record of {_words(int(qty['transitions_available']))} years produces a shift that size by chance "
                           f"about one time in {_words(odds)}" if odds else "")
                        + (f", and the same test was passed in {_joined([str(y) for y in flagged])}" if flagged else "") + ".")
    else:
        qty_sentence = (f"standard errors is the largest shift in the mix of skills in employment over the last three years, "
                        f"in work that draws on {name(qty['largest_bundle'])}, where {qty['threshold_95']:.1f} would be needed to stand out, {further(qty)}.")

    views = {
        "bridge": {
            "capline": f"{wages}% of wages go to tasks people bring to AI models · {_published(latest['release'])}",
            "mark": f"{wages}% of wages in tasks people bring",
            "items": [
                {"n": f"{wages}%", "view": "bridge",
                 "s": (f"of all the wages paid in the United States go to work on the tasks people bring to AI models, in the usage record "
                       f"the Anthropic Economic Index published in {_published(latest['release'])}, against {round(float(first['reach_share']) * 100)} percent "
                       f"in its {_published(first['release'])} release, and {round(float(split['delegated_share']) * 100)} percent go to tasks people hand "
                       f"over to the model entirely, on the {_published(split['release'])} record."),
                 "src": f"Anthropic Economic Index, {_published(latest['release'])} · OEWS wages, May {int(pay['year'])}",
                 "tables": ["usage_reach.csv"]},
                {"n": f"{top['concentration']:.1f}×", "view": "bridge",
                 "s": (f"is the weight of that use on {top['bundle'].lower()}, measured against their share of pay and the most of any skill group, "
                       f"while {low['bundle'].lower()} receive {low['concentration']:.1f} times their share."),
                 "src": f"Anthropic Economic Index, {_published(latest['release'])} · O*NET 30.2",
                 "tables": ["usage_landing.csv"]},
            ],
            "how": ("Each conversation in the usage record is matched to the O*NET tasks it touches, each task is weighted by the wages paid "
                    "for it in the latest OEWS release, and the share moves with every usage release, every few months, for the one platform "
                    "whose record the index reads so far."),
        },
        "city": {
            "capline": f"pay {pay['largest_statistic']:.1f}, {pay['threshold_95']:.1f} needed · jobs mix {qty['largest_statistic']:.1f}, {qty['threshold_95']:.1f} needed",
            "mark": f"pay {pay['largest_statistic']:.1f} of {pay['threshold_95']:.1f} needed · jobs {qty['largest_statistic']:.1f} of {qty['threshold_95']:.1f}",
            "items": [
                {"n": f"{pay['largest_statistic']:.1f}", "view": "city", "s": pay_sentence,
                 "src": f"OEWS, May {since - 1} to May {int(pay['year'])}, occupations present in every year",
                 "tables": ["outcomes_pay_series_balanced.csv", "outcomes_pay_changes.csv"]},
                {"n": f"{qty['largest_statistic']:.1f}", "view": "city", "s": qty_sentence,
                 "src": f"OEWS, May {since - 1} to May {int(qty['year'])}, occupations present in every year",
                 "tables": ["outcomes_quantity_series_balanced.csv"]},
            ],
            "how": (f"For each skill group the index takes the last three yearly changes in pay, and in the share of employment, and sets them "
                    f"against that group's own changes since {since}: a change stands out when it passes the level only the most extreme three-year "
                    f"stretches in the record reached, and both the reading and that level are recalculated with each spring release of the wage tables."),
        },
        "valley": {
            "capline": f"{degrees:.1f}% of new degrees in the most exposed fields · {year}",
            "mark": f"{degrees:.1f}% of new degrees in exposed fields",
            "items": [
                {"n": f"{degrees:.1f}%", "view": "valley",
                 "s": (f"of new bachelor's degrees in {year} went to the third of fields whose graduates hold the jobs most exposed to AI models, "
                       f"with each field scored by where its graduates actually work"
                       + (f", against {before:.1f} percent in {year - 1}." if before is not None else ".")),
                 "src": f"IPEDS completions, {year} · field exposure from ACS and the Eloundou task measure",
                 "tables": ["pipeline_completions_by_state.csv", "pipeline_field_exposure_crosswalk.csv"]},
            ],
            "how": ("Degrees come from the IPEDS completions file and each field of study is scored by the exposure of the occupations its "
                    "graduates hold, on the task measure of Eloundou and coauthors, so the share moves once a year, and people who arrive in "
                    "exposed jobs from other occupations will join this view when the flows between occupations are published."),
        },
    }

    # the opening sentence stays short enough for two or three lines: one clause per view, the detail is in the readings below
    if not pay_out and not qty_out:
        city = '<a href="#city" data-view="city">pay and the mix of jobs have stayed within their usual range</a>'
    else:
        city = ('<a href="#city" data-view="city">pay ' + ("has moved past" if pay_out else "has stayed within") + ' its usual range</a>'
                + (f" while the mix of jobs has shifted more than in any three years since {since}" if qty_record else
                   " while the mix of jobs has moved past its usual range" if qty_out else ""))
    lede = (f'The tasks people bring to AI models account for <a href="#bridge" data-view="bridge">{wages} percent of US wages</a>, {city}, '
            f'and <a href="#telescope" data-view="valley">{degrees:.0f} percent of new degrees</a> are in fields that lead to the most exposed jobs.')

    meaning = []
    if not pay_out:
        meaning.append(f"The tasks people bring to AI models are paid about {_fraction(wages / 100)} of all the wages in the United States, while pay "
                       f"across the skills behind them has moved no further over the last three years than in an ordinary stretch of the record, "
                       f"so these models already reach a wide share of paid work and there is no sign yet that employers pay for those skills differently.")
    else:
        meaning.append(f"The tasks people bring to AI models are paid about {_fraction(wages / 100)} of all the wages in the United States, and pay "
                       f"for {name(pay['largest_bundle'])} has moved past its usual range over the last three years, which makes it the reading to watch.")
    if qty_out:
        covid = set(flagged) and set(flagged) <= {2020, 2021}
        meaning.append(f"The reading that stands out is the mix of work: over the last three years employment has moved {toward} jobs that draw "
                       f"on {name(qty['largest_bundle'])}"
                       + (f" by more than in any three-year stretch since {since}" if qty_record else " past its usual range")
                       + (f", although a record of {_words(int(qty['transitions_available']))} years produces a shift that size by chance about one time "
                          f"in {_words(odds)}" if odds else "")
                       + (f", and the same test was passed in {_joined([str(y) for y in flagged])}" + (", when the pandemic reshuffled employment" if covid else "") if flagged else "")
                       + ", so the next release of the wage tables will show whether it holds.")
    meaning.append(f"Degrees are the slow channel and the one policy can count: {degrees:.1f} percent of new bachelor's degrees in {year} went to "
                   f"the most exposed third of fields"
                   + (f", against {before:.1f} percent in {year - 1}" if before is not None else "")
                   + ", and people who move into those jobs from other occupations will join the count once the flows between occupations are published.")

    notes = ["new data coming", f"next wage tables: spring {int(pay['year']) + 2}"]
    if qty_record:
        notes.append(f"jobs mix: largest shift since {since}")

    readings = {
        "built": datetime.now(timezone.utc).strftime("%-d %B %Y"),
        "lede": lede,
        "meaning": meaning,
        "notes": notes,
        "views": views,
        "releases": [{"date": str(r), "reach": round(float(x), 3)} for r, x in zip(anthropic["release"], anthropic["reach_share"])],
    }
    out = config.REPO_ROOT / "site" / "data" / "readings.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(readings, indent=2, ensure_ascii=False))
    return out
