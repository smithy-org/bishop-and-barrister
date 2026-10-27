import Challenge.Check

/-!
# The challenge state machine

Every challenge is in exactly one `Phase`. Two guarantees are carried by the types themselves, so no code path
can break them:

* `Phase.introduced` holds an `Earned`, which can only be built from five convinced votes, a passing verifier
  report with no level 1 conflict, a case with no unsupported step, and an independent panel.
* `Phase.attack` and `Phase.voting` hold a proof that some judge has yet to act; the round advances the moment
  the last one does.

`step` is the transition table: it refuses any event the table doesn't allow, with the reason.
-/

namespace Challenge

def filedBy (fs : List Filing) (k : Nat) : Bool := fs.any (fun f => f.judge == k)
def missingJudges (fs : List Filing) : List Nat := judges.filter (fun k => !filedBy fs k)
def votedBy (vs : List Vote) (k : Nat) : Bool := vs.any (fun v => v.judge == k)
def missingVoters (vs : List Vote) : List Nat := judges.filter (fun k => !votedBy vs k)

theorem noneFiled : missingJudges [] ≠ [] := by decide
theorem noneVoted : missingVoters [] ≠ [] := by decide

/-- The only way to build an introduced challenge. -/
structure Earned where
  claim : Case
  report : Report
  votes : List Vote
  panel : Panel
  full : missingVoters votes = []
  allConvinced : votes.all (fun v => v.convinced) = true
  passed : report.passed = true
  noConflict : report.level1Conflict = false
  sourced : claim.steps.all (fun st => st.source.isSome) = true
  independent : panel = Panel.independent

inductive Phase where
  /-- Before the opening event. -/
  | unopened
  | draft
  | briefed (c : Case)
  | attack (n : Nat) (c : Case) (filed : List Filing) (waiting : missingJudges filed ≠ [])
  | verify (n : Nat) (c : Case) (filed : List Filing)
  | answer (n : Nat) (c : Case) (filed : List Filing) (r : Report)
  | verifyAnswers (n : Nat) (c : Case) (filed : List Filing) (a : Answer)
  | voting (c : Case) (r : Report) (votes : List Vote) (waiting : missingVoters votes ≠ [])
  | introduced (e : Earned)
  | refuted (c : Case) (why : String)
  | open_ (c : Case) (why : String)
  | withdrawn
  | houseRule (c : Case)

def Phase.name : Phase → String
  | .unopened => "unopened"
  | .draft => "draft"
  | .briefed _ => "briefed"
  | .attack _ _ _ _ => "attack"
  | .verify _ _ _ => "verify"
  | .answer _ _ _ _ => "answer"
  | .verifyAnswers _ _ _ _ => "verify-answers"
  | .voting _ _ _ _ => "voting"
  | .introduced _ => "introduced"
  | .refuted _ _ => "refuted"
  | .open_ _ _ => "open"
  | .withdrawn => "withdrawn"
  | .houseRule _ => "house-rule"

def Phase.round : Phase → Option Nat
  | .attack n _ _ _ | .verify n _ _ | .answer n _ _ _ | .verifyAnswers n _ _ _ => some n
  | _ => none

/-- Identifies a phase together with its round, so `since` knows when a new one began. -/
def Phase.key (p : Phase) : String :=
  match p.round with
  | some n => s!"{p.name}:{n}"
  | none => p.name

/-- The challenge is over: nothing is owed by anyone. -/
def Phase.settled : Phase → Bool
  | .introduced _ | .refuted _ _ | .withdrawn | .houseRule _ => true
  | _ => false

/-- Who owes the next action. -/
def owed : Phase → List Actor
  | .unopened => [.user]
  | .draft => [.clerk]
  | .briefed _ => [.user]
  | .attack _ _ fs _ => (missingJudges fs).map .judge
  | .verify _ _ _ => [.verifier]
  | .answer _ _ _ _ => [.user]
  | .verifyAnswers _ _ _ _ => [.verifier]
  | .voting _ _ vs _ => (missingVoters vs).map .judge
  | .open_ _ _ => [.user]
  | .introduced _ | .refuted _ _ | .withdrawn | .houseRule _ => []

structure State where
  phase : Phase
  panel : Panel
  /-- The position of the event that started the current phase: filings and votes made since then are hidden
  from the other judges. -/
  since : Nat
  /-- The position of the event that set the current case. -/
  caseSeq : Nat
  /-- The hash of the last event. -/
  head : Option String

def State.init : State :=
  { phase := .unopened, panel := .independent, since := 0, caseSeq := 0, head := none }

def joinErrors (errs : List String) : String := String.intercalate "\n" errs

