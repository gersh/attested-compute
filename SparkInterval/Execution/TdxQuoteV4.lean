/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256Packed

/-!
# Parsing an Intel TDX v4 quote, in Lean

Until now this repository read nothing out of a TDX quote.  A receipt carried
the quote's SHA-256 and a `reportDataHash` field, and Lean checked that the
latter was the domain-separated commitment it should be -- but that the quote
*contained* that report data, and that the quote's measured configuration was
the pinned one, were assertions by whoever assembled the receipt.

This module removes those two assertions.  It parses exactly as much of the
quote as is needed to make them checkable, and nothing more.

## Layout

A v4 quote begins with a 48-byte header followed by the TD report body:

```text
offset  size  field
     0     2  version                       (little-endian, 4 for v4)
     2     2  attestation key type
     4     4  tee type                      (little-endian, 0x81 for TDX)
     6    ..  qe svn, pce svn, qe vendor id, user data
    48   584  TD report body
```

and the 584-byte TD report body is

```text
relative  size  field                         absolute
       0    16  tee tcb svn                         48
      16    48  mrseam                              64
      64    48  mrsignerseam                       112
     112     8  seam attributes                    160
     120     8  td attributes                      168
     128     8  xfam                               176
     136    48  mrtd                               184
     184    48  mrconfigid                         232
     232    48  mrowner                            280
     280    48  mrownerconfig                      328
     328    48  rtmr0                              376
     376    48  rtmr1                              424
     424    48  rtmr2                              472
     472    48  rtmr3                              520
     520    64  report data                        568
```

so the quote must be at least 632 bytes for any of this to exist.  Everything
after the report body is the ECDSA signature, the QE report, and the PCK
certificate chain.

## What is deliberately *not* parsed

The PCK certificate chain, the TCB levels, and the QE identity.  Appraising
those is X.509 and ASN.1 work against Intel's live TCB data, it is what
`dcap-qvl` exists for, and it stays outside Lean.  The pinned
`quoteAppraisalPolicyHash` and `quoteAppraisalArtifactHash` remain exactly
what they were: a commitment to *which* external appraiser ran, not a Lean
proof that it was right.  Nothing in this module should be read as verifying
an Intel signature.

## Representation

Quotes are carried as `SHA256.PackedBytes`: one big-endian natural plus a
byte count.  Field extraction is then a shift and a mask, both GMP-accelerated
kernel primitives, so pulling a 48-byte measurement out of a five-kilobyte
quote costs two big-integer operations rather than thousands of list steps.
`SHA256.packedByteSource_realizes` ties that representation to an ordinary
byte list, so the digest of a packed quote is provably the SHA-256 of its
bytes.

No axiom, `sorry`, or `native_decide` appears in this file.
-/

set_option autoImplicit false
set_option exponentiation.threshold 20000

namespace SparkInterval.Execution

open SparkInterval.Certificate

namespace TdxQuoteV4

/-- Offset of the TD report body inside the quote. -/
def reportBodyOffset : Nat := 48

/-- Size of the TD report body. -/
def reportBodySize : Nat := 584

/-- Smallest quote from which a report body can be read at all. -/
def minimumByteCount : Nat := reportBodyOffset + reportBodySize

/-- Absolute offset of `mrconfigid`. -/
def mrConfigIdOffset : Nat := reportBodyOffset + 184

/-- Absolute offset of `mrtd`. -/
def mrTdOffset : Nat := reportBodyOffset + 136

/-- Absolute offset of the 64-byte report data. -/
def reportDataOffset : Nat := reportBodyOffset + 520

/-- Quote format version.  Four for the format parsed here. -/
def version (quote : SHA256.PackedBytes) : Nat :=
  quote.leUInt16 0

/-- TEE type.  `0x81` is Intel TDX; `0x00` is SGX. -/
def teeType (quote : SHA256.PackedBytes) : Nat :=
  quote.leUInt32 4

/-- The 48-byte `mrtd` measurement, as a natural number. -/
def mrTd (quote : SHA256.PackedBytes) : Nat :=
  quote.field mrTdOffset 48

/-- The 48-byte `mrconfigid` measurement, as a natural number.

dstack writes `0x01` followed by the 32-byte SHA-256 of the measured
`app-compose.json`, then fifteen zero bytes. -/
def mrConfigId (quote : SHA256.PackedBytes) : Nat :=
  quote.field mrConfigIdOffset 48

/-- The first 32 bytes of the report data: the statement commitment. -/
def reportDataStatement (quote : SHA256.PackedBytes) : Nat :=
  quote.field reportDataOffset 32

/-- The last 32 bytes of the report data.  dstack leaves these zero. -/
def reportDataTail (quote : SHA256.PackedBytes) : Nat :=
  quote.field (reportDataOffset + 32) 32

