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

Built 20 September 2026 against paper-skills-dna at commit 9da9a31 and
O*NET 30.2. Every layer runs; see `aiindex/README.md` for what ran on the
publisher's files and what ran on fixtures, and `aiindex/AUDIT.md` for
every source. `COLLECT.md` lists the files to place by hand.

## Dependency

Clone paper-skills-dna beside this repository, or set `SKILLS_DNA_ROOT`
to its path. When the index is regenerated against a newer commit of it,
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
