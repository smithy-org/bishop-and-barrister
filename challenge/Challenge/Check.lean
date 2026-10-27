import Challenge.Types

/-!
# Structural checks of derivations

Every premise points to a fact or an earlier step (so there are no cycles and no dangling references), every
step has a pinned source or is labelled an assumption, and a refutation attacks a step that exists. Whether a
quote matches the rule's text is a data check, made by `challenge.py verify` before the verifier's report.
Each check returns every problem it finds, so one pass reports them all; an empty list means it passes.

## Main definitions

* `checkCase`, `checkRefutation`, `checkFiling`: the derivations and filings.
* `checkVote`, `checkReport`, `checkAnswer`: votes, the verifier's reports and the user's answers.
* `isGap`: whether a case fills a gap.
-/

namespace Challenge

/-- Whether a string is 64 lowercase hex digits, as a SHA-256 is written. -/
def isHex64 (s : String) : Bool :=
  s.length == 64 && s.all (fun ch => ch.isDigit || (ch.toNat ≥ 97 && ch.toNat ≤ 102))

/-- A source names its document, its place in it and the quote, and is pinned by a SHA-256. -/
def checkSource (label : String) (s : Source) : List String :=
  (if s.doc.isEmpty then [s!"{label}: the source needs a \"doc\""] else []) ++
  (if s.ref.isEmpty then [s!"{label}: the source needs a \"ref\""] else []) ++
  (if s.excerpt.isEmpty then [s!"{label}: the source needs the quoted \"excerpt\""] else []) ++
  (if isHex64 s.textSha256 then [] else [s!"{label}: the source isn't pinned (\"text_sha256\")"])

/-- A premise points to a fact, an earlier step, or a step of the case: `none` if it does, or else the problem. -/
def checkPremise (label : String) (facts caseSteps seen : List Nat) : Ref → Option String
  | .fact n => if facts.contains n then none else some s!"{label}: premise F{n} isn't a fact of the case"
  | .step n => if seen.contains n then none else some s!"{label}: premise S{n} isn't an earlier step"
  | .caseStep n =>
    if caseSteps.contains n then none else some s!"{label}: premise C{n} isn't a step of the case"

/-- A case that fills a gap says so in `challenges`: "none: a gap". -/
def isGap (challenges : String) : Bool := challenges.trim.toLower.startsWith "none"

/-- A step quotes a pinned source, or is labelled an assumption, or is a stipulation where one is allowed. Never two
of these. -/
def checkStepSource (label : String) (allowStip : Bool) (src : Option Source) (assumption stip : Bool) :
    List String :=
  if stip then
    (if allowStip then [] else [s!"{label}: only the case's own derivation can stipulate"]) ++
    (if src.isSome then [s!"{label}: a stipulation is the rule's new content; it doesn't quote a source"] else []) ++
    (if assumption then [s!"{label}: a step is a stipulation or an assumption, not both"] else [])
  else match src, assumption with
    | none, false => [s!"{label}: no source; quote one, or label the step an assumption"]
    | some _, true => [s!"{label}: an assumption can't also quote a source"]
    | some s, false => checkSource label s
    | none, true => []

/-- Checks steps in order: the numbers increase, premises point back, and each step has a source and a conclusion.
`seen` holds the earlier steps' numbers and `last` the previous one. -/
def checkStepsFrom (label : String) (allowStip : Bool) (facts caseSteps : List Nat) (seen : List Nat) (last : Nat) :
    List Step → List String
  | [] => []
  | st :: rest =>
    let here := s!"{label} step {st.id}"
    (if st.id ≤ last then [s!"{here}: step numbers must increase (1, 2, 3...)"] else []) ++
    st.premises.filterMap (checkPremise here facts caseSteps seen) ++
    checkStepSource here allowStip st.source st.assumption st.stipulation ++
    (if st.conclusion.isEmpty then [s!"{here}: no conclusion"] else []) ++
    checkStepsFrom label allowStip facts caseSteps (st.id :: seen) st.id rest

