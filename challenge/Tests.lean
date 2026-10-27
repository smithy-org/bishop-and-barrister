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
def allVote (convinced : Nat → Bool) : List Spec := panel.map fun k => voteS k (convinced k)

/-- Judge 1's refutation fails verification, so nothing stands; not everyone conceded, so the judges vote. -/
def toVoting : List Spec :=
  [opening, briefS, confirmS, refute 1 1 1] ++ (List.range' 2 4).map (concede · 1) ++ [reportS 1 "attack" []]
def toAnswer : List Spec :=
  [opening, briefS, confirmS, refute 1 1 1] ++ (List.range' 2 4).map (concede · 1) ++ [reportS 1 "attack" [(1, 1)]]

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
def expectNat (name : String) (actual expected : Nat) : Check :=
  (name, actual == expected, s!"got {actual}, expected {expected}")

/-- The user revises the case; the judges attack it again. -/
def roundSpecs (n : Nat) : List Spec :=
  [refute 1 n 1] ++ (List.range' 2 4).map (concede · n) ++
  [reportS n "attack" [(1, 1)], replyS "fix" n [(1, 1)] (some goodCase), reportS n "answers" [(1, 1)]]

/-- The user concedes, so nothing is answered; the judges settle, and all five are not convinced. -/
def toRefuted : List Spec :=
  toAnswer ++ [replyS "concede" 1 [(1, 1)], reportS 1 "answers" [(1, 1)]] ++ allVote (fun _ => false)

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
  expect "nothing standing, but not everyone conceded: the judges vote" (stateOf (chain toVoting)) "voting",
  expect "everyone conceded on the unchanged case: introduced, with no separate vote"
    (stateOf (chain ([opening, briefS, confirmS] ++ allConcede 1 ++ [reportS 1 "attack" []]))) "introduced",
  expect "five convinced: introduced" (stateOf (chain (toVoting ++ allVote (fun _ => true)))) "introduced",
  expect "one not convinced: no consensus, another round" (stateOf (chain (toVoting ++ allVote (· != 4)))) "attack",
  expect "two not convinced: no consensus, another round" (stateOf (chain (toVoting ++ allVote (· ≤ 3)))) "attack",
  expect "three not convinced and nothing stands: the case is unproven, so open"
    (stateOf (chain (toVoting ++ allVote (· > 3)))) "open",
  expect "five not convinced and nothing stands: open"
    (stateOf (chain (toVoting ++ allVote (fun _ => false)))) "open",
  expect "three not convinced and a refutation stands: refuted"
    (stateOf (chain (toAnswer ++ [replyS "concede" 1 [(1, 1)], reportS 1 "answers" [(1, 1)]] ++ allVote (· > 3)))) "refuted",
  expect "all convinced, but a verified refutation stands: refuted"
    (stateOf (chain (toAnswer ++ [replyS "concede" 1 [(1, 1)], reportS 1 "answers" [(1, 1)]] ++
      allVote (fun _ => true)))) "refuted",
  expect "a failed verifier report: open, the case is unproven"
    (stateOf (chain ([opening, briefS, confirmS] ++ allConcede 1 ++ [reportS 1 "attack" [] (passed := false)]))) "open",
  expect "a level 1 conflict: refuted"
    (stateOf (chain ([opening, briefS, confirmS] ++ allConcede 1 ++ [reportS 1 "attack" [] (conflict := true)]))) "refuted",
  expect "a case resting on an assumption: open, it is unproven"
    (stateOf (chain ([opening, briefWith (caseJ [stepJ 1 ["F1"] none]), confirmS] ++ allConcede 1 ++
      [reportS 1 "attack" []]))) "open",
  expect "a single-agent panel can't introduce: open"
    (stateOf (chain ([opening "single-agent", briefS, confirmS] ++ allConcede 1 ++ [reportS 1 "attack" []]))) "open",
  expect "refuted, kept as a house rule" (stateOf (chain (toRefuted ++ [words "user" "house-rule"]))) "house-rule",
  expect "open, kept as a house rule"
    (stateOf (chain ([opening, briefWith (caseJ [stepJ 1 ["F1"] none]), confirmS] ++ allConcede 1 ++
      [reportS 1 "attack" [], words "user" "house-rule"]))) "house-rule",
  expect "a verified refutation stands: answer" (stateOf (chain toAnswer)) "answer",
  expect "answered: verify the answers" (stateOf (chain (toAnswer ++ [answerS 1 [(1, 1)]]))) "verify-answers",
  expect "answers verified, case unchanged: the judges settle"
    (stateOf (chain (toAnswer ++ [answerS 1 [(1, 1)], reportS 1 "answers" []]))) "voting",
  expect "a refutation conceded without a fix: the judges settle, nothing closes it for them"
    (stateOf (chain (toAnswer ++ [replyS "concede" 1 [(1, 1)], reportS 1 "answers" [(1, 1)]]))) "voting",
  expect "the case revised: the judges attack it again, round 2"
    (stateOf (chain (toAnswer ++ [replyS "fix" 1 [(1, 1)] (some goodCase), reportS 1 "answers" []]))) "attack",
  expectRefused "judges can't file once the panel is voting"
    (stateOf (chain (toAnswer ++ [replyS "concede" 1 [(1, 1)], reportS 1 "answers" [(1, 1)], refute 1 2 1]))),
  expect "three revised rounds: the judges settle"
    (stateOf (chain ([opening, briefS, confirmS] ++ (List.range' 1 3).flatMap roundSpecs))) "voting",
  expect "one still not convinced after the last round: no consensus, so open"
    (stateOf (chain ([opening, briefS, confirmS] ++ (List.range' 1 3).flatMap roundSpecs ++ allVote (· ≤ 4)))) "open",
  expect "open, reopened with new facts: briefed"
    (stateOf (chain ([opening, briefS, confirmS] ++ (List.range' 1 3).flatMap roundSpecs ++ allVote (· ≤ 4) ++
      [("user", "reopen", [("case", goodCase), ("words", jstr "a new ruling came out")])]))) "briefed",
  expect "a stipulation in a gap case: briefed" (stateOf (chain [opening, briefWith (stipCase)])) "briefed",
  expect "a gap rule with a stipulation can be introduced"
    (stateOf (chain ([opening, briefWith (stipCase), confirmS] ++ allConcede 1 ++ [reportS 1 "attack" []]))) "introduced",
  expect "withdrawn while answering" (stateOf (chain (toAnswer ++ [words "user" "withdraw"]))) "withdrawn",

  -- terminal states take nothing
  expectRefused "nothing after introduced"
    (stateOf (chain (toVoting ++ allVote (fun _ => true) ++ [words "user" "withdraw"]))),
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
  expectRefused "a challenge must start with open" (stateOf (chain [briefS])),

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
  expectNat "votes are hidden while voting" (hiddenFor (chain (toVoting ++ [voteS 1 true, voteS 2 false])) 5) 2,
  expectNat "and shown once all have voted" (hiddenFor (chain (toVoting ++ allVote (fun _ => true))) 5) 0,

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
