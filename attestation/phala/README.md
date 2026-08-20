# The Phala TDX attested-run pipeline

Seven files that take CompCert-compiled artifacts, run them inside an Intel TDX
confidential VM, and produce evidence a third party can check offline — without
trusting the host, the cloud, or this repository.

The pipeline is **generic**: it names no artifact and no consumer. A
*deployment* is a directory holding a `deployment.json` manifest, its artifacts,
its generated compose and its retained evidence; the pipeline is invoked against
one. See `../../docs/PHALA_TDX_DEPLOYMENT.md` for the deployment format and
`../../docs/TRUSTING_THE_ENCLAVE.md` for what the evidence proves.

| file | what it does |
| --- | --- |
| `build_compose.py` | generates the measured `docker-compose.yaml` from a manifest, embedding every artifact and the entry point verbatim |
| `enclave_run.sh` | the in-CVM entry point, embedded byte-for-byte into that compose |
| `mock_dstack.py` | a stand-in guest agent, so the entry point can be rehearsed with no hardware and no cost |
| `dry_run.sh` | runs the **committed** compose's entry point locally, in the compose's own image and posture |
| `negative_test.sh` | six gates, each of which must **refuse** |
| `deploy.sh` | deploys, waits, captures evidence, verifies, and destroys the CVM |
| `verify_run.py` | checks the evidence offline against the pinned Intel SGX Root CA |

## The order things happen in

```sh
DEPLOYMENT=../../../claude_math/audits/compcert/rh_phala   # holds deployment.json

python3 build_compose.py --manifest "$DEPLOYMENT/deployment.json"
bash dry_run.sh       "$DEPLOYMENT"    # free; must pass before spending
bash negative_test.sh "$DEPLOYMENT"    # free; every gate must refuse
PHALA_CLOUD_API_KEY=phak_... bash deploy.sh "$DEPLOYMENT"   # ~$0.03
python3 verify_run.py --deployment "$DEPLOYMENT" \
        --log "$DEPLOYMENT/retained-evidence/phala-run.log"
```

Then, in the consuming repository, generate the Lean receipt literal rather
than transcribing sixteen hexadecimal fields by hand:

```sh
python3 ../../tools/attest/emit_lean_receipt.py "$DEPLOYMENT/retained-evidence" \
        compcert-run-v1:ceu_harmonic_1048576
```

It prints the app id, compose hash and enclave key to stderr — the three values
a reviewer must have pinned before the receipt can be accepted at all.

`deploy.sh` regenerates the compose first and refuses if it differs from the
committed one — otherwise the run would attest binaries that are not the ones
on disk here.

## Why the rehearsal is written the way it is

`dry_run.sh` extracts the entry point and the environment **from the committed
compose**, and derives its `docker run` flags — image, `read_only`, `tmpfs`,
`cap_drop`, `security_opt`, `pids_limit`, `user`, `network` — from that same
document rather than restating them.

This is not fastidiousness. Both scripts once ran in a convenient local image
while printing the compose's image in their logs, and that image happened to
have no native `gcc`. The consequence was that an entry point which
`apt-get install`ed its own signing interpreter looked necessary and passed the
gate whose entire purpose is *"what deploys is what was exercised"* — for nine
real runs. A rehearsal that diverges from the deployment in any dimension is
testing something else in that dimension.

Only two things still differ from a real run, and both are consequences of the
host being aarch64 while the artifacts are x86_64:

* `RUNNER=qemu-x86_64-static`, with the emulator and its sysroot bind-mounted
  in rather than installed, so the image itself is unmodified. **This makes the
  rehearsal blind to `noexec`**: qemu opens the artifact as *data*, so a
  work directory mounted `noexec` does not stop it, while on hardware every
  artifact would fail with exit 126. The entry point therefore probes
  executability directly, and `negative_test.sh` gate 6 proves the probe fires.
* the guest agent is `mock_dstack.py`, so the quote's signature is invalid —
  `verify_run.py` rejects it, which is the point.

## Why the negative tests exist

A gate that has only ever been seen to pass is not known to be a gate. Each of
the six was seen to refuse before it was relied on:

1. a tampered binary — refused *before* execution, on the digest;
2. a wrong pinned transcript digest — reported `MISMATCH`, `matched=0`;
3. a wrong pinned exit status — likewise;
4. a mock, unsigned quote — the verifier refuses the whole run;
5. an image without the toolchain — refused, rather than installing it;
6. a `noexec` work directory — refused up front, nothing executed.

Gate 1 exists because a checker that took its trust anchor as a *parameter*
once accepted a receipt signed by a key of the author's own making.

## Evidence leaves through the log

The only channel out of the CVM is `phala cvms logs`, so the entry point emits
each artefact as delimited base64 with a declared SHA-256. `verify_run.py`'s
**E** checks recompute those digests before anything else, which is why
tampering with an emitted document is caught at transport rather than by the
later content checks.
