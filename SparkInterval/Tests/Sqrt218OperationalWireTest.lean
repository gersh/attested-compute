/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.Sqrt218.Operational.Wire

/-!
# Small known-answer tests for the Sqrt218 V1 wire decoder

These elaboration-time guards use only the checked bound-64 presentation
fixture.  They do not load or replay production rows.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.Sqrt218OperationalWire

open SparkInterval.TernaryGoldbach.Sqrt218Operational

def sampleWithPresentationNewline : String :=
  include_str ".." / ".." / "examples" / "sqrt218" /
    "sample-certificate.bound64.json.txt"

def sampleCanonicalText : String :=
  (sampleWithPresentationNewline.dropEnd 1).toString

def sampleCanonicalBytes : ByteArray :=
  sampleCanonicalText.toUTF8

def acceptsBound64Sample : Bool :=
  match decodeCanonicalArchiveBytes sampleCanonicalBytes with
  | .error _ => false
  | .ok archive =>
      archive.bound == 64 &&
        archive.primes.length == 18 &&
        archive.events.length == 27 &&
        canonicalArchiveBytes archive == sampleCanonicalBytes

def rejects (raw : ByteArray) : Bool :=
  match decodeCanonicalArchiveBytes raw with
  | .error _ => true
  | .ok _ => false

#guard acceptsBound64Sample

/- The presentation fixture's newline is not part of canonical V1 bytes. -/
#guard rejects sampleWithPresentationNewline.toUTF8

/- Exact EOF means even a single otherwise harmless suffix is rejected. -/
#guard rejects (sampleCanonicalBytes ++ "\n".toUTF8)

/- A duplicate top-level key cannot be normalized away by the JSON object
representation. -/
def duplicateBoundText : String :=
  "{\"bound\":64," ++ (sampleCanonicalText.drop 1).toString

#guard rejects duplicateBoundText.toUTF8

/- Protocol discrimination occurs in the decoder, before arithmetic replay. -/
def wrongKindText : String :=
  sampleCanonicalText.replace
    "sparkinterval.sqrt218-finite-certificate.v1"
    "sparkinterval.sqrt218-finite-certificate.v2"

#guard rejects wrongKindText.toUTF8

#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218Operational.decodeCanonicalArchiveBytes_success
#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218Operational.decodeCanonicalArchiveBytes_kind
#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218Operational.decodeCanonicalArchiveBytes_exact
#print axioms
  SparkInterval.TernaryGoldbach.Sqrt218Operational.decodeCanonicalArchiveBytes_noAlternateEncoding

end SparkInterval.Tests.Sqrt218OperationalWire
