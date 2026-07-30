/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

/-!
# The PT21 verification ladder: window, group, and campaign levels

The Platt--Trudgian scan to height `3000175332800` isolates about
`1.24e13` sign brackets in `2966443783` blocks.  A certificate that names
every bracket cannot be checked by the Lean kernel: the measured
kernel-mode bracket rate is about 22 brackets/s, so a bracket-linear
certificate is a `5e4` core-year *check* for a `5e2` core-year *compute*.

Turing's method does not need every bracket individually.  Per block it
needs (i) the two endpoint zero counts obtained from the one-sided
Turing/argument-principle quotients, and (ii) that the requisite number of
sign changes was exhibited strictly inside the block.  Those two facts are
already produced and checked by `PT21ArtifactBinding.BlockArtifact.check`
and closed by `PairedTuringClosureCertificate.closure_equation`.  The
*only* things the next level up needs from a block are four naturals:

```text
block index, count at the left endpoint, isolated multiplicity slots,
count at the right endpoint.
```

This module is the arithmetic ladder over those summaries.  It has three
levels:

* `WindowSummary` (level 1) -- one per source block, `2966443783` records;
* `GroupSummary` (level 2) -- one per fixed run of consecutive blocks,
  together with a digest committing to the level-1 records it replaces;
* `CampaignRecord` (level 3) -- one record for the whole campaign.

Each level is checked by a linear `Option`-returning fold over exact
naturals.  There is no rational arithmetic, no `Rat`, no `decide` over a
`Fin` quantifier, and no `native_decide`, so the level-2 and level-3 checks
are cheap enough to run in the Lean kernel at production size.

## What compression preserves, and what it destroys

A checked ladder proves exactly this, and nothing more:

1. **Gap-free consecutive coverage.**  Block indices are forced to be
   `first, first+1, ...`; no block may be skipped, repeated, or reordered.
2. **Count telescoping.**  Every window's advertised right-endpoint count
   is the next window's left-endpoint count, and the campaign's total slot
   count is exactly the difference of the two campaign endpoint counts.
3. **Local closure.**  Every window satisfies
   `lowerCount + slots = upperCount`.

The ladder deliberately does *not* preserve:

* any zero ordinate.  After compression no zero can be located, and no
  claim about where a particular zero sits survives;
* any endpoint enclosure, sign bit, or interval.  Nothing in a summary
  witnesses that a sign change occurred, only that one was claimed;
* the Turing rounding arithmetic.  `lowerCount` and `upperCount` are the
  *advertised* counts; the exact-rational ceiling/floor cells that justify
  them live in `PairedTuringClosureCertificate`, one level below.

Item 2 is the reason the compression is sound for finite RH and unsound
for anything that needs zero locations.  Finite RH on a rectangle is a
statement about a *count*: if the multiplicity count over a block equals
the number of critical-line zeros exhibited in it, every zero of that
block is on the critical line, wherever it is.  A ladder record therefore
carries all the RH-relevant content of its block and none of the
zero-location content.

`GroupRefines` is the single place where trust is transferred rather than
eliminated.  It says a group digest really commits to a valid run of
window summaries.  Discharging it for `2966443783` windows is the job of
the compiled checker and its attestation, not of the Lean kernel; this
module makes the obligation explicit and universally quantified so that
nothing else can smuggle it in.

This module imports nothing.  It contains no axiom, `sorry`, or
`native_decide`.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PT21Ladder

/-! ## Source geometry

These are the pinned PT21 block constants, repeated here so the ladder can
be checked without importing the artifact decoder. -/

/-- First scanned ordinate: the LMFDB/Platt prefix boundary. -/
def sourceLower : Nat := 10_000_000_000

/-- Height covered by one source block. -/
def sourceBlockStep : Nat := 1_008

/-- Number of source blocks in the campaign. -/
def sourceBlockCount : Nat := 2_966_443_783

/-- Left ordinate of block `k`. -/
def blockLower (block : Nat) : Nat :=
  sourceLower + block * sourceBlockStep

