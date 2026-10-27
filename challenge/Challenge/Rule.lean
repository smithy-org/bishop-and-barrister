/-!
# The rule state machine

A rule introduced by a challenge lives for years. It goes stale when a source it relied on changes, and then
has to win its challenge again against the new text.

## Main definitions

* `RuleState`, `RuleEvent`: where a rule stands and what can happen to it.
* `ruleStep`: the transition table.
* `rule_final`: a superseded or retired rule takes no event.
-/

namespace Challenge

/-- Where an introduced rule stands. -/
inductive RuleState where
  /-- In force: its sources still read as it cited them. -/
  | current
  /-- A source it relied on changed; its challenge has to be heard again. -/
  | stale
  /-- Its challenge is being heard again against the new text. -/
  | reopened
  /-- A later rule replaced it. This is final. -/
  | superseded
  /-- Its reopened challenge was refuted. This is final. -/
  | retired
  deriving Repr, DecidableEq

/-- What can happen to an introduced rule. -/
inductive RuleEvent where
  /-- `recheck` found that a cited source or the Oracle text changed. -/
  | sourceChanged
  /-- A later challenge introduced a rule that replaces it. -/
  | replaced
  /-- Its challenge opened again against the new text. -/
  | challengeReopened
  /-- The reopened challenge introduced the rule again. -/
  | challengeIntroduced
  /-- The reopened challenge was refuted. -/
  | challengeRefuted
  deriving Repr, DecidableEq

/-- The transition table: the rule's next state, or `none` if the event isn't allowed in that state. -/
def ruleStep : RuleState → RuleEvent → Option RuleState
  | .current, .sourceChanged => some .stale
  | .current, .replaced => some .superseded
  | .stale, .challengeReopened => some .reopened
  | .stale, .sourceChanged => some .stale
  | .reopened, .sourceChanged => some .reopened
  | .reopened, .challengeIntroduced => some .current
  | .reopened, .challengeRefuted => some .retired
  | _, _ => none

/-- Guarantee 3, terminal states are final, for the rule machine. No event moves a superseded or retired rule, so
once a rule is gone it can't quietly come back. -/
theorem rule_final {s : RuleState} (h : s = .superseded ∨ s = .retired) (e : RuleEvent) :
    ruleStep s e = none := by
  rcases h with rfl | rfl <;> cases e <;> rfl

/-- The state's name, as the JSON interface writes it. -/
def RuleState.name : RuleState → String
  | .current => "current"
  | .stale => "stale"
  | .reopened => "reopened"
  | .superseded => "superseded"
  | .retired => "retired"

/-- Reads a rule state's name; `none` if it isn't one. -/
def parseRuleState : String → Option RuleState
  | "current" => some .current
  | "stale" => some .stale
  | "reopened" => some .reopened
  | "superseded" => some .superseded
  | "retired" => some .retired
  | _ => none

/-- Reads a rule event's name, such as `source-changed`; `none` if it isn't one. -/
def parseRuleEvent : String → Option RuleEvent
  | "source-changed" => some .sourceChanged
  | "replaced" => some .replaced
  | "challenge-reopened" => some .challengeReopened
  | "challenge-introduced" => some .challengeIntroduced
  | "challenge-refuted" => some .challengeRefuted
  | _ => none

end Challenge
