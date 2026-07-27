/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.RSA

/-!
# NIST P-256 (secp256r1) ECDSA signature verification

This module implements ECDSA signature verification over the NIST P-256 curve
with SHA-256, as executable Lean.  It follows the conventions of
`SparkInterval.Certificate.RSA`: it is a total, fail-closed, executable
checker, it contains no theorems, and its correctness is established by
reading it rather than by proof against Mathlib.  All arithmetic is direct
`Nat` arithmetic; Mathlib's abstract elliptic-curve development is deliberately
not used, because instantiating it here would be both slower to evaluate and
harder to audit than the explicit modular formulas below.

## Trust surface

Nothing in this file is an axiom and nothing here uses `native_decide`.
Evaluating a full verification inside the Lean kernel (`decide`) is possible
but slow; see the performance note at the end of this docstring.  Any caller
that closes a verification with `native_decide` adds `Lean.ofReduceBool` to its
own trust surface, and must say so.  This module makes no such choice on the
caller's behalf.

## Scope: this is a primitive, not attestation

A working P-256 verifier is **necessary but nowhere near sufficient** for Intel
TDX / SGX DCAP quote verification.  Nothing in this file parses, validates, or
interprets an attestation quote.  Real DCAP verification additionally requires
all of the following, none of which is implemented here:

* parsing the quote structure (header, TD report body / ISV report, signature
  data, certification data) and binding the report data to the payload;
* verifying the PCK certificate chain (PCK leaf -> Intel SGX PCK Platform or
  Processor CA -> Intel SGX Root CA), including X.509 DER parsing, validity
  periods, basic constraints, key usage, and the Intel SGX extensions;
* pinning and checking the Intel SGX Root CA against a reviewed trust anchor;
* checking certificate revocation (Root CA CRL and PCK CA CRL);
* fetching, authenticating, and evaluating the TCB info for the platform's
  FMSPC and comparing the platform's TCB components against TCB levels, with a
  policy for `OutOfDate`, `ConfigurationNeeded`, `Revoked`, and similar states;
* checking the QE identity (`QEIdentity`) and the quoting enclave's report,
  including the QE report signature and the `qe_report_data` binding to the
  attestation key;
* checking freshness/expiry of the collateral itself.

This file supplies exactly one of the cryptographic primitives that such a
verifier would need, and nothing else.  It is not wired into any trust path.

## Conventions and deliberate limitations

* Hex input is canonical lowercase, of exact expected length; anything else is
  rejected before any arithmetic runs.  Uppercase is rejected so a signed wire
  representation has a unique spelling (inherited from `RSA.lean`).
* Signatures are the fixed-width 64-byte `r || s` form.  ASN.1 / DER-encoded
  ECDSA signatures are **not** accepted; a caller holding DER must convert and
  must itself reject non-canonical DER.
* Public keys are the SEC1 *uncompressed* 65-byte form `04 || X || Y`.
  Compressed points are not accepted.
* Scalar multiplication is a plain most-significant-bit-first double-and-add
  and is *not* constant time.  That is acceptable here because verification
  consumes only public values (public key, signature, message).  Never reuse
  these routines for operations on a private key.

## Signature malleability

ECDSA signatures over a prime-order group are malleable: if `(r, s)` verifies
for a message under a key, then so does `(r, n - s)`, because negating `s`
negates `u1` and `u2` together, which negates `R` and leaves `R.x` unchanged.
`verifyDigestHex` implements the standard behaviour and accepts both.  A caller
that needs signature uniqueness (for example, when a signature is hashed into
an identifier) should additionally require the canonical low-`s` form,
`2 * s <= n - 1`; `isLowS` is provided for that purpose but is intentionally
not enforced here.  Whether to require it is a policy decision for the owner of
the surrounding trust boundary, not for this primitive.

## Performance

One verification is two 256-bit scalar multiplications, roughly a thousand
times the modular-multiplication work of the RSA-3072 public-exponent check in
`RSA.lean`.  Compiled evaluation is fast (single-digit milliseconds).  Kernel
reduction (`decide` / `decide +kernel`) is far slower but was measured as
feasible; see the module's test harness for the measured numbers.
-/

set_option autoImplicit false

namespace SparkInterval.Certificate.P256

open SparkInterval.Certificate.RSA (parseLowerHexNat)

/-! ## Domain parameters

Every constant below was taken from OpenSSL's explicit encoding of the named
curve `prime256v1` (`openssl ecparam -name prime256v1 -param_enc explicit
-text -noout`) and then independently cross-checked:

