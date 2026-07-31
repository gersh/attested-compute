#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Derive the Lean enclave pin and receipt literals from a retained TDX run.

A 130-character public key and a 128-character signature that a human retyped
are exactly how the wrong enclave gets pinned, and a wrong pin is not a build
failure -- it is a silently trusted stranger.  So nothing on this path is
transcribed.  This tool reads the evidence directory that
``tools/tg_phala_tdx_extract_evidence.py`` wrote, re-derives every literal
from the retained bytes, refuses if anything disagrees, and prints the Lean
module.

Usage::

    python3 tools/tg_phala_tdx_pin_from_evidence.py \\
        --evidence-dir tests/data/phala_tdx_prod5 \\
        --out SparkInterval/Execution/PhalaTdxProd5Evidence.lean

    python3 tools/tg_phala_tdx_pin_from_evidence.py \\
        --evidence-dir tests/data/phala_tdx_prod5 --check

``--check`` compares the committed module against what this tool would emit
and exits non-zero on any difference; ``tests/test_phala_tdx_prod5_pin.py``
runs it that way.

More than one deployment is attested, so everything that names a particular
one -- the Lean module, the namespace, the pin identifiers, the enclave
constructors the generated theorems talk about, the campaign's own evidence
files and the prose -- is collected in a *profile*.  ``--profile`` selects it
and supplies the default ``--evidence-dir`` and ``--out``::

    python3 tools/tg_phala_tdx_pin_from_evidence.py --profile live --check

The verification below is deployment-independent: it reads nothing from the
profile except the list of campaign files it must find.

What is re-derived, and what is only cross-checked
-------------------------------------------------

Re-derived from bytes:

* the SHA-256 of every retained input and output file, compared against both
  the evidence manifest and the enclave's *signed* statement fields;
* the canonical signed payload and its SHA-256, recomputed from the signed
  fields by ``tg_verifier.phala_tdx_receipt`` -- the same construction the
  Lean module mirrors -- and compared against the receipt's claim;
* the enclave's P-256 signature over that digest, verified against the
  enclave's own public key with the reference verifier;
* the TDX quote report-data commitment, recomputed from the public key, the
  challenge and the job binding, and compared against the signed field.

Cross-checked between independent files (any disagreement is fatal):

* the app id and the app-compose hash, which must agree across the signed
  receipt, ``input/job-scope.env``, ``evidence/prelude-summary.json`` and the
  RTMR3 event-log replay in ``evidence/rtmr-replay.json``;
* the image digest and the enclave public key, between the signed receipt and
  the prelude summary;
* the challenge nonce, job binding and issue time, against the run scope that
  was chosen before the run.

What this tool does **not** do is verify the TDX quote.  ``dcap-qvl`` did that
inside the CVM; only the retained appraisal's digests enter here.  Nor does it
decide whether a deployment deserves to be trusted.  It emits the literals;
setting ``attestationAuthority := true`` for the enclave identity that carries
them is a separate, deliberate source edit in
``SparkInterval/Execution/PhalaTdxAttestation.lean``, and the generated module
proves by ``decide`` that the two copies agree.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
import textwrap
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.phala_tdx_receipt import (  # noqa: E402
    SIGNED_FIELDS,
    report_data_hash,
    statement_digest,
    verify_digest_hex,
)


LOWER_HEX = frozenset("0123456789abcdef")

TD_REPORT_OFFSET = 48
TD_REPORT_SIZE = 584
MR_CONFIG_ID_OFFSET = TD_REPORT_OFFSET + 184
REPORT_DATA_OFFSET = TD_REPORT_OFFSET + 520

# The one field of the signed statement that no check other than the signature
# itself looks at.  Altering it changes the statement digest and nothing else,
# which is what makes it the sharp test of the in-Lean ECDSA verifier.
DIGEST_ONLY_TAMPER_FIELD = "issued_at"


# ---------------------------------------------------------------------------
# Deployment profiles
# ---------------------------------------------------------------------------
#
# A profile holds every string that names one deployment rather than the
# attestation machinery: where its evidence lives, what Lean module and
# namespace it becomes, the pin identifiers, the `PhalaTdxEnclave`
# constructors the generated theorems mention, which campaign-specific files
# the run must have left behind, and the module prose.  Nothing here is
# consulted by the signature, report-data or cross-file checks; adding a
# deployment cannot weaken them.


@dataclass(frozen=True)
class Profile:
    """One attested deployment: its evidence on disk and its Lean names."""

    # The profile's own name, as `--profile` spells it.
    name: str
    # The Lean module the emitted text declares, and where it is written.
    module_name: str
    out_path: str
    # Repository-relative directory holding `run-scope.txt` and
    # `retained-evidence/`.  Also quoted in the emitted prose.
    evidence_path: str
    # The namespace the generated `pin`, `receipt` and tamper literals sit in.
    # The declaration names inside it are the same for every deployment.
    namespace: str
    pin_id: str
    negative_pin_id: str
    # `PhalaTdxEnclave` constructors: the pinned identity, its tampered-key
    # negative-test twin, and the deliberately empty production slot the
    # generated module proves is still unreachable.
    enclave: str
    tampered_enclave: str
    unpinned_enclave: str
    # Prefix shared by every generated theorem name.
    theorem_prefix: str
    # The Lean test module that consumes the negative-test fixture.
    run_test_module: str
    # Files, relative to `retained-evidence/`, that this campaign must have
    # produced.  The evidence manifest also lists them, but a manifest is
    # written by the run itself; this is the generator's own expectation of
    # what the campaign is.
    campaign_files: tuple[str, ...]
    # Doc comments that name the deployment rather than the check: the one on
    # `pin`, the one on the trust-boundary flag, and the one on the
    # "production pin is still unpinned" theorem.
    pin_doc: str
    authority_theorem_doc: str
    unpinned_theorem_doc: str
    # Builds the module header, given the derived data and the signed fields.
    header: Callable[[dict, dict], str]


