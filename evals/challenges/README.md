# Challenge evals

Ten challenges a user might put forward, each with a known outcome, to check that the panel in `CHALLENGE.md`
earns its cost (plan 029). Each one is run three ways, and all three are graded the same way.

| Case | Expected | What it tests |
| --- | --- | --- |
| `urborg-still-swamps` | refuted | level 1 text: dependency (CR 613.8) and Urborg's ruling |
| `deathtouch-trample-full-toughness` | refuted | level 1 text: CR 702.2c with 702.19b |
| `humility-always-wins` | refuted | level 1 text: Humility's ruling on Opalescence (timestamps decide) |
| `summoning-sickness-all-permanents` | refuted | a counterexample: CR 302.6 is about creatures only |
| `extra-card-regular-rel-game-loss` | refuted | the tournament documents: JAR section 4 |
| `forged-quote` | refuted | the verifier: a quote that isn't in CR 702.19b is refused, leaving an assumption |
| `multiplayer-match-who-chooses` | introduced | a real gap: CR 103.1's "the loser" with several losers |
| `multiplayer-match-ends-at-time` | introduced | a real gap: MTR 2.1 is written for two players |
| `magar-aftermath` | open | both readings derivable (CR 707.12, 707.14, 702.127a) |
| `commander-tax-free-first-recast` | house-rule | refuted by CR 903.8, then kept as a house rule |

Each case has `prompt.md` (what the user says), `user.md` (how the simulated user argues), `case.yaml` (the
expected state and outcome, and what should decide it) and `graders/`.

## The three arms

Run each case in a fresh session with the skill installed and its own empty record
(`BISHOP_AND_BARRISTER_HOME` set to a new folder, then `judge.py build`). Count the tokens and time of the whole
run, every subagent included.

1. **The panel.** The orchestrator follows `CHALLENGE.md` for the prompt, in Claude Code, with seven judge
   subagents per round. A separate subagent plays the user from `user.md`, seeing only what the user would
   (the brief, the verified refutations, the outcome). When the challenge settles or stays open, grade it:

   ```bash
   python evals/challenges/grade.py <case> --home <that run's record>
   ```

   Graders 01 and 02 come from `grade.py`; 03 and 04 are graded by an LLM from the final report to the user,
   as in the other evals.

2. **A single agent.** One agent with the skill, and `user.md` as the user's position, is asked:

   > The user wants this introduced as a rule: {prompt}. Using the skill's sources, decide whether it should be
   > introduced, refuted (the official sources settle it otherwise) or left open (no source settles it).
   > Start your answer with one word, introduced, refuted or open, then give the deciding sources.
   > If it's refuted but the user wants it anyway, say it can only be a house rule.

3. **Majority of three.** Three independent runs of arm 2, then the verdict most of them gave (with no majority,
   the verdict is open). Their tokens are added together.

For arms 2 and 3, grader 01 is the verdict word (house-rule counts as refuted plus the house-rule remark),
grader 02 is whether every source it quotes exists and says what it claims, and 03 and 04 are graded as in
arm 1.

## What to compare

- The right outcome, per arm, out of 10. Separately, the two gaps and Magar, where a single answer is most
  tempted to settle what the sources leave open.
- Refutations filed, verified and dropped by the verifier (arm 1). A dropped refutation is one the judges got
  wrong.
- Tokens and time per case. The panel costs several times a single answer; it should earn that on the cases
  where a single answer is wrong.

Results go in `BASELINE.md` under a new "Challenges" heading, with the full outputs kept outside the
repository, as for the other evals.
