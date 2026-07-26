/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedRootWire

set_option autoImplicit false

namespace SparkInterval.Tests.CertifiedRootWireTest

open SparkInterval.Certificate
open SparkInterval.Dirichlet.CertifiedRootWire

/- Exact binary64 `[1,1] + i[0,0]`. -/
def exactOne : RawComplexBox where
  re :=
    { lo := 0x3ff0000000000000
      hi := 0x3ff0000000000000 }
  im :=
    { lo := 0x0000000000000000
      hi := 0x0000000000000000 }

/- The exponent-zero root is exactly one, so its singleton production box
passes the full raw-word/rational-root checker. -/
#guard check 160 80 17 0 exactOne

/- Exact binary64 axis singletons exercise the critical-root branch rather
than relying on a rounded enclosure of pi. -/
def exactI : RawComplexBox where
  re := exactOne.im
  im := exactOne.re

def exactNegativeOne : RawComplexBox where
  re :=
    { lo := 0xbff0000000000000
      hi := 0xbff0000000000000 }
  im := exactOne.im

def exactNegativeI : RawComplexBox where
  re := exactOne.im
  im := exactNegativeOne.re

#guard check 160 80 4 1 exactI
#guard check 160 80 4 2 exactNegativeOne
#guard check 160 80 4 3 exactNegativeI

/- A one-ulp-lower singleton cannot enclose the exact value one. -/
def belowOne : RawComplexBox where
  re :=
    { lo := 0x3fefffffffffffff
      hi := 0x3fefffffffffffff }
  im := exactOne.im

#guard !(check 160 80 17 0 belowOne)

/- Reversed endpoints, NaN, and order zero all fail closed. -/
def reversedOne : RawComplexBox where
  re :=
    { lo := 0x3ff0000000000000
      hi := 0x3fefffffffffffff }
  im := exactOne.im

def nanReal : RawComplexBox where
  re :=
    { lo := 0x7ff8000000000000
      hi := 0x7ff8000000000000 }
  im := exactOne.im

#guard !(check 160 80 17 0 reversedOne)
#guard !(check 160 80 17 0 nanReal)
#guard !(check 160 80 0 0 exactOne)

example
    {workPrecision outputPrecision order exponent : Nat}
    {raw : RawComplexBox}
    (hcheck :
      check workPrecision outputPrecision order exponent raw = true) :
    ∃ (outer : SparkInterval.Certified.ComplexRect)
        (hvalid : outer.IsValid),
      raw.decodeFinite = some outer ∧
      (toComplexInterval outer hvalid).Contains
        (SparkInterval.Dirichlet.FactoredSmallQDFT.unitRoot
          order exponent) :=
  checked_box_contains hcheck

#print axioms RawComplexBox.decodeFinite_isValid
#print axioms check_eq_true
#print axioms check_sound
#print axioms checked_box_contains

end SparkInterval.Tests.CertifiedRootWireTest
