<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/bb-lockup-dark-bg.svg">
    <img src="assets/bb-lockup-light-bg.svg" alt="Bishop &amp; Barrister" width="440">
  </picture>
</h1>

<p align="center">
  Magic: The Gathering rules answers from the official documents, with citations, for Claude.
</p>

<p align="center">
  <a href="https://github.com/smithy-org/bishop-and-barrister/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/smithy-org/bishop-and-barrister"></a>
  <a href="https://github.com/smithy-org/bishop-and-barrister/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/smithy-org/bishop-and-barrister/actions/workflows/tests.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="Licence: Apache 2.0" src="https://img.shields.io/badge/licence-Apache%202.0-blue"></a>
  <a href="https://ko-fi.com/pjderouen"><img alt="Tip on Ko-fi" src="https://img.shields.io/badge/Ko--fi-tip-FF5E5B?logo=kofi&amp;logoColor=white"></a>
</p>

Ask Claude a Magic rules question and it answers from memory. Usually that's close, but Magic's rules change
with every set, card text gets errata, and the interactions people ask about are the ones where intuition
fails. Bishop & Barrister makes Claude look the answer up instead: in the current Comprehensive Rules, the
card's Oracle text and the tournament documents, and it shows you the rule numbers so you can check.

> **You:** I have Blood Moon out. Does my opponent's Urborg, Tomb of Yawgmoth still make their lands Swamps?
>
> **Claude:** No. Blood Moon makes Urborg a Mountain, and a land set to a basic land type loses its other
> abilities (305.7), so no land becomes a Swamp. Both effects apply in layer 4 (613.1d), and Urborg's depends
> on Blood Moon's (613.8a), so the order they arrived in doesn't matter. Wizards' Urborg ruling of 2021-03-19
> says the same.

## Contents

