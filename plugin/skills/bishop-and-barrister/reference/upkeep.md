# Upkeep

## Keeping the documents current

The Comprehensive Rules change with every set, roughly quarterly; the MTR, IPG and JAR a few times a year.

```bash
python scripts/sources.py update --check  # has anything changed?
python scripts/sources.py update          # install new versions, then recheck the record
python scripts/sources.py list            # what is installed
```

When a document changes, `sources.py` runs `judge.py recheck`. It flags house rules whose cited text changed.
A rule a challenge introduced goes stale instead, and a new challenge opens against the new text, carrying the
old case: the rule is shown as unconfirmed until it wins again (`CHALLENGE.md`).

`reference/version.json` and `reference/sources.json` record the installed versions. The CR updater compares
the file's hash, not its dates: the filename's date (when Wizards posted it) and the effective date inside it
differ.

## Syncing with a remote store

There are two storage modes. **Local only** is the default: the record lives in `~/.claude/bishop-and-barrister/`
and nothing leaves the machine. **Local plus a remote RustFS** keeps a synced copy in a bucket the user chooses,
so their other devices share the same record: official rulings, challenges and the rules they introduced. In
both, the local record is the working copy every answer reads.

Only the user sets up a store; never pick an endpoint for them. Their keys go in the environment
(`BISHOP_AND_BARRISTER_S3_ACCESS_KEY`, `BISHOP_AND_BARRISTER_S3_SECRET_KEY`) or a `~/.aws/credentials` profile,
never in a command you echo back or in `config.json`.

```bash
python scripts/judge.py sync --setup --endpoint https://rustfs.example.net --bucket bishop-and-barrister --create
python scripts/judge.py sync
```

`--setup` checks the endpoint before saving it: plain `http://` only for this machine or a private network, keys
that work, a bucket that exists and refuses anonymous reads.

After that it **syncs by itself**. Reads pull in other devices' changes first, at most once every 10 minutes
(`$BISHOP_AND_BARRISTER_SYNC_INTERVAL` seconds): `judge.py search` and `show`, and `challenge.py status`, `show`,
`list` and `trace`. Writes upload this device's change straight after: `judge.py build`, `migrate` and `recheck`,
and every `challenge.py` command that adds an event. Neither ever stops the command: a problem is noted once on
stderr (`[sync paused: ...]`) and the local record carries on. `judge.py sync` forces a full sync now and reports
any problem; `BISHOP_AND_BARRISTER_AUTO_SYNC=0` turns the automatic part off.

Challenges can't conflict: each event is its own file, so two devices add files rather than edit one. If two
devices acted in the same state, `challenge.py status` reports a fork for the user to settle. If a sync stops on
a conflict elsewhere (two devices changed the same rule file), show the user both versions, settle it in their
words, then run `judge.py sync`. If the store can't be reached, say so once and carry on.
