# 028 — Bishop & Barrister: a rules library and a judge

**Status:** design for review. Nothing here is built. The Windows output fix, legality in every format and two
SKILL.md corrections are already in (the latest commit carried over from the old home).
**History:** written in smithy-org/smithy-discord-activity (PR 601), where the skill used to live, and moved
here with the skill's history on 2026-10-25. The number 028 is kept from there.
**Decided with the user (2026-10-25):**

- The skill becomes a rules library and a rules judge, and is open-sourced for other Claude users. It is free
  to download; users can tip what they think it is worth.
- Sources are ranked by authority. Informal posts by Wizards staff rank **below** the Comprehensive Rules, not
  above them.
- The skill is a project of its own, with no connection to Smithy: no shared code, data, CI or tooling. It
  lives in this public repository, smithy-org/bishop-and-barrister.
- The formats covered are Commander, Brawl, Oathbreaker, Standard, Pioneer, Modern, Legacy, Vintage, Pauper,
  Draft and Sealed. This is the skill's own list, maintained in the skill.
- Each user's rulings are their own. The database starts pre-filled with official rulings. When nothing matches,
  the judge works the question out and records an **unreviewed** ruling with its sources. The user and the model
  discuss it, and the user marks it **reviewed**. The discussion is kept with the ruling, and none of it leaves
  the user's machine.
- Git is the record, so every ruling, decision and source has a traceable history, much like an amended
  statute. SQLite is only a search index, rebuilt from the git files. Large files go in a local object store.
- Sync across the user's own devices is optional: a private git remote for the records, and the user's own
  RustFS bucket for the large files. A server shared by several users is out of scope.
- `pypdf` is added, to read the tournament documents.
- Tournament procedure and penalties are in scope.
- The project is named **Bishop & Barrister** and licensed under **Apache-2.0**, with the Fan Content statement in
  `NOTICE` so that redistributions must carry it.

## What exists

This repository, as moved:

- `scripts/lookup.py` searches a downloaded copy of the Comprehensive Rules (CR). The copy is gitignored and
  fetched by `scripts/update_rules.py`, which compares content hashes to spot a new release.
- `scripts/card.py` reads Oracle text, legality and rulings from Scryfall.
- `reference/formats.md` is one hand-written file covering each format on the skill's list and matches of
  several games, with a source for each fact.

Nothing is remembered between sessions. Each question is answered from scratch, and the answer exists only in
that conversation.

A second copy of the skill, `anthropic-skills:mtg-rules`, is the user's claude.ai upload from 2026-09-08. It
predates the format notes and the Windows fix. Replacing it is the user's call, after the open-source release.

## What it is used for

The user's two questions so far, and the ones the skill should expect next. Each ruling records its
`question_type`, and each type has the fields it needs (piece 3).

| `question_type`  | Asked as                                                   | What the ruling must give                                                        |
| ---------------- | ---------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `interaction`    | "Should this card and this card interact?"                 | Whether they interact, how, in what order, and the resulting board               |
| `legality-check` | "This happened in my game. Is this legal?"                 | A verdict for each observed event, and the first one that broke a rule           |
| `sequence`       | "What happens when ...?"                                   | The events in order: what goes on the stack, triggers, state-based actions       |
| `card-text`      | "What does this card actually do?"                         | The Oracle text read correctly, with the near-misses people make                 |
| `deck-legality`  | "Is this deck legal in Commander?"                         | Legal or not, each card or rule that fails, and the format file it came from     |
| `format-rule`    | "Is the first mulligan free in two-player Commander?"      | The answer for that format, from the format file and the CR                      |
| `tournament`     | "What's the fix for drawing an extra card at Competitive?" | The procedure and penalty, from the IPG or JAR, for the stated enforcement level |

The data the skill keeps is shaped for Claude to read (piece 3, "Shaped for Claude"); people read it through
Claude.

## Levels of authority

Every source the skill stores or cites has one level. The skill answers from the highest level that covers the
question. When a lower level disagrees, it says so, and the lower level never overrides a higher one.

