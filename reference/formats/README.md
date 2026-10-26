# Formats

One file per format the skill covers, plus `matches.md` for starting a game and for matches of several games.
Every fact names its source and that source's level (plan 028): **1** the Comprehensive Rules (CR) and other
official Wizards rules and pages; **2** the Magic Tournament Rules (MTR) and a community-run format's own rules,
for that format only; **4** community consensus and data. Digital clients are described for comparison, not as
rules.

| File             | Formats                                    |
| ---------------- | ------------------------------------------ |
| `constructed.md` | Standard, Pioneer, Modern, Legacy, Vintage |
| `pauper.md`      | Pauper                                     |
| `limited.md`     | Draft, Sealed                              |
| `commander.md`   | Commander                                  |
| `brawl.md`       | Brawl (the CR's and MTG Arena's)           |
| `oathbreaker.md` | Oathbreaker                                |
| `matches.md`     | Who starts, mulligans, the first draw, matches of several games, sideboarding, digital clients |

## The header

Each file starts with a header recording when it was checked and the version of each rules document it cites:

```
---
checked: 2026-10-26
sources:
  cr: September 25, 2026
  mtr: February 27, 2026
---
```

The versions are the effective dates `sources.py list` prints. After `sources.py update` installs a new
version of a document, it lists the files whose header names an older one. Re-check the numbers those files
cite with `lookup.py`, fix anything that moved, and update the header.
