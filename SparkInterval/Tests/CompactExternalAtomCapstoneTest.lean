/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone

/-!
Axiom audit for the compact all-atom checker capstone.

The output may contain Lean/Mathlib's foundational `propext`,
`Classical.choice`, and `Quot.sound`; it must not contain a production
receipt axiom, a generated-certificate theorem, or `native_decide`.
-/

#print axioms SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone.checkerDerivedClaim_of_canonicalAcceptances
#print axioms SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone.exactTableDownstreamClaim_of_checkerDerivedClaim
#print axioms SparkInterval.TernaryGoldbach.CompactExternalAtomCapstone.exactTableDownstreamClaim_of_canonicalAcceptances
