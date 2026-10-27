# 029 — Challenges: the only way a rule enters the record

**Status:** built (phases 1 to 6, merged 2026-10-26 to 27). **Revised 2026-10-27: the panel is five judges, not
seven**, at the maintainer's request, to cut the cost of a challenge (each judge is an agent, and starting any agent
costs about 60k tokens before it does any work). The five lenses are the original seven merged by their overlap, in
the table below. Where this document still says seven, read five.

**Revised 2026-10-27: the judges close the case by consensus** (decided with the maintainer after the first eval run,
`evals/BASELINE.md`). What changed, and why:

- **A judge is settled** when its latest position is on the final version of the case and carries evidence (pinned
  sources, checked by the core and the verifier) and reasoning. Concessions and votes needed neither before.
- **Introduction** needs all five convinced. **Refusal** needs three not convinced, and ends `refuted` if a
  verified refutation stands (or the case contradicts a level 1 source) and `open` if the case is merely
  unproven. One or two not convinced is no consensus: another round with the dissent visible, up to three rounds,
  then `open`.
- **Stipulations.** A gap rule is new content, which no source can support, so a case that fills a gap may mark
  steps `stipulation`: the judges attack them on their merits and vote on accepting them. Before, no gap rule could
  ever be introduced. They are refused in any case that challenges an official answer.
- **Nothing closes a case for the judges.** An answer that revises the case is attacked again; one that doesn't
  goes to the judges to settle, with no re-attack of an unchanged case. Five concessions on the unchanged case are
  the five settled positions, so no separate vote runs. The round limit is three.
- A case that ends `open` can also be kept as a house rule, as a `refuted` one can.

**Revised 2026-10-27 (second note): the Opinion of the Court, and targeted rounds** (decided with the maintainer,
PR B). What changed, and why:

- **A rule is introduced by an opinion that all five judges join**, not by the settling vote alone. Once all five are
  settled and convinced (and every guard holds), the case is `drafting`: the lowest-numbered convinced judge writes
  the opinion in the proof standard: the **holding** (the case's rule, word for word), the **reasoning** (sourced
  steps, no assumption) and the **stipulations** (exactly the case's, none added, none left out). Then the case is
  `joining`: each of the five answers the draft blind to the others with exactly one of **join** (adopt it as
  written), **concur** (the rule is right, for other reasons, which the judge states with evidence) or **dissent**
  (not convinced, with evidence). Every answer is a position, so it needs reasoning and evidence.
- **Only five joins introduce the rule.** A concurrence is not a join and is never unanimity. A concurrence or a
  dissent (fewer than three dissents) sends the draft back to its author, who sees every response and revises; after
  two revisions without five joins the case stays `open`. Three or more dissents refuse the case (`open`: the case
  has no refutation standing, so it is unproven). The opinion, who joined, and every concurrence and dissent are
  stored in `rules/challenge-<id>.json` and shown by `judge.py`.
- **A refused case needs no agents to be written up.** For `refuted` and `open` cases, `challenge.py` assembles a
  short per curiam record from each judge's last position (reasons and evidence) and stores it with the challenge,
  in `challenges/<id>/record/per-curiam.json` (outside the event chain, derived from it).
- **Targeted rounds.** After the first full round, an attack round after a revision convenes only the judges whose
  refutation was answered by that revision (a `fix` reply); the others' concessions stand for now. If the revision
  answered no one's refutation, nobody is convened and the judges settle. The **soundness rule**: every judge's
  last position must be on the final version of the case. When no refutation stands, a judge whose last look
  (a concession) was at an earlier version, or was a refutation, settles again with a vote; a concession on the
  final, unchanged version is already that judge's settled position (it exists for the all-concede case, and now
  holds for any judge). Blindness is unchanged: a judge never sees another's work from the phase in progress.
- **Kept:** the five-judge panel, unanimity to introduce, three of five to refuse, stipulations only in gaps,
  evidence and reasoning on every position, the round limit of three, house rules from refuted or open cases, the
  hash chain and fork detection.
- **Proofs.** `Earned` is now a `Settled` (the old guarantee) plus an opinion and five joins. `introduced_has_opinion`
  proves that an introduced rule has an opinion whose author was one of the convinced judges, whose holding is the
  case's rule and whose steps are sourced or stipulations, and that each of the five judges (distinct, as there are
  five) joined it. The other theorems are unchanged in statement.

