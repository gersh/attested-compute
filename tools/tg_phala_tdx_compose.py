#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Generate the dstack deploy manifest for the CH25 A.7 Phala TDX campaign.

Two files come out:

* ``docker-compose.yaml`` -- two services, both pinned to the campaign image
  **by registry digest**.  The first is the prelude, which stages the inputs
  the entry point requires; the second is the campaign itself, which starts
  only if the prelude exited zero.
* ``app-compose.json`` -- the dstack application document.  Its ``sha256`` is
  the ``compose_hash`` dstack measures into RTMR3, and its first twenty bytes
  are the ``app_id``.

Three source files are embedded verbatim inside ``docker-compose.yaml``, and
therefore inside ``app-compose.json``, and therefore inside the compose hash
and RTMR3:

* ``prelude_phala_tdx_inputs.py`` -- run by the prelude service to stage the
  inputs, and run again by the campaign service, in ``--derive-key-only``
  mode, to re-derive the signing key;
* ``run_phala_tdx_campaign.sh`` -- the campaign entry point;
* ``emit_phala_tdx_evidence.py`` -- prints the evidence to stdout at the end.

That is the point: everything that derives the key, computes the report-data
commitment, gates on the appraisal, signs, and decides what leaves the CVM is
measured by the same quote it requests.  None of it is fetched at run time.
The published image contributes the workload, ``tg_verifier`` and the pinned
python-flint wheel, and is itself pinned by registry digest here; the entry
scripts deliberately come from this document rather than from the image, so
that a change to them is visible in the compose hash without a republished
image.

Volumes, and the mistake this encodes
-------------------------------------

``campaign-shared`` is an ORDINARY named volume.  It must never be given
``driver_opts: {type: tmpfs}``: a tmpfs-backed named volume is **not** shared
between containers -- each mounting container gets its own fresh, empty
tmpfs.  The first real Phala TDX run failed exactly there, with the campaign
container reporting ``/workspace/staging/input/job-scope.env: No such file or
directory`` after a fully successful attestation.  Secrets stay off that
volume by not being written at all: the key is re-derived in the campaign
container onto a container-local tmpfs (a service-level ``tmpfs:`` entry,
which *is* private per container and is the right tool for that job).

``tests/test_phala_tdx_manifest.py`` re-runs this generator and requires the
committed files to match byte for byte, so the embedded copy cannot drift from
``proof_build/ch25_a7_phala_tdx/prelude_phala_tdx_inputs.py``.

Usage
-----

Committed template (challenge and job binding are refusal sentinels)::

    python3 tools/tg_phala_tdx_compose.py --template

A real deployment::

    python3 tools/tg_phala_tdx_compose.py \\
        --challenge <64 hex, unpredictable, chosen before the run> \\
        --job-binding <64 hex> \\
        --issued-at 2026-08-01T00:00:00Z \\
        --out-dir /somewhere/outside/the/repo
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "proof_build/ch25_a7_phala_tdx"
PRELUDE = BUILD / "prelude_phala_tdx_inputs.py"
CAMPAIGN_ENTRY = BUILD / "run_phala_tdx_campaign.sh"
EVIDENCE_EMITTER = BUILD / "emit_phala_tdx_evidence.py"
DEFAULT_OUT_DIR = BUILD

# Paths the compose entry points write the measured sources to, inside the
# containers.  ``/tmp`` is a container-local tmpfs in both services.
PRELUDE_IN_CVM = "/tmp/prelude_phala_tdx_inputs.py"
CAMPAIGN_ENTRY_IN_CVM = "/tmp/run_phala_tdx_campaign.sh"
EVIDENCE_EMITTER_IN_CVM = "/tmp/emit_phala_tdx_evidence.py"

SHARED_ROOT = "/workspace/shared"
INPUT_ROOT = SHARED_ROOT + "/input"
EVIDENCE_ROOT = SHARED_ROOT + "/evidence"
OUTPUT_ROOT = "/workspace/out/output"
KEY_ROOT = "/workspace/keys"

# How long each container stays alive after it has said everything it has to
# say.  `phala cvms logs` cannot read the logs of a container that has exited,
# so a container that exits immediately takes its output with it.  These are
# literals here, hence measured, and they are the only reason the evidence is
# retrievable at all.
EVIDENCE_HOLD_SECONDS = 86400
PRELUDE_FAILURE_HOLD_SECONDS = 86400

