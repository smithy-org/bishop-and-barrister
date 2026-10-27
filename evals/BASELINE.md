# Baseline

The skill's evals, run before plan 028's phase 1 changes anything, so that later phases can show their effect.
Each case was answered once with the skill and once by Claude without it. The run without the skill had no
skills, no rules files and no web, so it answered from memory. Each answer was graded against the case's
`graders/`. The full outputs, grades and a review page are kept outside the repository, in
`bishop-and-barrister-workspace/iteration-N/`, next to the clone.

## Challenges (plan 029), run 2026-10-27

The first run of `evals/challenges/`: each case played through the panel in `CHALLENGE.md`, with a simulated user
following the case's `user.md`, and answered three times by a single agent for comparison. Everything ran on
Claude Sonnet 5.5 (one pilot of `urborg-still-swamps` on Opus 5.5 also refuted it, at 738k tokens). The first six
cases ran with seven judges; the panel was then cut to five (#14), and the last three ran with five. **Nine of
the ten cases ran; `multiplayer-match-ends-at-time` was held** because it would meet the same wall as
`multiplayer-match-who-chooses`, below.

| Case                                 | Expected   | Panel (judges)         | Rounds | Single agents ×3 | Panel tokens | Singles ×3 |
| ------------------------------------ | ---------- | ---------------------- | ------ | ---------------- | ------------ | ---------- |
| `urborg-still-swamps`                | refuted    | refuted ✓ (7)          | 1      | refuted ×3       | 738k         | 224k       |
| `deathtouch-trample-full-toughness`  | refuted    | refuted ✓ (7)          | 1      | refuted ×3       | 730k         | 218k       |
| `humility-always-wins`               | refuted    | refuted ✓ (7)          | 1      | refuted ×3       | 897k         | 231k       |
| `summoning-sickness-all-permanents`  | refuted    | refuted ✓ (7)          | 1      | refuted ×3       | 1.01M        | 219k       |
| `extra-card-regular-rel-game-loss`   | refuted    | refuted ✓ (7)          | 3      | refuted ×3       | 2.14M        | 233k       |
| `forged-quote`                       | refuted    | **open** ✗ (7)         | 4      | refuted ×3       | 3.29M        | 237k       |
| `multiplayer-match-who-chooses`      | introduced | **refuted** ✗ (5)      | 4 + vote | open ×3        | 2.49M        | 231k       |
| `magar-aftermath`                    | open       | **refuted** ✗ (5)      | 4 + vote | refuted ×3     | 0.85M        | 265k       |
| `commander-tax-free-first-recast`    | house-rule | house-rule ✓ (5)       | 3 + vote | refuted ×3     | 1.99M        | 220k       |

Panel tokens include the clerk, the simulated user and every judge, including refiled filings. A single agent
costs about 75k tokens, so the panel cost 10 to 44 times as much.

### What it shows

- **The panel did not beat a single agent.** It reached the expected outcome in 6 of 9 cases; the single agents'
  majority did in 6 or 7 (it depends on how `commander-tax` is read, and on whether the expected answers for
  `magar-aftermath` and `who-chooses` are right). Where they disagreed, the single agents were right once
  (`forged-quote`) and the panel never was. On the five easy cases both were right every time, and the panel's cost
  bought nothing a single agent didn't deliver.
- **Starting an agent costs about 60k tokens before it does anything:** a simulated user that made one tool call
  cost 61k tokens. So the panel's cost is its agent count, not its depth of thought, which is why the judges were
  cut from seven to five (#14).
- **The judges mostly find the same thing.** On the one-round cases every judge attacked the same step and cited
  the same two sources (the Urborg ruling and CR 613.8), whatever their lens.

### What went wrong, and what each failure was

1. **Gap rules can't be introduced** (`who-chooses`, and so `ends-at-time`). All five judges voted convinced after
   four rounds, and the core still refused the rule: its tie-break steps are the rule's own new content, which has
   no official source, and the guard refuses an unsourced assumption. A rule that fills a gap is new content
   by definition, so as built no gap rule can ever be introduced. This is a design flaw. The proposed fix is a
   separate kind of step, a *stipulation*, that is the rule's declared new content and what the judges vote on,
   while factual steps still need sources.
2. **A case can stay `open` when it should be refuted** (`forged-quote`). The simulated user restated an unsourced
   claim for four rounds; all 22 refutations were verified and none answered, and the cap sent it to `open` after
   3.29M tokens. When no standing refutation has been answered with a sourced rebuttal, `refuted` is the honest
   outcome, and it could be reached after the first such round.
3. **`magar-aftermath` came out `refuted`, not `open`, on both the panel (all five judges not convinced) and every
   single agent.** Either the expected answer is wrong (the judges cite CR 707.12 and the aftermath ruling) or the
   panel and the agents share a blind spot. Settling it needs a human judge, so treat it as unresolved.
4. **`challenge.py trace` rejected a house rule's rule file** (it expected every rule file to belong to an
   introduced challenge), so the grader marked `commander-tax` wrong. The outcome was right.
5. **Prompt gotchas the judges kept hitting**, each costing a refused filing: premises written as bare numbers
   instead of `F1`/`S1`/`C1`; quoting a rule's `Example:` paragraph or a section heading, which isn't in the pinned
   text; an Oracle excerpt that included the type line; a `fix` reply with the revised case nested too deep; and a
   revised case with no `open_questions`.

### Caveats

- **The runs aren't perfectly controlled.** Seven judges ran the first six cases and five ran the last three, so
  the comparison of five against seven is confounded with the case type. The five-judge runs of `who-chooses` and
  `commander-tax` (and the start of `magar`) had no MTR, IPG or JAR, because the checkout lacked the downloaded
  documents; this was fixed during the run.
- **The simulated user doesn't follow `user.md` closely.** It was told to rebut once; it usually conceded
  everything, and twice narrowed its own case.
- **One Urborg run was filed twice** by mistake; the record shows the version that counted, and the orchestrator's
  report described the other.
- **Per-role token rows are approximate:** agents' usage arrives in notifications, and a few rows were mapped by order.
- The full outputs (records, filings, ledgers, reports) are kept outside the repository in
  `bishop-and-barrister-workspace/challenges-2` (seven judges) and `challenges-3` (five).

## Iteration 8 (current): phase 3, one file per format

Run on 2026-10-26 on branch `phase-3-formats`. `reference/formats.md` became `reference/formats/`: one file per
format plus `matches.md`, each with a header recording the CR and MTR versions it was checked against. Every fact
was re-checked against the local CR and MTR, Oathbreaker's site and Wizards' format pages, which corrected:

- Limited decks returning to their registered form: the old file's MTR 3.16 exception is now MTR 7.3, and only
  without decklists, never at Competitive REL;
- the "any number of basic lands" in Limited: only the five regular basics, not snow basics or Wastes (MTR 7.2);
- a claim that "CR 906 is something else": the CR's variant sections stop at 905.

It also added the rule that nobody may sideboard after a pre-game loss of game 1 (MTR 3.16), and a warning that
the MTR's pointer to "rule 103.4" for mulligans is out of date (it's 103.5).

