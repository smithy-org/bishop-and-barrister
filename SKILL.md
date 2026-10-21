---
name: mtg-rules
description: Answer Magic&#58; the Gathering rules questions from the official Comprehensive Rules and current Oracle card text instead of memory. Use this skill whenever the user asks how cards interact, whether a play is legal, what happens when two effects conflict, how the stack/priority/layers/state-based actions resolve, or anything involving a specific card's wording — even for questions that seem simple or that you think you already know the answer to. Also use it when the user quotes card text, describes a board state, asks "does X work with Y", or mentions rules numbers, judge calls, or format legality. Use it too for format rules (deck size, starting life, mulligans, who plays first, best-of-one or best-of-three matches, sideboarding between games, multiplayer) for any format the app offers.
---

# Magic: the Gathering rules

Magic's rules are unusually adversarial to recall-based answers. Card text is
errata'd, rules are renumbered between sets, and the interactions people ask
about are precisely the ones where intuition fails. So the working assumption
here is that memory is wrong until checked against the two authoritative
sources: the Comprehensive Rules and Oracle text.

## The three scripts

| Script                    | Use it for                                            |
| ------------------------- | ----------------------------------------------------- |
| `scripts/card.py`         | Current Oracle text and official rulings for any card |
| `scripts/lookup.py`       | Pulling specific rules out of the Comprehensive Rules |
| `scripts/update_rules.py` | Downloading/refreshing the rules file                 |

**Never read `reference/MagicCompRules.txt` directly.** It is roughly a
megabyte — reading it will blow out the context window for no benefit. Always
go through `lookup.py`, which returns only the passages you asked for.

If the rules file is missing, `lookup.py` will say so; run
`python scripts/update_rules.py` to fetch it.

## Answering a rules question

**1. Get the actual card text.** Any time a specific card is named, look it up
before reasoning about it:

```bash
python scripts/card.py "Humility" "Opalescence"
```

Printed text and remembered text are both unreliable. Oracle text is what the
game actually uses. Add `--rulings` when a card is famously fiddly — Scryfall's
official rulings often answer the exact question directly.

**2. Find the governing rules.** Search by concept, then narrow to specific
rules:

```bash
python scripts/lookup.py search "deathtouch"
python scripts/lookup.py rule 702.2      # the whole deathtouch section
python scripts/lookup.py rule 704.5g     # one specific state-based action
python scripts/lookup.py glossary "Deathtouch"
```

`search` scans rule text for a term and returns short snippets around each
match — some rules run to a full paragraph, so read the snippets to find the
relevant rule number, then use `rule` to pull its complete text. `rule` accepts
either a full rule number (`509.1a`) or a bare section (`509`); `glossary`
gives the formal definition of a keyword or game term; `toc` lists all 147
sections if you need to orient.

**3. Answer with rule numbers cited.** State the outcome plainly first, then
cite the rules that produce it — `704.5g`, not "the state-based action rule".
Citations let the user verify you, and in a real judge call they're the thing
that settles the argument.

**4. Walk the sequence when order matters.** For anything involving a
resolution order, step through it: what's put on the stack, what triggers,
what state-based actions are checked and when. Compressed answers hide exactly
the step where the surprise lives.

## Where intuition usually breaks

These are the areas where a confident-sounding wrong answer is most likely.
When a question touches one, look the rules up rather than reasoning from
first principles:

- **Layers** (613) — continuous effects apply in a fixed order, not in
  timestamp order alone. Power/toughness has its own sublayer stack.
  Characteristic-defining abilities apply in layer 7a and ignore timestamps.
- **State-based actions** (704) — checked whenever a player would receive
  priority, not immediately when the condition arises, and never during
  resolution of a spell or ability.
- **Replacement effects** (614) — never use the stack and never trigger. If
  several apply, the affected object's controller chooses the order.
- **Triggered vs. activated vs. static** (602, 603, 604) — the distinction
  drives almost everything downstream about timing and responses.
- **Priority and the stack** (117, 405) — nothing resolves while a player
  still holds priority, and each object resolves individually.
- **Copiable values** (707) — copy effects see through most other effects,
  which is why layers and copying interact so badly.
- **Targeting and legality** (608.2b) — a spell whose targets have all become
  illegal doesn't resolve at all.
- **Timestamps and dependency** (613.7, 613.8) — dependency is checked before
  timestamps, and this ordering surprises nearly everyone.

## Formats and matches

`reference/formats.md` covers each format this app offers (Commander, Brawl,
Oathbreaker, Standard, Pioneer, Modern, Legacy, Vintage, Pauper, Draft and
Sealed): deck construction, starting life, mulligans, the first draw, and
matches of several games — who starts later games, sideboarding, what resets
between games, and what no official rule covers at three or four players. It
is short; read it directly. Every CR number in it was checked with `lookup.py`
when it was written: re-check the ones you rely on, since rules get renumbered,
and cite the Magic Tournament Rules sections and other sources it names for
what the CR doesn't cover. Oathbreaker is not in the CR at all; its rules come
from oathbreakermtg.org, whose 906.x numbering is its own.

## Scope

The Comprehensive Rules govern gameplay. They are _not_ the tournament rules.
Match structure, the play/draw rule and sideboarding between games are
summarized from the Magic Tournament Rules in `reference/formats.md`. For
anything else there — missed triggers, slow play, deck registration,
penalties, judge procedure — the Magic Tournament Rules and Infraction
Procedure Guide at `wpn.wizards.com` apply, and this skill has no copy of them:
say so rather than guessing.

Format legality is partly in the CR (Commander is section 903, for example)
but current banned and restricted lists are not; those change independently
and should be checked at
`magic.wizards.com/en/banned-restricted-list`. `card.py` reports current
legality per format, which is usually the faster answer.

Un-sets, Alchemy rebalancing, and digital-only cards behave differently from
paper. Note the distinction if a question involves them.

## Keeping the rules current

The Comprehensive Rules are revised with every set release, roughly quarterly,
and are occasionally re-posted with corrections in between.

```bash
python scripts/update_rules.py --check    # has anything changed?
python scripts/update_rules.py            # install the new version
```

Two dates are attached to any given release and they don't match: the filename
carries the date Wizards posted the file, while the document itself states an
effective date, usually a couple of weeks earlier. Neither is a dependable
version key, so the updater compares a hash of the file contents instead. It
uses a cheap size/modification-time probe first and only downloads in full
when that is inconclusive.

`reference/version.json` records both dates and the hash of what is installed.
If it goes missing — say the rules file was copied in by hand — the updater
reconstructs what it needs from the file itself, so checking still works.

If a question involves a mechanic from a very recent set, check for an update
before answering.