IMAGE_DIGEST = (
    "sha256:4e6029a39771bd18f9e0b9bc64017393700ce47c17a678dd93cbf0ddc17c774f"
)
IMAGE = (
    "ghcr.io/gersh/sparkinterval-ch25-a7-phala-tdx@" + IMAGE_DIGEST
)

APP_NAME = "sparkinterval-ch25-a7-boundary"
HEREDOC = "SPARKINTERVAL_PRELUDE_SOURCE_EOF"
CAMPAIGN_HEREDOC = "SPARKINTERVAL_CAMPAIGN_ENTRY_EOF"
EVIDENCE_HEREDOC = "SPARKINTERVAL_EVIDENCE_EMITTER_EOF"

# Deliberately not 64 hex digits: `require_phala_tdx_worker` rejects these, so
# the committed template cannot be deployed by accident.
TEMPLATE_CHALLENGE = "REPLACE-WITH-64-HEX-UNPREDICTABLE-CHALLENGE-NONCE"
TEMPLATE_JOB_BINDING = "REPLACE-WITH-64-HEX-JOB-BINDING-SHA256"
TEMPLATE_ISSUED_AT = "REPLACE-WITH-RFC3339-UTC-INSTANT"

HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
RFC3339 = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


def compose_escape(text: str) -> str:
    """Protect an embedded shell script from Compose's own interpolation.

    Compose expands ``$VAR`` in the compose file *before* the container sees
    it, and aborts on ``${VAR:?message}`` when VAR is unset in the deploying
    shell.  The first real run of the restructured manifest died exactly
    there: ``required variable TG_PYTHON_FLINT_WHEEL is missing a value``,
    because the campaign entry point's own shell variables were read as
    compose variables.  Nothing in these blocks is ever meant to be
    interpolated by Compose -- the environment arrives via ``environment:``
    and everything else is resolved by the shell at run time -- so every ``$``
    is escaped, and ``$$`` reaches the container as a literal ``$``.
    """
    return text.replace("$", "$$")


def indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "".join(pad + line if line.strip() else line for line in text.splitlines(True))