theorem blockLower_succ (block : Nat) :
    blockLower (block + 1) = blockLower block + sourceBlockStep := by
  unfold blockLower
  rw [Nat.succ_mul]
  omega

theorem blockLower_lt_succ (block : Nat) :
    blockLower block < blockLower (block + 1) := by
  rw [blockLower_succ]
  unfold sourceBlockStep
  omega

/-- A 32-byte commitment, held as the big-endian natural it encodes.

`Nat` rather than `List UInt8` is a deliberate performance decision.  The
kernel only ever range-checks a digest; it never inspects bytes.  A
`List UInt8` literal costs 32 cons cells and 32 `OfNat` applications per
record; a `Nat` literal is one GMP-accelerated numeral and one
comparison. -/
abbrev Digest := Nat

/-- `2 ^ 256`, written out so the checker never recomputes a power. -/
def digestBound : Nat :=
  115792089237316195423570985008687907853269984665640564039457584007913129639936

theorem digestBound_eq : digestBound = 2 ^ 256 := by
  unfold digestBound
  decide

/-! ## Level 1: one window summary per source block -/

/-- Everything the ladder retains about one PT21 block.

`slots` is the block's isolated *multiplicity* slot count, matching
`PairedTuringClosureCertificate.mainIsolatedSlots`; it is a sum of
recorded multiplicities, not a count of brackets, so nothing here assumes
zeros are simple. -/
structure WindowSummary where
  block : Nat
  lowerCount : Nat
  slots : Nat
  upperCount : Nat
  deriving DecidableEq, Repr, Inhabited

namespace WindowSummary

/-- The local closure equation of one window. -/
def Closed (window : WindowSummary) : Prop :=
  window.lowerCount + window.slots = window.upperCount

end WindowSummary

/-- Total slot count of a window list. -/
def slotSum : List WindowSummary → Nat
  | [] => 0
  | window :: rest => window.slots + slotSum rest

@[simp] theorem slotSum_nil : slotSum [] = 0 := rfl

@[simp] theorem slotSum_cons (window : WindowSummary)
    (rest : List WindowSummary) :
    slotSum (window :: rest) = window.slots + slotSum rest := rfl

theorem slotSum_append (left right : List WindowSummary) :
    slotSum (left ++ right) = slotSum left + slotSum right := by
  induction left with
  | nil => simp
  | cons window rest ih =>
      simp only [List.cons_append, slotSum_cons, ih]
      omega

/-- Exact meaning of accepting a window run that starts at block `block`
with left-endpoint count `count`. -/
def WindowChainValid : Nat → Nat → List WindowSummary → Prop
  | _, _, [] => True
  | block, count, window :: rest =>
      window.block = block ∧ window.lowerCount = count ∧ window.Closed ∧
        WindowChainValid (block + 1) window.upperCount rest

/-- Linear executable window-run checker.  The returned pair is the state
handed to the next run, so the check is resumable and streaming. -/
def runWindows : Nat → Nat → List WindowSummary → Option (Nat × Nat)
  | block, count, [] => some (block, count)
  | block, count, window :: rest =>
      if window.block = block ∧ window.lowerCount = count ∧
          window.lowerCount + window.slots = window.upperCount then
        runWindows (block + 1) window.upperCount rest
      else
        none

theorem runWindows_sound :
    ∀ (block count : Nat) (windows : List WindowSummary) (result : Nat × Nat),
      runWindows block count windows = some result →
        WindowChainValid block count windows ∧
          result = (block + windows.length, count + slotSum windows) := by
  intro block count windows
  induction windows generalizing block count with
  | nil =>
      intro result hrun
      simp only [runWindows, Option.some.injEq] at hrun
      subst hrun
      exact ⟨trivial, by simp⟩
  | cons window rest induction =>
      intro result hrun
      simp only [runWindows] at hrun
      by_cases hlocal : window.block = block ∧ window.lowerCount = count ∧
          window.lowerCount + window.slots = window.upperCount
      · rw [if_pos hlocal] at hrun
        obtain ⟨htail, hresult⟩ := induction (block + 1) window.upperCount result hrun
        refine ⟨⟨hlocal.1, hlocal.2.1, hlocal.2.2, htail⟩, ?_⟩
        have hcount := hlocal.2.1
        have hclosed := hlocal.2.2
        rw [hresult]
        simp only [List.length_cons, slotSum_cons, Prod.mk.injEq]
        omega
      · rw [if_neg hlocal] at hrun
        exact absurd hrun (by simp)

