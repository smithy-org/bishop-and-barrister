# reference/

## Written by hand, shipped with the skill

| Path                    | What                                                                                  |
| ----------------------- | ------------------------------------------------------------------------------------- |
| `formats/`              | One file per format, plus `matches.md`; every fact with its source. See its README    |
| `trusted-sources.json`  | The only web sources the judge may use, with their levels                             |
| `upkeep.md`             | Keeping the documents current                                                         |

## Downloaded, never shipped

These belong to Wizards of the Coast and change several times a year, so each copy downloads its own:

    python scripts/sources.py update

| Path                 | What                                                                             |
| -------------------- | -------------------------------------------------------------------------------- |
| `MagicCompRules.txt` | The Comprehensive Rules (`update_rules.py`, which `sources.py` runs)             |
| `version.json`       | The CR version installed: its effective date, posting date and hash              |
| `docs/`              | The MTR, IPG and JAR: each PDF and its converted sections (`<doc>.json`)         |
| `sources.json`       | The version of each tournament document installed                               |

A CR copied in by hand works too: name it `MagicCompRules.txt` and put it here. It has no `version.json`, but
`update_rules.py --check` hashes the file and works out what it needs.
