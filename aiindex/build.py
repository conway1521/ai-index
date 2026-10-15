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

from . import (acs, btos, capacity, checks, config, cps, exposure, ipeds, onet_release, postings,
               openai, outcomes, pipeline, spine, state, usage, wagebill, site_static)
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
    panel = wagebill.harmonise(wagebill.load())
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
    _write("adoption_btos_national", btos.national_series())
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
    _write("pipeline_field_exposure_acs", field_acs)
    inst = ipeds.institutions(2025)
    frames = []
    for year in (2023, 2024, 2025):
        frames.append(ipeds.completions(year))
    awards = pd.concat(frames, ignore_index=True)
    by_state = pipeline.completions_by_state(awards, inst, field_xw, "eloundou_beta")
    _write("pipeline_completions_by_state", by_state)
    nsc_path = config.RAW_DIR / "nsc" / "major_field_appendix.csv"
    grade = "real"
    ctee = sorted((config.RAW_DIR / "nsc").glob("CTEE*CIPGroupEnrollment*.xlsx"))
    if ctee:
        nsc_path = config.OUTPUT_DIR / "tables" / "nsc_cip_family_enrolment.csv"
        pipeline.clearinghouse_cip_families(ctee[-1]).to_csv(nsc_path, index=False)
        MANIFEST.record("nsc_cip_group_enrolment", ctee[-1], grade="real",
                        official_url="https://nscresearchcenter.org/current-term-enrollment-estimates/")
    elif not nsc_path.exists():
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
    months = sorted(cps.CPS_DIR.glob("*pub.dat*")) + sorted(cps.CPS_DIR.glob("*.zip")) + sorted(cps.CPS_DIR.glob("*pub.csv"))
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
        if path.suffix.lower() == ".csv":
            frames.append(cps.read_month(path))
            continue
        year = 2000 + int(path.name[3:5]) if path.name[3:5].isdigit() else max(layouts)
        layout = layouts.get(year) or layouts[max(layouts)]
        positions = cps.parse_layout(layout.read_text(errors="replace"))
        frames.append(cps.read_month(path, positions))
    persons = pd.concat(frames, ignore_index=True)
    cells = cps.monthly_cells(persons, tercile)
    periods = sorted(cells["period"].unique())
    base = ("2022-01", "2022-12") if grade == "real" else (str(periods[0]), str(periods[min(2, len(periods) - 1)]))
    gauge = cps.gauge(cells, base=base, pooling=3 if grade == "real" else 2)
    kept = len(checks.ROWS)
    band = cps.rotation_se(cells, base=base, pooling=3 if grade == "real" else 2)
    del checks.ROWS[kept:]
    _write("cps_young_worker_se", band)
    _write("cps_young_worker_gauge", gauge)
    _write("cps_cells", cells.assign(period=cells["period"].astype(str)))
    if grade == "real" and len(periods) > 24:
        # the last twelve months of data against the months before them, with months relabelled within rotation groups
        treated_from = str(periods[-12])
        # the relabelled draws recompute the gauge a thousand times; their own unit checks are not part of the record
        kept = len(checks.ROWS)
        test = cps.reference_distribution(cells, treated_from, draws=1000)
        del checks.ROWS[kept:]
        test.insert(0, "treated_from", treated_from)
        test.insert(1, "last_period", str(periods[-1]))
        checks.note("cps", "young-worker gauge, last twelve months against the rest",
                    f"{test.iloc[0]['observed_shift']:+.4f} against a threshold of {test.iloc[0]['threshold_95']:.4f}",
                    float(test.iloc[0]["observed_shift"]))
        _write("cps_young_worker_test", test)
    return gauge


@_step("postings")
def build_postings() -> dict:
    out = postings.build()
    _write("postings_step_at_release", out["reading"])
    _write("postings_release_bound", out["step"])
    _write("postings_gradient_quarterly", out["quarterly"])
    _write("postings_specified_test", out["specified"])
    # the average exposure of tasks named in ads moves with which tasks are named as well as with their shares;
    # it is written for inspection and kept off the page until the difference from the gradient is understood
    _write("postings_asked_exposure_monthly", out["asked"])
    return out


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
    build_postings()

    checks.write()
    MANIFEST.write()
    try:
        print(f"  site readings: {export_site(release)}")
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


_SMALL = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
          "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]


# The 25 skill groups as a reader would say them; O*NET's own names (Mental Processes, Work Output) mean little on their own.
_PLAIN = {
    "1.A.1": "reasoning and memory", "1.A.2": "coordination and dexterity", "1.A.3": "physical strength and stamina",
    "1.A.4": "sight and hearing", "2.A.1": "reading, writing and math", "2.A.2": "learning and critical thinking",
    "2.B.1": "working with people", "2.B.2": "complex problem solving", "2.B.3": "technical skills such as programming and repair",
    "2.B.4": "judgment and systems analysis", "2.B.5": "managing time, money and staff",
    "2.C.1": "business and management knowledge", "2.C.10": "transportation knowledge",
    "2.C.2": "manufacturing and production knowledge", "2.C.3": "engineering and technology knowledge",
    "2.C.4": "math and science knowledge", "2.C.5": "health care knowledge", "2.C.6": "education and training knowledge",
    "2.C.7": "arts and humanities knowledge", "2.C.8": "law and public safety knowledge",
    "2.C.9": "communications and media knowledge", "4.A.1": "gathering information",
    "4.A.2": "analyzing information and making decisions", "4.A.3": "physical and computer work",
    "4.A.4": "working with and for other people",
}