theorem runWindows_complete :
    ∀ (block count : Nat) (windows : List WindowSummary),
      WindowChainValid block count windows →
        runWindows block count windows =
          some (block + windows.length, count + slotSum windows) := by
  intro block count windows
  induction windows generalizing block count with
  | nil => intro _; simp [runWindows]
  | cons window rest induction =>
      rintro ⟨hblock, hcount, hclosed, htail⟩
      have hlocal : window.block = block ∧ window.lowerCount = count ∧
          window.lowerCount + window.slots = window.upperCount :=
        ⟨hblock, hcount, hclosed⟩
      simp only [runWindows, if_pos hlocal]
      rw [induction (block + 1) window.upperCount htail]
      unfold WindowSummary.Closed at hclosed
      simp only [List.length_cons, slotSum_cons, Prod.mk.injEq, Option.some.injEq]
      omega

namespace WindowChainValid

/-- Block indices in an accepted run are exactly consecutive.  This is the
gap-free coverage property; it is what forbids a producer from omitting a
block and closing the count with a fabricated slot total. -/
theorem block_eq :
    ∀ (block count : Nat) (windows : List WindowSummary),
      WindowChainValid block count windows →
        ∀ (i : Nat) (hi : i < windows.length),
          windows[i].block = block + i := by
  intro block count windows
  induction windows generalizing block count with
  | nil => intro _ i hi; simp at hi
  | cons window rest induction =>
      rintro ⟨hblock, _hcount, _hclosed, htail⟩ i hi
      cases i with
      | zero => simpa using hblock
      | succ j =>
          have hj : j < rest.length := by simpa using hi
          have := induction (block + 1) window.upperCount htail j hj
          simpa [this] using by omega

/-- Every accepted window satisfies its own closure equation. -/
theorem closed :
    ∀ (block count : Nat) (windows : List WindowSummary),
      WindowChainValid block count windows →
        ∀ window ∈ windows, window.Closed := by
  intro block count windows
  induction windows generalizing block count with
  | nil => intro _ w hw; simp at hw
  | cons window rest induction =>
      rintro ⟨_hblock, _hcount, hclosed, htail⟩ w hw
      rcases List.mem_cons.mp hw with rfl | hrest
      · exact hclosed
      · exact induction (block + 1) window.upperCount htail w hrest

/-- Adjacent windows share their endpoint count: the right-endpoint count
of one window is the left-endpoint count of the next.  This is the
telescoping property. -/
theorem link :
    ∀ (block count : Nat) (windows : List WindowSummary),
      WindowChainValid block count windows →
        ∀ (i : Nat) (hi : i + 1 < windows.length),
          windows[i].upperCount = windows[i + 1].lowerCount := by
  intro block count windows
  induction windows generalizing block count with
  | nil => intro _ i hi; simp at hi
  | cons window rest induction =>
      rintro ⟨_hblock, _hcount, _hclosed, htail⟩ i hi
      cases i with
      | zero =>
          cases rest with
          | nil => simp at hi
          | cons next tail =>
              obtain ⟨_, hnext, _, _⟩ := htail
              simpa using hnext.symm
      | succ j =>
          have hj : j + 1 < rest.length := by simpa using hi
          have := induction (block + 1) window.upperCount htail j hj
          simpa using this

/-- The head of a nonempty accepted run starts at the advertised block and
count. -/
theorem head :
    ∀ (block count : Nat) (window : WindowSummary)
      (rest : List WindowSummary),
      WindowChainValid block count (window :: rest) →
        window.block = block ∧ window.lowerCount = count :=
  fun _ _ _ _ hvalid => ⟨hvalid.1, hvalid.2.1⟩