| Level | What                                                                                                                                                                                                                                           | Conflicts within the level                                                                                                                              |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | Published by Wizards for all play: current Oracle text, the CR, official rulings (release notes, Gatherer, Scryfall rulings with `source: "wotc"`), announced rules changes                                                                    | Card text beats the rules (CR 101.1). A later effective date beats an earlier one, so an announced change beats a CR file that does not include it yet. |
| 2     | Binding for one format or for tournaments: format pages, the Magic Tournament Rules (MTR), the Infraction Procedure Guide (IPG), the Judging at Regular REL guide (JAR); a community-run format's own rules (Oathbreaker) for that format only | Scoped: a level 2 source never answers a gameplay question that level 1 covers.                                                                         |
| 3     | Informal posts by Wizards staff (X, Bluesky, Discord, articles that are not rules documents)                                                                                                                                                   | Each records its author, role, date, link and an archived copy. Marked superseded once level 1 covers or contradicts it.                                |
| 4     | Judge and community consensus: the judges' annotated pages, Scryfall rulings with `source: "scryfall"`, the Multiplayer Addendum                                                                                                               | Cited with the source, never as "the rule".                                                                                                             |
| 5     | The user's own rulings, reviewed or not                                                                                                                                                                                                        | Precedent for that user only. Each cites levels 1–4 and is re-checked when what it cites changes.                                                       |

**House rules.** Two users can reach different rulings from different arguments, and that is allowed. But a
user's ruling that contradicts level 1 is recorded as a **house rule**, not as the rules. When it comes up, the
judge gives the official answer and the house rule side by side.

## The pieces

### 1. Source documents (level 1 and 2)

`update_rules.py` becomes `scripts/sources.py`, which keeps a registry of downloaded documents:

| Document                   | From                               | Format |
| -------------------------- | ---------------------------------- | ------ |
| Comprehensive Rules        | magic.wizards.com/en/rules         | .txt   |
| Magic Tournament Rules     | wpn.wizards.com/en/rules-documents | PDF    |
| Infraction Procedure Guide | wpn.wizards.com/en/rules-documents | PDF    |
| Judging at Regular REL     | wpn.wizards.com/en/rules-documents | PDF    |

None of them ships with the skill. They belong to Wizards and change several times a year, so each user's copy
downloads them. Each is fetched, hashed, kept in the object store (piece 4), and turned into searchable text;
`pypdf` reads the PDFs.

`lookup.py` takes a document: `lookup.py rule 613.3` stays the CR, and `lookup.py --doc ipg rule 2.1` reads the
IPG.

### 2. One file per format (level 2, summarised)

`reference/formats.md` splits into `reference/formats/<format>.md`, one per format on the skill's list:
`commander`, `brawl`, `oathbreaker`, `constructed` (Standard, Pioneer, Modern, Legacy, Vintage), `pauper` and
`limited` (Draft, Sealed). A shared `matches.md` keeps the rules for matches of several games.

Each file keeps today's rule: every fact names its source and level. Each also gets a header with the date it
was checked and the version of each source, so `sources.py` can list the files to re-check after an update.

### 3. A ruling

A ruling is written to be read by an AI agent, not only by a person. The agent reading it later did not see
the conversation that produced it, has a limited context, and has to decide fast whether the ruling fits the
situation in front of it. So every ruling carries, besides the answer:

- what must be true for it to apply,
- what would change the answer,
- what to ask the user when a fact is missing,
- which wrong answers are tempting, and why they are wrong,
- each reasoning step linked to the citation that backs it.

Every ruling, official or the user's, has the same shape:

