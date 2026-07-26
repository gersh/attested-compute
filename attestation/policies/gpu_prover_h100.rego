# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

package policy

import future.keywords.every

default nv_match := false

# The nonce is supplied and checked separately by nvattest.  This baseline
# policy additionally requires exactly one result and refuses non-GPU
# evidence, disabled secure boot, or an enabled debug state.  It is not a
# production measurement allowlist: pin the accepted H100 model, RIM,
# driver/VBIOS/firmware measurements, roots, and revocation policy in the
# separately reviewed production policy.
nv_match {
    count(input) == 1
    every result in input {
        result["x-nvidia-device-type"] == "gpu"
        result.secboot == true
        result.dbgstat == "disabled"
        result["x-nvidia-gpu-attestation-report-nonce-match"] == true
    }
}