def compose_yaml(*, challenge: str, job_binding: str, issued_at: str,
                 IMAGE: str = IMAGE) -> str:
    # ``IMAGE`` overrides the registry host only.  The digest is not a
    # parameter: ``IMAGE_DIGEST`` stays authoritative and the caller is
    # required to supply a reference carrying exactly it, so a different
    # registry can never mean different bytes.
    if not IMAGE.endswith("@" + IMAGE_DIGEST):
        raise SystemExit(
            f"image reference must be pinned to {IMAGE_DIGEST}; got {IMAGE}"
        )
    sources = {}
    for label, path, sentinel in (
        ("prelude", PRELUDE, HEREDOC),
        ("campaign entry point", CAMPAIGN_ENTRY, CAMPAIGN_HEREDOC),
        ("evidence emitter", EVIDENCE_EMITTER, EVIDENCE_HEREDOC),
    ):
        text = path.read_text(encoding="utf-8")
        for other in (HEREDOC, CAMPAIGN_HEREDOC, EVIDENCE_HEREDOC):
            if other in text:
                raise SystemExit(f"the {label} source contains a heredoc sentinel")
        if "\t" in text:
            raise SystemExit(
                f"the {label} source contains a tab; YAML block scalars and "
                "tabs do not mix"
            )
        for number, line in enumerate(text.splitlines(), start=1):
            if line != line.rstrip():
                raise SystemExit(
                    f"the {label} source has trailing whitespace on line "
                    f"{number}; a YAML block scalar would not round-trip it"
                )
        sources[label] = text

    write_prelude = (
        f"cat >{PRELUDE_IN_CVM} <<'{HEREDOC}'\n"
        + sources["prelude"]
        + f"{HEREDOC}\n"
    )

    # The prelude holds the container open when it FAILS, and only then.  A
    # failed prelude is the run whose log matters most -- the discovery run
    # prints the measurements to paste into the policy there -- and an exited
    # container's log is unreadable.  It still exits non-zero afterwards, so
    # `service_completed_successfully` is not satisfied and the campaign
    # service is never started.
    entrypoint = (
        write_prelude
        + "status=0\n"
        f"python3 {PRELUDE_IN_CVM} \\\n"
        f"  --input-root {INPUT_ROOT} \\\n"
        f"  --evidence-root {EVIDENCE_ROOT} || status=$?\n"
        'if [ "$status" -ne 0 ]; then\n'
        '  echo "prelude FAILED with status $status; holding this container '
        'open so its log can be retrieved with \'phala cvms logs\'."\n'
        '  sleep "${TG_PRELUDE_FAILURE_HOLD_SECONDS}" || true\n'
        "fi\n"
        'exit "$status"\n'
    )

    campaign_entrypoint = (
        write_prelude
        + f"cat >{CAMPAIGN_ENTRY_IN_CVM} <<'{CAMPAIGN_HEREDOC}'\n"
        + sources["campaign entry point"]
        + f"{CAMPAIGN_HEREDOC}\n"
        + f"cat >{EVIDENCE_EMITTER_IN_CVM} <<'{EVIDENCE_HEREDOC}'\n"
        + sources["evidence emitter"]
        + f"{EVIDENCE_HEREDOC}\n"
        # Read-only, and invoked as `bash <file>` rather than executed: /tmp is
        # a tmpfs and Docker mounts tmpfs `noexec` unless told otherwise, so an
        # exec of it would fail with "Permission denied".  Keeping /tmp noexec
        # is worth more than the convenience.
        f"chmod 0400 {CAMPAIGN_ENTRY_IN_CVM}\n"
        # The app id and the app-compose hash cannot be literals in this
        # document (its own SHA-256 is the compose hash), so the prelude took
        # them from the guest agent, checked them against what RTMR3 attests,
        # and wrote them here.  A missing job scope is fatal to the campaign
        # but must not be fatal to the evidence: without it the entry point is
        # not run at all, and the evidence below is still printed.
        "status=0\n"
        "set -a\n"
        f". {INPUT_ROOT}/job-scope.env || status=$?\n"
        "set +a\n"
        'if [ "$status" -eq 0 ]; then\n'
        f"  bash {CAMPAIGN_ENTRY_IN_CVM} || status=$?\n"
        "else\n"
        f'  echo "no job scope at {INPUT_ROOT}/job-scope.env; the campaign was '
        'NOT run." >&2\n'
        "fi\n"
        # The evidence is printed whether or not the campaign succeeded: a
        # failed campaign still has a quote, an appraisal and a replay report
        # worth reading, and they are unreachable any other way.
        f"python3 {EVIDENCE_EMITTER_IN_CVM} \\\n"
        f"  --input-root {INPUT_ROOT} \\\n"
        f"  --evidence-root {EVIDENCE_ROOT} \\\n"
        f"  --output-root {OUTPUT_ROOT} \\\n"
        f"  --refuse-if-contains {KEY_ROOT}/enclave-signing-key.hex \\\n"
        '  --campaign-status "$status" || true\n'
        'echo "holding this container open so the evidence above can be '
        "retrieved with 'phala cvms logs'; extract it with "
        'tools/tg_phala_tdx_extract_evidence.py."\n'
        'sleep "${TG_EVIDENCE_HOLD_SECONDS}" || true\n'
        'exit "$status"\n'
    )

    return f"""# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT
#
# GENERATED BY tools/tg_phala_tdx_compose.py -- DO NOT EDIT BY HAND.
# Regenerate with `python3 tools/tg_phala_tdx_compose.py --template`;
# tests/test_phala_tdx_manifest.py fails if this file drifts.
#
# dstack application for the CH25 Lemma A.7 boundary campaign in an Intel TDX
# confidential VM.  Two one-shot services:
#
#   prelude   asks the dstack guest agent for the application identity,
#             derives the P-256 signing key, commits to its public key in the
#             TDX quote's report data, fetches the quote, appraises it with
#             the pinned dcap-qvl against the reviewed policy, replays the
#             event log against the quote, stages the retained A.7 artifact,
#             and writes the six non-secret files the campaign entry point
#             requires.  It is the only service with network access.  It does
#             NOT write the signing key anywhere.
#   campaign  re-derives the same signing key from the same dstack socket,
#             refusing unless it reproduces the report-data commitment the
#             quote attests; runs the replay; signs the receipt; prints all
#             the evidence to stdout; and stays alive so the log can be
#             fetched.  It starts ONLY on `service_completed_successfully`, so
#             a failed appraisal is not followed by a receipt.  No network,
#             read-only root filesystem.
#
# The image is referenced by registry digest, never by a tag.
#
# WHY THE SHARED VOLUME IS ORDINARY, AND MUST STAY ORDINARY
#
# A tmpfs-backed *named* volume is not shared between containers: each
# container that mounts it gets its own fresh, empty tmpfs.  The first real
# run on Phala TDX hardware passed the whole attestation and then died with
# `/workspace/staging/input/job-scope.env: No such file or directory` for
# exactly that reason.  `campaign-shared` is therefore an ordinary volume,
# and nothing secret is ever written to it.  Container-local secrets go on
# service-level `tmpfs:` entries, which really are private per container:
# that is where the re-derived signing key is written, and it dies with the
# container.
#
# WHY BOTH SERVICES MOUNT THE DSTACK SOCKET
#
# The key cannot travel between containers without touching disk, so it does
# not travel: each container derives it.  `GetKey` is a deterministic
# HKDF-SHA256 of the app key and the derivation path, and the campaign refuses
# to proceed unless what it derives reproduces the public key and report-data
# commitment the prelude put inside the quote.  The socket is not network
# access: the campaign service still has `network_mode: none`.
#
# WHY THE CAMPAIGN PRINTS ITS EVIDENCE AND THEN SLEEPS
#
# There is no other way to get bytes out of a dstack CVM.  Volumes are not
# reachable, and `phala cvms logs` returns nothing for a container that has
# exited.  A container that prints and then stays alive can be read.

services:
  prelude:
    image: {IMAGE}
    restart: "no"
    volumes:
      - /var/run/dstack.sock:/var/run/dstack.sock
      - campaign-shared:{SHARED_ROOT}
    environment:
      - SPARKINTERVAL_PHALA_TDX_WORKER_SCOPE=sparkinterval.phala-tdx-measured-worker.v1
      - SPARKINTERVAL_PHALA_TDX_WORKER_BACKEND=phala_dstack_tdx_cpu
      - SPARKINTERVAL_PHALA_TDX_WORKER_CHALLENGE_NONCE={challenge}
      - SPARKINTERVAL_PHALA_TDX_WORKER_JOB_BINDING_SHA256={job_binding}
      - TG_FINAL_IMAGE_REFERENCE={IMAGE_DIGEST}
      - TG_ISSUED_AT={issued_at}
      - TG_PRELUDE_FAILURE_HOLD_SECONDS={PRELUDE_FAILURE_HOLD_SECONDS}
      # Supplied as dstack encrypted environment, listed in allowed_envs.
      # They are deliberately NOT literals here: the appraisal policy pins
      # RTMR3, and RTMR3 is a function of these compose bytes, so a policy
      # embedded here could never be filled in.
      - TG_DCAP_QVL_POLICY_B64
      - TG_A7_ARTIFACT_URL
    entrypoint:
      - /bin/bash
      - -ec
      - |
{indent(compose_escape(entrypoint), 8)}
  campaign:
    image: {IMAGE}
    restart: "no"
    network_mode: none
    read_only: true
    depends_on:
      prelude:
        condition: service_completed_successfully
    volumes:
      # Read-only, and it carries nothing secret: the prelude writes no key.
      - campaign-shared:{SHARED_ROOT}:ro
      # Not network access.  The key is re-derived here rather than handed
      # over, because handing it over would mean writing it to a disk-backed
      # volume.
      - /var/run/dstack.sock:/var/run/dstack.sock
      - campaign-output:/workspace/out
    tmpfs:
      # Service-level tmpfs entries ARE private per container, which is the
      # whole point: the re-derived signing key lives here and nowhere else,
      # and the deriver refuses to write it to any non-tmpfs filesystem.
      - {KEY_ROOT}:size=1m,mode=0700
      - /workspace/runtime:exec,size=64m
      - /tmp:size=16m
    environment:
      - SPARKINTERVAL_PHALA_TDX_WORKER_SCOPE=sparkinterval.phala-tdx-measured-worker.v1
      - SPARKINTERVAL_PHALA_TDX_WORKER_BACKEND=phala_dstack_tdx_cpu
      - SPARKINTERVAL_PHALA_TDX_WORKER_CHALLENGE_NONCE={challenge}
      - SPARKINTERVAL_PHALA_TDX_WORKER_JOB_BINDING_SHA256={job_binding}
      - TG_FINAL_IMAGE_REFERENCE={IMAGE_DIGEST}
      - TG_ISSUED_AT={issued_at}
      - TG_INPUT_ROOT={INPUT_ROOT}
      - TG_OUTPUT_ROOT={OUTPUT_ROOT}
      - TG_ENCLAVE_KEY_ROOT={KEY_ROOT}
      - TG_PHALA_TDX_KEY_DERIVER={PRELUDE_IN_CVM}
      - TG_PRELUDE_SUMMARY={EVIDENCE_ROOT}/prelude-summary.json
      - TG_EVIDENCE_HOLD_SECONDS={EVIDENCE_HOLD_SECONDS}
    entrypoint:
      - /bin/bash
      - -ec
      - |
{indent(compose_escape(campaign_entrypoint), 8)}
volumes:
  # ORDINARY on purpose.  Never give this driver_opts type tmpfs: that makes
  # it per-container and empty, which is the bug this layout exists to fix.
  campaign-shared: {{}}
  campaign-output: {{}}
"""


