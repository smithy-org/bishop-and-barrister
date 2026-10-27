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

def field (j : Json) (k : String) : Except String Json :=
  match j.getObjVal? k with
  | .ok v => .ok v
  | .error _ => .error s!"missing \"{k}\""

def getStr (j : Json) (k : String) : Except String String := do
  match ← field j k with
  | .str s => pure s
  | _ => throw s!"\"{k}\" must be a string"

def getNat (j : Json) (k : String) : Except String Nat := do
  match (← field j k).getNat? with
  | .ok n => pure n
  | .error _ => throw s!"\"{k}\" must be a whole number"

def getBool (j : Json) (k : String) : Except String Bool := do
  match ← field j k with
  | .bool b => pure b
  | _ => throw s!"\"{k}\" must be true or false"

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

def getStrOr (j : Json) (k : String) (d : String) : Except String String :=
  match getOpt j k with
  | some (.str s) => .ok s
  | some _ => .error s!"\"{k}\" must be a string"
  | none => .ok d

def getStrList (j : Json) (k : String) : Except String (List String) := do
  (← getArr j k).mapM fun v =>
    match v with
    | .str s => pure s
    | _ => throw s!"\"{k}\" must be a list of strings"

def parseRef (s : String) : Except String Ref :=
  match s.front, (s.drop 1).toNat? with
  | 'F', some n => .ok (.fact n)
  | 'S', some n => .ok (.step n)
  | 'C', some n => .ok (.caseStep n)
  | _, _ => .error s!"premise \"{s}\" must be F<n> (a fact), S<n> (an earlier step) or C<n> (a step of the case)"

def parseSource (j : Json) : Except String Source := do
  pure {
    doc := ← getStr j "doc", ref := ← getStr j "ref", excerpt := ← getStr j "excerpt",
    textSha256 := ← getStr j "text_sha256" }

def parseStep (j : Json) : Except String Step := do
  let premises ← (← getStrList j "premises").mapM parseRef
  let source ← match getOpt j "source" with
    | some v => some <$> parseSource v
    | none => pure none
  let assumption ← match getOpt j "assumption" with
    | some (.bool b) => pure b
    | some _ => throw "\"assumption\" must be true or false"
    | none => pure false
  pure { id := ← getNat j "id", premises := premises, source := source, assumption := assumption,
         conclusion := ← getStr j "conclusion" }

def parseSteps (j : Json) (k : String) : Except String (List Step) := do
  (← getArr j k).mapM parseStep

def parseFact (j : Json) : Except String Fact := do
  pure { id := ← getNat j "id", text := ← getStr j "text" }

def parseCase (j : Json) : Except String Case := do
  pure {
    facts := ← (← getArr j "facts").mapM parseFact,
    openQuestions := ← getStrList j "open_questions",
    rule := ← getStr j "rule",
    appliesWhen := ← getStrList j "applies_when",
    challenges := ← getStr j "challenges",
    steps := ← parseSteps j "steps" }

def parseGround : String → Except String Ground
  | "not-applicable" => .ok .notApplicable
  | "overridden" => .ok .overridden
  | "misread" => .ok .misread
  | "wrong-fact" => .ok .wrongFact
  | "missing-fact" => .ok .missingFact
  | "counterexample" => .ok .counterexample
  | g => .error s!"unknown ground \"{g}\"; one of not-applicable, overridden, misread, wrong-fact, missing-fact, counterexample"

def parseRefutation (j : Json) : Except String Refutation := do
  pure {
    target := ← getNat j "target", ground := ← parseGround (← getStr j "ground"),
    argument := ← getStr j "argument", steps := ← parseSteps j "steps" }

def parseSlot (j : Json) : Except String Slot := do
  pure { judge := ← getNat j "judge", index := ← getNat j "index" }

def parseStage : String → Except String Stage
  | "attack" => .ok .attack
  | "answers" => .ok .answers
  | s => .error s!"unknown stage \"{s}\"; \"attack\" or \"answers\""

def parseReplyKind : String → Except String ReplyKind
  | "concede" => .ok .concede
  | "fix" => .ok .fix
  | "rebut" => .ok .rebut
  | s => .error s!"unknown reply \"{s}\"; \"concede\", \"fix\" or \"rebut\""

def parseReply (j : Json) : Except String Reply := do
  let steps ← match getOpt j "steps" with
    | some _ => parseSteps j "steps"
    | none => pure []
  pure {
    slot := ← parseSlot j, kind := ← parseReplyKind (← getStr j "kind"), words := ← getStr j "words",
    steps := steps }

def parsePanel : String → Except String Panel
  | "independent" => .ok .independent
  | "single-agent" => .ok .singleAgent
  | s => .error s!"unknown panel \"{s}\"; \"independent\" or \"single-agent\""

def parseActor (s : String) : Except String Actor :=
  if s == "user" then .ok .user
  else if s == "clerk" then .ok .clerk
  else if s == "verifier" then .ok .verifier
  else if s.startsWith "judge-" then
    match (s.drop 6).toNat? with
    | some k => .ok (.judge k)
    | none => .error s!"unknown actor \"{s}\""
  else .error s!"unknown actor \"{s}\"; user, clerk, verifier or judge-<k>"

def actorName : Actor → String
  | .user => "user"
  | .clerk => "clerk"
  | .verifier => "verifier"
  | .judge k => s!"judge-{k}"

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
                  concedes := ← getStrOr j "concedes" "" })
  | "report" =>
    let standing ← (← getArr j "standing").mapM parseSlot
    pure (.report { round := ← getNat j "round", stage := ← parseStage (← getStr j "stage"),
                    passed := ← getBool j "passed", level1Conflict := ← getBool j "level1_conflict",
                    standing := standing })
  | "answer" =>
    let replies ← (← getArr j "replies").mapM parseReply
    let revised ← match getOpt j "case" with
      | some c => some <$> parseCase c
      | none => pure none
    pure (.answer { round := ← getNat j "round", replies := replies, revised := revised,
                    words := ← getStr j "words" })
  | "vote" =>
    pure (.vote { judge := judgeOf, convinced := ← getBool j "convinced", reason := ← getStr j "reason" })
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

def parseAllFrom (i : Nat) : List String → Except String (List Entry)
  | [] => .ok []
  | raw :: rest =>
    match parseEntry raw with
    | .error e => .error s!"event file {i + 1}: {e}"
    | .ok x => (x :: ·) <$> parseAllFrom (i + 1) rest

def parseAll (raws : List String) : Except String (List Entry) := parseAllFrom 0 raws

end Challenge
