# Docket example: who chooses who goes first

A recorded challenge laid out as a case file: the petition, the clerk's brief, each judge's filings round by round,
the verifier's reports, the user's answers, the judges' settling positions and the rule as recorded.

- `who-chooses.html` is the page (open it in a browser; fonts load from Google Fonts if online).
- `record/` is the challenge exactly as the program wrote it: 32 hash-chained event files and the resulting rule.
- `build.py` makes the page from a record: `python build.py record/challenges/<id> out.html`.

This is an evaluation run, not a real dispute. The user was a simulated user and the clerk and five judges were
Sonnet 5.5 agents, on the consensus model (PR #16) before the opinion step (PR B). So there is no Opinion of the
Court, joins, concurrences or dissents here; a run on the current model would have them.
