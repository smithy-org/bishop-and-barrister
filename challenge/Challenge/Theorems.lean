import Challenge.Chain

/-!
# The six guarantees

Checked on every build; `Audit.lean` fails the build if any of them is missing or rests on `sorry`.

1. `no_unearned_rule`: an introduced challenge had five convinced judges, each with evidence; a passing verifier
   report with no level 1 conflict and nothing standing; every step sourced or a stipulation; and an independent
   panel. `stipulations_only_in_gaps`: a stipulation can only be in a rule that fills a gap.
   `introduced_has_opinion`: and an opinion of the court, written by a convinced judge, that each of the five
   judges joined as written.
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

/-- Every judge on the panel cast a convinced vote. A step toward guarantee 1: `Earned` stores that no judge is
missing and that every vote is convinced, and this puts the two together. -/
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

/-- Guarantee 1, no unearned rule. `Phase.introduced` can only be built from an `Earned`, so any replay that
reaches it carries all of this: five convinced judges, each with evidence; a passing verifier report with no level 1
conflict and nothing standing; every step sourced or a stipulation; and an independent panel. No code path can
introduce a rule the panel and the verifier didn't earn. -/
theorem no_unearned_rule {evs : List Entry} {s : State} {tags : List (Nat × Entry)} {e : Earned}
    (_hr : replay evs = .state s tags) (_hp : s.phase = .introduced e) :
    (∀ k ∈ judges, ∃ v ∈ e.votes, v.judge = k ∧ v.convinced = true) ∧
    e.report.passed = true ∧ e.report.level1Conflict = false ∧ e.report.standing.isEmpty = true ∧
    e.votes.all (fun v => !v.evidence.isEmpty) = true ∧
    e.claim.steps.all (fun st => st.source.isSome || st.stipulation) = true ∧ e.panel = Panel.independent :=
  ⟨every_judge_convinced e, e.passed, e.noConflict, e.noStanding, e.evidenced, e.grounded, e.independent⟩

/-- Part of guarantee 1. A stipulation can only be in a rule that fills a gap, never one that challenges an official
answer, so new content never overrides what the sources say. -/
theorem stipulations_only_in_gaps {evs : List Entry} {s : State} {tags : List (Nat × Entry)} {e : Earned}
    (_hr : replay evs = .state s tags) (_hp : s.phase = .introduced e) :
    e.claim.steps.all (fun st => !st.stipulation || isGap e.claim.challenges) = true :=
  e.gapOnly

theorem every_judge_joined (e : Earned) :
    ∀ k ∈ judges, ∃ r ∈ e.joins, r.judge = k ∧ r.stance = Stance.join := by
  intro k hk
  have hfull := e.fullJoins
  unfold missingResponders at hfull
  rw [List.filter_eq_nil_iff] at hfull
  have hr : respondedBy e.joins k = true := by simpa using hfull k hk
  unfold respondedBy at hr
  rw [List.any_eq_true] at hr
  obtain ⟨r, hmem, hj⟩ := hr
  have hall := e.allJoin
  rw [List.all_eq_true] at hall
  exact ⟨r, hmem, by simpa using hj, by simpa using hall r hmem⟩

theorem author_was_convinced (e : Earned) :
    ∃ v ∈ e.votes, v.judge = e.opinion.author ∧ v.convinced = true := by
  have h := e.authorConvinced
  rw [List.any_eq_true] at h
  obtain ⟨v, hmem, hv⟩ := h
  have hv' := hv
  simp only [Bool.and_eq_true, beq_iff_eq] at hv'
  exact ⟨v, hmem, hv'.1, hv'.2⟩

theorem five_distinct_judges : judges.length = 5 ∧ judges.Nodup := ⟨by decide, by decide⟩

/-- An introduced rule has an opinion of the court: written by one of the convinced judges, stating the case's
rule and nothing new, and joined as written by each of the five judges (distinct, as there are five of them). A
concurrence is not a join, so a rule with any concurrence or dissent is never introduced. -/
theorem introduced_has_opinion {evs : List Entry} {s : State} {tags : List (Nat × Entry)} {e : Earned}
    (_hr : replay evs = .state s tags) (_hp : s.phase = .introduced e) :
    (∀ k ∈ judges, ∃ r ∈ e.joins, r.judge = k ∧ r.stance = Stance.join) ∧
    judges.length = 5 ∧ judges.Nodup ∧
    (∃ v ∈ e.votes, v.judge = e.opinion.author ∧ v.convinced = true) ∧
    (e.opinion.holding == e.claim.rule) = true ∧
    e.opinion.steps.all (fun st => st.source.isSome || st.stipulation) = true :=
  ⟨every_judge_joined e, five_distinct_judges.1, five_distinct_judges.2, author_was_convinced e, e.holdsRule,
    e.opinionGrounded⟩

/-! ## 2. Determinism -/

/-- Reordering the event files doesn't change which events follow a given one, up to order. A step toward guarantee
2. -/
theorem children_perm {a b : List Entry} (p : a.Perm b) (h : Option String) :
    (children a h).Perm (children b h) :=
  p.filter _