/-- The report data rendered as 64 lowercase hexadecimal digits, so it can be
compared directly with a `Digest`. -/
def reportDataStatementHex (quote : SHA256.PackedBytes) : String :=
  SHA256.hexOfNat 32 (reportDataStatement quote)

/-- `mrconfigid` rendered as 96 lowercase hexadecimal digits. -/
def mrConfigIdHex (quote : SHA256.PackedBytes) : String :=
  SHA256.hexOfNat 48 (mrConfigId quote)

/-- The `mrconfigid` a dstack CVM measuring the app-compose document with
SHA-256 `composeHash` must carry: the tag byte `01`, the 32-byte compose
hash, and fifteen zero bytes. -/
def expectedMrConfigIdHex (composeHash : String) : String :=
  "01" ++ composeHash ++ "000000000000000000000000000000"

/-- **The structural check.**  A quote long enough to contain a TD report
body, in the v4 format, from an Intel TDX platform.

This is a fail-closed guard, not an appraisal: it says the bytes can be
parsed, not that Intel signed them. -/
def wellFormed (quote : SHA256.PackedBytes) : Bool :=
  minimumByteCount ≤ quote.byteCount &&
    version quote == 4 &&
    teeType quote == 0x81

/-- A quote too short to contain a TD report body is rejected. -/
theorem wellFormed_eq_false_of_short {quote : SHA256.PackedBytes}
    (hshort : quote.byteCount < minimumByteCount) :
    wellFormed quote = false := by
  simp [wellFormed, Nat.not_le.mpr hshort]

/-- A quote whose version word is not 4 is rejected. -/
theorem wellFormed_eq_false_of_version {quote : SHA256.PackedBytes}
    (hversion : version quote ≠ 4) :
    wellFormed quote = false := by
  simp [wellFormed, hversion]

/-- A quote whose TEE type is not TDX is rejected. -/
theorem wellFormed_eq_false_of_teeType {quote : SHA256.PackedBytes}
    (htee : teeType quote ≠ 0x81) :
    wellFormed quote = false := by
  simp [wellFormed, htee]

/-- **The measured-configuration binding.**

`quoteBindsCompose quote composeHash` holds when the quote's own
`mrconfigid` field is the dstack encoding of `composeHash`.  This is the
check that turns "the receipt says the compose hash was X" into "the CPU
measured X". -/
def quoteBindsCompose (quote : SHA256.PackedBytes) (composeHash : String) :
    Bool :=
  mrConfigIdHex quote == expectedMrConfigIdHex composeHash

/-- **The statement binding.**

`quoteBindsStatement quote digest` holds when the quote's report data is
exactly `digest` in its first 32 bytes and zero in its last 32.  `digest` is
supplied by the caller as the digest it *computed*, never as one it read from
a receipt. -/
def quoteBindsStatement (quote : SHA256.PackedBytes) (digest : String) :
    Bool :=
  reportDataStatementHex quote == digest && reportDataTail quote == 0

/-- A quote whose report data does not begin with `digest` cannot bind it. -/
theorem quoteBindsStatement_eq_false_of_mismatch
    {quote : SHA256.PackedBytes} {digest : String}
    (hmismatch : reportDataStatementHex quote ≠ digest) :
    quoteBindsStatement quote digest = false := by
  simp [quoteBindsStatement, hmismatch]

/-- A quote with nonzero high report data cannot bind any digest.  dstack
leaves those bytes zero, so a nonzero tail means the report data was built by
something else. -/
theorem quoteBindsStatement_eq_false_of_tail
    {quote : SHA256.PackedBytes} {digest : String}
    (htail : reportDataTail quote ≠ 0) :
    quoteBindsStatement quote digest = false := by
  simp [quoteBindsStatement, htail]

/-- A quote whose `mrconfigid` is not the dstack encoding of `composeHash`
cannot bind it. -/
theorem quoteBindsCompose_eq_false_of_mismatch
    {quote : SHA256.PackedBytes} {composeHash : String}
    (hmismatch : mrConfigIdHex quote ≠ expectedMrConfigIdHex composeHash) :
    quoteBindsCompose quote composeHash = false := by
  simp [quoteBindsCompose, hmismatch]

/-- Reading past the end of a truncated quote yields zero, never a stale or
adjacent value.  This is what makes the parser fail closed rather than
fail open on a short input: an all-zero `mrconfigid` is not the dstack
encoding of any SHA-256, and an all-zero report data prefix is not the
SHA-256 of anything anyone can exhibit. -/
theorem field_eq_zero_of_empty {start width : Nat} :
    SHA256.PackedBytes.field ⟨0, 0⟩ start width = 0 := by
  simp [SHA256.PackedBytes.field]

/-- An empty quote is rejected outright. -/
theorem wellFormed_empty : wellFormed ⟨0, 0⟩ = false :=
  wellFormed_eq_false_of_short (by decide)

end TdxQuoteV4

end SparkInterval.Execution
