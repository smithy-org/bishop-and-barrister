# mtg-rules-skill

A Claude skill that answers Magic: The Gathering rules questions from the official Comprehensive Rules and
current Oracle card text instead of from memory, and cites the rules it relies on.

## Install

Clone it into your Claude Code skills folder:

```bash
git clone https://github.com/smithy-org/mtg-rules-skill ~/.claude/skills/mtg-rules
```

Then fetch the Comprehensive Rules once. They are not bundled, because they belong to Wizards of the Coast and
change with every set:

```bash
python ~/.claude/skills/mtg-rules/scripts/update_rules.py
```

## What's here

| Path                      | What                                                                  |
| ------------------------- | --------------------------------------------------------------------- |
| `SKILL.md`                | The skill's instructions for Claude                                   |
| `scripts/card.py`         | Oracle text, official rulings and format legality, from Scryfall      |
| `scripts/lookup.py`       | Searches the downloaded Comprehensive Rules                           |
| `scripts/update_rules.py` | Downloads the Comprehensive Rules and checks for new releases         |
| `reference/formats.md`    | Rules for each format the skill covers, with a source for every fact  |
| `docs/plans/`             | Design plans; plan 028 turns the skill into a rules library and judge |

## Status

Early. Plan 028 is the design for what comes next. There is no licence yet, so all rights are reserved until
one is chosen.

## Fan Content

mtg-rules-skill is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by
Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.

Card data and rulings come from [Scryfall](https://scryfall.com), which is not affiliated with this project.