```json
{
  "id": "0f6c…",
  "kind": "unreviewed",
  "level": 5,
  "question": "Humility and Opalescence are both on the battlefield. What are the creatures?",
  "question_type": "interaction",
  "aliases": ["Opalescence plus Humility, what P/T", "Humility Opalescence layers"],
  "mechanics": ["layers", "dependency", "timestamps", "type-changing", "P/T setting"],

  "agent_summary": "Self-contained, three to five sentences: the answer, the conditions it holds under, and the deciding rule numbers.",
  "applies_when": [
    { "fact": "Humility and Opalescence are both on the battlefield", "why": "..." },
    { "fact": "No other effect changes the types or P/T of these enchantments", "why": "..." }
  ],
  "answer_changes_if": [{ "if": "Opalescence entered after Humility", "then": "...", "refs": ["c1"] }],
  "ask_if_unknown": ["Which of the two entered the battlefield first?"],
  "misconceptions": [{ "wrong": "...", "why_wrong": "...", "refs": ["c1"] }],

  "situation": {
    "format": "commander",
    "rel": null,
    "objects": [
      { "card": "Humility", "zone": "battlefield", "controller": "A", "timestamp": 1 },
      { "card": "Opalescence", "zone": "battlefield", "controller": "B", "timestamp": 2 }
    ]
  },
  "ruling": "The answer in one or two sentences.",
  "outcome": [{ "object": "Humility", "becomes": { "types": ["..."], "power": null, "toughness": null } }],
  "steps": [{ "n": 1, "text": "Layer 4: ...", "refs": ["c1"] }],

  "citations": [{ "id": "c1", "level": 1, "doc": "cr", "ref": "613.8a", "excerpt": "...", "text_sha256": "..." }],
  "cards": [{ "name": "Humility", "oracle_id": "...", "oracle_sha256": "..." }],
  "related": [{ "id": "…", "relation": "specializes" }],
  "post": { "url": null, "archive_object": null, "author": null, "role": null, "date": null },

  "confidence": "likely",
  "house_rule": false,
  "deliberation_summary": "Arguments considered and why each was accepted or rejected, compressed for an agent.",
  "deliberation": [
    { "by": "user", "at": "2026-10-25T21:04:00Z", "said": "Opalescence came down second, so..." },
    { "by": "model", "at": "2026-10-25T21:04:30Z", "said": "Timestamps don't settle it here: 613.8a..." },
    { "by": "user", "at": "2026-10-25T21:06:00Z", "decision": "reviewed" }
  ],
  "status": "current",
  "cr_sha256": "...",
  "created_at": "2026-10-25T21:03:00Z",
  "updated_at": "2026-10-25T21:06:00Z"
}
```

(The example shows the shape only; its answer is left out on purpose.)

**The fields an agent relies on:**