* `fieldPrime` equals the closed form `2^256 - 2^224 + 2^192 + 2^96 - 1`;
* `curveA` equals `fieldPrime - 3`;
* `curveB` was re-derived from the published NIST curve SEED
  `c49d360886e704936a6678e1139d26b7819f7e90` by the ANSI X9.62 / FIPS 186-4
  procedure: with `t = 256`, `s = 1`, `h = 96`, take the rightmost 96 bits of
  `SHA-1(SEED)` with the leftmost bit cleared, concatenate `SHA-1(SEED + 1)`,
  and check `curveB^2 * c = -27 (mod fieldPrime)`;
* `groupOrder` and the base point were checked by this file's own arithmetic:
  the base point satisfies the curve equation and `groupOrder` times the base
  point is the point at infinity (`baseIsOnCurve`, `orderAnnihilatesBase`);
* the whole parameter set was checked against OpenSSL key generation: for
  freshly generated P-256 keypairs, `privateScalar * G` reproduces the public
  point OpenSSL reports.
-/

/-- The P-256 field prime, `2^256 - 2^224 + 2^192 + 2^96 - 1`. -/
def fieldPrime : Nat :=
  0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff

/-- The curve coefficient `a`, equal to `fieldPrime - 3`.  The doubling
formula below is specialized to this value. -/
def curveA : Nat := fieldPrime - 3

/-- The curve coefficient `b`. -/
def curveB : Nat :=
  0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b

/-- The order of the base point.  P-256 has cofactor 1, so this is also the
order of the whole curve group. -/
def groupOrder : Nat :=
  0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551

/-- `x` coordinate of the base point `G`. -/
def baseX : Nat :=
  0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296

/-- `y` coordinate of the base point `G`. -/
def baseY : Nat :=
  0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5

/-- Both `fieldPrime` and `groupOrder` are 256-bit, so all exponentiations and
scalar multiplications below run over a fixed 256-bit window. -/
def scalarBits : Nat := 256

/-! ## Field arithmetic modulo `fieldPrime`

Every operand of these operations is expected to be already reduced, i.e. less
than `fieldPrime`.  Each operation reduces its result, so that invariant is
maintained by construction once inputs are reduced at the parsing boundary.
-/

/-- Addition in the P-256 base field. -/
def fieldAdd (left right : Nat) : Nat := (left + right) % fieldPrime

/-- Subtraction in the P-256 base field.  The addend `fieldPrime - right %
fieldPrime` is a natural number for every `right`, so no truncating `Nat`
subtraction can occur. -/
def fieldSub (left right : Nat) : Nat :=
  (left + (fieldPrime - right % fieldPrime)) % fieldPrime

/-- Multiplication in the P-256 base field. -/
def fieldMul (left right : Nat) : Nat := (left * right) % fieldPrime

/-- Squaring in the P-256 base field. -/
def fieldSqr (value : Nat) : Nat := fieldMul value value

/-- The bits of `value` below `width`, most significant first.  Bits at or
above `width` are ignored, so callers must pass a `width` that covers the
exponent or scalar they intend. -/
def bitsMsbFirst (value width : Nat) : List Bool :=
  (List.range width).map fun index => value.testBit (width - 1 - index)

/-- `base ^ exponent mod modulus` by most-significant-bit-first repeated
squaring, using the same technique as `RSA.pow65537Mod` but with a general
`width`-bit exponent instead of the fixed public RSA exponent.

The exponent must satisfy `exponent < 2 ^ width`; higher bits are silently
ignored.  Every call in this file passes a literal `width = scalarBits` with a
fixed 256-bit exponent, so the condition holds by inspection. -/
def powModWidth (modulus base exponent width : Nat) : Nat :=
  if modulus = 0 then
    0
  else
    let reduced := base % modulus
    (bitsMsbFirst exponent width).foldl
      (fun accumulator bit =>
        let squared := (accumulator * accumulator) % modulus
        if bit then (squared * reduced) % modulus else squared)
      (1 % modulus)

/-- Multiplicative inverse in the base field by Fermat's little theorem,
`value ^ (fieldPrime - 2) mod fieldPrime`.  `fieldPrime` is prime, so this is
the inverse for every nonzero `value`.  The inverse of `0` is defined to be
`0`; callers must reject a zero input on their own, and every caller in this
file does. -/
def fieldInverse (value : Nat) : Nat :=
  powModWidth fieldPrime value (fieldPrime - 2) scalarBits

