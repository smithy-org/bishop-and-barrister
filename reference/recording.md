# Recording, discussing and reviewing rulings

Read this when SKILL.md's step 4 says to record a ruling, or when the user argues a ruling or accepts one.

## Record a ruling

When the record search found no official or reviewed ruling that fits, record the one you just worked out, so
the next question like it starts from there:

```bash
python scripts/judge.py record ruling.json
```

Copy the shape from `reference/ruling-template.json`. Two fields take fixed values, and `record` refuses
anything else:

- **`question_type`:** `interaction` (how cards or effects combine), `legality-check` (is this play or game
  state legal), `sequence` (what happens in what order), `card-text` (what one card's wording means),
  `deck-legality` (can this card or deck be played in a format), `format-rule` (a format's own rules: life,
  mulligans, first draw, multiplayer) or `tournament` (tournament rules and penalties).
- **`confidence`:** `certain` (the rules or an official ruling settle it), `likely` (the best reading, but
  nothing official settles it) or `unsure`. A ruling backed only by level 4 sources is at most `likely`.

The record is read later by an agent that never saw this conversation, so write it for that reader:

- **`agent_summary`:** the answer, its conditions and the deciding rule numbers in a few self-contained
  sentences.
- **The context fields:** `applies_when`, `answer_changes_if`, `ask_if_unknown` and `misconceptions`. Empty
  lists are fine and mean "none".
- **`steps`:** each step names the citations (`refs`) that back it.
- **`citations`:** each needs an `id`.
  - CR citations need only `ref`; the judge pins the rule's text.
  - Tournament documents: `{"doc": "ipg", "ref": "2.3"}`, or `mtr` or `jar`. `ref` can also be words from
    the section's heading, which the JAR needs because it has no numbers. The judge pins the section's text.
  - Official rulings, Oracle text and web pages need an `excerpt`; a web page also needs its URL and date.

`record` refuses a ruling with missing fields, a CR rule that doesn't exist, or a document section it can't
find. It looks up each card on Scryfall to pin its Oracle text, so `recheck` can spot later errata. New rulings
are `unreviewed`.

## Discuss and review, only with the user

- **If the user argues the point,** keep the exchange:

  ```bash
  python scripts/judge.py discuss <id> entries.json --summary "What was settled"
  ```

  `entries.json` holds `[{"by": "user", "said": "..."}, {"by": "model", "said": "..."}]`. A judge's answer
  the user brings back goes in too, with who said it and when.

- **Mark a ruling reviewed only when the user says they accept it,** quoting their words:

  ```bash
  python scripts/judge.py review <id> --user-said "<their words>"
  ```

  Add `--house-rule` if the ruling knowingly departs from the official rules. Never review a ruling on your
  own judgement.

## Syncing with a remote store

There are two storage modes. **Local only** is the default: the record lives in `~/.claude/bishop-and-barrister/`
and nothing leaves the machine. **Local plus a remote RustFS** keeps a synced copy in a bucket the user chooses,
so their other devices share the same rulings. In both, the local record is the working copy every answer reads.

Only the user sets up a store; never pick an endpoint for them. Their keys go in the environment
(`BISHOP_AND_BARRISTER_S3_ACCESS_KEY`, `BISHOP_AND_BARRISTER_S3_SECRET_KEY`) or a `~/.aws/credentials` profile,
never in a command you echo back or in `config.json`.

```bash
python scripts/judge.py sync --setup --endpoint https://rustfs.example.net --bucket bishop-and-barrister --create
python scripts/judge.py sync
```

`--setup` checks the endpoint before saving it: plain `http://` only for this machine or a private network, keys
that work, a bucket that exists and refuses anonymous reads. `sync` merges the other devices' histories in and
uploads this device's. If it stops on a conflict, two devices changed the same ruling: show the user both
versions, settle it in their words, then sync again. If the store can't be reached, the local record still works;
say so and carry on.

## Keeping the documents current

The Comprehensive Rules change with every set, roughly quarterly; the MTR, IPG and JAR a few times a year.

```bash
python scripts/sources.py update --check  # has anything changed?
python scripts/sources.py update          # install new versions, then recheck rulings
python scripts/sources.py list            # what is installed
```

When a document changes, `sources.py` runs `judge.py recheck`, which flags recorded rulings whose cited text
changed. `reference/version.json` and `reference/sources.json` record the installed versions. The CR updater
compares the file's hash, not its dates: the filename's date (when Wizards posted it) and the effective date
inside it differ.
