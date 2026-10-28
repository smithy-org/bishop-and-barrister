import Challenge.Sha256
import Challenge.Types
import Challenge.Check
import Challenge.Machine
import Challenge.Chain
import Challenge.Rule
import Challenge.Parse
import Challenge.Api

/-!
# The challenge core

Bishop & Barrister's challenge machine: how a user's challenge to an established rules answer is heard by a panel
of five judges, and when it may introduce a rule. Importing `Challenge` brings in every part:

* `Challenge.Sha256`: SHA-256, for the hash chain.
* `Challenge.Types`: the shapes of a challenge and its events.
* `Challenge.Check`: the structural checks of derivations, filings, votes, reports and answers.
* `Challenge.Machine`: the challenge state machine.
* `Challenge.Chain`: the hash chain, replay, and what each judge may see.
* `Challenge.Rule`: the state machine of an introduced rule.
* `Challenge.Parse`: reading event files.
* `Challenge.Api`: the JSON replies of the `bab-challenge` tool.

The six guarantees are proved in `Challenge.Theorems`.
-/

/-- Temporary probe: an unused variable, to check that `lake build --wfail` fails. -/
def wfailProbe (x : Nat) : Nat := 0
