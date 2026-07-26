/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Dirichlet.CertifiedBluesteinRootBridge

set_option autoImplicit false

namespace SparkInterval.Tests.CertifiedBluesteinRootBridgeTest

open SparkInterval
open SparkInterval.Dirichlet
open SparkInterval.Dirichlet.FactoredSmallQDFT
open SparkInterval.Dirichlet.DirectedIntervalFFT
open SparkInterval.Dirichlet.DirectedIntervalBluestein
open SparkInterval.Dirichlet.CertifiedBluesteinRootBridge

example
    {workPrecision outputPrecision order exponent : Nat}
    {box : ComplexInterval}
    (hcertificate :
      FastRootCertificate workPrecision outputPrecision
        order exponent box) :
    box.Contains (unitRoot order exponent) :=
  fastRootCertificate_contains hcertificate

example
    {workPrecision outputPrecision logLength : Nat}
    {positiveBoxes : Nat → Nat → ComplexInterval}
    (hcertificates :
      PositiveTwiddleCertificates workPrecision outputPrecision
        logLength positiveBoxes) :
    TwiddlesContain (logLength := logLength)
      (fun stage offset => conjugateBox (positiveBoxes stage offset))
      BluesteinCUDADataflow.negativeTwiddle :=
  negativeTwiddlesContain_of_positive_certificates hcertificates

example
    {workPrecision outputPrecision order logLength : Nat}
    (horder : 0 < order)
    {positiveBoxes : Fin order → ComplexInterval}
    (hcertificates :
      PositiveChirpCertificates workPrecision outputPrecision
        order positiveBoxes) :
    KernelContains (order := order)
      (kernelBoxesFromPositiveChirps
        (logLength := logLength) positiveBoxes) :=
  kernelContains_of_positive_chirp_certificates horder hcertificates

/- The fast evaluator succeeds for a positive FFT root and for the
doubled-order root used by a nontrivial half-angle chirp. -/
#guard
  (CertifiedRootTable.rootRectFast? 160 80 16 7).isSome

#guard
  (CertifiedRootTable.rootRectFast? 160 80 (2 * 5) (4 ^ 2)).isSome

#print axioms contains_of_enclosesRect
#print axioms fastRootCertificate_contains
#print axioms positiveTwiddlesContain_of_certificates
#print axioms negativeTwiddlesContain_of_positive_certificates
#print axioms halfRoot_nat_eq_unitRoot
#print axioms inputChirpsContain_of_certificates
#print axioms kernelContains_of_positive_chirp_certificates
#print axioms certifiedRoots_directedBluestein_contains_positiveDFT

end SparkInterval.Tests.CertifiedBluesteinRootBridgeTest