/-- Reordering a list of children doesn't change whether there are none, one or many. -/
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

/-- Following the chain gives the same events whatever order the files are in. -/
theorem follow_perm {a b : List Entry} (p : a.Perm b) :
    ∀ fuel h, follow a fuel h = follow b fuel h
  | 0, _ => rfl
  | fuel + 1, h => by
    simp only [follow]
    rw [pick_perm (children_perm p h)]
    have ih : follow a fuel = follow b fuel := funext (follow_perm p fuel)
    rw [ih]

/-- Whether some event passes a test doesn't depend on their order. -/
theorem any_perm {a b : List Entry} (p : a.Perm b) (f : Entry → Bool) : a.any f = b.any f := by
  apply Bool.eq_iff_iff.mpr
  simp only [List.any_eq_true]
  constructor
  · rintro ⟨x, hx, hf⟩
    exact ⟨x, p.subset hx, hf⟩
  · rintro ⟨x, hx, hf⟩
    exact ⟨x, p.symm.subset hx, hf⟩

/-- Whether there is a fork doesn't depend on the order of the files. -/
theorem hasFork_perm {a b : List Entry} (p : a.Perm b) : hasFork a = hasFork b := by
  unfold hasFork
  have hc : ∀ h, (children a h).length = (children b h).length := fun h => (children_perm p h).length_eq
  simp only [hc]
  exact any_perm p _

/-- The chain order doesn't depend on the order the files are read in. -/
theorem linearize_perm {a b : List Entry} (p : a.Perm b) : linearize a = linearize b := by
  unfold linearize
  rw [hasFork_perm p, p.length_eq, follow_perm p]

/-- Guarantee 2, determinism. Replay gives the same result for any order of the same event files, so every device
holding the same events computes the same state. Without it, two judges could see two different challenges. -/
theorem determinism {a b : List Entry} (p : a.Perm b) : replay a = replay b := by
  unfold replay
  rw [linearize_perm p]

/-! ## 3. Terminal states are final -/

/-- Guarantee 3, terminal states are final: once a rule is introduced, no event is accepted. An introduced rule
can't be undone or changed by a later event. -/
theorem terminal_final_introduced {s : State} {e : Earned} (h : s.phase = .introduced e) (x : Entry) :
    accepted (step s x) = false := by
  simp [step, h, accepted]

/-- Guarantee 3, terminal states are final: once a challenge is withdrawn, no event is accepted. -/
theorem terminal_final_withdrawn {s : State} (h : s.phase = .withdrawn) (x : Entry) :
    accepted (step s x) = false := by
  simp [step, h, accepted]

/-- Guarantee 3, terminal states are final: once a case is kept as a house rule, no event is accepted. -/
theorem terminal_final_house_rule {s : State} {c : Case} (h : s.phase = .houseRule c) (x : Entry) :
    accepted (step s x) = false := by
  simp [step, h, accepted]

/-- Guarantee 3 for `refuted`: the only event it accepts makes the same case a house rule. A refuted case can't come
back as an introduced rule. -/
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

/-- Guarantee 4, blindness. A filing or vote from the phase in progress that judge `k` is shown is judge `k`'s own.
No judge sees another's position until everyone has filed or voted, so none can follow the others. -/
theorem blindness {k : Nat} {s : State} {tags : List (Nat × Entry)} {t : Nat × Entry}
    (hm : t ∈ view k s tags) (hnow : t.1 = s.since) (hact : isPanelAct t.2 = true) :
    t.2.actor = Actor.judge k := by
  have hv := (List.mem_filter.mp hm).2
  simpa [hiddenFrom, hnow, hact] using hv

/-! ## 5. Progress -/

/-- Guarantee 5, progress. Every phase that isn't settled names someone who owes the next action, so a challenge
can't stall with nobody to act. -/
theorem progress (p : Phase) (h : p.settled = false) : owed p ≠ [] := by
  cases p <;> simp_all [owed, Phase.settled]

/-! ## 6. Forks are caught -/

/-- A list holding two different events has at least two. A step toward guarantee 6. -/
theorem two_le_of_two_mem {l : List Entry} {x y : Entry} (hne : x ≠ y) (hx : x ∈ l) (hy : y ∈ l) :
    2 ≤ l.length := by
  rcases l with _ | ⟨a, _ | ⟨b, t⟩⟩
  · simp at hx
  · simp only [List.mem_singleton] at hx hy
    exact absurd (hx.trans hy.symm) hne
  · simp only [List.length_cons]
    omega

/-- An event is among the children of its own predecessor. -/
theorem mem_children {evs : List Entry} {x : Entry} {h : Option String} (hx : x ∈ evs) (hp : x.prev = h) :
    x ∈ children evs h :=
  List.mem_filter.mpr ⟨hx, by simp [hp]⟩

/-- Guarantee 6, forks caught. Two different events naming the same predecessor make replay report a fork. Replay
never silently picks one, so two devices acting in the same state are always noticed. -/
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
