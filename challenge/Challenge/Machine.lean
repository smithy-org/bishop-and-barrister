import Challenge.Check

/-!
# The challenge state machine

Every challenge is in exactly one `Phase`. Two guarantees are carried by the types themselves, so no code path
can break them:

* `Phase.introduced` holds an `Earned`, which can only be built from a `Settled` (five convinced, evidenced
  votes, a passing verifier report with no level 1 conflict and no standing refutation, a case whose every step
  is sourced or a stipulation in a gap, and an independent panel) and an opinion that all five judges joined.
* `Phase.attack`, `Phase.voting` and `Phase.joining` hold a proof that some judge has yet to act; the phase
  advances the moment the last one does.

`step` is the transition table: it refuses any event the table doesn't allow, with the reason.
-/

namespace Challenge

/-- Judge `k` has filed this round. -/
def filedBy (fs : List Filing) (k : Nat) : Bool := fs.any (fun f => f.judge == k)
/-- The convened judges who haven't filed yet. -/
def missingJudges (convened : List Nat) (fs : List Filing) : List Nat := convened.filter (fun k => !filedBy fs k)
/-- Judge `k` has a position on record. -/
def votedBy (vs : List Vote) (k : Nat) : Bool := vs.any (fun v => v.judge == k)
/-- The judges with no position on record yet. -/
def missingVoters (vs : List Vote) : List Nat := judges.filter (fun k => !votedBy vs k)
/-- Judge `k` has answered the draft opinion. -/
def respondedBy (rs : List Response) (k : Nat) : Bool := rs.any (fun r => r.judge == k)
/-- The judges who haven't answered the draft opinion yet. -/
def missingResponders (rs : List Response) : List Nat := judges.filter (fun k => !respondedBy rs k)

/-- At the start of an attack round with all five convened, someone has yet to file. The phase needs this proof to
exist, which is how guarantee 5, progress, is carried by the types. -/
theorem noneFiled : missingJudges judges [] ≠ [] := by decide
/-- Before any vote, someone has yet to vote. The voting phase needs this proof to start empty. -/
theorem noneVoted : missingVoters [] ≠ [] := by decide
/-- Before any response to a draft, someone has yet to answer it. The joining phase needs this proof to start empty. -/
theorem noneResponded : missingResponders [] ≠ [] := by decide

/-- Five convinced, evidenced positions on a case that passed the verifier: the judges are settled, and the rule
still needs its opinion. -/
structure Settled where
  /-- The case the judges settled on. -/
  claim : Case
  /-- The verifier's last report on it. -/
  report : Report
  /-- Every judge's settled position. -/
  votes : List Vote
  /-- The panel that heard it. -/
  panel : Panel
  /-- No judge's position is missing. -/
  full : missingVoters votes = []
  /-- Every judge is convinced. -/
  allConvinced : votes.all (fun v => v.convinced) = true
  /-- Every position names its evidence. -/
  evidenced : votes.all (fun v => !v.evidence.isEmpty) = true
  /-- The verifier passed the case. -/
  passed : report.passed = true
  /-- The case contradicts no level 1 source. -/
  noConflict : report.level1Conflict = false
  /-- No verified refutation stands. -/
  noStanding : report.standing.isEmpty = true
  /-- Every step quotes a pinned source or is a stipulation. No step is a bare assumption. -/
  grounded : claim.steps.all (fun st => st.source.isSome || st.stipulation) = true
  /-- Stipulations appear only in a case that fills a gap. -/
  gapOnly : claim.steps.all (fun st => !st.stipulation || isGap claim.challenges) = true
  /-- The panel is independent, not a single agent. -/
  independent : panel = Panel.independent

/-- The only way to build an introduced challenge: a `Settled` and an opinion that all five judges joined. -/
structure Earned extends Settled where
  /-- The opinion of the court. -/
  opinion : Opinion
  /-- Every judge's answer to it. -/
  joins : List Response
  /-- No judge's answer is missing. -/
  fullJoins : missingResponders joins = []
  /-- Every judge joined. A concurrence is not a join. -/
  allJoin : joins.all (fun r => r.stance == Stance.join) = true
  /-- The author is one of the convinced judges. -/
  authorConvinced : votes.any (fun v => v.judge == opinion.author && v.convinced) = true
  /-- The holding is the case's rule, word for word. -/
  holdsRule : (opinion.holding == claim.rule) = true
  /-- Every step of the opinion quotes a pinned source or is a stipulation. -/
  opinionGrounded : opinion.steps.all (fun st => st.source.isSome || st.stipulation) = true
  /-- Every stipulation in the opinion is one the case made: the opinion adds nothing. -/
  nothingNew : opinion.steps.all (fun st => !st.stipulation ||
    claim.steps.any (fun cs => cs.stipulation && cs.conclusion == st.conclusion)) = true