| Field                  | What it gives an agent                                                                                                                                          |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agent_summary`        | The answer and its conditions in a few self-contained sentences: no "as discussed", no pronouns pointing at the deliberation, exact card names and rule numbers |
| `applies_when`         | The facts that must hold. If one does not hold in the agent's situation, the ruling does not apply                                                              |
| `answer_changes_if`    | The nearby situations with a different answer, so a near miss is not mistaken for a match                                                                       |
| `ask_if_unknown`       | The questions the agent must ask the user before using the ruling, when the situation leaves a deciding fact out                                                |
| `misconceptions`       | The tempting wrong answers and why they are wrong, so the agent does not repeat them                                                                            |
| `situation`, `outcome` | The board before and the result after, as data: an agent can compare them with a described game state without parsing prose                                     |
| `steps`                | The reasoning in order; every step names the citations (`refs`) that back it                                                                                    |
| `citations`            | The cited text itself (`excerpt`), so the agent does not need another lookup unless `recheck` flags a change                                                    |
| `aliases`, `mechanics` | Other ways people ask the same question, and the mechanics involved, for search                                                                                 |
| `related`              | Links to rulings this one generalises, specialises, contradicts or supersedes                                                                                   |
| `deliberation_summary` | The arguments already made and settled, so the agent does not reopen them. The full `deliberation` stays for the user                                           |

**Checked on record.** `judge.py record` refuses a ruling that has no `agent_summary`, no `applies_when`, a step
without `refs`, or a `ref` that names no citation. `ask_if_unknown`, `answer_changes_if` and `misconceptions`
may be empty, but must be present, so an empty list means "none" rather than "not thought about".

**Official rulings.** Scryfall's rulings arrive as one paragraph per card, without these fields. The first time
the judge relies on one, it fills them in. The original text stays as it was, `kind` stays `official`, and the
added fields are marked as written by the model.

**Legality checks.** A `legality-check` ruling also records what was observed and a verdict for each event:

```json
{
  "question_type": "legality-check",
  "observed": {
    "source": "paper",
    "events": [
      {
        "n": 1,
        "actor": "A",
        "action": "cast",
        "card": "...",
        "targets": ["..."],
        "zone_from": "hand",
        "zone_to": "stack"
      },
      { "n": 2, "actor": "B", "action": "activate", "card": "...", "during": "A's main phase 1, A holds priority" }
    ],
    "raw": "The user's own words: 'I cast Lightning Bolt at their creature and they activated ... in response'"
  },
  "verdicts": [
    { "event": 1, "verdict": "legal", "refs": ["c1"] },
    { "event": 2, "verdict": "illegal", "refs": ["c2"], "why": "B does not have priority (117.3a)" }
  ],
  "first_illegal_event": 2
}
```

- **Described in words.** Most users describe what happened at a paper table, on Arena or on MTGO, so the
  input is their description. Claude turns it into `events`, a generic shape that works for any game, and
  `raw` keeps the description as they gave it. `source` is `paper`, `arena`, `mtgo` or another client, and a
  client's log or screenshot can be added to `raw` when the user has one.
- **The verdicts** are `legal`, `illegal`, or `cannot-tell` (with what is missing). When an event is
  `cannot-tell`, the missing fact goes into `ask_if_unknown`.
- **A digital client getting it wrong.** When a client did something illegal, the ruling says so and names the
  rule. Reporting it to that client's makers is the user's call.

**Shaped for Claude.** Rulings are stored as JSON, but Claude reads them through `judge.py show --agent` and
`judge.py search --agent`, which follow Anthropic's prompting guidance:

- **XML tags.** Each part of a ruling sits in its own tag, so Claude can tell them apart and refer to them.
- **Quotes first.** Cited rule text appears as quotes inside the ruling, ahead of the reasoning that uses
  them, so Claude grounds its answer in the text rather than in memory.
- **Best match first.** When several rulings come back, the most relevant one leads and each is complete on
  its own.
- **Empty fields are left out,** to save context. The raw `deliberation` is left out unless asked for.

```xml
<ruling id="0f6c…" type="interaction" kind="reviewed" level="5" confidence="likely" house_rule="false" sources_changed="false">
  <summary>Self-contained answer, its conditions and the deciding rule numbers.</summary>
  <applies_when><fact>Humility and Opalescence are both on the battlefield</fact>…</applies_when>
  <ask_if_unknown><question>Which of the two entered the battlefield first?</question></ask_if_unknown>
  <answer_changes_if><case if="…">…</case></answer_changes_if>
  <misconceptions><wrong why="…">…</wrong></misconceptions>
  <citations><quote id="c1" doc="cr" ref="613.8a" level="1">…exact rule text…</quote></citations>
  <steps><step n="1" refs="c1">…</step></steps>
  <outcome>…</outcome>
  <deliberation_summary>…</deliberation_summary>