/-- Splitting an accepted run at a group boundary yields two accepted runs
whose states meet exactly.  This is what makes the level-2 aggregation
sound: a group can be checked in isolation. -/
theorem append :
    ∀ (block count : Nat) (left right : List WindowSummary),
      WindowChainValid block count left →
      WindowChainValid (block + left.length) (count + slotSum left) right →
        WindowChainValid block count (left ++ right) := by
  intro block count left
  induction left generalizing block count with
  | nil => intro right _ hright; simpa using hright
  | cons window rest induction =>
      rintro right ⟨hblock, hcount, hclosed, htail⟩ hright
      refine ⟨hblock, hcount, hclosed, ?_⟩
      apply induction (block + 1) window.upperCount right htail
      have hlen : block + (window :: rest).length = block + 1 + rest.length := by
        simp only [List.length_cons]; omega
      have hslot : count + slotSum (window :: rest) =
          window.upperCount + slotSum rest := by
        simp only [slotSum_cons]
        have := hclosed
        unfold WindowSummary.Closed at this
        omega
      rw [hlen, hslot] at hright
      exact hright

end WindowChainValid

/-! ## Level 2: one group summary per run of consecutive blocks -/

/-- A level-2 record.  It replaces `blockCount` level-1 records with four
naturals and a digest.  `digest` is the commitment under which the
compiled checker's acceptance of those level-1 records is imported. -/
structure GroupSummary where
  firstBlock : Nat
  blockCount : Nat
  lowerCount : Nat
  slots : Nat
  upperCount : Nat
  digest : Digest
  deriving DecidableEq, Repr, Inhabited

/-- Total slot count of a group list. -/
def groupSlotSum : List GroupSummary → Nat
  | [] => 0
  | group :: rest => group.slots + groupSlotSum rest

@[simp] theorem groupSlotSum_nil : groupSlotSum [] = 0 := rfl

@[simp] theorem groupSlotSum_cons (group : GroupSummary)
    (rest : List GroupSummary) :
    groupSlotSum (group :: rest) = group.slots + groupSlotSum rest := rfl

/-- Total block count of a group list. -/
def groupBlockSum : List GroupSummary → Nat
  | [] => 0
  | group :: rest => group.blockCount + groupBlockSum rest

@[simp] theorem groupBlockSum_nil : groupBlockSum [] = 0 := rfl

@[simp] theorem groupBlockSum_cons (group : GroupSummary)
    (rest : List GroupSummary) :
    groupBlockSum (group :: rest) = group.blockCount + groupBlockSum rest := rfl

/-- Exact meaning of accepting a group run.  Empty groups are rejected so
the block cursor is strictly monotone and a producer cannot pad the ladder
with zero-width records. -/
def GroupChainValid : Nat → Nat → List GroupSummary → Prop
  | _, _, [] => True
  | block, count, group :: rest =>
      group.firstBlock = block ∧ group.lowerCount = count ∧
        0 < group.blockCount ∧ group.digest < digestBound ∧
        group.lowerCount + group.slots = group.upperCount ∧
        GroupChainValid (block + group.blockCount) group.upperCount rest

/-- Linear executable group-run checker. -/
def runGroups : Nat → Nat → List GroupSummary → Option (Nat × Nat)
  | block, count, [] => some (block, count)
  | block, count, group :: rest =>
      if group.firstBlock = block ∧ group.lowerCount = count ∧
          0 < group.blockCount ∧ group.digest < digestBound ∧
          group.lowerCount + group.slots = group.upperCount then
        runGroups (block + group.blockCount) group.upperCount rest
      else
        none