def _prod5_header(data: dict, fields: dict) -> str:
    """The prod5 module prose, unchanged since the deployment was pinned."""

    return f"""\
# The Phala prod5 CH25 Lemma A.7 enclave pin and receipt, as literals

**GENERATED BY `tools/tg_phala_tdx_pin_from_evidence.py` -- DO NOT EDIT BY
HAND.**  Regenerate with

```
python3 tools/tg_phala_tdx_pin_from_evidence.py \\
    --evidence-dir tests/data/phala_tdx_prod5 \\
    --out SparkInterval/Execution/PhalaTdxProd5Evidence.lean
```

`tests/test_phala_tdx_prod5_pin.py` fails if this file drifts from the
evidence, and the generator refuses to emit anything unless the enclave's
signature verifies, the report-data commitment binds the quote to that key,
and the app id and app-compose hash agree across the signed receipt, the job
scope, the prelude summary and the RTMR3 event-log replay.

## Which deployment this is

One run, and only one:

* Phala Cloud **prod5**, CVM `a7-e2e`, Intel TDX, {fields['issued_at']}.
* dstack application id `{data['app_id']}`,
  instance `{data['instance_id']}`.
* app-compose hash
  `{data['compose_hash']}`,
  measured into RTMR3 and reproduced by replaying the retained dstack event
  log.
* OCI image `{data['image_digest']}`.
* `MRTD` `{data['mr_td']}`.
* `dcap-qvl v0.6.1` appraised the retained quote against the reviewed policy
  and reported `Quote verified`, TCB `UpToDate`, no advisories.
* {data['strict_note']}

The retained evidence is committed at `tests/data/phala_tdx_prod5/`.

## What the literals below do and do not license

`ch25A7BoundaryPhalaProd5V1` carries `attestationAuthority := true`.  That is
the project's trust-boundary statement about **this deployment and no other**:
that the P-256 public key below was derived by dstack inside that TD and never
left it.  It licenses nothing about any other app id, any other image, or any
future run of the same image on a different platform, and it does not make the
still-unpinned `ch25A7BoundaryProductionV1` reachable.

`ch25A7BoundaryPhalaProd5TamperedKeyV1` is the same pin with one hexadecimal
digit of the public key changed.  It exists only so that
`SparkInterval/Tests/PhalaTdxProd5RunTest.lean` can state, as a Lean theorem,
that the acceptance check *rejects* it.  It carries no attestation authority.\
"""


def _live_header(data: dict, fields: dict) -> str:
    """The live-campaign module prose, derived from the retained evidence.

    Every deployment coordinate quoted here -- the issue time, the app id, the
    compose hash, the image digest, the MRTD -- comes from the same values the
    checks above re-derived, so the prose cannot describe a different run from
    the one the literals pin.
    """

    return f"""\
# The Phala `platt-stronger-range-live` enclave pin and receipt, as literals

**GENERATED BY `tools/tg_phala_tdx_pin_from_evidence.py` -- DO NOT EDIT BY
HAND.**  Regenerate with

```
python3 tools/tg_phala_tdx_pin_from_evidence.py --profile live \\
    --evidence-dir tests/data/phala_tdx_live \\
    --out SparkInterval/Execution/PhalaTdxLiveCampaignEvidence.lean
```

Adding `--check` to that command fails if this file drifts from the evidence,
and the generator refuses to emit anything unless the enclave's signature
verifies, the report-data commitment binds the quote to that key, and the app
id and app-compose hash agree across the signed receipt, the job scope, the
prelude summary and the RTMR3 event-log replay.

## Which deployment this is

One run, and only one:

* Phala Cloud, Intel TDX, {fields['issued_at']}.
* dstack application id `{data['app_id']}`,
  instance `{data['instance_id']}`.
* app-compose hash
  `{data['compose_hash']}`,
  measured into RTMR3 and reproduced by replaying the retained dstack event
  log.
* OCI image `{data['image_digest']}`.
* `MRTD` `{data['mr_td']}`.
* `dcap-qvl v0.6.1` appraised the retained quote against the reviewed policy
  and reported `Quote verified`, TCB `UpToDate`, no advisories.
* {data['strict_note']}

The retained evidence is committed at `tests/data/phala_tdx_live/`.

## What ran inside the TD

The `platt-stronger-range-live` campaign: ten CompCert-compiled freestanding
x86_64 artifacts, run one after another, which between them test

```
|sum_{{m <= n}} mu(m)/m| <= 1/(2 sqrt(n+1))
```

at every integer n in [5, 7727068586].  `output/work/campaign-run.json`
records how many links ran and what each returned,
`output/work/window-status.txt` the per-link detail behind it, and
`output/work/campaign-precheck.json` the artifact-manifest check the entry
point ran before anything executed.  The signed `result` field is the verdict
those three files stand behind, and its digest is `outputHash` below.

## What the literals below do and do not license

`plattStrongerRangeLivePhalaV1` carries `attestationAuthority := true`.  That
is the project's trust-boundary statement about **this deployment and no
other**: that the P-256 public key below was derived by dstack inside that TD
and never left it.  It licenses nothing about any other app id, any other
image, or any future run of the same image on a different platform, and it
does not make the still-unpinned `ch25A7BoundaryProductionV1` reachable.

`plattStrongerRangeLiveTamperedKeyV1` is the same pin with one hexadecimal
digit of the public key changed.  It exists only so that
`SparkInterval/Tests/PhalaTdxLiveCampaignRunTest.lean` can state, as a Lean
theorem, that the acceptance check *rejects* it.  It carries no attestation
authority."""


