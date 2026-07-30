/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PT21Ladder

/-!
# The production PT21 ladder geometry

`SparkInterval.Zeta.PT21Ladder` is generic in how many blocks a level-2
record covers.  Production pins that choice to the campaign scheduler's
geometry (`tg_verifier/platt_windowed_scheduler.py`):

```text
1 unit  =    512 blocks          ->  5793836 units
1 shard =   2048 units = 2^20 blocks  ->     2830 shards
```

That fixes the ladder to four levels of aggregation and one campaign
record:

| Level | Unit | Count | Checked by |
|---|---|---:|---|
| L1 | block window | 2,966,443,783 | compiled checker; `Prop`-level only in Lean |
| L2 | unit | 5,793,836 | compiled checker |
| L3 | shard | 2,830 | compiled checker **and the Lean kernel** |
| L4 | campaign | 1 | Lean kernel |

The `2830`-record level-3 ladder is the largest object the Lean kernel
ever reduces.  At the measured `1.4` ms per record that is about four
seconds -- a rounding error inside an ordinary `lake build`.

Both aggregation steps reuse the *same* record type and the *same*
checker: a unit and a shard are both `GroupSummary`, and both are checked
by `runGroupsTo`.  Only the digest scheme differs, and the digest scheme
is a parameter.  This module adds the second aggregation step
(`shard -> unit`) and composes it with the first (`unit -> window`) into
one theorem.

No axiom, `sorry`, or `native_decide`.
-/

set_option autoImplicit false

namespace SparkInterval.Zeta.PT21Ladder

/-! ## Pinned geometry -/

/-- Blocks in one scheduler work unit. -/
def blocksPerUnit : Nat := 512

/-- Units in one scheduler shard.  `512 * 2048 = 2^20` blocks. -/
def unitsPerShard : Nat := 2_048

/-- Units needed to cover every source block. -/
def sourceUnitCount : Nat := 5_793_836

/-- Shards needed to cover every source unit. -/
def sourceShardCount : Nat := 2_830

theorem blocksPerShard : blocksPerUnit * unitsPerShard = 1_048_576 := by
  unfold blocksPerUnit unitsPerShard
  decide

/-- The unit grid covers the campaign; the final unit is partly outside the
scanned range, which the ladder permits because a level-2 record carries its
own block count. -/
theorem sourceUnitCount_covers :
    sourceBlockCount ≤ sourceUnitCount * blocksPerUnit := by
  unfold sourceBlockCount sourceUnitCount blocksPerUnit
  decide

theorem sourceUnitCount_tight :
    (sourceUnitCount - 1) * blocksPerUnit < sourceBlockCount := by
  unfold sourceBlockCount sourceUnitCount blocksPerUnit
  decide

/-- The shard grid covers the unit grid, again with a partial final shard. -/
theorem sourceShardCount_covers :
    sourceUnitCount ≤ sourceShardCount * unitsPerShard := by
  unfold sourceUnitCount sourceShardCount unitsPerShard
  decide

theorem sourceShardCount_tight :
    (sourceShardCount - 1) * unitsPerShard < sourceUnitCount := by
  unfold sourceUnitCount sourceShardCount unitsPerShard
  decide

/-! ## Splitting and joining level-2 runs

`WindowChainValid.append` already lets level-1 runs be checked in
isolation.  The same is needed one level up, so that a shard can be
checked without its units being present. -/

theorem groupBlockSum_append (left right : List GroupSummary) :
    groupBlockSum (left ++ right) =
      groupBlockSum left + groupBlockSum right := by
  induction left with
  | nil => simp
  | cons group rest ih =>
      simp only [List.cons_append, groupBlockSum_cons, ih]
      omega

theorem groupSlotSum_append (left right : List GroupSummary) :
    groupSlotSum (left ++ right) =
      groupSlotSum left + groupSlotSum right := by
  induction left with
  | nil => simp
  | cons group rest ih =>
      simp only [List.cons_append, groupSlotSum_cons, ih]
      omega

theorem GroupChainValid.append :
    ∀ (block count : Nat) (left right : List GroupSummary),
      GroupChainValid block count left →
      GroupChainValid (block + groupBlockSum left)
        (count + groupSlotSum left) right →
        GroupChainValid block count (left ++ right) := by
  intro block count left
  induction left generalizing block count with
  | nil => intro right _ hright; simpa using hright
  | cons group rest induction =>
      rintro right ⟨hfirst, hcount, hpositive, hdigest, hclosed, htail⟩ hright
      refine ⟨hfirst, hcount, hpositive, hdigest, hclosed, ?_⟩
      apply induction (block + group.blockCount) group.upperCount right htail
      have hblock : block + groupBlockSum (group :: rest) =
          block + group.blockCount + groupBlockSum rest := by
        simp only [groupBlockSum_cons]; omega
      have hslot : count + groupSlotSum (group :: rest) =
          group.upperCount + groupSlotSum rest := by
        simp only [groupSlotSum_cons]; omega
      rw [hblock, hslot] at hright
      exact hright

