# Sqrt218 cloud Clight/VST/CompCert proof-build lane

This directory defines a cloud-only, fail-closed build lane for the remaining
Sqrt218 compiler obligation. It does not replay a production certificate and
does not turn build metadata into a Lean theorem.

The exact Lean target is:

```text
ArchitectureExecutionSuppliesSuccessfulPureEntry implementation
```

The source checker on that boundary is
`successfulPureEntryChecker implementation.identity.neutralContractId`.
An accepted source execution must supply the values and facts in
`CSuccessfulPureEntryTrace`; it is not an abstract `nativeRun` callback.

## Current status

`cloud-proof-build.v1.json` deliberately has
`proof_project.execution_ready: false`. The substantive files
`Sqrt218Spec.v` and `Sqrt218Proof.v` do not yet exist, so their digest and size
pins are `null`. Ordinary metadata/source validation succeeds, while the
cloud runner and `--require-ready` fail before invoking a tool:

```bash
python3 tools/tg_sqrt218_proof_build.py \
  validate proof_build/sqrt218/cloud-proof-build.v1.json \
  --repository-root .

python3 tools/tg_sqrt218_proof_build.py \
  validate proof_build/sqrt218/cloud-proof-build.v1.json \
  --repository-root . \
  --proof-root /reviewed/sqrt218-vst \
  --require-ready
```

Do not change `execution_ready` until both reviewed files have non-null exact
SHA-256 and size pins, the blocker list is empty, and the manifest self-hash
has been updated. No admitted placeholder or Rocq `Axiom` is an acceptable
substitute for the missing proof.

The readable plan, including the closed Azure argv, is available without
running anything:

```bash
python3 tools/tg_sqrt218_proof_build.py \
  show-plan proof_build/sqrt218/cloud-proof-build.v1.json
```

## Pinned toolchain image

The Dockerfile starts from the official Rocq 9.1.1 amd64 image by immutable
OCI digest. It checks out exact full revisions of:

- CompCert 3.17 at
  `7b1f02b09954b9b916eb2a91d283c9b5355bf172`; and
- VST 2.16 development source at
  `cbee87efb4bee2b588f8321e16b4cb7664d5cf60`.

The VST source itself identifies its bundled CompCert front end as 3.17.
CompCert 3.17 supports Rocq 9.1. The final image produced by Azure Container
Registry is nevertheless the run identity: Debian packages fetched while
building are not treated as reproducible merely because the base image and
Git revisions are pinned. The proof job must use
`registry/repository@sha256:digest`, never a tag.

The image build is intended for Azure, not an ordinary local verification:

```bash
LANE_SHA="$(
  python3 tools/tg_sqrt218_proof_build.py \
    show-plan proof_build/sqrt218/cloud-proof-build.v1.json |
  python3 -c \
    'import json,sys; print(json.load(sys.stdin)["review"]["lane_manifest_sha256"])'
)"

az acr build \
  --registry "${ACR_NAME}" \
  --platform linux/amd64 \
  --image "sqrt218-proof-build:${LANE_SHA}" \
  --file proof_build/sqrt218/Dockerfile \
  .

FINAL_IMAGE_DIGEST="$(
  az acr manifest show-metadata \
    --registry "${ACR_NAME}" \
    --name "sqrt218-proof-build:${LANE_SHA}" \
    --query digest \
    --output tsv
)"

case "${FINAL_IMAGE_DIGEST}" in
  sha256:[0-9a-f][0-9a-f]*) ;;
  *) echo "ACR did not return a SHA-256 image digest" >&2; exit 2 ;;
esac
```

The `az acr manifest` command group is currently preview; retain the returned
metadata response and independently check that the digest is exactly 64
lowercase hexadecimal digits before deployment.

The ACI argv in the lane manifest:

- uses the final image by digest;
- uses a user-assigned identity for both ACR pull and the container;
- mounts one Azure Files workspace;
- requires an operator-supplied VNet/subnet whose reviewed policy denies
  proof-run egress; and
- passes `TG_CLOUD_PROOF_BUILD=1`.

The identity needs `AcrPull` on the registry. The Azure Files share must have
this shape before the run:

```text
/workspace/
  repository/   exact source snapshot containing this lane
  proof/        reviewed Sqrt218Spec.v and Sqrt218Proof.v
  # output/ must not exist
```

The runner verifies all repository and proof pins before creating `output/`.
It refuses a pre-existing output directory and a final image reference that
is not digest-pinned. The complete command can be copied from `show-plan`
after substituting the named `${...}` operator values. Microsoft documents
the corresponding [managed-identity ACR pull][aci-acr] and
[Azure Files ACI mount][aci-cli] parameters.

## Closed proof-build sequence

The image entrypoint performs these steps only after readiness validation:

1. Hash the exact C/header/wrapper/proof source closure.
2. Run `ccomp -E` with `TG_SQ218_PURE_ENTRY_ONLY=1` and retain the `.i`.
3. Run `clightgen -csyntax -canonical-idents`, retaining the generated Rocq
   CompCert Csyntax program.
4. Run `clightgen -clight -normalize -canonical-idents`, retaining the
   generated Rocq Clight program. The textual `.compcert.c` and `.light.c`
   renderings are retained as additional diagnostics, not substituted for
   either Rocq AST.
