# Docket example: who chooses who goes first

A recorded challenge laid out as a case file: the petition, the clerk's brief, each judge's filings round by round,
the verifier's reports, the user's answers, the judges' settling positions, the Opinion of the Court with each
judge's join, concurrence or dissent, and the rule as recorded.

- `who-chooses.html` is the page (open it in a browser; fonts load from Google Fonts if online).
- `record/` is the challenge exactly as the program wrote it: 31 hash-chained event files and the resulting rule.
- `build.py` makes the page from any record: `python build.py record/challenges/<id> out.html`.

This is an evaluation run, not a real dispute. The user was a simulated user and the clerk and five judges were
Sonnet 5.5 agents, run on the model that includes the Opinion of the Court (PR #23). It took three attack rounds (the
second and third targeted at the judges whose objections were answered), a settling pass and one opinion, which all
five judges joined.
