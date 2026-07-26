#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Check native artifacts against their GitHub build-provenance attestations.

This is the verifier for layer 1 of the attested-provenance trust model.  A
successful result means exactly one thing: the named bytes carry a Sigstore
signature, logged in Rekor, whose Fulcio certificate binds them to a workflow
run of a specific repository at a specific commit.

It does **not** mean that a computation ran, that any particular input was
processed, or that any Merkle root is correct.  Those are separate layers.
The emitted record repeats that disclaimer in machine-readable form so a
downstream consumer cannot quietly widen the claim.

Subcommands:

``verify``
    Delegate to ``gh attestation verify`` and normalise its result.  Fails
    closed when ``gh`` is missing, too old to have the ``attestation``
    command, or reports anything other than success.

``inspect-bundle``
    Offline structural read of a Sigstore bundle: DSSE payload subjects,
    predicate type, build definition.  This performs **no** cryptographic
    verification and always reports ``signature_verified: false``.  Use it to
    read an attestation, never to accept one.

``check-manifest``
    Recompute artifact digests and compare them with a
    ``build-manifest.json`` emitted by ``tools/reproduce_attested_build.sh``.
    This is what a third-party rebuilder runs to show that its own rebuild
    produced the digests that were attested.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_PREDICATE_TYPE = "https://slsa.dev/provenance/v1"

# The `gh attestation` command group landed in cli/cli v2.49.0.  Anything
# older cannot verify and must not be treated as a soft failure.
MINIMUM_GH_VERSION = (2, 49, 0)


AUTHORITY = {
    "attests_that_a_computation_ran": False,
    "attests_that_a_merkle_root_is_correct": False,
    "authorizes_lean_theorem": False,
    "binds_artifact_bytes_to_a_source_commit": True,
    "establishes_hardware_evidence": False,
    "replaces_execution_evidence": False,
}


class ProvenanceVerificationError(ValueError):
    """The provenance check could not be completed or did not pass."""


