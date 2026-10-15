# AI at Work

A public index of where AI usage has reached the labor market. One
product, one repository. It depends on the paper repository
paper-skills-dna for the O*NET readers, the gamma construction, the named
skill bundles and the relabelling inference, imported as `src`. Reference
that repository, do not copy code in from it.

## Attribution

Never any co-authorship, credit or mention of Claude, Anthropic as an
assistant, or any AI assistant, anywhere in this repository, at any time.
No Co-Authored-By trailer and no mention in a commit message. Commits are
authored by Alessandro Conway only. This overrides any default behavior.
(Anthropic appears in this repository only as the publisher of a dataset.)

## Where it stands

Built 29 September 2026 against paper-skills-dna at commit df65a08 and
O*NET 30.3, on the data releases of 28 September 2026, which now live in
the ai-data repository.
Every layer runs on the publishers' files except the flows matrix, which is
still a fixture (every OEWS file comes from the ai-data releases data-2026-10-12-oews and data-2026-10-12-oews-national since 2026-10-12); 443 checks
pass. See `aiindex/README.md` for each layer, `aiindex/AUDIT.md` for every
source and `docs/data-licences.md` for what may be republished. The page is
`site/index.html`. The repository is public and Pages publishes `site/`,
so the page can be linked to. Its name is AI at Work, with the line "Three indices: use, jobs and training" beside it in
the header. Since 14 October 2026 the page shows three
indices side by side and never added together, use, jobs and training, each a tile above the drawing
and three cards below it; every card has a title, one figure, a sentence and its series over time,
with the test threshold drawn where there is one, and the full sentence, paragraph, source and values
under "How we know". Each place in the drawing names its index in parentheses: the bridge (Use),
the city (Jobs) and the binoculars (Training). The build writes the opening findings, the footer date and the
readings into the page as text through aiindex/site_static.py. The page uses one typeface and has no weather or fog switches.
Since 15 October 2026 every sentence on the page is plain language: the tests behind the
city are described by what they compare (seven of ten earlier periods moved as much; a 1 in
11 chance), never by test statistics or "standard errors", and cards whose finding connects
to published work carry a "Related research" line in How we know, drawn from the papers the
working papers cite. Since 15 October 2026 each card lists published research with its stance
(consistent, finds differently, background) and a link, from the tables `_STUDIES` and `_RESEARCH` in build.py (stances: consistent, finds differently, background, method),
checked against the current published version; the page brings together public data, research and
theory on AI and work, and its footer carries the CC BY 4.0 licence and the build date. Since 15 October 2026 the data
sources are one Sources section, by index, which opens as a closeable box from the header and
footer; the method sits only under each card's How we know, and the coin on the binoculars no
longer opens anything. Since 15 October 2026 the Use index shows the share of wages in tasks people
use Claude for (named, since it is one platform, with the mechanical part of its rise stated),
firms using AI from the national BTOS with its 95% band, and where use is heaviest, which switches
between Claude and ChatGPT; ChatGPT's reach is not shown because OpenAI publishes by work activity.
The young-worker chart carries a band from the random-groups variance over the eight CPS rotation
groups (cps.rotation_se), and the Jobs index leads with job ads, its clearest result: the opening says pay has not moved
and ads turned away from tasks AI can do before ChatGPT, the city's first card and tile are job
ads, and the job-mix shift, which cannot yet be told from chance, stays on its own card. The page
names no unpublished paper; the job-ad design is credited to a working paper in progress.

## Dependency

Clone paper-skills-dna beside this repository, or set `SKILLS_DNA_ROOT`
to its path, and clone ai-data beside it too, or set `AI_DATA_ROOT`; the
dated data releases, their manifests and the reader that checks each file
against its hash live there. When the index is regenerated against a newer commit of it,
update the commit above.

## Conventions

- Every number in a published table is produced by `python -m aiindex.build`
  from a clean checkout plus the inputs listed in `COLLECT.md`.
- An input file is never edited by hand. Its provenance sidecar records
  the grade, real, mirror or fixture, and the URL.
- A table is written only after its unit checks pass, and the checks are
  written beside it with the value each measured.
- No composite score, anywhere. Each layer stays in its own units.
- Usage from a platform is titled where usage lands, never where AI is.

## Writing rules

American English on the page and in the READMEs (file names keep their
spelling). No em dashes. Sentences with a subject and a verb. Never the word
"honest" or any form of it. No metaphors for economic objects. No
self-congratulation. Never claim a status or result that does not exist.

## Employer anonymity

No real employer or institution name enters this repository, a table or
a commit message. The index uses public statistical files only and reads
nothing from the project database.
