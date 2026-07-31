#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Generate the dstack deploy manifest for the per-integer leancompcert campaign.

This is the sibling of ``tools/tg_phala_tdx_compose.py``.  That generator
deploys the CH25 Lemma A.7 FLINT/Arb replay; this one deploys
``platt-stronger-range-live``: ten statically linked, freestanding,
CompCert-compiled x86_64 artifacts that test
``|Σ_{m≤n} μ(m)/m| ≤ 1/(2√(n+1))`` at **every** integer ``n`` in
``[5, 7 727 068 586]``, chained through a two-limb accumulator at scale
``2^78``.

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

* ``proof_build/leancompcert_tdx/prelude_live_tdx_inputs.py`` -- run by the
  prelude service to stage the inputs, and run again by the campaign service,
  in ``--derive-key-only`` mode, to re-derive the signing key;
* ``proof_build/leancompcert_tdx/run_seg_campaign.sh`` -- the campaign entry
  point, which runs the chain and signs the receipt;
* ``proof_build/leancompcert_tdx/emit_live_tdx_evidence.py`` -- prints the
  evidence to stdout at the end.

What the *image* contributes is the campaign itself: the manifest, the ten
artifacts, the emitted C they were compiled from, ``tg_verifier`` and the
campaign pre-checker.  It is pinned here by registry digest, and the digest of
the manifest is named inside the registered algorithm's ``canonicalDefinition``
and therefore inside ``TG_ALGORITHM_HASH`` below, which the enclave signs.  A
substituted campaign changes that digest and the Lean acceptance check
refuses.

Everything the A.7 generator's docstring says about the shared volume, the
socket, the ``$$`` escaping and the print-then-sleep discipline applies here
unchanged, and for the same reasons.  The one structural difference is that
there is **no artifact to fetch**: the campaign is in the image, so the
prelude's only network use is the pinned ``dcap-qvl`` download.

Usage
-----

Committed template (challenge and job binding are refusal sentinels)::

    python3 tools/tg_phala_tdx_live_compose.py --template

A real deployment::

    python3 tools/tg_phala_tdx_live_compose.py \\
        --challenge <64 hex, unpredictable, chosen before the run> \\
        --job-binding <64 hex> \\
        --issued-at 2026-07-31T00:00:00Z \\
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
BUILD = ROOT / "proof_build/leancompcert_tdx"
PRELUDE = BUILD / "prelude_live_tdx_inputs.py"
CAMPAIGN_ENTRY = BUILD / "run_seg_campaign.sh"
EVIDENCE_EMITTER = BUILD / "emit_live_tdx_evidence.py"
DEFAULT_OUT_DIR = BUILD

PRELUDE_IN_CVM = "/tmp/prelude_live_tdx_inputs.py"
CAMPAIGN_ENTRY_IN_CVM = "/tmp/run_seg_campaign.sh"
EVIDENCE_EMITTER_IN_CVM = "/tmp/emit_live_tdx_evidence.py"

SHARED_ROOT = "/workspace/shared"
INPUT_ROOT = SHARED_ROOT + "/input"
EVIDENCE_ROOT = SHARED_ROOT + "/evidence"
OUTPUT_ROOT = "/workspace/out/output"
KEY_ROOT = "/workspace/keys"

EVIDENCE_HOLD_SECONDS = 86400
PRELUDE_FAILURE_HOLD_SECONDS = 86400

# ---------------------------------------------------------------------------
# The campaign pin.  Every literal below is machine-derived by
# `proof_build/leancompcert_tdx/build_live_campaign.py` and reproduced in
# `SparkInterval/Execution/RegisteredAlgorithm.lean`.
# ---------------------------------------------------------------------------
CAMPAIGN_NAME = "platt-stronger-range-live"
ALGORITHM_ID = "sparkinterval.leancompcert.platt-stronger-range-live.v1"
ALGORITHM_HASH = "7080938bc1af83e75b1c273e6388916741250422d964ac734e5b638ab61386c2"
PARAMETERS_HASH = "8c8166cce5f1b071deb1ab977549fc9364d1787309055650e458e431eac8b9b0"
DOMAIN_HASH = "e5a470a3565f520b333f6fd7c2b400c12121fd5a17f77452dbb6efd0667410d4"
MANIFEST_SHA256 = "6c67c2a900889087d3c1f88eed9caecf4e08ba0c40ab23e83ef316ff0d7ef0a9"

