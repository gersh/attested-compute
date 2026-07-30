/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.PT21LadderGeometry

/-!
# Kernel-checked tests for the PT21 verification ladder

Small literal instances of every level, plus the rejections that matter.
Each acceptance is proved by `rfl`, so the Lean kernel performs the whole
check; each rejection is proved by `rfl` on `= false`, so a checker that
silently accepted would fail to compile.

The rejection cases are the point.  A ladder that accepted a skipped
block, a broken count chain, an empty group, or a slot total that does not
match the endpoint counts would compress away exactly the content it is
supposed to preserve.
-/

set_option autoImplicit false
set_option maxRecDepth 100000

namespace SparkInterval.Zeta.PT21Ladder.Test

open SparkInterval.Zeta.PT21Ladder

/-! ## Level 3: a three-shard ladder -/

def shardA : GroupSummary :=
  { firstBlock := 0, blockCount := 1048576, lowerCount := 32130158315,
    slots := 4358759515, upperCount := 36488917830, digest := 11 }

def shardB : GroupSummary :=
  { firstBlock := 1048576, blockCount := 1048576, lowerCount := 36488917830,
    slots := 4358759515, upperCount := 40847677345, digest := 22 }

def shardC : GroupSummary :=
  { firstBlock := 2097152, blockCount := 1048576, lowerCount := 40847677345,
    slots := 4358759515, upperCount := 45206436860, digest := 33 }

def shards : List GroupSummary := [shardA, shardB, shardC]

def campaign : CampaignRecord :=
  { firstBlock := 0, blockCount := 3145728, lowerCount := 32130158315,
    slots := 13076278545, upperCount := 45206436860, root := 44 }

theorem campaign_accepts : checkCampaign campaign shards = true := by rfl

/-! ## Rejections -/

/-- A skipped block breaks gap-free coverage. -/
def shardsWithGap : List GroupSummary :=
  [shardA, { shardB with firstBlock := 1048577 }, shardC]

theorem gap_rejected : checkCampaign campaign shardsWithGap = false := by rfl

/-- A broken count chain breaks telescoping. -/
def shardsWithCountBreak : List GroupSummary :=
  [shardA, { shardB with lowerCount := 36488917831 }, shardC]

theorem countBreak_rejected :
    checkCampaign campaign shardsWithCountBreak = false := by rfl

/-- An empty shard would let a producer pad the ladder. -/
def shardsWithEmpty : List GroupSummary :=
  [shardA, { shardB with blockCount := 0 }, shardC]

theorem empty_rejected : checkCampaign campaign shardsWithEmpty = false := by rfl

/-- A shard whose own closure equation fails. -/
def shardsWithBadClosure : List GroupSummary :=
  [shardA, { shardB with slots := 4358759516 }, shardC]

theorem badClosure_rejected :
    checkCampaign campaign shardsWithBadClosure = false := by rfl

/-- A campaign record that claims more slots than its shards deliver. -/
def inflatedCampaign : CampaignRecord :=
  { firstBlock := 0, blockCount := 3145728, lowerCount := 32130158315,
    slots := 13076278546, upperCount := 45206436861, root := 44 }

theorem inflatedCampaign_rejected :
    checkCampaign inflatedCampaign shards = false := by rfl

/-- A campaign record that stops short of its shards. -/
def shortCampaign : CampaignRecord :=
  { firstBlock := 0, blockCount := 2097152, lowerCount := 32130158315,
    slots := 13076278545, upperCount := 45206436860, root := 44 }

theorem shortCampaign_rejected :
    checkCampaign shortCampaign shards = false := by rfl

/-- An out-of-range digest. -/
def shardsWithHugeDigest : List GroupSummary :=
  [shardA, { shardB with digest := digestBound }, shardC]

theorem hugeDigest_rejected :
    checkCampaign campaign shardsWithHugeDigest = false := by rfl

/-! ## The accepted ladder's consequences -/

theorem campaign_chainValid :
    GroupChainValid campaign.firstBlock campaign.lowerCount shards :=
  (checkCampaign_sound campaign_accepts).1

theorem campaign_blocks : groupBlockSum shards = campaign.blockCount :=
  (checkCampaign_sound campaign_accepts).2.1

theorem campaign_slots : groupSlotSum shards = campaign.slots :=
  (checkCampaign_sound campaign_accepts).2.2.1

/-- The full two-tier aggregation, given one imported shard-refinement fact
per shard.  Nothing here discharges those facts: that is the compiled
checker's job. -/
theorem campaign_windows
    (unitCommit : List WindowSummary → Digest)
    (shardCommit : List GroupSummary → Digest)
    (refines : ∀ shard ∈ shards, ShardRefines unitCommit shardCommit shard) :
    ∃ windows : List WindowSummary,
      windows.length = campaign.blockCount ∧
      WindowChainValid campaign.firstBlock campaign.lowerCount windows ∧
      slotSum windows = campaign.slots ∧
      campaign.lowerCount + slotSum windows = campaign.upperCount :=
  campaign_windowChain_twoTier unitCommit shardCommit campaign_accepts refines

end SparkInterval.Zeta.PT21Ladder.Test