def app_compose(compose_text: str) -> str:
    """Serialize exactly the way dstack's own ``vmm-cli.py`` does.

    ``compose_hash`` is the SHA-256 of these raw bytes -- there is no
    canonicalization step anywhere in dstack -- so key order, indentation and
    the absence of a trailing newline all matter.  The key set and the
    ``json.dumps(indent=4, ensure_ascii=False)`` call below mirror
    ``vmm/src/vmm-cli.py::create_app_compose`` at dstack v0.5.3 so that a hash
    computed here and a hash computed by dstack's tooling agree.

    ``no_instance_id`` is true on purpose: it removes the per-instance random
    value from the RTMR3 chain, which is what makes RTMR3 a function of the
    app id and the compose hash alone and therefore pinnable at all.
    """

    document = {
        "manifest_version": 2,
        "name": APP_NAME,
        "runner": "docker-compose",
        "docker_compose_file": compose_text,
        "kms_enabled": True,
        "gateway_enabled": False,
        "local_key_provider_enabled": False,
        "key_provider_id": "",
        "public_logs": False,
        "public_sysinfo": False,
        "allowed_envs": ["TG_DCAP_QVL_POLICY_B64", "TG_A7_ARTIFACT_URL"],
        "no_instance_id": True,
        "secure_time": True,
    }
    return json.dumps(document, indent=4, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--challenge")
    parser.add_argument("--job-binding")
    parser.add_argument("--issued-at")
    parser.add_argument(
        "--template",
        action="store_true",
        help="emit the committed template, whose challenge and job binding "
        "are refusal sentinels rather than valid hexadecimal",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--image",
        default=IMAGE,
        help="registry reference for the campaign image.  It must still be "
        f"pinned to {IMAGE_DIGEST}, so this changes only where the bytes are "
        "fetched from, never which bytes.  Use it when the default registry "
        "is not anonymously pullable by the CVM.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="write nothing; print the compose hash and app id",
    )
    args = parser.parse_args()

    if args.template:
        if args.challenge or args.job_binding or args.issued_at:
            parser.error("--template takes no challenge, binding or timestamp")
        challenge = TEMPLATE_CHALLENGE
        job_binding = TEMPLATE_JOB_BINDING
        issued_at = TEMPLATE_ISSUED_AT
    else:
        for name, value, pattern, shape in (
            ("--challenge", args.challenge, HEX64, "64 lowercase hex digits"),
            ("--job-binding", args.job_binding, HEX64, "64 lowercase hex digits"),
            ("--issued-at", args.issued_at, RFC3339, "an RFC 3339 UTC instant"),
        ):
            if not value or not pattern.match(value):
                parser.error(f"{name} must be {shape}")
        if args.challenge == args.job_binding:
            parser.error("--challenge and --job-binding must differ")
        challenge = args.challenge
        job_binding = args.job_binding
        issued_at = args.issued_at

    compose_text = compose_yaml(
        challenge=challenge, job_binding=job_binding, issued_at=issued_at,
        IMAGE=args.image,
    )
    document = app_compose(compose_text)
    compose_hash = hashlib.sha256(document.encode("utf-8")).hexdigest()

    if not args.print_only:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "docker-compose.yaml").write_text(
            compose_text, encoding="utf-8"
        )
        (args.out_dir / "app-compose.json").write_text(document, encoding="utf-8")

    print(f"app-compose.json sha256 (compose_hash) : {compose_hash}")
    print(f"app id (first 20 bytes)                : {compose_hash[:40]}")
    print(f"image                                  : {args.image}")
    if args.template:
        print(
            "TEMPLATE: the challenge and job binding are refusal sentinels; "
            "the campaign guard rejects them."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