# Published work the page draws on, one entry per study, with the link checked against the current version. Each card
# names the studies that bear on it and how: consistent with its reading, finding differently, background to it, or the
# method or data it is built on.
_STUDIES = {
    "alm": ("Autor, Levy and Murnane (2003), Quarterly Journal of Economics", "https://doi.org/10.1162/003355303322552801", "tasks",
            "Jobs are bundles of tasks, and technology substitutes for some and complements others."),
    "aa": ("Acemoglu and Autor (2011), Handbook of Labor Economics", "https://doi.org/10.1016/S0169-7218(11)02410-5", "tasks",
           "The task framework became the standard account of how technology moves wages and employment."),
    "ar18": ("Acemoglu and Restrepo (2018), American Economic Review", "https://doi.org/10.1257/aer.20160696", "tasks",
             "Automation displaces labor from tasks while productivity gains and new tasks bring it back."),
    "ar19": ("Acemoglu and Restrepo (2019), Journal of Economic Perspectives", "https://doi.org/10.1257/jep.33.2.3", "tasks",
             "An exposed task can lose labor without its occupation shrinking, because new tasks reinstate work."),
    "ar22": ("Acemoglu and Restrepo (2022), Econometrica", "https://doi.org/10.3982/ECTA19815", "tasks",
             "Automation of tasks accounts for much of the rise in US wage inequality."),
    "acemoglu25": ("Acemoglu (2025), Economic Policy", "https://doi.org/10.1093/epolic/eiae042", "tasks",
                   "The gains from AI depend on the share of tasks it affects and the cost it saves on them, not on technical exposure alone."),
    "km": ("Katz and Murphy (1992), Quarterly Journal of Economics", "https://doi.org/10.2307/2118323", "tasks",
           "Skill prices can be read off relative wages and relative supplies."),
    "felten": ("Felten, Raj and Seamans (2021), Strategic Management Journal", "https://doi.org/10.1002/smj.3286", "exposure",
               "Score exposure by linking AI applications to the abilities each occupation uses."),
    "webb": ("Webb (2020), working paper", "https://www.michaelwebb.co/webb_ai.pdf", "exposure",
             "Scores exposure by the overlap between patent text and task descriptions."),
    "bmr": ("Brynjolfsson, Mitchell and Rock (2018), AEA Papers and Proceedings", "https://doi.org/10.1257/pandp.20181019", "exposure",
            "Rate tasks for how suitable they are for machine learning."),
    "eloundou": ("Eloundou, Manning, Mishkin and Rock (2024), Science", "https://doi.org/10.1126/science.adj0998", "exposure",
                 "Rate tasks for what language models can do; counting complementary software, just over 46% of jobs have more than half their tasks exposed."),
    "handa": ("Handa and coauthors (2025), Anthropic", "https://arxiv.org/abs/2503.04761", "exposure",
              "Measure observed use from millions of Claude conversations sorted into O*NET tasks."),
    "bls": ("Bureau of Labor Statistics (2026), AI exposure categories", "https://www.bls.gov/emp/publications/ai-exposure-categories.htm", "exposure",
            "Combines five exposure measures across 831 occupations and keeps what AI could do apart from what people use it for."),
    "yale": ("Yale Budget Lab (2026)", "https://budgetlab.yale.edu/topic/artificial-intelligence", "exposure",
             "Exposure measures broadly agree, less so among the most exposed jobs, and there are no significant employment or wage effects so far."),
    "gmyrek": ("Gmyrek, Berg and Bescond (2025), Polish Journal of Economics", "https://econpapers.repec.org/article/sghgosnar/y_3a2025_3ai_3a3_3ap_3a6-30.htm", "exposure",
               "Worldwide, clerical work is the only broad group highly exposed, and augmentation is more likely than automation."),
    "hk": ("Hershbein and Kahn (2018), American Economic Review", "https://doi.org/10.1257/aer.20161570", "ads",
           "Skill requirements in job ads rose within firms and occupations after the Great Recession."),
    "atalay": ("Atalay, Phongthiengtham, Sotelo and Tannenbaum (2020), AEJ: Applied Economics", "https://doi.org/10.1257/app.20190070", "ads",
               "Newspaper ads show the task content of occupations changing over half a century."),
    "dn": ("Deming and Noray (2020), Quarterly Journal of Economics", "https://doi.org/10.1093/qje/qjaa021", "ads",
           "Skill requirements change fastest in technical jobs."),
    "hemelt": ("Hemelt, Hershbein, Martin and Stange (2023), Labour Economics", "https://www.iza.org/publications/dp/14964", "ads",
               "Link college majors to the skills employers ask for, using nearly all online job ads."),
    "mnn": ("Meisenbacher, Nestorov and Norlander (2025), working paper and data", "https://arxiv.org/abs/2510.01470", "ads",
            "Public aggregates of the National Labor Exchange: the tasks, skills and AI content of job ads by occupation."),
    "bbg": ("Berman, Bound and Griliches (1994), Quarterly Journal of Economics", "https://doi.org/10.2307/2118467", "ads",
            "The decomposition into change within occupations and change in the mix of occupations."),
    "chen": ("Chen, Srinivasan and Zakerinia (2025), Harvard Business School", "https://www.library.hbs.edu/working-knowledge/enhance-or-eliminate-how-ai-will-likely-change-these-jobs", "ads",
             "Postings for structured, repetitive occupations fell 13% after ChatGPT's launch, while analytical, technical and creative roles rose 20%."),
    "revelio25": ("Revelio Labs (December 2025 newsletter)", None, "ads",
                  "The share of AI-exposed tasks in job postings fell from 29% in early 2022 to 25.5% by early 2025."),
    "revelio26": ("Revelio Labs AI Labor Market Tracker (August 2026)", "https://www.reveliolabs.com/news/ai-and-work/introduction-the-revelio-ai-labor-market-tracker", "effects",
                  "Employment in the most AI-exposed jobs is down against the least exposed since November 2022, by 19% for workers aged 22 to 25."),
    "dallas": ("Dodini and Smith (2026), Federal Reserve Bank of Dallas", "https://www.dallasfed.org/research/economics/2026/0901", "ads",
               "Job openings fell after ChatGPT in occupations whose tasks AI can automate, mostly in Texas, with effects on recent graduates and students."),
    "lw": ("Liu and Webber (2026), Federal Reserve Board", "https://www.federalreserve.gov/econres/notes/feds-notes/ai-adoption-and-firms-job-posting-behavior-20260327.html", "ads",
           "No reduction in job postings at firms or industries that adopted more AI."),
    "engberg": ("Engberg and coauthors (2026), Applied Economics Letters", "https://ratio.se/publikationer/artificial-intelligence-hiring-and-employment-job-postings-evidence-from-sweden-2", "ads",
                "Swedish establishments more exposed to AI hired more, including for roles that do not use AI."),
    "rinz": ("Rinz (2026), Federal Reserve Bank of Cleveland", "https://doi.org/10.26509/frbc-wp-202624", "effects",
             "Postings in more exposed occupations declined before ChatGPT and leveled off after it; small earnings losses for incumbents from late 2024."),
    "stefanik": ("Štefánik, Lyócsa and Bilka (2023), Social Science Computer Review", "https://doi.org/10.1177/08944393221085705", "ads",
                 "Counts of online job ads improve forecasts of vacancies, employment and unemployment."),
    "tsvetkova": ("Tsvetkova and coauthors (2024), OECD", "https://doi.org/10.1787/c17cae09-en", "ads",
                  "Online postings match official statistics less well by occupation and sector than by region."),
    "humlum": ("Humlum and Vestergaard (2025), NBER Working Paper 33777", "https://www.nber.org/papers/w33777", "effects",
               "Small effects of AI chatbots on earnings and hours among exposed workers in Denmark."),
    "canaries": ("Brynjolfsson, Chandar and Chen (2026 revision), Stanford Digital Economy Lab",
                 "https://digitaleconomy.stanford.edu/publication/canaries-in-the-coal-mine-six-facts-about-the-recent-employment-effects-of-artificial-intelligence/", "effects",
                 "Employment of workers aged 22 to 25 in the most AI-exposed occupations is 19% below where it would be had it kept pace with less-exposed peers."),
    "hampole": ("Hampole, Papanikolaou, Schmidt and Seegmiller (2025), NBER Working Paper 33509", "https://www.nber.org/papers/w33509", "effects",
                "Occupations whose tasks are more exposed to AI see lower demand afterward; overall employment effects are modest."),
    "fm": ("Freund and Mann (2026), Minneapolis Fed Institute Working Paper 114", "https://doi.org/10.21034/iwp.114", "organization",
           "Occupations bundle tasks and automating one shifts weight to the rest: gains at moderate exposure, losses in the most exposed jobs."),
    "korv": ("Krusell, Ohanian, Ríos-Rull and Violante (2000), Econometrica", "https://doi.org/10.1111/1468-0262.00150", "organization",
             "Capital complements skilled labor, so cheaper equipment raises the skill premium."),
    "card": ("Card (2009), American Economic Review", "https://doi.org/10.1257/aer.99.2.1", "organization",
             "Substitution between skill groups determines how a change in supply moves relative wages."),
    "sahin": ("Şahin, Song, Topa and Violante (2014), American Economic Review", "https://doi.org/10.1257/aer.104.11.3529", "matching",
              "Mismatch unemployment measures how far job seekers sit in different occupations from vacancies."),
}
def _study(stance: str, key: str, text: str | None = None) -> dict:
    cite, url, _, summary = _STUDIES[key]
    return {"stance": stance, "cite": cite, "url": url, "text": text or summary}


