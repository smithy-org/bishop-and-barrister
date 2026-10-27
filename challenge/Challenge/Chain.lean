import Challenge.Machine

/-!
# The hash chain, replay and what each judge may see

Each event names the hash of the one before it. `linearize` puts the events in chain order by following those
links from the opening event, so the order the files arrive in doesn't matter. It finds a **fork** when two
events name the same predecessor (two devices acted in the same state), and a **broken** chain when an event
was edited, removed or reordered (some event is no longer reachable from the opening).

## Main definitions

* `linearize`: the events in chain order, or a fork, or a broken chain.
* `replay`: the challenge's outcome from its event files, in any order.
* `view`: the events judge `k` may see.
-/

namespace Challenge

/-- The events that name `h` as their predecessor. -/
def children (evs : List Entry) (h : Option String) : List Entry := evs.filter (fun e => e.prev == h)

/-- How many events follow a given one: none, exactly one, or more (a fork). -/
inductive Pick where
  /-- No event follows: the chain ends here. -/
  | none
  /-- Exactly one event follows. -/
  | one (e : Entry)
  /-- Two or more events follow: a fork. -/
  | many

/-- Sorts a list of children into none, one or many. -/
def pick : List Entry → Pick
  | [] => .none
  | [e] => .one e
  | _ :: _ :: _ => .many

/-- Adds the one next event to the chain and continues from its hash; stops at none or many. -/
def cont : Pick → (Option String → List Entry) → List Entry
  | .one e, k => e :: k (some e.hash)
  | _, _ => []

/-- The chain from `h`, at most `fuel` events long. -/
def follow (evs : List Entry) : Nat → Option String → List Entry
  | 0, _ => []
  | fuel + 1, h => cont (pick (children evs h)) (follow evs fuel)

/-- Some event has a sibling: another event naming the same predecessor. -/
def hasFork (evs : List Entry) : Bool := evs.any (fun e => Nat.ble 2 (children evs e.prev).length)

/-- The result of putting the events in chain order. -/
inductive Linear where
  /-- The events in chain order, from the opening event. -/
  | ok (l : List Entry)
  /-- Two events name the same predecessor. -/
  | fork
  /-- Some event isn't reachable from the opening event, and why. -/
  | broken (why : String)

/-- Puts the events in chain order, or reports a fork or a broken chain. Forks are checked first. -/
def linearize (evs : List Entry) : Linear :=
  if hasFork evs then .fork
  else if (follow evs (evs.length + 1) none).length = evs.length then .ok (follow evs (evs.length + 1) none)
  else .broken "an event was edited, removed or reordered: the hash chain doesn't reach every event"

/-- Replays a challenge from its event files, in any order: chain them, then run the state machine. -/
def replay (evs : List Entry) : Outcome :=
  match linearize evs with
  | .ok l => run l
  | .fork => .fork
  | .broken why => .broken why

/-- A judge's filing, vote or response to the draft opinion: what the other judges mustn't see until the phase is
complete. (The draft itself is not hidden: the judges must read it to answer it.) -/
def isPanelAct (x : Entry) : Bool :=
  match x.event with
  | .file _ | .vote _ | .respond _ => true
  | _ => false

/-- Hidden from judge `k` while the phase that started at `cur` lasts: another judge's filing or vote in it. -/
def hiddenFrom (k cur : Nat) (t : Nat × Entry) : Bool :=
  t.1 == cur && isPanelAct t.2 && !(t.2.actor == Actor.judge k)

/-- The events judge `k` may see. -/
def view (k : Nat) (s : State) (tags : List (Nat × Entry)) : List (Nat × Entry) :=
  tags.filter (fun t => !hiddenFrom k s.since t)

end Challenge
