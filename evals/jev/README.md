# Would Jev help the challenge panel? An offline replay

Jev (TypeSafe AI's "System One" model) returns typed answers with calibrated confidence and no free text. It cannot
write a refutation, so the question is whether it helps **next to** the five judges. This folder replays data we
already recorded (three eval runs of the challenge panel, ten challenge cases, thirty everyday cases) through Jev and
through Claude Sonnet 5.5, in three roles. Nothing here touches the skill; it is documentation, scripts and raw
results. Everything ran on 2026-10-27 against `jev-1.14.0` (the version string in every response).

**Short answer.** On this data Jev is fast (median 155 ms) and almost free ($0.00002 to $0.00009 a call), and it is
good at one narrow thing: spotting a step whose conclusion has been negated or whose quote is unrelated. It is not
better than Sonnet at anything we measured, it is clearly worse at the triage and second-opinion questions, and the
samples are too small to show more. Recommendations are at the end; none says adopt.

## What was run

| | Jev | Sonnet 5.5 |
| --- | --- | --- |
| Calls | 243 attempts (cap 2,000), 0 failures, 0 retries needed | 26 subagents, 5 to 17 items each |
| Model | `jev-1.14.0`, `model: "jev-latest"` | `model: "sonnet"` |
| Input | the same text, one item per call | the same text, read from one input file |
| Cost | from `usage.input_tokens` at the published $0.042 per million input tokens (output is free) | about 70,000 tokens per agent (see the caveat below) |

Sonnet agents were told to use no tool except one Read of their input file and one Write of their answers, and to
judge every item independently. They are general-purpose agents, so that is an instruction, not a guarantee; each
reported 4 tool calls (we did not inspect which). Item ids are opaque
(`q101`), so no case name reaches them. The 26 inputs and answers are in `results/sonnet/` (`make_prompts.py` regenerates the prompt files, which hold local paths and so are not committed).

## Data and how it was labelled

- **Challenge cases** (10, `evals/challenges/`). E1 label from `case.yaml`'s `expected_state`: `refuted` and
  `house-rule` become **settled** (the official sources decide it against the user); the two multiplayer cases
  (`introduced`) are **gap**; `magar-aftermath` (`open`) is **contested**. That is 7 settled, 2 gap, 1 contested.
- **Everyday cases** (30, `evals/*/`): all **settled** except `magar-aftermath-unsettled`, which is **contested**.
  Together with the challenges that is 36 settled, 2 gap, 2 contested out of 40. **A reader who always answers
  "settled" scores 36/40 (90%).** Every accuracy below has to be read against that.
- **Recorded runs** (13 with complete event files and a `grade.json`): `challenges-2` six cases (seven judges),
  `challenges-3` three (five judges), `challenges-4` four (consensus model). The panel's final state is the
  `state` in `grade.json`; the expected outcome is from `case.yaml`. The panel matched expectations in 10 of 13 runs
  (the three misses are the first-run failures: `c2/forged-quote` stayed open, `c3/magar-aftermath` was refuted,
  `c3/multiplayer-match-who-chooses` was refuted).
- **Steps**: 34 distinct sourced steps across every recorded version of every case; 20 of them are in a final case.
  The brief asked for the final cases and a Sonnet sample of at most 40, so the Sonnet arm saw all 34.

## E1. Triage: do the sources settle it? (settled / gap / contested)

Variant **a** gives only the challenge text (or the everyday question). Variant **b** adds source text: for the
challenge cases the ten most-cited quotes from what the judges and clerk cited in the recorded runs; for the everyday
cases the rule text of the CRs named in `case.yaml`'s Sources line (38 rule texts in all; MTR/IPG/JAR sections where
the line names one; 6 cases got no text because their sources are card rulings or a document outside the CR, and the
card text was never attached). Both variants therefore use sources chosen **knowing the answer**, which flatters (b).

| | Accuracy (n=40) | Challenge cases (n=10) | Everyday (n=30) | Everyday false alarms (of 29 settled) |
| --- | --- | --- | --- | --- |
| Always "settled" | 36/40 (90%) | 7/10 | 29/30 | 0 |
| Jev, text only | 37/40 (92%, 95% CI 80-97%) | 8/10 | 29/30 | 0/29 |
| Jev, with sources | 36/40 (90%, CI 77-96%) | 7/10 | 29/30 | 0/29 |
| Sonnet, text only | 35/40 (88%, CI 74-95%) | 9/10 | 26/30 | 3/29 |
| Sonnet, with sources | 38/40 (95%, CI 83-99%) | 9/10 | 29/30 | 0/29 |

