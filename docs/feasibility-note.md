# Feasibility assessment: a public index of where AI usage has reached the labour market

Alessandro Conway. Working note, 20 September 2026. This note belongs to the
index project once that repository exists, and sits here on a branch only
because the machinery it tests is this paper's.

## What was tested and how

The design under test joins three layers, each in its own units and never
composited: a national layer that maps observed AI usage into the wage bill
and tests realised wages and employment against a stated detection
threshold; a state layer at annual cadence carrying exposure, adoption and
capacity; and a pipeline and capacity layer that sizes arrivals from
education against lateral arrivals from other occupations.

Each source was tested for four things: whether it is reachable and under
what licence, whether it carries the grain and cadence the layer needs,
whether the join to the occupational spine closes, and what harmonisation
the join costs. The sandbox used for this note reaches GitHub and nothing
else: every official statistical host, and Hugging Face, refused the
connection. So the verification column below distinguishes three grades.
"Opened" means the file was downloaded and inspected here. "Code" means the
join is already implemented in `src/` of this repository and has run
against the data. "Documented" means the claim rests on the publisher's
documentation and on the sibling papers, and has to be confirmed by
opening the file in an environment that reaches the host, which is the
first task of the build.

## Source by source

### Anthropic Economic Index (usage by O*NET task)

Grade: code for the task join, documented for the monthly schema.

- Licence CC-BY 4.0. Six releases from February 2025 to June 2026. Task
  metrics with an O*NET task identifier, usage share, and the automation and
  augmentation split, already flow into this repository through the lake
  table `aei_task_metrics`, and `src/within_occupation.py` runs on them, so
  the join from usage to the task-to-skill weights and then to the 25
  bundles is built and tested.
- Geography starts with the September 2025 release. From the June 2026
  release the schema changed to calendar-month aggregates with a
  `geo_level` column and ISO 3166-2 subregion codes, so US states read as
  `US-CA`. The monthly usage files exceed 200 MB. Filenames changed
  convention at the same time and the raw-versus-enriched variant was
  dropped. The R package `aieconindex` documents these breaks and is a
  usable reference for the harmonisation.
- Anthropic also publishes standalone labour-market tables, job exposure
  and task penetration, from the Massenkoff and McCrory work of March
  2026, which already finds a slowdown of about 14 percent in hiring of
  22 to 25 year olds into the most exposed occupations. That is the
  vendor's own version of the outcome test.
- Two costs. The lake export used here comes from the project database, so
  a public index must ingest from Hugging Face directly and re-derive the
  task identifiers itself, which means re-implementing the product's
  ingestion in `src/`. And the platform-selection problem is now a
  published result, Yin and Ogut (2026), who show that varying only the
  platform changes the post-2022 employment coefficient by a factor of
  1.9 and that reweighting to workforce shares attenuates estimates by 42
  to 93 percent. The usage layer therefore has to carry more than one
  platform and be titled as where usage lands, never as where AI is.

### OpenAI Signals (usage by work activity)

Grade: documented.

- CC-BY 4.0, CSV downloads, consumer accounts only, July 2024 to June 2026,
  with a data dictionary. Work-related shares are published by O*NET
  intermediate work activity, not by task. The join therefore runs through
  the work-activity hierarchy, which `src/onet.py` already walks from tasks
  to detailed work activities and up, and the allocation from an
  intermediate activity down to its tasks has to be stated as an
  assumption: equal shares across the activity's tasks, or task importance
  weights, with the difference reported. This is a coarser column than the
  Anthropic one and should be presented as such.

### WildChat mapping (Somerstep, Guha, Srivastava and Sun 2026)

Grade: documented.

- Open dataset `umich-fatml/OpenEconIndex` on Hugging Face with stable
  O*NET task identifiers, code on GitHub. A single snapshot of free-tier
  ChatGPT use in 2023 and 2024 with heavy translation traffic. Useful as a
  third usage column for the platform-selection comparison and for nothing
  else. No time series.

### OEWS (wages and employment by occupation, national and state)

Grade: code.

- The balanced national panel, 693 occupations across 2012 to 2025, and the
  state panel, `foundation.state_panel`, both exist and run. The 2010 to
  2018 SOC crosswalk with coverage reporting is in `src/oews_history.py`.
- The one reliability problem is ingestion. BLS refuses every automated
  request from the whole of bls.gov, and the files are downloaded by hand
  into `data/raw/oews/`. For a product that promises regeneration from a
  clean checkout this is a manual step once a year, and it must be
  recorded in a manifest exactly as the database snapshots are. It is
  acceptable at annual cadence and would not be at any faster one.

### CPS basic monthly (the young-worker gauge)

Grade: documented.

- Public use files, fixed width with a record layout per year, monthly.
  Occupation is `PEIO1OCD`, a four-digit Census 2018 occupation code from
  January 2020, with age, labour-force status, hours and state. The
  Census occupation to SOC 2018 crosswalk is a published spreadsheet and
  is many-to-one in places, so exposure has to be assigned at the Census
  code by employment-weighting the SOC codes it contains.
- Sample arithmetic: about 60,000 households a month, roughly 5,000 to
  6,000 employed persons aged 22 to 27 with an occupation code, so about
  1,800 per exposure tercile per month. That supports a monthly series of
  the employment share of young workers in the top tercile relative to the
  rest, pooled over three months, with the relabelling inference this
  project uses. The 4-8-4 rotation means consecutive months share three
  quarters of their sample, which the reference distribution has to
  respect by relabelling at the rotation-group level.