One case was added, for 30 in all: `draft-snow-basics` (snow basics and Wastes at a draft, MTR 7.2). The four
format cases were rerun with the skill; the new one with and without it.

| Case                                 | Iteration 4                | Iteration 8                |
| ------------------------------------ | -------------------------- | -------------------------- |
| `three-player-first-draw`            | 3 / 3, 78.5k, 43.8 s       | 3 / 3, 75.9k, 35.7 s       |
| `two-player-commander-free-mulligan` | 4 / 4, 82.2k, 62.8 s       | 4 / 4, 78.8k, 43.1 s       |
| `oathbreaker-signature-spell`        | 4 / 4, 79.8k, 62.3 s       | 4 / 4, 77.3k, 49.9 s       |
| `commander-relentless-rats-sol-ring` | 5 / 5, 82.3k, 73.8 s       | 5 / 5, 78.6k, 61.6 s       |
| `draft-snow-basics`                  | new                        | 5 / 5 (without: 3 / 5)     |

### What it shows

- **Scores held, cost fell.** The four format cases kept 16 / 16 with 3.0k fewer tokens (80.7k to 77.7k), 13 s
  less time (60.7 s to 47.6 s) and answers 37% shorter. Each run read only the format file it needed.
- **The new case:** without the skill Claude had the answer from memory but cited nothing, said it should be
  checked, and claimed Wastes is the only basic that makes colorless mana (Snow-Covered Wastes does too). With
  the skill it quoted MTR 7.2 and found official card rulings saying the same.
- **All four drafted rulings passed `judge.py record`**, including Oathbreaker's, which cites the community
  site's 906.x numbers.
- **A test now guards the format files:** every CR, MTR and IPG number they cite must exist in the installed
  documents. It caught the "CR 906" claim.

## Iteration 7: checking side remarks

Run on 2026-10-25 after one line was added to SKILL.md's step 3: every side remark gets the same check as the main
answer (look up its rule and cite it), or is left out. Only the two cases that slipped in iteration 6 were rerun.

| Case                             | Iteration 6 | Iteration 7 |
| -------------------------------- | ----------- | ----------- |
| `deck-problem-59-cards-game-one` | 4 / 5       | 5 / 5       |
| `die-roll-decides-match`         | 4 / 5       | 5 / 5       |

