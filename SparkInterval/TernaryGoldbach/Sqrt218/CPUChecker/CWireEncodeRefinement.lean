/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.CPUChecker.CRecordRefinement

/-!
# Exact source-read to canonical-encoder refinement

This module proves the byte identity facts needed to connect successful
source-level fixed-width reads to the canonical V2 encoder.  All theorems are
symbolic in an arbitrary `ByteArray`; no certificate is loaded or replayed.

`bytesAt raw start count` is the source-order list of `count` bytes beginning
at `start`.  The fixed-width theorems show that encoding each C big-endian
read returns exactly this list.  Header and record theorems then concatenate
those field identities, retaining the source reserved-byte guards.
-/

set_option autoImplicit false

namespace SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CWireEncodeRefinement

open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CHeaderRefinement
open SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CRecordRefinement

/-! ## Contiguous byte windows -/

def bytesAt (raw : ByteArray) (start count : Nat) : List UInt8 :=
  (List.range count).map fun index => raw.get! (start + index)

theorem bytesAt_append (raw : ByteArray) (start left right : Nat) :
    bytesAt raw start left ++ bytesAt raw (start + left) right =
      bytesAt raw start (left + right) := by
  simp only [bytesAt, List.range_add, List.map_append]
  congr 1
  simp [Function.comp_def, Nat.add_assoc]

theorem bytesAt_toByteArray_eq_extract
    (raw : ByteArray) (start count : Nat)
    (hbound : start + count ≤ raw.size) :
    (bytesAt raw start count).toByteArray =
      raw.extract start (start + count) := by
  apply ByteArray.ext
  rw [List.data_toByteArray, ByteArray.data_extract]
  apply Array.ext
  · simp [bytesAt, hbound]
  · intro index hleft _hright
    have hindex : index < count := by
      simpa [bytesAt] using hleft
    have hraw : start + index < raw.size := by
      omega
    rw [List.getElem_toArray]
    simp only [bytesAt, List.getElem_map, List.getElem_range]
    rw [Array.getElem_extract]
    cases raw with
    | mk data =>
        exact getElem!_pos data (start + index) (by
          simpa only [ByteArray.size] using hraw)

theorem bytesAt_zero_size_toByteArray (raw : ByteArray) :
    (bytesAt raw 0 raw.size).toByteArray = raw := by
  apply ByteArray.ext
  rw [List.data_toByteArray]
  apply Array.ext
  · simp [bytesAt]
  · intro index _hleft hright
    rw [List.getElem_toArray]
    simp only [bytesAt, List.getElem_map, List.getElem_range,
      Nat.zero_add]
    cases raw with
    | mk data =>
        exact getElem!_pos data index hright

/-! ## Fixed-width big-endian round trips -/

theorem encodeBE16_readBE16 (b0 b1 : UInt8) :
    Wire.encodeBE16 (CPrimitives.readBE16 b0 b1) =
      some [b0, b1] := by
  have h0 := UInt8.toNat_lt b0
  have h1 := UInt8.toNat_lt b1
  unfold Wire.encodeBE16 Wire.encodeBE
  rw [if_pos (by
    norm_num
    exact CPrimitives.readBE16_fits b0 b1)]
  rw [show List.range 2 = [0, 1] by decide]
  simp only [List.map_cons, List.map_nil]
  simp only [CPrimitives.readBE16]
  simp only [Option.some.injEq, List.cons.injEq, and_true]
  constructor
  · apply UInt8.ext
    norm_num at h0 h1 ⊢
    omega
  · apply UInt8.ext
    norm_num at h0 h1 ⊢

theorem encodeBE32_readBE32 (b0 b1 b2 b3 : UInt8) :
    Wire.encodeBE32 (CPrimitives.readBE32 b0 b1 b2 b3) =
      some [b0, b1, b2, b3] := by
  have h0 := UInt8.toNat_lt b0
  have h1 := UInt8.toNat_lt b1
  have h2 := UInt8.toNat_lt b2
  have h3 := UInt8.toNat_lt b3
  unfold Wire.encodeBE32 Wire.encodeBE
  rw [if_pos (by
    norm_num
    exact CPrimitives.readBE32_fits b0 b1 b2 b3)]
  rw [show List.range 4 = [0, 1, 2, 3] by decide]
  simp only [List.map_cons, List.map_nil]
  simp only [CPrimitives.readBE32]
  simp only [Option.some.injEq, List.cons.injEq, and_true]
  repeat' apply And.intro
  all_goals
    apply UInt8.ext
    norm_num at h0 h1 h2 h3 ⊢
    omega