5. Compile the reviewed VST specification and proof with `rocq makefile`.
6. Run standalone `rocq check -o` on `Sqrt218.Sqrt218Proof`.
7. Compile `Sqrt218AssumptionAudit.v`, which prints the assumptions of
   `body_tg_sq218_verify_snapshot_v2`.
8. Run `ccomp -S -sdump -dc -dclight -fnone` on the same preprocessed input,
   retaining abstract assembly JSON, textual assembly, and front-end dumps.
9. Run the system assembler and linker separately.
10. Retain the object, link map, static ET_EXEC ELF, and `readelf` header,
   segment, section, symbol, and dependency reports.
11. Produce a bounded artifact index containing every path, size, SHA-256,
    command argv, exit code, tool executable identity, and final image digest.

Command argv is retained as NUL-separated bytes (`*.argv0`), so argument
boundaries are unambiguous. Empty stdout/stderr is represented by an explicit
domain-separated empty-stream marker so every compiler-evidence artifact has
positive size. No artifact index authorizes a receipt or Lean theorem.

The retained paths map directly to the existing
`sqrt218-compiler-evidence-manifest.schema.json` fields. In particular:

- source closure, preprocessed source, generated Rocq Csyntax and Clight ASTs
  map to `build_chain.c_translation`;
- the `rocq check` streams, assumption report, and deterministic proof bundle
  map to `build_chain.vst`;
- `ccomp`, its configuration, `.sdump`, and `.s` map to
  `build_chain.compcert`;
- system `as`, object, `ld`, map, ELF, and `readelf` reports map to the
  assembler/linker/ELF sections.

Valex is recorded as unsupported unless an independently pinned licensed
tool is supplied; its absence never silently removes the assembler boundary.

## What the VST proof must establish

The VST theorem must be about the generated Clight function
`tg_sq218_verify_snapshot_v2`. For every successful call under the exact
pointer, length, writable-output, and non-aliasing preconditions, it must
establish the neutral source contract that maps field-for-field to:

```text
CSuccessfulPureEntryTrace
  inputBytes encodedInputByteLength cResult snapshotSHA256 outputBytes
```

That includes the exact source SHA-256 bytes, successful complete validation,
and exact 120-byte result encoder output. The cross-prover map must explain
how the VST memory arrays, words, return/status values, and existential
results correspond to those Lean fields. The checker identifier is the
neutral-contract ID; there is no unconstrained function parameter.

VST proves a property of Clight execution. The standalone Rocq checker
rechecks the resulting `.vo` dependency closure, but neither operation proves
the Lean/Rocq proposition mapping by itself.

## Exact remaining boundary

The [CompCert manual][compcert-cli] documents `-E`, already-preprocessed `.i`
input, `-S`, `-sdump`, `-dc`, and `-dclight`. It also explicitly places the
preprocessor, assembler, and linker outside CompCert's verified core. The
lane therefore stops its compiler theorem at CompCert abstract x86-64
assembly. These remain separate obligations:

```text
external preprocessing / Clight generation
Rocq-to-Lean neutral-contract equivalence
CompCert extraction and the concrete compiler executable
abstract assembly -> assembler output object
object + link map -> exact static ET_EXEC bytes
ELF decoding, loading, and SysV ABI entry behavior
x86-64 instruction semantics
physical CPU conformance and Azure execution evidence
```

CompCert's x86-64 support does not collapse those edges. The flat entry avoids
CompCert's documented nonstandard x86-64 struct-by-value convention, but the
pointer/scalar SysV ABI bridge still needs proof.

Two research directions remain candidates, not integrations:

- Mario Carneiro's [MM0 x86-64/ELF work][mm0-paper] has a small executable
  behavior specification derived from Sail and a Lean translation at
  `mm0-lean/x86.lean`. It may seed the exact x86/ELF machine model, but no
  translation or refinement into this repository has been proved.
- [CompCertELF][compcertelf] verifies a research chain to relocatable ELF
  object files. Its published chain does not directly produce this final
  static x86-64 ET_EXEC or close the linker/loader edge; later analysis also
  describes its implemented instruction support as x86-32-specific. It is
  therefore only a research alternative.

Official references:

- [CompCert command-line manual][compcert-cli]
- [CompCert installation and external-tool boundary][compcert-install]
- [VST installation/build organization][vst-build]
- [Rocq batch compiler and standalone checker][rocq-commands]
- [Official Rocq container image][rocq-image]

[aci-acr]: https://learn.microsoft.com/en-us/azure/container-instances/using-azure-container-registry-mi
[aci-cli]: https://learn.microsoft.com/en-gb/cli/azure/container
[compcert-cli]: https://compcert.org/man/manual003.html
[compcert-install]: https://compcert.org/man/manual002.html
[compcertelf]: https://flint.cs.yale.edu/shao/papers/compcertelf.html
[mm0-paper]: https://arxiv.org/abs/1907.01283
[rocq-commands]: https://docs.rocq-prover.org/master/refman/practical-tools/coq-commands.html
[rocq-image]: https://hub.docker.com/r/rocq/rocq-prover/
[vst-build]: https://github.com/PrincetonUniversity/VST/blob/master/BUILD_ORGANIZATION.md
