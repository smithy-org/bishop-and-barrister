# challenge/: the Lean core of a challenge

The challenge state machine described in [CHALLENGE.md](../plugin/skills/bishop-and-barrister/CHALLENGE.md), written in Lean 4 so its guarantees
are proved rather than only tested. It builds to one binary, `bab-challenge`, which the skill's `scripts/challenge.py` runs.
Users don't need Lean: the binary is downloaded from the release, checked against the SHA-256 in
`plugin/skills/bishop-and-barrister/binaries.json`.

## What is here

| File | What it holds |
| --- | --- |
| `Challenge/Types.lean` | Cases, derivations, refutations, reports, answers, votes, opinions and responses, events |
| `Challenge/Check.lean` | The structural checks: premises point to a fact or an earlier step, every step quotes a pinned source or is labelled an assumption, a refutation attacks a step that exists |
| `Challenge/Machine.lean` | The phases, who owes the next action, and `step`, the transition table |
| `Challenge/Chain.lean` | The hash chain, fork detection, `replay`, and `view`: what each judge may see |
| `Challenge/Rule.lean` | The rule state machine (`current`, `stale`, `reopened`, `superseded`, `retired`) |
| `Challenge/Theorems.lean` | The six guarantees, proved |
| `Challenge/Parse.lean`, `Challenge/Api.lean`, `Main.lean` | Reading event files, and the JSON interface |
| `Audit.lean` | Fails the build if a theorem is missing or uses `sorry` |
| `Tests.lean` | Example sequences for every path, and refused events |

## The guarantees

1. **No unearned rule.** `Phase.introduced` holds an `Earned`: a `Settled` (five convinced positions, each with
   evidence; a passing verifier report with no level 1 conflict and nothing standing; a case whose every step is
   sourced or a stipulation; and an independent panel) plus an Opinion of the Court that all five judges joined.
   A stipulation, the rule's own new content, is only allowed in a case that fills a gap
   (`stipulations_only_in_gaps`). `introduced_has_opinion` proves the opinion: its author was one of the convinced
   judges, its holding is the case's rule, its steps are sourced or stipulations, and each of the five judges
   joined it as written. A concurrence is not a join. After the judges settle, the phases are `drafting` (the
   lowest-numbered convinced judge writes it) and `joining` (all five join, concur or dissent; up to two
   revisions).
2. **Determinism.** `replay` gives the same result for any order of the same events (`determinism`).
3. **Terminal states are final.** No event leaves `introduced`, `withdrawn` or `house-rule`; `refuted` leaves
   only for `house-rule`, at the user's request.
4. **Blindness.** `view k` never shows judge *k* another judge's filing or vote from the phase in progress.
5. **Progress.** Every state that isn't settled names who acts next (`progress`).
6. **Forks are caught.** Two different events with the same predecessor make `replay` report a fork
   (`forks_caught`).

Whether a quoted excerpt matches the rule's text is a data check made in Python before the verifier's report;
the Comprehensive Rules aren't formalised here.

## The command line

JSON on stdin, one JSON object on stdout. Each event file is passed as its exact text, because its hash is the
SHA-256 of that text.

```sh
echo '{"events": ["{...}", "{...}"]}' | bab-challenge replay         # the state, the round, who acts next
echo '{"events": [...], "proposed": "{...}"}' | bab-challenge check  # accepted, or the reasons it's refused
echo '{"events": [...]}' | bab-challenge view --judge 3              # the event files judge 3 may see
echo '{"state": "current", "event": "source-changed"}' | bab-challenge rule
```

An event file:

```json
{"v": 1, "seq": 0, "prev": null, "actor": "user", "device": "laptop", "time": "2026-10-26T10:00:00Z",
 "type": "open", "statement": "Who chooses who plays first in game 2 of a three-player match?",
 "panel": "independent"}
```

The types are `open`, `brief`, `edit`, `confirm`, `file`, `report`, `answer`, `vote`, `opinion`, `respond`,
`withdraw`, `house-rule` and `reopen`; `Challenge/Parse.lean` lists each one's fields. `replay` also reports
`convened` (the judges who attack in the round: all five in round 1, then only those whose refutation a revision
answered), `revision` and `responded` (the opinion's revision and who has answered the draft).

## Building

Install Lean with [elan](https://github.com/leanprover/elan); the toolchain is pinned in `lean-toolchain`.

```sh
cd challenge
lake build   # compiles, and checks every proof
lake test    # the example sequences
```

A release tag (`v*`) builds `bab-challenge` for Linux x64 and arm64, macOS x64 and arm64, and Windows x64, and
attaches them to the release with their SHA-256s.
