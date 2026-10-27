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

| Phase | Ships                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Waits on                            |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| 0     | Done 2026-10-25: 25 cases in `evals/` (classic, newer than the training data, and hard-card interactions), each with a citation check; baseline in `evals/BASELINE.md`: 99% with the skill, 73% without                                                                                                                                                                                                                                                                   | Done                                |
| 1     | Merged 2026-10-25 (#1): `judge.py` (build, index, search, record, discuss, review, show, recheck) with the git record, the SQLite index and the object store, pre-filled with 79,706 rulings from Scryfall's bulk file; rulings with agent fields, rendered as XML; the judge procedure in SKILL.md; `card.py` shows each ruling's source. Evals rerun (iteration 4): 96%, 13 of 25 answered from official rulings in the record. Still to do: agent fields on official rulings when the judge relies on one | Nothing |
| 2     | Merged 2026-10-25 (#3): `sources.py` downloads the MTR, IPG and JAR from media.wizards.com and converts them with `pypdf`; `lookup.py --doc`; rulings cite their sections, pinned by hash; `recheck` after each update; `reference/trusted-sources.json`. Evals: iteration 5 25/25 on the tournament cases (13/25 without); token cuts in iteration 6 (−17% time, −28% answer length), 41/41 after iteration 7 | Nothing |
| 3     | Merged 2026-10-26 (#4): `reference/formats/`, one file per format plus `matches.md`, each with a header of the CR and MTR versions it was checked against; every fact re-checked against the local CR and MTR; `sources.py` names the files to re-check after an update; a test checks every cited number exists | Nothing |
| 4     | Optional sync through the user's own RustFS bucket (1.0.4 or later), no git host: (a) `judge.py sync` with one git bundle per device, merged, never rebased; `config.json` gitignored, keys from the environment; S3 signed with the standard library. (b) Every CR, MTR, IPG and JAR release kept in the object store by hash, and citations record the release they used. (c) Objects synced by hash. Tested against a local RustFS container. The bucket stays private: a public one would republish Scryfall's and Wizards' files | Nothing |
| 5     | The release: the tip link, a version tag, install notes for Claude Code and claude.ai                                                                                                                                                                                                                                                                                                                                                                                     | The tip link above                  |

## To check before building

Facts the plan relies on that were not confirmed on 2026-10-25.

| Check                                                                                                                                 | Before                   |
| ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| RustFS's releases: checked 2026-10-26. 1.0.0 released 2026-09-16, 1.0.4 on 2026-10-25; an RPC authentication bypass was patched, so require 1.0.4 or later | Done |
| Whether GitHub Sponsors lets a sponsor enter their own amount, or only pick a tier                                                    | Choosing the tip service |
| Which trusted sources claude.ai's sandbox can reach (Scryfall, Wizards, Magic Judges)                                                 | Phase 2's install notes  |
| Scryfall's terms for the bulk rulings file: downloading it on each user's machine is fine; confirm nothing in the plan republishes it | Phase 1                  |

## Upkeep, after each Comprehensive Rules release

- `python scripts/sources.py update`; it names the `reference/formats/` files to re-check.
- Review the rulings `judge.py recheck` flags (`sources.py update` runs it).
- Re-run the evals.

## Later (ideas, not planned)

- A public website where rulings are challenged and settled socially, reopening a settled ruling once enough
  challenges pile up. See plan 028's "Later" section for what it would need first.
- Search by meaning (`sqlite-vec`), only if the evals show the index missing paraphrased questions.
