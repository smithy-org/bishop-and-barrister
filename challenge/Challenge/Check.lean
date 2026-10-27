import Challenge.Types

/-!
# Structural checks of derivations

Every premise points to a fact or an earlier step (so there are no cycles and no dangling references), every
step has a pinned source or is labelled an assumption, and a refutation attacks a step that exists. Whether a
quote matches the rule's text is a data check, made by `challenge.py verify` before the verifier's report.
Each check returns every problem it finds, so one pass reports them all; an empty list means it passes.
-/

namespace Challenge

def isHex64 (s : String) : Bool :=
  s.length == 64 && s.all (fun ch => ch.isDigit || (ch.toNat ≥ 97 && ch.toNat ≤ 102))

def checkSource (label : String) (s : Source) : List String :=
  (if s.doc.isEmpty then [s!"{label}: the source needs a \"doc\""] else []) ++
  (if s.ref.isEmpty then [s!"{label}: the source needs a \"ref\""] else []) ++
  (if s.excerpt.isEmpty then [s!"{label}: the source needs the quoted \"excerpt\""] else []) ++
  (if isHex64 s.textSha256 then [] else [s!"{label}: the source isn't pinned (\"text_sha256\")"])

def checkPremise (label : String) (facts caseSteps seen : List Nat) : Ref → Option String
  | .fact n => if facts.contains n then none else some s!"{label}: premise F{n} isn't a fact of the case"
  | .step n => if seen.contains n then none else some s!"{label}: premise S{n} isn't an earlier step"
  | .caseStep n =>
    if caseSteps.contains n then none else some s!"{label}: premise C{n} isn't a step of the case"

def checkStepSource (label : String) : Option Source → Bool → List String
  | none, false => [s!"{label}: no source; quote one, or label the step an assumption"]
  | some _, true => [s!"{label}: an assumption can't also quote a source"]
  | some src, false => checkSource label src
  | none, true => []

def checkStepsFrom (label : String) (facts caseSteps : List Nat) (seen : List Nat) (last : Nat) :
    List Step → List String
  | [] => []
  | st :: rest =>
    let here := s!"{label} step {st.id}"
    (if st.id ≤ last then [s!"{here}: step numbers must increase (1, 2, 3...)"] else []) ++
    st.premises.filterMap (checkPremise here facts caseSteps seen) ++
    checkStepSource here st.source st.assumption ++
    (if st.conclusion.isEmpty then [s!"{here}: no conclusion"] else []) ++
    checkStepsFrom label facts caseSteps (st.id :: seen) st.id rest

/-- A derivation: `facts` are the case's fact numbers, `caseSteps` the case's step numbers (empty for the case's
own derivation, which can't cite itself with `C`). -/
def checkSteps (label : String) (facts caseSteps : List Nat) (steps : List Step) : List String :=
  checkStepsFrom label facts caseSteps [] 0 steps

def Case.factIds (c : Case) : List Nat := c.facts.map (·.id)
def Case.stepIds (c : Case) : List Nat := c.steps.map (·.id)

def checkCase (c : Case) : List String :=
  (if c.factIds == List.range' 1 c.facts.length then [] else ["the facts must be numbered F1, F2, F3..."]) ++
  (if c.facts.any (·.text.isEmpty) then ["every fact needs its text"] else []) ++
  (if c.rule.isEmpty then ["the case needs the proposed rule"] else []) ++
  (if c.challenges.isEmpty then
    ["the case must name the established answer it challenges, or say \"none: a gap\""] else []) ++
  (if c.steps.isEmpty then ["the case needs a derivation"] else []) ++
  checkSteps "case" c.factIds [] c.steps

def checkRefutation (c : Case) (label : String) (r : Refutation) : List String :=
  (if c.stepIds.contains r.target then [] else [s!"{label}: attacks step {r.target}, which the case doesn't have"]) ++
  (if r.argument.isEmpty then [s!"{label}: no argument"] else []) ++
  (if r.steps.isEmpty then [s!"{label}: no derivation"] else []) ++
  (if r.steps.any (·.source.isSome) then [] else
    [s!"{label}: no evidence; a refutation needs at least one step that quotes a source"]) ++
  checkSteps label c.factIds c.stepIds r.steps

def checkRefutationsFrom (c : Case) (judge : Nat) : Nat → List Refutation → List String
  | _, [] => []
  | i, r :: rest =>
    checkRefutation c s!"judge {judge}'s refutation {i}" r ++ checkRefutationsFrom c judge (i + 1) rest

def checkFiling (c : Case) (f : Filing) : List String :=
  (if f.refutations.isEmpty && f.concedes.isEmpty then
    ["a filing needs refutations, or says what the judge concedes"] else []) ++
  checkRefutationsFrom c f.judge 1 f.refutations

/-- The slot names a refutation some judge filed this round. -/
def slotValid (fs : List Filing) (sl : Slot) : Bool :=
  fs.any (fun f => f.judge == sl.judge && 1 ≤ sl.index && sl.index ≤ f.refutations.length)

def checkSlots (fs : List Filing) (slots : List Slot) : List String :=
  (slots.filter (fun sl => !slotValid fs sl)).map fun sl =>
    s!"judge {sl.judge} filed no refutation {sl.index} this round"

def checkReport (n : Nat) (stage : Stage) (fs : List Filing) (r : Report) : List String :=
  (if r.round = n then [] else [s!"this is round {n}, not round {r.round}"]) ++
  (if r.stage = stage then [] else
    [match stage with
      | .attack => "the verifier checks the judges' refutations now (stage \"attack\")"
      | .answers => "the verifier checks the user's answers now (stage \"answers\")"]) ++
  checkSlots fs r.standing

def checkReply (c : Case) (hasRevision : Bool) (rp : Reply) : List String :=
  let label := s!"the reply to judge {rp.slot.judge}'s refutation {rp.slot.index}"
  (if rp.words.isEmpty then [s!"{label}: needs the user's words"] else []) ++
  match rp.kind with
  | .concede => []
  | .fix => if hasRevision then [] else [s!"{label}: a fix needs the revised case"]
  | .rebut =>
    if rp.steps.isEmpty then [s!"{label}: a rebuttal needs a derivation"]
    else checkSteps label c.factIds c.stepIds rp.steps

/-- Every standing refutation needs a reply, every reply a refutation filed this round. -/
def checkAnswer (n : Nat) (c : Case) (fs : List Filing) (r : Report) (a : Answer) : List String :=
  (if a.round = n then [] else [s!"this is round {n}, not round {a.round}"]) ++
  (if a.words.isEmpty then ["the answer needs the user's words"] else []) ++
  ((r.standing.filter (fun sl => !a.replies.any (fun rp => rp.slot == sl))).map fun sl =>
    s!"judge {sl.judge}'s refutation {sl.index} stands and has no reply") ++
  checkSlots fs (a.replies.map (·.slot)) ++
  a.replies.flatMap (checkReply c a.revised.isSome) ++
  match a.revised with
  | some c' => checkCase c'
  | none => []

end Challenge
