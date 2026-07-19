# Documentation

SparkInterval separates mathematical verification, modeled GPU execution, and
physical-run provenance. Start with the section that matches your role.

## Users

- [Project overview and quick start](../README.md)
- [User workflows](USING.md)
- [DGX Spark setup](DGX_SPARK_SETUP.md)
- [Worked examples](../examples/README.md)
- [H100 offline support](H100.md)

## Verifiers

- [Verifier guide](VERIFYING.md)
- [Correctness claims and proof boundary](CORRECTNESS_CLAIMS.md)
- [Trust model and execution assumptions](TRUST_MODEL.md)
- [Reproducibility and independent-checking runbook](REPRODUCIBILITY.md)
- [GPU and typed-machine model](GPU_MODEL.md)

## Operators and maintainers

- [Memory-safe build requirements](MEMORY_SAFE_BUILDS.md)
- [DGX Spark setup and acceptance runs](DGX_SPARK_SETUP.md)
- [Attestation component boundary](../attestation/README.md)

## Format reference

- [Certificates, run bundles, profiles, and signatures](FORMAT.md)
- [Real-integer zeta tutorial](algorithms/REAL_ZETA_POC.md)
- [Immutable algorithm specifications](../specifications/README.md)
- [Canonical JSON schemas](../schemas/)
- [Target and trust profiles](../profiles/)

The zeta tutorial evaluates positive real values for integers greater than one.
It does not verify critical-strip zeros or zeros up to a height.
