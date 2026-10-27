# Bishop & Barrister

A Claude skill that answers Magic: The Gathering rules questions from the official Comprehensive Rules and
current Oracle card text instead of from memory, and cites the rules it relies on.

## Install

Clone it into your Claude Code skills folder:

```bash
git clone https://github.com/smithy-org/bishop-and-barrister ~/.claude/skills/bishop-and-barrister
```

Then fetch the rules documents once: the Comprehensive Rules, the Magic Tournament Rules, the Infraction
Procedure Guide and Judging at Regular REL. They are not bundled, because they belong to Wizards of the Coast
and change several times a year. The three tournament documents are PDFs, read with `pypdf`:

```bash
pip install pypdf
python ~/.claude/skills/bishop-and-barrister/scripts/sources.py update
```

Optionally, build the rulings record now; otherwise the skill does it the first time it needs it. This downloads
Scryfall's official rulings (about 5 MB) into `~/.claude/bishop-and-barrister/`, a git repository that keeps
every ruling the judge makes, with its history:

```bash
python ~/.claude/skills/bishop-and-barrister/scripts/judge.py build
```

Needs Python 3.10 or later, git, and `pypdf` for the tournament documents.

### Challenges (optional)

Everyday answering needs nothing more. To let a user challenge a ruling or argue for a new rule, the skill uses a
small program, `bab-challenge`, built for Linux, macOS and Windows. The first time a challenge runs, the skill
downloads the one for your machine from this repository's latest release and refuses it unless its SHA-256
matches the one recorded in `challenge/binaries.json`. If there is none for your machine, or no network,
challenges say so and everything else keeps working. A challenge uses a few million tokens at most, so the skill
tells you the cost and asks first. See `CHALLENGE.md`.

### On claude.ai

Zip this repository and add it as a custom skill in claude.ai's skills settings. This has not been tested
there yet. The skill fetches card data from scryfall.com and the rules documents from media.wizards.com, and a
challenge downloads its program from GitHub; if the sandbox blocks any of them, the script that needed it
reports the failure and the rest still works. Without independent subagents, claude.ai can open and refute a
challenge as a single-agent panel but cannot introduce a rule.

### Optional: sync across your devices

By default everything stays on your machine. To share your rulings between devices, point the skill at a
RustFS you control, on your own network or a remote server (1.0.4 or later; any S3-compatible store should
work). The bucket must be private. Put the keys in the environment, never in a file the skill writes:

```bash
export BISHOP_AND_BARRISTER_S3_ACCESS_KEY=...   # or a profile in ~/.aws/credentials (--profile)
export BISHOP_AND_BARRISTER_S3_SECRET_KEY=...
python ~/.claude/skills/bishop-and-barrister/scripts/judge.py sync --setup --endpoint https://rustfs.example.net --bucket bishop-and-barrister --create
python ~/.claude/skills/bishop-and-barrister/scripts/judge.py sync
```

After setup it syncs by itself: searches pull other devices' rulings in (at most every 10 minutes) and every
change is uploaded straight away, without ever holding up an answer. `judge.py sync` forces it. The local record
stays the copy the skill works from; the bucket is a synced copy. A RustFS to try it with:
`docker run -d -p 127.0.0.1:9000:9000 -e RUSTFS_ACCESS_KEY=... -e RUSTFS_SECRET_KEY=... rustfs/rustfs:1.0.4`.

## What's here

| Path                             | What                                                                  |
| -------------------------------- | --------------------------------------------------------------------- |
| `SKILL.md`                       | The skill's instructions for Claude                                   |
| `CHALLENGE.md`                   | How a challenge runs: the clerk, five judges, rounds and the vote    |
| `scripts/judge.py`               | The rulings record: search, show, recheck                             |
| `scripts/challenge.py`           | Challenges: the only way a rule enters the record (`CHALLENGE.md`)    |
| `challenge/`                     | The challenge core in Lean 4, with its proofs, built to `bab-challenge` |
| `scripts/card.py`                | Oracle text, official rulings and format legality, from Scryfall      |
| `scripts/lookup.py`              | Searches the Comprehensive Rules, or with `--doc` the MTR, IPG or JAR |
| `scripts/sources.py`             | Downloads the rules documents and checks for new versions             |
| `scripts/s3.py`                  | The optional remote store's client (standard library only)            |
| `scripts/update_rules.py`        | Downloads the Comprehensive Rules (`sources.py` runs it)              |
| `reference/trusted-sources.json` | The only web sources the judge may use, with their levels             |
| `reference/formats/`             | One file per format the skill covers, with a source for every fact    |
| `reference/upkeep.md`            | Keeping the documents current                                         |
| `evals/`                         | Rules questions with known answers, and the baseline results          |
| `tests/`                         | Tests: `python -m unittest discover -s tests`; CI also requires 70% coverage (`.coveragerc`) |
| `docs/plans/`                    | Design plans; plan 028 turns the skill into a rules library and judge |
| `docs/ROADMAP.md`                | Everything planned but not done yet, and who or what it waits on      |
| `docs/RELEASING.md`              | How a version is numbered and released                                |

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
