# Source audit

## Rebuild of 29 September 2026, on the data releases

The inputs the publishers would not serve to a script were downloaded by
hand, attached to the paper repository's releases `data-2026-10-01`,
`data-2026-10-01-addendum` and `data-2026-10-01-addendum2`, and recorded
there with their hashes; `python -m aiindex.place_release` links them where
the loaders read them. The build read 80 inputs graded real, 44 graded
mirror and 2 graded fixture, and all 443 checks passed. The mirrors are
OEWS 2012 to 2024, the two earliest usage releases, the CPS record layouts,
which the CSV months do not use, and the O*NET 30.2 activity reference that
translates the Signals codes; the fixtures are the flows matrix and its
arrivals, which no number on the page reads.

| Input | Now | What it changed |
|---|---|---|
| O*NET 30.3 | real | every layer on the paper's own release; Signals activity codes, which follow 30.2, are carried onto 30.3 through the detailed activity titles, all 2,087 of which match, each 30.2 intermediate activity landing on one 30.3 activity |
| OEWS May 2025, national and state | real | the state layer gains 2025; 2012 to 2024 remain checked copies |
| OEWS hybrid structure, May 2019 and 2020 | real, new | 11.8 and 12.5 percent of the 2019 and 2020 wage bills sat on hybrid codes and are now carried onto the 2018 SOC, a code spanning several split by their May 2021 national employment; the balanced panel rises from 653 to 661 occupations against the paper's 693 |
| CPS basic monthly | real, new | 55 months as CSV, January 2022 to August 2026; October 2025 was not collected; weighted population 16 and over 263.2 million in January 2022 and 275.4 million in August 2026 |
| Economic Index, June 2026 monthly file | real | the file omits tasks below a reporting threshold and publishes 88.4 and 94.3 percent of use in April and May 2026; reach counts every published task, so the headline reach comes from the latest release that publishes all of its use, March 2026, and a second reach, the wage share of the tasks making up three quarters of all use, is recorded for every release |
| Economic Index labor market tables, Signals v2.0 | real | replace the copies |
| BTOS | real | through cycle 202619; the calendar sheet now spells the reference start in full |
| IPEDS | real | completions 2023 and 2024 in their revised release, 2025 provisional, institutions 2023 to 2025 |
| ACS 2024 one-year, national | real, new | 340.1 million weighted persons, replacing the one-state test file |
| Clearinghouse, fall 2024 CIP group enrolment | real, new | undergraduate four-year enrolment by two-digit CIP family, fall 2019 to 2024, read by code, so no label mapping is needed |
| NLx job ads, aggregates by Meisenbacher, Nestorov and Norlander | real, new | the job-ads layer, run by the paper's Appendix B code; each occupation-month lists its fifty most frequent tasks |
| Flows transition matrix | fixture | unchanged |

One reading was built and kept off the page. The average exposure of the
tasks named in ads, within occupations with complete task lists, falls from
2023 to 2025 while the task-level gradient holds flat after the release; the
average also moves with which tasks are named, and the difference is written
to `postings_asked_exposure_monthly.csv` for inspection until it is
understood.

## The build of 20 September 2026


What each layer reads, where the file came from on this build, and what
stands between the build and the publisher's own release. Grades follow
the manifest: "real" is the publisher's file from the publisher's host,
"mirror" is a byte-for-byte or row-for-row copy of the publisher's file
committed to a public GitHub repository and checked against the published
layout and row counts, "fixture" is a file in the right shape standing in
for one that could not be reached.

The build environment reaches GitHub and PyPI and nothing else: BLS, the
Census Bureau, NCES, O*NET, the Clearinghouse and Hugging Face all refuse
the connection. Every mirror below is therefore a copy that someone else
committed. The build tries the official URL first on every run, so on a
network that reaches the publishers the mirrors are never used and the
manifest reads "real" throughout. The mirror URLs are in `sources.py`.