The four non-settled cases are what matter, because that is where triage would save a panel or send one.

| Case (true label) | Jev text | Jev + sources | Sonnet text | Sonnet + sources |
| --- | --- | --- | --- | --- |
| `multiplayer-match-who-chooses` (gap) | gap | settled | gap | gap |
| `multiplayer-match-ends-at-time` (gap) | settled | settled | gap | gap |
| `magar-aftermath` (contested) | settled | settled | gap | settled |
| `magar-aftermath-unsettled` (contested) | settled | settled | settled | settled |

- **Jev flagged 1 of the 4 non-settled cases as not settled with text alone, and 0 of 4 with sources. Sonnet flagged
  3 of 4 with text (2 with the right label; it called Magar "gap", not "contested") and 2 of 4 with sources.**
  Neither ever answered "contested" (0 of 2 true contested). Jev's headline accuracy equals the trivial baseline.
  Jev was confidently wrong on Magar: "settled" at 0.80 in both variants (and 0.56 / 0.64 on the unsettled everyday
  Magar case), while its one right gap call was at 0.35 confidence.
- Confusion matrices (rows true, columns predicted; in `results/tables.md`): Jev text: settled 36/0/0, gap 1/1/0,
  contested 2/0/0. Jev with sources: gap 2/0/0, contested 2/0/0. Sonnet text: settled 33/3/0, gap 0/2/0,
  contested 1/1/0. Sonnet with sources: gap 0/2/0, contested 2/0/0.
- **Calibration.** Jev: mean confidence 0.84 when right (n=37), 0.61 when wrong (n=3) in text-only; 0.80 (n=36) versus
  0.59 (n=4) with sources. By band, text-only: below 0.60 right 3 of 5, 0.60-0.80 right 6 of 6, 0.80-0.95 right 19 of
  20, 0.95+ right 9 of 9. So higher confidence did go with more often right, but with 3 to 4 wrong answers that is an
  anecdote, not a calibration curve, and one wrong answer carried 0.80. Sonnet's stated
  confidence behaved similarly (0.85 right vs 0.47 wrong, text only).
- **False alarms.** The brief worried about flagging settled everyday cases. Jev flagged none (0 of 29, CI 0-12%).
  Sonnet text-only flagged 3 of 29 (10%), none with sources.
- **Cost and speed.** Jev: median 155 ms (text only) and 163 ms (with sources), p95 about 200 ms, max 359 ms;
  462 and 647 input tokens a call on average, $0.00002 and $0.00003 a call, $0.0019 for all 80 calls. Sonnet:
  12 agents, 837,000 tokens in all and 15 to 23 seconds each for 5 to 10 items. Each agent carries about 65,000 tokens
  of fixed context, so these are not per-item costs; a bare API call with this text would be a few thousand tokens,
  but we did not measure that.

## E2. A second opinion at the settling step

Input per run: the final case text exactly as the judges see it (rule, applies-when, facts, derivation with each quote
and the `ASSUMPTION` / `STIPULATION` flags). **A** is that alone. **B** adds each judge's last filing (concession text
or refutation arguments and the quoted evidence; the vote flag and vote reasons are removed). B still leaks the
panel's reasoning, so treat B as "can it echo the evidence", A as the cleaner test. Questions: `convinced` (noul) and
`verdict` (introduce / refuse / unproven). The panel's final state maps introduced to introduce, refuted (and
house-rule) to refuse, open to unproven.

| Rater | Agrees with expected outcome (n=13) | Agrees with panel | Catches the 3 panel errors | Disagrees with the 10 correct panels |
| --- | --- | --- | --- | --- |
| Panel itself | 10/13 (77%, CI 50-92%) | - | - | - |
| **Flag rule only** (any assumption step: refuse; otherwise introduce) | 10/13 (77%) | - | - | - |
| Jev A | 6/13 (46%, CI 23-71%) | 6/13 | 1/3 | 5/10 |
| Jev B | 8/13 (62%, CI 36-82%) | 8/13 | 1/3 | 3/10 |
| Sonnet A | 12/13 (92%, CI 67-99%) | 10/13 | 2/3 | 0/10 |
| Sonnet B | 9/13 (69%, CI 42-87%) | 9/13 | 1/3 | 2/10 |