PROFILES: dict[str, Profile] = {
    "prod5": Profile(
        name="prod5",
        module_name="SparkInterval.Execution.PhalaTdxProd5Evidence",
        out_path="SparkInterval/Execution/PhalaTdxProd5Evidence.lean",
        evidence_path="tests/data/phala_tdx_prod5",
        namespace="PhalaTdxProd5",
        pin_id="sparkinterval.phala-tdx.ch25-a7-boundary.phala-prod5.v1",
        negative_pin_id=(
            "sparkinterval.phala-tdx.ch25-a7-boundary.prod5-negative-test.v1"
        ),
        enclave="ch25A7BoundaryPhalaProd5V1",
        tampered_enclave="ch25A7BoundaryPhalaProd5TamperedKeyV1",
        unpinned_enclave="ch25A7BoundaryProductionV1",
        theorem_prefix="phalaTdxProd5_",
        run_test_module="SparkInterval/Tests/PhalaTdxProd5RunTest.lean",
        campaign_files=("output/work/a7-replay.json",),
        pin_doc=(
            "/-- The reviewed pin literals for the Phala prod5 deployment, "
            "derived from\n`tests/data/phala_tdx_prod5/` rather than "
            "transcribed. -/"
        ),
        authority_theorem_doc=(
            "/-- **The trust-boundary flag.**  This is the one deployment the "
            "project\ntreats as an Intel TDX attestation authority. -/"
        ),
        unpinned_theorem_doc=(
            "/-- Installing the prod5 identity left the older, deliberately "
            "empty\nproduction pin exactly as it was: still unreachable. -/"
        ),
        header=_prod5_header,
    ),
    "live": Profile(
        name="live",
        module_name="SparkInterval.Execution.PhalaTdxLiveCampaignEvidence",
        out_path="SparkInterval/Execution/PhalaTdxLiveCampaignEvidence.lean",
        evidence_path="tests/data/phala_tdx_live",
        namespace="PhalaTdxLiveCampaign",
        pin_id="sparkinterval.phala-tdx.platt-stronger-range-live.phala.v1",
        negative_pin_id=(
            "sparkinterval.phala-tdx.platt-stronger-range-live."
            "negative-test.v1"
        ),
        enclave="plattStrongerRangeLivePhalaV1",
        tampered_enclave="plattStrongerRangeLiveTamperedKeyV1",
        unpinned_enclave="ch25A7BoundaryProductionV1",
        theorem_prefix="phalaTdxLiveCampaign_",
        run_test_module=(
            "SparkInterval/Tests/PhalaTdxLiveCampaignRunTest.lean"
        ),
        campaign_files=(
            "output/work/campaign-run.json",
            "output/work/window-status.txt",
            "output/work/campaign-precheck.json",
        ),
        pin_doc=(
            "/-- The reviewed pin literals for the "
            "`platt-stronger-range-live` deployment,\nderived from "
            "`tests/data/phala_tdx_live/` rather than transcribed. -/"
        ),
        authority_theorem_doc=(
            "/-- **The trust-boundary flag.**  The project treats this "
            "deployment as an\nIntel TDX attestation authority. -/"
        ),
        unpinned_theorem_doc=(
            "/-- Installing the live-campaign identity left the older, "
            "deliberately empty\nproduction pin exactly as it was: still "
            "unreachable. -/"
        ),
        header=_live_header,
    ),
}

DEFAULT_PROFILE = PROFILES["prod5"]

# Kept for callers that import the prod5 constants by name.
MODULE_NAME = DEFAULT_PROFILE.module_name
DEFAULT_OUT = ROOT / DEFAULT_PROFILE.out_path
DEFAULT_EVIDENCE = ROOT / DEFAULT_PROFILE.evidence_path
PIN_ID = DEFAULT_PROFILE.pin_id
NEGATIVE_PIN_ID = DEFAULT_PROFILE.negative_pin_id


class PinError(RuntimeError):
    """The evidence directory is not a self-consistent, verified TDX run."""


def _fail(message: str) -> None:
    raise PinError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lower_hex(value: object, length: int, what: str) -> str:
    if not isinstance(value, str):
        _fail(f"{what} is not a string")
    assert isinstance(value, str)
    if len(value) != length or any(c not in LOWER_HEX for c in value):
        _fail(
            f"{what} is not {length} lowercase hexadecimal digits: {value!r}"
        )
    return value


