# Keeping the documents current

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