_RESEARCH = {
    ("bridge", 0): [
        _study("consistent", "handa", "In the first report on these data, about 36% of occupations used AI for at least a quarter of their tasks."),
        _study("background", "eloundou"),
        _study("background", "bls"),
        _study("background", "acemoglu25"),
        _study("method", "handa", "Describe how the Anthropic Economic Index sorts conversations into O*NET tasks, the data this card is built on."),
        _study("method", "aa", "The task framework, which is why use is measured task by task and weighted by what each task is paid."),
    ],
    ("bridge", 2): [
        _study("consistent", "handa", "Software development and writing tasks make up nearly half of all use."),
        _study("background", "gmyrek"),
        _study("background", "felten", "Score exposure from abilities, an alternative to the task measure used on this page."),
        _study("method", "handa", "Describe how the Anthropic Economic Index sorts conversations into O*NET tasks, the data this card is built on."),
    ],
    ("bridge", 1): [
        _study("background", "lw", "Use this survey with job postings and find no reduction in postings at firms or industries that adopted more AI."),
        _study("background", "yale"),
    ],
    ("city", 1): [
        _study("consistent", "humlum"),
        _study("consistent", "yale", "Finds no statistically or economically significant employment or wage effects of AI so far."),
        _study("consistent", "rinz", "A small fall in real earnings, under 1%, for workers who stayed in more exposed US jobs from the second half of "
               "2024, after the last year of these wage tables."),
        _study("background", "fm"),
        _study("background", "ar22"),
        _study("method", "km", "Skill prices read off relative wages, the approach behind pay by skill group."),
        _study("method", "alm"),
    ],
    ("city", 2): [
        _study("background", "hampole"),
        _study("background", "ar19"),
        _study("background", "card"),
        _study("method", "alm", "Jobs as bundles of tasks and skills, which is how employment is assigned to the 25 skill groups."),
    ],
    ("city", 0): [
        _study("consistent", "rinz", "The same timing in commercial job-ad data: ads in more exposed occupations were declining before ChatGPT and "
               "leveled off after it."),
        _study("consistent", "lw"),
        _study("consistent", "engberg"),
        _study("different", "dallas", "Job openings fell after ChatGPT's release in occupations whose tasks AI can automate, mostly in Texas. The "
               "comparison is across occupations; this index compares tasks within the same occupation."),
        _study("different", "chen", "Postings for structured, repetitive occupations fell 13% after ChatGPT's launch, while analytical, technical and "
               "creative roles rose 20%. This too compares across occupations."),
        _study("different", "revelio25", "The share of AI-exposed tasks in job postings fell from 29% in early 2022 to 25.5% by early 2025, which "
               "Revelio reads as firms removing automatable duties from the jobs they post."),
        _study("background", "hk"),
        _study("background", "atalay"),
        _study("background", "tsvetkova"),
        _study("method", "mnn", "The public aggregates of the National Labor Exchange this card reads: how often ads in each occupation name each O*NET task."),
        _study("method", "eloundou", "The exposure score given to each task."),
        _study("method", "bbg"),
    ],
    ("valley", 0): [
        _study("background", "hemelt"),
        _study("method", "eloundou", "The exposure measure used to score fields of study, jobs and tasks across this page."),
    ],
    ("valley", 1): [
        _study("different", "dallas", "Weaker demand for AI-exposed occupations led students at Texas universities to change what they study."),
        _study("method", "eloundou", "The exposure measure used to score each field family, through the jobs its graduates hold."),
    ],
    ("valley", 2): [
        _study("consistent", "canaries"),
        _study("consistent", "revelio26"),
        _study("consistent", "dallas", "The fall in openings for AI-exposed occupations hurt recent graduates of Texas universities."),
        _study("method", "eloundou", "The exposure measure that defines the most exposed third of jobs."),
    ],
}


