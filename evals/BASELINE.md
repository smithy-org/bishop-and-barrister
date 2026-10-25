# Baseline (phase 0, iteration 1)

Run on 2026-10-25 against commit `d034ed0`, with the Comprehensive Rules effective 2026-09-25. Each of the 13
cases in this folder was answered once with the skill and once by Claude without it. The run without the skill
had no skills, no rules files and no web, so it answered from memory. Each answer was graded against the case's
`graders/`.

|                     | With the skill | Without       | Difference |
| ------------------- | -------------- | ------------- | ---------- |
| Assertions passed   | 43 / 44 (98%)  | 42 / 44 (95%) | +3 points  |
| Time per question   | 42.7 s         | 26.9 s        | +15.9 s    |
| Tokens per question | 74.0k          | 66.4k         | +7.6k      |

## What it shows

- **This set is too easy to tell the two apart.** 41 of the 44 assertions pass either way. These are classic
  interactions that Claude already knows from training.
- **The real gap is accuracy of sources, which the assertions didn't check.** Every error was in the baseline:

  - trample cited as 702.19c (trample over planeswalkers; trample is 702.19b);
  - Hidden Card Error cited as IPG 2.2 (it is 2.3);
  - the first-draw rule given as "103.7 or 103.8";
  - Pithing Needle quoted with wording that has since been updated.

  The skill's answers cited verified rule numbers and quoted current Oracle text and official rulings.

- **Where the skill lost:** the tournament question. It has no copy of the Infraction Procedure Guide, said so
  correctly, and then gave a vaguer remedy than the baseline. Phase 2 adds the IPG.
- **Cost:** about 16 seconds and 7.6k tokens more per question, for the card and rules lookups.

## Next iteration

- **Every case:** add an assertion that each cited rule number exists and says what the answer claims.
- **Questions where memory fails:**
  - cards and rules newer than the training data (the 2026-09-25 Comprehensive Rules, the latest sets);
  - recent errata;
  - obscure interactions;
  - more cases that leave out a deciding fact.
- **Repeat runs:** run each configuration more than once, to measure variance.

The full outputs, grades and a review page are kept outside the repository, in
`bishop-and-barrister-workspace/iteration-1/`, next to the clone.
