# Bishop & Barrister

A Claude skill that answers Magic: The Gathering rules questions from the official Comprehensive Rules and
current Oracle card text instead of from memory, and cites the rules it relies on.

## Install

Clone it into your Claude Code skills folder:

```bash
git clone https://github.com/smithy-org/bishop-and-barrister ~/.claude/skills/bishop-and-barrister
```

Then fetch the Comprehensive Rules once. They are not bundled, because they belong to Wizards of the Coast and
change with every set:

```bash
python ~/.claude/skills/bishop-and-barrister/scripts/update_rules.py
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
| `docs/ROADMAP.md`         | Everything planned but not done yet, and who or what it waits on      |

## Status

Early. Plan 028 is the design for what comes next, and `docs/ROADMAP.md` tracks it.

## Licence

[Apache License 2.0](LICENSE). Redistributions must keep the [NOTICE](NOTICE), which carries the Fan Content
statement below. The licence covers this project's own code and text, not Wizards of the Coast's materials or
Scryfall's data.

## Fan Content

Bishop & Barrister is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by
Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.

Card data and rulings come from [Scryfall](https://scryfall.com), which is not affiliated with this project.