**Decided with the user (2026-10-26):**

- **Nothing the skill answers enters the database.** Established rules are only what official sources say:
  Oracle text, the Comprehensive Rules, Wizards' rulings, and the MTR, IPG and JAR. `judge.py record` and
  `review` are retired.
- **The only way in is a challenge**: the user puts forward a case for a rule. Challenging is a **separate
  part of the skill** (`CHALLENGE.md`, `challenge/`, `scripts/challenge.py`), apart from everyday answering.
- **A panel of five agents judges it.** They use the skill itself (`lookup.py`, `card.py`, `judge.py search`,
  the tournament documents) to verify the case and **argue fervently against it, with evidence**. The user
  argues back.
- **If every agent is convinced, the new rule is introduced**, in a file named after its challenge
  (`rules/challenge-<id>.json`) so it can always be traced.
- **Challenges are a state machine.** The rest of the skill was reviewed for statefulness and stays mostly
  stateless (below).
- **The challenge core is written in a functional language: Lean 4**, so its guarantees are proved, not only
  tested.

**Assumed, not yet confirmed by the user:** the panel convenes only when the user challenges (everyday questions
stay one agent); in Claude Code each judge is a subagent, and on claude.ai one agent plays each judge but cannot
introduce a rule.

**Related:** [plan 028](028-rules-library-and-judge.md) (the library and judge; its "Later" section's public
challenge website would build on this).

## What the evidence says about AI reasoning accuracy (why the panel works this way)

- **Identical agents debating, then voting, do no better than majority voting** at the same cost, and they
  conform: in one 2026 study agents adopted the majority answer up to 85% of the time, sometimes abandoning a
  correct one. So agreement among agents proves little.
- **What helps:** each agent reaching a view **independently before seeing the others**; **different lenses**
  rather than identical agents; a correct minority being able to win; adversarial argument that a judge
  weighs. And debate helps a human judge more than a weaker model, which fits the user arguing in person.
- **Magic is unusually checkable.** The CR is close to an algorithm and Oracle text is exact, so an argument can
  be written as a **derivation** whose every step quotes a rule, and a script can check each quote. That turns
  "is this argument right?" partly into "does every step check?", which is where accuracy comes from.

## The burden of proof, and the proof standard

The challenger carries the burden. The established answer stands unless the case survives every attack.