theorem encodeBE64_readBE64
    (b0 b1 b2 b3 b4 b5 b6 b7 : UInt8) :
    Wire.encodeBE64
        (CPrimitives.readBE64 b0 b1 b2 b3 b4 b5 b6 b7) =
      some [b0, b1, b2, b3, b4, b5, b6, b7] := by
  have h0 := UInt8.toNat_lt b0
  have h1 := UInt8.toNat_lt b1
  have h2 := UInt8.toNat_lt b2
  have h3 := UInt8.toNat_lt b3
  have h4 := UInt8.toNat_lt b4
  have h5 := UInt8.toNat_lt b5
  have h6 := UInt8.toNat_lt b6
  have h7 := UInt8.toNat_lt b7
  unfold Wire.encodeBE64 Wire.encodeBE
  rw [if_pos (by
    norm_num [limbBase]
    exact CPrimitives.readBE64_fits b0 b1 b2 b3 b4 b5 b6 b7)]
  rw [show List.range 8 = [0, 1, 2, 3, 4, 5, 6, 7] by decide]
  simp only [List.map_cons, List.map_nil]
  simp only [CPrimitives.readBE64]
  simp only [Option.some.injEq, List.cons.injEq, and_true]
  repeat' apply And.intro
  all_goals
    apply UInt8.ext
    norm_num at h0 h1 h2 h3 h4 h5 h6 h7 ⊢
    omega

theorem encodeBE16_cReadBE16At (raw : ByteArray) (offset : Nat) :
    Wire.encodeBE16 (cReadBE16At raw offset) =
      some (bytesAt raw offset 2) := by
  simpa [cReadBE16At, bytesAt, show List.range 2 = [0, 1] by decide,
    Nat.add_assoc] using
    encodeBE16_readBE16 (raw.get! offset) (raw.get! (offset + 1))

theorem encodeBE32_cReadBE32At (raw : ByteArray) (offset : Nat) :
    Wire.encodeBE32 (cReadBE32At raw offset) =
      some (bytesAt raw offset 4) := by
  simpa [cReadBE32At, bytesAt,
    show List.range 4 = [0, 1, 2, 3] by decide,
    Nat.add_assoc] using
    encodeBE32_readBE32
      (raw.get! offset) (raw.get! (offset + 1))
      (raw.get! (offset + 2)) (raw.get! (offset + 3))

theorem encodeBE64_cReadBE64At (raw : ByteArray) (offset : Nat) :
    Wire.encodeBE64 (cReadBE64At raw offset) =
      some (bytesAt raw offset 8) := by
  simpa [cReadBE64At, bytesAt,
    show List.range 8 = [0, 1, 2, 3, 4, 5, 6, 7] by decide,
    Nat.add_assoc] using
    encodeBE64_readBE64
      (raw.get! offset) (raw.get! (offset + 1))
      (raw.get! (offset + 2)) (raw.get! (offset + 3))
      (raw.get! (offset + 4)) (raw.get! (offset + 5))
      (raw.get! (offset + 6)) (raw.get! (offset + 7))

/-! ## Complete header -/

