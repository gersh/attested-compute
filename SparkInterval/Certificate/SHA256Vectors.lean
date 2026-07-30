/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256Packed

/-!
# FIPS 180-4 test vectors, checked by the Lean kernel

The implementation in `Certificate/SHA256.lean` is proved internally
consistent -- the packed streaming path is proved equal to the linked-list
reference -- but internal consistency does not say the two of them compute
SHA-256.  Only agreement with the published vectors says that.

Every theorem below is closed by `rfl`, so the digests are produced by kernel
reduction of the repository's own implementation and compared with the
constants from FIPS 180-4 and from NIST's byte-oriented SHA-256 examples.
No `native_decide`, no `decide +kernel`, no axiom.

The vectors are, in order:

* the empty message (0 bytes, 1 padded block);
* `"abc"` (3 bytes, 1 block) -- FIPS 180-4 Appendix B.1;
* the 56-byte two-block-boundary message -- FIPS 180-4 Appendix B.2;
* the 112-byte message -- the SHA-512 B.3 message run through SHA-256, which
  is NIST's standard 2-block byte-oriented example;
* 1 000 bytes of `0x61` -- checks that the length encoding is right well past
  a single block.

`digestString` is the UTF-8 wrapper, so the ASCII vectors exercise the same
path production receipts use.  The 1 000-byte vector is driven through the
packed source with the chunk splitting of `SHA256Chunked`, which is the only
way a message that size fits the build's kernel memory cap; that is itself a
test of the splitting law.
-/

set_option autoImplicit false
set_option maxRecDepth 100000
set_option maxHeartbeats 1000000
set_option exponentiation.threshold 20000

namespace SparkInterval.Certificate.SHA256.Vectors

/-- FIPS 180-4: the empty message. -/
theorem digest_empty :
    digestString "" =
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" :=
  rfl

/-- FIPS 180-4 Appendix B.1: `"abc"`. -/
theorem digest_abc :
    digestString "abc" =
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" :=
  rfl

/-- FIPS 180-4 Appendix B.2: the 448-bit message.  56 bytes, so the padding
spills into a second block. -/
theorem digest_fips_b2 :
    digestString
        "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq" =
      "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1" :=
  rfl

/-- NIST's 112-byte two-block byte-oriented example. -/
theorem digest_nist_112 :
    digestString
        ("abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmn" ++
         "hijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu") =
      "cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1" :=
  rfl

/-! ## A vector past the kernel's single-reduction budget

One thousand `a` bytes is sixteen padded blocks.  Reduced in one piece that
exceeds the `-M8192` cap the build imposes; split into chunks of six, six and
four it does not.  The intermediate states are exactly the ones
`tools/tg_sha256_chunk_witnesses.py --text "aaa...a" --chunk 6` prints, and
the digest is checked against an independent SHA-256 by
`tests/test_sha256_lean_vectors.py`.

This vector exists to exercise `SHA256Chunked.foldSourceBlocks_of_split` on a
message no single kernel reduction in this repository could otherwise reach. -/

/-- One thousand `0x61` bytes, packed big-endian. -/
def thousandA : PackedBytes where
  packed := 0x61616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161616161
  byteCount := 1000

/-- The packed literal really is one thousand `a` bytes.  Checking the count,
both ends, the middle, and the first and last eight-byte words is cheap and
rules out a truncated, padded, or shifted literal; the digest theorem below
would fail on any of those anyway. -/
theorem thousandA_bytes :
    thousandA.byteCount = 1000 ∧
      thousandA.byte 0 = 0x61 ∧
      thousandA.byte 499 = 0x61 ∧
      thousandA.byte 999 = 0x61 ∧
      thousandA.field 0 8 = 0x6161616161616161 ∧
      thousandA.field 992 8 = 0x6161616161616161 :=
  ⟨rfl, rfl, rfl, rfl, rfl, rfl⟩

theorem thousandA_blocks : thousandA.source.paddedSize / 64 = 6 + (6 + 4) :=
  rfl

/-- Chunk 0: blocks 0 to 6. -/
private theorem thousandA_chunk0 :
    foldSourceBlocks (sourceBlockStep thousandA.source) 6 0
        { a := 0x6a09e667, b := 0xbb67ae85, c := 0x3c6ef372, d := 0xa54ff53a, e := 0x510e527f, f := 0x9b05688c, g := 0x1f83d9ab, h := 0x5be0cd19 } =
      { a := 0x846016fd, b := 0x63ce922b, c := 0xc214d039, d := 0x178eceab, e := 0x7fd0bfb1, f := 0x2d7ce142, g := 0xbdcb169f, h := 0xbdb11325 } := by
  rfl

/-- Chunk 1: blocks 6 to 12. -/
private theorem thousandA_chunk1 :
    foldSourceBlocks (sourceBlockStep thousandA.source) 6 384
        { a := 0x846016fd, b := 0x63ce922b, c := 0xc214d039, d := 0x178eceab, e := 0x7fd0bfb1, f := 0x2d7ce142, g := 0xbdcb169f, h := 0xbdb11325 } =
      { a := 0x66ce742d, b := 0xfa30cd09, c := 0x0656becf, d := 0xd3fd9f28, e := 0xda67d3ad, f := 0xe8917c49, g := 0x99338374, h := 0x714e86a8 } := by
  rfl

/-- Chunk 2: blocks 12 to 16. -/
private theorem thousandA_chunk2 :
    foldSourceBlocks (sourceBlockStep thousandA.source) 4 768
        { a := 0x66ce742d, b := 0xfa30cd09, c := 0x0656becf, d := 0xd3fd9f28, e := 0xda67d3ad, f := 0xe8917c49, g := 0x99338374, h := 0x714e86a8 } =
      { a := 0x41edece4, b := 0x2d63e8d9, c := 0xbf515a9b, d := 0xa6932e1c, e := 0x20cbc9f5, f := 0xa5d13464, g := 0x5adb5db1, h := 0xb9737ea3 } := by
  rfl

/-- SHA-256 of one thousand `a` bytes, assembled from the three chunks. -/
theorem digest_thousandA :
    thousandA.digest =
      "41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3" := by
  rw [PackedBytes.digest,
    digestSource_eq_of_chunks thousandA_blocks
      (foldSourceBlocks_of_split _ thousandA_chunk0
        (foldSourceBlocks_of_split _ thousandA_chunk1 thousandA_chunk2))]
  rfl

end SparkInterval.Certificate.SHA256.Vectors
