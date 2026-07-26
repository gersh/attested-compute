/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedRootTable

set_option autoImplicit false

namespace SparkInterval.Tests.CertifiedRootTable

open SparkInterval.Certificate
open SparkInterval.Certified
open SparkInterval.Dirichlet

example (order exponent : Nat) :
    (CertifiedRootTable.phaseInterval order exponent).ContainsReal
      ((2 * Real.pi * (exponent : ℝ)) / (order : ℝ)) :=
  CertifiedRootTable.phaseInterval_containsReal order exponent

example
    {depth workPrecision outputPrecision order exponent : Nat}
    {R : ComplexRect}
    (hcheck :
      CertifiedRootTable.rootRect?
        depth workPrecision outputPrecision order exponent = some R) :
    R.ContainsComplex (FactoredSmallQDFT.unitRoot order exponent) :=
  CertifiedRootTable.rootRect?_containsComplex hcheck

#eval
  (CertifiedRootTable.rootRect? 40 160 52 17 5).map
    (fun R => (R.re.lo, R.re.hi, R.im.lo, R.im.hi))

#print axioms CertifiedRootTable.phaseInterval_containsReal
#print axioms CertifiedRootTable.rootRect?_containsComplex

end SparkInterval.Tests.CertifiedRootTable
