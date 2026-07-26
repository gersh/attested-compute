/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256

/-!
# Small RSA signature checker for trusted-compute receipts

This module implements the narrow cryptographic operation needed at the Lean
boundary: strict RSASSA-PKCS1-v1_5 verification with SHA-256, a 3072-bit
modulus, and public exponent 65537.  It is deliberately not a general-purpose
cryptography library.

The implementation is pure Lean, but it is diagnostic rather than the
authoritative receipt-admission path.  Reducing a full RSA-3072 verification
inside each concrete theorem is impractical.  Production import therefore
checks the signature externally against the reviewed public-key manifest and
emits a closed, source-pinned registry entry.  Lean kernel-checks registry
membership and structural binding without an FFI or `native_decide`; the sole
execution axiom remains explicit.  This file supplies only an executable check
of the exact RSA equation for audits and small experiments.
-/

set_option autoImplicit false

namespace SparkInterval.Certificate.RSA

/-- Convert one lowercase hexadecimal digit to its value.  Uppercase is
rejected so the signed wire representation has a unique spelling. -/
def lowerHexNibble (character : Char) : Option Nat :=
  let value := character.toNat
  if '0'.toNat ≤ value && value ≤ '9'.toNat then
    some (value - '0'.toNat)
  else if 'a'.toNat ≤ value && value ≤ 'f'.toNat then
    some (value - 'a'.toNat + 10)
  else
    none

/-- Parse a canonical lowercase hexadecimal natural number. -/
def parseLowerHexNat (text : String) : Option Nat :=
  text.toList.foldlM (fun accumulator character => do
    let nibble ← lowerHexNibble character
    pure (16 * accumulator + nibble)) 0

/-- Concatenate exactly `count` copies of `piece`. -/
def repeatString (piece : String) (count : Nat) : String :=
  String.join (List.replicate count piece)

/-- Compute `base^65537 mod modulus` using the fixed public exponent
`65537 = 2^16 + 1`.  Specializing the exponent keeps concrete checking small
and avoids a 65,537-step unary recursion in the kernel. -/
def pow65537Mod (base modulus : Nat) : Nat :=
  if modulus = 0 then
    0
  else
    let reduced := base % modulus
    let squared16 := (List.range 16).foldl
      (fun value _ => (value * value) % modulus) reduced
    (squared16 * reduced) % modulus

/-- DER `DigestInfo` prefix for SHA-256 in EMSA-PKCS1-v1_5. -/
def sha256DigestInfoPrefix : String :=
  "3031300d060960864801650304020105000420"

/-- Canonical 384-byte EMSA-PKCS1-v1_5 encoding for a SHA-256 digest.

The padding contains 330 `0xff` octets because
`384 - 3 - (19 + 32) = 330`.
-/
def emsaPkcs1v15Sha256Hex (digest : String) : String :=
  "0001" ++ repeatString "ff" 330 ++ "00" ++
    sha256DigestInfoPrefix ++ digest

/-- Strict verification for a 3072-bit RSA/SHA-256 signature.

Both the signature and modulus must use exactly 384 bytes of lowercase hex.
The strict length and range checks rule out alternate encodings before the RSA
equation is evaluated.
-/
def verifyPkcs1v15Sha256
    (modulusHex payload signatureHex : String) : Bool :=
  modulusHex.length == 768 &&
  signatureHex.length == 768 &&
  match parseLowerHexNat modulusHex, parseLowerHexNat signatureHex,
      parseLowerHexNat (emsaPkcs1v15Sha256Hex (SHA256.digestString payload)) with
  | some modulus, some signature, some expected =>
      modulus > 0 && signature < modulus &&
        pow65537Mod signature modulus == expected
  | _, _, _ => false

end SparkInterval.Certificate.RSA
