import Challenge
open Lean Challenge

def usage : String :=
  "usage: bab-challenge replay | check | view --judge <k> | rule | version
  replay  stdin {\"events\": [<event file text>...]}                → the state and who acts next
  check   stdin {\"events\": [...], \"proposed\": <event file text>}  → accepted, or the reasons it's refused
  view    stdin {\"events\": [...]}                                 → the event files judge k may see
  rule    stdin {\"state\": \"current\", \"event\": \"source-changed\"} → the rule's next state"

def version : String := "bab-challenge 0.2.0 (challenge format v1)"

partial def readAll (h : IO.FS.Stream) (acc : String) : IO String := do
  let line ← h.getLine
  if line.isEmpty then pure acc else readAll h (acc ++ line)

def eventsOf (j : Json) : Except String (List String) := do
  (← getArr j "events").mapM fun v =>
    match v with
    | .str s => pure s
    | _ => throw "\"events\" must be a list of event files' text"

/-- The reply to one command, or why the input can't be read. -/
def respond (args : List String) (j : Json) : Except String Json := do
  match args with
  | ["rule"] => pure (ruleJson j)
  | ["replay"] => pure (replayJson (← eventsOf j))
  | ["check"] => pure (checkJson (← eventsOf j) (← getStr j "proposed"))
  | ["view", "--judge", k] =>
    match k.toNat? with
    | some n => pure (viewJson (← eventsOf j) n)
    | none => throw usage
  | _ => throw usage

def main (args : List String) : IO UInt32 := do
  if args == ["version"] || args == ["--version"] then
    IO.println version
    return 0
  if !(args matches ["replay"] | ["check"] | ["rule"] | ["view", "--judge", _]) then
    IO.eprintln usage
    return 2
  let input ← readAll (← IO.getStdin) ""
  match Json.parse input >>= respond args with
  | .ok out =>
    IO.println out.compress
    return 0
  | .error e =>
    IO.eprintln s!"bab-challenge: {e}"
    return 2
