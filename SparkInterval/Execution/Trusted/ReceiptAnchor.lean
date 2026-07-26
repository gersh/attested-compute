/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.Trusted.RunCertificate

/-!
# Kernel-visible trusted-compute receipt anchors

`#print axioms` reports the one trusted-execution axiom, but not the concrete
receipt hash at which it was instantiated.  Generated receipt modules use the
wrapper below so the exact hash remains visible in their proof terms and can
be inventoried by `SparkInterval.Audit.TrustedComputeCertificates`.

The equality premise prevents the displayed hash from drifting away from the
hash carried by the certificate.  This is an ordinary theorem derived from
the existing single axiom; it introduces no additional trust.
-/

set_option autoImplicit false

namespace SparkInterval.Execution.Trusted

/-- Kernel-visible instantiation point for one source-pinned receipt. -/
theorem acceptedRunCertificateForReceipt
    (receiptHash : Digest)
    (certificate : RunCertificate)
    (_receiptBinding :
      certificate.attestation = .trustedCompute receiptHash)
    (accepted : checkTrustedCompute certificate.statement
      certificate.attestation = true) :
    certificate.ProducedOutcome :=
  accepted_run_certificate_sound accepted

end SparkInterval.Execution.Trusted
