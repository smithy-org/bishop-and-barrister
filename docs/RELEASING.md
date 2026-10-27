# Releasing

A release is a git tag named `vMAJOR.MINOR.PATCH`, such as `v0.1.0`. Pushing the tag builds the challenge program
`bab-challenge` for five platforms and attaches the binaries, with their SHA-256 sums and a `pins.json`, to a
GitHub release. Nothing else needs releasing: everyday answering is just the files in the repository.

## What each number means

The version belongs to the challenge program, because that is the part users download and whose behaviour old
records depend on.

| Number | Bump it when | Example |
| ------ | ------------ | ------- |
| **MAJOR** | A change an existing challenge record can't be replayed under: the event file format, or the state machine's rules | Renaming an event type; a phase that old events can't reach |
| **MINOR** | New commands or event types, or new behaviour, that every old record still replays under | A new `view` option; a new optional event field |
| **PATCH** | Fixes that change no record's outcome | A wrong error message; a prompt fix in `CHALLENGE.md` |

Before 1.0.0 the program is still being shaped, so a MINOR bump may change behaviour; the three rules above are
what 1.0.0 will keep.

## The procedure

1. **Bump the version** in `challenge/Main.lean` (`def version`, the number after `bab-challenge`). Merge it to
   `main` through a pull request with the checks green.
2. **Tag that commit** and push the tag:
   ```bash
   git tag v0.1.0 && git push origin v0.1.0
   ```
   The `challenge` workflow refuses a tag that isn't `v` plus the number the built program reports, so a
   forgotten bump fails before anything is published.
3. **Wait for the release build.** It proves the theorems, runs the tests, builds five binaries, attaches them to
   the release and attaches `pins.json` (each file's name and SHA-256).
4. **Pin the binaries.** Copy the release's `pins.json` into `challenge/binaries.json` and merge that through a
   pull request. Until then `challenge.py` says there is no released program for the platform.
5. **Check a real download** on at least one platform: with no `BISHOP_AND_BARRISTER_CHALLENGE_BIN` set, run
   `python scripts/challenge.py open --statement "test"` against a throwaway `BISHOP_AND_BARRISTER_HOME`.
6. Write the release notes on the GitHub release: what changed, and the platforms built.

## If a release goes wrong

A tag that failed to build can be deleted and pushed again only before anyone has pinned its binaries. After
`binaries.json` names a release, fix forward with a new PATCH version; never replace published binaries, because
their SHA-256 sums are what users' installs check.
