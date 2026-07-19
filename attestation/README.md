# Attestation adapters

This directory contains fail-closed and negative-test adapters for the H100
evidence boundary:

- `mock_attestation.py` emits visibly non-production `mock_attested` data so
  parsers and rejection paths can be tested.
- `nvidia_cc_provider_stub.py` is a fail-closed production placeholder. It
  emits no positive evidence and exits with status 78.

DGX operator signatures are implemented by
[`tools/local_operator_signature.py`](../tools/local_operator_signature.py),
not by these adapters. They authenticate an operator's endorsement of a local
record and never become hardware evidence.

No included component collects or cryptographically verifies positive NVIDIA
confidential-computing evidence. Replacing the stub requires a supported H100
CC system, pinned trust roots, measurement/result binding, freshness and
replay checks, and negative acceptance tests.

Start with the [verifier guide](../docs/VERIFYING.md), then consult the
[trust model](../docs/TRUST_MODEL.md), [bundle format](../docs/FORMAT.md), and
[H100 guide](../docs/H100.md).