- [Why use it](#why-use-it)
- [Features](#features)
- [Requirements](#requirements)
- [Proved, not just tested](#proved-not-just-tested)
- [Installation](#installation)
- [Usage](#usage)
- [How it works](#how-it-works)
- [Future plans](#future-plans)
- [Support](#support)
- [Licence](#licence)
- [Fan Content](#fan-content)

## Why use it

We test it on rules questions with known answers: each is asked once with the skill and once without, and
every answer is graded against the official rules. The share of graded checks passed:

|                                          | Claude on its own | With Bishop & Barrister |
| ---------------------------------------- | ----------------- | ----------------------- |
| All questions (29)                       | 69%               | **98%**                 |
| Cards newer than Claude's training       | 39%               | **100%**                |
| Tournament penalties and fixes           | 52%               | **100%**                |
| Answers citing real rules that fit       | 68%               | **100%**                |

On its own, Claude guessed at new mechanics, gave the Competitive fix for a Friday Night Magic mistake, and
cited rules that say something else. With the skill, each answer names the rule it rests on. Each row is the
latest run of that group of questions; the full results are in [`evals/BASELINE.md`](evals/BASELINE.md).

## Features

- **Cited answers.** Every answer names the rules it rests on (`704.5g`, not "the state-based action rule"),
  so you can check it or show it at the table.
- **Always current.** Oracle text, official rulings and format legality come live from
  [Scryfall](https://scryfall.com), and one request brings the rules documents up to date when Wizards revises
  them, so new sets and mechanics are covered.
- **Tournament-ready.** The Magic Tournament Rules, the Infraction Procedure Guide and Judging at Regular REL,
  with the section and its effective date: "IPG 2.3 (effective September 23, 2024)". It tells Regular REL
  from Competitive, which memory gets wrong.
- **Eleven formats.** Deck rules, starting life, mulligans and matches for Commander, Brawl,
  Oathbreaker, Standard, Pioneer, Modern, Legacy, Vintage, Pauper, Draft and Sealed, each fact with its source.
- **Honest when it's unsettled.** If no official source decides a question, it says so, explains what would
  change the answer, and points you to a judge, instead of guessing confidently.
- **Challenges.** Think an answer is wrong, or want a rule of your own? Argue it before a panel of five
  adversarial judges. Only a case that convinces all five enters your rulings record. See
  [CHALLENGE.md](CHALLENGE.md).
- **Local.** Your rulings record and the downloaded documents stay on your machine. The skill only goes
  online for card data (Scryfall), the rules documents (Wizards) and, for challenges, its program (GitHub).

## Requirements

- Claude Code, or claude.ai with code execution turned on.
- Python 3.10 or later, and git.
- [`pypdf`](https://pypi.org/project/pypdf/) for the three tournament documents (`pip install pypdf`).

## Proved, not just tested

Most AI tools ask you to trust them. Bishop & Barrister never adds an AI's opinion to your rules: the only way
in is a **challenge**, and the rules of that process are written in [Lean 4](https://lean-lang.org), a language
whose compiler checks mathematical proofs, theorem by theorem, that the code keeps its promises. If any proof
breaks, the build fails, so no release can ship without them.

```mermaid
flowchart TD
  A[You state your case] --> B[A clerk writes the brief]
  B --> C[You confirm it]
  C --> D[Five judges attack it, blind to each other]
  D --> E[A script checks every quote against the rules]
  E -->|an attack stands| F[You answer it]
  E -->|nothing stands| G[The judges settle, each with evidence]
  F -->|you revise the case| D
  F -->|you stand by it| G
  G -->|one or two unconvinced| D
  G -->|three or more unconvinced| R[Refused: the official answer stands]
  G -->|all five convinced| O[One judge writes the Opinion of the Court]
  O --> J{All five join it?}
  J -->|yes| I[The rule enters your record]
  J -->|not yet| O
  J -->|not after two revisions| R
```

What is proved, among 23 theorems checked on every build:

- **No unearned rule.** A rule enters your record only if all five judges were convinced with evidence, every
  quote checked out, nothing contradicts the official rules, and all five joined the same written opinion.
- **No peeking.** A judge never sees another judge's work from the round in progress, so they can't simply
  agree with each other.
- **Same record, same result.** Every device reaches the same outcome from the same challenge.
- **Finished is final.** A decided challenge can't be quietly reopened.
- **Nothing gets stuck, nothing gets lost.** Every open challenge says who acts next, and two devices acting at
  once is caught, never silently merged.

The proofs cover the process, not Magic itself: Magic's rules are too large to formalise. Everyday answers rest
on the official documents, cited so you can check them.

## Installation

### Claude Code (recommended)

Install it as a plugin:

```
/plugin install bishop-and-barrister --marketplace https://github.com/smithy-org/bishop-and-barrister.git
```

Or from a terminal:

```bash
claude plugin install bishop-and-barrister --marketplace https://github.com/smithy-org/bishop-and-barrister.git
```

On Claude Code before 2.1.275, add the marketplace first:

```
/plugin marketplace add https://github.com/smithy-org/bishop-and-barrister.git
/plugin install bishop-and-barrister@smithy-org
```

Use the full HTTPS address. The short form, `smithy-org/bishop-and-barrister`, clones over SSH, which fails
with "Could not read from remote repository" unless you have an SSH key set up with GitHub.

Then start a new session. To get updates without asking, turn on auto-update: `/plugin`, Marketplaces,
`smithy-org`, Enable auto-update.

<details>
<summary>From a clone instead</summary>

```bash
git clone https://github.com/smithy-org/bishop-and-barrister ~/.claude/skills/bishop-and-barrister
```

</details>

### claude.ai

1. Download `bishop-and-barrister.zip` from the
   [latest release](https://github.com/smithy-org/bishop-and-barrister/releases/latest), or build it from a
   clone with `python tools/package_skill.py`. Don't use GitHub's "Download ZIP": its folder is named
   `bishop-and-barrister-main`, and claude.ai needs the folder to match the skill's name.
2. Turn on code execution: Settings, Capabilities, "Code execution and file creation". On Team and Enterprise
   plans an owner enables code execution and skills for the organization first.
3. Upload the zip under Skills on the same page.

Not yet tested on claude.ai. The skill needs to reach scryfall.com, media.wizards.com and, for challenges,
github.com. If the sandbox blocks one, the script that needed it says so and the rest keeps working.

### The rules documents

Claude downloads the Comprehensive Rules and the three tournament documents the first time it needs them.
They aren't bundled because they belong to Wizards of the Coast and change several times a year. They're
kept in `~/.claude/bishop-and-barrister/documents/`, so updating the skill keeps them. To fetch them up front,
ask Claude to "update the Bishop & Barrister rules documents", or from a clone:

```bash
python scripts/sources.py update
```

## Usage

Ask a rules question the way you'd ask a judge. The skill loads by itself:

- "Does deathtouch plus trample let me assign 1 damage to the blocker?"
- "Humility and Opalescence are both on the battlefield. What are the creatures' power and toughness?"
- "At Competitive REL, what's the penalty for drawing an extra card?"
- "How many cards does each player draw first in a four-player Commander game?"

For tournament questions, say the Rules Enforcement Level (Regular or Competitive), or Claude will ask.

If an answer comes back without citations, call the skill by name:

```
/bishop-and-barrister:bishop-and-barrister How does Blood Moon interact with Urborg?
```

### Keeping the rules current

Wizards revises the Comprehensive Rules with each set. Ask Claude to "check the Bishop & Barrister rules
documents for updates", or run `python scripts/sources.py update --check`.

### Challenges

To dispute an answer or argue for a rule of your own, tell Claude, for example "I want to challenge that
ruling". A clerk writes up your case; five judges, each looking from a different angle, try to refute it with
the rules; you answer; they vote. A rule enters your record only if all five are convinced, and it can never
override the Comprehensive Rules or Oracle text.

A challenge uses `bab-challenge`, a small program the skill downloads from this repository's releases the
first time, checked against a pinned SHA-256. A challenge costs up to a few million tokens, so Claude tells you
the cost and asks first. Everyday answers don't need any of this. Details: [CHALLENGE.md](CHALLENGE.md).

## How it works

Sources are ranked by authority, and the skill reads them in order:

| Level | Source |
| ----- | ------ |
| 1 | The Comprehensive Rules, Oracle text and Wizards' official rulings |
| 2 | The tournament documents (MTR, IPG, JAR), and rules binding for one format |
| 4 | Judges' and community consensus, and Scryfall's own notes |
| 5 | Rules you introduced by challenge, which never override level 1 |

Forums and AI-written summaries are never sources. The web sources the skill may use are listed in
[`reference/trusted-sources.json`](reference/trusted-sources.json).

Nothing Claude answers is recorded. Your rulings record, in `~/.claude/bishop-and-barrister/`, is a git
repository that starts with the official rulings and grows only through challenges. When a rule it cites
changes, the record flags it.

| Path | What |
| ---- | ---- |
| [`SKILL.md`](SKILL.md) | The skill's instructions for Claude |
| [`CHALLENGE.md`](CHALLENGE.md) | How a challenge runs: the clerk, five judges, rounds and the vote |
| `scripts/card.py` | Oracle text, official rulings and legality, from Scryfall |
| `scripts/lookup.py` | The Comprehensive Rules; with `--doc`, the MTR, IPG or JAR |
| `scripts/sources.py` | Downloads the rules documents and checks for new versions |
| `scripts/judge.py` | The rulings record: search, show, recheck |
| `scripts/challenge.py` | Challenges, the only way a rule enters the record |
| `scripts/paths.py` | Where the skill keeps your data |
| `challenge/` | The challenge state machine in Lean 4, with its proofs, built to `bab-challenge` |
| `reference/formats/` | One file per format, with a source for every fact |

## Future plans

Planned for the future, depending on interest:

- **Cloud upload:** keep your rulings record backed up and in step across your devices.
- **A social rules platform:** share rulings and challenges with other players and settle them together.

If either would help you, say so in an [issue](https://github.com/smithy-org/bishop-and-barrister/issues).

## Support

Bishop & Barrister is free and always will be. If it settles an argument at your table and you'd like to say
thanks, you can leave a tip of any amount on [Ko-fi](https://ko-fi.com/pjderouen). It's entirely optional
and unlocks nothing.

Bugs and wrong answers are welcome as [issues](https://github.com/smithy-org/bishop-and-barrister/issues).

## Licence

[Apache License 2.0](LICENSE). Redistributions must keep the [NOTICE](NOTICE), which carries the Fan Content
statement below. The licence covers this project's own code and text, not Wizards of the Coast's materials or
Scryfall's data.

## Fan Content

Bishop & Barrister is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by
Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.

Card data and rulings come from [Scryfall](https://scryfall.com), which is not affiliated with this project.
