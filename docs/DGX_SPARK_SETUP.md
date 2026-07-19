# DGX Spark setup

The tested baseline is NVIDIA DGX OS on `aarch64`, one GB10 GPU with compute
capability 12.1, and CUDA 13.0 or another toolkit that explicitly supports
`sm_121`.

Required commands on `PATH` are `lean`, `lake`, `cmake`, `nvidia-smi`,
`openssl` 3.x for optional Ed25519 operator signatures, and the CUDA tools
under `/usr/local/cuda/bin`. Use the NVIDIA-provided driver/toolkit pair rather
than replacing the driver as part of this build.

```bash
git status --short
./tools/build_dgx_spark.sh
```

Expected outputs include:

- `build/run/environment.txt` and its SHA-256 record;
- `build/run/probe.json`, with `evidence_class` equal to
  `local_unattested`, `passed` equal to `true`, and
  `hardware_attestation` equal to `null`;
- the executable, PTX, ELF and SASS dumps plus hashes in
  `build/artifacts/`;
- a successful `lake build`, axiom audit and CTest run.

The CTests use small development samples (`1024` primitive rows per operation,
`1024` randomized expression/row cases, and `1024` generated-PTX polynomial
rows). They catch regressions quickly but do not satisfy the Phase 4/5
acceptance runs. Run the large paths separately:

```bash
python3 tools/run_primitive_conformance.py --count 1250000 \
  --work-dir build/primitive-conformance/rows-1250000
python3 tools/run_expression_conformance.py --count 1000000 \
  --program-count 256 \
  --work-dir build/expression-conformance/rows-1000000-programs-256
python3 tools/run_generated_ptx_conformance.py \
  --generator .lake/build/bin/sparkinterval-gen \
  --driver build/dgx-spark/sparkinterval-generated-driver \
  --count 100000 \
  --work-dir build/generated-ptx-conformance/rows-100000
python3 tools/close_generated_ptx_acceptance.py \
  --work-dir build/generated-ptx-conformance/rows-100000 \
  --generator .lake/build/bin/sparkinterval-gen \
  --driver build/dgx-spark/sparkinterval-generated-driver \
  --phase4 build/dgx-spark/sparkinterval-expression-batch
```

The primitive count is per operation; the expression count is total across
the randomized programs. The generated-PTX closure deliberately repeats its
exact comparison. Exact rational CPU recomputation, not GPU execution,
dominates the validation wall time. The current `build_dgx_spark.sh` bundle is
the diagnostic probe bundle. After the generated-cubin closure succeeds, use
`tools/create_dgx_generated_cubin_bundle.py` as documented in
`REPRODUCIBILITY.md` to create the complete local arithmetic-result bundle.

For a small end-to-end mathematical application after the build, run:

```bash
python3 tools/run_zeta_poc.py run \
  --work-dir build/examples/zeta2-4096 --s 2 --terms 4096
python3 tools/run_zeta_poc.py verify build/examples/zeta2-4096
```

This produces a rigorous real `zeta(2)` enclosure by combining exactly checked
GPU term intervals with an integral-test tail. It remains a local-unattested
record. The operator-signature commands in `examples/README.md` can endorse
the exact bundle with a user-owned Ed25519 key; they cannot turn GB10 into
hardware-attested execution.

The strict probe expects exactly one GPU.  Its development override is for
portability experiments and must never be used in a recorded DGX acceptance
run.

If the probe fails, retain its standard error and environment record.  Do not
edit expected bit patterns or substitute an unbounded interval to turn a
failure into success.