| Source | Layer | Grade tonight | Copy used | Harmonisation |
|---|---|---|---|---|
| O*NET database 30.2, 16 text files | spine, usage, outcomes | mirror | pythonski/bottlenecks, byte-identical core files to two other copies | Column names of the work-activity crosswalks translated to the 30.3 names the paper's reader expects; Skills is one file before 30.3 |
| O*NET-SOC 2019 to SOC 2018 crosswalk | spine | mirror | ApprenticeshipStandardsDotOrg, identical to a second copy | none |
| Census 2018 occupation code list with SOC crosswalk, May 2020 revision | spine, cps, acs | mirror | avdluduvice/WidraLuduvice_BK | X placeholders expanded to detailed SOC codes; 2 Census codes carry no SOC |
| Census 2010 to 2018 crosswalk sheet | wage bill | mirror | same workbook | 419 one-to-one codes carried, 44 splits dropped, 12 percent of the early wage bill |
| OEWS state files 2012 to 2024, national 2019 and 2021 to 2025 | wage bill, outcomes, state | mirror | Soorej30/wage_analysis (2020 to 2024 state), KHALEDRABBAH/US-Unemployment-Dashboard (2012 to 2019 state), several for national | Detailed rows only; 2012 to 2018 on the 2010 SOC carried onto 2018; national 2020 summed from states; state 2025 not mirrored anywhere |
| Eloundou task ratings | exposure | real | GitHub, the authors' repository | mean beta over an occupation's rated tasks |
| Felten AIOE | exposure | real | GitHub, the authors' repository | as published, six-digit SOC |
| Anthropic Economic Index, releases of September 2025, January 2026 and March 2026, consumer raw tables | usage, state, exposure | mirror | IlanStrauss/anthropic-econ-critique and dioandre3/UMICH-STAT507; the first two match the sha256 Hugging Face records, the March 2026 file was republished by Anthropic and the copy is an earlier version | task statements joined to task identifiers through the release's own statement list, 99.9 percent of usage matched; collaboration modes grouped as Handa et al.; global consumer slice, latest week in each file |
| Anthropic Economic Index, June 2026 monthly release | usage | mirror, derived | theodorewright11, a slice of the 219 MB file: global task shares for April and May 2026, text only | text join; no collaboration split in the slice |
| Anthropic labor market tables, job exposure and task penetration | exposure | mirror | tkc88888888/EconomicIndex, sha256 matches Hugging Face | observed exposure by six-digit SOC 2018 enters as the third exposure measure |
| OpenAI Signals v2.0, share of work-related messages by intermediate work activity and month, July 2024 to June 2026 | usage | mirror | prashgarg/global-automation-atlas, the download as committed | activity shares allocated to tasks by dollars and, as a comparison, equally; latest month |
| WildChat open index | usage | not reachable | the repository commits no aggregates; the dataset is on Hugging Face | none |
| Indeed AI tracker | context | real | GitHub, the publisher's repository | none |
| Census BTOS State, National, Sector workbooks, 8 December 2025 download | state | mirror | EIG-Research/ai-btos, downloaded from the Census site on 9 December 2025 | wide to long; two question wordings kept as separate series; cycles dated by the workbook's reference calendar; nothing after December 2025 |
| CPS basic monthly record layouts 2022 to 2026 | cps | mirror | rmmomin/ai-adoption-labor-trends, byte-exact copies of the Census files | parsed rather than hard coded; 2026 renames the occupation variable and the alias is handled |
| CPS basic monthly microdata | cps | fixture | none committed anywhere public; synthetic months on the real 2025 layout | the reader, cells and gauge run on the fixture; the numbers mean nothing until the Census files are in `data/raw/cps` |
| IPEDS completions 2023 and 2024, header 2023 | pipeline | mirror | arijacob/chicago_majors and ftrain/ipeds2, served from GitHub's large-file host | first majors, six-digit CIP, total column; 2024 awards joined to the 2023 institution file for state |
| NCES CIP 2020 to SOC 2018 crosswalk | pipeline | mirror | lrussell-research/CIP-NAICS-Crosswalk, the unmodified NCES workbook | CIP-SOC sheet only |
| ACS 2022 one-year person file, Minnesota | pipeline | mirror | beeckcenter/climate-equity-workforce, GitHub large-file host | one state as a test of the field-of-degree link; national extract to follow |
| Clearinghouse major field appendix | pipeline | fixture | none | the label-to-CIP table is committed; the appendix must be downloaded by hand |
| Flows transition matrix | capacity | fixture | unpublished in the flows repository | schema defined and validated; the sibling export drops in |