# Names in the page's sentences that are linked wherever they appear, as patterns and the study each points to.
_LINKS = [
    (r"Eloundou(?:, Manning, Mishkin and Rock \(2024\)| and coauthors)?", "eloundou"),
    (r"Meisenbacher, Nestorov and Norlander", "mnn"),
]


def _links() -> list[dict]:
    return [{"pattern": pattern, "url": _STUDIES[key][1]} for pattern, key in _LINKS]


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


def export_site(release: str) -> Path:
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
    plain = lambda code: _PLAIN.get(code, name(code))
    reach = pd.read_csv(tables / "usage_reach.csv")
    anthropic = reach[reach["platform"] == "anthropic"].sort_values("release")
    # reach counts every published task, so the headline comes from the latest release that publishes
    # all of its use; a release with a reporting threshold is in the table and not in the headline
    complete = anthropic[anthropic["published_use"] >= 0.99]
    latest, first = complete.iloc[-1], complete.iloc[0]
    newest = anthropic.iloc[-1]
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

    # the valley: enrolment by the exposure of the field family, and young workers' place in exposed jobs
    enrol = pd.read_csv(tables / "pipeline_enrolment_by_exposure.csv")
    e_last, e_first = enrol.iloc[-1], enrol.iloc[0]
    enrolled, enrolled_first = float(e_last["share_exposed"]) * 100, float(e_first["share_exposed"]) * 100
    gauge = pd.read_csv(tables / "cps_young_worker_gauge.csv")
    g_last = gauge.iloc[-1]
    young = (1 - float(g_last["young_relative_to_prime"])) * 100
    g_when = datetime.strptime(str(g_last["period"]), "%Y-%m").strftime("%B %Y")
    test_path = tables / "cps_young_worker_test.csv"
    gtest = pd.read_csv(test_path).iloc[0] if test_path.exists() else None

    # what employers ask for: the step at the release in the job-ad gradient, and when the fall came
    asks = pd.read_csv(tables / "postings_step_at_release.csv").iloc[0]
    grad = pd.read_csv(tables / "postings_gradient_quarterly.csv").set_index("quarter")["all_coef"]
    pre_release = grad[[q for q in grad.index if q < "2022Q4"]]
    post_release = grad[[q for q in grad.index if q >= "2022Q4"]]
    low_q = pre_release.idxmin()
    ordinal = {"1": "first", "2": "second", "3": "third", "4": "fourth"}
    low_when = f"the {ordinal[low_q[-1]]} quarter of {low_q[:4]}"
    fell_before = float(pre_release.min()) <= float(post_release.mean())
    asks_out = asks["statistic"] >= asks["threshold_95"]
    # how much of the fall the latest quarter has made up, measured from the lowest quarter after the release
    low_after = float(post_release.min())
    made_up = (float(grad.iloc[-1]) - low_after) / -low_after if low_after < 0 else 0.0
    last_when = f"the {ordinal[grad.index[-1][-1]]} quarter of {grad.index[-1][:4]}"

    wages = round(float(latest["reach_share"]) * 100)
    core = float(newest["reach_share_three_quarters"]) * 100
    core_first = float(anthropic.iloc[0]["reach_share_three_quarters"]) * 100
    since = int(pay["first_transition"])
    pay_out = pay["largest_statistic"] >= pay["threshold_95"]
    qty_out = qty["largest_statistic"] >= qty["threshold_95"]
    qty_record = qty_out and int(qty["earlier_windows_at_least"]) == 0
    flagged = [int(y) for y, s_, t_ in zip(qty_all["year"], qty_all["largest_statistic"], qty_all["threshold_95"])
               if s_ > t_ and int(y) != int(qty["year"])]
    others = int(qty["consecutive_relabellings"]) - 1
    odds = round(1 / float(qty["p_largest_consecutive"])) if qty["p_largest_consecutive"] > 0 else None
    toward = "toward" if int(qty["largest_direction"]) > 0 else "away from"

    # The words on the page. Every sentence is written for a reader who has not seen the method: what moved, by how much,
    # and the one thing that limits it. The tests behind the city are described by what they compare, never by their units.
    def series(x, y, fmt, threshold=None, unit="", band=None):
        return {"x": [str(v) for v in x], "y": [round(float(v), 4) for v in y], "fmt": fmt, "unit": unit,
                "threshold": None if threshold is None else [round(float(v), 4) for v in threshold],
                "band": None if band is None else [[round(float(v), 4) for v in band[0]], [round(float(v), 4) for v in band[1]]]}
    def label(release):
        tag = str(release)
        return _published(tag) + (f" ({datetime.strptime(tag.split('(')[1][:7], '%Y-%m').strftime('%b')})"
                                   if "(" in tag and len(tag.split("(")[1].rstrip(")")) == 7 else "")
    def pct(x, digits=0):
        return f"{x * 100:.{digits}f}%"

    first_share = round(float(first["reach_share"]) * 100)
    top_name, low_name = top["bundle"].lower(), low["bundle"].lower()
    top_path = landing[(landing["platform"] == "anthropic") & (landing["bundle"] == top["bundle"])
                       & landing["release"].isin(complete["release"])].sort_values("release")
    young_series = gauge.assign(v=(gauge["young_relative_to_prime"] - 1) * 100)
    se_path = tables / "cps_young_worker_se.csv"
    young_se = pd.read_csv(se_path).set_index("period")["se"] if se_path.exists() else None
    firms = pd.read_csv(tables / "adoption_btos_national.csv", parse_dates=["ref_end"])
    firms = firms[(firms["series"] == "ai_in_any_function") & firms["share_using_ai"].notna()].sort_values("ref_end")
    firms_first, firms_last = firms.iloc[0], firms.iloc[-1]
    firms_first_v, firms_now = float(firms_first["share_using_ai"]), float(firms_last["share_using_ai"])
    chatgpt = landing[(landing["platform"] == "openai") & (landing["release"] == "2026-06 (dollar allocation)")].sort_values("concentration")

    def platform_variant(label_, frame):
        hi, lo = frame.iloc[-1], frame.iloc[0]
        ranked = frame.sort_values("concentration", ascending=False)
        return {"key": label_.lower(), "label": label_, "big": f"{hi['concentration']:.1f}×",
                "note": (f"Tasks that call for {plain(hi['bundle_id'])} make up {pct(hi['usage_share_on_bundle'], 1)} of {label_} use "
                         f"but only {pct(hi['wage_bill_share_on_bundle'], 1)} of US wages, {hi['concentration']:.1f} times as much use as "
                         f"their share of pay. Tasks that call for {plain(lo['bundle_id'])} get the least, {lo['concentration']:.1f} times."),
                "bars": [{"name": plain(b_id).capitalize(), "value": round(float(v), 3)}
                         for b_id, v in zip(ranked["bundle_id"], ranked["concentration"])][:8],
                "unit": "use relative to share of pay (tick at 1×), top 8 of 25 groups"}
    start, end = int(pay["year"]) - 3, int(pay["year"])
    earlier = int(pay["consecutive_relabellings"]) - 1
    windows = int(qty["consecutive_relabellings"])
    pay_flagged = [int(y) for y, s_, t_ in zip(pay_all["year"], pay_all["largest_statistic"], pay_all["threshold_95"])
                   if s_ > t_ and int(y) != int(pay["year"])]
    pay_moved = "rise" if int(pay["largest_direction"]) > 0 else "fall"
    mix_field = plain(qty["largest_bundle"])
    shift_word = "toward" if int(qty["largest_direction"]) > 0 else "away from"
    tasks_core = int(newest["tasks_three_quarters"])
    shift_pts = abs(float(gtest["observed_shift"])) * 100 if gtest is not None else None
    draws = int(gtest["draws"]) if gtest is not None else 0
    as_large = round(float(gtest["p_two_sided"]) * draws) if gtest is not None else 0
    pay_big = "Unusual change" if pay_out else "No unusual change"
    mix_big = (f"Largest shift since {since}" if qty_record else "Unusual shift" if qty_out else "No unusual shift")
    ads_big = "Fell before ChatGPT" if fell_before and not asks_out else "Changed at ChatGPT's release" if asks_out else "No change at ChatGPT's release"

    views = {
        "bridge": {
            "index": "Use", "index_line": "How much of the country's paid work involves tasks people already use AI for, and how many firms use it",
            "why": ("If AI is going to change work, it will start with the tasks people already bring to it and the firms that adopt it, "
                    "so this index shows where change could come first."),
            "capline": f"{wages}% of US wages are in tasks people use Claude for; {firms_now:.1f}% of firms use AI",
            "mark": f"{wages}% of US wages are in tasks people use Claude for",
            "headline": (f"Tasks people use Claude for make up {wages}% of US wages, {firms_now:.0f}% of US firms now use AI, and "
                         f"use relative to pay is heaviest on {top_name}."),
            "items": [
                {"title": "Share of US wages in tasks people use Claude for", "big": f"{wages}%",
                 "note": (f"Up from {first_share}% in {_published(first['release'])}. A task counts once anyone uses Claude for it, so part "
                          f"of that rise comes from each release covering more tasks ({int(first['tasks_used']):,} then, "
                          f"{int(latest['tasks_used']):,} now). The tasks behind three quarters of all use, a measure that more coverage "
                          f"does not move, rose from {core_first:.1f}% to {core:.1f}% of US wages."),
                 "more": (f"The Anthropic Economic Index sorts conversations with Claude into the job tasks the Labor Department lists for "
                          f"each occupation (O*NET). We add up what US workers earn on the tasks that appear, using the BLS wage tables. "
                          f"The June 2026 file leaves out rarely used tasks, so this figure uses {_published(latest['release'])}, the most "
                          f"recent file that lists them all. Tasks people hand to Claude to do entirely account for "
                          f"{round(float(split['delegated_share']) * 100)}% of US wages. ChatGPT is not shown here: OpenAI publishes use "
                          f"by broad work activity, so every task under an activity would count and the figure would not be comparable."),
                 "tech": ("Each occupation's OEWS wage bill is split across its O*NET tasks by frequency-weighted task shares, so "
                          "task values sum exactly to the occupation's bill. Reach is the share of the national wage bill in tasks with "
                          "any published usage, which rises mechanically with the number of tasks a release covers; the core, the "
                          f"smallest set of tasks covering 75% of usage ({tasks_core} tasks in the latest file), does not. The published "
                          "shares come without sampling errors, so no band is drawn. Claude.ai users are a selected population."),
                 "src": f"Anthropic Economic Index, {_published(latest['release'])}; OEWS wages, May {int(pay['year'])}",
                 "series": series([label(r) for r in complete["release"]], complete["reach_share"] * 100, "pct0", unit="% of US wages"),
                 "tables": ["usage_reach.csv"]},
                {"title": "Firms using AI", "big": f"{firms_now:.1f}%",
                 "note": (f"{firms_now:.1f}% of US businesses used AI in some part of their work in the two weeks to "
                          f"{firms_last['ref_end'].strftime('%-d %B %Y')}, up from {firms_first_v:.1f}% in "
                          f"{firms_first['ref_end'].strftime('%B %Y')}. The band shows the Census Bureau's 95% margin of error."),
                 "more": ("The Census Bureau's Business Trends and Outlook Survey asks firms every two weeks whether they used AI in any "
                          "of their business functions. The question took this wording in November 2025, so the series starts then; the "
                          "earlier question, about AI in producing goods or services, measures something narrower and is not joined to it."),
                 "tech": ("National estimates and standard errors as published, for the share answering yes; the band is the estimate "
                          "plus or minus 1.96 standard errors. The survey counts firms, not workers or spending, so a small firm and a large "
                          "one weigh the same."),
                 "src": f"Census Bureau, Business Trends and Outlook Survey, {firms_first['ref_end'].strftime('%B %Y')} to {firms_last['ref_end'].strftime('%B %Y')}",
                 "series": series(firms["ref_end"].dt.strftime("%Y-%m-%d"), firms["share_using_ai"], "pct1", unit="% of US firms using AI",
                                  band=(firms["share_using_ai"] - 1.96 * firms["se"], firms["share_using_ai"] + 1.96 * firms["se"])),
                 "tables": ["adoption_btos_national.csv"]},
                {"title": "Where AI use is heaviest", "big": f"{top['concentration']:.1f}×",
                 "note": (f"{top_name.capitalize()} account for {pct(top['usage_share_on_bundle'], 1)} of Claude use but only "
                          f"{pct(top['wage_bill_share_on_bundle'], 1)} of US wages, {top['concentration']:.1f} times as much use as "
                          f"their share of pay. {low_name.capitalize()} get the least, {low['concentration']:.1f} times."),
                 "more": (f"We sort job tasks into 25 skill groups and compare each group's share of AI use with its share of US wages. "
                          f"A value above 1 means people use AI on that group's tasks more than its share of pay alone would lead you to "
                          f"expect. Switch between Claude and ChatGPT to compare the two platforms' users."),
                 "tech": ("Each task's labor is split across O*NET's 161 descriptors by a task-to-skill matrix built from O*NET, whose rows sum to "
                          "one, and the descriptors roll up to 25 bundles, so neither usage nor wage dollars are lost in the mapping. "
                          "OpenAI publishes shares by intermediate work activity, allocated here to tasks in proportion to their wage "
                          f"value; allocating equally instead gives the same top three groups. Claude: {_published(latest['release'])}. "
                          "ChatGPT: June 2026."),
                 "src": f"Anthropic Economic Index, {_published(latest['release'])}; OpenAI Signals v2.0, June 2026; O*NET {release}",
                 "variants": [platform_variant("Claude", here), platform_variant("ChatGPT", chatgpt)],
                 "tables": ["usage_landing.csv"]},
            ],
        },
        "city": {
            "index": "Jobs", "index_line": "Whether pay, the mix of jobs and what job ads ask for have changed more than usual",
            "why": ("If AI were already reshaping work, it would show up here first: in what employers pay for different skills, "
                    "in which kinds of jobs grow, and in the tasks job ads ask for."),
            "capline": (f"Job ads: {ads_big[0].lower() + ads_big[1:]}. Pay: {pay_big.lower()}. Job mix: {mix_big.lower()}."),
            "mark": f"Job ads: {ads_big[0].lower() + ads_big[1:]}. Pay: {pay_big.lower()}.",
            "headline": (("Job ads turned away from tasks AI can do from 2020 to 2022, before ChatGPT, with no further drop at its release. "
                          if fell_before and not asks_out else
                          "Job ads changed at ChatGPT's release more than at almost any earlier month. " if asks_out else
                          "Job ads show no change at ChatGPT's release. ")
                         + ("Pay has changed more than usual" if pay_out else "Pay hasn't changed more than usual")
                         + (f", and the mix of jobs has shifted more than at any time since {since}, though chance can't yet be ruled out."
                            if qty_record else ", and the mix of jobs has shifted more than usual." if qty_out else ".")),
            "items": [
                {"title": "Pay for different skills", "big": pay_big,
                 "note": ((f"If AI were changing what employers pay for, pay for some skills would be moving faster than usual. "
                           f"Between {start} and {end}, none was. The biggest move, a {'rise' if pay_moved == 'rise' else 'drop'} in pay for "
                           f"{plain(pay['largest_bundle'])}, was smaller than the biggest move in {_words(int(pay['earlier_windows_at_least']))} "
                           f"of the {_words(earlier)} earlier three-year periods since {since}."
                           + (f" The reading for {pay_flagged[-1] - 3} to {pay_flagged[-1]} was above the dashed line, so pay did move "
                              f"unusually then, but that has not carried into the latest period." if pay_flagged else ""))
                          if not pay_out else
                          f"Pay for {plain(pay['largest_bundle'])} moved more between {start} and {end} than in almost any earlier "
                          f"three-year period since {since}."),
                 "more": (f"Every occupation uses a mix of 25 skill groups, from working with people to complex problem solving, as "
                          f"described in O*NET. From the wages BLS publishes for each occupation, we estimate what employers pay for "
                          f"each skill group. For each group, we compare the change over the last three years with its own changes "
                          f"since {since}, and call a change unusual only if it is bigger than 95% of the changes we get when we shuffle "
                          f"the years at random. These are averages over whole occupations, so a raise for new hires and a cut for "
                          f"people already in the job would cancel out."),
                 "tech": (f"Relative pay is each bundle's log pay growth against the employment-weighted average, estimated for every "
                          f"annual transition from {since - 1} ({int(pay['transitions_available'])} transitions) on a balanced panel of "
                          f"occupations. The statistic is the largest, across the 25 bundles, of the mean of the last three transitions "
                          f"standardized by the bundle's own year-to-year variability. Its reference distribution relabels which three "
                          f"transitions are treated, using consecutive triples only, since pay changes are autocorrelated; the dashed "
                          f"line is that distribution's 95th percentile, and the chart divides the statistic by it, so 1.0 marks the line "
                          f"(p = {float(pay['p_largest_consecutive']):.2f} for the latest period)."),
                 "src": f"OEWS, May {since - 1} to May {int(pay['year'])}, occupations present in every year",
                 "series": series(pay_all["year"], pay_all["largest_statistic"] / pay_all["threshold_95"], "x1", [1.0] * len(pay_all),
                                  "biggest move in any skill's pay, as a multiple of the unusual level"),
                 "tables": ["outcomes_pay_series_balanced.csv", "outcomes_pay_changes.csv"]},
                {"title": "Mix of jobs", "big": mix_big,
                 "note": ((f"Between {start} and {end}, employment moved {shift_word} jobs that rely heavily on {mix_field}." if qty_record else
                           f"Between {start} and {end}, employment moved {shift_word} jobs that rely heavily on {mix_field} more than usual." if qty_out else
                           f"Between {start} and {end}, the largest shift was {shift_word} jobs that rely heavily on {mix_field}, within the usual range.")
                          + (f" It is the largest shift of all {_words(windows)} three-year periods since {since}, which is as unusual as "
                             f"{_words(windows)} periods can show." if qty_record else "")
                          + (f" The reading for {flagged[-1] - 3} to {flagged[-1]}, which includes the first year of the pandemic, was also above the dashed line, "
                             f"so the spring {int(pay['year']) + 2} wage tables will show whether this one lasts." if qty_out and flagged else
                             f" The spring {int(pay['year']) + 2} wage tables will show whether it lasts." if qty_out else "")),
                 "more": ("We measure how much of all US employment goes to each of the same 25 skill groups. That share changes "
                          "when people move between occupations, which can happen before pay changes at all. It is tested the same "
                          "way as pay, against each group's own history."),
                 "tech": (f"The same statistic on employment-weighted bundle intensity. With {int(qty['transitions_available'])} "
                          f"transitions there are {windows} consecutive triples, so the smallest attainable p is 1/{windows}; the "
                          f"latest period attains it (p = {float(qty['p_largest_consecutive']):.2f}). The test cannot yet separate an "
                          f"AI effect from the post-pandemic reallocation of employment."),
                 "src": f"OEWS, May {since - 1} to May {int(qty['year'])}, occupations present in every year",
                 "series": series(qty_all["year"], qty_all["largest_statistic"] / qty_all["threshold_95"], "x1", [1.0] * len(qty_all),
                                  "biggest shift in employment, as a multiple of the unusual level"),
                 "tables": ["outcomes_quantity_series_balanced.csv"]},
                {"title": "Job ads for tasks AI can do", "big": ads_big,
                 "note": ((f"From 2020 to {low_when}, job ads in the same occupation asked less and less often for tasks AI can do. "
                           f"ChatGPT's release in November 2022 brought no further drop" if fell_before and not asks_out else
                           f"Job ads changed at ChatGPT's release in November 2022 more than at almost any earlier month" if asks_out else
                           "Job ads show no change at ChatGPT's release in November 2022")
                          + (f", and by {last_when} ads had recovered {made_up * 100:.0f}% of the decline." if made_up >= 0.25 else ".")),
                 "more": (f"The National Labor Exchange (NLx) data count how often ads in each occupation name each O*NET task. We check "
                          f"whether tasks AI can do lost ground to other tasks in the same occupation, and whether anything changed at "
                          f"ChatGPT's release. In {_words(int(asks['earlier_at_least']))} of the {_words(int(asks['earlier_windows']))} "
                          f"earlier months, the same comparison showed a change at least as large as the one at the release."),
                 "tech": (f"From a working paper in progress by the author: the gradient of a task's share of its occupation's ads on the task's Eloundou "
                          f"exposure, by quarter against 2019, so the comparison is within occupation by construction. The step at "
                          f"the release is measured against the sixteen months before it and set against the same step placed at "
                          f"each of {int(asks['earlier_windows'])} earlier months (p = {int(asks['earlier_at_least']) / int(asks['earlier_windows']):.2f}). "
                          f"Occupation-months list at most fifty tasks, and the result holds on occupations whose lists are always complete."),
                 "src": "NLx job ads, September 2015 to September 2025, in the aggregates of Meisenbacher, Nestorov and Norlander; Eloundou task measure",
                 "series": series(list(grad.index), grad.to_numpy() * 100, "pp2", unit="share of ads, change since 2019 (points)"),
                 "tables": ["postings_step_at_release.csv", "postings_gradient_quarterly.csv", "postings_release_bound.csv"]},
            ],
        },
        "valley": {
            "index": "Training", "index_line": "What students choose to study, and whether young workers still get the jobs most exposed to AI",
            "why": ("Students pick fields years before they work, and entry-level jobs hold many of the tasks AI can do, so the "
                    "next generation of workers is where an early shift would appear."),
            "capline": (f"{degrees:.1f}% of new degrees and {enrolled:.1f}% of enrollment are in exposed fields; "
                        f"young workers down {young:.0f}% in exposed jobs since 2022"),
            "mark": f"{degrees:.1f}% of new degrees are in exposed fields",
            "headline": (f"{degrees:.0f}% of new degrees and {enrolled:.0f}% of four-year enrollment are in the fields most exposed "
                         f"to AI, and young workers have lost ground in exposed jobs since 2022."),
            "items": [
                {"title": "New degrees in exposed fields", "big": f"{degrees:.1f}%",
                 "note": (f"{degrees:.1f}% of {year} bachelor's degrees went to the third of fields whose graduates hold the most "
                          f"AI-exposed jobs" + (f", up from {before:.1f}% in {year - 1}." if before is not None else ".")),
                 "more": ("Degrees by field come from the Education Department's IPEDS completions files. We score each field by the AI "
                          "exposure of the jobs its graduates actually hold, using the Census Bureau's American Community Survey and the "
                          "exposure measure of Eloundou, Manning, Mishkin and Rock (2024)."),
                 "tech": ("Fields are six-digit CIP codes scored by the employment-weighted Eloundou exposure of the occupations "
                          "ACS 2024 degree holders in each field actually work in, which measures where graduates go instead of where "
                          "programs say they lead. Exposed fields are the top third of fields by that score."),
                 "src": f"IPEDS completions, {year}; field exposure from ACS and the Eloundou task measure",
                 "series": series(list(share.index), share.to_numpy() * 100, "pct1", unit="% of bachelor's degrees"),
                 "tables": ["pipeline_completions_by_state.csv", "pipeline_field_exposure_crosswalk.csv"]},
                {"title": "Enrollment in exposed fields", "big": f"{enrolled:.1f}%",
                 "note": (f"{enrolled:.1f}% of four-year undergraduates in {str(e_last['term']).lower()} were in those fields, "
                          f"{'up' if enrolled >= enrolled_first else 'down'} from {enrolled_first:.1f}% in {str(e_first['term']).lower()}. "
                          f"Students choose fields years before they graduate, so a turn away from exposed fields would show up here first."),
                 "more": "Enrollment by field comes from the National Student Clearinghouse and is scored the same way as degrees.",
                 "src": f"National Student Clearinghouse, {e_first['term']} to {e_last['term']}; field exposure from ACS and the Eloundou task measure",
                 "series": series(enrol["term"].str.replace("Fall ", ""), enrol["share_exposed"] * 100, "pct1", unit="% of four-year undergraduates"),
                 "tables": ["pipeline_enrolment_by_exposure.csv", "nsc_cip_family_enrolment.csv"]},
                {"title": "Young workers in exposed jobs", "big": f"−{young:.0f}%",
                 "note": (f"Since 2022, workers aged 22 to 27 have lost ground in the jobs most exposed to AI, by {young:.0f}% compared "
                          f"with workers aged 35 to 54."
),
                 "more": ("From the Census Bureau's monthly Current Population Survey. For each age group we divide employment in the most "
                          "exposed third of jobs by employment in all other jobs, then compare the young group's ratio with the older "
                          "group's. "
                          + (f"Over the last 12 months the gap was {shift_pts:.1f} points wider than in the months before. "
                             + (f"In {draws:,} random reorderings of the months, none produced a gap that large. " if as_large == 0 else
                                f"In {draws:,} random reorderings of the months, {as_large} produced a gap that large. ")
                             if gtest is not None else "")
                          + "The data start in January 2022, so they can't show whether the decline began before ChatGPT."),
                 "tech": ("The gauge is (E_young,exposed / E_young,other) / (E_prime,exposed / E_prime,other), with composited CPS "
                          "weights, exposed meaning the top third of occupations on the Eloundou measure, Census codes mapped to SOC "
                          "with OEWS employment weights, and the series indexed to 2022. The permutation relabels which months count "
                          "as the last twelve at the level of CPS rotation groups, so the overlap between adjacent months' samples is "
                          "kept under the null. The band is plus or minus 1.96 standard errors from the random-groups method over the "
                          "eight rotation groups, recomputing the gauge with each group left out."),
                 "src": f"Current Population Survey, January 2022 to {g_when}",
                 "series": series(young_series["period"], young_series["v"], "pct0s", unit="% change since 2022, against ages 35 to 54",
                                  band=None if young_se is None else
                                  (young_series["v"] - 196 * young_series["period"].map(young_se).fillna(0),
                                   young_series["v"] + 196 * young_series["period"].map(young_se).fillna(0))),
                 "tables": ["cps_young_worker_gauge.csv"] + (["cps_young_worker_test.csv"] if gtest is not None else [])},
            ],
        },
    }
    # the city leads with job ads, its clearest result, then pay and the mix of jobs
    views["city"]["items"] = [views["city"]["items"][i] for i in (2, 0, 1)]
    for key, view in views.items():
        for i, entry in enumerate(view["items"]):
            entry["view"] = key
            entry["research"] = _RESEARCH.get((key, i), [])

    # the opening paragraph: one sentence per index, each linked to its view
    lede = (f'Tasks people use Claude for make up <a href="#bridge" data-view="bridge">{wages}% of US wages</a>. '
            + ('<a href="#city" data-view="city">Pay has changed more than usual</a>' if pay_out else
               '<a href="#city" data-view="city">Pay hasn\'t changed more than usual</a>')
            + (", and job ads turned away from tasks AI can do from 2020 to 2022, before ChatGPT, with no further drop at its release. "
               if fell_before and not asks_out else
               ", and job ads changed at ChatGPT's release more than at almost any earlier month. " if asks_out else
               ", and job ads show no change at ChatGPT's release. ")
            + f'And <a href="#binoculars" data-view="valley">{degrees:.0f}% of new degrees</a> are in fields that lead to the jobs most exposed to AI.')

    meaning = [
        (f"Use: Tasks people use Claude for are worth {wages}% of US pay, but the most-used few hundred are worth {core:.1f}%, "
         f"and {firms_now:.0f}% of US firms now use AI."),
        ("Jobs: " + ("AI hasn't shown up in pay. " if not pay_out else "Pay has changed more than usual. ")
         + ("The mix of jobs has shifted more than usual, though chance can't yet be ruled out, " if qty_out and odds and odds < 20 else
            "The mix of jobs has shifted, " if qty_out else "The mix of jobs is within its usual range, ")
         + ("and job ads moved away from tasks AI can do before ChatGPT came out." if fell_before else
            "and job ads show no change at ChatGPT's release.")),
        (("Training: The share of degrees and enrollment in exposed fields has risen slightly, so students have not moved "
          "away from them. " if (before is None or degrees >= before) and enrolled >= enrolled_first else
          "Training: The share of degrees or enrollment in exposed fields has fallen. ")
         + f"Young workers' place in exposed jobs, against older workers', is {young:.0f}% lower than in 2022."),
    ]
    notes = ["new data coming soon"]

    # the page reads as prose: lists inside a line are separated by semicolons, never by middle dots
    for view in views.values():
        for key in ("capline", "mark"):
            view[key] = view[key].replace(" · ", "; ")
        for entry in view["items"]:
            entry["src"] = entry["src"].replace(" · ", "; ")

    readings = {
        "built": datetime.now(timezone.utc).strftime("%-d %B %Y"),
        "lede": lede,
        "meaning": meaning,
        "notes": notes,
        "views": views,
        "links": _links(),
        "releases": [{"date": str(r), "reach": round(float(x), 3), "published_use": round(float(p), 3)}
                 for r, x, p in zip(anthropic["release"], anthropic["reach_share"], anthropic["published_use"])],
    }
    out = config.REPO_ROOT / "site" / "data" / "readings.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(readings, indent=2, ensure_ascii=False))
    site_static.write(readings=out)
    return out


if __name__ == "__main__":
    main()