- This gauge is no longer a first. The Stanford and ADP Canaries
  Dashboard, launched in mid 2026 and updated monthly, reports the same
  quantity on payroll data covering about a sixth of workers, and the
  August 2026 revision puts the young-worker gap in exposed occupations
  at 19 percent. What a CPS version adds is a representative sample, a
  published detection threshold, and independence from one payroll
  provider. That is a replication with a stronger design, and it should be
  presented as one.

### Census BTOS (firm adoption by state and sector)

Grade: documented.

- Biweekly, public downloads by state, sector, three-digit subsector,
  employment size class and the 25 largest metros. The core question, use
  of AI in producing goods or services in the past two weeks, has run since
  September 2023, so a three-year state series exists. A supplement with
  more detailed AI questions ran from November 2025 to February 2026 and is
  a one-off. Files are wide, one column per collection period, with
  question and answer codes, and the harmonisation is a reshape plus a
  period calendar. Firm-level adoption does not join to occupations at
  all, so this enters the state layer as its own column and never as an
  input to exposure.

### Indeed Hiring Lab AI tracker

Grade: opened.

- CC-BY 4.0, daily from January 2019 to August 2026, nine countries, one
  variable: the share of postings mentioning AI terms, seven-day trailing.
  The US series ends August 2026 at 6.7 percent. The generative-AI file
  named in the README is absent from the repository. No occupation or
  state breakdown in the public files. It is a national context line and
  nothing in the design depends on it.

### Postings task composition (Appendix B of the paper)

Grade: blocked, unchanged.

- The NLx series is still not in hand. The New York Fed ran a postings
  test in May 2026 on Lightcast data and found the relative decline in
  exposed-occupation vacancies began before late 2022 with no junior
  versus senior gap, which is the reading the paper's Appendix B would
  test on public data. The USAJOBS API remains the only fully public
  full-text corpus and covers federal hiring only.

### National Student Clearinghouse (enrolment by field)

Grade: documented.

- Current Term Enrollment Estimates in January and May, and a final
  spring report in June, with a Major Field Data Appendix as a
  spreadsheet. Major fields are the Clearinghouse's own groupings of
  two-digit CIP codes, so a mapping table from their labels to CIP is a
  small hand-built file to be committed. State-level estimates are
  published, but state by major field is not indicated in the
  documentation and should be assumed absent until the appendix is opened.
  Consequence: the enrolment series by field exposure is national.

### IPEDS completions (awards by field, institution and state)

Grade: documented.

- Annual, complete data files by six-digit CIP 2020, award level and
  institution, joined to institution state through the header file. The
  provisional release lags the award year by about a year. This is the
  only field-by-state source and it is annual, which sets the cadence of
  the state capacity column.
- The NCES CIP 2020 to SOC 2018 crosswalk is a published spreadsheet and
  is many-to-many. It is a statement of intended destinations rather than
  observed ones, and the observed link, field of degree to occupation, is
  available in the ACS microdata through the field-of-degree variable.
  The design should use the ACS link for the exposure of a field and keep
  the NCES crosswalk as a comparison, since the point of this programme is
  revealed rather than declared destinations.

### The bilateral transition matrix (lateral capacity)

Grade: built in the sibling repository and not published.

- The flows account exists for 230 occupations, 2009 to 2025, by age band,
  with replicate-weight standard errors. The full origin by destination
  matrix is described in the moves and shortage papers as built and not
  yet published, and both of those papers wait on it. Lateral capacity in
  the index is the same object. This is the single hard dependency in the
  design that is not a download: the capacity column cannot be built
  until that matrix is released from the flows repository, and releasing
  it is a decision about the sibling papers, not about the index.
- Transition rates are national and annual, at 230 occupations rather
  than the 693 of the wage panel, so capacity is computed at the flows
  grain and applied to state stocks, with the mismatch in occupation
  detail stated.

## Does the logic hold

- **Usage into the wage bill.** Sound and already running for one platform.
  The weak point is platform selection, which is now a published critique,
  and the answer is to show three platforms side by side rather than to
  pick one. The OpenAI column is coarser by construction.
- **Detection threshold as the headline.** Sound, and the machinery exists
  at annual cadence. At monthly cadence it depends on a CPS build that is
  new work and on rotation-aware inference.
- **State layer at annual cadence.** Sound, and the exposure part already
  runs. The realised-change part carries the Check C noise finding and has
  to be shown with intervals.
- **Capacity through lateral flows.** The argument is sound and the size
  ordering is established, but the object it needs is unpublished. Until
  it is, the capacity column can show only the education channel with its
  measured size, which is the smaller channel, and the note has to say so.

## Assessment

The national usage layer and the annual outcome test can be built now from
code in this repository, with one re-implementation, the Hugging Face
ingestion, and one manual annual step, the OEWS download. The CPS gauge is
new work of a few weeks and enters a field where a dashboard already
exists, so its claim is design and representativeness rather than novelty.
The state layer is a composition of things that exist and can follow within
a month of the national layer. The pipeline column is straightforward and
annual. The capacity column is the differentiator and is blocked on the
transition matrix.

Order of work, if the design is accepted: ingest Anthropic and OpenAI from
their public files and reproduce the existing task join from them; build
the three-platform wage-bill mapping; publish the annual outcome test as a
series with its threshold; then the CPS gauge; then the state layer; then
enrolment by field exposure. Lateral capacity waits on the flows
repository and should be scheduled there.

Two decisions this note cannot make. Whether the flows matrix is released
before the moves and shortage papers use it, since the index needs it
first. And whether the CPS gauge is worth building given the Canaries
Dashboard, which I would answer yes on the grounds above, but which is a
judgement about effort and not about data.
