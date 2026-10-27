import Challenge.Chain

/-!
# The six guarantees

Checked on every build; `Audit.lean` fails the build if any of them is missing or rests on `sorry`.

1. `no_unearned_rule`: an introduced challenge had seven convinced judges, a passing verifier report, no level 1
   conflict, no unsupported step and an independent panel.
2. `determinism`: the state depends only on which events there are, not the order the files are read in, so
   every device holding the same events computes the same state.
3. `terminal_final_*`, `refuted_only_to_house_rule`: no event leaves `introduced`, `withdrawn` or `house-rule`;
   the only way out of `refuted` is the user's request to keep it as a house rule.
4. `blindness`: what judge *k* is shown contains no other judge's filing or vote from the phase in progress.
5. `progress`: every state that isn't settled names who acts next.
6. `forks_caught`: two different events with the same predecessor make replay report a fork, never a silent
   choice.
-/

namespace Challenge

/-! ## 1. No unearned rule -/

theorem every_judge_convinced (e : Earned) :
    ∀ k ∈ judges, ∃ v ∈ e.votes, v.judge = k ∧ v.convinced = true := by
  intro k hk
  have hfull := e.full
  unfold missingVoters at hfull
  rw [List.filter_eq_nil_iff] at hfull
  have hv : votedBy e.votes k = true := by simpa using hfull k hk
  unfold votedBy at hv
  rw [List.any_eq_true] at hv
  obtain ⟨v, hmem, hj⟩ := hv
  have hall := e.allConvinced
  rw [List.all_eq_true] at hall
  exact ⟨v, hmem, by simpa using hj, hall v hmem⟩

/-- `Phase.introduced` can only be built from an `Earned`, so any replay that reaches it carries all of this. -/
theorem no_unearned_rule {evs : List Entry} {s : State} {tags : List (Nat × Entry)} {e : Earned}
    (_hr : replay evs = .state s tags) (_hp : s.phase = .introduced e) :
    (∀ k ∈ judges, ∃ v ∈ e.votes, v.judge = k ∧ v.convinced = true) ∧
    e.report.passed = true ∧ e.report.level1Conflict = false ∧
    e.claim.steps.all (fun st => st.source.isSome) = true ∧ e.panel = Panel.independent :=
  ⟨every_judge_convinced e, e.passed, e.noConflict, e.sourced, e.independent⟩

/-! ## 2. Determinism -/

theorem children_perm {a b : List Entry} (p : a.Perm b) (h : Option String) :
    (children a h).Perm (children b h) :=
  p.filter _

theorem pick_perm {a b : List Entry} (p : a.Perm b) : pick a = pick b := by
  have hl := p.length_eq
  rcases a with _ | ⟨x, _ | ⟨x2, t⟩⟩ <;> rcases b with _ | ⟨y, _ | ⟨y2, u⟩⟩
  all_goals simp only [List.length_cons, List.length_nil] at hl
  all_goals first
    | rfl
    | omega
    | (have hx : x ∈ [y] := p.subset (List.mem_singleton_self x)
       rw [List.mem_singleton] at hx
       rw [hx])

theorem follow_perm {a b : List Entry} (p : a.Perm b) :
    ∀ fuel h, follow a fuel h = follow b fuel h
  | 0, _ => rfl
  | fuel + 1, h => by
    simp only [follow]
    rw [pick_perm (children_perm p h)]
    have ih : follow a fuel = follow b fuel := funext (follow_perm p fuel)
    rw [ih]

theorem any_perm {a b : List Entry} (p : a.Perm b) (f : Entry → Bool) : a.any f = b.any f := by
  apply Bool.eq_iff_iff.mpr
  simp only [List.any_eq_true]
  constructor
  · rintro ⟨x, hx, hf⟩
    exact ⟨x, p.subset hx, hf⟩
  · rintro ⟨x, hx, hf⟩
    exact ⟨x, p.symm.subset hx, hf⟩

theorem hasFork_perm {a b : List Entry} (p : a.Perm b) : hasFork a = hasFork b := by
  unfold hasFork
  have hc : ∀ h, (children a h).length = (children b h).length := fun h => (children_perm p h).length_eq
  simp only [hc]
  exact any_perm p _

theorem linearize_perm {a b : List Entry} (p : a.Perm b) : linearize a = linearize b := by
  unfold linearize
  rw [hasFork_perm p, p.length_eq, follow_perm p]

theorem determinism {a b : List Entry} (p : a.Perm b) : replay a = replay b := by
  unfold replay
  rw [linearize_perm p]

/-! ## 3. Terminal states are final -/

theorem terminal_final_introduced {s : State} {e : Earned} (h : s.phase = .introduced e) (x : Entry) :
    accepted (step s x) = false := by
  simp [step, h, accepted]

theorem terminal_final_withdrawn {s : State} (h : s.phase = .withdrawn) (x : Entry) :
    accepted (step s x) = false := by
  simp [step, h, accepted]

theorem terminal_final_house_rule {s : State} {c : Case} (h : s.phase = .houseRule c) (x : Entry) :
    accepted (step s x) = false := by
  simp [step, h, accepted]

theorem refuted_only_to_house_rule {s s' : State} {c : Case} {why : String} {x : Entry}
    (hp : s.phase = .refuted c why) (h : step s x = .ok s') : s'.phase = .houseRule c := by
  simp only [step, hp, onRefuted] at h
  split at h
  · split at h
    · cases h
      rfl
    · cases h
  · cases h

/-! ## 4. Blindness -/

theorem blindness {k : Nat} {s : State} {tags : List (Nat × Entry)} {t : Nat × Entry}
    (hm : t ∈ view k s tags) (hnow : t.1 = s.since) (hact : isPanelAct t.2 = true) :
    t.2.actor = Actor.judge k := by
  have hv := (List.mem_filter.mp hm).2
  simpa [hiddenFrom, hnow, hact] using hv

/-! ## 5. Progress -/

theorem progress (p : Phase) (h : p.settled = false) : owed p ≠ [] := by
  cases p <;> simp_all [owed, Phase.settled]

/-! ## 6. Forks are caught -/

theorem two_le_of_two_mem {l : List Entry} {x y : Entry} (hne : x ≠ y) (hx : x ∈ l) (hy : y ∈ l) :
    2 ≤ l.length := by
  rcases l with _ | ⟨a, _ | ⟨b, t⟩⟩
  · simp at hx
  · simp only [List.mem_singleton] at hx hy
    exact absurd (hx.trans hy.symm) hne
  · simp only [List.length_cons]
    omega

theorem mem_children {evs : List Entry} {x : Entry} {h : Option String} (hx : x ∈ evs) (hp : x.prev = h) :
    x ∈ children evs h :=
  List.mem_filter.mpr ⟨hx, by simp [hp]⟩

theorem forks_caught {evs : List Entry} {x y : Entry} (hx : x ∈ evs) (hy : y ∈ evs) (hne : x ≠ y)
    (hp : x.prev = y.prev) : replay evs = .fork := by
  have hf : hasFork evs = true := by
    unfold hasFork
    rw [List.any_eq_true]
    refine ⟨x, hx, ?_⟩
    rw [Nat.ble_eq]
    exact two_le_of_two_mem hne (mem_children hx rfl) (mem_children hy hp.symm)
  unfold replay linearize
  simp [hf]

end Challenge
