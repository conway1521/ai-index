# aiindex

A public index of where AI usage has reached the labour market, built on
the paper's machinery. Three layers, each in its own units and never added
together:

1. **National.** Where observed AI usage lands in the wage bill, by skill
   bundle and by platform (`usage`), and what has moved in realised pay and
   employment against a stated detection threshold, once per OEWS year
   (`outcomes`), with a monthly young-worker gauge from the CPS (`cps`).
2. **State, annual.** The share of each state's wage bill on exposed
   occupations under each exposure measure, the Census Bureau's biweekly
   firm adoption averaged to the year, and the realised exposed-against-
   unexposed change with its cell counts (`state`).
3. **Pipeline and capacity.** Enrolment and completions by the exposure of
   the field (`pipeline`), and what refills an exposed occupation, the
   education channel at its measured size beside the lateral channel
   (`capacity`).

## Running

The index imports the paper's machinery from the paper-skills-dna
repository, cloned beside this one or pointed to by `SKILLS_DNA_ROOT`.

    pip install -r requirements.txt
    python -m aiindex.build
    python -m pytest aiindex/tests

`COLLECT.md` lists every input to place by hand, with its source. Most of
them are attached to the dated data releases of the paper repository, and

    python -m aiindex.place_release

fetches each one, checks it against the release manifest and links it where
the loaders read it. It needs `GITHUB_TOKEN` with read access to the paper
repository when the files are not already on disk.

The build fetches every input from its official host, falls back to a
committed copy when the host refuses, and writes `output/manifest.json`
with the URL, byte count, hash and grade of every file it read;
`output/checks.csv` with every unit check it ran and the value it
measured; `output/build_report.json` with what was skipped; and the
tables under `output/tables/`. `AUDIT.md` records what each source is,
where tonight's copy came from and what harmonisation it needed.

Inputs are not committed. The `.source` sidecar beside each input is,
and records the grade and URL it was fetched from, so a clean checkout
regenerates the same files.

## Running on GitHub

Three workflows, in `.github/workflows/`:

- `build.yml` rebuilds the index on demand; its weekly schedule is paused
  until a run can place the data releases on the runner, since a runner
  without them would rebuild from copies and commit that. It begins by asking
  every publisher whether it will serve a GitHub runner, reports the answer
  into the run summary, and then rebuilds, tests and commits whatever
  changed in `aiindex/output` and `site/data`. The raw inputs are cached
  between runs, so only a new release is fetched.
- `tests.yml` runs the suite on every push.
- `pages.yml` publishes `site/`, whose `index.html` is the page. GitHub serves Pages from a
  private repository only on a paid plan; on the free plan this one fails
  until the repository is public.

Both `build.yml` and `tests.yml` check out `paper-skills-dna`, whose `src`
holds the O*NET readers, gamma, the named bundles and the relabelling
inference. While that repository is private they need a `PAPER_REPO_TOKEN`
secret with read access to it; when it goes public, delete the token line.
The build skips itself rather than failing if the checkout does not happen,
so the reachability report still lands.

The same probe runs anywhere:

    python -m aiindex.probe_hosts
    python -m aiindex.probe_hosts --plain-agent

It needs no third-party packages. A publisher that refuses is recorded, not
treated as an error: the build falls back to a committed copy and grades
that input `mirror` in the manifest.

## Where each layer stands

| Layer | Module | Ran on | Notes |
|---|---|---|---|
| Spine | `spine.py` | official crosswalks, O*NET 30.3 | O*NET-SOC, Census 2018, CIP 2020 and SOC 2010 crosswalks with coverage reported |
| Wage bill | `wagebill.py` | OEWS May 2025 official, 2012 to 2024 copies | 2019 and 2020 hybrid codes carried onto the 2018 SOC through the BLS table; 2012 to 2018 carried onto the 2018 SOC |
| Exposure | `exposure.py` | Eloundou and Felten (authors' files), Anthropic observed exposure | three measures; state and pipeline tables are written once per measure |
| Usage | `usage.py`, `aei.py`, `openai.py` | Anthropic releases of September 2025 to the June 2026 monthly file, OpenAI Signals to June 2026 | the June file publishes 88 and 94 percent of use, so the headline reach comes from the latest release that publishes all of it; Signals activity codes translated onto O*NET 30.3 by title |
| Outcomes | `outcomes.py` | real panel | the paper's test as a series with a 95th percentile threshold |
| CPS gauge | `cps.py` | 55 Census months, January 2022 to August 2026 | October 2025 was not collected |
| Job ads | `postings.py` | NLx aggregates, September 2015 to September 2025 | the paper's Appendix B code; each occupation-month lists its top fifty tasks |
| State | `state.py`, `btos.py` | official BTOS through cycle 202619 | Anthropic state usage per worker |
| Pipeline | `pipeline.py`, `ipeds.py`, `acs.py` | IPEDS 2023 to 2025, ACS 2024 national, Clearinghouse fall 2019 to 2024 | Clearinghouse by two-digit CIP family, undergraduate four-year |
| Capacity | `capacity.py` | fixture | the flows repository's matrix drops in on its schema |

## Units, checked at every step

Every table is written only after its checks pass. Wage bills are
employment times mean annual wage in nominal dollars of the release year,
detailed occupations only. Task values within an occupation sum to that
occupation's wage bill to machine precision. Task rows of gamma sum to
one over 161 descriptors and to one over 25 bundles. Usage shares sum to
one within a platform and release, and no reach figure exceeds the wage
bill it is a share of. Exposure terciles are employment-weighted. CPS
weights carry four implied decimals and are divided out. BTOS shares are
percent of firms and are kept in percent. Every coverage figure is
recorded whether or not it passed a threshold.

## What the numbers are not

Usage from one platform is a selected sample of the workforce, so the
usage layer is titled where usage lands and is written once per platform.
The state exposure column is a composition of a national score with a
state's occupational mix and cannot fail, which is why it is not the
headline of that layer. The realised-change column at state level
carries the noise the paper found in state cells and is written with the
number of cells behind it. No composite score exists anywhere in the
package and none should be added.
