# reference/

`formats.md` is written by hand and ships with the skill: the rules for each
format the skill covers and for matches of several games, with a source for every
fact. Update it when a source changes (its last section says how).

`MagicCompRules.txt` is downloaded here by `scripts/update_rules.py`.

It is not bundled with the skill: it's about a megabyte, it is revised with
every set release, and it belongs to Wizards of the Coast. Fetch a fresh copy
rather than shipping a stale one.

    python scripts/update_rules.py

`version.json` records which release is currently downloaded.

If you already have the file, you can drop it in manually instead — rename it
to `MagicCompRules.txt` and place it here. A manual copy has no `version.json`,
but `update_rules.py --check` will hash the file and work it out, so staleness
checking still works either way.
