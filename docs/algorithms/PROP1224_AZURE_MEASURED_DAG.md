# Proposition 12.2.4: closed Azure measured DAG

The `helfgott-prop-12-2-4-mpfr-v1` portfolio campaign now has a closed
Azure SEV-SNP CPU workload factory, source-build materializer, retained-export
protocol, and terminal registered-result path. This is production capability,
not evidence that the production computation has run. No Azure receipt or
unconditional Lean theorem is claimed here, and the semantic portfolio row
remains disabled.

## Exact computation and registered boundary

The fixed plan partitions all 3,389,047,618 source q-ranks into 12,930
gap-free logical leaves. Four measured jobs each use 96 worker processes over
a balanced strided group of those leaves. They run the source-reviewed C++
producer at 192-bit MPFR precision with exact GMP prefix arithmetic, retain
every canonical receipt, and emit operational results that pin the retained
archives and trees. Each external trace verifier reruns its entire group and
compares every timing-independent receipt field.

The terminal accepts exactly the four signed predecessor-group identities in
order. It safely extracts every retained export, validates all 12,930 receipts,
requires one common packaged executable hash, replays the fixed-plan affine
coverage proof, and checks the final state is exactly 3,389,047,618. Only then
does it emit literal `true`. Its trace verifier independently repeats the full
merge from the predecessor handoff.

The registered invocation `helfgottProp1224ProductionV1` has these hashes:

| Field | SHA-256 |
| --- | --- |
| algorithm | `184e8f8f60f511868d39a7a1ab7599a4b725415892e99c8fd84a35f8bf6c38a1` |
| input | `ced1a63532a63b6e24290c51082ff8865ce38c75daae0d4f3439a63eef2444ec` |
| parameters | `fac07cd6c76a9e2caf7e475107046d76683788426b1c9e26ac8d66aed8114853` |
| domain | `effa0ec90992a66d497c13fba77923a9fb96996d93be9d8d6fd54b21a09e92a3` |
| output `true` | `b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b` |

## Source-built runtime closure

The site document conforms to
`schemas/azure-cpu-prop1224-materializer-site.schema.json`. It supplies no
executable, argv, shell, or environment. It supplies only a pinned base CPU
operator site, the exact official GMP 6.3.0 and MPFR 4.2.1 source trees, and,
for the terminal, the exact retained predecessor exports.

On an x86-64 build host, the materializer builds static GMP, GMP C++, and MPFR
libraries with generic x86-64-v2 flags, compiles and strips the fixed C++
producer, rejects a dynamic runner, and runs a fast representative directed
sample. It
packages the complete canonical GMP and MPFR source archives, all project
sources used by the measured program, a source-closure manifest, the static
producer, and one image-bound CPython host. Prefix maps, a zero source epoch,
generic tuning, and omission of a linker build ID are intended to make
independently built leaf binaries reproducible; the terminal additionally rejects the campaign if
any leaf executable hash differs from its own packaged runner.

The official source pins are:

- GMP archive SHA-256
  `a3c2b80201b89e68616f4ad30bc66aee4927c3ce50e33929ca819d5c43538898`
  and source-tree SHA-256
  `a1cba368a6dcf6d3bd96715628d4837c071f38cb3e35db45aeaac063ad0623a6`;
- MPFR archive SHA-256
  `277807353a6726978996945af13e52829e3abd7a9a5b7fb2793894e18f1fcbb2`
  and source-tree SHA-256
  `63e9189eabea4cc9496f5091a81cae6eb45e21ca072090ea281704e3cd9c259d`.

The copied CPython executable still uses the loader, libc, and standard
library in the reviewed Azure image. The compiler and those image components
remain disclosed parts of the trusted implementation boundary.

## Materialize and run

Prepare a portfolio leaf, then review and build its package on x86-64:

```bash
python3 tools/tg_azure_cpu_prop1224_materializer.py plan \
  /operator/portfolio-spec.json \
  helfgott-prop-12-2-4-mpfr-v1::mpfr-shards 0 \
  /operator/prop1224-materializer-site.json

python3 tools/tg_azure_cpu_prop1224_materializer.py materialize \
  /operator/portfolio-spec.json \
  helfgott-prop-12-2-4-mpfr-v1::mpfr-shards 0 \
  /operator/prop1224-materializer-site.json
```

After all logical-leaf receipts and retained exports are recorded, the
terminal site must enumerate all four exact group-export pins and the terminal group is
`helfgott-prop-12-2-4-mpfr-v1::merge-and-verify`. Review the emitted
`materialization-manifest.json` against
`schemas/azure-cpu-prop1224-materialization.schema.json`, then execute its
`cpu-campaign.json` through the Azure CPU production operator.

The returned certificate package carries each export at
`bundle-root/work/prop1224/prop1224-retained.tar`. Preserve that file beside
the verified operational receipt and put its exact path, SHA-256, byte length,
group ID, and group index in the terminal site. The materializer rechecks both
the signed result pin and the complete retained tree before copying it into the
terminal handoff.

Materialization always reports `accepted:false`. Completion still requires
the actual Azure jobs, MAA/SEV-SNP/vTPM and transcript appraisal, Managed HSM
receipts, source-registry admission, review of the MPFR/GMP-to-exact-real
`SourceScaleEvidence`, and explicit enablement of the semantic binding.

The materializer's x86-64 build is intentionally refused on the current
aarch64 DGX Spark host. The same source worker was built and sampled natively
on aarch64, but the production x86 package and cross-job binary reproducibility
still require an x86-64 review-host smoke test before launch.

## Runtime and cost envelope

Empty-row measurements extrapolate to 61--73 core-hours for one replay. The
production sizing model retains the more conservative 105.6--640 core-hour
range per replay, and this protocol performs two complete replays. On the fixed
four-node, 384-vCPU fleet that is 211.2--1,280 aggregate core-hours, or about
0.55--3.34 ideal compute hours before launch, attestation, terminal, and retry
overheads. At the recorded East US 2 rates, that compute band is approximately
$9.59--$58.22 PAYG or $1.77--$10.76 Spot. A complete-node Azure pilot is still
required; these are planning bounds, not a measured source-scale completion.

## Focused checks

```bash
python3 -m unittest -v \
  tests.test_azure_cpu_prop1224_workload \
  tests.test_azure_tg_portfolio \
  tests.test_trusted_compute_registry

./tools/safe_lean.sh \
  SparkInterval/Tests/RegisteredProp1224CertificateTest.lean
```
