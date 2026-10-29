import Lean.Data.Json.Parser
import Lean.Data.Json.FromToJson
import Challenge.Types
import Challenge.Sha256

/-!
# Reading event files

An event file is one JSON object. Its hash is the SHA-256 of the file's exact text, which is why the Python
wrapper passes each file's text unchanged rather than the parsed object.

```json
{"v": 1, "seq": 0, "prev": null, "actor": "user", "device": "laptop", "time": "2026-10-26T10:00:00Z",
 "type": "open", "statement": "...", "panel": "independent"}
```
-/

namespace Challenge
open Lean

/-- A required field of a JSON object. -/
def field (j : Json) (k : String) : Except String Json :=
  match j.getObjVal? k with
  | .ok v => .ok v
  | .error _ => .error s!"missing \"{k}\""

/-- A required string field. -/
def getStr (j : Json) (k : String) : Except String String := do
  match ← field j k with
  | .str s => pure s
  | _ => throw s!"\"{k}\" must be a string"

/-- A required whole-number field. -/
def getNat (j : Json) (k : String) : Except String Nat := do
  match (← field j k).getNat? with
  | .ok n => pure n
  | .error _ => throw s!"\"{k}\" must be a whole number"

/-- A required true-or-false field. -/
def getBool (j : Json) (k : String) : Except String Bool := do
  match ← field j k with
  | .bool b => pure b
  | _ => throw s!"\"{k}\" must be true or false"

/-- A required list field. -/
def getArr (j : Json) (k : String) : Except String (List Json) := do
  match ← field j k with
  | .arr a => pure a.toList
  | _ => throw s!"\"{k}\" must be a list"

/-- An optional field; `null` counts as absent. -/
def getOpt (j : Json) (k : String) : Option Json :=
  match j.getObjVal? k with
  | .ok Json.null => none
  | .ok v => some v
  | .error _ => none

/-- An optional string field, or `d` if it is absent. -/
def getStrOr (j : Json) (k : String) (d : String) : Except String String :=
  match getOpt j k with
  | some (.str s) => .ok s
  | some _ => .error s!"\"{k}\" must be a string"
  | none => .ok d

/-- A required list of strings. -/
def getStrList (j : Json) (k : String) : Except String (List String) := do
  (← getArr j k).mapM fun v =>
    match v with
    | .str s => pure s
    | _ => throw s!"\"{k}\" must be a list of strings"

/-- Reads a premise: `F<n>`, `S<n>` or `C<n>`. -/
def parseRef (s : String) : Except String Ref :=
  match s.front, (s.drop 1).toNat? with
  | 'F', some n => .ok (.fact n)
  | 'S', some n => .ok (.step n)
  | 'C', some n => .ok (.caseStep n)
  | _, _ => .error s!"premise \"{s}\" must be F<n> (a fact), S<n> (an earlier step) or C<n> (a step of the case)"

/-- Reads a quoted source. -/
def parseSource (j : Json) : Except String Source := do
  pure {
    doc := ← getStr j "doc", ref := ← getStr j "ref", excerpt := ← getStr j "excerpt",
    textSha256 := ← getStr j "text_sha256" }

/-- Reads an optional list of sources; absent means none. -/
def parseSources (j : Json) (k : String) : Except String (List Source) :=
  match getOpt j k with
  | some _ => do (← getArr j k).mapM parseSource
  | none => pure []

/-- Reads a step. `source`, `assumption` and `stipulation` may be left out. -/
def parseStep (j : Json) : Except String Step := do
  let premises ← (← getStrList j "premises").mapM parseRef
  let source ← match getOpt j "source" with
    | some v => some <$> parseSource v
    | none => pure none
  let assumption ← match getOpt j "assumption" with
    | some (.bool b) => pure b
    | some _ => throw "\"assumption\" must be true or false"
    | none => pure false
  let stipulation ← match getOpt j "stipulation" with
    | some (.bool b) => pure b
    | some _ => throw "\"stipulation\" must be true or false"
    | none => pure false
  pure { id := ← getNat j "id", premises := premises, source := source, assumption := assumption,
         stipulation := stipulation, conclusion := ← getStr j "conclusion" }