def withdrawBy (s : State) (x : Entry) (words : String) : Except String State :=
  if x.actor = Actor.user ∧ words ≠ "" then .ok { s with phase := .withdrawn }
  else .error "only the user withdraws a challenge, in their own words"

/-- The verdict once all five have voted. -/
def close (c : Case) (r : Report) (vs : List Vote) (full : missingVoters vs = []) (p : Panel) : Phase :=
  if hc : vs.all (fun v => v.convinced) = true then
    if hp : r.passed = true then
      if hn : r.level1Conflict = false then
        if hs : c.steps.all (fun st => st.source.isSome) = true then
          if hi : p = Panel.independent then .introduced ⟨c, r, vs, p, full, hc, hp, hn, hs, hi⟩
          else .open_ c "all five were convinced, but by a single-agent panel: only an independent panel can introduce a rule"
        else .refuted c "the case relies on an assumption"
      else .refuted c "the case contradicts a level 1 source"
    else .refuted c "the final case didn't pass the verifier"
  else .refuted c "not every judge was convinced"

def onUnopened (s : State) (x : Entry) : Except String State :=
  match x.event with
  | .start statement panel =>
    if x.actor ≠ Actor.user then .error "the user opens a challenge"
    else if statement = "" then .error "the opening needs the user's case, in their own words"
    else .ok { s with phase := .draft, panel := panel }
  | _ => .error "a challenge starts with an \"open\" event"

def onDraft (s : State) (x : Entry) : Except String State :=
  match x.event with
  | .brief c =>
    if x.actor ≠ Actor.clerk then .error "the clerk writes the brief"
    else match checkCase c with
      | [] => .ok { s with phase := .briefed c }
      | errs => .error (joinErrors errs)
  | .withdraw w => withdrawBy s x w
  | _ => .error "the challenge is a draft: the clerk writes the brief next"

