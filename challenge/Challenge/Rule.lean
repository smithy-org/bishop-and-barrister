/-!
# The rule state machine

A rule introduced by a challenge lives for years. It goes stale when a source it relied on changes, and then
has to win its challenge again against the new text.
-/

namespace Challenge

inductive RuleState where
  | current
  | stale
  | reopened
  | superseded
  | retired
  deriving Repr, DecidableEq

inductive RuleEvent where
  /-- `recheck` found that a cited source or the Oracle text changed. -/
  | sourceChanged
  /-- A later challenge introduced a rule that replaces it. -/
  | replaced
  /-- Its challenge opened again against the new text. -/
  | challengeReopened
  | challengeIntroduced
  | challengeRefuted
  deriving Repr, DecidableEq

def ruleStep : RuleState → RuleEvent → Option RuleState
  | .current, .sourceChanged => some .stale
  | .current, .replaced => some .superseded
  | .stale, .challengeReopened => some .reopened
  | .stale, .sourceChanged => some .stale
  | .reopened, .sourceChanged => some .reopened
  | .reopened, .challengeIntroduced => some .current
  | .reopened, .challengeRefuted => some .retired
  | _, _ => none

theorem rule_final {s : RuleState} (h : s = .superseded ∨ s = .retired) (e : RuleEvent) :
    ruleStep s e = none := by
  rcases h with rfl | rfl <;> cases e <;> rfl

def RuleState.name : RuleState → String
  | .current => "current"
  | .stale => "stale"
  | .reopened => "reopened"
  | .superseded => "superseded"
  | .retired => "retired"

def parseRuleState : String → Option RuleState
  | "current" => some .current
  | "stale" => some .stale
  | "reopened" => some .reopened
  | "superseded" => some .superseded
  | "retired" => some .retired
  | _ => none

def parseRuleEvent : String → Option RuleEvent
  | "source-changed" => some .sourceChanged
  | "replaced" => some .replaced
  | "challenge-reopened" => some .challengeReopened
  | "challenge-introduced" => some .challengeIntroduced
  | "challenge-refuted" => some .challengeRefuted
  | _ => none

end Challenge
