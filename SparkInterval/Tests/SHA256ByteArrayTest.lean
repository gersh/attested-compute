/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certificate.SHA256

/-! Tiny known-answer tests for exact arbitrary-byte SHA-256. -/

set_option autoImplicit false

namespace SparkInterval.Tests.SHA256ByteArray

open SparkInterval.Certificate

private def nonUTF8 : ByteArray :=
  ([0x00, 0x80, 0xff, 0xfe, 0x41] : List UInt8).toByteArray

private def allByteValues : ByteArray :=
  ((List.range 256).map UInt8.ofNat).toByteArray

#guard
  SHA256.digestByteArray ByteArray.empty =
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

#guard
  SHA256.digestByteArray "abc".toUTF8 =
    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

/- This byte sequence is intentionally not valid UTF-8. -/
#guard
  SHA256.digestByteArray nonUTF8 =
    "9c1331e828ee11c2078baec74b31e32713cda32649a2de28a1b8324f05900f55"

/- Fixed external known answer for "TGDOMAIN\0" followed by bytes 17...240. -/
#guard
  SHA256.digestPrefixSlice "TGDOMAIN\u0000".toUTF8 allByteValues 17 241 =
    "b5508c978a499931480bebe82e07b941637a718bcb59f89ddb832d53322358b4"

/- The slice clamps to the packed array, matching `ByteArray.extract`. -/
#guard
  SHA256.digestPrefixSlice "z".toUTF8 allByteValues 250 300 =
    "1a18f5ee09345501b33843768f50ec7738f769c249cf260df2130c349ba1bc5e"

/- Reversed and wholly out-of-range half-open slices are empty. -/
#guard
  SHA256.digestPrefixSlice "reverse".toUTF8 allByteValues 241 17 =
    "b2d7f24e833051d5fc296d4a747281e9d155ecfb636b983cfd70b51ed9b45a32"

#guard
  SHA256.digestPrefixSlice "past".toUTF8 allByteValues 300 400 =
    "84ccdf8a849ffbc98d3a8a4bfb0999eda9254015f75a1c6cc7f68338d61c00b0"

/- SHA-256's eight-byte bit length wraps modulo `2^64`.  The middle and
last cases are outside the successful Sqrt218 C wrapper's explicit
`byteCount * 8 < 2^64` guard, but pin the total definition's behavior. -/
#guard
  SHA256.encodedLength (2 ^ 61 - 1) =
    [0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xf8]

#guard
  SHA256.encodedLength (2 ^ 61) =
    [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

#guard
  SHA256.encodedLength (2 ^ 61 + 1) =
    [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x08]

example (bytes : ByteArray) :
    SHA256.digestByteArray bytes = SHA256.digestByteArrayReference bytes :=
  SHA256.digestByteArray_eq_reference bytes

example (domainPrefix bytes : ByteArray) (start stop : Nat) :
    SHA256.digestPrefixSlice domainPrefix bytes start stop =
      SHA256.digestByteArray
        (domainPrefix ++ bytes.extract start stop) :=
  SHA256.digestPrefixSlice_eq_digestByteArray_append_extract
    domainPrefix bytes start stop

example (text : String) :
    SHA256.digestString text = SHA256.digestByteArray text.toUTF8 :=
  SHA256.digestString_eq_digestByteArray_toUTF8 text

#print axioms SHA256.hashSource_eq_hashBytes_of_realizes
#print axioms SHA256.digestByteArray_eq_reference
#print axioms SHA256.digestPrefixSlice_eq_digestByteArray_append_extract

end SparkInterval.Tests.SHA256ByteArray