**The case** (written by the user, or with the panel's clerk from what the user says) and **every refutation**
use one shape, which `challenge.py` validates:

- **Facts**: numbered (F1, F2...). Unknown facts are listed as open questions, never assumed.
- **Proposed rule**: the rule the user wants introduced, with `applies_when` conditions, and the established
  answer it challenges (an official ruling, a CR or document section, or Oracle text), or "none: a gap".
- **Derivation**: numbered steps; each = premises (facts or earlier steps) + one quoted source (pinned by hash,
  as `judge.py record` pins citations today) + the conclusion it licenses. A step with no source is an
  assumption, labelled as one.
- **Precedence** when sources conflict, from the CR: card text over rules (101.1); "can't" over "can" (101.2);
  the specific over the general; plan 028's levels (1 over 2 over 4).

**A refutation must attack a specific step** and name its ground: the cited rule doesn't apply (a condition
isn't met), a higher-precedence source overrides it, the quote is misread, a fact is wrong or missing, or a
**counterexample**: the proposed rule gives a wrong answer in another game situation that official sources do
settle.

**What a challenge can never do:** contradict level 1 text directly. A case whose rule conflicts with Oracle
text, the CR or a Wizards ruling on the same facts is refuted by precedence. If the user still wants it, it can
be stored only as a **house rule**, marked as departing from the official rules, never as a rule.

## The panel

| Role | Lens | Job |
| --- | --- | --- |
| **Clerk** | The case as stated | Puts the case in the proof standard, lists missing facts, asks the user before the panel runs |
| **Five adversarial judges** | 1. the CR's text; 2. cards and their rulings: Oracle text and wording, and Wizards' rulings and precedent from analogous cards; 3. game-state simulation (stack, priority, state-based actions, step by step); 4. counterexamples and logic: other situations where the proposed rule fails, and hidden assumptions, circular steps and gaps between steps; 5. the tournament documents and formats | Each, **blind to the others in the first round**, uses the skill to try to refute the case and writes a refutation in the proof standard, or concedes a step it cannot refute |
| **Verifier** (a script, `challenge.py verify`) | | Checks every citation in the case and every refutation: the source exists, the quote matches the pinned text, the Oracle text is current, every premise refers to a real fact or step. A failed step cannot be relied on by anyone |

**The rounds:**

1. **Clerk's brief** → the user confirms or corrects the facts and the proposed rule.
2. **Round 1, blind:** the five judges attack the case independently.
3. **Verifier** checks the case and all five refutations.
4. **The user answers** the verified refutations, step by step: concede, fix the case, or rebut (in the same
   shape, with sources).
5. **Next round:** each judge sees the user's answers and the other judges' verified refutations, and attacks
   again or concedes. Rounds continue until no verified refutation stands unanswered, or the user withdraws,
   with a cap (say 4 rounds) after which it stays open.
6. **The verdict:** each judge votes **privately and with reasons**: convinced (states which step settled it
   for them) or not (names the verified refutation still standing). Votes are cast blind to each other's
   votes, so they can't conform.

**The rule is introduced only if** every judge is convinced, the verifier passes the final case with no
unsupported step, and the case doesn't contradict level 1 text. Anything less: the established answer stands,
and the challenge is stored as **refuted** (with the refutation that defeated it) or **open** (unanswered, a
gap the user can return to). Unanimity is deliberate: one judge with a verified refutation standing is exactly
the correct minority the research says must be able to win. (The threshold is a setting if the user wants a
supermajority later.)

## Does the skill need state? A review, part by part

State only belongs where something lasts across turns, sessions or devices and its next legal step depends on
where it is. Part by part:

| Part | Lasts beyond one command? | Verdict |
| --- | --- | --- |
| **Everyday answering** (search, card, lookup, answer) | No: each question reads the record and documents, answers, and is done | **Stateless, and stays so.** No conversation memory is stored: it keeps answers fast and private, and nothing the skill says becomes a rule |
| **Documents** (`sources.py`) | Yes, but only "which version is installed" | **Plain data** (`sources.json`, `version.json`). Install-or-not has no lifecycle worth a machine |
| **Sync** (`judge.py sync`, auto-sync) | Yes, per device | **Operational status, not a machine.** Today it's scattered (`pulled_at`, `uploaded_head`, `notice`). Make it one explicit field: `ok`, `paused: unreachable`, `paused: public bucket`, `blocked: conflict` (blocked stops auto-pull from retrying a known conflict until it's settled). Still derived from facts, so it can't drift |
| **Introduced rules** | Yes, for years | **A small state machine** (below): a rule can go stale when its sources change and must win again |
| **Challenges** | Yes: rounds span sessions, days and devices, with the user and five judges acting in turn | **A full state machine** (below). This is where statefulness earns its keep: a new session must know exactly what happens next, and nothing may skip verification or voting |

So the skill stays mostly stateless; the two entities with a life of their own get explicit state machines,
enforced by `challenge.py` rather than by the agent remembering what to do.

## The challenge state machine

Every challenge is in exactly one state. `challenge.py status <id>` prints the state and **the next action and
who owes it** (the user, judge *k*, the verifier, or the panel), so any session, on any device, picks it up.
`challenge.py` refuses any transition the table doesn't allow.

| State | Who acts | Leaves by | To |
| --- | --- | --- | --- |
| `draft` | User (with the clerk) | Clerk writes the brief | `briefed` |
| `briefed` | User | Confirms facts and the proposed rule / edits them | `attack(n=1)` / `briefed` |
| `attack(n)` | The convened judges (all five in round 1), blind; each judge's refutation or concession is a separate event | All convened judges filed | `verify(n)` |
| `verify(n)` | Verifier (script) | Report filed | `answer(n)`, or, if no verified refutation stands, `voting` (or `drafting` when every judge is already settled and convinced) |
| `answer(n)` | User | Answers each verified refutation (concede, fix the case, rebut) / withdraws | `verify-answers(n)` / `withdrawn` |
| `verify-answers(n)` | Verifier | Report filed | `attack(n+1)` if n < cap and the revision answered a refutation, convening only those judges; else `voting` |
| `voting` | The judges not yet settled on the final case, blind to each other's votes | All have voted | `drafting` if every guard holds and all five are convinced; `attack(n+1)` with one or two not convinced; else `refuted` or `open` |
| `drafting` | The lowest-numbered convinced judge | Writes the opinion | `joining` |
| `joining` | The five judges, blind to each other's answers | All five answered | `introduced` on five joins; `drafting` (a revision, at most two) on a concurrence or a dissent; `open` on three dissents or after two revisions |
| `introduced` | | Terminal for the challenge; creates a rule (below) | |
| `refuted` | | Terminal. Optionally the user asks to keep it as a house rule | `house-rule` |
| `open` | User | Returns with new facts or sources | `briefed` |
| `withdrawn`, `house-rule` | | Terminal | |