/-- Reads a list of steps. -/
def parseSteps (j : Json) (k : String) : Except String (List Step) := do
  (← getArr j k).mapM parseStep

/-- Reads a fact. -/
def parseFact (j : Json) : Except String Fact := do
  pure { id := ← getNat j "id", text := ← getStr j "text" }

/-- Reads a case. -/
def parseCase (j : Json) : Except String Case := do
  pure {
    facts := ← (← getArr j "facts").mapM parseFact,
    openQuestions := ← getStrList j "open_questions",
    rule := ← getStr j "rule",
    appliesWhen := ← getStrList j "applies_when",
    challenges := ← getStr j "challenges",
    steps := ← parseSteps j "steps" }

/-- Reads a refutation's ground, such as `not-applicable`. -/
def parseGround : String → Except String Ground
  | "not-applicable" => .ok .notApplicable
  | "overridden" => .ok .overridden
  | "misread" => .ok .misread
  | "wrong-fact" => .ok .wrongFact
  | "missing-fact" => .ok .missingFact
  | "counterexample" => .ok .counterexample
  | g => .error s!"unknown ground \"{g}\"; one of not-applicable, overridden, misread, wrong-fact, missing-fact, counterexample"

/-- Reads a refutation. -/
def parseRefutation (j : Json) : Except String Refutation := do
  pure {
    target := ← getNat j "target", ground := ← parseGround (← getStr j "ground"),
    argument := ← getStr j "argument", steps := ← parseSteps j "steps" }

/-- Reads a slot: a judge and the number of its refutation. -/
def parseSlot (j : Json) : Except String Slot := do
  pure { judge := ← getNat j "judge", index := ← getNat j "index" }

/-- Reads a report's stage: `attack` or `answers`. -/
def parseStage : String → Except String Stage
  | "attack" => .ok .attack
  | "answers" => .ok .answers
  | s => .error s!"unknown stage \"{s}\"; \"attack\" or \"answers\""

/-- Reads a response's stance: `join`, `concur` or `dissent`. -/
def parseStance : String → Except String Stance
  | "join" => .ok .join
  | "concur" => .ok .concur
  | "dissent" => .ok .dissent
  | s => .error s!"unknown stance \"{s}\"; \"join\", \"concur\" or \"dissent\""

/-- Reads a reply's kind: `concede`, `fix` or `rebut`. -/
def parseReplyKind : String → Except String ReplyKind
  | "concede" => .ok .concede
  | "fix" => .ok .fix
  | "rebut" => .ok .rebut
  | s => .error s!"unknown reply \"{s}\"; \"concede\", \"fix\" or \"rebut\""

/-- Reads a reply. A rebuttal's `steps` may be left out of the others. -/
def parseReply (j : Json) : Except String Reply := do
  let steps ← match getOpt j "steps" with
    | some _ => parseSteps j "steps"
    | none => pure []
  pure {
    slot := ← parseSlot j, kind := ← parseReplyKind (← getStr j "kind"), words := ← getStr j "words",
    steps := steps }

/-- Reads a panel: `independent` or `single-agent`. -/
def parsePanel : String → Except String Panel
  | "independent" => .ok .independent
  | "single-agent" => .ok .singleAgent
  | s => .error s!"unknown panel \"{s}\"; \"independent\" or \"single-agent\""

/-- Reads an actor: `user`, `clerk`, `verifier` or `judge-<k>`. -/
def parseActor (s : String) : Except String Actor :=
  if s == "user" then .ok .user
  else if s == "clerk" then .ok .clerk
  else if s == "verifier" then .ok .verifier
  else if s.startsWith "judge-" then
    match (s.drop 6).toNat? with
    | some k => .ok (.judge k)
    | none => .error s!"unknown actor \"{s}\""
  else .error s!"unknown actor \"{s}\"; user, clerk, verifier or judge-<k>"