/-- Where a challenge stands. Each phase holds what the next step needs, and the waiting phases hold a proof that
someone has yet to act. -/
inductive Phase where
  /-- Before the opening event. -/
  | unopened
  /-- Opened: the clerk writes the brief next. -/
  | draft
  /-- The brief is written: the user confirms or corrects it. -/
  | briefed (c : Case)
  /-- `convened` are the judges who attack this round (all five in the first). `looks` are every judge's latest. -/
  | attack (n : Nat) (c : Case) (convened : List Nat) (looks : List Look) (filed : List Filing)
      (waiting : missingJudges convened filed ≠ [])
  /-- Attack round `n` is filed: the verifier checks the refutations. -/
  | verify (n : Nat) (c : Case) (looks : List Look) (filed : List Filing)
  /-- Some refutations stood: the user answers them. -/
  | answer (n : Nat) (c : Case) (looks : List Look) (filed : List Filing) (r : Report)
  /-- The user answered: the verifier checks the answers. -/
  | verifyAnswers (n : Nat) (c : Case) (looks : List Look) (filed : List Filing) (a : Answer)
  /-- The judges not yet settled on the final case vote. -/
  | voting (c : Case) (r : Report) (votes : List Vote) (waiting : missingVoters votes ≠ [])
  /-- The judges are settled and convinced; one of them drafts (or revises) the opinion. -/
  | drafting (st : Settled) (revision : Nat)
  /-- The draft opinion is out: each judge joins, concurs, or dissents. -/
  | joining (st : Settled) (op : Opinion) (revision : Nat) (responses : List Response)
      (waiting : missingResponders responses ≠ [])
  /-- The rule is introduced. This is final. -/
  | introduced (e : Earned)
  /-- The case was refuted, and why. Only a house rule can follow. -/
  | refuted (c : Case) (why : String)
  /-- The case is unproven, and why. The user can reopen it, keep it as a house rule, or withdraw it. -/
  | open_ (c : Case) (why : String)
  /-- The user withdrew the challenge. This is final. -/
  | withdrawn
  /-- The user kept the case as a house rule. This is final. -/
  | houseRule (c : Case)

/-- The phase's name, as the JSON interface writes it. -/
def Phase.name : Phase → String
  | .unopened => "unopened"
  | .draft => "draft"
  | .briefed _ => "briefed"
  | .attack _ _ _ _ _ _ => "attack"
  | .verify _ _ _ _ => "verify"
  | .answer _ _ _ _ _ => "answer"
  | .verifyAnswers _ _ _ _ _ => "verify-answers"
  | .voting _ _ _ _ => "voting"
  | .drafting _ _ => "drafting"
  | .joining _ _ _ _ _ => "joining"
  | .introduced _ => "introduced"
  | .refuted _ _ => "refuted"
  | .open_ _ _ => "open"
  | .withdrawn => "withdrawn"
  | .houseRule _ => "house-rule"

/-- The round number, in the phases that belong to a round. -/
def Phase.round : Phase → Option Nat
  | .attack n _ _ _ _ _ | .verify n _ _ _ | .answer n _ _ _ _ | .verifyAnswers n _ _ _ _ => some n
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

/-- The lowest-numbered convinced judge writes the opinion. -/
def drafter (vs : List Vote) : Nat :=
  (judges.find? (fun k => vs.any (fun v => v.judge == k && v.convinced))).getD 1

/-- Who owes the next action. -/
def owed : Phase → List Actor
  | .unopened => [.user]
  | .draft => [.clerk]
  | .briefed _ => [.user]
  | .attack _ _ cv _ fs _ => (missingJudges cv fs).map .judge
  | .verify _ _ _ _ => [.verifier]
  | .answer _ _ _ _ _ => [.user]
  | .verifyAnswers _ _ _ _ _ => [.verifier]
  | .voting _ _ vs _ => (missingVoters vs).map .judge
  | .drafting st _ => [.judge (drafter st.votes)]
  | .joining _ _ _ rs _ => (missingResponders rs).map .judge
  | .open_ _ _ => [.user]
  | .introduced _ | .refuted _ _ | .withdrawn | .houseRule _ => []

