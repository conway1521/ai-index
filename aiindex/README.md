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

`COLLECT.md` lists every input to place by hand, with its source.

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

## Where each layer stands

| Layer | Module | Ran on | Notes |
|---|---|---|---|
| Spine | `spine.py` | real files (copies) | O*NET-SOC, Census 2018, CIP 2020 and SOC 2010 crosswalks with coverage reported |
| Wage bill | `wagebill.py` | OEWS 2012 to 2025 (copies) | state files to 2024, national 2025; 2012 to 2018 carried onto the 2018 SOC |
| Exposure | `exposure.py` | Eloundou and Felten (authors' files), Anthropic observed exposure (copy, hash-verified) | three measures; state and pipeline tables are written once per measure |
| Usage | `usage.py`, `aei.py`, `openai.py` | Anthropic releases of September 2025 to June 2026 and OpenAI Signals to June 2026 (copies) | three Anthropic raw tables, two monthly slices, OpenAI by activity under two allocation rules; WildChat not reachable |
| Outcomes | `outcomes.py` | real panel | the paper's test as a series with a 95th percentile threshold |
| CPS gauge | `cps.py` | real layouts, synthetic months | drop the Census monthly files into `data/raw/cps` and rerun |
| State | `state.py`, `btos.py` | real (copies) | BTOS to December 2025; Anthropic state usage per worker for three releases |
| Pipeline | `pipeline.py`, `ipeds.py`, `acs.py` | IPEDS 2023 and 2024, ACS one state, NCES crosswalk | Clearinghouse appendix is a fixture until fetched |
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
