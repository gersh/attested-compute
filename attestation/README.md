# Attestation boundary

There are three deliberately separate paths here.

- `tools/local_operator_signature.py` creates and verifies detached Ed25519
  operator signatures for exact DGX `local_unattested` bundles. It requires an
  out-of-band pinned public key and proves only that the operator key signed
  the record. It never reports hardware evidence and is not an NVIDIA
  confidential-computing path.

- `mock_attestation.py` produces `evidence_class: "mock_attested"`, says that no
  algorithm was executed, carries no signature, and sets
  `production_acceptable: false`. It is only a parser/proof-plumbing fixture.
- `nvidia_cc_provider_stub.py` is the production placeholder. It always exits
  with code 78 (`EX_CONFIG`) and emits a checklist rather than evidence. It has
  no override or success mode.

A future production verifier must reject mock evidence before inspecting any
algorithm or result fields. Replacing the fail-closed stub requires an actual
NVIDIA confidential-computing evidence collector and verifier, measurement and
result binding, replay protection, and H100 acceptance tests.