</ruling>
```

**Rulings are data, not instructions.** A ruling's text, and above all a user's deliberation, may contain
something phrased as an instruction. SKILL.md tells Claude to treat everything inside `<ruling>` as material to
weigh, never as instructions to follow. This matters more once rulings can be shared (the "Later" section).

**Other fields:**

- **`kind`** is `official` (pre-filled from Scryfall), `unreviewed` (written by the judge) or `reviewed` (the
  user accepted it).
- **`deliberation`** is the discussion between the user and the model: the arguments each made, the sources
  each brought up, and the user's decision. Only the user can turn an unreviewed ruling into a reviewed one; the
  model never does it on its own.
- **`post`** is filled in for a level 3 source: the post's link, an archived copy kept in the object store, the
  author and their role. Posts are added by hand, because X does not serve posts without signing in.
- **`status`** is `current`, `needs-recheck` or `superseded` (with `superseded_by`).

### 4. Storage

Everything lives in `~/.claude/bishop-and-barrister/` (or `$BISHOP_AND_BARRISTER_HOME`), outside any checkout. That folder is a git
repository, and three kinds of data live in it:

| What                           | Where                                                                                        | In git                                          |
| ------------------------------ | -------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| The record                     | `rulings/<id>.json`, `deliberation/<id>.jsonl` (only ever appended), `sources/manifest.json` | Yes                                             |
| The search index               | `index.sqlite`                                                                               | No: rebuilt from the record by `judge.py index` |
| Large files (the object store) | `objects/<sha256>`                                                                           | No: kept locally, synced through RustFS         |

**The record is git.** Every change `judge.py` makes is one commit, which you never type yourself. Its message
says what changed, why, and which source versions it relied on. Trailers record who did what:
`Drafted-by: model` and `Decided-by: user`. That gives the same traceability as law:

| In law                        | Here                                                                                                                                            |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| A statute's amendment history | `git log rulings/<id>.json`: every change to a ruling, with its diff and reason                                                                 |
| Who drafted, who decided      | The commit trailers                                                                                                                             |
| Citing a specific edition     | Each citation pins its source's hash; `sources/manifest.json` maps the hash to the URL, date and level                                          |
| "Is this still good law?"     | `recheck` flags a ruling when a cited source changes; the fix is a commit giving the reason, for example "amended: CR 2026-09-25 changed 613.8" |
| Overruled by                  | Superseding is a commit that links the old ruling to the new one                                                                                |
| The law as of a date          | A git tag for each CR release: "my rulings as of CR 2026-09-25"                                                                                 |
| Who changed this, and why     | `git blame` on a ruling                                                                                                                         |

Deleting a ruling also leaves a commit; removing one for good means rewriting history on purpose.

Official rulings from Scryfall are not committed; they are downloaded and loaded straight into the index. Only
the agent fields the judge adds to one (piece 3) are committed, as an overlay keyed by the official ruling.

**The index is SQLite.** Python's built-in `sqlite3` (SQLite 3.45 with FTS5 on this machine), with:

- exact-key tables for cards (by Oracle ID), rule numbers and mechanics, which most questions hit first;
- full-text search (FTS5) over the question, aliases, summary, ruling, reasoning and deliberation.

It can be deleted at any time; `judge.py index` rebuilds it from the record in seconds. Semantic search (the
`sqlite-vec` extension) is added only if the evals show the index missing paraphrased questions.

**The object store** holds each downloaded document release, each archived post, page or screenshot, and
Scryfall's bulk file, each named by the hash of its content. A file is stored once and never changes, so a
citation can point at the exact copy of the document it relied on, even after a newer release. These files
stay out of git: some are large, and the rules documents are Wizards' material.

**Pre-filled.** `judge.py build` downloads Scryfall's bulk `rulings` file (`/bulk-data/rulings`, gzipped JSON
Lines, 5.4 MB on 2026-10-25) and loads it: rulings with `source: "wotc"` as official level 1, those with
`source: "scryfall"` as level 4. It refreshes when Scryfall publishes a new file (daily). The file is downloaded
on each user's machine, never shipped with the skill: Scryfall's terms forbid republishing its data as is.

**Sync across the user's own devices (optional).** Two remotes, both the user's own, set in
`~/.claude/bishop-and-barrister/config.toml`:

- **A private git remote** (GitHub, GitLab, a self-hosted server) for the record. `judge.py sync` pulls with a
  rebase, then pushes. One file per ruling and append-only deliberation files keep conflicts rare. A real
  conflict on the same ruling is shown to the user to settle; it is never merged by guesswork.
- **A RustFS bucket** for the object store. RustFS is a self-hosted, S3-compatible object store (Apache-2.0),
  and the README shows how to run one. `sync` uploads and downloads objects by hash, so nothing is copied
  twice. This keeps the archived pages, which cannot be downloaded again, and old document releases after
  Wizards stops hosting them. The skill speaks plain S3, so any S3-compatible store works; RustFS is the one
  documented and tested. Its maturity is still settling (reports disagree on whether 1.0 is stable), so phase 4
  checks its own releases page first.
- **No remote database.** Each device rebuilds its own index from the synced record.

`boto3` is needed only by users who turn on the bucket. Nothing here is designed for several users sharing one
server; it may happen to work, but it is out of scope.

**claude.ai.** Its sandbox does not keep files between sessions. Without sync, the index is rebuilt each session
and the user's rulings are forgotten. With sync, and if the sandbox can reach the remotes, each session clones
the record, rebuilds the index, and fetches objects only when a ruling needs one.

### 5. The judge

`scripts/judge.py`:

| Command                        | Does                                                                                                                                          |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `judge.py build`               | Set up `~/.claude/bishop-and-barrister/` (git init on first run), download Scryfall's bulk rulings into the object store, and build the index |
| `judge.py search <text>`       | Rulings by text, card or rule number: official first, then reviewed, then unreviewed                                                          |
| `judge.py record <file>`       | Store a new unreviewed ruling given as JSON (the shape above)                                                                                 |
| `judge.py discuss <id> <file>` | Add entries to a ruling's deliberation                                                                                                        |
| `judge.py review <id>`         | Mark a ruling reviewed, only on the user's say-so, recording their decision                                                                   |
| `judge.py show <id>`           | One ruling with its citations and deliberation; `--agent` for the compact agent form                                                          |
| `judge.py recheck`             | Mark `needs-recheck` every ruling whose cited rule text or Oracle text has changed                                                            |
| `judge.py index`               | Rebuild the SQLite search index from the git record and the downloaded official rulings                                                       |
| `judge.py sync`                | Pull and push the git remote, and upload and download objects in RustFS, if configured                                                        |

`sources.py` runs `recheck` after it installs a new document. Rule numbers alone are not enough to spot a
change, because rules get renumbered; the hash of each cited rule's text is.

SKILL.md gains the judge procedure, used for every rules question:

1. **Search the database.** `judge.py search --agent` by card names, mechanic and rule numbers. A ruling
   matches only if every `applies_when` fact holds and no `answer_changes_if` case does; anything in
   `ask_if_unknown` that the question leaves open is asked first.
   - **An official or reviewed ruling matches:** re-read the card's Oracle text and the cited rules; if their
     hashes are unchanged, answer from it and name it. If they changed, treat it as no match. A matching house
     rule is shown beside the official answer.
   - **Only an unreviewed ruling matches:** work the question out again and compare. Disagreement is reported
     to the user, and both answers stay recorded.
   - **Nothing matches:** go on to step 2.
2. **Read the cards and the rules** (`card.py`, `lookup.py`), plus the format file and, for tournament
   questions, the MTR, IPG or JAR.
3. **Rule.** The ruling first, in one or two sentences. Then the sequence step by step when order matters.
   Then the citations, each with its level. Then the confidence, and what would change the answer (an unknown
   board detail, a level 3 source pending confirmation). A tournament question also says which enforcement
   level (REL) the answer is for, since the IPG and the JAR differ.
4. **Record.** When step 1 found nothing official or reviewed, `judge.py record` creates an unreviewed ruling,
   with every agent field filled in.
   If the user argues the point, `judge.py discuss` keeps the exchange; if the user accepts the ruling,
   `judge.py review` records that.

### 6. Open-source release

- **Its own repository.** Done: smithy-org/bishop-and-barrister, public.
- **Licence.** Done: Apache-2.0 (`LICENSE`), with the Fan Content statement in `NOTICE`.
- **No payment needed.** Free to download, with an optional tip link where $0 is fine. Wizards' Fan Content
  Policy (checked 2026-10-25) bans selling fan content or requiring payment for it, but allows donations,
  sponsorships and Patreon. Scryfall's terms forbid paywalling card data.
- **The Fan Content disclaimer** in the README, in the policy's wording: unofficial Fan Content permitted under
  the Fan Content Policy, not approved or endorsed by Wizards, portions of the materials used are property of
  Wizards of the Coast, © Wizards of the Coast LLC.
- **What ships:** the scripts, SKILL.md and the format files (our own summaries, with sources). Nothing from
  Wizards or Scryfall: each user's copy downloads those.
- **Dependencies:** `git` and `pypdf` always; `boto3` only for the RustFS bucket.

### 7. Trusted sources when nothing local answers

When neither the database nor the skill's own files answer a question, the judge may look further, but only
at sources on an allowlist, `reference/trusted-sources.json`. Each entry gives a domain, its level, what it is
good for, and how to cite it. Checked on 2026-10-25; "Reachable" means a script got the page.

| Source                                                               | Level | Good for                                                                                                                  | Reachable                                                                                       |
| -------------------------------------------------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Scryfall API                                                         | 1     | Oracle text, Wizards' rulings per card, legality                                                                          | Yes                                                                                             |
| Gatherer (gatherer.wizards.com)                                      | 1     | Wizards' own card database and rulings                                                                                    | Yes                                                                                             |
| magic.wizards.com: rules, release notes, announcements               | 1     | The CR; each set's release notes (the fullest official rulings for new cards); rules changes; banned and restricted lists | Yes                                                                                             |
| wpn.wizards.com/en/rules-documents                                   | 2     | MTR, IPG, JAR                                                                                                             | Yes                                                                                             |
| Format sites (Commander on magic.wizards.com; oathbreakermtg.org)    | 2     | That format's rules and banned list                                                                                       | Yes                                                                                             |
| Magic Judges Rules Resources (blogs.magicjudges.org/rules)           | 4     | The rules documents with a link per rule; annotated MTR and IPG; Missed Triggers Guides (newest: 2026-09-25)              | Yes                                                                                             |
| Cranial Insertion (cranial-insertion.com)                            | 4     | Judge-written answers about specific interactions; the newest found is from June 2025, and older ones may be out of date  | Yes                                                                                             |
| Judge Foundry (judgefoundry.org)                                     | 4     | The judge organisation for the US and Canada since Judge Academy closed in 2024; training material                        | Yes                                                                                             |
| Academy Ruins (academyruins.com and its API)                         | —     | Older versions of the CR, MTR and IPG, and what changed between them. A mirror: cite the official document                | Yes                                                                                             |
| Yawgatog (yawgatog.com)                                              | —     | The CR with a link per rule. A mirror: cite the official document                                                         | Yes                                                                                             |
| MTG Wiki (mtg.fandom.com)                                            | —     | Finding out which rules and terms are involved; never cited as a source                                                   | Yes                                                                                             |
| Reddit (r/mtgrules), Stack Exchange                                  | —     | Judges answer there, but the skill cannot read them                                                                       | No: both refuse scripts, and Reddit also blocks Anthropic's crawler                             |
| Judge chat (chat.magicjudges.org; #magicjudges-rules on Libera.Chat) | —     | Live answers from judges                                                                                                  | A person's channel, not a source: suggested to the user when the skill cannot settle a question |

Rules for using them:

- **Check the date.** Every page from the web is checked for its date against the current CR. An answer
  written before a rules change does not count.
- **Keep a copy.** A page that a ruling cites is archived in the object store, so the citation still works if
  the page changes or disappears.
- **Level 4 alone means lower confidence.** A ruling backed only by level 4 sources is at most `likely`, and
  the judge says so.
- **What is not a source:**
  - other AI-written answers, the judge's own included;
  - pages that copy the CR on sites that are not on the list;
  - anything with no author or date.
- **When nothing settles it,** the judge says so, records a `cannot-tell` or `unsure` ruling, and points the user
  to judge chat. A judge's answer brought back to the conversation goes into the deliberation, with who said it
  and when.
- **claude.ai** may block some of these sites. Then the judge works from what it has and says which sources it
  could not reach.

## How we know it works

The measure is a set of rules questions with
known answers, run against the skill:

- **What the questions cover.** Every `question_type`, written the way people ask them, not the way the rules
  phrase them. Some leave a deciding fact out on purpose.
- **Where the answers come from.** Level 1 and 2 sources: official rulings in release notes and Scryfall's
  `wotc` rulings, the CR's own examples, and the IPG for tournament questions.
- **What is scored:**
  - the answer is right;
  - each citation exists and says what the ruling claims;
  - the skill asks when a deciding fact is missing, instead of guessing;
  - it says `cannot-tell` instead of inventing a verdict;
  - a stored ruling is reused only when it really matches, and not when an `answer_changes_if` case applies.
- **The baseline.** The same questions answered by Claude without the skill, to show what the skill adds.

The question set ships with the skill as `evals/`, and is re-run after each CR release and before each release
of the skill.

## Phases

| Phase | Ships                                                                                                                                                                      |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0     | A first `evals/` set, with the baseline taken on today's skill before anything changes                                                                                     |
| 1     | `judge.py` with the git record, the SQLite index and the object store, pre-filled from Scryfall's bulk rulings; the judge procedure; `card.py` prints each ruling's source |
| 2     | `sources.py` with the MTR, IPG and JAR (`pypdf`); `lookup.py --doc`; `recheck` after each update                                                                           |
| 3     | `reference/formats/` split, with per-file source versions                                                                                                                  |
| 4     | Optional sync: a private git remote for the record, a RustFS bucket for the object store (after checking RustFS's release status)                                          |
| 5     | The open-source release: the tip link (licence, disclaimer and repository done)                                                                                            |

Phase 1 comes first, so rulings start piling up while the rest is built.

## Later: challenging rulings in public (an idea, not planned)

The user's idea (2026-10-25): a website where users of the skill submit rulings to be challenged and settled
socially, in an automated, crowd-sourced way. Nothing in this plan builds it. Two things keep it possible:

- **Same shape.** A ruling's shape (piece 3) is the same everywhere, so it could be published as it is.
- **Personal by default.** Submitting would be a separate, explicit step, `judge.py publish <id>`, in which the
  user chooses whether the deliberation goes too and strips anything personal.

How it would work, as the user described it:

- **One database.** Every submitted ruling and challenge goes to one shared database.
- **Settling.** A question is settled socially, and the settled ruling is what the site shows.
- **Reopening.** A settled ruling can be challenged again once enough challenges against it pile up. Enough
  means a threshold, for example a number of reviewed rulings from distinct users that disagree with it.
- **Automatic.** The site reopens the question itself when the threshold is met, and the community settles it
  again.

Questions that would need answers first: what counts as a challenge (a vote, or a reviewed ruling with its own
citations); whether challenges citing a new CR release or new Oracle text reopen a ruling at once, without a
threshold; and how one person is kept from meeting the threshold alone.

Constraints it would have to respect:

- **Crowd consensus is level 4.** It can settle questions the official sources leave open, and it can show
  where they are unclear. It can never overrule level 1; a crowd answer against Oracle text or the CR is a
  house rule with many votes.
- **Its most useful output** is probably the list of questions where users' reviewed rulings disagree with
  each other. Those are the gaps worth asking Wizards about.
- **It would be a shared server,** which this plan leaves out of scope. It also brings costs the skill does not
  have: hosting, moderation, abuse, and votes from people who never read the sources.
- **It must stay free under the Fan Content Policy,** with donations or sponsors allowed, and Scryfall's terms
  apply to any card data it shows.

## Questions for the user

None open. The remaining choice, the tip service, is tracked in `docs/ROADMAP.md`.