theorem encodeHeader_cDecodedHeader
    {raw : ByteArray} (accepted : COpenV2Accepted raw) :
    Wire.encodeHeader (cDecodedHeader raw) =
      some (bytesAt raw 0 headerBytes) := by
  have hmagic :
      Wire.magicBytes = bytesAt raw 0 8 := by
    apply List.toByteArray_inj.mp
    rw [bytesAt_toByteArray_eq_extract raw 0 8 (by
      have := accepted.headerInside
      norm_num [headerBytes] at *
      omega)]
    exact accepted.sameMagic.symm
  have hversion :
      Wire.encodeBE16 (cDecodedHeader raw).version =
        some (bytesAt raw 8 2) := by
    simpa only [cDecodedHeader] using
      encodeBE16_cReadBE16At raw 8
  have hwidth :
      Wire.encodeBE16 headerBytes =
        some (bytesAt raw 10 2) := by
    rw [← accepted.width]
    exact encodeBE16_cReadBE16At raw 10
  have hflags :
      Wire.encodeBE32 (cDecodedHeader raw).flags =
        some (bytesAt raw 12 4) := by
    simpa only [cDecodedHeader] using
      encodeBE32_cReadBE32At raw 12
  have hbound :
      Wire.encodeBE64 (cDecodedHeader raw).bound =
        some (bytesAt raw 16 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 16
  have hreused :
      Wire.encodeBE64 (cDecodedHeader raw).reusedPrimeBound =
        some (bytesAt raw 24 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 24
  have hseed :
      Wire.encodeBE64 (cDecodedHeader raw).logSeedAt =
        some (bytesAt raw 32 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 32
  have hlogScale :
      Wire.encodeBE64 (cDecodedHeader raw).logScale =
        some (bytesAt raw 40 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 40
  have hreciprocal :
      Wire.encodeBE64 (cDecodedHeader raw).reciprocalScale =
        some (bytesAt raw 48 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 48
  have hprimeCount :
      Wire.encodeBE64 (cDecodedHeader raw).primeCount =
        some (bytesAt raw 56 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 56
  have hfactorRefCount :
      Wire.encodeBE64 (cDecodedHeader raw).factorRefCount =
        some (bytesAt raw 64 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 64
  have hfactorPairCount :
      Wire.encodeBE64 (cDecodedHeader raw).factorPairCount =
        some (bytesAt raw 72 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 72
  have heventCount :
      Wire.encodeBE64 (cDecodedHeader raw).eventCount =
        some (bytesAt raw 80 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 80
  have hpowerRefCount :
      Wire.encodeBE64 (cDecodedHeader raw).powerRefCount =
        some (bytesAt raw 88 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 88
  have hprimesOffset :
      Wire.encodeBE64 (cDecodedHeader raw).primesOffset =
        some (bytesAt raw 96 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 96
  have hfactorRefsOffset :
      Wire.encodeBE64 (cDecodedHeader raw).factorRefsOffset =
        some (bytesAt raw 104 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 104
  have hfactorPairsOffset :
      Wire.encodeBE64 (cDecodedHeader raw).factorPairsOffset =
        some (bytesAt raw 112 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 112
  have heventsOffset :
      Wire.encodeBE64 (cDecodedHeader raw).eventsOffset =
        some (bytesAt raw 120 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 120
  have hpowerRefsOffset :
      Wire.encodeBE64 (cDecodedHeader raw).powerRefsOffset =
        some (bytesAt raw 128 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 128
  have harchiveBytes :
      Wire.encodeBE64 (cDecodedHeader raw).archiveBytes =
        some (bytesAt raw 136 8) := by
    simpa only [cDecodedHeader] using
      encodeBE64_cReadBE64At raw 136
  have hreserved0 :
      Wire.zeroBytes 8 = bytesAt raw 144 8 := by
    have h := encodeBE64_cReadBE64At raw 144
    rw [accepted.reserved0] at h
    simpa [Wire.encodeBE64, Wire.encodeBE, Wire.zeroBytes] using
      Option.some.inj h
  have hreserved1 :
      Wire.zeroBytes 8 = bytesAt raw 152 8 := by
    have h := encodeBE64_cReadBE64At raw 152
    rw [accepted.reserved1] at h
    simpa [Wire.encodeBE64, Wire.encodeBE, Wire.zeroBytes] using
      Option.some.inj h
  have hreserved :
      Wire.zeroBytes 16 = bytesAt raw 144 16 := by
    calc
      Wire.zeroBytes 16 =
          Wire.zeroBytes 8 ++ Wire.zeroBytes 8 := by decide
      _ = bytesAt raw 144 8 ++ bytesAt raw 152 8 :=
        congrArg₂ (· ++ ·) hreserved0 hreserved1
      _ = bytesAt raw 144 16 := by
        simpa using bytesAt_append raw 144 8 8
  unfold Wire.encodeHeader
  simp only [hversion, hwidth, hflags, hbound, hreused, hseed,
    hlogScale, hreciprocal, hprimeCount, hfactorRefCount,
    hfactorPairCount, heventCount, hpowerRefCount, hprimesOffset,
    hfactorRefsOffset, hfactorPairsOffset, heventsOffset,
    hpowerRefsOffset, harchiveBytes, Option.bind_eq_bind,
    Option.bind_some]
  rw [hmagic, hreserved]
  rw [bytesAt_append raw 0 8 2,
    bytesAt_append raw 0 10 2,
    bytesAt_append raw 0 12 4,
    bytesAt_append raw 0 16 8,
    bytesAt_append raw 0 24 8,
    bytesAt_append raw 0 32 8,
    bytesAt_append raw 0 40 8,
    bytesAt_append raw 0 48 8,
    bytesAt_append raw 0 56 8,
    bytesAt_append raw 0 64 8,
    bytesAt_append raw 0 72 8,
    bytesAt_append raw 0 80 8,
    bytesAt_append raw 0 88 8,
    bytesAt_append raw 0 96 8,
    bytesAt_append raw 0 104 8,
    bytesAt_append raw 0 112 8,
    bytesAt_append raw 0 120 8,
    bytesAt_append raw 0 128 8,
    bytesAt_append raw 0 136 8,
    bytesAt_append raw 0 144 16]
  rfl

/-! ## Complete fixed records -/

theorem CPrimeAtAccepted.encodeRecord
    {raw : ByteArray} {index offset : Nat}
    (accepted : CPrimeAtAccepted raw index offset) :
    Wire.encodePrimeRecord (cDecodedPrimeRecord raw offset) =
      some (bytesAt raw offset primeRecordBytes) := by
  have h0 := encodeBE64_cReadBE64At raw offset
  have h8 := encodeBE64_cReadBE64At raw (offset + 8)
  have h16 := encodeBE64_cReadBE64At raw (offset + 16)
  have h24 := encodeBE32_cReadBE32At raw (offset + 24)
  have h28 := encodeBE32_cReadBE32At raw (offset + 28)
  have h32 := encodeBE64_cReadBE64At raw (offset + 32)
  have h40 := encodeBE64_cReadBE64At raw (offset + 40)
  have h48 := encodeBE32_cReadBE32At raw (offset + 48)
  have h56 := encodeBE64_cReadBE64At raw (offset + 56)
  have h64 := encodeBE64_cReadBE64At raw (offset + 64)
  have hreserved0 :
      Wire.zeroBytes 4 = bytesAt raw (offset + 52) 4 := by
    have h := encodeBE32_cReadBE32At raw (offset + 52)
    rw [accepted.reserved0] at h
    simpa [Wire.encodeBE32, Wire.encodeBE, Wire.zeroBytes] using
      Option.some.inj h
  have hreserved1 :
      Wire.zeroBytes 8 = bytesAt raw (offset + 72) 8 := by
    have h := encodeBE64_cReadBE64At raw (offset + 72)
    rw [accepted.reserved1] at h
    simpa [Wire.encodeBE64, Wire.encodeBE, Wire.zeroBytes] using
      Option.some.inj h
  unfold Wire.encodePrimeRecord
  simp only [cDecodedPrimeRecord, h0, h8, h16, h24, h28, h32,
    h40, h48, h56, h64, Option.bind_eq_bind, Option.bind_some]
  rw [hreserved0, hreserved1]
  rw [bytesAt_append raw offset 8 8,
    bytesAt_append raw offset 16 8,
    bytesAt_append raw offset 24 4,
    bytesAt_append raw offset 28 4,
    bytesAt_append raw offset 32 8,
    bytesAt_append raw offset 40 8,
    bytesAt_append raw offset 48 4,
    bytesAt_append raw offset 52 4,
    bytesAt_append raw offset 56 8,
    bytesAt_append raw offset 64 8,
    bytesAt_append raw offset 72 8]
  rfl

theorem CFactorPairAtAccepted.encodeRecord
    {raw : ByteArray} {index offset : Nat}
    (_accepted : CFactorPairAtAccepted raw index offset) :
    Wire.encodeFactorPair (cDecodedFactorPair raw offset) =
      some (bytesAt raw offset factorPairBytes) := by
  have h0 := encodeBE64_cReadBE64At raw offset
  have h8 := encodeBE64_cReadBE64At raw (offset + 8)
  unfold Wire.encodeFactorPair
  simp only [cDecodedFactorPair, h0, h8, Option.bind_eq_bind,
    Option.bind_some]
  rw [bytesAt_append raw offset 8 8]
  rfl

theorem CEventAtAccepted.encodeRecord
    {raw : ByteArray} {index offset : Nat}
    (accepted : CEventAtAccepted raw index offset) :
    Wire.encodeEventRecord (cDecodedEventRecord raw offset) =
      some (bytesAt raw offset eventRecordBytes) := by
  have h0 := encodeBE64_cReadBE64At raw offset
  have h8 := encodeBE64_cReadBE64At raw (offset + 8)
  have h16 := encodeBE32_cReadBE32At raw (offset + 16)
  have h24 := encodeBE64_cReadBE64At raw (offset + 24)
  have hreserved :
      Wire.zeroBytes 4 = bytesAt raw (offset + 20) 4 := by
    have h := encodeBE32_cReadBE32At raw (offset + 20)
    rw [accepted.reserved] at h
    simpa [Wire.encodeBE32, Wire.encodeBE, Wire.zeroBytes] using
      Option.some.inj h
  unfold Wire.encodeEventRecord
  simp only [cDecodedEventRecord, h0, h8, h16, h24,
    Option.bind_eq_bind, Option.bind_some]
  rw [hreserved]
  rw [bytesAt_append raw offset 8 8,
    bytesAt_append raw offset 16 4,
    bytesAt_append raw offset 20 4,
    bytesAt_append raw offset 24 8]
  rfl

end SparkInterval.TernaryGoldbach.Sqrt218CPUChecker.CWireEncodeRefinement