- **A trivial script is as good as the panel here.** The verifier already marks assumption steps, and "assumption
  means refuse" matches the expected outcome in 10 of 13 runs. Any rater that sees those flags can read them, so
  agreement with the expected outcome is partly the flag, not judgement.
- **Jev did not do what a second opinion needs.** Its `convinced` value is low everywhere (mean 0.18 for the three
  cases that should be introduced, 0.05 for the rest in A), so it separates them (AUC 0.97 in A, 0.90 in B, with
  3 versus 10 cases) but no threshold gives a verdict. Its choice answers were `unproven` for all three
  should-introduce cases in A (0 of 3 introduce; B: 1 of 3), and it called `refuse` on `magar-aftermath`'s two
  `open` runs (both wrong; the expected answer is unproven). In B it refused `c4/multiplayer-match-who-chooses`,
  which the panel introduced correctly (convinced 0.07). It never produced a case where it was right and the panel
  wrong, except `c2/forged-quote` (panel "open" after four rounds; Jev refuse, as expected; Sonnet also).
- **Sonnet A got 12 of 13**, missing only `c3/multiplayer-match-who-chooses` (unproven, expected introduce). It
  caught 2 of the 3 panel errors (`c2/forged-quote` and `c3/magar-aftermath`) and overturned none of the 10 correct
  panels, but with 3 panel errors and the assumption flags visible this is a weak result.
  **Adding the judges' evidence (B) made Sonnet worse (12 to 9), which suggests the extra text pushed it toward the
  judges' own wrong turns.** `c3/commander-tax-free-first-recast` read as "unproven" to Jev (both) and Sonnet B.
- Disagreement tables per run are in the table above and `results/tables.md`; the raw answers are in
  `results/jev_e2a.json`, `jev_e2b.json` and `results/sonnet/out/e2*.json`.
- Cost: Jev $0.00004 (A) and $0.00009 (B) a call, 170 to 180 ms median. Sonnet 6 agents, 449,000 tokens.

## E3. Step entailment: does the conclusion follow from the premises and the quote?

For each sourced step, Jev (noul) is asked whether the conclusion follows from the premises and the quoted source.
Corruptions, made with a fixed seed (`build_inputs.py`): **neg** prefixes "It is not true that"; **swap** replaces the
conclusion with another sourced step's conclusion from the same case (27 of 34) or another case (7); **excerpt**
replaces the quote and its reference with a real quote from a different case's different rule. "Detected" means the
answer fell below the threshold. Counts are over 34 steps (102 corrupted copies); the 20 final-case steps alone give
the same picture (`results/tables.md`).

| Threshold | Jev: false alarms on 34 originals | Jev: detected, all 102 corrupted | Sonnet: false alarms | Sonnet: detected |
| --- | --- | --- | --- | --- |
| 0.5 | 9/34 (26%) | 90/102 (88%, CI 81-93%) | 3/34 (9%) | 87/102 (85%, CI 77-91%) |
| 0.7 | 11/34 (32%) | 97/102 (95%) | 4/34 (12%) | 90/102 (88%) |
| 0.3 | 2/34 (6%) | 82/102 (80%) | 1/34 (3%) | 81/102 (79%) |

By corruption at 0.5: Jev negation 34/34, unrelated quote 32/34, swapped conclusion 24/34 (same-case swaps 17/27,
other-case swaps 7/7). Sonnet: negation 34/34, quote 29/34, swap 24/34. Rank quality is the same: AUC 0.94 for Jev,
0.94 for Sonnet (originals ranked above corrupted copies).

- **Jev detects corruptions about as well as Sonnet at 0.5 (88% versus 85%) but with 26% false alarms versus 9%.** At
  Jev's 0.3 threshold (6% false alarms) it detects 80% against Sonnet's 79% at 0.3 (3% false alarms), so the two are
  indistinguishable at this size. The fair statement is "comparable ranking; Jev's values sit lower on originals".
- **What a human would call a real step flaw is not separated from corruption here.** Jev flagged 9 originals below
  0.5. Reading three of them: `s033` (0.06) concludes "the stipulation does not apply to a draw", but its quote is the
  draw sentence of CR 103.1, which says nothing about the stipulation; that is plausibly a real over-reach the script
  cannot see, so some "false alarms" may be true findings. Several "missed" swaps are a neighbouring step that is
  equally true of the quote, so they are not corruptions in substance. Neither reading was adjudicated by an
  independent reader; do not read the false-alarm rate as a clean error rate.