def _alter_one_character(value: str) -> str:
    """Return `value` with exactly one character deterministically changed.

    The rightmost hexadecimal digit is used, so a digest, a key, a signature
    and a timestamp are all handled by the same rule and the result is stable
    across regenerations.
    """

    for index in range(len(value) - 1, -1, -1):
        character = value[index]
        if character in LOWER_HEX:
            replacement = "0" if character != "0" else "1"
            return value[:index] + replacement + value[index + 1:]
    _fail(f"cannot alter a character of {value!r}")
    raise AssertionError("unreachable")


def _read_json(path: Path) -> dict:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PinError(f"cannot read {path}: {error}") from error
    if not isinstance(loaded, dict):
        _fail(f"{path} is not a JSON object")
    return loaded


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip()
    return values


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def load_evidence(evidence_dir: Path, profile: Profile | None = None) -> dict:
    """Re-derive every pin and receipt literal, or refuse.

    `profile` names the deployment; it supplies the pin identifiers and the
    campaign files this run must have left behind, and nothing else.  Every
    cryptographic check below is the same for any deployment.
    """

    if profile is None:
        profile = DEFAULT_PROFILE
    evidence_dir = evidence_dir.resolve()
    retained = evidence_dir / "retained-evidence"
    if not retained.is_dir():
        retained = evidence_dir
    scope_path = evidence_dir / "run-scope.txt"
    if not scope_path.is_file():
        scope_path = retained.parent / "run-scope.txt"
    _require(scope_path.is_file(), f"no run-scope.txt beside {retained}")

    # --- the evidence manifest, and the campaign's own exit status ----------
    manifest = _read_json(retained / "evidence-manifest.json")
    _require(
        manifest.get("kind") == "sparkinterval.phala-tdx-evidence-manifest.v1",
        "the evidence manifest is not the expected kind",
    )
    _require(
        manifest.get("campaign_exit_status") == 0,
        "the campaign did not exit 0; this run must not be pinned",
    )
    _require(
        manifest.get("missing_required") == [],
        f"the run is missing required evidence: "
        f"{manifest.get('missing_required')!r}",
    )
    for entry in manifest.get("files", []):
        if not entry.get("required", False) and not entry.get("present", False):
            continue
        path = retained / entry["root"] / entry["name"]
        _require(path.is_file(), f"the manifest lists a missing file {path}")
        actual = _sha256_file(path)
        _require(
            actual == entry["sha256"],
            f"{path} has sha256 {actual}, the manifest states "
            f"{entry['sha256']}",
        )

    # --- the campaign this profile names really ran -------------------------
    #
    # The manifest lists these files too, but the manifest is written by the
    # run itself.  Requiring them here is the generator's own statement of
    # which workload it is willing to pin: evidence from some other campaign
    # does not become this deployment by being handed to `--profile`.
    for relative in profile.campaign_files:
        _require(
            (retained / relative).is_file(),
            f"the {profile.name} campaign left no {relative}",
        )

    # --- the enclave receipt ------------------------------------------------
    receipt = _read_json(retained / "output/enclave-receipt.json")
    _require(
        receipt.get("kind") == "sparkinterval.phala-tdx-attested-run.v1",
        "the receipt is not a Phala TDX attested-run receipt",
    )
    _require(
        receipt.get("local_dry_run") is not True,
        "the receipt is flagged as a local dry run and must never be pinned",
    )
    fields = receipt.get("signed_fields")
    _require(isinstance(fields, dict), "the receipt has no signed fields")
    assert isinstance(fields, dict)
    _require(
        sorted(fields) == sorted(SIGNED_FIELDS),
        "the receipt's signed fields are not exactly the canonical set",
    )

    public_key = _lower_hex(
        receipt.get("enclave_public_key"), 130, "the enclave public key"
    )
    _require(
        public_key.startswith("04"),
        "the enclave public key is not a SEC1 uncompressed point",
    )
    signature = _lower_hex(
        receipt.get("signature"), 128, "the enclave signature"
    )

    # --- the signature, over the recomputed statement ----------------------
    digest = statement_digest(fields)
    _require(
        receipt.get("statement_sha256") == digest,
        f"the receipt claims statement digest "
        f"{receipt.get('statement_sha256')!r} but the canonical payload "
        f"hashes to {digest}",
    )
    _require(
        verify_digest_hex(public_key, digest, signature),
        "THE ENCLAVE SIGNATURE DOES NOT VERIFY over the recomputed "
        "statement; refusing to emit a pin",
    )

    # --- the report-data commitment ----------------------------------------
    recomputed_report_data = report_data_hash(
        enclave_public_key_hex=public_key,
        challenge_nonce=fields["challenge_nonce"],
        job_binding=fields["job_binding_sha256"],
    )
    _require(
        recomputed_report_data == fields["report_data_sha256"],
        "the signed report-data digest does not commit to this public key, "
        "challenge and job binding; the quote and the signature may come "
        "from unrelated parties",
    )

    # --- the signed digests really are the retained files ------------------
    for field, relative in (
        ("tdx_quote_sha256", "input/tdx-quote.bin"),
        ("dcap_qvl_output_sha256", "input/dcap-qvl-appraisal.json"),
        ("dcap_qvl_policy_sha256", "input/dcap-qvl-policy.json"),
        ("dcap_qvl_artifact_sha256", "input/dcap-qvl-artifact.sha256"),
        ("input_hash", "input/registered-input.json"),
        ("output_hash", "output/registered-result.txt"),
    ):
        actual = _sha256_file(retained / relative)
        _require(
            actual == fields[field],
            f"signed field {field} is {fields[field]} but {relative} hashes "
            f"to {actual}",
        )
    _require(
        (retained / "output/registered-result.txt").read_bytes()
        == fields["result"].encode("utf-8"),
        "the retained result bytes are not the signed result",
    )
    _require(
        fields["result"] == "true",
        f"the campaign result is {fields['result']!r}, not the success bytes",
    )
    _require(
        hashlib.sha256(fields["result"].encode("utf-8")).hexdigest()
        == fields["output_hash"],
        "the signed output digest is not the digest of the signed result",
    )

    # --- the run scope was fixed before the run ----------------------------
    scope = _read_env(scope_path)
    for scope_key, field in (
        ("challenge", "challenge_nonce"),
        ("job_binding", "job_binding_sha256"),
        ("issued_at", "issued_at"),
    ):
        _require(
            scope.get(scope_key) == fields[field],
            f"run scope {scope_key}={scope.get(scope_key)!r} does not match "
            f"the signed {field}={fields[field]!r}",
        )

    # --- the deployment coordinates, from four independent files -----------
    job_scope = _read_env(retained / "input/job-scope.env")
    prelude = _read_json(retained / "evidence/prelude-summary.json")
    rtmr = _read_json(retained / "evidence/rtmr-replay.json")
    bindings = rtmr.get("rtmr3_bindings")
    _require(
        isinstance(bindings, dict),
        "the RTMR3 replay records no boot-chain bindings",
    )
    assert isinstance(bindings, dict)

    app_id = _lower_hex(fields["app_id"], 40, "the signed app id")
    compose_hash = _lower_hex(
        fields["compose_hash"], 64, "the signed app-compose hash"
    )
    for label, observed in (
        ("input/job-scope.env", job_scope.get(
            "SPARKINTERVAL_PHALA_TDX_WORKER_APP_ID")),
        ("evidence/prelude-summary.json", prelude.get("app_id")),
        ("evidence/rtmr-replay.json", bindings.get("app-id")),
    ):
        _require(
            observed == app_id,
            f"{label} reports app id {observed!r}, the signed receipt says "
            f"{app_id!r}",
        )
    for label, observed in (
        ("input/job-scope.env", job_scope.get(
            "SPARKINTERVAL_PHALA_TDX_WORKER_COMPOSE_HASH")),
        ("evidence/prelude-summary.json", prelude.get("compose_hash")),
        ("evidence/rtmr-replay.json", bindings.get("compose-hash")),
    ):
        _require(
            observed == compose_hash,
            f"{label} reports app-compose hash {observed!r}, the signed "
            f"receipt says {compose_hash!r}",
        )
    _require(
        prelude.get("enclave_public_key") == public_key,
        "the prelude and the receipt disagree about the enclave public key",
    )
    _require(
        prelude.get("image_digest") == fields["image_digest"],
        "the prelude and the receipt disagree about the image digest",
    )
    _require(
        prelude.get("report_data_sha256") == fields["report_data_sha256"],
        "the prelude and the receipt disagree about the report data",
    )

    image_digest = fields["image_digest"]
    _require(
        image_digest.startswith("sha256:"),
        f"the image digest {image_digest!r} is not a sha256 OCI digest",
    )
    _lower_hex(image_digest[len("sha256:"):], 64, "the image digest body")

    # --- the appraisal actually happened, against the pinned policy --------
    _require(
        prelude.get("measurements_pinned") is True,
        "the prelude ran with unpinned measurements; such a receipt must not "
        "be promoted to a production pin",
    )
    _require(
        prelude.get("unpinned") == [],
        f"the prelude reports unpinned measurements: {prelude.get('unpinned')!r}",
    )
    observed = prelude.get("observed", {})
    _require(
        isinstance(observed, dict),
        "the prelude summary records no observed appraisal",
    )
    tcb = observed.get("tcb", {})
    _require(isinstance(tcb, dict), "the appraisal records no TCB status")
    for key in ("status", "platform_status.status", "qe_status.status"):
        _require(
            tcb.get(key) == "UpToDate",
            f"the appraisal reports {key}={tcb.get(key)!r}, not UpToDate",
        )
    _require(
        observed.get("advisory_ids") == [],
        f"the appraisal carries advisories: {observed.get('advisory_ids')!r}",
    )
    _require(
        observed.get("report_data_padded_hex", "").startswith(
            fields["report_data_sha256"]
        ),
        "the quote's report data does not begin with the committed digest",
    )
    verify_stderr = (retained / "evidence/dcap-qvl-verify.stderr").read_text(
        encoding="utf-8", errors="replace"
    )
    _require(
        "Quote verified" in verify_stderr,
        f"dcap-qvl did not report a verified quote: {verify_stderr!r}",
    )
    policy = _read_json(retained / "input/dcap-qvl-policy.json")
    _require(
        policy.get("first_run_measurement_discovery") is False,
        "the appraisal policy is still in first-run measurement discovery",
    )
    strict = _read_json(retained / "evidence/dcap-qvl-strict.json")
    strict_passed = bool(strict.get("passed"))
    _require(
        strict_passed or policy.get("require_dcap_qvl_strict") is False,
        "the policy requires `dcap-qvl --strict` and the run did not pass it",
    )
    if strict_passed:
        strict_note = "`dcap-qvl verify --strict` also passed."
    else:
        strict_note = (
            "`dcap-qvl verify --strict` did **not** pass: "
            + " ".join(str(strict.get("stderr", "")).split())
            + "  The reviewed policy sets `require_dcap_qvl_strict: false` "
            "and records why; the ungated floor is the plain `verify` above, "
            "which is the full cryptographic appraisal, and it passed."
        )
    strict_note = textwrap.fill(
        strict_note, width=76, initial_indent="", subsequent_indent="  "
    )

    # --- the tamper vectors the Lean negative tests consume ----------------
    tampered_key = _alter_one_character(public_key)
    tampered_signature = _alter_one_character(signature)
    tampered_fields = dict(fields)
    tampered_fields[DIGEST_ONLY_TAMPER_FIELD] = _alter_one_character(
        fields[DIGEST_ONLY_TAMPER_FIELD]
    )
    tampered_digest = statement_digest(tampered_fields)
    _require(
        tampered_digest != digest,
        "the tampered statement hashes to the genuine digest",
    )
    for label, key_hex, digest_hex, signature_hex in (
        ("altered public key", tampered_key, digest, signature),
        ("altered signature", public_key, digest, tampered_signature),
        ("altered statement", public_key, tampered_digest, signature),
    ):
        _require(
            not verify_digest_hex(key_hex, digest_hex, signature_hex),
            f"SOUNDNESS: the reference verifier ACCEPTS an {label}",
        )

    # --- the quote itself says what the receipt says it says ---------------
    #
    # Lean now parses the quote (`SparkInterval/Execution/TdxQuoteV4.lean`), so
    # the generator must not emit a pin whose quote disagrees with the signed
    # fields.  These two checks are the Python mirror of `phalaTdxQuoteCheck`.
    quote_bytes = (retained / "input/tdx-quote.bin").read_bytes()
    _require(
        len(quote_bytes) >= TD_REPORT_OFFSET + TD_REPORT_SIZE,
        f"the retained quote is {len(quote_bytes)} bytes, too short to "
        "contain a TD report body",
    )
    _require(
        int.from_bytes(quote_bytes[0:2], "little") == 4
        and int.from_bytes(quote_bytes[4:8], "little") == 0x81,
        "the retained quote is not a v4 Intel TDX quote",
    )
    measured_report_data = quote_bytes[
        REPORT_DATA_OFFSET:REPORT_DATA_OFFSET + 64
    ]
    _require(
        measured_report_data[:32].hex() == fields["report_data_sha256"],
        "the quote's report data is not the signed report-data digest",
    )
    _require(
        measured_report_data[32:] == b"\x00" * 32,
        "the quote's report data has a nonzero upper half",
    )
    measured_config = quote_bytes[
        MR_CONFIG_ID_OFFSET:MR_CONFIG_ID_OFFSET + 48
    ]
    _require(
        measured_config[0] == 0x01
        and measured_config[1:33].hex() == compose_hash
        and measured_config[33:] == b"\x00" * 15,
        "the quote's mr_config_id does not measure the signed app-compose "
        "hash",
    )

    return {
        "profile": profile,
        "pin_id": profile.pin_id,
        "negative_pin_id": profile.negative_pin_id,
        "app_id": app_id,
        "compose_hash": compose_hash,
        "image_digest": image_digest,
        "public_key": public_key,
        "policy_hash": fields["dcap_qvl_policy_sha256"],
        "artifact_hash": fields["dcap_qvl_artifact_sha256"],
        "signature": signature,
        "statement_digest": digest,
        "quote_packed": "0x" + quote_bytes.hex(),
        "quote_byte_count": len(quote_bytes),
        "fields": fields,
        "tampered_public_key": tampered_key,
        "tampered_signature": tampered_signature,
        "tampered_issued_at": tampered_fields[DIGEST_ONLY_TAMPER_FIELD],
        "tampered_statement_digest": tampered_digest,
        "tampered_app_id": _alter_one_character(app_id),
        "tampered_compose_hash": _alter_one_character(compose_hash),
        "strict_note": strict_note,
        "instance_id": bindings.get("instance-id", ""),
        "os_image_hash": bindings.get("os-image-hash", ""),
        "mr_td": observed.get("measurements", {}).get("mr_td", ""),
    }


