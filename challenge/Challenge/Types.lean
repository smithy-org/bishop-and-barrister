/-!
# The shapes of a challenge

A case and every refutation use one proof standard (plan 029): numbered facts, the proposed rule, and a
derivation whose every step names its premises and quotes one pinned source, or is labelled an assumption, or, in a
case that fills a gap, is a stipulation: the rule's own new content. A rule the judges accept is written up as an
Opinion of the Court, in the same shape, which every judge joins, concurs in, or dissents from.
-/

namespace Challenge

/-- The panel has five judges, numbered 1 to 5. -/
def panelSize : Nat := 5

/-- After this many attack rounds the judges settle the case, however it stands. -/
def roundCap : Nat := 3

/-- A rule is introduced only if every judge is convinced; a case is refused when this many are not. -/
def refuseNeeds : Nat := 3

/-- A draft opinion that doesn't win five joins is revised by its author this many times before the case stays open. -/
def opinionRevisions : Nat := 2

def judges : List Nat := List.range' 1 panelSize

/-- A premise: a fact of the case (`F1`), an earlier step of the same derivation (`S2`), or, inside a
refutation or a rebuttal, a step of the case (`C3`). -/
inductive Ref where
  | fact (n : Nat)
  | step (n : Nat)
  | caseStep (n : Nat)
  deriving Repr, DecidableEq

/-- A quoted source, pinned by the SHA-256 of the text it quotes. `doc` is `cr`, `oracle`, `ruling`, `mtr`,
`ipg`, `jar` or `format`, as in `judge.py`'s citations. -/
structure Source where
  doc : String
  ref : String
  excerpt : String
  textSha256 : String
  deriving Repr

structure Step where
  id : Nat
  premises : List Ref
  source : Option Source
  assumption : Bool
  /-- The rule's own new content, in a case that fills a gap. It quotes no source: it is what the judges vote on. -/
  stipulation : Bool
  conclusion : String
  deriving Repr

structure Fact where
  id : Nat
  text : String
  deriving Repr

/-- The case for a rule, in the proof standard. `challenges` names the established answer it challenges, or
says "none: a gap". -/
structure Case where
  facts : List Fact
  openQuestions : List String
  rule : String
  appliesWhen : List String
  challenges : String
  steps : List Step
  deriving Repr

/-- What a refutation says is wrong with the step it attacks. -/
inductive Ground where
  | notApplicable
  | overridden
  | misread
  | wrongFact
  | missingFact
  | counterexample
  deriving Repr, DecidableEq

structure Refutation where
  target : Nat
  ground : Ground
  argument : String
  steps : List Step
  deriving Repr

/-- One judge's filing in an attack round: refutations, or none and a concession. -/
structure Filing where
  judge : Nat
  round : Nat
  refutations : List Refutation
  concedes : String
  /-- What a concession rests on: the pinned sources the judge checked. -/
  concedeEvidence : List Source
  deriving Repr

/-- A refutation, by its judge and its number (1, 2...) in that judge's filing. -/
structure Slot where
  judge : Nat
  index : Nat
  deriving Repr, DecidableEq

inductive Stage where
  | attack
  | answers
  deriving Repr, DecidableEq

/-- The verifier's report: whether the case passes (every citation checks, no unsupported step), whether it
contradicts a level 1 source, and which verified refutations still stand. -/
structure Report where
  round : Nat
  stage : Stage
  passed : Bool
  level1Conflict : Bool
  standing : List Slot
  deriving Repr

inductive ReplyKind where
  | concede
  | fix
  | rebut
  deriving Repr, DecidableEq

structure Reply where
  slot : Slot
  kind : ReplyKind
  words : String
  steps : List Step
  deriving Repr

/-- The user's answer to a round's verified refutations, with the revised case if they fixed it. -/
structure Answer where
  round : Nat
  replies : List Reply
  revised : Option Case
  words : String
  deriving Repr

structure Vote where
  judge : Nat
  convinced : Bool
  reason : String
  /-- What the position rests on: the pinned sources relied on or checked. Never empty. -/
  evidence : List Source
  deriving Repr

/-- A judge's latest look at the case: the version it saw (the position of the event that set that case), and,
if the judge conceded, the concession as its settled position. A refutation leaves no position. -/
structure Look where
  judge : Nat
  version : Nat
  position : Option Vote
  deriving Repr

/-- How a judge answers the draft opinion: join it as written, concur in the judgment only (the rule is right,
but for other reasons), or dissent (not convinced). -/
inductive Stance where
  | join
  | concur
  | dissent
  deriving Repr, DecidableEq

/-- The Opinion of the Court: the holding (the rule's text) and its reasoning, with the case's stipulations.
`revision` counts the author's revisions (0 for the first draft). -/
structure Opinion where
  author : Nat
  revision : Nat
  holding : String
  steps : List Step
  deriving Repr

/-- A judge's answer to the draft: a position, so it carries reasoning and evidence. -/
structure Response where
  judge : Nat
  revision : Nat
  stance : Stance
  reason : String
  evidence : List Source
  deriving Repr

/-- `singleAgent` is claude.ai's fallback, where one agent plays every judge: it can open and refute a
challenge but never introduce a rule, because its judges aren't independent. -/
inductive Panel where
  | independent
  | singleAgent
  deriving Repr, DecidableEq

inductive Actor where
  | user
  | clerk
  | verifier
  | judge (k : Nat)
  deriving Repr, DecidableEq

inductive Event where
  | start (statement : String) (panel : Panel)
  | brief (c : Case)
  | edit (c : Case) (words : String)
  | confirm (words : String)
  | file (f : Filing)
  | report (r : Report)
  | answer (a : Answer)
  | vote (v : Vote)
  | opinion (o : Opinion)
  | respond (r : Response)
  | withdraw (words : String)
  | houseRule (words : String)
  | reopen (c : Case) (panel : Panel) (words : String)
  deriving Repr

/-- One event file: its own hash, the hash of the event before it (none for the opening event), its place in
the chain, who wrote it from which device and when, and the event. -/
structure Entry where
  hash : String
  prev : Option String
  seq : Nat
  actor : Actor
  device : String
  time : String
  event : Event
  deriving Repr

end Challenge