/-- Multiplicative inverse modulo `groupOrder`, again by Fermat.  `groupOrder`
is prime.  The inverse of `0` is `0`; `verifyDigestHex` rejects `s = 0` before
calling this. -/
def scalarInverse (value : Nat) : Nat :=
  powModWidth groupOrder value (groupOrder - 2) scalarBits

/-- Whether the affine point `(x, y)` lies on the curve
`y^2 = x^3 + curveA * x + curveB` over the field of `fieldPrime` elements.
The coordinate range checks are part of the predicate: an unreduced coordinate
is rejected rather than silently reduced. -/
def isOnCurve (x y : Nat) : Bool :=
  x < fieldPrime && y < fieldPrime &&
    fieldSqr y ==
      fieldAdd (fieldAdd (fieldMul x (fieldSqr x)) (fieldMul curveA x)) curveB

/-! ## Jacobian point arithmetic

Affine addition needs one modular inverse per operation.  A verification
performs roughly 512 doublings and 512 conditional additions, so affine
arithmetic would cost about a thousand Fermat exponentiations.  Jacobian
coordinates keep inversion out of the inner loop: a Jacobian triple
`(X, Y, Z)` with `Z <> 0` represents the affine point `(X / Z^2, Y / Z^3)`,
and `Z = 0` represents the point at infinity.  Exactly one inversion is done,
in `toAffine`, at the very end.
-/

/-- A point in Jacobian coordinates.  `z = 0` is the point at infinity. -/
structure Jacobian where
  /-- Jacobian `X` coordinate; the affine `x` is `X / Z^2`. -/
  x : Nat
  /-- Jacobian `Y` coordinate; the affine `y` is `Y / Z^3`. -/
  y : Nat
  /-- Jacobian `Z` coordinate; `0` marks the point at infinity. -/
  z : Nat
  deriving Repr, DecidableEq

namespace Jacobian

/-- The point at infinity.  Any triple with `z = 0` denotes it; this is the
canonical representative produced by the routines below. -/
def infinity : Jacobian := { x := 1, y := 1, z := 0 }

/-- Whether a point is the point at infinity. -/
def isInfinity (point : Jacobian) : Bool := point.z == 0

/-- Embed an affine point.  `z = 1` means the Jacobian and affine coordinates
agree. -/
def ofAffine (x y : Nat) : Jacobian := { x := x, y := y, z := 1 }

/-- Doubling in Jacobian coordinates, specialized to `a = -3`
(the "dbl-2001-b" formula).  Writing
`alpha = 3 * (X - Z^2) * (X + Z^2) = 3 * X^2 + a * Z^4` uses `a = -3` and saves
a squaring.

Both degenerate inputs behave correctly and need no special case:

* if `Z = 0` (infinity) then `Z3 = (Y + 0)^2 - Y^2 - 0 = 0`, so the result is
  again infinity;
* if `Y = 0` (a point of order two) then `gamma = 0` and
  `Z3 = Z^2 - 0 - Z^2 = 0`, i.e. infinity, which is the correct double.  P-256
  has prime order, so no such point actually occurs.
-/
def double (point : Jacobian) : Jacobian :=
  let delta := fieldSqr point.z
  let gamma := fieldSqr point.y
  let beta := fieldMul point.x gamma
  let alpha :=
    fieldMul 3 (fieldMul (fieldSub point.x delta) (fieldAdd point.x delta))
  let x3 := fieldSub (fieldSqr alpha) (fieldMul 8 beta)
  let z3 :=
    fieldSub (fieldSub (fieldSqr (fieldAdd point.y point.z)) gamma) delta
  let y3 :=
    fieldSub (fieldMul alpha (fieldSub (fieldMul 4 beta) x3))
      (fieldMul 8 (fieldSqr gamma))
  { x := x3, y := y3, z := z3 }

/-- Addition of two Jacobian points (the "add-2007-bl" formula) with all
exceptional cases handled explicitly, so the result is correct for every pair
of inputs:

* either operand at infinity returns the other operand;
* equal affine points (`u1 = u2` and `s1 = s2`) fall back to `double`, which
  the general formula cannot compute since it would divide by `h = 0`;
