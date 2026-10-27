import Challenge
open Lean Challenge

/-! Example event sequences for every path through both machines, and refused events. `lake test` runs this. -/

def jstr (s : String) : Json := toJson s
def jnat (n : Nat) : Json := toJson n

def pin : String := hashString "pinned text"

def source (ref : String) (sha := pin) : Json :=
  Json.mkObj [("doc", jstr "cr"), ("ref", jstr ref), ("excerpt", jstr "quoted text"), ("text_sha256", jstr sha)]

def stepJ (id : Nat) (premises : List String) (src : Option Json) (assumption := src.isNone) (stip := false) : Json :=
  Json.mkObj [("id", jnat id), ("premises", toJson premises.toArray), ("source", src.getD Json.null),
    ("assumption", toJson assumption), ("stipulation", toJson stip), ("conclusion", jstr s!"conclusion {id}")]

/-- What a concession or a vote rests on: the pinned sources checked. -/
def evidenceJ : Json := Json.arr #[source "103.1"]

def caseJ (steps : List Json) (challenges : String := "none: a gap") : Json := Json.mkObj [
  ("facts", Json.arr #[Json.mkObj [("id", jnat 1), ("text", jstr "three players; game 2 of a match")]]),
  ("open_questions", Json.arr #[]), ("rule", jstr "the player who lost game 1 chooses who plays first"),
  ("applies_when", Json.arr #[jstr "a three-player match"]), ("challenges", jstr challenges),
  ("steps", Json.arr steps.toArray)]

def goodCase : Json :=
  caseJ [stepJ 1 ["F1"] (some (source "103.1")), stepJ 2 ["F1", "S1"] (some (source "103.2"))]

/-- A gap rule: one sourced step, and the rule's own new content as a stipulation. -/
def stipJ (id : Nat) (premises : List String) : Json := stepJ id premises none (assumption := false) (stip := true)
def stipCase (challenges : String := "none: a gap") : Json :=
  caseJ [stepJ 1 ["F1"] (some (source "103.1")), stipJ 2 ["F1", "S1"]] challenges

def refutationJ (target : Nat) (steps : List Json := [stepJ 1 ["C1"] (some (source "103.3"))]) : Json :=
  Json.mkObj [("target", jnat target), ("ground", jstr "counterexample"),
    ("argument", jstr "it gives the wrong answer for two players"), ("steps", Json.arr steps.toArray)]

/-- actor, type, the event's own fields -/
abbrev Spec := String × String × List (String × Json)

def mkEvent (seq : Nat) (prev : Option String) (device : String) (sp : Spec) : String :=
  (Json.mkObj ([("v", jnat 1), ("seq", jnat seq), ("prev", toJson prev), ("actor", jstr sp.1),
    ("device", jstr device), ("time", jstr "2026-10-26T10:00:00Z"), ("type", jstr sp.2.1)] ++ sp.2.2)).compress

def chain (specs : List Spec) (device : String := "laptop") : List String := Id.run do
  let mut prev : Option String := none
  let mut out : Array String := #[]
  for sp in specs do
    let raw := mkEvent out.size prev device sp
    out := out.push raw
    prev := some (hashString raw)
  return out.toList

def opening (panel : String := "independent") : Spec :=
  ("user", "open", [("statement", jstr "who chooses who plays first in game 2?"), ("panel", jstr panel)])
def briefWith (c : Json) : Spec := ("clerk", "brief", [("case", c)])
def briefS : Spec := briefWith goodCase
def confirmS : Spec := ("user", "confirm", [("words", jstr "yes, that's my case")])
def concede (k n : Nat) : Spec :=
  (s!"judge-{k}", "file", [("round", jnat n), ("refutations", Json.arr #[]), ("concedes", jstr "I can't refute it"),
    ("concede_evidence", evidenceJ)])
def refuteWith (k n : Nat) (r : Json) : Spec := (s!"judge-{k}", "file", [("round", jnat n), ("refutations", Json.arr #[r])])
def refute (k n target : Nat) : Spec := refuteWith k n (refutationJ target)
def slotsJ (slots : List (Nat × Nat)) : Json :=
  Json.arr (slots.map fun (j, i) => Json.mkObj [("judge", jnat j), ("index", jnat i)]).toArray
def reportS (n : Nat) (stage : String) (standing : List (Nat × Nat)) (passed := true) (conflict := false) : Spec :=
  ("verifier", "report", [("round", jnat n), ("stage", jstr stage), ("passed", toJson passed),
    ("level1_conflict", toJson conflict), ("standing", slotsJ standing)])
def answerS (n : Nat) (slots : List (Nat × Nat)) : Spec :=
  ("user", "answer", [("round", jnat n), ("words", jstr "my answers"),
    ("replies", Json.arr (slots.map fun (j, i) => Json.mkObj [("judge", jnat j), ("index", jnat i),
      ("kind", jstr "rebut"), ("words", jstr "that situation isn't a match"),
      ("steps", Json.arr #[stepJ 1 ["C1"] (some (source "103.4"))])]).toArray)])
def replyS (kind : String) (n : Nat) (slots : List (Nat × Nat)) (revised : Option Json := none) : Spec :=
  ("user", "answer", [("round", jnat n), ("words", jstr "my answers"),
    ("replies", Json.arr (slots.map fun (j, i) => Json.mkObj [("judge", jnat j), ("index", jnat i),
      ("kind", jstr kind), ("words", jstr "fair point")]).toArray)] ++
    (match revised with
     | some c => [("case", c)]
     | none => []))
def voteS (k : Nat) (convinced : Bool) : Spec :=
  (s!"judge-{k}", "vote", [("convinced", toJson convinced), ("reason", jstr "step 2 settled it"),
    ("evidence", evidenceJ)])
def words (actor type_ : String) : Spec := (actor, type_, [("words", jstr "in my own words")])

def panel : List Nat := List.range' 1 5
def allConcede (n : Nat) : List Spec := panel.map (concede · n)
def votesBy (ks : List Nat) (convinced : Nat → Bool) : List Spec := ks.map fun k => voteS k (convinced k)

def standingOf (ks : List Nat) : List (Nat × Nat) := ks.map (·, 1)

/-- Round 1: the judges in `refuters` file a refutation, the rest concede. -/
def roundOne (refuters : List Nat) : List Spec :=
  [opening, briefS, confirmS] ++ panel.map (fun k => if refuters.contains k then refute k 1 1 else concede k 1)

/-- The refutations fail verification, so nothing stands; the judges who didn't concede settle. -/
def toVotingWith (refuters : List Nat) : List Spec := roundOne refuters ++ [reportS 1 "attack" []]
def toVoting : List Spec := toVotingWith [1]
/-- The refutations by `ks` are verified and stand. -/
def toAnswerBy (ks : List Nat) : List Spec := roundOne ks ++ [reportS 1 "attack" (standingOf ks)]
def toAnswer : List Spec := toAnswerBy [1]

/-- The judges are settled with no refutation standing, so the opinion of the court is drafted next. -/
def toDrafting : List Spec := [opening, briefS, confirmS] ++ allConcede 1 ++ [reportS 1 "attack" []]

/-- The opinion's holding is the case's rule; its reasoning is sourced. -/
def holdingText : String := "the player who lost game 1 chooses who plays first"
def opinionSteps : List Json := [stepJ 1 ["F1"] (some (source "103.1"))]
def draftWith (rev : Nat) (steps : List Json) (holding : String := holdingText) (k : Nat := 1) : Spec :=
  (s!"judge-{k}", "opinion", [("revision", jnat rev), ("holding", jstr holding), ("steps", Json.arr steps.toArray)])
def draftS (rev : Nat := 0) : Spec := draftWith rev opinionSteps
def stipOpinion : List Json := [stepJ 1 ["F1"] (some (source "103.1")), stipJ 2 ["F1", "S1"]]
def respondS (k rev : Nat) (stance : String) : Spec :=
  (s!"judge-{k}", "respond", [("revision", jnat rev), ("stance", jstr stance),
    ("reason", jstr "the opinion states the rule and its reasons"), ("evidence", evidenceJ)])
def respondAll (rev : Nat) (stance : Nat → String) : List Spec := panel.map fun k => respondS k rev (stance k)
def allJoin (rev : Nat := 0) : List Spec := respondAll rev (fun _ => "join")
/-- Everyone joins except the judges in `others`, who give `stance`. -/
def allJoinBut (others : List Nat) (stance : String) (rev : Nat := 0) : List Spec :=
  respondAll rev (fun k => if others.contains k then stance else "join")

def toJoining : List Spec := toDrafting ++ [draftS]

/-- The user revises the case; in round 1 all five judges attack it, and after that only the judges whose
refutation the revision answered. -/
def roundSpecs (n : Nat) : List Spec :=
  [refute 1 n 1] ++ (if n = 1 then (List.range' 2 4).map (concede · n) else []) ++
  [reportS n "attack" [(1, 1)], replyS "fix" n [(1, 1)] (some goodCase), reportS n "answers" [(1, 1)]]

/-- Judges 1 and 2 refute and both stand; the user fixes judge 1's refutation and rebuts judge 2's. -/
def mixedAnswerS : Spec :=
  ("user", "answer", [("round", jnat 1), ("words", jstr "my answers"),
    ("replies", Json.arr #[
      Json.mkObj [("judge", jnat 1), ("index", jnat 1), ("kind", jstr "fix"), ("words", jstr "fair point")],
      Json.mkObj [("judge", jnat 2), ("index", jnat 1), ("kind", jstr "rebut"), ("words", jstr "not a match"),
        ("steps", Json.arr #[stepJ 1 ["C1"] (some (source "103.4"))])]]),
    ("case", goodCase)])

/-- The user concedes the refutations by `ks`, so nothing is answered; the judges who didn't concede settle. -/
def toConcededBy (ks : List Nat) : List Spec :=
  toAnswerBy ks ++ [replyS "concede" 1 (standingOf ks), reportS 1 "answers" (standingOf ks)]
/-- Three judges' refutations stand and the user concedes them; all three are not convinced. -/
def toRefuted : List Spec := toConcededBy [1, 2, 3] ++ votesBy [1, 2, 3] (fun _ => false)

/-- Round 2 convenes only judge 1, whose refutation the revision answered. -/
def toRoundTwo : List Spec := [opening, briefS, confirmS] ++ roundSpecs 1
/-- Judge 1 concedes the revised case; judges 2 to 5 last looked at the case before the revision. -/
def toSettling : List Spec := toRoundTwo ++ [concede 1 2, reportS 2 "attack" []]

def outcomeName : Outcome → String
  | .state s _ => s.phase.name
  | .fork => "fork"
  | .broken _ => "broken"
  | .refused seq why => s!"refused {seq}: {why}"

def stateOf (raws : List String) : String :=
  match parseAll raws with
  | .error e => s!"parse error: {e}"
  | .ok evs => outcomeName (replay evs)

def hiddenFor (raws : List String) (k : Nat) : Nat :=
  match parseAll raws with
  | .ok evs =>
    match replay evs with
    | .state s tags => tags.length - (view k s tags).length
    | _ => 999
  | .error _ => 999

abbrev Check := String × Bool × String

def expect (name actual expected : String) : Check :=
  (name, actual == expected, s!"got \"{actual}\", expected \"{expected}\"")
def expectRefused (name actual : String) : Check :=
  (name, actual.startsWith "refused", s!"got \"{actual}\", expected a refusal")
def expectParseError (name actual : String) : Check :=
  (name, actual.startsWith "parse error", s!"got \"{actual}\", expected a parse error")
def expectNat (name : String) (actual expected : Nat) : Check :=
  (name, actual == expected, s!"got {actual}, expected {expected}")

/-- One field of the replay's JSON, as text. -/
def replayField (raws : List String) (name : String) : String := ((replayJson raws).getObjValD name).compress

def forked : List String :=
  let base := chain [opening, briefS, confirmS]
  let head := hashString base.getLast!
  base ++ [mkEvent 3 (some head) "laptop" (concede 1 1), mkEvent 3 (some head) "phone" (concede 2 1)]

def edited : List String :=
  let raws := chain [opening, briefS, confirmS]
  [raws[0]!, raws[1]!.replace "three players" "four players", raws[2]!]

def checks : List Check := [
  -- SHA-256 against the FIPS 180-4 vectors
  expect "sha256 of the empty string" (hashString "")
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  expect "sha256 of abc" (hashString "abc") "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
  expect "sha256 across two blocks" (hashString "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq")
    "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",

  -- the paths through the challenge machine
  expect "nothing yet" (stateOf []) "unopened",
  expect "opened" (stateOf (chain [opening])) "draft",
  expect "briefed" (stateOf (chain [opening, briefS])) "briefed",
  expect "an edit keeps it briefed" (stateOf (chain [opening, briefS, ("user", "edit", [("case", goodCase),
    ("words", jstr "F1 is three players")])])) "briefed",
  expect "confirmed: round 1" (stateOf (chain [opening, briefS, confirmS])) "attack",
  expect "four of five filed: still attacking" (stateOf (chain ([opening, briefS, confirmS] ++ (allConcede 1).take 4)))
    "attack",
  expect "all five filed: verify" (stateOf (chain ([opening, briefS, confirmS] ++ allConcede 1))) "verify",
  expect "nothing standing, but not everyone conceded: the judges who didn't concede settle"
    (stateOf (chain toVoting)) "voting",
  expect "only the judge who didn't concede is still to settle"
    (replayField (chain toVoting) "next") "[\"judge-1\"]",
  expect "everyone conceded on the unchanged case: settled, with no separate vote; the opinion is drafted next"
    (stateOf (chain toDrafting)) "drafting",
  expect "one not convinced: no consensus, another round" (stateOf (chain (toVoting ++ votesBy [1] (fun _ => false))))
    "attack",
  expect "two not convinced: no consensus, another round"
    (stateOf (chain (toVotingWith [1, 2] ++ votesBy [1, 2] (fun _ => false)))) "attack",
  expect "three not convinced and nothing stands: the case is unproven, so open"
    (stateOf (chain (toVotingWith [1, 2, 3] ++ votesBy [1, 2, 3] (fun _ => false)))) "open",
  expect "five not convinced and nothing stands: open"
    (stateOf (chain (toVotingWith panel ++ votesBy panel (fun _ => false)))) "open",
  expect "five convinced after voting: settled, the opinion is drafted next"
    (stateOf (chain (toVotingWith panel ++ votesBy panel (fun _ => true)))) "drafting",
  expect "three not convinced and a refutation stands: refuted" (stateOf (chain toRefuted)) "refuted",
  expect "all convinced, but a verified refutation stands: refuted"
    (stateOf (chain (toConcededBy [1] ++ votesBy [1] (fun _ => true)))) "refuted",
  expect "a failed verifier report: open, the case is unproven"
    (stateOf (chain ([opening, briefS, confirmS] ++ allConcede 1 ++ [reportS 1 "attack" [] (passed := false)]))) "open",
  expect "a level 1 conflict: refuted"
    (stateOf (chain ([opening, briefS, confirmS] ++ allConcede 1 ++ [reportS 1 "attack" [] (conflict := true)]))) "refuted",
  expect "a case resting on an assumption: open, it is unproven"
    (stateOf (chain ([opening, briefWith (caseJ [stepJ 1 ["F1"] none]), confirmS] ++ allConcede 1 ++
      [reportS 1 "attack" []]))) "open",
  expect "a single-agent panel can't introduce: open, with no opinion"
    (stateOf (chain ([opening "single-agent", briefS, confirmS] ++ allConcede 1 ++ [reportS 1 "attack" []]))) "open",
  expect "refuted, kept as a house rule" (stateOf (chain (toRefuted ++ [words "user" "house-rule"]))) "house-rule",
  expect "open, kept as a house rule"
    (stateOf (chain ([opening, briefWith (caseJ [stepJ 1 ["F1"] none]), confirmS] ++ allConcede 1 ++
      [reportS 1 "attack" [], words "user" "house-rule"]))) "house-rule",
  expect "a verified refutation stands: answer" (stateOf (chain toAnswer)) "answer",
  expect "answered: verify the answers" (stateOf (chain (toAnswer ++ [answerS 1 [(1, 1)]]))) "verify-answers",
  expect "answers verified, case unchanged: the judge who refuted settles"
    (stateOf (chain (toAnswer ++ [answerS 1 [(1, 1)], reportS 1 "answers" []]))) "voting",
  expect "a refutation conceded without a fix: the judges settle, nothing closes it for them"
    (stateOf (chain (toConcededBy [1]))) "voting",
  expect "the case revised: the judge whose refutation it answered attacks again, round 2"
    (stateOf (chain (toAnswer ++ [replyS "fix" 1 [(1, 1)] (some goodCase), reportS 1 "answers" []]))) "attack",
  expectRefused "judges can't file once the panel is voting"
    (stateOf (chain (toConcededBy [1] ++ [refute 1 2 1]))),
  expect "three revised rounds: the judges settle on the final case, all five of them"
    (stateOf (chain ([opening, briefS, confirmS] ++ (List.range' 1 3).flatMap roundSpecs))) "voting",
  expect "none of the five has settled on the final revision"
    (replayField (chain ([opening, briefS, confirmS] ++ (List.range' 1 3).flatMap roundSpecs)) "next")
    "[\"judge-1\",\"judge-2\",\"judge-3\",\"judge-4\",\"judge-5\"]",
  expect "one still not convinced after the last round: no consensus, so open"
    (stateOf (chain ([opening, briefS, confirmS] ++ (List.range' 1 3).flatMap roundSpecs ++
      votesBy panel (· ≤ 4)))) "open",
  expect "open, reopened with new facts: briefed"
    (stateOf (chain ([opening, briefS, confirmS] ++ (List.range' 1 3).flatMap roundSpecs ++ votesBy panel (· ≤ 4) ++
      [("user", "reopen", [("case", goodCase), ("words", jstr "a new ruling came out")])]))) "briefed",
  expect "a stipulation in a gap case: briefed" (stateOf (chain [opening, briefWith (stipCase)])) "briefed",
  expect "withdrawn while answering" (stateOf (chain (toAnswer ++ [words "user" "withdraw"]))) "withdrawn",

  -- targeted rounds
  expect "after a revision, round 2 convenes only the judge whose refutation it answered"
    (replayField (chain toRoundTwo) "convened") "[1]",
  expect "round 2 waits on that judge alone" (replayField (chain toRoundTwo) "next") "[\"judge-1\"]",
  expect "round 2 is an attack round" (stateOf (chain toRoundTwo)) "attack",
  expect "round 1 convened all five" (replayField (chain [opening, briefS, confirmS]) "convened")
    "[1,2,3,4,5]",
  expectRefused "a judge who wasn't convened can't file" (stateOf (chain (toRoundTwo ++ [concede 2 2]))),
  expect "a revision that answers one of two refutations convenes only that judge"
    (replayField (chain (toAnswerBy [1, 2] ++ [mixedAnswerS, reportS 1 "answers" [(2, 1)]])) "convened") "[1]",
  expect "judge 1 concedes the final case: judges 2 to 5 last looked before the revision, so they settle"
    (stateOf (chain toSettling)) "voting",
  expect "the soundness rule: only the judges whose last look predates the final revision settle"
    (replayField (chain toSettling) "next") "[\"judge-2\",\"judge-3\",\"judge-4\",\"judge-5\"]",
  expect "judge 1's concession on the final case is its position" (replayField (chain toSettling) "voted") "[1]",
  expect "the others settle on the final case: settled, the opinion is next"
    (stateOf (chain (toSettling ++ votesBy [2, 3, 4, 5] (fun _ => true)))) "drafting",
  expect "an older concession doesn't count, and a not-convinced vote on the final case is heard"
    (stateOf (chain (toSettling ++ votesBy [2, 3, 4, 5] (· != 3)))) "attack",
  expectRefused "a judge settled by its concession on the final case can't also vote"
    (stateOf (chain (toSettling ++ [voteS 1 true]))),
  expect "round 3 convenes judge 1 again if its refutation stood and the user fixed it again"
    (replayField (chain ([opening, briefS, confirmS] ++ roundSpecs 1 ++ roundSpecs 2)) "convened") "[1]",
  expect "a concession in round 1 stands through a later round if the judge is not convened: only judge 1 attacks"
    (stateOf (chain ([opening, briefS, confirmS] ++ roundSpecs 1 ++ roundSpecs 2))) "attack",

  -- the opinion of the court
  expect "the lowest-numbered convinced judge drafts" (replayField (chain toDrafting) "next") "[\"judge-1\"]",
  expect "the draft is out: all five answer it" (stateOf (chain toJoining)) "joining",
  expect "all five are owed an answer" (replayField (chain toJoining) "next")
    "[\"judge-1\",\"judge-2\",\"judge-3\",\"judge-4\",\"judge-5\"]",
  expect "four joins: still answering" (stateOf (chain (toJoining ++ (allJoin).take 4))) "joining",
  expect "all five join: introduced" (stateOf (chain (toJoining ++ allJoin))) "introduced",
  expect "five joins after a vote: introduced"
    (stateOf (chain (toVotingWith panel ++ votesBy panel (fun _ => true) ++ [draftS] ++ allJoin))) "introduced",
  expect "a concurrence is not a join: the author revises"
    (stateOf (chain (toJoining ++ allJoinBut [3] "concur"))) "drafting",
  expect "the revision is the first" (replayField (chain (toJoining ++ allJoinBut [3] "concur")) "revision") "1",
  expect "five concurrences are not unanimous either"
    (stateOf (chain (toJoining ++ respondAll 0 (fun _ => "concur")))) "drafting",
  expect "one dissent: the author revises" (stateOf (chain (toJoining ++ allJoinBut [4] "dissent"))) "drafting",
  expect "two dissents and a concurrence: the author revises"
    (stateOf (chain (toJoining ++ respondAll 0 (fun k => if k ≤ 2 then "dissent" else if k = 3 then "concur" else "join"))))
    "drafting",
  expect "three dissents refuse the case: open, the case is unproven"
    (stateOf (chain (toJoining ++ allJoinBut [1, 2, 3] "dissent"))) "open",
  expect "a revised draft that wins five joins: introduced"
    (stateOf (chain (toJoining ++ allJoinBut [3] "concur" ++ [draftS 1] ++ allJoin 1))) "introduced",
  expect "the second revision can still win"
    (stateOf (chain (toJoining ++ allJoinBut [3] "concur" ++ [draftS 1] ++ allJoinBut [2] "dissent" 1 ++
      [draftS 2] ++ allJoin 2))) "introduced",
  expect "two revisions without five joins: the case stays open"
    (stateOf (chain (toJoining ++ allJoinBut [3] "concur" ++ [draftS 1] ++ allJoinBut [3] "concur" 1 ++
      [draftS 2] ++ allJoinBut [3] "concur" 2))) "open",
  expectRefused "there is no third revision"
    (stateOf (chain (toJoining ++ allJoinBut [3] "concur" ++ [draftS 1] ++ allJoinBut [3] "concur" 1 ++
      [draftS 2] ++ allJoinBut [3] "concur" 2 ++ [draftS 3]))),
  expect "open after the opinion, kept as a house rule"
    (stateOf (chain (toJoining ++ allJoinBut [1, 2, 3] "dissent" ++ [words "user" "house-rule"]))) "house-rule",
  expect "a gap rule with a stipulation is introduced when the opinion states it and all five join"
    (stateOf (chain ([opening, briefWith (stipCase), confirmS] ++ allConcede 1 ++ [reportS 1 "attack" [],
      draftWith 0 stipOpinion] ++ allJoin))) "introduced",

  -- terminal states take nothing
  expectRefused "nothing after introduced"
    (stateOf (chain (toJoining ++ allJoin ++ [words "user" "withdraw"]))),
  expectRefused "nothing after withdrawn" (stateOf (chain (toAnswer ++ [words "user" "withdraw", answerS 1 [(1, 1)]]))),
  expectRefused "nothing after a house rule"
    (stateOf (chain (toRefuted ++ [words "user" "house-rule", words "user" "house-rule"]))),
  expectRefused "refuted can't be withdrawn" (stateOf (chain (toRefuted ++ [words "user" "withdraw"]))),

  -- refused events
  expectRefused "a vote during an attack round" (stateOf (chain [opening, briefS, confirmS, voteS 1 true])),
  expectRefused "a judge files twice" (stateOf (chain [opening, briefS, confirmS, concede 1 1, concede 1 1])),
  expectRefused "the user files as a judge"
    (stateOf (chain [opening, briefS, confirmS, ("user", "file", [("round", jnat 1), ("refutations", Json.arr #[]),
      ("concedes", jstr "x")])])),
  expectRefused "there is no judge 6" (stateOf (chain [opening, briefS, confirmS, concede 6 1])),
  expectRefused "a filing for the wrong round" (stateOf (chain [opening, briefS, confirmS, concede 1 2])),
  expectRefused "the user writes the brief" (stateOf (chain [opening, ("user", "brief", [("case", goodCase)])])),
  expectRefused "a premise pointing nowhere"
    (stateOf (chain [opening, briefWith (caseJ [stepJ 1 ["S2"] (some (source "103.1"))])])),
  expectRefused "a premise that isn't a fact"
    (stateOf (chain [opening, briefWith (caseJ [stepJ 1 ["F9"] (some (source "103.1"))])])),
  expectRefused "a step with no source that isn't labelled an assumption"
    (stateOf (chain [opening, briefWith (caseJ [stepJ 1 ["F1"] none (assumption := false)])])),
  expectRefused "a source that isn't pinned"
    (stateOf (chain [opening, briefWith (caseJ [stepJ 1 ["F1"] (some (source "103.1" "abc"))])])),
  expectRefused "steps out of order"
    (stateOf (chain [opening, briefWith (caseJ [stepJ 2 ["F1"] (some (source "103.1")),
      stepJ 1 ["F1"] (some (source "103.1"))])])),
  expectRefused "a refutation of a step the case doesn't have" (stateOf (chain [opening, briefS, confirmS, refute 1 1 9])),
  expectRefused "a refutation with no evidence"
    (stateOf (chain [opening, briefS, confirmS, refuteWith 1 1 (refutationJ 1 [stepJ 1 ["C1"] none])])),
  expectRefused "a report citing a refutation nobody filed"
    (stateOf (chain ([opening, briefS, confirmS] ++ allConcede 1 ++ [reportS 1 "attack" [(3, 1)]]))),
  expectRefused "an answer that leaves a refutation unanswered" (stateOf (chain (toAnswer ++ [answerS 1 []]))),
  expectRefused "a vote with no reason"
    (stateOf (chain (toVoting ++ [("judge-1", "vote", [("convinced", toJson true), ("reason", jstr ""),
      ("evidence", evidenceJ)])]))),
  expectRefused "a vote with no evidence"
    (stateOf (chain (toVoting ++ [("judge-1", "vote", [("convinced", toJson true), ("reason", jstr "settled")])]))),
  expectRefused "a vote whose evidence isn't pinned"
    (stateOf (chain (toVoting ++ [("judge-1", "vote", [("convinced", toJson true), ("reason", jstr "settled"),
      ("evidence", Json.arr #[source "103.1" "abc"])])]))),
  expectRefused "a concession with no evidence"
    (stateOf (chain [opening, briefS, confirmS, ("judge-1", "file", [("round", jnat 1), ("refutations", Json.arr #[]),
      ("concedes", jstr "I can't refute it")])])),
  expectRefused "a concession with no reasoning"
    (stateOf (chain [opening, briefS, confirmS, ("judge-1", "file", [("round", jnat 1), ("refutations", Json.arr #[]),
      ("concedes", jstr ""), ("concede_evidence", evidenceJ)])])),
  expectRefused "a stipulation in a case that challenges an official answer"
    (stateOf (chain [opening, briefWith (stipCase "Official ruling on Urborg (2021-03-19)")])),
  expectRefused "a stipulation that quotes a source"
    (stateOf (chain [opening, briefWith (caseJ [stepJ 1 ["F1"] (some (source "103.1")) (stip := true)])])),
  expectRefused "a step that is both a stipulation and an assumption"
    (stateOf (chain [opening, briefWith (caseJ [stepJ 1 ["F1"] none (assumption := true) (stip := true)])])),
  expectRefused "a refutation can't stipulate"
    (stateOf (chain [opening, briefS, confirmS, refuteWith 1 1 (refutationJ 1 [stepJ 1 ["C1"] (some (source "103.3")),
      stipJ 2 ["S1"]])])),
  expectRefused "a judge votes twice" (stateOf (chain (toVoting ++ [voteS 1 true, voteS 1 true]))),
  expectRefused "a judge who conceded on this case has already settled"
    (stateOf (chain (toVoting ++ [voteS 2 true]))),
  expectRefused "a challenge must start with open" (stateOf (chain [briefS])),

  -- refused: the opinion
  expectRefused "the opinion can't be drafted before the judges settle"
    (stateOf (chain [opening, briefS, confirmS, draftS])),
  expectRefused "a judge other than the lowest-numbered convinced one drafts"
    (stateOf (chain (toDrafting ++ [draftWith 0 opinionSteps holdingText 2]))),
  expectRefused "the user drafts the opinion"
    (stateOf (chain (toDrafting ++ [("user", "opinion", [("revision", jnat 0), ("holding", jstr holdingText),
      ("steps", Json.arr opinionSteps.toArray)])]))),
  expectRefused "a holding that isn't the case's rule"
    (stateOf (chain (toDrafting ++ [draftWith 0 opinionSteps "the youngest player always goes first"]))),
  expectRefused "an opinion with no steps" (stateOf (chain (toDrafting ++ [draftWith 0 []]))),
  expectRefused "an opinion resting on an assumption"
    (stateOf (chain (toDrafting ++ [draftWith 0 [stepJ 1 ["F1"] none]]))),
  expectRefused "an opinion whose quote isn't pinned"
    (stateOf (chain (toDrafting ++ [draftWith 0 [stepJ 1 ["F1"] (some (source "103.1" "abc"))]]))),
  expectRefused "an opinion citing a fact the case doesn't have"
    (stateOf (chain (toDrafting ++ [draftWith 0 [stepJ 1 ["F9"] (some (source "103.1"))]]))),
  expectRefused "the first draft is revision 0" (stateOf (chain (toDrafting ++ [draftS 1]))),
  expectRefused "an opinion that adds a stipulation the case doesn't have"
    (stateOf (chain (toDrafting ++ [draftWith 0 stipOpinion]))),
  expectRefused "an opinion that leaves out the case's stipulation"
    (stateOf (chain ([opening, briefWith (stipCase), confirmS] ++ allConcede 1 ++ [reportS 1 "attack" [], draftS]))),
  expectRefused "a response before there is a draft" (stateOf (chain (toDrafting ++ [respondS 1 0 "join"]))),
  expectRefused "a response to the wrong revision" (stateOf (chain (toJoining ++ [respondS 1 1 "join"]))),
  expectRefused "a judge answers the draft twice" (stateOf (chain (toJoining ++ [respondS 1 0 "join", respondS 1 0 "join"]))),
  expectRefused "there is no judge 6 to answer" (stateOf (chain (toJoining ++ [respondS 6 0 "join"]))),
  expectRefused "the user answers the draft"
    (stateOf (chain (toJoining ++ [("user", "respond", [("revision", jnat 0), ("stance", jstr "join"),
      ("reason", jstr "fine"), ("evidence", evidenceJ)])]))),
  expectRefused "a response with no reasoning"
    (stateOf (chain (toJoining ++ [("judge-1", "respond", [("revision", jnat 0), ("stance", jstr "join"),
      ("reason", jstr ""), ("evidence", evidenceJ)])]))),
  expectRefused "a response with no evidence"
    (stateOf (chain (toJoining ++ [("judge-1", "respond", [("revision", jnat 0), ("stance", jstr "join"),
      ("reason", jstr "fine")])]))),
  expectRefused "a response whose evidence isn't pinned"
    (stateOf (chain (toJoining ++ [("judge-1", "respond", [("revision", jnat 0), ("stance", jstr "dissent"),
      ("reason", jstr "no"), ("evidence", Json.arr #[source "103.1" "abc"])])]))),
  expectParseError "a stance that is not join, concur or dissent"
    (stateOf (chain (toJoining ++ [("judge-1", "respond", [("revision", jnat 0), ("stance", jstr "abstain"),
      ("reason", jstr "no"), ("evidence", evidenceJ)])]))),
  expectRefused "the user can't withdraw while the judges answer the draft"
    (stateOf (chain (toJoining ++ [words "user" "withdraw"]))),
  expectRefused "a judge can't vote while the opinion is drafted" (stateOf (chain (toDrafting ++ [voteS 1 true]))),
  expectRefused "no draft once the revisions are used up and the case is open"
    (stateOf (chain (toJoining ++ allJoinBut [1, 2, 3] "dissent" ++ [draftS 1]))),

  -- the hash chain
  expect "two devices act in the same state: fork" (stateOf forked) "fork",
  expect "two opening events: fork" (stateOf (chain [opening] ++ chain [opening] "phone")) "fork",
  expect "an edited event breaks the chain" (stateOf edited) "broken",
  expect "a removed event breaks the chain"
    (stateOf (let r := chain [opening, briefS, confirmS]; [r[0]!, r[2]!])) "broken",
  expect "the files' order doesn't matter" (stateOf (chain toAnswer).reverse) (stateOf (chain toAnswer)),

  -- blindness
  expectNat "judge 3 can't see judges 1 and 2's filings"
    (hiddenFor (chain [opening, briefS, confirmS, concede 1 1, concede 2 1]) 3) 2,
  expectNat "judge 1 sees its own filing" (hiddenFor (chain [opening, briefS, confirmS, concede 1 1, concede 2 1]) 1) 1,
  expectNat "once all five filed, everyone sees all" (hiddenFor (chain ([opening, briefS, confirmS] ++ allConcede 1)) 3) 0,
  expectNat "votes are hidden while voting"
    (hiddenFor (chain (toVotingWith panel ++ [voteS 1 true, voteS 2 false])) 5) 2,
  expectNat "and shown once all have voted" (hiddenFor (chain (toVotingWith panel ++ votesBy panel (fun _ => true))) 5) 0,
  expectNat "the draft opinion is not hidden: the judges must read it to answer it" (hiddenFor (chain toJoining) 3) 0,
  expectNat "responses to the draft are hidden from the other judges"
    (hiddenFor (chain (toJoining ++ [respondS 1 0 "join", respondS 2 0 "dissent"])) 5) 2,
  expectNat "a judge sees its own response"
    (hiddenFor (chain (toJoining ++ [respondS 1 0 "join", respondS 2 0 "dissent"])) 1) 1,
  expectNat "the author sees every response when it revises"
    (hiddenFor (chain (toJoining ++ allJoinBut [3] "concur")) 1) 0,
  expectNat "and the judges see them too when the revision is read"
    (hiddenFor (chain (toJoining ++ allJoinBut [3] "concur" ++ [draftS 1, respondS 2 1 "join"])) 4) 1,

  -- the id and the JSON interface
  expect "the id is the date and 12 hex of the opening event"
    ((replayJson (chain [opening])).getObjValD "id").compress
    s!"\"challenge-20261026-{(hashString (chain [opening]).head!).take 12}\"",
  expect "check refuses an event that doesn't follow the head"
    ((checkJson (chain [opening, briefS]) (mkEvent 2 none "laptop" confirmS)).getObjValD "accepted").compress
    "false",
  expect "check accepts the next event"
    ((checkJson (chain [opening, briefS])
      (mkEvent 2 (some (hashString (chain [opening, briefS]).getLast!)) "laptop" confirmS)).getObjValD "accepted").compress
    "true",
  expect "replay names who acts next"
    ((replayJson (chain ([opening, briefS, confirmS] ++ (allConcede 1).take 3))).getObjValD "next").compress
    "[\"judge-4\",\"judge-5\"]",
  expect "replay says who has answered the draft"
    (replayField (chain (toJoining ++ [respondS 2 0 "join", respondS 4 0 "concur"])) "responded") "[2,4]",

  -- the rule machine
  expect "a current rule goes stale when a source changes"
    ((ruleJson (Json.mkObj [("state", jstr "current"), ("event", jstr "source-changed")])).getObjValD "state").compress
    "\"stale\"",
  expect "a retired rule takes nothing"
    ((ruleJson (Json.mkObj [("state", jstr "retired"), ("event", jstr "challenge-reopened")])).getObjValD "accepted").compress
    "false"]

def main : IO UInt32 := do
  let mut failed := 0
  for (name, ok, detail) in checks do
    if ok then
      IO.println s!"ok    {name}"
    else
      failed := failed + 1
      IO.println s!"FAIL  {name}: {detail}"
  IO.println s!"{checks.length - failed} of {checks.length} passed"
  return (if failed == 0 then 0 else 1)
