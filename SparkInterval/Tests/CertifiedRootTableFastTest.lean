/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedRootTable

set_option autoImplicit false

namespace SparkInterval.Tests.CertifiedRootTableFast

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet

example {order exponent : Nat} (horder : 0 < order) :
    FactoredSmallQDFT.unitRoot order exponent =
      FactoredSmallQDFT.unitRoot order (exponent % order) :=
  CertifiedRootTable.unitRoot_mod horder exponent

example
    {terms : Nat} (hterms : 0 < terms)
    {depth workPrecision outputPrecision order exponent : Nat}
    {R : ComplexRect}
    (hcheck :
      CertifiedRootTable.rootRectConfigured?
        terms depth workPrecision outputPrecision order exponent = some R) :
    R.ContainsComplex (FactoredSmallQDFT.unitRoot order exponent) :=
  CertifiedRootTable.rootRectConfigured?_containsComplex hterms hcheck

example
    {workPrecision outputPrecision order exponent : Nat}
    {R : ComplexRect}
    (hcheck :
      CertifiedRootTable.rootRectFast?
        workPrecision outputPrecision order exponent = some R) :
    R.ContainsComplex (FactoredSmallQDFT.unitRoot order exponent) :=
  CertifiedRootTable.rootRectFast?_containsComplex hcheck

#guard CertifiedRootTable.fastTaylorTerms = 13
#guard CertifiedRootTable.fastTaylorDepth = 9

/- The order-zero branch is explicitly fail-closed. -/
#guard CertifiedRootTable.rootRectFast? 160 52 0 123456789 = none

/- A large Bluestein-style numerator is reduced before it can magnify the
finite-width rational enclosure of pi. -/
def largeExponent : Nat := 1000000000000000007 ^ 2

def sameRectOption (left right : Option ComplexRect) : Bool :=
  match left, right with
  | none, none => true
  | some L, some R => decide (L.re = R.re ∧ L.im = R.im)
  | _, _ => false

/- The four exact axis roots bypass the finite-width enclosure of pi.  This
lets a producer certify the exact binary64 singletons `±1` and `±i`. -/
#guard sameRectOption
  (CertifiedRootTable.rootRectFast? 160 80 4 0)
  (some (ComplexRect.point 1 0))
#guard sameRectOption
  (CertifiedRootTable.rootRectFast? 160 80 4 1)
  (some (ComplexRect.point 0 1))
#guard sameRectOption
  (CertifiedRootTable.rootRectFast? 160 80 4 2)
  (some (ComplexRect.point (-1) 0))
#guard sameRectOption
  (CertifiedRootTable.rootRectFast? 160 80 4 3)
  (some (ComplexRect.point 0 (-1)))
#guard sameRectOption
  (CertifiedRootTable.rootRectFast? 160 80 4 5)
  (some (ComplexRect.point 0 1))

#guard
  sameRectOption
    (CertifiedRootTable.rootRectFast? 160 52 100003 largeExponent)
    (CertifiedRootTable.rootRectFast? 160 52 100003
      (largeExponent % 100003))

/- The resulting large-exponent sample remains at binary64-scale width. -/
#guard
  match CertifiedRootTable.rootRectFast? 160 52 100003 largeExponent with
  | none => false
  | some R =>
      R.re.hi - R.re.lo ≤ (1 : ℚ) / 2 ^ 51 &&
      R.im.hi - R.im.lo ≤ (1 : ℚ) / 2 ^ 51

#print axioms CertifiedRootTable.unitRoot_mod
#print axioms CertifiedRootTable.exactQuarterRoot?_containsComplex
#print axioms CertifiedRootTable.rootRectConfigured?_containsComplex
#print axioms CertifiedRootTable.rootRectFast?_containsComplex

end SparkInterval.Tests.CertifiedRootTableFast