# ---------------------------------------------------------------------------
# Lean emission
# ---------------------------------------------------------------------------


def _lean_string(value: str, indent: str) -> str:
    """Render a Lean string literal, wrapping long values with `++`.

    The split points are deterministic so that regenerating an unchanged
    evidence directory reproduces the committed file byte for byte.
    """

    if len(value) <= 80:
        return f'"{value}"'
    head, tail = value[:64], value[64:]
    return f'"{head}" ++\n{indent}"{tail}"'


def _field(name: str, value: str, indent: str) -> str:
    rendered = _lean_string(value, indent + "  ")
    single = f"{indent}{name} := {rendered}"
    if "\n" not in rendered and len(single) <= 78:
        return single
    return f"{indent}{name} :=\n{indent}  {rendered}"


def _doc(text: str) -> str:
    """Wrap a docstring to the repository's 78-column source width."""

    words = text.split()
    lines: list[str] = []
    current = "/--"
    for word in words:
        if len(current) + 1 + len(word) > 75:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if len(current) + 3 > 78:
        lines.append(current)
        lines.append("-/")
    else:
        lines.append(current + " -/")
    return "\n".join(lines)


def _def(name: str, value: str, doc: str) -> str:
    return (
        _doc(doc)
        + f"\ndef {name} : String :=\n  "
        + _lean_string(value, "  ")
        + "\n"
    )