/-! ## The level-3 to level-2 refinement

`GroupRefines` is the level-2 obligation: a unit digest commits to a valid
run of window summaries.  `ShardRefines` is its level-3 analogue, and it
carries the level-2 obligation for each of its units so that the two can be
composed. -/

/-- A shard summary refines a valid run of unit summaries, each of which
itself refines a valid run of window summaries. -/
def ShardRefines
    (unitCommit : List WindowSummary → Digest)
    (shardCommit : List GroupSummary → Digest)
    (shard : GroupSummary) : Prop :=
  ∃ units : List GroupSummary,
    groupBlockSum units = shard.blockCount ∧
    GroupChainValid shard.firstBlock shard.lowerCount units ∧
    groupSlotSum units = shard.slots ∧
    shardCommit units = shard.digest ∧
    ∀ unit ∈ units, GroupRefines unitCommit unit

/-- Level-3 aggregation: a checked shard run plus one refinement fact per
shard yields a single valid unit run over the whole range, with every
unit's own level-2 obligation preserved. -/
theorem exists_unitChain_of_shardChain
    (unitCommit : List WindowSummary → Digest)
    (shardCommit : List GroupSummary → Digest) :
    ∀ (block count : Nat) (shards : List GroupSummary),
      GroupChainValid block count shards →
      (∀ shard ∈ shards, ShardRefines unitCommit shardCommit shard) →
        ∃ units : List GroupSummary,
          groupBlockSum units = groupBlockSum shards ∧
          GroupChainValid block count units ∧
          groupSlotSum units = groupSlotSum shards ∧
          ∀ unit ∈ units, GroupRefines unitCommit unit := by
  intro block count shards
  induction shards generalizing block count with
  | nil =>
      intro _ _
      exact ⟨[], by simp, trivial, by simp, by simp⟩
  | cons shard rest induction =>
      rintro ⟨hfirst, hcount, _hpositive, _hdigest, hclosed, htail⟩ hrefines
      obtain ⟨head, hblocks, hvalid, hslots, _hdigestEq, hheadUnits⟩ :=
        hrefines shard List.mem_cons_self
      obtain ⟨tail, htailBlocks, htailValid, htailSlots, htailUnits⟩ :=
        induction (block + shard.blockCount) shard.upperCount htail
          (fun s hs => hrefines s (List.mem_cons_of_mem _ hs))
      refine ⟨head ++ tail, ?_, ?_, ?_, ?_⟩
      · rw [groupBlockSum_append, hblocks, htailBlocks, groupBlockSum_cons]
      · apply GroupChainValid.append
        · rw [hfirst, hcount] at hvalid
          exact hvalid
        · have hblock : block + groupBlockSum head = block + shard.blockCount := by
            rw [hblocks]
          have hslot : count + groupSlotSum head = shard.upperCount := by
            rw [hslots]; omega
          rw [hblock, hslot]
          exact htailValid
      · rw [groupSlotSum_append, hslots, htailSlots, groupSlotSum_cons]
      · intro unit hunit
        rcases List.mem_append.mp hunit with hleft | hright
        · exact hheadUnits unit hleft
        · exact htailUnits unit hright

/-- **The production ladder theorem.**

A kernel-checked campaign record over `2830` shard summaries, plus one
shard-refinement fact per shard, produces a single valid window chain over
all `2966443783` source blocks whose total slot count is exactly the
campaign's advertised count increase.

Neither the `5793836`-unit list nor the `2966443783`-window list is ever
materialized by the kernel: both are eliminated existentials. -/
theorem campaign_windowChain_twoTier
    (unitCommit : List WindowSummary → Digest)
    (shardCommit : List GroupSummary → Digest)
    {record : CampaignRecord} {shards : List GroupSummary}
    (hcheck : checkCampaign record shards = true)
    (hrefines : ∀ shard ∈ shards, ShardRefines unitCommit shardCommit shard) :
    ∃ windows : List WindowSummary,
      windows.length = record.blockCount ∧
      WindowChainValid record.firstBlock record.lowerCount windows ∧
      slotSum windows = record.slots ∧
      record.lowerCount + slotSum windows = record.upperCount := by
  obtain ⟨hvalid, hblocks, hslots, hclosed⟩ := checkCampaign_sound hcheck
  obtain ⟨units, hunitBlocks, hunitValid, hunitSlots, hunitRefines⟩ :=
    exists_unitChain_of_shardChain unitCommit shardCommit
      record.firstBlock record.lowerCount shards hvalid hrefines
  obtain ⟨windows, hlen, hchain, hsum⟩ :=
    exists_windowChain_of_groupChain unitCommit record.firstBlock
      record.lowerCount units hunitValid hunitRefines
  refine ⟨windows, by omega, hchain, by omega, by omega⟩

end SparkInterval.Zeta.PT21Ladder
