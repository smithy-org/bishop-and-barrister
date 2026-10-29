/-!
# The shapes of a challenge

A case and every refutation use one proof standard (see CHALLENGE.md): numbered facts, the proposed rule, and a
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

/-- The judges' numbers: 1 to 5. -/
def judges : List Nat := List.range' 1 panelSize

/-- A premise: a fact of the case (`F1`), an earlier step of the same derivation (`S2`), or, inside a
refutation or a rebuttal, a step of the case (`C3`). -/
inductive Ref where
  /-- `F<n>`: fact `n` of the case. -/
  | fact (n : Nat)
  /-- `S<n>`: an earlier step `n` of the same derivation. -/
  | step (n : Nat)
  /-- `C<n>`: step `n` of the case, cited from a refutation or a rebuttal. -/
  | caseStep (n : Nat)
  deriving Repr, DecidableEq

/-- A quoted source, pinned by the SHA-256 of the text it quotes. `doc` is `cr`, `oracle`, `ruling`, `mtr`,
`ipg`, `jar` or `format`, as in `judge.py`'s citations. -/
structure Source where
  /-- Which document it quotes: `cr`, `oracle`, `ruling`, `mtr`, `ipg`, `jar` or `format`. -/
  doc : String
  /-- Where in that document, such as a rule number. -/
  ref : String
  /-- The quoted text. -/
  excerpt : String
  /-- The SHA-256 of the text it quotes, in hex. A changed source no longer matches it. -/
  textSha256 : String
  deriving Repr

/-- One step of a derivation: what it rests on, what supports it, and what it concludes. -/
structure Step where
  /-- The step's number: 1, 2, 3, increasing. -/
  id : Nat
  /-- The facts and earlier steps it rests on. -/
  premises : List Ref
  /-- The pinned source it quotes, if it quotes one. -/
  source : Option Source
  /-- The step is labelled an assumption: it quotes no source, so a case resting on it is unproven. -/
  assumption : Bool
  /-- The rule's own new content, in a case that fills a gap. It quotes no source: it is what the judges vote on. -/
  stipulation : Bool
  /-- What the step concludes. -/
  conclusion : String
  deriving Repr

/-- A numbered fact of the case. -/
structure Fact where
  /-- The fact's number: `F1` is 1. -/
  id : Nat
  /-- What the fact says. -/
  text : String
  deriving Repr

/-- The case for a rule, in the proof standard. `challenges` names the established answer it challenges, or
says "none: a gap". -/
structure Case where
  /-- The facts, numbered from `F1`. -/
  facts : List Fact
  /-- Questions the facts leave open. -/
  openQuestions : List String
  /-- The proposed rule, in words. -/
  rule : String
  /-- The situations the rule applies to. -/
  appliesWhen : List String
  /-- The established answer it challenges, or "none: a gap". -/
  challenges : String
  /-- The derivation of the rule. -/
  steps : List Step
  deriving Repr

/-- What a refutation says is wrong with the step it attacks. -/
inductive Ground where
  /-- The cited source doesn't apply to these facts. -/
  | notApplicable
  /-- Another source overrides the one cited. -/
  | overridden
  /-- The step misreads its source. -/
  | misread
  /-- The step rests on a fact that isn't so. -/
  | wrongFact
  /-- The step leaves out a fact that changes the answer. -/
  | missingFact
  /-- A situation the rule covers where it gives the wrong answer. -/
  | counterexample
  deriving Repr, DecidableEq

/-- A judge's attack on one step of the case, with its own derivation. -/
structure Refutation where
  /-- The number of the case's step it attacks. -/
  target : Nat
  /-- What it says is wrong with that step. -/
  ground : Ground
  /-- The argument, in words. -/
  argument : String
  /-- The refutation's derivation. At least one step quotes a source. -/
  steps : List Step
  deriving Repr

/-- One judge's filing in an attack round: refutations, or none and a concession. -/
structure Filing where
  /-- The judge who filed it. -/
  judge : Nat
  /-- The attack round it is filed in. -/
  round : Nat
  /-- The judge's refutations, if any. -/
  refutations : List Refutation
  /-- What the judge concedes and why, when it files no refutation. -/
  concedes : String
  /-- What a concession rests on: the pinned sources the judge checked. -/
  concedeEvidence : List Source
  deriving Repr

/-- A refutation, by its judge and its number (1, 2...) in that judge's filing. -/
structure Slot where
  /-- The judge who filed the refutation. -/
  judge : Nat
  /-- Its number in that judge's filing, from 1. -/
  index : Nat
  deriving Repr, DecidableEq

/-- Which half of a round the verifier is checking. -/
inductive Stage where
  /-- The judges' refutations. -/
  | attack
  /-- The user's answers to the refutations that stood. -/
  | answers
  deriving Repr, DecidableEq

/-- The verifier's report: whether the case passes (every citation checks, no unsupported step), whether it
contradicts a level 1 source, and which verified refutations still stand. -/
structure Report where
  /-- The round it reports on. -/
  round : Nat
  /-- Whether it checks the refutations or the user's answers. -/
  stage : Stage
  /-- Every citation of the case checks and no step is unsupported. -/
  passed : Bool
  /-- The case contradicts a level 1 source. -/
  level1Conflict : Bool
  /-- The verified refutations that still stand. -/
  standing : List Slot
  /-- The verified refutations the user answered with a rebuttal whose sources check. They no longer stand, but
  whether the rebuttal actually answers them is the judges' call: if three or more stay unconvinced, they refute. -/
  rebutted : List Slot := []
  deriving Repr