/-- The actor's name, as event files write it. -/
def actorName : Actor → String
  | .user => "user"
  | .clerk => "clerk"
  | .verifier => "verifier"
  | .judge k => s!"judge-{k}"

/-- Reads the event from its `type` and fields. A judge's number comes from the actor, never from the event's fields. -/
def parseEvent (actor : Actor) (j : Json) : Except String Event := do
  let judgeOf := match actor with
    | .judge k => k
    | _ => 0
  match ← getStr j "type" with
  | "open" => pure (.start (← getStr j "statement") (← parsePanel (← getStr j "panel")))
  | "brief" => pure (.brief (← parseCase (← field j "case")))
  | "edit" => pure (.edit (← parseCase (← field j "case")) (← getStr j "words"))
  | "confirm" => pure (.confirm (← getStr j "words"))
  | "file" =>
    let refutations ← (← getArr j "refutations").mapM parseRefutation
    pure (.file { judge := judgeOf, round := ← getNat j "round", refutations := refutations,
                  concedes := ← getStrOr j "concedes" "", concedeEvidence := ← parseSources j "concede_evidence" })
  | "report" =>
    let standing ← (← getArr j "standing").mapM parseSlot
    let rebutted ← if (getOpt j "rebutted").isSome then (← getArr j "rebutted").mapM parseSlot else pure []
    pure (.report { round := ← getNat j "round", stage := ← parseStage (← getStr j "stage"),
                    passed := ← getBool j "passed", level1Conflict := ← getBool j "level1_conflict",
                    standing := standing, rebutted := rebutted })
  | "answer" =>
    let replies ← (← getArr j "replies").mapM parseReply
    let revised ← match getOpt j "case" with
      | some c => some <$> parseCase c
      | none => pure none
    pure (.answer { round := ← getNat j "round", replies := replies, revised := revised,
                    words := ← getStr j "words" })
  | "vote" =>
    pure (.vote { judge := judgeOf, convinced := ← getBool j "convinced", reason := ← getStr j "reason",
                  evidence := ← parseSources j "evidence" })
  | "opinion" =>
    pure (.opinion { author := judgeOf, revision := ← getNat j "revision", holding := ← getStr j "holding",
                     steps := ← parseSteps j "steps" })
  | "respond" =>
    pure (.respond { judge := judgeOf, revision := ← getNat j "revision",
                     stance := ← parseStance (← getStr j "stance"), reason := ← getStr j "reason",
                     evidence := ← parseSources j "evidence" })
  | "withdraw" => pure (.withdraw (← getStr j "words"))
  | "house-rule" => pure (.houseRule (← getStr j "words"))
  | "reopen" =>
    pure (.reopen (← parseCase (← field j "case")) (← parsePanel (← getStrOr j "panel" "independent"))
      (← getStr j "words"))
  | t => throw s!"unknown event type \"{t}\""

/-- One event file's text. -/
def parseEntry (raw : String) : Except String Entry := do
  let j ← Json.parse raw
  let v ← getNat j "v"
  if v ≠ 1 then throw s!"event format version {v} isn't supported"
  let actor ← parseActor (← getStr j "actor")
  let prev ← match getOpt j "prev" with
    | some (.str h) => pure (some h)
    | some _ => throw "\"prev\" must be the previous event's hash, or null"
    | none => pure none
  pure {
    hash := hashString raw, prev := prev, seq := ← getNat j "seq", actor := actor,
    device := ← getStr j "device", time := ← getStr j "time", event := ← parseEvent actor j }

/-- Reads event files, numbering them from `i + 1` in errors. -/
def parseAllFrom (i : Nat) : List String → Except String (List Entry)
  | [] => .ok []
  | raw :: rest =>
    match parseEntry raw with
    | .error e => .error s!"event file {i + 1}: {e}"
    | .ok x => (x :: ·) <$> parseAllFrom (i + 1) rest

/-- Reads every event file, or says which one can't be read. -/
def parseAll (raws : List String) : Except String (List Entry) := parseAllFrom 0 raws

end Challenge
