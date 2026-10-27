import Challenge.Machine

/-!
# The hash chain, replay and what each judge may see

Each event names the hash of the one before it. `linearize` puts the events in chain order by following those
links from the opening event, so the order the files arrive in doesn't matter. It finds a **fork** when two
events name the same predecessor (two devices acted in the same state), and a **broken** chain when an event
was edited, removed or reordered (some event is no longer reachable from the opening).
-/

namespace Challenge

def children (evs : List Entry) (h : Option String) : List Entry := evs.filter (fun e => e.prev == h)

inductive Pick where
  | none
  | one (e : Entry)
  | many

def pick : List Entry → Pick
  | [] => .none
  | [e] => .one e
  | _ :: _ :: _ => .many

def cont : Pick → (Option String → List Entry) → List Entry
  | .one e, k => e :: k (some e.hash)
  | _, _ => []

/-- The chain from `h`, at most `fuel` events long. -/
def follow (evs : List Entry) : Nat → Option String → List Entry
  | 0, _ => []
  | fuel + 1, h => cont (pick (children evs h)) (follow evs fuel)

/-- Some event has a sibling: another event naming the same predecessor. -/
def hasFork (evs : List Entry) : Bool := evs.any (fun e => Nat.ble 2 (children evs e.prev).length)

inductive Linear where
  | ok (l : List Entry)
  | fork
  | broken (why : String)

def linearize (evs : List Entry) : Linear :=
  if hasFork evs then .fork
  else if (follow evs (evs.length + 1) none).length = evs.length then .ok (follow evs (evs.length + 1) none)
  else .broken "an event was edited, removed or reordered: the hash chain doesn't reach every event"

def replay (evs : List Entry) : Outcome :=
  match linearize evs with
  | .ok l => run l
  | .fork => .fork
  | .broken why => .broken why

/-- A judge's filing or vote: what the other judges mustn't see until the round is complete. -/
def isPanelAct (x : Entry) : Bool :=
  match x.event with
  | .file _ | .vote _ => true
  | _ => false

/-- Hidden from judge `k` while the phase that started at `cur` lasts: another judge's filing or vote in it. -/
def hiddenFrom (k cur : Nat) (t : Nat × Entry) : Bool :=
  t.1 == cur && isPanelAct t.2 && !(t.2.actor == Actor.judge k)

/-- The events judge `k` may see. -/
def view (k : Nat) (s : State) (tags : List (Nat × Entry)) : List (Nat × Entry) :=
  tags.filter (fun t => !hiddenFrom k s.since t)

end Challenge