Both wrong remarks were gone: the Deck Problem answer no longer claimed sideboarding in game 2, and the die-roll
answer no longer described single elimination. Every aside left in was backed by a section that says it (IPG
section 3's introduction on intent, IPG 1.1 on when a Match Loss applies). With the eight iteration 6 cases, that
makes 41 / 41. The session restarted while these runs finished, so their token and time figures weren't
captured.

## Iteration 6: fewer tokens

Run on 2026-10-25 on branch `phase-2-sources`, after six changes meant to cut tokens and time:

1. `lookup.py --doc ipg rule` leaves out each section's Examples and Philosophy (`--all` adds them back).
2. Every document lookup prints its effective date, so `toc` isn't needed to find it.
3. `lookup.py rule` takes several rules or sections at once, and SKILL.md asks for batched calls.
4. `judge.py search` keeps only close matches when not every word matches, takes `--type`, lists the user's
   rulings briefly (`show` prints one in full), and returns 5 results instead of 8.
5. SKILL.md went from 15.8k to 7.4k characters. Recording, discussing, reviewing and updating moved to
   `reference/recording.md`, read only when needed.
6. SKILL.md asks for shorter answers: the ruling, its citations, the sequence only when order matters, and edge
   cases in a line each.

The five tournament cases and three card cases (Torbran, Magar, Humility) were rerun with the skill, and compared
with their latest earlier runs (iteration 5 for tournament cases, iteration 4 for card cases).

| Mean over the 8 cases                    | Before  | Iteration 6 | Change   |
| ---------------------------------------- | ------- | ----------- | -------- |
| Tokens per run                           | 84.8k   | 81.0k       | −3.8k    |
| The skill's share (above ~66.5k fixed)   | ~18.3k  | ~14.5k      | about −21% |
| Time per run                             | 73.8 s  | 61.3 s      | −17%     |
| Answer length (characters)               | 3,066   | 2,207       | −28%     |
| Assertions passed                        | 40 / 41 | 39 / 41     | −1       |

### What it shows

- **Smaller and faster, but less than estimated.** The estimate was about 9k tokens saved per question; the
  run saved 3.8k. Runs still asked for `--all` when they wanted examples, and runs that drafted a ruling read
  `reference/recording.md` and the template (about 1.7k).
- **Answers are a quarter shorter.** Output tokens cost more than input, so this is most of the money saved.
- **Two new citation slips, both in side remarks:**
  - The Deck Problem answer said both players may sideboard for game 2. IPG 1.1 says that after a Game Loss
    issued before the match begins, neither may sideboard for the first game played. Iteration 5 had this right.
  - The die-roll answer said that in single elimination the highest life total wins the match. MTR 2.4 uses
    life totals to decide the current game, and only when game wins are tied.
  - With one run per case, this could be variance or the shorter answers, which leave less room to qualify an
    aside. Repeat runs would tell.
- **Magar now passes 6/6:** its shorter answer still sends the user to judge chat, which iteration 4 left out.

## Iteration 5: phase 2, the tournament documents

Run on 2026-10-25 on branch `phase-2-sources`: `sources.py` downloads the Magic Tournament Rules (effective
2026-02-27), the Infraction Procedure Guide (2024-09-23) and Judging at Regular REL (2024-08-05), and
`lookup.py --doc` reads them. Four tournament cases were added, for 29 in all:

- `extra-card-regular-rel`: an extra card drawn at FNM (the JAR's fix, not the IPG's);
- `deck-problem-59-cards-game-one`: a 59-card deck at pre-game shuffling (Warning, upgraded to a Game Loss);
- `die-roll-decides-match`: rolling a die to settle a time draw (Match Loss; Cheating if they knew);
- `missed-trigger-regular-pointing-out`: an opponent's missed Dark Confidant trigger at a store event.

`extra-card-competitive-rel`'s grader 04 used to accept "says the skill has no copy of the IPG"; now that it
has one, the grader asks for IPG 2.3. The five tournament cases were run with the skill; the four new ones
without it too, and the old one's iteration 3 answer was regraded. The other 24 cases keep iteration 4's runs.

|                                      | With the skill  | Without        |
| ------------------------------------ | --------------- | -------------- |
| The five tournament cases            | 25 / 25         | 13 / 25        |
| All 29 cases                         | 131 / 134 (98%) | 92 / 134 (69%) |
| Time per tournament question         | 78.2 s          | 29.9 s         |
| Tokens per tournament question       | 85.8k           | 67.0k          |
| Drafted rulings `record` accepts     | 5 / 5           |                |

### What it shows

- **Tournament rules are where memory fails worst.** Without the skill:
  - At FNM, Claude gave the Competitive fix: reveal the hand, the opponent picks, shuffle it in. The JAR says to
    put a random card on top and not to shuffle.
  - It said rolling a die to settle a match disqualifies both players. IPG 4.3 makes it a Match Loss, and
    Cheating only if the players knew.
  - It knew the 59-card deck was a Game Loss but not why. It blamed the format minimum, which is the rule after
    sideboarding, and didn't know the base penalty is a Warning.
- **With the documents, every answer was right and cited the section and its version.** The runs used the
  MTR to settle side questions too: Appendix F to confirm FNM is Regular REL, 2.4 for what happens at time.
- **The iteration 3 and 4 miss is fixed.** The Competitive extra-card answer now says the card goes back into the
  random portion of the library, from cards the opponent didn't already know.
- **Rulings now record.** All five drafted rulings passed `judge.py record`, against 1 of 12 in iteration 4,
  after SKILL.md listed the allowed values. Their IPG, MTR and JAR citations were pinned to the section, by
  number or by words from a JAR heading.
- **The cost:** about 50 s and 19k tokens more per tournament question, spent reading the documents.

## Iteration 4: phase 1

Run on 2026-10-25 against commit `989d79b`, the phase 1 skill: SKILL.md's judge procedure, with `judge.py search`
over a copy of a real record (79,706 official rulings) as step 0. All 25 with-skill cases were rerun. The runs
without the skill are iteration 3's, since nothing changed for them. Runs were told to write the ruling they
would record to `ruling.json` instead of running `judge.py record`, so they didn't commit to one shared record.

|                         | Phase 1         | Iteration 3     | Without        |
| ----------------------- | --------------- | --------------- | -------------- |
| Assertions passed       | 110 / 114 (96%) | 113 / 114 (99%) | 83 / 114 (73%) |
| Time per question       | 60.9 s          | 40.9 s          | 28.2 s         |
| Tokens per question     | 79.0k           | 74.0k           | 66.5k          |
| Drafted rulings valid   | 1 / 12          |                 |                |

### What it shows

- **Step 0 works.** Every run searched the record first, and 13 of 25 found official rulings that answered the
  question (Torbran, Panglacial Wurm, Chains, Ob Nixilis, Karn, Blood Artist, Sting, Humility, Urborg and others)
  and quoted them. These runs correctly recorded nothing.
- **The score dropped by three, and none of the three is caused by the record.** Two answers cited a wrong rule
  for a correct claim: Empower Jace cited 606.4 and 306.5b for "loyalty is the number of loyalty counters", and
  Sting cited 704.5n (an Equipment attached illegally) where 704.5p applies (Sting has lost the subtype). The Magar
  answer labelled its "no" unsettled but didn't send the user to a judge. These are single-run variance; repeat
  runs would show it.
- **Only 1 of the 12 drafted rulings would record.** The other 11 used a `question_type` or `confidence` value
  that `judge.py` doesn't accept (`legality`, `outcome`, `format`; `probable`). SKILL.md never lists the allowed
  values; the template shows one. With those mapped to the nearest allowed value, all 11 recorded.
- **Scryfall rate-limited 9 of 25 runs** (HTTP 429) while 25 ran at once. Those answers quoted card text from
  memory and said so; it was correct each time. `card.py` and `judge.py` don't retry. Most of the 20 s slowdown
  is retries and the extra record search.
- **The tournament remedy is still the one miss** carried from iteration 3 (no IPG until phase 2).

## Iteration 3

Run on 2026-10-25. There are 25 cases: iteration 2's 19, plus six on cards known for hard rules interactions:

- Torbran, Thane of Red Fell with a trampler;
- Panglacial Wurm cast during a fetch's search;
- Chains of Mephistopheles with an empty hand;
- Ob Nixilis, Captive Kingpin and simultaneous combat damage;
- Karn Liberated's restart in Commander;
- Magar of the Magic Strings with an aftermath card. This case has no official answer, and it tests whether the
  skill says so.

The skill hasn't changed since iteration 2, so those 19 cases keep their iteration 2 runs; only the six new ones
were run.

|                                 | With the skill  | Without        | Difference |
| ------------------------------- | --------------- | -------------- | ---------- |
| Assertions passed, all 25 cases | 113 / 114 (99%) | 83 / 114 (73%) | +26 points |
| The six hard-card cases         | 29 / 29         | 20 / 29        |            |
| Time per question, all 25       | 40.9 s          | 28.2 s         | +12.7 s    |
| Tokens per question, all 25     | 74.0k           | 66.5k          | +7.4k      |

### What it shows

- **Claude without the skill knows these older cards fairly well, but its answers can't be checked.** Four of the
  six cited no rule. The Karn answer wasn't sure who starts the restarted game, and never said that no one wins
  the old one. The Magar answer misdescribed the card (it said Magar exiles the card, and called the face-down
  creature a 2/2) while giving a firm "no" on Dawn.
- **On Magar, the skill did what an unsettled question needs.** It found the contrasting rule for Garth One-Eye
  (707.13) and an aftermath ruling, and leaned towards "no" on Dawn. It still said no official source settles it,
  explained what would change the answer, and sent the user to a judge.

## Iteration 2

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