/-- How the user answers one verified refutation. -/
inductive ReplyKind where
  /-- The user accepts the refutation. -/
  | concede
  /-- The user revises the case to answer it. -/
  | fix
  /-- The user argues back, with a derivation. -/
  | rebut
  deriving Repr, DecidableEq

/-- The user's reply to one verified refutation. -/
structure Reply where
  /-- The refutation it replies to. -/
  slot : Slot
  /-- Concede, fix or rebut. -/
  kind : ReplyKind
  /-- The user's own words. -/
  words : String
  /-- A rebuttal's derivation; empty otherwise. -/
  steps : List Step
  deriving Repr

/-- The user's answer to a round's verified refutations, with the revised case if they fixed it. -/
structure Answer where
  /-- The round it answers. -/
  round : Nat
  /-- One reply for each refutation that stood. -/
  replies : List Reply
  /-- The revised case, if the user fixed it. -/
  revised : Option Case
  /-- The user's own words. -/
  words : String
  deriving Repr

/-- A judge's settled position on the case: convinced or not, with its reasons and evidence. -/
structure Vote where
  /-- The judge who votes. -/
  judge : Nat
  /-- Whether the judge is convinced the case holds. -/
  convinced : Bool
  /-- The reasoning: the step that settled it, or what defeats it. -/
  reason : String
  /-- What the position rests on: the pinned sources relied on or checked. Never empty. -/
  evidence : List Source
  deriving Repr

/-- A judge's latest look at the case: the version it saw (the position of the event that set that case), and,
if the judge conceded, the concession as its settled position. A refutation leaves no position. -/
structure Look where
  /-- The judge. -/
  judge : Nat
  /-- The position of the event that set the case the judge last saw. -/
  version : Nat
  /-- The judge's settled position, if a concession gave it one. -/
  position : Option Vote
  deriving Repr

/-- How a judge answers the draft opinion: join it as written, concur in the judgment only (the rule is right,
but for other reasons), or dissent (not convinced). -/
inductive Stance where
  /-- Joins the opinion as written. -/
  | join
  /-- Agrees with the rule but not the reasons. Not a join. -/
  | concur
  /-- Isn't convinced. -/
  | dissent
  deriving Repr, DecidableEq

/-- The Opinion of the Court: the holding (the rule's text) and its reasoning, with the case's stipulations.
`revision` counts the author's revisions (0 for the first draft). -/
structure Opinion where
  /-- The judge who wrote it. -/
  author : Nat
  /-- Which revision this is: 0 for the first draft. -/
  revision : Nat
  /-- The rule, word for word as the case states it. -/
  holding : String
  /-- The reasoning, each step quoting a pinned source, with the case's stipulations. -/
  steps : List Step
  deriving Repr

/-- A judge's answer to the draft: a position, so it carries reasoning and evidence. -/
structure Response where
  /-- The judge who answers. -/
  judge : Nat
  /-- The revision of the draft it answers. -/
  revision : Nat
  /-- Join, concur or dissent. -/
  stance : Stance
  /-- Why. -/
  reason : String
  /-- The pinned sources it relied on or checked. -/
  evidence : List Source
  deriving Repr

/-- `singleAgent` is claude.ai's fallback, where one agent plays every judge: it can open and refute a
challenge but never introduce a rule, because its judges aren't independent. -/
inductive Panel where
  /-- Five independent judges. Only this panel can introduce a rule. -/
  | independent
  /-- One agent playing every judge. -/
  | singleAgent
  deriving Repr, DecidableEq

/-- Who writes an event. -/
inductive Actor where
  /-- The user who brought the challenge. -/
  | user
  /-- The clerk, who writes the brief. -/
  | clerk
  /-- The verifier, who checks citations and refutations. -/
  | verifier
  /-- Judge `k`, 1 to 5. -/
  | judge (k : Nat)
  deriving Repr, DecidableEq

/-- What an event file records. -/
inductive Event where
  /-- The user opens a challenge with a statement and a choice of panel. -/
  | start (statement : String) (panel : Panel)
  /-- The clerk writes the case up as a brief. -/
  | brief (c : Case)
  /-- The brief is corrected for the user, with the user's words. -/
  | edit (c : Case) (words : String)
  /-- The user confirms the brief, and round 1 begins. -/
  | confirm (words : String)
  /-- A judge files refutations, or concedes, in an attack round. -/
  | file (f : Filing)
  /-- The verifier reports on a round's refutations or answers. -/
  | report (r : Report)
  /-- The user answers the refutations that stood. -/
  | answer (a : Answer)
  /-- A judge settles its position on the case. -/
  | vote (v : Vote)
  /-- The drafting judge writes, or revises, the opinion of the court. -/
  | opinion (o : Opinion)
  /-- A judge joins, concurs in, or dissents from the draft opinion. -/
  | respond (r : Response)
  /-- The user withdraws the challenge. -/
  | withdraw (words : String)
  /-- The user keeps a refuted or open case as a house rule. -/
  | houseRule (words : String)
  /-- The user reopens an open challenge with a new case and panel. -/
  | reopen (c : Case) (panel : Panel) (words : String)
  deriving Repr

/-- One event file: its own hash, the hash of the event before it (none for the opening event), its place in
the chain, who wrote it from which device and when, and the event. -/
structure Entry where
  /-- The SHA-256 of the file's exact text. -/
  hash : String
  /-- The hash of the event before it; none for the opening event. -/
  prev : Option String
  /-- Its place in the chain, from 0. -/
  seq : Nat
  /-- Who wrote it. -/
  actor : Actor
  /-- The device it was written on. -/
  device : String
  /-- When it was written. -/
  time : String
  /-- What happened. -/
  event : Event
  deriving Repr

end Challenge
