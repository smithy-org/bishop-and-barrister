# Roadmap

Everything planned for Bishop & Barrister that is not done yet, grouped by what it waits on. The design behind
most of it is [plan 028](plans/028-rules-library-and-judge.md). Last updated 2026-10-25.

## Done

- Its own public repository, smithy-org/bishop-and-barrister, carrying the skill's history from Smithy.
- The name Bishop & Barrister.
- The Apache-2.0 licence, with the Fan Content statement in `NOTICE`.
- The Windows output fix, legality in every format, and the corrections to SKILL.md.
- Plan 028 accepted as the design.

## Waiting on the maintainer

These need accounts, money or a decision that only the maintainer can make.

| Item                     | What to do                                                                                                                                                                                                                         | Then                                                                                                                  |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Tip link                 | Open a [Ko-fi](https://ko-fi.com) page (any amount; no platform fee on tips) and/or apply for [GitHub Sponsors](https://github.com/sponsors) (needs bank and tax details). Pick which account receives it: your own, or smithy-org | Add `.github/FUNDING.yml` and a tip line in the README. The link must stay optional and allow $0 (Fan Content Policy) |
| The old claude.ai upload | `anthropic-skills:mtg-rules` (uploaded 2026-09-08) is out of date. Disable it in claude.ai's skills settings, or replace it                                                                                                        | Optional: upload a zip of this repository as Bishop & Barrister instead                                               |
| Smithy's copy            | Review and merge smithy-org/smithy-discord-activity PR 604, which deletes Smithy's copy and points its scripts at `~/.claude/skills/bishop-and-barrister`                                                                          | Nothing here; Smithy is just another user of the skill                                                                |

## To build (plan 028)

In order; each phase is one pull request or more.

| Phase | Ships                                                                                                                                                                                                                             | Waits on                             |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| 0     | Done 2026-10-25: 13 cases in `evals/`, baseline in `evals/BASELINE.md` (98% with the skill, 95% without). The set is too easy; the next iteration adds citation-accuracy checks and questions newer than the training data        | Nothing; next                        |
| 1     | `judge.py` with the git record, the SQLite index and the object store, pre-filled from Scryfall's bulk rulings. Rulings with agent fields, rendered as XML. The judge procedure in SKILL.md. `card.py` shows each ruling's source | Phase 0, so the effect is measurable |
| 2     | `sources.py`: the MTR, IPG and JAR via `pypdf`; `lookup.py --doc`; `recheck` after each update. The trusted-sources allowlist                                                                                                     | Phase 1                              |
| 3     | `reference/formats/` split one file per format, each with the versions of its sources                                                                                                                                             | Phase 2                              |
| 4     | Optional sync: a private git remote for the record, a RustFS bucket for the object store                                                                                                                                          | Phase 1, and the RustFS check below  |
| 5     | The release: the tip link, a version tag, install notes for Claude Code and claude.ai                                                                                                                                             | The tip link above                   |

## To check before building

Facts the plan relies on that were not confirmed on 2026-10-25.

| Check                                                                                                                                 | Before                   |
| ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| RustFS's own releases page: is 1.0 stable, and does distributed mode exist? Reports disagree                                          | Phase 4                  |
| Whether GitHub Sponsors lets a sponsor enter their own amount, or only pick a tier                                                    | Choosing the tip service |
| Which trusted sources claude.ai's sandbox can reach (Scryfall, Wizards, Magic Judges)                                                 | Phase 2's install notes  |
| Scryfall's terms for the bulk rulings file: downloading it on each user's machine is fine; confirm nothing in the plan republishes it | Phase 1                  |

## Upkeep, after each Comprehensive Rules release

- `python scripts/update_rules.py`, then re-check every CR number cited in `reference/formats.md`.
- Once phase 1 ships: `judge.py recheck`, then review the rulings it flags.
- Re-run the evals.

## Later (ideas, not planned)

- A public website where rulings are challenged and settled socially, reopening a settled ruling once enough
  challenges pile up. See plan 028's "Later" section for what it would need first.
- Search by meaning (`sqlite-vec`), only if the evals show the index missing paraphrased questions.
