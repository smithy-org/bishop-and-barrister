import Challenge

/-!
# The `bab-challenge` command

The command-line tool the Python wrapper runs. It reads one JSON object on stdin and prints one JSON reply on
stdout: `replay`, `check`, `view --judge k` and `rule` are in `Challenge.Api`, and `version` prints the version.
-/

open Lean Challenge

/-- The help text, printed for a command it doesn't know. -/
def usage : String :=
  "usage: bab-challenge replay | check | view --judge <k> | rule | version
  replay  stdin {\"events\": [<event file text>...]}                → the state and who acts next
  check   stdin {\"events\": [...], \"proposed\": <event file text>}  → accepted, or the reasons it's refused
  view    stdin {\"events\": [...]}                                 → the event files judge k may see
  rule    stdin {\"state\": \"current\", \"event\": \"source-changed\"} → the rule's next state"

/-- The tool's version and the event format it reads. -/
def version : String := "bab-challenge 0.2.0 (challenge format v1)"

/-- Reads a stream to its end. -/
partial def readAll (h : IO.FS.Stream) (acc : String) : IO String := do
  let line ← h.getLine
  if line.isEmpty then pure acc else readAll h (acc ++ line)

/-- The event files' text from the input's `events` list. -/
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

/-- Runs one command: reads stdin, prints the reply, and exits 0, or 2 if the input or the command is wrong. -/
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
