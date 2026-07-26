# Scheduled large-q Dirichlet component graph

Copyright (c) 2026 Gershon Bialer. All rights reserved.

The executable graph

```text
scheduled residue producer
  -> TGDQORD1 multi-q CUDA transform
  -> scheduled completed-L/sign consumer
```

is implemented by
`tg_verifier.dirichlet_scheduled_largeq_pipeline`. It is the operational
integration of the primitive-V2 q-order optimization documented in
`DIRICHLET_ALL_CHARACTER_Q_SCHEDULER.md`; it is not a new analytic argument.

Every component receives the same immutable `TGDQORD1` file. The producer
will not emit a q or t row outside the manifest. The transform independently
parses the binary manifest and enforces its exact coverage. The consumer
allows nonmonotone q only in this explicit mode, verifies the same exact
coverage, and resolves each actual q through the independently authenticated
`TGDRNRO1` root catalog. All three receipts and the supervisor receipt contain
the complete manifest SHA-256 plus both internal roster digests.

Production and test entry points are:

```text
tools/tg_dirichlet_scheduled_largeq_pipeline.py
tools/tg_dirichlet_residue_composition.py --schedule-manifest ...
tools/tg_dirichlet_stream_zero_consumer.py --schedule-manifest ...
```

The ordinary fixed-q producer, transform, and consumer interfaces remain
available and retain their earlier monotonicity rules.

The bounded conformance run uses actual q labels and actual component
algorithms. Test-only wrappers bypass the Azure dispatch guard; they do not
forge attestation or alter arithmetic. The production CLIs remain
cloud-gated. Bounded relay receipts have an exact schema, bind the configured
capture ceiling as well as the manifest and exact stream digests, use at most
one MiB of relay memory, and publish captures only after clean EOF. The
supervisor records that ceiling, rejects symlink output directories, binds
the resolved bytes and invoked spelling of every interpreter/tool/executable,
checks the consumer event digest and size directly, and records the positive
finite process timeout used for the run. Every component is launched in an
isolated process group so fail-fast cancellation reaches descendants.
Bounded runs default to a 15-minute process-graph timeout; the deliberately
unintegrated full-source mode must receive an explicit operator timeout. The
retained-stream ceiling is itself capped at 256 MiB in this bounded KAT
implementation.

Bounded replay enforces the retained capture ceiling before reading a capture,
spools fresh producer and consumer stdout to temporary files and applies
post-run size checks, applies a positive finite timeout to every fresh
producer, MPFR, and Arb subprocess, and records the replay executable
artifacts. These provenance records bind the named files, not the complete
Python environment, dynamic-library closure, kernel, driver, or
confidential-compute identity; those remain part of the measured-runner
boundary.

No production-completion claim follows from this wiring. The retained KAT is
small, synthetic upstream intervals are widened through zero, and no
source-scale zero-isolation/Turing artifact or confidential-compute receipt
exists. The current supervisor also retains bounded control files; connecting
the formulaic t-block source producer without a source-sized control manifest
is still required before a full launch. Upstream semantic receipt linkage and
target-specific calibration are also not completed by this integration.