* opposite points (`u1 = u2`, `s1 <> s2`) return infinity.
-/
def add (left right : Jacobian) : Jacobian :=
  if left.z == 0 then
    right
  else if right.z == 0 then
    left
  else
    let z1z1 := fieldSqr left.z
    let z2z2 := fieldSqr right.z
    let u1 := fieldMul left.x z2z2
    let u2 := fieldMul right.x z1z1
    let s1 := fieldMul (fieldMul left.y right.z) z2z2
    let s2 := fieldMul (fieldMul right.y left.z) z1z1
    if u1 == u2 then
      if s1 == s2 then double left else infinity
    else
      let h := fieldSub u2 u1
      let i := fieldSqr (fieldMul 2 h)
      let j := fieldMul h i
      let r := fieldMul 2 (fieldSub s2 s1)
      let v := fieldMul u1 i
      let x3 := fieldSub (fieldSub (fieldSqr r) j) (fieldMul 2 v)
      let y3 :=
        fieldSub (fieldMul r (fieldSub v x3)) (fieldMul 2 (fieldMul s1 j))
      let z3 :=
        fieldMul
          (fieldSub (fieldSub (fieldSqr (fieldAdd left.z right.z)) z1z1) z2z2)
          h
      { x := x3, y := y3, z := z3 }

/-- Scalar multiplication by most-significant-bit-first double-and-add over a
fixed 256-bit window.  The scalar must be less than `2 ^ scalarBits`, which
holds for every scalar in this file because all scalars are reduced modulo
`groupOrder` first.

This is not constant time.  See the module docstring: verification handles only
public data. -/
def scalarMul (scalar : Nat) (point : Jacobian) : Jacobian :=
  (bitsMsbFirst scalar scalarBits).foldl
    (fun accumulator bit =>
      let doubled := accumulator.double
      if bit then doubled.add point else doubled)
    infinity

/-- Convert to affine coordinates, returning `none` for the point at infinity.
This is the only modular inversion performed per verification. -/
def toAffine (point : Jacobian) : Option (Nat × Nat) :=
  if point.z == 0 then
    none
  else
    let zInv := fieldInverse point.z
    let zInv2 := fieldSqr zInv
    let zInv3 := fieldMul zInv2 zInv
    some (fieldMul point.x zInv2, fieldMul point.y zInv3)

end Jacobian

/-- The base point `G` in Jacobian coordinates. -/
def basePoint : Jacobian := Jacobian.ofAffine baseX baseY

/-! ## Self-checks on the domain parameters

These are executable predicates, not theorems.  Evaluating them checks the
published constants against this file's own arithmetic. -/

/-- The base point satisfies the curve equation. -/
def baseIsOnCurve : Bool := isOnCurve baseX baseY

/-- `groupOrder * G` is the point at infinity. -/
def orderAnnihilatesBase : Bool :=
  (Jacobian.scalarMul groupOrder basePoint).isInfinity

/-- `1 * G` recovers the affine base point, i.e. the scalar ladder and the
affine conversion agree with the published generator. -/
def baseRoundTrips : Bool :=
  (Jacobian.scalarMul 1 basePoint).toAffine == some (baseX, baseY)

/-- `(groupOrder - 1) * G = -G`, an independent check of `groupOrder` that does
not go through the point at infinity. -/
def orderPredecessorNegatesBase : Bool :=
  (Jacobian.scalarMul (groupOrder - 1) basePoint).toAffine ==
    some (baseX, fieldSub 0 baseY)

/-- All parameter self-checks together. -/
def parametersSelfCheck : Bool :=
  baseIsOnCurve && orderAnnihilatesBase && baseRoundTrips &&
    orderPredecessorNegatesBase &&
    (curveA == fieldPrime - 3) &&
    (fieldPrime == 2 ^ 256 - 2 ^ 224 + 2 ^ 192 + 2 ^ 96 - 1)

/-! ## Parsing -/

/-- Parse a fixed-width lowercase hex field of exactly `2 * byteCount` digits
taken from `digits` starting at `offset`.  Returns `none` if the slice is short
or contains a non-lowercase-hex character. -/
def parseHexField (digits : List Char) (offset byteCount : Nat) :
    Option Nat :=
  let slice := (digits.drop offset).take (2 * byteCount)
  if slice.length == 2 * byteCount then
    parseLowerHexNat (String.ofList slice)
  else
    none

/-- Parse a SEC1 uncompressed public point `04 || X || Y`, 65 bytes written as
exactly 130 lowercase hex digits.

The point at infinity has no representation in this encoding: SEC1 encodes it
as the single byte `00`, whose hex form has length 2 and is rejected by the
length check.  `verifyDigestHex` additionally rejects infinity structurally.
Compressed encodings (`02`/`03` tags, 33 bytes) are rejected as well. -/
def parseUncompressedPoint (pointHex : String) : Option (Nat × Nat) :=
  let digits := pointHex.toList
  if digits.length == 130 && digits.take 2 == ['0', '4'] then
    match parseHexField digits 2 32, parseHexField digits 66 32 with
    | some x, some y => some (x, y)
    | _, _ => none
  else
    none