/-- The replay's state: the phase, the panel, and the bookkeeping that blindness and the hash chain need. -/
structure State where
  /-- Where the challenge stands. -/
  phase : Phase
  /-- Which kind of panel is hearing it. -/
  panel : Panel
  /-- The position of the event that started the current phase: filings, votes and responses made since then are
  hidden from the other judges. -/
  since : Nat
  /-- The position of the event that set the current case. -/
  caseSeq : Nat
  /-- The hash of the last event. -/
  head : Option String

/-- The state before the opening event. -/
def State.init : State :=
  { phase := .unopened, panel := .independent, since := 0, caseSeq := 0, head := none }

/-- Puts a check's problems on one line each. -/
def joinErrors (errs : List String) : String := String.intercalate "\n" errs

/-- The user withdraws the challenge, in their own words; anyone else is refused. -/
def withdrawBy (s : State) (x : Entry) (words : String) : Except String State :=
  if x.actor = Actor.user ∧ words ≠ "" then .ok { s with phase := .withdrawn }
  else .error "only the user withdraws a challenge, in their own words"

/-- The only way to build a `Settled`: every guard on the case, checked together. -/
def settle? (c : Case) (r : Report) (vs : List Vote) (full : missingVoters vs = []) (p : Panel) : Option Settled :=
  if h : vs.all (fun v => v.convinced) = true ∧ vs.all (fun v => !v.evidence.isEmpty) = true ∧
      r.passed = true ∧ r.level1Conflict = false ∧ r.standing.isEmpty = true ∧
      c.steps.all (fun st => st.source.isSome || st.stipulation) = true ∧
      c.steps.all (fun st => !st.stipulation || isGap c.challenges) = true ∧ p = Panel.independent then
    have ⟨h1, h2, h3, h4, h5, h6, h7, h8⟩ := h
    some ⟨c, r, vs, p, full, h1, h2, h3, h4, h5, h6, h7, h8⟩
  else none

/-- The only way to build an `Earned`: all five joined, the author is one of the convinced judges, and the
opinion states the case's rule and no new content. -/
def earn? (st : Settled) (op : Opinion) (rs : List Response) (full : missingResponders rs = []) :
    Option Earned :=
  if h : rs.all (fun r => r.stance == Stance.join) = true ∧
      st.votes.any (fun v => v.judge == op.author && v.convinced) = true ∧
      (op.holding == st.claim.rule) = true ∧
      op.steps.all (fun t => t.source.isSome || t.stipulation) = true ∧
      op.steps.all (fun t => !t.stipulation ||
        st.claim.steps.any (fun cs => cs.stipulation && cs.conclusion == t.conclusion)) = true then
    have ⟨h1, h2, h3, h4, h5⟩ := h
    some { toSettled := st, opinion := op, joins := rs, fullJoins := full, allJoin := h1, authorConvinced := h2,
           holdsRule := h3, opinionGrounded := h4, nothingNew := h5 }
  else none

/-- How many votes are not convinced. -/
def notConvinced (vs : List Vote) : Nat := (vs.filter (fun v => !v.convinced)).length

/-- A concession is that judge's settled position, if the case hasn't changed since: convinced, with its evidence. -/
def concessionVote (f : Filing) : Vote :=
  { judge := f.judge, convinced := true, reason := f.concedes, evidence := f.concedeEvidence }

/-- The judges' latest looks once these filings are in, seen at the case version `version`. A concession is a
settled position only in a round where no judge filed a refutation; in a round with any refutation, every filer
must settle by vote. -/
def updateLooks (old : List Look) (fs : List Filing) (version : Nat) : List Look :=
  let clean := fs.all (fun f => f.refutations.isEmpty)
  old.filter (fun l => !filedBy fs l.judge) ++
    fs.map (fun f => { judge := f.judge, version := version,
                       position := if clean then some (concessionVote f) else none })

/-- The positions already settled on the case as it now stands: a concession on this very version, made in a round
where no judge filed a refutation. A judge whose last look predates the final revision, or came in a round with any
refutation, isn't settled and must look again. -/
def settledOn (looks : List Look) (version : Nat) : List Vote :=
  judges.filterMap (fun k => (looks.find? (fun l => l.judge == k && l.version == version)).bind (·.position))