- **What this cannot show.** The corruptions are synthetic and crude (a prefix, a swapped sentence). The judges'
  real refutations of a step are subtler. 34 steps from 10 cases, many near-duplicates across versions.
- Cost: Jev 136 calls, $0.0027 in all, median 158 ms. Sonnet 8 agents, 576,000 tokens.

## Uncertainty and what the data cannot show

- Ten challenge cases, 13 runs, 34 steps. All intervals are Wilson 95% and are wide; none of the Jev-versus-Sonnet
  differences in E1 and E3 is distinguishable from noise. The E2 gap (Jev 6 to 8 of 13, Sonnet 9 to 12) is the only
  difference large enough to count, and it is against Jev.
- One run of each model per item; no repeat to measure variance. Sonnet answered in batches of 5 to 17 items, which may lower or raise its quality.
- The labels, sources and cases come from the maintainer's own eval design, and Sonnet 5.5 produced the panel's
  judgements; a Sonnet comparator agreeing with them is not independent. That is also why "blind spots shared within
  a model family", the reason for a second model, **cannot be tested** with a Sonnet comparison: no case here has a
  verdict the panel got wrong in a way Jev correctly caught (it caught `c2/forged-quote` and nothing else).
- Real use differs: a live case, not a replay; the judges' text would be unfinished.

## Constraints on any adoption

The skill must keep working with no account. Anything sent to Jev leaves the machine, which is a privacy decision
for the user (we sent only rules text and challenge statements, no paths or personal data). Jev's output could only
ever advise: the engine's proofs cover only the engine, and a Jev "follows" is neither a proof nor a verified quote.

## Recommendation

| Role | Verdict | Why the data supports it |
| --- | --- | --- |
| **E1 triage before a panel** | **Drop** | Jev's accuracy (92% and 90%) equals "always settled" (90%). It flagged 1 of 4 non-settled cases with text and 0 of 4 with sources, never said "contested", and was 0.80 confident that Magar is settled. Its one strength, no false alarms on 29 settled cases, is what the trivial baseline also has. Sonnet flagged 3 of 4 (text) and 2 of 4 (sources). A reliable triage needs more non-settled cases than we have (4 of 40). |
| **E2 second opinion at settling** | **Drop** | Jev agreed with the expected outcome in 6 and 8 of 13, below the panel (10), the flag rule (10) and Sonnet without evidence (12). `convinced` ranks the should-introduce cases higher but never reached a usable threshold, and it refused a correct introduction. The model-family blind-spot argument could not be tested here. |
| **E3 step entailment** | **Test further** | The only role where Jev works as designed: it caught 100% of negated conclusions, 94% of unrelated quotes and 71% of swaps at 0.5, ranking as well as Sonnet (AUC 0.94 each) at a tiny fraction of the latency and cost. But a quarter of the real steps were flagged, we have not shown the flags are wrong, and the corruptions are synthetic. Next step: run it over the real refutations (does a Jev flag line up with a verified refutation?) and over steps a human has judged, with a threshold chosen on one half and tested on the other. If it adopts anywhere it is as an optional advisory cross-check on the judges' steps, off by default, with a notice that case text is sent to TypeSafe. |

Nothing in this folder should be taken as a reason to change the skill now.

## Reproducing

```bash
# the recorded runs live outside the repository; point at them and at a checkout that has reference/
export BAB_WORKSPACE=.../bishop-and-barrister-workspace
export BAB_MAIN=.../bishop-and-barrister          # for lookup.py
python evals/jev/build_inputs.py                  # writes results/inputs_e*.json and results/sonnet/inputs
python evals/jev/run_jev.py e1 && python evals/jev/run_jev.py e2 && python evals/jev/run_jev.py e3
python evals/jev/make_prompts.py                  # then run each results/sonnet/prompts/*.md as a sonnet agent
python evals/jev/analyse.py                       # prints the tables, writes results/summary.json and tables.md
```

The key is read from `TYPESAFE_API_KEY` or `~/.bishop-and-barrister-secrets/typesafe_api_key`, never printed or
stored. `results/call_count.json` is the running count against the cap of 2,000.