def onBriefed (s : State) (c : Case) (x : Entry) : Except String State :=
  match x.event with
  | .confirm w =>
    if x.actor ≠ Actor.user ∨ w = "" then .error "the user confirms the brief, in their own words"
    else .ok { s with phase := .attack 1 c [] noneFiled }
  | .edit c' w =>
    if (x.actor ≠ Actor.user ∧ x.actor ≠ Actor.clerk) ∨ w = "" then
      .error "the brief is edited for the user, with the user's own words"
    else match checkCase c' with
      | [] => .ok { s with phase := .briefed c' }
      | errs => .error (joinErrors errs)
  | .withdraw w => withdrawBy s x w
  | _ => .error "the brief is waiting for the user to confirm or correct it"

def onAttack (s : State) (n : Nat) (c : Case) (fs : List Filing) (x : Entry) : Except String State :=
  match x.event, x.actor with
  | .file f, .judge k =>
    if !judges.contains k then .error s!"there is no judge {k}; the judges are 1 to {panelSize}"
    else if filedBy fs k then .error s!"judge {k} has already filed in round {n}"
    else if f.round ≠ n then .error s!"this is round {n}, not round {f.round}"
    else
      let f' := { f with judge := k }
      match checkFiling c f' with
      | [] =>
        let fs' := fs ++ [f']
        if hw : missingJudges fs' = [] then .ok { s with phase := .verify n c fs' }
        else .ok { s with phase := .attack n c fs' hw }
      | errs => .error (joinErrors errs)
  | .file _, _ => .error "only a judge files in an attack round"
  | _, _ => .error s!"round {n} is an attack round: each judge files refutations or concedes"

def onVerify (s : State) (n : Nat) (c : Case) (fs : List Filing) (x : Entry) : Except String State :=
  match x.event with
  | .report r =>
    if x.actor ≠ Actor.verifier then .error "only the verifier files a report"
    else match checkReport n .attack fs r with
      | [] =>
        if r.standing.isEmpty then .ok { s with phase := .voting c r [] noneVoted }
        else .ok { s with phase := .answer n c fs r }
      | errs => .error (joinErrors errs)
  | _ => .error s!"round {n}'s refutations are waiting for the verifier"

def onAnswer (s : State) (n : Nat) (c : Case) (fs : List Filing) (r : Report) (x : Entry) :
    Except String State :=
  match x.event with
  | .answer a =>
    if x.actor ≠ Actor.user then .error "only the user answers the refutations"
    else match checkAnswer n c fs r a with
      | [] => .ok { s with phase := .verifyAnswers n (a.revised.getD c) fs a }
      | errs => .error (joinErrors errs)
  | .withdraw w => withdrawBy s x w
  | _ => .error s!"round {n}'s verified refutations are waiting for the user's answer"

/-- A refutation the user conceded without revising the case: it defeats the case. -/
def concededWithoutFix (a : Answer) : Option Slot :=
  if a.revised.isSome then none else (a.replies.find? (fun rp => rp.kind == ReplyKind.concede)).map (·.slot)

def onVerifyAnswers (s : State) (n : Nat) (c : Case) (fs : List Filing) (a : Answer) (x : Entry) :
    Except String State :=
  match x.event with
  | .report r =>
    if x.actor ≠ Actor.verifier then .error "only the verifier files a report"
    else match checkReport n .answers fs r with
      | [] =>
        match concededWithoutFix a with
        | some sl =>
          .ok { s with phase := .refuted c s!"the user conceded judge {sl.judge}'s refutation {sl.index} and didn't revise the case" }
        | none =>
          if n < roundCap then .ok { s with phase := .attack (n + 1) c [] noneFiled }
          else if r.standing.isEmpty then .ok { s with phase := .voting c r [] noneVoted }
          else .ok { s with phase := .open_ c s!"{roundCap} rounds, and refutations still stand" }
      | errs => .error (joinErrors errs)
  | _ => .error s!"the user's answers to round {n} are waiting for the verifier"

def onVoting (s : State) (c : Case) (r : Report) (vs : List Vote) (x : Entry) : Except String State :=
  match x.event, x.actor with
  | .vote v, .judge k =>
    if !judges.contains k then .error s!"there is no judge {k}; the judges are 1 to {panelSize}"
    else if votedBy vs k then .error s!"judge {k} has already voted"
    else if v.reason = "" then
      .error "a vote needs its reason: the step that settled it, or the refutation still standing"
    else
      let vs' := vs ++ [{ v with judge := k }]
      if hw : missingVoters vs' = [] then .ok { s with phase := close c r vs' hw s.panel }
      else .ok { s with phase := .voting c r vs' hw }
  | .vote _, _ => .error "only a judge votes"
  | _, _ => .error "the panel is voting"

def onOpen (s : State) (_c : Case) (x : Entry) : Except String State :=
  match x.event with
  | .reopen c' p w =>
    if x.actor ≠ Actor.user ∨ w = "" then .error "the user reopens a challenge, in their own words"
    else match checkCase c' with
      | [] => .ok { s with phase := .briefed c', panel := p }
      | errs => .error (joinErrors errs)
  | .withdraw w => withdrawBy s x w
  | _ => .error "the challenge is open: the user can return with new facts or sources, or withdraw it"

def onRefuted (s : State) (c : Case) (x : Entry) : Except String State :=
  match x.event with
  | .houseRule w =>
    if x.actor = Actor.user ∧ w ≠ "" then .ok { s with phase := .houseRule c }
    else .error "only the user keeps a refuted case as a house rule, in their own words"
  | _ => .error "the challenge was refuted; the user can only keep it as a house rule"

/-- The transition table. -/
def step (s : State) (x : Entry) : Except String State :=
  match s.phase with
  | .introduced _ => .error "the challenge is closed: it introduced a rule"
  | .withdrawn => .error "the challenge was withdrawn"
  | .houseRule _ => .error "the challenge is closed: it was kept as a house rule"
  | .refuted c _ => onRefuted s c x
  | .unopened => onUnopened s x
  | .draft => onDraft s x
  | .briefed c => onBriefed s c x
  | .attack n c fs _ => onAttack s n c fs x
  | .verify n c fs => onVerify s n c fs x
  | .answer n c fs r => onAnswer s n c fs r x
  | .verifyAnswers n c fs a => onVerifyAnswers s n c fs a x
  | .voting c r vs _ => onVoting s c r vs x
  | .open_ c _ => onOpen s c x

def accepted {α : Type} : Except String α → Bool
  | .ok _ => true
  | .error _ => false

def setsCase : Event → Bool
  | .brief _ | .edit _ _ | .reopen _ _ _ => true
  | .answer a => a.revised.isSome
  | _ => false

/-- The result of replaying a challenge's events. `tags` pairs each event with the `since` of the phase it was
filed in. -/
inductive Outcome where
  | state (s : State) (tags : List (Nat × Entry))
  | fork
  | broken (why : String)
  | refused (seq : Nat) (why : String)

def runFrom : State → Nat → List Entry → List (Nat × Entry) → Outcome
  | s, _, [], acc => .state s acc.reverse
  | s, i, x :: xs, acc =>
    if x.seq ≠ i then .refused i s!"event {i} says it is event {x.seq}"
    else match step s x with
      | .error why => .refused i why
      | .ok s' =>
        let since := if s'.phase.key == s.phase.key then s.since else i + 1
        let caseSeq := if setsCase x.event then i else s.caseSeq
        runFrom { s' with since := since, caseSeq := caseSeq, head := some x.hash } (i + 1) xs ((s.since, x) :: acc)

/-- Replays events already in chain order. -/
def run (l : List Entry) : Outcome := runFrom State.init 0 l []

end Challenge