/-- Parse a fixed-width ECDSA signature `r || s`, 64 bytes written as exactly
128 lowercase hex digits.  DER is not accepted; see the module docstring. -/
def parseSignature (signatureHex : String) : Option (Nat × Nat) :=
  let digits := signatureHex.toList
  if digits.length == 128 then
    match parseHexField digits 0 32, parseHexField digits 64 32 with
    | some r, some s => some (r, s)
    | _, _ => none
  else
    none

/-! ## Verification -/

/-- Whether a public point is acceptable as a P-256 public key.

For a curve of cofactor 1, a point that is not the point at infinity and that
satisfies the curve equation with reduced coordinates necessarily has order
`groupOrder`, so the full-strength check `groupOrder * Q = infinity` from
SP 800-56A is implied and is not repeated here (it would double the cost of a
verification).  Both remaining conditions are checked explicitly:
`isOnCurve` rejects unreduced coordinates and off-curve points, and the
`isInfinity` test rejects the point at infinity.  Note that `(0, 0)` is not on
the curve because `curveB <> 0`. -/
def isValidPublicKey (x y : Nat) : Bool :=
  isOnCurve x y && !(Jacobian.ofAffine x y).isInfinity

/-- Whether `s` is in the canonical low-`s` form `2 * s <= groupOrder - 1`.
This is *not* required by `verifyDigestHex`; see the malleability note in the
module docstring. -/
def isLowS (s : Nat) : Bool := 2 * s ≤ groupOrder - 1

/-- ECDSA verification for P-256 against an already-computed SHA-256 digest.

Inputs are canonical lowercase hex of exact length: 130 digits for the SEC1
uncompressed public point, 64 for the digest, 128 for `r || s`.  Any other
length, any non-lowercase-hex character, any invalid public key, and any
out-of-range `r` or `s` are rejected before the curve arithmetic runs.

The message representative `e` is the digest read as a big-endian integer.
FIPS 186-4 takes the leftmost `min(bitlen(n), outlen)` bits of the digest; for
P-256 with SHA-256 both are 256, so that truncation is the identity and the
whole digest is used.  This is stated rather than left implicit because using
the wrong truncation is a classic source of interoperability failure with
other digest sizes.  `e` is then reduced modulo `groupOrder`, which is what
`u1 = e * w mod n` does in any case.

The verification equation is the standard one: `w = s^-1 mod n`,
`u1 = e * w mod n`, `u2 = r * w mod n`, `R = u1 * G + u2 * Q`; reject if `R` is
the point at infinity, and otherwise accept exactly when
`R.x mod n = r`. -/
def verifyDigestHex (publicKeyHex digestHex signatureHex : String) : Bool :=
  publicKeyHex.length == 130 &&
  digestHex.length == 64 &&
  signatureHex.length == 128 &&
  match parseUncompressedPoint publicKeyHex, parseLowerHexNat digestHex,
      parseSignature signatureHex with
  | some (qx, qy), some e, some (r, s) =>
      isValidPublicKey qx qy &&
      1 ≤ r && r ≤ groupOrder - 1 &&
      1 ≤ s && s ≤ groupOrder - 1 &&
      (let w := scalarInverse s
       let u1 := (e % groupOrder) * w % groupOrder
       let u2 := r * w % groupOrder
       let combined :=
         (Jacobian.scalarMul u1 basePoint).add
           (Jacobian.scalarMul u2 (Jacobian.ofAffine qx qy))
       match combined.toAffine with
       | none => false
       | some (rx, _) => rx % groupOrder == r)
  | _, _, _ => false

/-- ECDSA/SHA-256 verification over the UTF-8 bytes of a string payload,
matching the `RSA.verifyPkcs1v15Sha256` calling convention. -/
def verifySha256 (publicKeyHex payload signatureHex : String) : Bool :=
  verifyDigestHex publicKeyHex (SHA256.digestString payload) signatureHex

/-- ECDSA/SHA-256 verification over exact bytes, without any UTF-8
interpretation of the payload. -/
def verifySha256Bytes (publicKeyHex : String) (payload : ByteArray)
    (signatureHex : String) : Bool :=
  verifyDigestHex publicKeyHex (SHA256.digestByteArray payload) signatureHex

end SparkInterval.Certificate.P256
