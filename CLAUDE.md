# AI index

A public index of where AI usage has reached the labour market. One
product, one repository. It depends on the paper repository
paper-skills-dna for the O*NET readers, the gamma construction, the named
skill bundles and the relabelling inference, imported as `src`. Reference
that repository, do not copy code in from it.

## Attribution

Never any co-authorship, credit or mention of Claude, Anthropic as an
assistant, or any AI assistant, anywhere in this repository, at any time.
No Co-Authored-By trailer and no mention in a commit message. Commits are
authored by Alessandro Conway only. This overrides any default behaviour.
(Anthropic appears in this repository only as the publisher of a dataset.)

## Where it stands

Built 29 September 2026 against paper-skills-dna at commit df65a08 and
O*NET 30.3, on the data releases of 28 September 2026, which now live in
the ai-data repository.
Every layer runs on the publishers' files except the flows matrix, which is
still a fixture, and OEWS 2012 to 2024, which are checked copies; 443 checks
pass. See `aiindex/README.md` for each layer, `aiindex/AUDIT.md` for every
source and `docs/data-licences.md` for what may be republished. The page is
`site/index.html`. The repository is public and Pages publishes `site/`,
so the page can be linked to, and it carries no name yet.

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

No em dashes. Sentences with a subject and a verb. Never the word
"honest" or any form of it. No metaphors for economic objects. No
self-congratulation. Never claim a status or result that does not exist.

## Employer anonymity

No real employer or institution name enters this repository, a table or
a commit message. The index uses public statistical files only and reads
nothing from the project database.