APP_NAME = "sparkinterval-platt-stronger-range-live"
HEREDOC = "SPARKINTERVAL_PRELUDE_SOURCE_EOF"
CAMPAIGN_HEREDOC = "SPARKINTERVAL_CAMPAIGN_ENTRY_EOF"
EVIDENCE_HEREDOC = "SPARKINTERVAL_EVIDENCE_EMITTER_EOF"

TEMPLATE_CHALLENGE = "REPLACE-WITH-64-HEX-UNPREDICTABLE-CHALLENGE-NONCE"
TEMPLATE_JOB_BINDING = "REPLACE-WITH-64-HEX-JOB-BINDING-SHA256"
TEMPLATE_ISSUED_AT = "REPLACE-WITH-RFC3339-UTC-INSTANT"

HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
RFC3339 = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")

IMAGE_DIGEST = (
    "sha256:e58fd209cb294db396633c3645d15a01e5717a0d4fe914e25d5b892c3adbab54"
)
# The permanent home of these exact bytes.  `--image` may name a different
# registry host for the deployment -- the CVM has to be able to pull
# anonymously, and a GHCR user package cannot be made public except through
# GitHub's web UI -- but `compose_yaml` refuses any reference that does not
# carry `IMAGE_DIGEST`, so a different host can never mean different bytes.
PERMANENT_IMAGE = "ghcr.io/gersh/sparkinterval-platt-live-phala-tdx@" + IMAGE_DIGEST
IMAGE = PERMANENT_IMAGE


def compose_escape(text: str) -> str:
    """Protect an embedded shell script from Compose's own interpolation.

    Compose expands ``$VAR`` in the compose file *before* the container sees
    it, and aborts on ``${VAR:?message}`` when VAR is unset in the deploying
    shell -- and ``run_seg_campaign.sh`` is full of exactly that form.
    Nothing in these blocks is ever meant to be interpolated by Compose, so
    every ``$`` is doubled; ``$$`` reaches the container as a literal ``$``.
    """
    return text.replace("$", "$$")


def indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "".join(
        pad + line if line.strip() else line for line in text.splitlines(True)
    )


