/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.GoldbachAtomicBatching

namespace SparkInterval.Tests.GoldbachAtomicBatchingTest

open TernaryGoldbach.GoldbachAtomicClears
open TernaryGoldbach.GoldbachAtomicBatching

private def initial : PackedState :=
  fun _ _ => true

private def firstBatch : PackedBatch :=
  { wordIndex := 7, bits := [⟨3, by norm_num⟩, ⟨11, by norm_num⟩] }

private def secondBatch : PackedBatch :=
  { wordIndex := 9, bits := [⟨2, by norm_num⟩] }

private def fallback : List AddressedClear :=
  [{ wordIndex := 7, bit := ⟨17, by norm_num⟩ }]

private def original : List AddressedClear :=
  (expandBatches [firstBatch, secondBatch] ++ fallback).reverse

example :
    applyClearMask (fun _ => true)
        [⟨3, by norm_num⟩, ⟨11, by norm_num⟩] =
      runClears (fun _ => true)
        [⟨3, by norm_num⟩, ⟨11, by norm_num⟩] :=
  applyClearMask_eq_runClears _ _

example :
    runAddressed initial original =
      runAddressed
        (runBatches initial [firstBatch, secondBatch])
        fallback := by
  apply partitioned_batch_schedule_eq
  exact List.reverse_perm _

/-- The equation covers a repeated clear as well: the combined mask and
individual atomic stream are both idempotent. -/
example (bit : Fin 64) :
    applyClearMask (fun _ => true) [bit, bit] =
      runClears (fun _ => true) [bit, bit] :=
  applyClearMask_eq_runClears _ _

/-- Capacity one forces the second distinct key through the fallback, while a
later event for the occupied key is still combined exactly. -/
example :
    let events : List AddressedClear :=
      [{ wordIndex := 7, bit := ⟨3, by norm_num⟩ },
       { wordIndex := 9, bit := ⟨2, by norm_num⟩ },
       { wordIndex := 7, bit := ⟨11, by norm_num⟩ }]
    runAddressed initial events =
      let result :=
        batchStream 1 { batches := [], fallback := [] } events
      runAddressed
        (runBatches initial result.batches) result.fallback := by
  exact bounded_batch_schedule_eq initial 1 _

example :
    let events : List AddressedClear :=
      [{ wordIndex := 7, bit := ⟨3, by norm_num⟩ },
       { wordIndex := 9, bit := ⟨2, by norm_num⟩ }]
    (batchStream 1
      { batches := [], fallback := [] } events).batches.length ≤ 1 := by
  exact batchStream_empty_capacity 1 _

/-- This exact state check confirms that capacity one really combines the
two word-7 events and sends the distinct word-9 event to fallback. -/
example :
    let first : AddressedClear :=
      { wordIndex := 7, bit := ⟨3, by norm_num⟩ }
    let overflow : AddressedClear :=
      { wordIndex := 9, bit := ⟨2, by norm_num⟩ }
    let repeatedKey : AddressedClear :=
      { wordIndex := 7, bit := ⟨11, by norm_num⟩ }
    batchStream 1 { batches := [], fallback := [] }
        [first, overflow, repeatedKey] =
      { batches :=
          [{ wordIndex := 7,
             bits := [repeatedKey.bit, first.bit] }],
        fallback := [overflow] } := by
  rfl

/-- Duplicate equal events may be collapsed when only the final physical mask
is available: addressed-clear membership, rather than multiplicity, is the
exact semantic requirement. -/
example (event : AddressedClear) :
    runAddressed initial [event, event] =
      runAddressed initial [event] := by
  apply runAddressed_eq_of_mem_iff
  intro queried
  simp

end SparkInterval.Tests.GoldbachAtomicBatchingTest
