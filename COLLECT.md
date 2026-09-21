# Files to collect by hand

Everything below goes under `aiindex/data/raw/`. A file placed there with no
`.source` sidecar beside it is treated as the publisher's release and graded
"real" in the manifest on the next build. Keep the publisher's file name
unless a different name is given. Then run `python -m aiindex.build`.

Files marked "replaces a copy" are ones the build already has from a
committed copy on GitHub; replacing them makes the manifest read "real".
Files marked "new" are ones the index has never run on.

## 1. OEWS wages and employment (BLS), replaces copies, plus one new file

Where: https://www.bls.gov/oes/tables.htm. Pick each year's "May" release,
then "All data", then the National and the State zip. BLS refuses scripted
downloads, so this is a browser job. Direct links follow the pattern
`https://www.bls.gov/oes/special-requests/oesm25nat.zip` and
`https://www.bls.gov/oes/special-requests/oesm25st.zip`, with the
two-digit year in place of 25.

Get: for every year 2012 to 2025, `oesmYYnat.zip` and `oesmYYst.zip`.
The May 2025 state file, `oesm25st.zip`, is the one the index has never
had; the rest replace copies.

Put in: `aiindex/data/raw/oews/`, zips as downloaded. Delete the
`state_M20YY_dl.xlsx` and `national_M20YY_dl.xlsx` copies that are there
now, together with their `.source` sidecars, so the release zips are read
instead.

## 2. O*NET database 30.3, replaces a copy of 30.2

Where: https://www.onetcenter.org/database.html, "Database" then the
"Text" format for release 30.3. Direct link:
https://www.onetcenter.org/dl_files/database/db_30_3_text.zip

Put in: `aiindex/data/raw/onet/onet_db_30_3_text.zip` (rename to this).
Delete `onet_db_30_2_text.zip` and its sidecar. The loader takes the
newest release zip in the folder.

## 3. CPS basic monthly microdata (Census Bureau), new

Where: https://www.census.gov/data/datasets/time-series/demo/cps/cps-basic.html.
Each month has a zip of the public-use file, named like `jan22pub.zip`,
under the year's section. Direct pattern:
`https://www2.census.gov/programs-surveys/cps/datasets/2025/basic/jan25pub.zip`

Get: every month from January 2022 to the latest month published.

Put in: `aiindex/data/raw/cps/`, zips as downloaded, names unchanged.
The record layouts for 2022 to 2026 are already in
`aiindex/data/raw/cps/layouts/`; if a 2027 layout exists by the time you
do this, add it there under the Census name.

## 4. Anthropic Economic Index (Hugging Face), one replacement and one new

Where: https://huggingface.co/datasets/Anthropic/EconomicIndex/tree/main

Get:
- `release_2026_03_24/data/intermediate/aei_raw_claude_ai_2026-02-05_to_2026-02-12.csv`
  (the current version; the copy in hand is an earlier one Anthropic republished).
  Put in: `aiindex/data/raw/aei/release_2026_03_24/`, delete the sidecar.
- `release_2026_06_26/data/aei_claude_ai_2026-06-26.csv` (about 219 MB), new.
  Put in: `aiindex/data/raw/aei/release_2026_06_26/`. Then delete the two
  slice files `task_pct_2026-04.csv` and `task_pct_2026-05.csv` and their
  sidecars from that folder, since the full file supersedes them.
- Any release published after June 2026: its `aei_claude_ai_<date>.csv`
  into `aiindex/data/raw/aei/release_<date>/`.
- `labor_market_impacts/job_exposure.csv` and `task_penetration.csv`,
  replacing copies. Put in: `aiindex/data/raw/aei_labor_market/`.

## 5. OpenAI Signals (v2.0 or later), replaces copies

Where: https://openai.com/signals/data-download/

Get: `usa_share_of_work_related_messages_by_onet_iwa_month.csv` and
`usa_share_of_messages_by_onet_iwa_month.csv`.

Put in: `aiindex/data/raw/openai/`, names unchanged, delete the sidecars.

## 6. Census BTOS firm adoption, replaces copies and extends them

Where: https://www.census.gov/hfp/btos/data_downloads