/-- The consensus, once every judge has settled. All convinced, and every guard holds: the judges are settled and
write the opinion. Three or more not convinced: refused, as `refuted` if a verified refutation stands or the case
contradicts a level 1 source, and as `open` if it is merely unproven. One or two not convinced: no consensus, so
another round (the dissenters' reasons are visible to all), until the round limit, when it stays `open`. -/
def close (c : Case) (r : Report) (vs : List Vote) (full : missingVoters vs = []) (p : Panel) : Phase :=
  match settle? c r vs full p with
  | some st => .drafting st 0
  | none =>
    let defeated := !r.standing.isEmpty || r.level1Conflict
    let dissent := notConvinced vs
    if dissent = 0 then
      if p = Panel.singleAgent then
        .open_ c "all five were convinced, but by a single-agent panel: only an independent panel can introduce a rule"
      else if defeated then
        .refuted c "all five were convinced, but a verified refutation stands and a vote cannot override it"
      else .open_ c "all five were convinced, but the case has an unsourced step or a position without evidence"
    else if dissent ≥ refuseNeeds then
      if defeated then .refuted c s!"{dissent} of {panelSize} judges were not convinced, and a verified refutation stands"
      else .open_ c s!"{dissent} of {panelSize} judges were not convinced and no refutation stands: the case is unproven"
    else if r.round + 1 ≤ roundCap then .attack (r.round + 1) c judges [] [] noneFiled
    else .open_ c s!"no consensus after {roundCap} rounds: {dissent} of {panelSize} judges were not convinced"

/-- The judges not yet settled on the final case vote; with none left, the case closes. -/
def settleOrVote (c : Case) (r : Report) (settled : List Vote) (p : Panel) : Phase :=
  if hf : missingVoters settled = [] then close c r settled hf p else .voting c r settled hf

/-- Once all five have answered the draft. All joined: the rule is introduced. Three or more dissented: refused, as
the case is unproven. Otherwise the author revises (up to `opinionRevisions` times) to win the joins, then the case
stays `open`. A concurrence is not a join. -/
def closeOpinion (st : Settled) (op : Opinion) (revision : Nat) (rs : List Response)
    (full : missingResponders rs = []) : Phase :=
  match earn? st op rs full with
  | some e => .introduced e
  | none =>
    let dissent := (rs.filter (fun r => r.stance == Stance.dissent)).length
    if dissent ≥ refuseNeeds then
      .open_ st.claim s!"{dissent} of {panelSize} judges dissented from the opinion: the case is unproven"
    else if revision + 1 ≤ opinionRevisions then .drafting st (revision + 1)
    else .open_ st.claim
      s!"no opinion won all {panelSize} joins after {opinionRevisions} revisions: every judge must join the same opinion"

/-- Before the opening: only the user's opening event is accepted. -/
def onUnopened (s : State) (x : Entry) : Except String State :=
  match x.event with
  | .start statement panel =>
    if x.actor ≠ Actor.user then .error "the user opens a challenge"
    else if statement = "" then .error "the opening needs the user's case, in their own words"
    else .ok { s with phase := .draft, panel := panel }
  | _ => .error "a challenge starts with an \"open\" event"

/-- A draft: the clerk writes the brief, or the user withdraws. -/
def onDraft (s : State) (x : Entry) : Except String State :=
  match x.event with
  | .brief c =>
    if x.actor ≠ Actor.clerk then .error "the clerk writes the brief"
    else match checkCase c with
      | [] => .ok { s with phase := .briefed c }
      | errs => .error (joinErrors errs)
  | .withdraw w => withdrawBy s x w
  | _ => .error "the challenge is a draft: the clerk writes the brief next"

/-- A brief: the user confirms it, which starts round 1, or it is edited, or the user withdraws. -/
def onBriefed (s : State) (c : Case) (x : Entry) : Except String State :=
  match x.event with
  | .confirm w =>
    if x.actor ≠ Actor.user ∨ w = "" then .error "the user confirms the brief, in their own words"
    else .ok { s with phase := .attack 1 c judges [] [] noneFiled }
  | .edit c' w =>
    if (x.actor ≠ Actor.user ∧ x.actor ≠ Actor.clerk) ∨ w = "" then
      .error "the brief is edited for the user, with the user's own words"
    else match checkCase c' with
      | [] => .ok { s with phase := .briefed c' }
      | errs => .error (joinErrors errs)
  | .withdraw w => withdrawBy s x w
  | _ => .error "the brief is waiting for the user to confirm or correct it"

/-- An attack round: each convened judge files once; the last filing sends the round to the verifier. -/
def onAttack (s : State) (n : Nat) (c : Case) (cv : List Nat) (looks : List Look) (fs : List Filing) (x : Entry) :
    Except String State :=
  match x.event, x.actor with
  | .file f, .judge k =>
    if !judges.contains k then .error s!"there is no judge {k}; the judges are 1 to {panelSize}"
    else if !cv.contains k then
      .error s!"judge {k} isn't convened in round {n}: only the judges whose refutation the revision answered attack again"
    else if filedBy fs k then .error s!"judge {k} has already filed in round {n}"
    else if f.round ≠ n then .error s!"this is round {n}, not round {f.round}"
    else
      let f' := { f with judge := k }
      match checkFiling c f' with
      | [] =>
        let fs' := fs ++ [f']
        if hw : missingJudges cv fs' = [] then .ok { s with phase := .verify n c looks fs' }
        else .ok { s with phase := .attack n c cv looks fs' hw }
      | errs => .error (joinErrors errs)
  | .file _, _ => .error "only a judge files in an attack round"
  | _, _ => .error s!"round {n} is an attack round: each convened judge files refutations or concedes"

/-- The verifier reports on a round's refutations. If none stands, the judges settle; otherwise the user answers. -/
def onVerify (s : State) (n : Nat) (c : Case) (looks : List Look) (fs : List Filing) (x : Entry) :
    Except String State :=
  match x.event with
  | .report r =>
    if x.actor ≠ Actor.verifier then .error "only the verifier files a report"
    else match checkReport n .attack fs r with
      | [] =>
        let looks' := updateLooks looks fs s.caseSeq
        -- No refutation stands: a judge's concession on this very case is its settled position, and every other
        -- judge looks again on the final case. A standing refutation goes to the user first.
        if r.standing.isEmpty then
          .ok { s with phase := settleOrVote c r (settledOn looks' s.caseSeq) s.panel }
        else .ok { s with phase := .answer n c looks' fs r }
      | errs => .error (joinErrors errs)
  | _ => .error s!"round {n}'s refutations are waiting for the verifier"

/-- The user answers the refutations that stood, or withdraws. -/
def onAnswer (s : State) (n : Nat) (c : Case) (looks : List Look) (fs : List Filing) (r : Report) (x : Entry) :
    Except String State :=
  match x.event with
  | .answer a =>
    if x.actor ≠ Actor.user then .error "only the user answers the refutations"
    else match checkAnswer n c fs r a with
      | [] => .ok { s with phase := .verifyAnswers n (a.revised.getD c) looks fs a }
      | errs => .error (joinErrors errs)
  | .withdraw w => withdrawBy s x w
  | _ => .error s!"round {n}'s verified refutations are waiting for the user's answer"

/-- The verifier reports on the user's answers. A revised case goes back to the judges whose refutation it answered;
otherwise the judges settle. -/
def onVerifyAnswers (s : State) (n : Nat) (c : Case) (looks : List Look) (fs : List Filing) (a : Answer)
    (x : Entry) : Except String State :=
  match x.event with
  | .report r =>
    if x.actor ≠ Actor.verifier then .error "only the verifier files a report"
    else match checkReport n .answers fs r with
      | [] =>
        -- A revised case is attacked again, but only by the judges whose refutation the revision answered (a
        -- `fix`); the others' earlier concessions stand for now. An unchanged case, or one nobody's refutation
        -- led to, goes to the judges to settle: no script closes it.
        let convened := judges.filter (fun k => a.replies.any (fun rp => rp.slot.judge == k && rp.kind == ReplyKind.fix))
        if a.revised.isSome ∧ n < roundCap then
          if hw : missingJudges convened [] = [] then
            .ok { s with phase := settleOrVote c r (settledOn looks s.caseSeq) s.panel }
          else .ok { s with phase := .attack (n + 1) c convened looks [] hw }
        else .ok { s with phase := settleOrVote c r (settledOn looks s.caseSeq) s.panel }
      | errs => .error (joinErrors errs)
  | _ => .error s!"the user's answers to round {n} are waiting for the verifier"

/-- Voting: each judge votes once; the last vote closes the case. -/
def onVoting (s : State) (c : Case) (r : Report) (vs : List Vote) (x : Entry) : Except String State :=
  match x.event, x.actor with
  | .vote v, .judge k =>
    if !judges.contains k then .error s!"there is no judge {k}; the judges are 1 to {panelSize}"
    else if votedBy vs k then .error s!"judge {k} has already settled its position on this case"
    else match checkVote v with
      | [] =>
        let vs' := vs ++ [{ v with judge := k }]
        if hw : missingVoters vs' = [] then .ok { s with phase := close c r vs' hw s.panel }
        else .ok { s with phase := .voting c r vs' hw }
      | errs => .error (joinErrors errs)
  | .vote _, _ => .error "only a judge votes"
  | _, _ => .error "the panel is voting"

/-- Drafting: the lowest-numbered convinced judge writes the opinion of the court. -/
def onDrafting (s : State) (st : Settled) (revision : Nat) (x : Entry) : Except String State :=
  match x.event, x.actor with
  | .opinion o, .judge k =>
    if k ≠ drafter st.votes then .error s!"judge {drafter st.votes}, the lowest-numbered convinced judge, writes the opinion"
    else
      let o' := { o with author := k }
      match checkOpinion st.claim revision o' with
      | [] => .ok { s with phase := .joining st o' revision [] noneResponded }
      | errs => .error (joinErrors errs)
  | .opinion _, _ => .error "only a judge writes the opinion"
  | _, _ => .error "the judges are settled: the opinion of the court is drafted next"

/-- Joining: each judge answers the draft once; the last answer closes the opinion. -/
def onJoining (s : State) (st : Settled) (op : Opinion) (revision : Nat) (rs : List Response) (x : Entry) :
    Except String State :=
  match x.event, x.actor with
  | .respond r, .judge k =>
    if !judges.contains k then .error s!"there is no judge {k}; the judges are 1 to {panelSize}"
    else if respondedBy rs k then .error s!"judge {k} has already answered this draft"
    else match checkResponse revision r with
      | [] =>
        let rs' := rs ++ [{ r with judge := k }]
        if hw : missingResponders rs' = [] then .ok { s with phase := closeOpinion st op revision rs' hw }
        else .ok { s with phase := .joining st op revision rs' hw }
      | errs => .error (joinErrors errs)
  | .respond _, _ => .error "only a judge answers the draft opinion"
  | _, _ => .error "the judges are answering the draft opinion: each joins, concurs, or dissents"

/-- Open: the user keeps it as a house rule, reopens it with a new case, or withdraws it. -/
def onOpen (s : State) (c : Case) (x : Entry) : Except String State :=
  match x.event with
  | .houseRule w =>
    if x.actor = Actor.user ∧ w ≠ "" then .ok { s with phase := .houseRule c }
    else .error "only the user keeps a case as a house rule, in their own words"
  | .reopen c' p w =>
    if x.actor ≠ Actor.user ∨ w = "" then .error "the user reopens a challenge, in their own words"
    else match checkCase c' with
      | [] => .ok { s with phase := .briefed c', panel := p }
      | errs => .error (joinErrors errs)
  | .withdraw w => withdrawBy s x w
  | _ => .error "the challenge is open: the user can return with new facts or sources, keep it as a house rule, or withdraw it"

/-- Refuted: the user can only keep it as a house rule. -/
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
  | .attack n c cv looks fs _ => onAttack s n c cv looks fs x
  | .verify n c looks fs => onVerify s n c looks fs x
  | .answer n c looks fs r => onAnswer s n c looks fs r x
  | .verifyAnswers n c looks fs a => onVerifyAnswers s n c looks fs a x
  | .voting c r vs _ => onVoting s c r vs x
  | .drafting st rev => onDrafting s st rev x
  | .joining st op rev rs _ => onJoining s st op rev rs x
  | .open_ c _ => onOpen s c x

/-- Whether a step was accepted. -/
def accepted {α : Type} : Except String α → Bool
  | .ok _ => true
  | .error _ => false

/-- The event sets a new case: a brief, an edit, a reopening, or an answer with a revised case. -/
def setsCase : Event → Bool
  | .brief _ | .edit _ _ | .reopen _ _ _ => true
  | .answer a => a.revised.isSome
  | _ => false

/-- The result of replaying a challenge's events. `tags` pairs each event with the `since` of the phase it was
filed in. -/
inductive Outcome where
  /-- The events replayed to a state, each tagged with the phase it was filed in. -/
  | state (s : State) (tags : List (Nat × Entry))
  /-- Two events name the same predecessor. -/
  | fork
  /-- Some event isn't reachable from the opening, and why. -/
  | broken (why : String)
  /-- The state machine refused event `seq`, and why. -/
  | refused (seq : Nat) (why : String)

/-- Runs the machine from state `s` over the events, expecting the next to be event `i`. Keeps `since` and `caseSeq`
current and tags each event as it goes. -/
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
