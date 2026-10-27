import Lean.Data.Json
import Challenge.Parse
import Challenge.Chain
import Challenge.Rule

/-!
# The JSON interface

What `bab-challenge` prints for `replay`, `check`, `view --judge k` and `rule`. Every reply is one JSON object
with `"ok"`; a refusal says why.
-/

namespace Challenge
open Lean

def slotJson (sl : Slot) : Json := Json.mkObj [("judge", toJson sl.judge), ("index", toJson sl.index)]

/-- `challenge-<YYYYMMDD>-<12 hex>`: the opening event's date and the start of its hash. -/
def challengeId (opening : Entry) : String :=
  let date := (opening.time.take 10).replace "-" ""
  s!"challenge-{date}-{opening.hash.take 12}"

def Phase.filed : Phase → List Nat
  | .attack _ _ fs _ | .verify _ _ fs | .answer _ _ fs _ | .verifyAnswers _ _ fs _ => fs.map (·.judge)
  | _ => []

def Phase.voted : Phase → List Nat
  | .voting _ _ vs _ => vs.map (·.judge)
  | .introduced e => e.votes.map (·.judge)
  | _ => []

def Phase.standing : Phase → List Slot
  | .answer _ _ _ r => r.standing
  | _ => []

def Phase.why : Phase → Option String
  | .refuted _ w | .open_ _ w => some w
  | .introduced _ => some "all seven judges were convinced"
  | _ => none

def panelName : Panel → String
  | .independent => "independent"
  | .singleAgent => "single-agent"

def entryJson (x : Entry) : Json :=
  Json.mkObj [("seq", toJson x.seq), ("actor", toJson (actorName x.actor)), ("device", toJson x.device),
    ("hash", toJson x.hash)]

def stateJson (s : State) (tags : List (Nat × Entry)) : Json :=
  let entries := tags.map (·.2)
  Json.mkObj [
    ("ok", toJson true),
    ("id", toJson (entries.head?.map challengeId)),
    ("state", toJson s.phase.name),
    ("round", toJson s.phase.round),
    ("panel", toJson (panelName s.panel)),
    ("next", toJson ((owed s.phase).map actorName).toArray),
    ("settled", toJson s.phase.settled),
    ("why", toJson s.phase.why),
    ("filed", toJson s.phase.filed.toArray),
    ("voted", toJson s.phase.voted.toArray),
    ("standing", Json.arr (s.phase.standing.map slotJson).toArray),
    ("head", toJson s.head),
    ("next_seq", toJson entries.length),
    ("case_seq", toJson (if s.phase matches .unopened | .draft then none else some s.caseSeq)),
    ("since", toJson s.since)]

/-- Every predecessor that two or more events name, with those events. -/
def forkJson (evs : List Entry) : Json :=
  let parents := (evs.map (·.prev)).eraseDups.filter (fun h => (children evs h).length ≥ 2)
  Json.arr (parents.map fun h =>
    Json.mkObj [("parent", toJson h), ("events", Json.arr ((children evs h).map entryJson).toArray)]).toArray

def failJson (key : String) (value : Json) : Json := Json.mkObj [("ok", toJson false), (key, value)]

def outcomeJson (evs : List Entry) : Outcome → Json
  | .state s tags => stateJson s tags
  | .fork => failJson "fork" (forkJson evs)
  | .broken why => failJson "broken" (toJson why)
  | .refused seq why =>
    failJson "refused" (Json.mkObj [("seq", toJson seq), ("why", toJson (why.splitOn "; ").toArray)])

/-- `bab-challenge replay`: the events → the state, the next action and who owes it. -/
def replayJson (raws : List String) : Json :=
  match parseAll raws with
  | .error e => failJson "error" (toJson e)
  | .ok evs => outcomeJson evs (replay evs)

def refuseJson (reasons : List String) : Json :=
  Json.mkObj [("ok", toJson true), ("accepted", toJson false), ("reasons", toJson reasons.toArray)]

/-- `bab-challenge check`: would this proposed event be accepted after these? -/
def checkJson (raws : List String) (proposed : String) : Json :=
  match parseAll raws, parseEntry proposed with
  | .error e, _ => failJson "error" (toJson e)
  | _, .error e => refuseJson [s!"the proposed event: {e}"]
  | .ok evs, .ok p =>
    match replay evs with
    | .state s _ =>
      if p.prev ≠ s.head then
        refuseJson ["the proposed event must follow the last event: its \"prev\" must be the last event's hash"]
      else if p.seq ≠ evs.length then refuseJson [s!"the proposed event's \"seq\" must be {evs.length}"]
      else match replay (evs ++ [p]) with
        | .state s' tags' =>
          Json.mkObj [("ok", toJson true), ("accepted", toJson true), ("hash", toJson p.hash),
            ("state", stateJson s' tags')]
        | .refused _ why => refuseJson (why.splitOn "; ")
        | _ => refuseJson ["the proposed event doesn't extend the chain"]
    | other => failJson "replay" (outcomeJson evs other)

/-- `bab-challenge view --judge k`: the event files judge `k` may see, in chain order. -/
def viewJson (raws : List String) (k : Nat) : Json :=
  match parseAll raws with
  | .error e => failJson "error" (toJson e)
  | .ok evs =>
    match replay evs with
    | .state s tags =>
      let table := raws.map (fun r => (hashString r, r))
      let visible := view k s tags
      Json.mkObj [("ok", toJson true), ("judge", toJson k),
        ("events", toJson (visible.map (fun t => (table.lookup t.2.hash).getD "")).toArray),
        ("hidden", toJson (tags.length - visible.length)), ("state", stateJson s tags)]
    | other => outcomeJson evs other

/-- `bab-challenge rule`: one transition of an introduced rule. -/
def ruleJson (j : Json) : Json :=
  match getStr j "state", getStr j "event" with
  | .ok st, .ok ev =>
    match parseRuleState st, parseRuleEvent ev with
    | some s, some e =>
      match ruleStep s e with
      | some s' => Json.mkObj [("ok", toJson true), ("accepted", toJson true), ("state", toJson s'.name)]
      | none => refuseJson [s!"a {st} rule can't take \"{ev}\""]
    | none, _ => failJson "error" (toJson s!"unknown rule state \"{st}\"")
    | _, none => failJson "error" (toJson s!"unknown rule event \"{ev}\"")
  | .error e, _ | _, .error e => failJson "error" (toJson e)

end Challenge