# Doc comments for the generated theorems.  These describe the checks rather
# than the deployment, so every profile shares them word for word; the one
# that does name a deployment is the profile's `unpinned_theorem_doc`.
PIN_EQ_GENERATED_DOC = """\
/-- The hand-written pin case in `Execution/PhalaTdxAttestation.lean` is
exactly the machine-derived one.  A single mistyped hexadecimal digit in
either copy fails this `decide`, which is the point: the 130-character public
key is never trusted to a human's eyes. -/"""

NEGATIVE_PIN_EQ_GENERATED_DOC = (
    "/-- Likewise for the negative-test fixture. -/"
)

PIN_PUBLIC_KEY_DOC = "/-- The pinned key is the one the enclave published. -/"

RECEIPT_SIGNATURE_DOC = (
    "/-- The receipt carries the signature spelled out above. -/"
)

NEGATIVE_TEST_NO_AUTHORITY_DOC = "/-- The negative-test fixture never does. -/"


def _theorem(name: str, doc: str, lhs: str, rhs: str) -> str:
    """Render one `decide`-closed equation, wrapped the same way every time.

    The equation goes on one line when it fits the repository's 78-column
    width and breaks before the `=` when it does not, so a longer deployment
    name changes only the line breaks, never the statement.
    """

    single = f"    {lhs} = {rhs} := by"
    if len(single) <= 78:
        statement = single
    else:
        statement = f"    {lhs}\n      = {rhs} := by"
    return f"{doc}\ntheorem {name} :\n{statement}\n  decide\n"


