# Baseline

The skill's evals, run before plan 028's phase 1 changes anything, so that later phases can show their effect.
Each case was answered once with the skill and once by Claude without it. The run without the skill had no
skills, no rules files and no web, so it answered from memory. Each answer was graded against the case's
`graders/`. The full outputs, grades and a review page are kept outside the repository, in
`bishop-and-barrister-workspace/iteration-N/`, next to the clone.

## Iteration 2 (current)

Run on 2026-10-25 against commit `d9a0170`, with the Comprehensive Rules effective 2026-09-25. There are 19 cases:

- the 13 from iteration 1;
- six about mechanics from sets released after mid-2026 (The Hobbit, 2026-08-14; Reality Fracture,
  2026-10-02): empower Jace, storied, recruit, the new "attacks a player alone" rule (506.6), Heartwood tokens and
  hone counters.

Every case now also checks that the answer cites at least one rule, and that each rule it cites exists and says
what the answer claims.

|                                 | With the skill | Without       | Difference |
| ------------------------------- | -------------- | ------------- | ---------- |
| Assertions passed, all 19 cases | 84 / 85 (99%)  | 63 / 85 (74%) | +25 points |
| The six new-set cases           | 28 / 28        | 11 / 28       |            |
| The 13 older cases              | 56 / 57        | 52 / 57       |            |
| Citation check passed           | 19 / 19        | 13 / 19       |            |
| Time per question               | 38.3 s         | 26.8 s        | +11.4 s    |
| Tokens per question             | 73.2k          | 66.4k         | +6.8k      |

### What it shows

- **The skill matters most where Claude's memory runs out.** On the six new-set cases, Claude without the skill
  didn't know the mechanics. It hedged, guessed by analogy, or got them wrong:

  - it allowed that Heartwood tokens might be lands, and said they might tap the turn they arrive;
  - it said a Lake-town Lookout gives its token "whatever recruit did", but recruit makes a token only for a
    nonland discard;
  - it said Sting's hone bonus stops if Sting loses its abilities, but the official ruling says it doesn't;
  - it compared empower Jace to amass and cited amass as 701.44, but 701.44 is explore.

  With the skill, all six were right, quoting the new rules (506.6, 701.70a, 701.71a, 702.195a, 122.1j, 111.10x)
  and the official rulings.

- **Citations:** every rule the skill cited exists and supports its claim. Without the skill:
  - four answers cited no rule at all;
  - two cited the wrong rule: 702.19c for trample (it's trample over planeswalkers) and 701.44 for amass.
- **On classic interactions both do well** (56/57 against 52/57). These are in Claude's training data.
- **The skill's one miss** is still the tournament remedy. It leaves out that the opponent chooses only from cards
  that weren't previously known. Phase 2 adds the Infraction Procedure Guide.

## Iteration 1

Run on 2026-10-25 against commit `d034ed0`, with the 13 original cases and no citation check.

- **Assertions passed:** 43/44 (98%) with the skill, 42/44 (95%) without.
- **Cost of the skill:** 42.7 s and 74.0k tokens per question, against 26.9 s and 66.4k without.

The set was too easy to tell the two apart. The real difference, accuracy of sources, wasn't checked yet: the run
without the skill had cited 702.19c for trample, IPG 2.2 for Hidden Card Error (it's 2.3) and "103.7 or 103.8" for
the first-draw rule. Iteration 2 added the citation check and the new-set cases.

## Next

- **Repeat runs:** run each configuration more than once, to measure variance.
- **More cases where memory fails:** recent errata, obscure interactions, and more cases that leave out a
  deciding fact.
- **After each phase of plan 028:** rerun this set.
