# Attestation adapters

The project goal is to turn evidence from measured secure CPU/GPU execution
into durable certificates for finite computations. Those certificates can be
stored by digest and referenced through SparkInterval's explicit Lean
execution axiom. This directory is the beginning of that evidence boundary,
not a completed production implementation.

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
replay checks, negative acceptance tests, and a reviewed importer into Lean's
private positive-evidence capability. The content-addressed shared certificate
library described in the [project vision](../docs/VISION.md) is also future
work.

Start with the [verifier guide](../docs/VERIFYING.md), then consult the
[trust model](../docs/TRUST_MODEL.md), [bundle format](../docs/FORMAT.md), and
[H100 guide](../docs/H100.md). Contributors can use the
[secure-execution work list](../docs/CONTRIBUTING.md#secure-execution-and-certificates)
to find the next missing pieces.
