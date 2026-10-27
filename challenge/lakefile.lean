import Lake
open Lake DSL

package «bab-challenge» where
  leanOptions := #[⟨`autoImplicit, false⟩]

/-- The challenge core: types, the state machines, replay, the checks and the theorems. -/
@[default_target]
lean_lib Challenge where
  globs := #[.andSubmodules `Challenge]

/-- Fails the build if any of the theorems is missing or rests on `sorry`. -/
@[default_target]
lean_lib Audit

/-- The command-line tool the Python wrapper runs: JSON on stdin, JSON on stdout. -/
@[default_target]
lean_exe «bab-challenge» where
  root := `Main

/-- Example event sequences for every path through both machines; run by `lake test`. -/
@[test_driver]
lean_exe tests where
  root := `Tests