theorem runGroups_sound :
    ∀ (block count : Nat) (groups : List GroupSummary) (result : Nat × Nat),
      runGroups block count groups = some result →
        GroupChainValid block count groups ∧
          result = (block + groupBlockSum groups, count + groupSlotSum groups) := by
  intro block count groups
  induction groups generalizing block count with
  | nil =>
      intro result hrun
      simp only [runGroups, Option.some.injEq] at hrun
      subst hrun
      exact ⟨trivial, by simp⟩
  | cons group rest induction =>
      intro result hrun
      simp only [runGroups] at hrun
      by_cases hlocal : group.firstBlock = block ∧ group.lowerCount = count ∧
          0 < group.blockCount ∧ group.digest < digestBound ∧
          group.lowerCount + group.slots = group.upperCount
      · rw [if_pos hlocal] at hrun
        obtain ⟨htail, hresult⟩ :=
          induction (block + group.blockCount) group.upperCount result hrun
        refine ⟨⟨hlocal.1, hlocal.2.1, hlocal.2.2.1, hlocal.2.2.2.1,
          hlocal.2.2.2.2, htail⟩, ?_⟩
        have hcount := hlocal.2.1
        have hclosed := hlocal.2.2.2.2
        rw [hresult]
        simp only [groupBlockSum_cons, groupSlotSum_cons, Prod.mk.injEq]
        omega
      · rw [if_neg hlocal] at hrun
        exact absurd hrun (by simp)

theorem runGroups_complete :
    ∀ (block count : Nat) (groups : List GroupSummary),
      GroupChainValid block count groups →
        runGroups block count groups =
          some (block + groupBlockSum groups, count + groupSlotSum groups) := by
  intro block count groups
  induction groups generalizing block count with
  | nil => intro _; simp [runGroups]
  | cons group rest induction =>
      rintro ⟨hfirst, hcount, hpositive, hdigest, hclosed, htail⟩
      have hlocal : group.firstBlock = block ∧ group.lowerCount = count ∧
          0 < group.blockCount ∧ group.digest < digestBound ∧
          group.lowerCount + group.slots = group.upperCount :=
        ⟨hfirst, hcount, hpositive, hdigest, hclosed⟩
      simp only [runGroups, if_pos hlocal]
      rw [induction (block + group.blockCount) group.upperCount htail]
      simp only [groupBlockSum_cons, groupSlotSum_cons, Prod.mk.injEq,
        Option.some.injEq]
      omega

/-! ### The single trust-transfer point

`GroupRefines` is the obligation that a level-2 record really summarizes a
valid level-1 run.  Nothing in this module proves it; the compiled checker
does, under attestation.  The digest function is a parameter, so the
statement commits to the wire format without this module implementing a
hash. -/

/-- A group summary refines a valid run of window summaries under the
digest scheme `commit`. -/
def GroupRefines (commit : List WindowSummary → Digest)
    (group : GroupSummary) : Prop :=
  ∃ windows : List WindowSummary,
    windows.length = group.blockCount ∧
    WindowChainValid group.firstBlock group.lowerCount windows ∧
    slotSum windows = group.slots ∧
    commit windows = group.digest

/-- Aggregation: a checked group run plus one refinement fact per group
yields a single valid window run over the whole range, without the window
run ever being materialized in the kernel. -/
theorem exists_windowChain_of_groupChain
    (commit : List WindowSummary → Digest) :
    ∀ (block count : Nat) (groups : List GroupSummary),
      GroupChainValid block count groups →
      (∀ group ∈ groups, GroupRefines commit group) →
        ∃ windows : List WindowSummary,
          windows.length = groupBlockSum groups ∧
          WindowChainValid block count windows ∧
          slotSum windows = groupSlotSum groups := by
  intro block count groups
  induction groups generalizing block count with
  | nil => intro _ _; exact ⟨[], by simp, trivial, by simp⟩
  | cons group rest induction =>
      rintro ⟨hfirst, hcount, _hpositive, _hdigest, hclosed, htail⟩ hrefines
      obtain ⟨head, hlen, hvalid, hslots, _hdigestEq⟩ :=
        hrefines group List.mem_cons_self
      obtain ⟨tail, htailLen, htailValid, htailSlots⟩ :=
        induction (block + group.blockCount) group.upperCount htail
          (fun g hg => hrefines g (List.mem_cons_of_mem _ hg))
      refine ⟨head ++ tail, ?_, ?_, ?_⟩
      · simp only [List.length_append, groupBlockSum_cons, hlen, htailLen]
      · apply WindowChainValid.append
        · rw [hfirst, hcount] at hvalid
          exact hvalid
        · have hblock : block + head.length = block + group.blockCount := by
            rw [hlen]
          have hslot : count + slotSum head = group.upperCount := by
            rw [hslots]
            omega
          rw [hblock, hslot]
          exact htailValid
      · rw [slotSum_append, hslots, htailSlots, groupSlotSum_cons]

