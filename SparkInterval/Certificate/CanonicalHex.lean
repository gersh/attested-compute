/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.RSA

/-!
# Compositional certificates for canonical hexadecimal strings

Large signed receipts contain many SHA-256 digests and one 768-character
RSA-3072 signature.  Reducing one monolithic character scan in a generated
theorem creates an impractically large proof term.  This module gives the
registry generator a kernel-checked alternative: certify small literal chunks
and compose their proofs with an abstract append theorem.
-/

set_option autoImplicit false

namespace SparkInterval.Certificate

/-- A string has exactly the requested number of characters and consists only
of lowercase hexadecimal digits. -/
def isCanonicalLowerHexOfLength (expected : Nat) (value : String) : Bool :=
  value.length == expected &&
    value.toList.all (fun character => (RSA.lowerHexNibble character).isSome)

/-- Canonical lowercase-hex syntax carried with its kernel proof. -/
structure CanonicalLowerHex (length : Nat) where
  value : String
  canonical : isCanonicalLowerHexOfLength length value = true

namespace CanonicalLowerHex

/-- Concatenating certified strings adds their certified lengths. -/
theorem canonical_append {m n : Nat} {a b : String}
    (ha : isCanonicalLowerHexOfLength m a = true)
    (hb : isCanonicalLowerHexOfLength n b = true) :
    isCanonicalLowerHexOfLength (m + n) (a ++ b) = true := by
  simp only [isCanonicalLowerHexOfLength, Bool.and_eq_true, beq_iff_eq]
    at ha hb ⊢
  constructor
  · simp [String.length_append, ha.1, hb.1]
  · simp [String.toList_append, List.all_append, ha.2, hb.2]

/-- Compose two syntax certificates without rescanning the concatenation. -/
def append {m n : Nat} (left : CanonicalLowerHex m)
    (right : CanonicalLowerHex n) : CanonicalLowerHex (m + n) := {
  value := left.value ++ right.value
  canonical := canonical_append left.canonical right.canonical
}

end CanonicalLowerHex

end SparkInterval.Certificate