def render_module(data: dict) -> str:
    fields = data["fields"]
    profile: Profile = data["profile"]
    i = "  "

    pin_body = "\n".join(
        [
            _field("pinId", data["pin_id"], i),
            _field("appId", data["app_id"], i),
            _field("composeHash", data["compose_hash"], i),
            _field("imageDigest", data["image_digest"], i),
            _field("enclavePublicKeyHex", data["public_key"], i),
            _field("quoteAppraisalPolicyHash", data["policy_hash"], i),
            _field("quoteAppraisalArtifactHash", data["artifact_hash"], i),
            f"{i}attestationAuthority := true",
        ]
    )
    negative_pin_body = "\n".join(
        [
            _field("pinId", data["negative_pin_id"], i),
            _field("appId", data["app_id"], i),
            _field("composeHash", data["compose_hash"], i),
            _field("imageDigest", data["image_digest"], i),
            _field("enclavePublicKeyHex", data["tampered_public_key"], i),
            _field("quoteAppraisalPolicyHash", data["policy_hash"], i),
            _field("quoteAppraisalArtifactHash", data["artifact_hash"], i),
            f"{i}attestationAuthority := false",
        ]
    )
    receipt_body = "\n".join(
        [
            _field("algorithmId", fields["algorithm_id"], i),
            _field("algorithmHash", fields["algorithm_hash"], i),
            _field("inputHash", fields["input_hash"], i),
            _field("parametersHash", fields["parameters_hash"], i),
            _field("domainHash", fields["domain_hash"], i),
            _field("result", fields["result"], i),
            _field("outputHash", fields["output_hash"], i),
            _field("challengeNonce", fields["challenge_nonce"], i),
            _field("jobBindingHash", fields["job_binding_sha256"], i),
            _field("appId", fields["app_id"], i),
            _field("composeHash", fields["compose_hash"], i),
            _field("imageDigest", fields["image_digest"], i),
            _field("quoteHash", fields["tdx_quote_sha256"], i),
            f"{i}-- The retained quote itself, packed big-endian from\n"
            f"{i}-- `{profile.evidence_path}/retained-evidence/input/"
            "tdx-quote.bin`.\n"
            f"{i}-- `phalaTdxQuoteCheck` parses it and requires its SHA-256 to "
            "be the\n"
            f"{i}-- `quoteHash` immediately above.\n"
            f"{i}quote := ⟨{data['quote_packed']}, "
            f"{data['quote_byte_count']}⟩",
            _field("quoteAppraisalHash", fields["dcap_qvl_output_sha256"], i),
            _field(
                "quoteAppraisalPolicyHash", fields["dcap_qvl_policy_sha256"], i
            ),
            _field(
                "quoteAppraisalArtifactHash",
                fields["dcap_qvl_artifact_sha256"],
                i,
            ),
            _field("reportDataHash", fields["report_data_sha256"], i),
            _field("issuedAt", fields["issued_at"], i),
            _field("signatureHex", data["signature"], i),
        ]
    )

    namespace_ = profile.namespace
    enclave = f"PhalaTdxEnclave.{profile.enclave}"
    tampered_enclave = f"PhalaTdxEnclave.{profile.tampered_enclave}"
    unpinned_enclave = f"PhalaTdxEnclave.{profile.unpinned_enclave}"
    theorems = "\n".join(
        [
            _theorem(
                f"{profile.theorem_prefix}pin_eq_generated",
                PIN_EQ_GENERATED_DOC,
                f"{enclave}.pin",
                f"{namespace_}.pin",
            ),
            _theorem(
                f"{profile.theorem_prefix}negativeTestPin_eq_generated",
                NEGATIVE_PIN_EQ_GENERATED_DOC,
                f"{tampered_enclave}.pin",
                f"{namespace_}.negativeTestPin",
            ),
            _theorem(
                f"{profile.theorem_prefix}pin_publicKey",
                PIN_PUBLIC_KEY_DOC,
                f"{enclave}.pin.enclavePublicKeyHex",
                f"{namespace_}.enclavePublicKeyHex",
            ),
            _theorem(
                f"{profile.theorem_prefix}receipt_signature",
                RECEIPT_SIGNATURE_DOC,
                f"{namespace_}.receipt.signatureHex",
                f"{namespace_}.signatureHex",
            ),
            _theorem(
                f"{profile.theorem_prefix}has_attestationAuthority",
                profile.authority_theorem_doc,
                f"{enclave}.pin.attestationAuthority",
                "true",
            ),
            _theorem(
                f"{profile.theorem_prefix}negativeTest_no_authority",
                NEGATIVE_TEST_NO_AUTHORITY_DOC,
                f"{tampered_enclave}.pin.attestationAuthority",
                "false",
            ),
            _theorem(
                f"{profile.theorem_prefix}leaves_productionV1_unpinned",
                profile.unpinned_theorem_doc,
                f"{unpinned_enclave}.pin.enclavePublicKeyHex",
                '""',
            ),
        ]
    )

    return f"""\
/- Copyright (c) 2026 Gershon Bialer. All rights reserved.
SPDX-License-Identifier: MIT -/

import SparkInterval.Execution.PhalaTdxAttestation

/-!
{profile.header(data, fields)}
-/

set_option autoImplicit false

namespace SparkInterval.Execution

namespace {namespace_}

{profile.pin_doc}
def pin : PhalaTdxEnclavePin := {{
{pin_body}
}}

/-- The same pin with the final hexadecimal digit of the enclave public key
changed.  A negative-test fixture; never an identity to trust. -/
def negativeTestPin : PhalaTdxEnclavePin := {{
{negative_pin_body}
}}

/-- The receipt the enclave signed inside the TD, field for field. -/
def receipt : PhalaTdxReceipt := {{
{receipt_body}
}}

{_def("enclavePublicKeyHex", data["public_key"],
      "The dstack-derived SEC1 uncompressed P-256 public key, spelled out so "
      "a kernel check does no structure projection of its own.")}
{_def("signatureHex", data["signature"],
      "The enclave's `r || s` signature over `statementDigest`.")}
{_def("statementDigest", data["statement_digest"],
      "SHA-256 of the canonical signed payload, as the enclave reported it. "
      "`receipt.statementDigest` recomputes it from the fields above.")}
{_def("tamperedPublicKeyHex", data["tampered_public_key"],
      "The enclave public key with its final hexadecimal digit changed.")}
{_def("tamperedSignatureHex", data["tampered_signature"],
      "The enclave signature with its final hexadecimal digit changed.")}
{_def("tamperedStatementDigest", data["tampered_statement_digest"],
      "The statement digest obtained by altering only `issuedAt`, the one "
      "signed field no check other than the signature itself inspects.")}
{_def("tamperedIssuedAt", data["tampered_issued_at"],
      "The altered `issuedAt` that produces `tamperedStatementDigest`.")}
{_def("tamperedAppId", data["tampered_app_id"],
      "The app id with its final hexadecimal digit changed.")}
{_def("tamperedComposeHash", data["tampered_compose_hash"],
      "The app-compose hash with its final hexadecimal digit changed: a "
      "different measured code base.")}
end {namespace_}

{theorems}
end SparkInterval.Execution
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default=DEFAULT_PROFILE.name,
        help=(
            "which attested deployment to emit; supplies the defaults for "
            "--evidence-dir and --out (default: %(default)s)"
        ),
    )
    # These two default from the profile, which is not known until the
    # arguments are parsed, so they start unset and are filled in below.
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=None,
        help="directory holding retained-evidence/ and run-scope.txt",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Lean module to write (default: the profile's committed one)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare --out against the generated text instead of writing",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="print the generated module instead of writing it",
    )
    arguments = parser.parse_args(argv)

    profile = PROFILES[arguments.profile]
    if arguments.evidence_dir is None:
        arguments.evidence_dir = ROOT / profile.evidence_path
    if arguments.out is None:
        arguments.out = ROOT / profile.out_path

    try:
        data = load_evidence(arguments.evidence_dir, profile)
    except PinError as error:
        print(f"phala tdx pin: {error}", file=sys.stderr)
        return 2
    rendered = render_module(data)

    if arguments.stdout:
        sys.stdout.write(rendered)
        return 0
    if arguments.check:
        if not arguments.out.is_file():
            print(f"phala tdx pin: {arguments.out} does not exist", file=sys.stderr)
            return 1
        committed = arguments.out.read_text(encoding="utf-8")
        if committed != rendered:
            print(
                f"phala tdx pin: {arguments.out} does not match the evidence "
                f"at {arguments.evidence_dir}; regenerate it",
                file=sys.stderr,
            )
            return 1
        print(f"phala tdx pin: {arguments.out} matches the retained evidence.")
        return 0
    arguments.out.write_text(rendered, encoding="utf-8")
    print(f"phala tdx pin: wrote {arguments.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