/-! ## Level 3: the campaign record -/

/-- The single top-level record.  `root` is the commitment to the level-2
list; the level-2 list itself is small enough to be presented literally to
the kernel. -/
structure CampaignRecord where
  firstBlock : Nat
  blockCount : Nat
  lowerCount : Nat
  slots : Nat
  upperCount : Nat
  root : Digest
  deriving DecidableEq, Repr, Inhabited

/-- Level-2 checker in *closed* form: a single tail-recursive pass that also
verifies the campaign endpoints.

This shape matters for kernel performance.  A checker that first computes a
state with `runGroups` and then compares that state against the campaign
record forces the kernel to re-reduce the whole run once per comparison; at
`100` records that costs `54` s, versus `0.9` s here.  The closed form
carries the targets through the recursion so the level-2 list is reduced
exactly once. -/
def runGroupsTo :
    Nat → Nat → Nat → Nat → List GroupSummary → Bool
  | block, count, targetBlock, targetCount, [] =>
      decide (block = targetBlock) && decide (count = targetCount)
  | block, count, targetBlock, targetCount, group :: rest =>
      if group.firstBlock = block ∧ group.lowerCount = count ∧
          0 < group.blockCount ∧ group.digest < digestBound ∧
          group.lowerCount + group.slots = group.upperCount then
        runGroupsTo (block + group.blockCount) group.upperCount
          targetBlock targetCount rest
      else
        false

theorem runGroupsTo_sound :
    ∀ (block count targetBlock targetCount : Nat)
      (groups : List GroupSummary),
      runGroupsTo block count targetBlock targetCount groups = true →
        GroupChainValid block count groups ∧
          block + groupBlockSum groups = targetBlock ∧
          count + groupSlotSum groups = targetCount := by
  intro block count targetBlock targetCount groups
  induction groups generalizing block count with
  | nil =>
      intro hrun
      simp only [runGroupsTo, Bool.and_eq_true, decide_eq_true_eq] at hrun
      exact ⟨trivial, by simp [hrun.1], by simp [hrun.2]⟩
  | cons group rest induction =>
      intro hrun
      simp only [runGroupsTo] at hrun
      by_cases hlocal : group.firstBlock = block ∧ group.lowerCount = count ∧
          0 < group.blockCount ∧ group.digest < digestBound ∧
          group.lowerCount + group.slots = group.upperCount
      · rw [if_pos hlocal] at hrun
        obtain ⟨htail, hblocks, hcounts⟩ :=
          induction (block + group.blockCount) group.upperCount hrun
        refine ⟨⟨hlocal.1, hlocal.2.1, hlocal.2.2.1, hlocal.2.2.2.1,
          hlocal.2.2.2.2, htail⟩, ?_, ?_⟩
        · simp only [groupBlockSum_cons]; omega
        · have hcount := hlocal.2.1
          have hclosed := hlocal.2.2.2.2
          simp only [groupSlotSum_cons]
          omega
      · rw [if_neg hlocal] at hrun
        exact absurd hrun (by simp)

/-- Full ladder acceptance.  The three constant-cost record conditions are
checked first so short-circuiting keeps the level-2 pass last. -/
def checkCampaign (record : CampaignRecord)
    (groups : List GroupSummary) : Bool :=
  decide (record.lowerCount + record.slots = record.upperCount) &&
  decide (0 < record.blockCount) &&
  decide (record.root < digestBound) &&
  runGroupsTo record.firstBlock record.lowerCount
    (record.firstBlock + record.blockCount) record.upperCount groups

