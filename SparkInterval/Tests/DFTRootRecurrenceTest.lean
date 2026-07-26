/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.DFTRootRecurrence

set_option autoImplicit false

namespace SparkInterval.Tests.DFTRootRecurrenceTest

open SparkInterval
open SparkInterval.Dirichlet

example
    (rounding : DirectedRound)
    {order start count : Nat}
    {unitStep initial : ComplexInterval}
    (horder : 0 < order)
    (hstep :
      unitStep.Contains (FactoredSmallQDFT.unitRoot order 1))
    (hinitial :
      initial.Contains (FactoredSmallQDFT.unitRoot order start)) :
    (DFTRootRecurrence.runDirected rounding unitStep count initial).Contains
      (FactoredSmallQDFT.unitRoot order (start + count)) :=
  DFTRootRecurrence.runDirected_from_contains
    rounding horder hstep hinitial count

#print axioms DFTRootRecurrence.unitRoot_succ
#print axioms DFTRootRecurrence.directedNext_contains
#print axioms DFTRootRecurrence.runDirected_from_contains
#print axioms DFTRootRecurrence.runDirected_contains

end SparkInterval.Tests.DFTRootRecurrenceTest
