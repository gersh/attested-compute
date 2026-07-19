# Examples

Run these commands from the repository root. Build artifacts and generated
evidence go under `build/`; private keys must stay outside version control.

## 1. Exact reference certificate

This small expression computes `x * (1 + y)` on two interval rows. The checker
recomputes every result using exact rational binary64 arithmetic.

```bash
python3 examples/reference-certificate/create_example.py
mkdir -p build/examples/reference
python3 -m reference.cli evaluate \
  examples/reference-certificate/batch.json \
  build/examples/reference/result.json
python3 -m reference.cli certify \
  --result build/examples/reference/result.json \
  examples/reference-certificate/batch.json \
  build/examples/reference/certificate.json
python3 -m reference.cli check \
  build/examples/reference/certificate.json
```

This is a Python-recomputed reference certificate, not execution evidence and
not yet a Phase 8 Lean certificate.

## 2. Axiom-free Lean interval proof

```bash
lake env lean examples/lean/IntervalArithmetic.lean
lake env lean examples/lean/ZetaIdentity.lean
```

The first file proves a concrete interval multiplication enclosure using the
verified core. The second records Mathlib's exact identity
`riemannZeta 2 = pi^2 / 6`; it deliberately does not claim that Lean parsed the
GPU result format.

## 3. Rigorous real-zeta DGX tutorial

Build the native expression runner and compute 4,096 terms of the positive
Dirichlet series for `zeta(2)`:

```bash
cmake -S . -B build/dgx-spark \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=121
cmake --build build/dgx-spark --parallel
python3 tools/run_zeta_poc.py run \
  --work-dir build/examples/zeta2-4096 \
  --s 2 --terms 4096
python3 tools/run_zeta_poc.py verify build/examples/zeta2-4096
```

The GPU evaluates `1/n^2` as an interval for every `n`. Verification reparses
and exactly recomputes all rows, requires a byte-identical replay, re-runs the
PTX and SASS audits, folds the intervals outward, and applies
`1/(N+1) <= tail <= 1/N`. The retained GB10 run enclosed the real value between
raw binary64 endpoints `3ffa51a65a53d51c` and `3ffa51a66a52e51f`.

Other real integer arguments use the same reviewed algorithm when the fixed
binary64 program remains finite:

```bash
python3 tools/run_zeta_poc.py run \
  --work-dir build/examples/zeta3-2048 \
  --s 3 --terms 2048
python3 tools/run_zeta_poc.py verify build/examples/zeta3-2048
```

This tutorial evaluates real values for `s > 1`; it does not locate or count
critical-strip zeros.

## 4. Create an operator key and sign the zeta run

For a disposable local tutorial, explicitly request an unencrypted mode-`0600`
Ed25519 private key:

```bash
python3 tools/local_operator_signature.py keygen \
  --private-key build/examples/operator-key/operator-private.pem \
  --public-key build/examples/operator-key/operator-public.pem \
  --allow-unencrypted-private-key
python3 tools/local_operator_signature.py sign \
  build/examples/zeta2-4096/run-bundle.json \
  --artifact-root build/examples/zeta2-4096 \
  --private-key build/examples/operator-key/operator-private.pem \
  --out build/examples/zeta2-4096/run-bundle.signature.json
```

For a retained key, use `--passphrase-file` at key generation and signing
instead. Both the private key and passphrase file must be mode `0600`. Back up
the private key securely and distribute the public-key fingerprint through a
separate trusted channel.

The signing utility can check the detached signature and all bundle artifacts
directly:

```bash
python3 tools/local_operator_signature.py verify \
  build/examples/zeta2-4096/run-bundle.json \
  build/examples/zeta2-4096/run-bundle.signature.json \
  --artifact-root build/examples/zeta2-4096 \
  --trusted-public-key \
    build/examples/operator-key/operator-public.pem
```

Verify the signed policy with the separately pinned public key and persistent
replay state:

```bash
python3 tools/verify_run_bundle.py \
  build/examples/zeta2-4096/run-bundle.json \
  --artifact-root build/examples/zeta2-4096 \
  --policy dgx_operator_signed \
  --operator-signature \
    build/examples/zeta2-4096/run-bundle.signature.json \
  --trusted-operator-key \
    build/examples/operator-key/operator-public.pem \
  --replay-db build/examples/verifier/operator-nonces.sqlite3
```

Success means the pinned key signed the exact artifact-verified local record.
It still returns `hardware_evidence: false`. Repeating the command with the
same replay database rejects the nonce.

## 5. Unsigned DGX and generated-cubin evidence

The development script creates an unsigned diagnostic probe bundle:

```bash
./tools/build_dgx_spark.sh
python3 tools/verify_run_bundle.py \
  build/dgx-probe-bundle/run-bundle.json \
  --artifact-root build/dgx-probe-bundle
```

For the stronger restricted-PTX polynomial path, run the base acceptance,
independent closure, and strict packager shown in
[`docs/REPRODUCIBILITY.md`](../docs/REPRODUCIBILITY.md). The detached signature
tool can sign that resulting local bundle in exactly the same way as the zeta
bundle.

## 6. Lean execution-trust boundary

```bash
lake env lean examples/lean/ExecutionTrust.lean
```

The example shows that unsigned local evidence is rejected and displays the
shape of the explicit DGX operator-trust axiom. That axiom assumes the signed
operator claim truthfully describes a physical run; Ed25519 alone does not
prove that fact.

## 7. H100 offline example

```bash
./tools/build_h100_offline.sh
./tests/test_h100_offline.sh
./tools/build_h100_interval_batch_offline.sh
./tests/test_h100_interval_batch_offline.sh
```

These commands produce and inspect real `sm_90` artifacts without claiming an
H100 ran. Production acceptance remains fail-closed until a supported H100
confidential-computing platform and verifier are available.
