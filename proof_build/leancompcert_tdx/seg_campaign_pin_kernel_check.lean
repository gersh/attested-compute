/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT

The preimage binding for the chained leancompcert campaign pin, in the kernel.

Run it OUTSIDE `lake build`, because `lakefile.toml` caps every module at
`-M8192` and this reduction needs about 10 GB:

    lake env lean proof_build/leancompcert_tdx/seg_campaign_pin_kernel_check.lean

Measured on the 20-core aarch64 development host, 2026-07-30:
`16.4 s` user, `10.0 GB` peak resident, exit 0.
-/
import SparkInterval.Execution.LeanCompCertSegCampaign

open SparkInterval.Execution
open SparkInterval.Certificate

/-- `algorithmHash` really is the SHA-256 of the definition that names the
campaign manifest by digest.  Nothing here is `native_decide`. -/
theorem segCampaignAlgorithmHash_eq :
    SHA256.digestString segCampaignCanonicalDefinition
      = segCampaignAlgorithmHash := by
  decide +kernel

#print axioms segCampaignAlgorithmHash_eq