**Guards** (checked by `challenge.py`, not the agent):
- `voting` → `introduced` only if all five votes are "convinced", the final case passes the verifier with no
  unsupported step, it contradicts no level 1 source, and the panel was independent (not the claude.ai
  single-agent fallback).
- A judge can't see other judges' round-*n* refutations or votes until all five have filed (the event files
  are hidden from the prompt until the state advances).
- Every transition records who made it: a judge, the verifier, or the user in their own words.

**Every challenge has a traceable id:** `challenge-<YYYYMMDD>-<12 hex>`, where the hex is the start of the
SHA-256 of its opening event (the user's case as first stated, with the device and time). The id is:
- **unique without coordination:** any device mints it offline, and two devices can't collide in practice;
- **verifiable:** anyone holding the files can recompute it from the opening event, so an id can't be attached
  to a different case;
- **sortable by date**, and the same everywhere it appears: file names, commit messages, the index, the bucket,
  and any future public site.

**Storage is event-sourced**, which fits git and sync:
- One file per event: `challenges/challenge-<id>/<seq>-<actor>-<device>.json` (brief, refutation, verifier
  report, user answer, vote, transition). Never edited, only added.
- **The events form a hash chain:** each event records the SHA-256 of the one before it, so a removed, edited
  or reordered event breaks the chain, and `bab-challenge replay` refuses a broken chain.
- The state is computed by replaying the events through the transition table, so it can't disagree with them.
- **No sync conflicts by construction:** two devices add different files rather than editing one. If two devices
  both act in the same state (both answered round 2), the replay finds a **fork**; the challenge pauses in
  `fork` until the user picks one. Nothing is merged by guesswork.
- Git keeps the history; the index stores each challenge's current state for search.

## The rule state machine

| State | Meaning | Leaves by | To |
| --- | --- | --- | --- |
| `current` | Introduced by a challenge and still backed by its sources | `recheck` finds a cited source or Oracle text changed / a later challenge introduces a rule that replaces it | `stale` / `superseded` |
| `stale` | A source it relied on changed | A new challenge (pre-filled with the old case) opens automatically against the new text | `reopened` |
| `reopened` | Its challenge is running again; search shows the rule flagged as unconfirmed | The challenge ends `introduced` / `refuted` | `current` / `retired` |
| `superseded`, `retired` | No longer applies; kept in history with the reason | | |

## The database (record) changes

- **`judge.py record` and `review` are retired.** Everyday answers are not stored. Existing reviewed or
  unreviewed rulings are migrated: reviewed ones become **open challenges** carrying their deliberation (they
  must pass a panel to become rules); house rules stay house rules. The user's real record has none today.
- **New: `challenges/challenge-<id>/`**, one event file per step (see the state machine), replayed for the
  state. Terminal outcomes: `introduced`, `refuted`, `open`, `withdrawn`, `house-rule`.
- **A successful challenge writes its rule to `rules/challenge-<id>.json`**, named with the challenge's own id,
  so every rule traces to the challenge that introduced it, wherever the file travels (the local record, the
  synced bucket, an upload). The rule file carries its provenance:
  - the challenge id, and the hash of the final `introduced` event, which pins it to the exact verified history;
  - the five judges' votes and the verifier's final report hash;
  - the devices and dates of opening and introduction;
  - the sources it relies on, pinned by hash.
  `challenge.py trace challenge-<id>` checks a rule file against its challenge: the id recomputes from the
  opening event, the chain is unbroken, and the final hash matches.
- A **house rule** from a refuted challenge is likewise `rules/house-challenge-<id>.json`, so it can never be
  mistaken for an introduced rule.
- **An introduced rule** is a new kind, `rule`, at level 5 ("the user's rules, introduced by challenge"),
  ranked after official level 1 rulings, linked to its challenge. It carries `applies_when`, the full verified
  derivation, and the pinned sources.
- **It gets rechecked:** `recheck` flags it when any cited source changes, and it reopens as a challenge
  (needs to win again against the new text).
- **It travels with sync** like the rest of the record, with commit trailers `Drafted-by: panel` and
  `Decided-by: panel` plus the user's own words on opening and closing.

## A separate part of the skill

- **`CHALLENGE.md`** at the skill's root: the challenge procedure, the proof standard, the five judges'
  prompts, how to run rounds. SKILL.md gets only a short pointer: "if the user wants to challenge a rule or
  introduce a new one, read `CHALLENGE.md`". Everyday answering is unchanged and stays cheap.
- **`challenge/`**: the Lean 4 core (see "Implementation language"): the challenge and rule state machines,
  replay, guards, the structural derivation checks, and their proofs, built to the `bab-challenge` binary.
- **`scripts/challenge.py`**: `open`, `brief`, `confirm`, `add` (a refutation, answer or vote, validated and
  pinned), `verify`, `status` (state + next action + who owes it), `show`, `list`, `withdraw`. Every command
  is a proposed event that `bab-challenge check` accepts or refuses. It reuses `judge.py`'s `validate()`/`fill_sources()` citation
  checks and pinning, `append_deliberation`, `commit()`, `rebuild_index()`, and the sync hooks (`auto_sync`).
- **Runtime:** in Claude Code, each judge is a subagent (Agent tool), launched in parallel for the blind round.
  On claude.ai, which can't launch subagents, one agent plays each judge in turn and the challenge is marked
  "single-agent panel", which can open and refute but **cannot introduce a rule** (it isn't independent).

## Implementation language: Lean 4 for the challenge core (decided 2026-10-26)

The challenge core is written in a functional language. **Lean 4** is the choice: it is a functional
programming language and a proof assistant in one.

- **Illegal states can't be written down.** States and events are inductive types; the transition function is
  total, and the compiler rejects a state × event case left unhandled.
- **The guarantees are proved, not only tested.** Theorems in the code, checked on every build:
  1. **No unearned rule:** `replay events = introduced` implies all five judges voted convinced, the final
     verifier report passed, no level 1 conflict was found, and the panel was independent.
  2. **Determinism:** replay is a pure function of the events, so every device computes the same state.
  3. **Terminal states are final:** no event leaves `introduced`, `refuted`, `withdrawn` or `house-rule`.
  4. **Blindness:** what judge *k* is shown in `attack(n)` or `voting` contains no other judge's round-*n*
     filing or vote.
  5. **Progress:** every reachable non-terminal state names who acts next; nothing gets stuck.
  6. **Forks are caught:** two filings for the same slot from different devices yield `fork`, never a silent
     choice.
- **Derivations are checked structurally in Lean:** every premise points to a fact or an earlier step (no
  cycles, no dangling references), every step has a pinned source or is labelled an assumption, and a
  refutation targets a step that exists, with a valid ground. Whether a *quote* matches the rule text stays a
  data check (below), because the CR isn't formalised; formalising it is out of scope (Magic's rules are rich
  enough to be Turing complete).

**The boundary between Lean and Python:**

| Lean (`challenge/`, a Lake project, built to one binary `bab-challenge`) | Python (`scripts/challenge.py`, a thin wrapper) |
| --- | --- |
| Types for events, states, cases, derivations, refutations, votes | Reading and writing the event files in the record |
| `replay`, the transition table, the guards, fork detection, what each judge may see | Citation checks and pinning, reusing `judge.py`'s `validate()` / `fill_sources()`, `lookup.py`, `card.py` |
| Structural checks of derivations and refutations | Git commits, the index, `recheck`, sync (unchanged) |
| The theorems above | Finding, downloading and verifying the binary |

The binary speaks JSON on stdin/stdout: `bab-challenge replay` (events → state, next action, who owes it),
`bab-challenge check` (a proposed event → accepted or the reasons it's refused), and
`bab-challenge view --judge k` (the events judge *k* may see). Lean 4's core has JSON (`Lean.Data.Json`), so
the binary needs no extra libraries.

**Distribution**, so users don't need a Lean toolchain:
- GitHub Actions builds `bab-challenge` for Linux x64 and arm64, macOS x64 and arm64, and Windows x64 on each
  release tag, and attaches them to the release. The build fails if any theorem fails.
- The repository pins each binary's SHA-256 in `challenge/binaries.json`. On first use `challenge.py`
  downloads the binary for the platform from the matching release and refuses it unless the hash matches.
- No binary for the platform, or no network the first time: challenges are unavailable, with a message saying
  so. Everyday answering is unaffected. There is no Python fallback, so the state machine has one
  implementation and one set of proofs.
- claude.ai: works only if its sandbox can download the Linux binary from GitHub; part of the existing
  claude.ai check.

**Development:** contributors install Lean with `elan`; `lake build` compiles and checks the proofs, and
`lake test` runs example-based tests. A Lean toolchain version is pinned in `lean-toolchain`.

## Phases (one PR each)

1. **Plan 029 document** in the repo, for review.
2. **The Lean core:** the `challenge/` Lake project (types, transition table, `replay`, guards, fork
   detection, what each judge may see, structural derivation checks) with the six theorems proved; the
   `bab-challenge` CLI (`replay`, `check`, `view`); GitHub Actions building the five platform binaries on a
   release tag, with the build failing on any unproved theorem.
3. **The Python wrapper:** `challenge.py` with the event store, binary download and SHA-256 check,
   `open/brief/confirm/add/verify/status`, citation pinning through `judge.py`; tests (a forged quote, a step
   with no source, a premise pointing nowhere, a fork from two devices after a sync). Sync status made explicit
   in `judge.py` (`ok` / `paused` / `blocked: conflict`).
4. **`CHALLENGE.md` and the panel:** the clerk and five judge prompts, rounds, blind voting, `vote/close`, the
   unanimity rule, the single-agent marking.
5. **The record:** retire `record`/`review` with migration; the `rule` kind in search, index, recheck (reopen
   on change) and sync; SKILL.md pointer.
6. **Challenge evals**, then tuning the judges' prompts against them.

## Verification

- **Proofs (Lean):** `lake build` checks the six theorems (no unearned rule, determinism, final terminal
  states, blindness, progress, forks caught); CI fails if any is missing or `sorry`'d.
- **Lean tests** (`lake test`): example event sequences for every path through both machines, and refused
  events with their reasons.
- **Python tests:** the binary's JSON interface; download refused on a wrong SHA-256; a fork from two devices
  acting in the same state, after a sync through the S3 stand-in; citation pinning; recheck moving a rule
  `current` → `stale` → `reopened`; migration; the id recomputes from the opening event; `trace` passes for an
  introduced rule and fails when any event is edited, removed or reordered, or the rule file is swapped onto
  another challenge; blindness end to end (a judge's prompt, built from
  `bab-challenge view`, never contains another judge's round-*n* filing).
- **Resumability:** stop a challenge in each non-terminal state, start a new session, and check that
  `challenge.py status` alone is enough for it to take the right next step.
- **A challenge eval set** (about 10 cases, known outcomes), each a case a user puts forward:
  - should be **refuted** by level 1 text: "Blood Moon turns Urborg's Swamps off but Urborg still makes my lands
    Swamps";
  - should be **refuted by counterexample**: an overgeneralised rule that breaks on another card;
  - a real **gap** that should be **introduced**: e.g. who chooses the first player in game 2 of a three-player
    match (no official rule; plan 028's formats research);
  - **Magar and aftermath**: both readings derivable, so it should stay **open**;
  - a **house rule** the user wants despite official text.
  Graded on: the right outcome; every judge's refutation verified; the deciding step named; and against a
  single agent and three independent answers with a majority vote, at measured tokens, so the panel earns its
  cost.
- **End-to-end** in Claude Code: two real challenges argued with the user before phase 3 merges.

## Sources

- [The Cost of Consensus (2026)](https://arxiv.org/pdf/2605.00914), [Minority Sentinel (2026)](https://arxiv.org/pdf/2606.29270),
  [Free-MAD](https://arxiv.org/html/2509.11035v1), [LLMs Cannot Self-Correct Reasoning Yet](https://arxiv.org/pdf/2310.01798)
- [Debating with More Persuasive LLMs Leads to More Truthful Answers](https://www.emergentmind.com/videos/debate-enhances-llm-truthfulness-e6e931db),
  [Humans correct judgements through debate, weaker AI models not (NeurIPS 2026)](https://neurips.cc/virtual/2026/poster/154000),
  [Quanta on debate](https://www.quantamagazine.org/debate-may-help-ai-models-converge-on-truth-20241108/)