def compose_yaml(*, challenge: str, job_binding: str, issued_at: str,
                 IMAGE: str = IMAGE) -> str:
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
        f"chmod 0400 {CAMPAIGN_ENTRY_IN_CVM}\n"
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
# GENERATED BY tools/tg_phala_tdx_live_compose.py -- DO NOT EDIT BY HAND.
#
# dstack application for the per-integer leancompcert campaign
# `platt-stronger-range-live` in an Intel TDX confidential VM.  Ten
# statically linked, freestanding, CompCert-compiled x86_64 executables -- no
# libc, no analytic stack, nothing fetched over the network -- run in chain
# order, each seeded with the previous link's two-limb carry, testing
# `|sum_{{m<=n}} mu(m)/m| <= 1/(2 sqrt(n+1))` at EVERY integer n in
# [5, 7727068586].
#
# Two one-shot services:
#
#   prelude   asks the dstack guest agent for the application identity,
#             derives the P-256 signing key, commits to its public key in the
#             TDX quote's report data, fetches the quote, appraises it with
#             the pinned dcap-qvl against the reviewed policy, replays the
#             event log against the quote, writes the registered input, and
#             hands over the five files the entry point requires.  It is the
#             only service with network access, and its only network use is
#             the pinned dcap-qvl download.  It does NOT write the signing
#             key anywhere.
#   campaign  re-derives the same signing key from the same dstack socket,
#             refusing unless it reproduces the report-data commitment the
#             quote attests; verifies the campaign manifest against the digest
#             named inside `algorithmHash`; runs the ten artifacts in chain
#             order; signs the receipt; prints all the evidence to stdout; and
#             stays alive so the log can be fetched.  It starts ONLY on
#             `service_completed_successfully`, so a failed appraisal is not
#             followed by a receipt.  No network, read-only root filesystem.
#
# The image is referenced by registry digest, never by a tag.
#
# WHERE THESE IMAGE BYTES PERMANENTLY LIVE
#
# The same manifest digest is held permanently at
# `ghcr.io/gersh/sparkinterval-platt-live-phala-tdx@{IMAGE_DIGEST}`.
# The reference in the `image:` lines below may be a different registry host,
# because a dstack CVM has to pull anonymously and a GitHub user-scoped
# container package cannot be made public through any API -- only through
# GitHub's web UI, which is not available to the process that built this.  The
# generator refuses any reference that does not carry exactly that digest, so
# the host is a delivery detail and the digest is the identity.  This comment
# is inside the compose document, hence inside the compose hash, hence inside
# RTMR3.
#
# WHY THE SHARED VOLUME IS ORDINARY, AND MUST STAY ORDINARY
#
# A tmpfs-backed *named* volume is not shared between containers: each
# container that mounts it gets its own fresh, empty tmpfs.  `campaign-shared`
# is therefore an ordinary volume, and nothing secret is ever written to it.
# Container-local secrets go on service-level `tmpfs:` entries, which really
# are private per container: that is where the re-derived signing key is
# written, and it dies with the container.
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
      # Deliberately NOT a literal here: the appraisal policy pins RTMR3, and
      # RTMR3 is a function of these compose bytes, so a policy embedded here
      # could never be filled in.
      - TG_DCAP_QVL_POLICY_B64
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
      # The campaign identity.  `TG_ALGORITHM_HASH` is the SHA-256 of the
      # registered algorithm's canonicalDefinition, which names
      # `TG_MANIFEST_SHA256`; the entry point refuses unless the manifest in
      # the image hashes to exactly that.
      - TG_ALGORITHM_ID={ALGORITHM_ID}
      - TG_ALGORITHM_HASH={ALGORITHM_HASH}
      - TG_PARAMETERS_HASH={PARAMETERS_HASH}
      - TG_DOMAIN_HASH={DOMAIN_HASH}
      - TG_CAMPAIGN_NAME={CAMPAIGN_NAME}
      - TG_MANIFEST_SHA256={MANIFEST_SHA256}
      - TG_CAMPAIGN_ROOT=/opt/sparkinterval/campaign
      - TG_CAMPAIGN_CHECKER=/opt/sparkinterval/tg_seg_campaign_check.py
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
    the absence of a trailing newline all matter.

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
        "allowed_envs": ["TG_DCAP_QVL_POLICY_B64"],
        "no_instance_id": True,
        "secure_time": True,
    }
    return json.dumps(document, indent=4, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--challenge")
    parser.add_argument("--job-binding")
    parser.add_argument("--issued-at")
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--image", default=IMAGE)
    args = parser.parse_args()

    if args.template:
        if args.challenge or args.job_binding or args.issued_at:
            parser.error("--template takes no challenge, binding or timestamp")
        challenge = TEMPLATE_CHALLENGE
        job_binding = TEMPLATE_JOB_BINDING
        issued_at = TEMPLATE_ISSUED_AT
    else:
        for name, value, pattern in (
            ("--challenge", args.challenge, HEX64),
            ("--job-binding", args.job_binding, HEX64),
            ("--issued-at", args.issued_at, RFC3339),
        ):
            if not value or not pattern.fullmatch(value):
                parser.error(f"{name} is required and must match {pattern.pattern}")
        if args.challenge == args.job_binding:
            parser.error("the challenge and the job binding must differ")
        challenge = args.challenge
        job_binding = args.job_binding
        issued_at = args.issued_at

    for label, value in (("ALGORITHM_HASH", ALGORITHM_HASH),
                         ("PARAMETERS_HASH", PARAMETERS_HASH),
                         ("DOMAIN_HASH", DOMAIN_HASH),
                         ("MANIFEST_SHA256", MANIFEST_SHA256),
                         ("IMAGE_DIGEST", IMAGE_DIGEST[7:])):
        if not HEX64.fullmatch(value):
            raise SystemExit(f"{label} is still a placeholder: {value}")

    compose = compose_yaml(challenge=challenge, job_binding=job_binding,
                           issued_at=issued_at, IMAGE=args.image)
    document = app_compose(compose)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "docker-compose.yaml").write_text(compose, encoding="utf-8")
    (args.out_dir / "app-compose.json").write_text(document, encoding="utf-8")
    digest = hashlib.sha256(document.encode("utf-8")).hexdigest()
    # This is the compose hash *of the document above*.  When the deployment
    # is driven by the `phala` CLI, the CLI builds its own app-compose
    # document from `docker-compose.yaml`, so the authoritative compose hash
    # is the one the guest agent reports and RTMR3 attests -- which the
    # prelude checks against each other, and which the Lean pin records.  The
    # app id is assigned by the KMS and is not a prefix of either.
    print(f"local app-compose.json sha256 = {digest}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
