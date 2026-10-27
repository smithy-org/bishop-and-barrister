import Lean
import Challenge.Theorems

/-!
# The proof audit

`lake build` builds this file, and it fails the build if any guarantee is missing or isn't proved: each theorem
named below must exist and may rest only on Lean's three standard axioms, never on `sorryAx`.
-/

open Lean Elab Command

/-- `#assert_proved` checks that each named theorem rests only on `propext`, `Classical.choice` and `Quot.sound`,
and fails the build if one doesn't. -/
elab "#assert_proved " ids:ident* : command => do
  for id in ids do
    let name ← resolveGlobalConstNoOverload id
    let axioms ← Lean.collectAxioms name
    for ax in axioms do
      unless [``propext, ``Classical.choice, ``Quot.sound].contains ax do
        throwError m!"{name} isn't proved: it depends on {ax}"
    logInfo m!"{name}: proved"

#assert_proved
  Challenge.no_unearned_rule
  Challenge.stipulations_only_in_gaps
  Challenge.introduced_has_opinion
  Challenge.determinism
  Challenge.terminal_final_introduced
  Challenge.terminal_final_withdrawn
  Challenge.terminal_final_house_rule
  Challenge.refuted_only_to_house_rule
  Challenge.blindness
  Challenge.progress
  Challenge.forks_caught