def _emit(record: dict[str, Any], *, pretty: bool) -> int:
    record = dict(record)
    record.setdefault("authority", AUTHORITY)
    record.setdefault("kind", "sparkinterval.build-provenance-verification.v1")
    record.setdefault("schema_version", 1)
    if pretty:
        print(json.dumps(record, indent=2, sort_keys=True))
    else:
        print(json.dumps(record, sort_keys=True, separators=(",", ":")))
    return 0 if record.get("accepted") is True else 1


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _gh_version(binary: str) -> tuple[int, int, int] | None:
    try:
        completed = subprocess.run(
            [binary, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for token in completed.stdout.replace("\n", " ").split():
        parts = token.split(".")
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            return (int(parts[0]), int(parts[1]), int(parts[2]))
    return None


def _gh_has_attestation(binary: str) -> bool:
    completed = subprocess.run(
        [binary, "attestation", "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return completed.returncode == 0


def _verify_one(
    *,
    gh_binary: str,
    artifact: Path,
    repository: str,
    source_commit: str | None,
    signer_workflow: str | None,
    bundle: Path | None,
    deny_self_hosted: bool,
) -> dict[str, Any]:
    argv = [
        gh_binary,
        "attestation",
        "verify",
        str(artifact),
        "--repo",
        repository,
        "--predicate-type",
        EXPECTED_PREDICATE_TYPE,
        "--format",
        "json",
    ]
    if source_commit is not None:
        argv += ["--source-digest", f"sha1:{source_commit}"]
    if signer_workflow is not None:
        argv += ["--signer-workflow", signer_workflow]
    if bundle is not None:
        argv += ["--bundle", str(bundle)]
    if deny_self_hosted:
        argv += ["--deny-self-hosted-runners"]

    completed = subprocess.run(
        argv, check=False, capture_output=True, text=True, timeout=600
    )
    row: dict[str, Any] = {
        "artifact": artifact.name,
        "artifact_sha256": _sha256_file(artifact),
        "command": argv[1:],
        "exit_code": completed.returncode,
        "verified": completed.returncode == 0,
    }
    stdout = completed.stdout.strip()
    if stdout:
        try:
            row["gh_result"] = json.loads(stdout)
        except json.JSONDecodeError:
            row["gh_stdout"] = stdout[:4000]
    if completed.returncode != 0:
        row["error"] = (completed.stderr.strip() or stdout)[:4000]
    else:
        row.update(_summarise_gh_result(row.get("gh_result")))
    return row


def _summarise_gh_result(result: Any) -> dict[str, Any]:
    """Pull the identity fields out of ``gh attestation verify --format json``.

    The command returns a list of verification results.  Only the fields this
    project actually reasons about are lifted; the raw result is retained
    beside them so nothing is hidden by the summary.
    """

    summary: dict[str, Any] = {}
    if not isinstance(result, list) or not result:
        return summary
    first = result[0]
    if not isinstance(first, dict):
        return summary
    verification = first.get("verificationResult")
    if not isinstance(verification, dict):
        return summary
    signature = verification.get("signature")
    if isinstance(signature, dict):
        certificate = signature.get("certificate")
        if isinstance(certificate, dict):
            summary["signer"] = {
                key: certificate.get(key)
                for key in (
                    "buildSignerURI",
                    "buildSignerDigest",
                    "sourceRepositoryURI",
                    "sourceRepositoryDigest",
                    "sourceRepositoryRef",
                    "runnerEnvironment",
                    "issuer",
                )
                if certificate.get(key) is not None
            }
    statement = verification.get("statement")
    if isinstance(statement, dict):
        summary["predicate_type"] = statement.get("predicateType")
        subjects = statement.get("subject")
        if isinstance(subjects, list):
            summary["subjects"] = [
                {
                    "name": entry.get("name"),
                    "sha256": (entry.get("digest") or {}).get("sha256"),
                }
                for entry in subjects
                if isinstance(entry, dict)
            ]
    return summary


def command_verify(arguments: argparse.Namespace) -> int:
    artifacts = [Path(item) for item in arguments.artifact]
    missing = [str(path) for path in artifacts if not path.is_file()]
    if missing:
        return _emit(
            {
                "accepted": False,
                "mode": "verify",
                "status": "artifact_missing",
                "detail": missing,
            },
            pretty=arguments.pretty,
        )

    gh_binary = arguments.gh_binary or shutil.which("gh")
    if gh_binary is None:
        return _emit(
            {
                "accepted": False,
                "mode": "verify",
                "status": "gh_not_installed",
                "detail": (
                    "the GitHub CLI is required; install cli/cli >= "
                    f"{'.'.join(str(part) for part in MINIMUM_GH_VERSION)}"
                ),
            },
            pretty=arguments.pretty,
        )

    version = _gh_version(gh_binary)
    if not _gh_has_attestation(gh_binary):
        return _emit(
            {
                "accepted": False,
                "mode": "verify",
                "status": "gh_attestation_unavailable",
                "gh_binary": gh_binary,
                "gh_version": (
                    ".".join(str(part) for part in version) if version else None
                ),
                "minimum_gh_version": ".".join(
                    str(part) for part in MINIMUM_GH_VERSION
                ),
                "detail": (
                    "this gh build has no `attestation` command group, so no "
                    "signature was checked; fail-closed"
                ),
            },
            pretty=arguments.pretty,
        )

    rows = [
        _verify_one(
            gh_binary=gh_binary,
            artifact=path,
            repository=arguments.repo,
            source_commit=arguments.source_commit,
            signer_workflow=arguments.signer_workflow,
            bundle=Path(arguments.bundle) if arguments.bundle else None,
            deny_self_hosted=not arguments.allow_self_hosted_runners,
        )
        for path in artifacts
    ]
    accepted = bool(rows) and all(row["verified"] for row in rows)
    return _emit(
        {
            "accepted": accepted,
            "artifacts": rows,
            "gh_binary": gh_binary,
            "gh_version": (
                ".".join(str(part) for part in version) if version else None
            ),
            "mode": "verify",
            "repository": arguments.repo,
            "required_predicate_type": EXPECTED_PREDICATE_TYPE,
            "self_hosted_runners_denied": (
                not arguments.allow_self_hosted_runners
            ),
            "signer_workflow": arguments.signer_workflow,
            "source_commit": arguments.source_commit,
            "status": "verified" if accepted else "verification_failed",
        },
        pretty=arguments.pretty,
    )


def _decode_dsse_payload(bundle: dict[str, Any]) -> dict[str, Any] | None:
    envelope = bundle.get("dsseEnvelope")
    if not isinstance(envelope, dict):
        return None
    payload = envelope.get("payload")
    if not isinstance(payload, str):
        return None
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return None
    try:
        statement = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return statement if isinstance(statement, dict) else None


def command_inspect_bundle(arguments: argparse.Namespace) -> int:
    path = Path(arguments.bundle)
    if not path.is_file():
        return _emit(
            {
                "accepted": False,
                "mode": "inspect-bundle",
                "signature_verified": False,
                "status": "bundle_missing",
                "detail": str(path),
            },
            pretty=arguments.pretty,
        )

    entries: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    documents: list[Any] = []
    stripped = text.strip()
    if stripped.startswith("["):
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError as error:
            return _emit(
                {
                    "accepted": False,
                    "mode": "inspect-bundle",
                    "signature_verified": False,
                    "status": "bundle_unparsable",
                    "detail": str(error),
                },
                pretty=arguments.pretty,
            )
        documents = loaded if isinstance(loaded, list) else [loaded]
    else:
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                documents.append(json.loads(line))
            except json.JSONDecodeError as error:
                return _emit(
                    {
                        "accepted": False,
                        "mode": "inspect-bundle",
                        "signature_verified": False,
                        "status": "bundle_unparsable",
                        "detail": str(error),
                    },
                    pretty=arguments.pretty,
                )

    for document in documents:
        if not isinstance(document, dict):
            continue
        bundle = document.get("bundle") if "bundle" in document else document
        if not isinstance(bundle, dict):
            continue
        statement = _decode_dsse_payload(bundle)
        entry: dict[str, Any] = {
            "media_type": bundle.get("mediaType"),
            "statement_decoded": statement is not None,
        }
        if statement is not None:
            entry["predicate_type"] = statement.get("predicateType")
            subjects = statement.get("subject")
            if isinstance(subjects, list):
                entry["subjects"] = [
                    {
                        "name": item.get("name"),
                        "sha256": (item.get("digest") or {}).get("sha256"),
                    }
                    for item in subjects
                    if isinstance(item, dict)
                ]
            predicate = statement.get("predicate")
            if isinstance(predicate, dict):
                definition = predicate.get("buildDefinition")
                if isinstance(definition, dict):
                    entry["build_type"] = definition.get("buildType")
                    external = definition.get("externalParameters")
                    if isinstance(external, dict):
                        entry["external_parameters"] = external
                run_details = predicate.get("runDetails")
                if isinstance(run_details, dict):
                    builder = run_details.get("builder")
                    if isinstance(builder, dict):
                        entry["builder_id"] = builder.get("id")
        entries.append(entry)

    return _emit(
        {
            # An offline read is never an acceptance.  `accepted` stays false
            # even for a perfectly well-formed bundle.
            "accepted": False,
            "bundle": str(path),
            "entries": entries,
            "mode": "inspect-bundle",
            "signature_verified": False,
            "status": "structural_read_only",
            "detail": (
                "no signature, certificate chain, or transparency-log "
                "inclusion proof was checked; use `verify` to accept"
            ),
        },
        pretty=arguments.pretty,
    )


def command_check_manifest(arguments: argparse.Namespace) -> int:
    manifest_path = Path(arguments.manifest)
    if not manifest_path.is_file():
        return _emit(
            {
                "accepted": False,
                "mode": "check-manifest",
                "status": "manifest_missing",
                "detail": str(manifest_path),
            },
            pretty=arguments.pretty,
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return _emit(
            {
                "accepted": False,
                "mode": "check-manifest",
                "status": "manifest_unparsable",
                "detail": str(error),
            },
            pretty=arguments.pretty,
        )

    artifact_root = Path(
        arguments.artifact_root or manifest_path.parent / "artifacts"
    )
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    claimed = manifest.get("artifacts")
    if not isinstance(claimed, list) or not claimed:
        return _emit(
            {
                "accepted": False,
                "mode": "check-manifest",
                "status": "manifest_has_no_artifacts",
            },
            pretty=arguments.pretty,
        )

    for entry in claimed:
        name = entry.get("name")
        path = artifact_root / str(name)
        row: dict[str, Any] = {"name": name, "claimed_sha256": entry.get("sha256")}
        if not path.is_file():
            row["status"] = "missing"
            failures.append(f"{name}: missing")
        else:
            actual = _sha256_file(path)
            row["actual_sha256"] = actual
            row["size_bytes"] = path.stat().st_size
            if actual != entry.get("sha256"):
                row["status"] = "digest_mismatch"
                failures.append(f"{name}: digest mismatch")
            elif row["size_bytes"] != entry.get("size_bytes"):
                row["status"] = "size_mismatch"
                failures.append(f"{name}: size mismatch")
            else:
                row["status"] = "match"
        rows.append(row)

    present = sorted(
        item.name for item in artifact_root.iterdir() if item.is_file()
    ) if artifact_root.is_dir() else []
    unexpected = sorted(set(present) - {str(entry.get("name")) for entry in claimed})
    if unexpected:
        failures.append(f"unlisted artifacts present: {unexpected}")

    return _emit(
        {
            "accepted": not failures,
            "artifact_root": str(artifact_root),
            "artifacts": rows,
            "commit": manifest.get("commit"),
            "failures": failures,
            "manifest": str(manifest_path),
            "manifest_sha256": _sha256_file(manifest_path),
            "mode": "check-manifest",
            "status": "manifest_matches_bytes" if not failures else "manifest_mismatch",
            "unexpected_artifacts": unexpected,
        },
        pretty=arguments.pretty,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify GitHub build-provenance attestations for SparkInterval "
            "native artifacts and report a machine-readable result"
        )
    )
    parser.add_argument(
        "--pretty", action="store_true", help="indent the emitted JSON record"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser(
        "verify", help="check artifacts with `gh attestation verify`"
    )
    verify.add_argument(
        "--artifact",
        action="append",
        required=True,
        help="path to an attested artifact (repeatable)",
    )
    verify.add_argument(
        "--repo",
        required=True,
        help="owner/name of the repository expected to have produced it",
    )
    verify.add_argument(
        "--source-commit",
        default=None,
        help="require the attestation to name this source commit SHA-1",
    )
    verify.add_argument(
        "--signer-workflow",
        default=None,
        help=(
            "require this signing workflow, e.g. "
            "owner/name/.github/workflows/build-provenance.yml"
        ),
    )
    verify.add_argument(
        "--bundle",
        default=None,
        help="offline Sigstore bundle to verify against instead of the API",
    )
    verify.add_argument(
        "--allow-self-hosted-runners",
        action="store_true",
        help=(
            "do not pass --deny-self-hosted-runners; only for a reviewed "
            "self-hosted builder"
        ),
    )
    verify.add_argument(
        "--gh-binary",
        default=None,
        help="explicit GitHub CLI path (default: the first `gh` on PATH)",
    )
    verify.set_defaults(handler=command_verify)

    inspect = subparsers.add_parser(
        "inspect-bundle",
        help="structurally read a Sigstore bundle without verifying it",
    )
    inspect.add_argument("bundle", help="path to a .sigstore.json bundle")
    inspect.set_defaults(handler=command_inspect_bundle)

    check = subparsers.add_parser(
        "check-manifest",
        help="compare a build manifest with the artifact bytes on disk",
    )
    check.add_argument(
        "manifest", help="build-manifest.json from reproduce_attested_build.sh"
    )
    check.add_argument(
        "--artifact-root",
        default=None,
        help="directory holding the artifacts (default: <manifest dir>/artifacts)",
    )
    check.set_defaults(handler=command_check_manifest)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        return arguments.handler(arguments)
    except ProvenanceVerificationError as error:
        print(f"build provenance verification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