Get: `State.xlsx`, `National.xlsx`, `Sector.xlsx` (the current downloads;
they carry the AI question under both wordings and run past December 2025).

Put in: `aiindex/data/raw/btos/`, names unchanged, delete the sidecars.

## 7. IPEDS completions and institutions (NCES), replaces copies and adds one

Where: https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx, choose
"Complete data files", the year, then the Completions survey file
`C2024_A` and the Institutional Characteristics file `HD2024`. Also
`C2023_A` and `HD2023`. When the 2025 files appear, `C2025_A` and `HD2025`.

Get: each zip, then take the CSV inside (`c2024_a.csv`, `hd2024.csv`).

Put in: `aiindex/data/raw/ipeds/` as `C2024_A.csv`, `HD2024.csv`,
`C2023_A.csv`, `HD2023.csv` (upper case as shown). Delete the sidecars.

## 8. Crosswalks, replace copies

- CIP 2020 to SOC 2018: https://nces.ed.gov/ipeds/cipcode/resources.aspx?y=56,
  the file `CIP2020_SOC2018_Crosswalk.xlsx`.
  Put in: `aiindex/data/raw/crosswalks/cip_2020_soc_2018.xlsx`.
- Census 2018 occupation code list with SOC crosswalk:
  https://www2.census.gov/programs-surveys/demo/guidance/industry-occupation/2018-occupation-code-list-and-crosswalk.xlsx
  Put in: `aiindex/data/raw/crosswalks/census_2018_occupation_crosswalk.xlsx`.
- O*NET-SOC 2019 to SOC 2018:
  https://www.onetcenter.org/taxonomy/2019/soc/2019_to_SOC_Crosswalk.csv
  Put in: `aiindex/data/raw/crosswalks/onetsoc_2019_to_soc_2018.csv`.
- OEWS hybrid codes for May 2019 and May 2020, new: on
  https://www.bls.gov/oes/, the technical notes for the May 2019 and May
  2020 estimates link a crosswalk between the hybrid occupation structure
  and the 2018 SOC (an xlsx). Save it as
  `aiindex/data/raw/crosswalks/oews_hybrid_2019_2020.xlsx`. The loader
  for it is the task "Map the 2019 and 2020 OEWS hybrid SOC codes".

Delete the sidecars beside each replaced file.

## 9. ACS one-year person file (Census Bureau), new

Where: https://www2.census.gov/programs-surveys/acs/data/pums/2024/1-Year/
(or 2023). The national person file is `csv_pus.zip`, about a gigabyte,
holding `psam_pusa.csv` to `psam_pusd.csv`.

Get: `csv_pus.zip`, unzip it.

Put in: `aiindex/data/raw/acs/` as the `psam_pus*.csv` files. Delete the
Minnesota test file `psam_p27_2022_1yr.csv` and its sidecar. The loader
stacks every `psam_p*.csv` in the folder.

## 10. Clearinghouse major field enrolment, new

Where: https://nscresearchcenter.org/current-term-enrollment-estimates/,
the "Major Field Data Appendix" spreadsheet for the latest term, and the
same appendix for earlier terms from the page's archive.

Get: each appendix xlsx.

Put in: `aiindex/data/raw/nsc/`, names unchanged. The reshape into
`major_field_appendix.csv` is written once the layout is seen; the task
"Fetch the Clearinghouse major field appendix" covers it.

## 11. Flows transition matrix, new, from the flows repository

Export from the flows account, when you decide to release it:
- `transition_matrix.csv` with columns `year, age_band, origin,
  destination, flow, se` (age_band "all" plus the bands; origin and
  destination on the flows account's occupation coding; flow in weighted
  persons; se from the replicate weights).
- `arrivals.csv` with columns `year, occupation, from_education,
  from_other_occupations, from_outside_work, stock`.

Put in: `aiindex/data/raw/flows/`.

## 12. Indeed AI tracker, already real

`aiindex/data/raw/indeed_ai_posting.csv` is fetched from the publisher's
own repository and needs nothing.

## After placing files

    pip install -r requirements.txt
    python -m aiindex.build
    python -m pytest aiindex/tests

Then read `aiindex/output/build_report.json` for the grade count, which
should show no "mirror", and `aiindex/output/checks.csv` for any check
that failed.