/-- A derivation: `facts` are the case's fact numbers, `caseSteps` the case's step numbers (empty for the case's
own derivation, which can't cite itself with `C`). -/
def checkSteps (label : String) (allowStip : Bool) (facts caseSteps : List Nat) (steps : List Step) : List String :=
  checkStepsFrom label allowStip facts caseSteps [] 0 steps

/-- The case's fact numbers. -/
def Case.factIds (c : Case) : List Nat := c.facts.map (·.id)
/-- The case's step numbers. -/
def Case.stepIds (c : Case) : List Nat := c.steps.map (·.id)

/-- A case: facts numbered from `F1`, each with its text; a rule; what it challenges; a derivation; and stipulations
only in a gap. -/
def checkCase (c : Case) : List String :=
  (if c.factIds == List.range' 1 c.facts.length then [] else ["the facts must be numbered F1, F2, F3..."]) ++
  (if c.facts.any (·.text.isEmpty) then ["every fact needs its text"] else []) ++
  (if c.rule.isEmpty then ["the case needs the proposed rule"] else []) ++
  (if c.challenges.isEmpty then
    ["the case must name the established answer it challenges, or say \"none: a gap\""] else []) ++
  (if c.steps.isEmpty then ["the case needs a derivation"] else []) ++
  (if c.steps.any (·.stipulation) && !isGap c.challenges then
    ["stipulations are for gaps: only a case that says \"none: a gap\" can stipulate"] else []) ++
  checkSteps "case" true c.factIds [] c.steps

/-- A refutation attacks a step the case has, argues, and has a derivation that quotes at least one source. It can't
stipulate. -/
def checkRefutation (c : Case) (label : String) (r : Refutation) : List String :=
  (if c.stepIds.contains r.target then [] else [s!"{label}: attacks step {r.target}, which the case doesn't have"]) ++
  (if r.argument.isEmpty then [s!"{label}: no argument"] else []) ++
  (if r.steps.isEmpty then [s!"{label}: no derivation"] else []) ++
  (if r.steps.any (·.source.isSome) then [] else
    [s!"{label}: no evidence; a refutation needs at least one step that quotes a source"]) ++
  checkSteps label false c.factIds c.stepIds r.steps

/-- Checks a filing's refutations, numbering them from `i`. -/
def checkRefutationsFrom (c : Case) (judge : Nat) : Nat → List Refutation → List String
  | _, [] => []
  | i, r :: rest =>
    checkRefutation c s!"judge {judge}'s refutation {i}" r ++ checkRefutationsFrom c judge (i + 1) rest

/-- A filing has refutations, or a concession with its reasons and evidence. -/
def checkFiling (c : Case) (f : Filing) : List String :=
  (if f.refutations.isEmpty then
    (if f.concedes.isEmpty then ["a filing needs refutations, or says what the judge concedes and why"] else []) ++
    (if f.concedeEvidence.isEmpty then
      [s!"judge {f.judge}'s concession needs evidence: the pinned sources the judge checked"] else []) ++
    f.concedeEvidence.flatMap (checkSource s!"judge {f.judge}'s concession")
  else []) ++
  checkRefutationsFrom c f.judge 1 f.refutations

/-- A vote is a position with its reasons and the evidence it rests on. -/
def checkVote (v : Vote) : List String :=
  (if v.reason.isEmpty then
    ["a vote needs its reasoning: the step that settled it, or the refutation or missing evidence that defeats it"]
  else []) ++
  (if v.evidence.isEmpty then ["a vote needs evidence: the pinned sources it relied on or checked"] else []) ++
  v.evidence.flatMap (checkSource "the vote")

/-- The conclusions of the case's stipulations: the rule's new content. -/
def Case.stipulations (c : Case) : List String := (c.steps.filter (·.stipulation)).map (·.conclusion)

/-- A draft of the Opinion of the Court: the holding is the case's rule, the reasoning is sourced step by step, and
the stipulations are the case's own, all of them and no others (the judges join exactly what they settled on). -/
def checkOpinion (c : Case) (revision : Nat) (o : Opinion) : List String :=
  (if o.revision = revision then [] else [s!"this is revision {revision} of the opinion, not revision {o.revision}"]) ++
  (if o.holding == c.rule then [] else ["the holding must be the case's rule, word for word"]) ++
  (if o.steps.isEmpty then ["the opinion needs its reasoning: the steps, each quoting a pinned source"] else []) ++
  ((o.steps.filter (fun st => !(st.source.isSome || st.stipulation))).map fun st =>
    s!"the opinion's step {st.id}: an assumption can't support a rule; quote a source") ++
  (((o.steps.filter (·.stipulation)).map (·.conclusion)).filter (fun t => !c.stipulations.contains t)).map
    (fun t => s!"the opinion stipulates \"{t}\", which the case doesn't: the opinion can't add to the rule") ++
  (c.stipulations.filter (fun t => !((o.steps.filter (·.stipulation)).map (·.conclusion)).contains t)).map
    (fun t => s!"the opinion leaves out the stipulation \"{t}\": it must state everything the judges accepted") ++
  checkSteps "the opinion" true c.factIds [] o.steps

/-- A response is a position, like a vote: its reasoning and the evidence it rests on. -/
def checkResponse (revision : Nat) (r : Response) : List String :=
  (if r.revision = revision then [] else [s!"this is revision {revision} of the opinion, not revision {r.revision}"]) ++
  (if r.reason.isEmpty then
    ["a response needs its reasoning: why the judge joins, concurs in the judgment only, or dissents"] else []) ++
  (if r.evidence.isEmpty then ["a response needs evidence: the pinned sources it relied on or checked"] else []) ++
  r.evidence.flatMap (checkSource "the response")

/-- The slot names a refutation some judge filed this round. -/
def slotValid (fs : List Filing) (sl : Slot) : Bool :=
  fs.any (fun f => f.judge == sl.judge && 1 ≤ sl.index && sl.index ≤ f.refutations.length)

/-- Every slot names a refutation filed this round. -/
def checkSlots (fs : List Filing) (slots : List Slot) : List String :=
  (slots.filter (fun sl => !slotValid fs sl)).map fun sl =>
    s!"judge {sl.judge} filed no refutation {sl.index} this round"

/-- A report is for this round and stage, and its standing refutations were filed this round. -/
def checkReport (n : Nat) (stage : Stage) (fs : List Filing) (r : Report) : List String :=
  (if r.round = n then [] else [s!"this is round {n}, not round {r.round}"]) ++
  (if r.stage = stage then [] else
    [match stage with
      | .attack => "the verifier checks the judges' refutations now (stage \"attack\")"
      | .answers => "the verifier checks the user's answers now (stage \"answers\")"]) ++
  checkSlots fs r.standing

/-- A reply has the user's words. A fix needs the revised case, and a rebuttal a derivation. -/
def checkReply (c : Case) (hasRevision : Bool) (rp : Reply) : List String :=
  let label := s!"the reply to judge {rp.slot.judge}'s refutation {rp.slot.index}"
  (if rp.words.isEmpty then [s!"{label}: needs the user's words"] else []) ++
  match rp.kind with
  | .concede => []
  | .fix => if hasRevision then [] else [s!"{label}: a fix needs the revised case"]
  | .rebut =>
    if rp.steps.isEmpty then [s!"{label}: a rebuttal needs a derivation"]
    else checkSteps label false c.factIds c.stepIds rp.steps

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
