/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Certified.ComplexDiskContainment

/-!
# Exact KATs for complex-disk containment

The positive case is tight:

```
inner = disk(1 + 2i, 1/4)
outer = disk(3/2 + 2i, 3/4).
```

The centre distance is `1/2`, exactly the radius difference.  Independent
mutations exercise the radius-order and squared-distance rejection paths.
-/

set_option autoImplicit false

namespace SparkInterval.Tests.ComplexDiskContainment

open SparkInterval.Certified
open SparkInterval.Certified.ComplexDisk

def tight : ContainmentCertificate := {
  inner := ⟨1, 2, 1 / 4⟩
  outer := ⟨3 / 2, 2, 3 / 4⟩
}

theorem tight_check : tight.check = true := by
  norm_num [ContainmentCertificate.check,
    ContainmentCertificate.WellFormed, tight, centerDistanceSq]

def radiusOrderMutation : ContainmentCertificate := {
  tight with outer := { tight.outer with radius := 1 / 8 }
}

theorem radiusOrderMutation_rejected :
    radiusOrderMutation.check = false := by
  norm_num [ContainmentCertificate.check,
    ContainmentCertificate.WellFormed, radiusOrderMutation, tight,
    centerDistanceSq]

def centerDistanceMutation : ContainmentCertificate := {
  tight with outer := { tight.outer with re := 2 }
}

theorem centerDistanceMutation_rejected :
    centerDistanceMutation.check = false := by
  norm_num [ContainmentCertificate.check,
    ContainmentCertificate.WellFormed, centerDistanceMutation, tight,
    centerDistanceSq]

def negativeInnerRadiusMutation : ContainmentCertificate := {
  tight with inner := { tight.inner with radius := -1 / 4 }
}

theorem negativeInnerRadiusMutation_rejected :
    negativeInnerRadiusMutation.check = false := by
  norm_num [ContainmentCertificate.check,
    ContainmentCertificate.WellFormed, negativeInnerRadiusMutation, tight,
    centerDistanceSq]

/-- Live semantic consumer of the checker soundness theorem. -/
theorem tight_semantic_consumer {value : ℂ}
    (hvalue : tight.inner.ContainsComplex value) :
    tight.outer.ContainsComplex value :=
  ContainmentCertificate.outer_contains_of_inner_contains tight_check hvalue

#print axioms ContainmentCertificate.check_sound
#print axioms ContainmentCertificate.outer_contains_of_inner_contains
#print axioms tight_semantic_consumer

end SparkInterval.Tests.ComplexDiskContainment
