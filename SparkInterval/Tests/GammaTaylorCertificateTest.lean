/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Zeta.GammaTaylorCertificate

set_option autoImplicit false

namespace SparkInterval.Tests.GammaTaylorCertificateTest

open SparkInterval.Certified
open SparkInterval.Zeta.GammaTaylorCertificate

example (u : ℝ) : gaussianExponent u sourceGaussianH ≤ 0 :=
  sourceGaussianExponent_nonpos u

example {exactLog approximateLog : ℂ} {epsilon u : ℝ}
    (hepsilon : 0 ≤ epsilon)
    (hlog : ‖exactLog - approximateLog‖ ≤ epsilon) :
    ‖Complex.exp (exactLog + (gaussianExponent u sourceGaussianH : ℂ)) -
        Complex.exp
          (approximateLog + (gaussianExponent u sourceGaussianH : ℂ))‖ ≤
      Real.exp approximateLog.re * (epsilon * Real.exp epsilon) :=
  norm_sourceValue_sub_approximation_le hepsilon hlog

example {logValue : ℂ} {approximate : Fin 1 → ℂ}
    {u epsilon : ℝ} {outputError : ℚ} {Z : ComplexRect}
    (hepsilon : 0 ≤ epsilon)
    (hlog : ‖logValue - taylorPolynomial approximate u‖ ≤ epsilon)
    (happroximation : Z.ContainsComplex
      (Complex.exp
        (taylorPolynomial approximate u +
          (gaussianExponent u sourceGaussianH : ℂ))))
    (houtputError :
      Real.exp (taylorPolynomial approximate u).re *
          (epsilon * Real.exp epsilon) ≤ (outputError : ℝ)) :
    (ComplexRect.widenRect outputError Z).ContainsComplex
      (Complex.exp
        (logValue + (gaussianExponent u sourceGaussianH : ℂ))) :=
  widenedRect_contains_sourceValue hepsilon hlog happroximation houtputError

#print axioms norm_sourceValue_sub_taylorValue_le
#print axioms widenedRect_contains_sourceValue

end SparkInterval.Tests.GammaTaylorCertificateTest