/-- Everything a successful campaign check proves about the level-2 list. -/
theorem checkCampaign_sound {record : CampaignRecord}
    {groups : List GroupSummary}
    (hcheck : checkCampaign record groups = true) :
    GroupChainValid record.firstBlock record.lowerCount groups ∧
      groupBlockSum groups = record.blockCount ∧
      groupSlotSum groups = record.slots ∧
      record.lowerCount + record.slots = record.upperCount := by
  simp only [checkCampaign, Bool.and_eq_true, decide_eq_true_eq] at hcheck
  obtain ⟨⟨⟨hclosed, _hpositive⟩, _hroot⟩, hrun⟩ := hcheck
  obtain ⟨hvalid, hblocks, hcounts⟩ :=
    runGroupsTo_sound record.firstBlock record.lowerCount
      (record.firstBlock + record.blockCount) record.upperCount groups hrun
  exact ⟨hvalid, by omega, by omega, hclosed⟩

/-- The full ladder theorem.  A kernel-checked campaign record, a
kernel-checked level-2 list, and one imported refinement fact per group
produce a single valid window run over every block of the campaign, whose
total slot count is exactly the campaign's advertised count increase.

The level-1 list is produced only as a `Prop`-level witness: it is never
materialized, hashed, or reduced by the kernel. -/
theorem campaign_windowChain
    (commit : List WindowSummary → Digest)
    {record : CampaignRecord} {groups : List GroupSummary}
    (hcheck : checkCampaign record groups = true)
    (hrefines : ∀ group ∈ groups, GroupRefines commit group) :
    ∃ windows : List WindowSummary,
      windows.length = record.blockCount ∧
      WindowChainValid record.firstBlock record.lowerCount windows ∧
      slotSum windows = record.slots ∧
      record.lowerCount + slotSum windows = record.upperCount := by
  obtain ⟨hvalid, hblocks, hslots, hclosed⟩ := checkCampaign_sound hcheck
  obtain ⟨windows, hlen, hchain, hsum⟩ :=
    exists_windowChain_of_groupChain commit record.firstBlock record.lowerCount
      groups hvalid hrefines
  exact ⟨windows, by omega, hchain, by omega, by omega⟩

/-! ## The pinned campaign instance

These are the exact PT21 endpoints.  `sourceLowerCount` is the multiplicity
count at height `10^10` decoded from the public LMFDB prefix in
`SparkInterval.Zeta.LMFDBPrefixBoundary`; `sourceUpperCount` is the count
advertised at the campaign endpoint by
`SparkInterval.TernaryGoldbach.ZetaRHCompactChecker`. -/

/-- Multiplicity count at height `10^10`. -/
def sourceLowerCount : Nat := 32_130_158_315

/-- Multiplicity count at the campaign endpoint. -/
def sourceUpperCount : Nat := 12_363_153_437_138

/-- Slots the campaign must exhibit between the two endpoints. -/
def sourceSlots : Nat := sourceUpperCount - sourceLowerCount

theorem sourceSlots_closes :
    sourceLowerCount + sourceSlots = sourceUpperCount := by
  unfold sourceSlots sourceLowerCount sourceUpperCount
  decide

/-- The campaign's final scanned ordinate.  The last block deliberately
overshoots the Platt--Trudgian source height `3000175332800` by `464`: the
block lattice is fixed by the source geometry, so the campaign covers the
source height rather than landing on it. -/
theorem source_endpoint_height :
    blockLower sourceBlockCount = 3_000_175_333_264 := by
  unfold blockLower sourceLower sourceBlockCount sourceBlockStep
  decide

/-- The campaign endpoint covers the exact source height. -/
theorem source_endpoint_covers :
    3_000_175_332_800 ≤ blockLower sourceBlockCount := by
  rw [source_endpoint_height]
  decide

/-- The campaign is a `1.23e13`-slot claim spread over `2.97e9` blocks:
about `4157` slots per block. -/
theorem source_slots_value : sourceSlots = 12_331_023_278_823 := by
  unfold sourceSlots sourceLowerCount sourceUpperCount
  decide

end SparkInterval.Zeta.PT21Ladder
