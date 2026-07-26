/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.A7BoundarySuccessEvidence

namespace SparkInterval.Tests.A7BoundaryCertificateTest

open SparkInterval.TernaryGoldbach
open A7BoundaryCertificate

private def leaf (edgeId : ℕ) : DyadicLeaf where
  edgeId := edgeId
  depth := 0
  index := 0
  normSqUpperMantissa := 1
  normSqUpperExponent := 0
  zetaAbsLowerMantissa := 1
  zetaAbsLowerExponent := 0

/-- Tiny topology/arithmetic KAT only.  It is not analytic realization
evidence and is not a production certificate. -/
private def tinyCertificate : Certificate where
  maxDepth := 0
  leaves := [leaf 0, leaf 1, leaf 2, leaf 3]

example : tinyCertificate.check = true := by decide

private def halfLeftLeaf : DyadicLeaf where
  edgeId := 0
  depth := 1
  index := 0
  normSqUpperMantissa := 1
  normSqUpperExponent := 0
  zetaAbsLowerMantissa := 1
  zetaAbsLowerExponent := 0

private def gappedCertificate : Certificate where
  maxDepth := 1
  leaves := [halfLeftLeaf, leaf 1, leaf 2, leaf 3]

/-- A half-edge is rejected rather than being mistaken for a full cover. -/
example : gappedCertificate.check = false := by decide

private def tooLargeNormLeaf : DyadicLeaf where
  edgeId := 0
  depth := 0
  index := 0
  normSqUpperMantissa := 2
  normSqUpperExponent := 0
  zetaAbsLowerMantissa := 1
  zetaAbsLowerExponent := 0

private def tooLargeNormCertificate : Certificate where
  maxDepth := 0
  leaves := [tooLargeNormLeaf, leaf 1, leaf 2, leaf 3]

/-- The exact guard rejects `2`, since `2 > (349/250)^2`. -/
example : tooLargeNormCertificate.check = false := by decide

example (realization : AnalyticRealization tinyCertificate) :
    A7BoundarySourceSemantics.SourceClaim :=
  sourceClaim_of_checked_certificate (by decide) realization

example (evidence : A7BoundarySuccessEvidence.SuccessEvidence) :
    A7BoundarySourceSemantics.SourceClaim :=
  A7BoundarySuccessEvidence.sourceClaim_of_successEvidence evidence

#print axioms DyadicLeaf.check_sound
#print axioms Certificate.accepted_of_check_eq_true
#print axioms Certificate.edgeCover_covers
#print axioms Certificate.covers_frontier
#print axioms AnalyticRealization.zeta_ne_zero
#print axioms sourceClaim_of_checked_certificate
#print axioms A7BoundarySuccessEvidence.sourceClaim_of_successEvidence

end SparkInterval.Tests.A7BoundaryCertificateTest
