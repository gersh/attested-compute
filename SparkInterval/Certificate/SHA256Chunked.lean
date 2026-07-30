/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256

/-!
# Splitting a SHA-256 reduction into kernel-sized pieces

`SHA256.hashSource` is a single tail-recursive fold over 64-byte blocks.  It
is executable and it is proved equal to the linked-list reference, but a
whole-message reduction is not affordable in the Lean kernel at the sizes this
repository actually needs.  Measured on this host, with `lakefile.toml`'s
`-M8192` cap in force:

```text
blocks   bytes   result
     1      55   ok        4.6 s
     2     119   ok        5.9 s
     4     247   ok        8.1 s
     8     503   ok       11.6 s
    12     759   (kernel) excessive memory consumption detected
    18    1080   (kernel) excessive memory consumption detected
```

The reason is not arithmetic.  Every word operation is `Nat` and every `Nat`
primitive the compression function uses (`+`, `%`, `Nat.land`, `Nat.xor`,
`Nat.shiftLeft`, `Nat.shiftRight`) is GMP-accelerated in the kernel.  What
grows is the *term*: `foldSourceBlocks` applied to a literal count unfolds
into a nest of `compressFrom` applications, and the kernel holds every
intermediate `State` as an unevaluated application until the outermost
comparison forces it.  Memory therefore grows with the block count, not with
the arithmetic.

The fix is to force the intermediate states by hand.  `foldSourceBlocks` is
tail-recursive in both its offset and its accumulator, so it splits exactly:

```text
foldSourceBlocks step (m + n) offset state
  = foldSourceBlocks step n (offset + m * 64) (foldSourceBlocks step m offset state)
```

Stating each intermediate `State` as an explicit eight-word literal and
proving each chunk separately keeps every individual kernel reduction inside
the eight-block regime that is known to fit.  Nothing about the hash changes:
the chunk lemmas compose to the same `hashSource`, which
`SHA256.hashSource_eq_hashBytes_of_realizes` already identifies with the
linked-list reference implementation.

This file introduces no axiom, no `sorry`, and no `native_decide`.
-/

set_option autoImplicit false

namespace SparkInterval.Certificate.SHA256

/-- The single 64-byte step `hashSource` folds over, named so that chunk
lemmas can mention it. -/
def sourceBlockStep (source : ByteSource) (current : State) (offset : Nat) :
    State :=
  compressFrom current fun position => source.paddedByte (offset + position)

/-- `hashSource` is exactly the fold of `sourceBlockStep`. -/
theorem hashSource_eq_foldSourceBlocks (source : ByteSource) :
    hashSource source =
      foldSourceBlocks (sourceBlockStep source) (source.paddedSize / 64) 0
        initialState :=
  rfl

/-- **The splitting law.**  A fold of `m + n` blocks starting at `offset` is
the fold of the last `n` blocks, starting where the first `m` ended, applied
to the fold of the first `m`.

This is a statement about `foldSourceBlocks` alone; it does not mention
SHA-256 and holds for any step function. -/
theorem foldSourceBlocks_add {α : Type} (step : α → Nat → α)
    (m n offset : Nat) (state : α) :
    foldSourceBlocks step (m + n) offset state =
      foldSourceBlocks step n (offset + m * 64)
        (foldSourceBlocks step m offset state) := by
  induction m generalizing offset state with
  | zero => simp [foldSourceBlocks]
  | succ m ih =>
      have hcount : m + 1 + n = m + n + 1 := by omega
      rw [hcount, foldSourceBlocks, ih (offset + 64) (step state offset),
        foldSourceBlocks]
      congr 1
      omega

/-- Chain one chunk onto another.  Both premises are ordinary equalities
between explicit `State` literals, so each is discharged by its own bounded
kernel reduction. -/
theorem foldSourceBlocks_of_split {α : Type} (step : α → Nat → α)
    {m n offset : Nat} {state mid final : α}
    (hfirst : foldSourceBlocks step m offset state = mid)
    (hsecond : foldSourceBlocks step n (offset + m * 64) mid = final) :
    foldSourceBlocks step (m + n) offset state = final := by
  rw [foldSourceBlocks_add, hfirst, hsecond]

/-- Read a whole-message hash off a chunked fold.

`hcount` records the message's block count, `hchunks` is the chained chunk
equality, and the conclusion is the ordinary `hashSource`.  Everything the
existing correctness theorems say about `hashSource` therefore applies
unchanged. -/
theorem hashSource_eq_of_chunks {source : ByteSource} {blocks : Nat}
    {final : State}
    (hcount : source.paddedSize / 64 = blocks)
    (hchunks :
      foldSourceBlocks (sourceBlockStep source) blocks 0 initialState = final) :
    hashSource source = final := by
  rw [hashSource_eq_foldSourceBlocks, hcount, hchunks]

/-- The hexadecimal digest of a chunked fold. -/
theorem digestSource_eq_of_chunks {source : ByteSource} {blocks : Nat}
    {final : State}
    (hcount : source.paddedSize / 64 = blocks)
    (hchunks :
      foldSourceBlocks (sourceBlockStep source) blocks 0 initialState = final) :
    digestSource source = stateHex final := by
  unfold digestSource
  rw [hashSource_eq_of_chunks hcount hchunks]

/-- The hexadecimal digest of a packed byte array, via a chunked fold. -/
theorem digestByteArray_eq_of_chunks {bytes : ByteArray} {blocks : Nat}
    {final : State}
    (hcount : (ByteSource.ofByteArray bytes).paddedSize / 64 = blocks)
    (hchunks :
      foldSourceBlocks (sourceBlockStep (ByteSource.ofByteArray bytes)) blocks
        0 initialState = final) :
    digestByteArray bytes = stateHex final :=
  digestSource_eq_of_chunks hcount hchunks

/-- The hexadecimal digest of a domain prefix followed by a byte array, via a
chunked fold.  This is the shape every attestation preimage in this
repository takes. -/
theorem digestPrefixSlice_eq_of_chunks {domainPrefix bytes : ByteArray}
    {start stop blocks : Nat} {final : State}
    (hcount :
      (ByteSource.append (ByteSource.ofByteArray domainPrefix)
        (ByteSource.slice bytes start stop)).paddedSize / 64 = blocks)
    (hchunks :
      foldSourceBlocks
        (sourceBlockStep (ByteSource.append
          (ByteSource.ofByteArray domainPrefix)
          (ByteSource.slice bytes start stop))) blocks 0 initialState
        = final) :
    digestPrefixSlice domainPrefix bytes start stop = stateHex final :=
  digestSource_eq_of_chunks hcount hchunks

end SparkInterval.Certificate.SHA256