## What did not run on real data

- The WildChat column of the usage layer. No aggregate is committed
  anywhere; the dataset sits on Hugging Face.
- The CPS gauge. The code is tested on the real layouts with synthetic
  records. Placing the monthly files in `data/raw/cps` and rerunning is
  the whole remaining step.
- Lateral capacity. Blocked on the flows repository's matrix, as the
  feasibility note said.
- Clearinghouse enrolment. The appendix must be fetched by hand.

## Checks on the build

264 checks ran and passed on the full build, recorded in
`output/checks.csv` with the value each measured. The ones that carry
information rather than a pass are the coverage notes: the share of each
year's wage bill that joins O*NET (0.95 before 2019, 0.86 in 2019 and
2020 on the hybrid classification, 0.92 from 2021), the share of the
early wage bill carried across the 2010 to 2018 recoding (0.88), and the
Census codes without a SOC (2 of 570).

## Reconciliation with the paper

The outcome series is the paper's permutation test run year by year on
the same code. The paper reports, on a balanced panel of 693 occupations,
five of 25 bundles moving beyond two of their own standard errors over the
2023 to 2025 transitions, a largest statistic of 3.01, and p-values of
0.112 on the count and 0.430 on the largest against all 286 relabellings.

Rerun on the index's panel, the same statistic reads:

| Panel | Occupations | Bundles beyond two | Largest | p count, all | p largest, all |
|---|---|---|---|---|---|
| common occupations per transition, national files | 751 | 4 | 2.54 | 0.213 | 0.720 |
| balanced, national files | 653 | 6 | 2.83 | 0.035 | 0.563 |
| balanced, state files summed | 654 | 7 | 2.88 | 0.028 | 0.503 |

The largest statistic sits inside the relabelling distribution on every
construction, which is the paper's reading. The count of bundles beyond
two is one or two higher than the paper's and its p-value lower, and the
two differences left are known: the O*NET release is 30.2 here against
30.3, and the balanced panel holds about forty fewer occupations because
the 2019 and 2020 OEWS files use hybrid codes that do not join the 2018
SOC and are dropped rather than mapped. Mapping those hybrid codes from
the BLS documentation is the next step on a network that reaches BLS, and
the build writes both the common-occupation and the balanced series so
the two constructions stay visible.

## A note on how the copies were found

The agents that located the copies used web search and, for enumerating
files inside candidate repositories, GitHub code search. Every file was
then fetched from raw.githubusercontent.com or media.githubusercontent.com
and checked. No file came from a host the proxy refused.

## Usage layer readings on this build

Anthropic's consumer usage lands on about a fifth of the wage bill, the
tasks that appear in the index at all: 0.18 of the bill in the August
2025 week, 0.22 in November 2025, 0.23 in February 2026, and 0.19 and
0.21 in the April and May 2026 slices. The share delegated, the task's
dollars scaled by the automation share of its usage, sits between 0.05
and 0.06. Between 75 and 81 percent of usage share lands on tasks that
carry a value, the rest being tasks with no frequency rating or no
occupation in the wage panel. OpenAI's activity shares reach 0.62 of the
bill under either allocation rule, which is the coarseness of the
activity grain and not a finding about breadth of use. The three exposure
measures correlate at 0.85 (Eloundou and Felten), 0.64 and 0.54 with
Anthropic's observed exposure.
