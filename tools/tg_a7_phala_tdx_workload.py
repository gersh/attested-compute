#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed CH25 Lemma A.7 campaign job for a Phala/dstack Intel TDX enclave.

This is the Phala sibling of ``tools/tg_a7_azure_measured_workload.py``.  It
does not import that module and does not touch the Azure measured-runner
guard: the only scope check it performs is
``tg_verifier.campaign_io.require_phala_tdx_worker``.

The job produces two things:

1. ``--output`` -- the registered result bytes (``true``), exactly as the
   Azure job produces them; and
2. ``--receipt`` -- an enclave-signed receipt binding the registered
   algorithm identity, the exact result, the dstack job identity, the pinned
   image digest, and the SHA-256 identities of the retained TDX quote and its
   external ``dcap-qvl`` appraisal.

Quote verification is *not* performed here and is not performed in Lean.  It
is performed by ``dcap-qvl`` outside, and only the SHA-256 of the retained
quote, the appraisal output, the appraisal policy, and the appraisal binary
enter the signed statement.  Lean checks the P-256 signature and the
bindings.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.a7_flint import A7FlintReplayError, replay_a7_flint  # noqa: E402
from tg_verifier.analytic import canonical_json_bytes  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    PhalaTdxWorkerScopeError,
    hash_file_once,
    require_phala_tdx_worker,
)
from tg_verifier.phala_tdx_receipt import (  # noqa: E402
    PhalaTdxReceiptError,
    report_data_hash,
    sign_receipt,
)
from tg_verifier.python_flint_runtime import (  # noqa: E402
    PythonFlintRuntimeError,
    extract_verified_wheel,
    load_pin as load_python_flint_pin,
    verify_wheel,
)


# Exactly the values pinned by `RegisteredAlgorithm.ch25A7BoundaryV1` and
# `RegisteredInvocation.ch25A7BoundaryProductionV1` in
# `SparkInterval/Execution/RegisteredAlgorithm.lean`.  Any drift makes the
# Lean invocation check fail closed, and
# `tests/test_phala_tdx_first_run.py` asserts the literals still agree.
REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.ch25-lemma-a7-boundary.v1"
)
REGISTERED_ALGORITHM_HASH = (
    "340dc36f2ceb992ab16e34c534cd97b786d348ba057e159c295b3abd1328cdfa"
)
REGISTERED_INPUT_HASH = (
    "4e45410d2d26467dbd5f78f8ea536b1a8bbf44f1cd5248e234b985bd1f595674"
)
REGISTERED_PARAMETERS_HASH = (
    "f377fb7b8c8d8d033083a0759841411d9bb955e919041f2a5b5be830ed69212e"
)
REGISTERED_DOMAIN_HASH = (
    "629d9c7b3c084ef33f69d92abbe22b5120bac210fc963191c4b1e8289ff1dea5"
)
REGISTERED_INPUT = (
    b'{"campaign":"ch25-a7-boundary-v1","retained_artifact_sha256":'
    b'"ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"}'
)
REGISTERED_RESULT = b"true"
RETAINED_ARTIFACT_SHA256 = (
    "ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"
)
REPORT_PATH = Path("a7-replay.json")
MAX_REPORT_BYTES = 64 * 1024
MAX_QUOTE_BYTES = 1024 * 1024

# Named, explicitly non-production mode.  It is refused unless the caller
# both passes `--local-dry-run` and sets the environment marker, and the
# emitted receipt carries an unsigned `local_dry_run` marker.  Containment of
# a dry run does NOT rely on this flag: it relies on the Lean enclave pin,
# whose `attestationAuthority` field is `false` for the dry-run identity, so
# no dry-run receipt can reach the production campaign theorem.
DRY_RUN_ENV = "SPARKINTERVAL_PHALA_TDX_LOCAL_DRY_RUN"


class A7PhalaTdxWorkloadError(RuntimeError):
    """The exact input, runtime, artifact replay, key, or receipt differed."""


def _safe_relative(value: str, what: str) -> Path:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or value != path.as_posix()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise A7PhalaTdxWorkloadError(f"{what} is not a safe relative path")
    return Path(*path.parts)


def _hex(value: str, length: int, what: str) -> str:
    if len(value) != length or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise A7PhalaTdxWorkloadError(
            f"{what} is not {length} lowercase hexadecimal digits"
        )
    return value


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o400,
    )
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise A7PhalaTdxWorkloadError("short exclusive output write")
            view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _read(path: Path, maximum: int, what: str) -> bytes:
    try:
        with path.open("rb") as source:
            raw = source.read(maximum + 1)
    except OSError as error:
        raise A7PhalaTdxWorkloadError(f"cannot read {what}: {error}") from error
    if len(raw) > maximum:
        raise A7PhalaTdxWorkloadError(f"{what} exceeds its byte limit")
    return raw


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for directory, names, _files in os.walk(path):
        try:
            Path(directory).chmod(0o700)
        except OSError:
            pass
        for name in names:
            candidate = Path(directory) / name
            if candidate.is_dir():
                try:
                    candidate.chmod(0o700)
                except OSError:
                    pass
    shutil.rmtree(path, ignore_errors=True)


def _activate_runtime(wheel: Path, destination: Path) -> dict[str, Any]:
    pin = load_python_flint_pin(ROOT / "specifications/PYTHON_FLINT_0_9_UPSTREAM.json")
    identity = extract_verified_wheel(wheel, destination, pin)
    sys.path.insert(0, str(destination))
    try:
        import flint  # type: ignore

        if (
            str(flint.__version__) != "0.9.0"
            or str(flint.__FLINT_VERSION__) != "3.6.0"
            or int(flint.__FLINT_RELEASE__) != 30_600
        ):
            raise A7PhalaTdxWorkloadError(
                "loaded python-flint/FLINT version differs"
            )
    except (ImportError, AttributeError, OSError, ValueError) as error:
        raise A7PhalaTdxWorkloadError(
            f"cannot load pinned python-flint runtime: {error}"
        ) from error
    return identity


def _normalized_report(
    report: dict[str, Any], *, retained: bool
) -> dict[str, Any]:
    value = dict(report)
    elapsed = value.pop("elapsed_milliseconds", None)
    if isinstance(elapsed, bool) or not isinstance(elapsed, int) or elapsed < 0:
        raise A7PhalaTdxWorkloadError("A.7 replay elapsed time is malformed")
    required_true = (
        "four_edge_dyadic_cover_verified",
        "every_leaf_flint_box_recomputed",
        "every_exact_leaf_endpoint_matched",
        "all_denominator_and_zeta_nonvanishing_guards_checked",
        "strict_norm_square_bound_verified_under_flint_semantics",
        "external_analytic_verification_complete",
    )
    if (
        value.get("accepted") is not True
        or value.get("artifact_kind") != "ch25_a7_boundary"
        or value.get("verification_class")
        != "complete_external_flint_arb_leaf_replay"
        or value.get("python_flint_version") != "0.9.0"
        or value.get("flint_version") != "3.6.0"
        or value.get("flint_release") != 30_600
        or any(value.get(field) is not True for field in required_true)
        or value.get("ordinary_kernel_lean_proof") is not False
        or value.get("mathlib_zeta_realization_theorem_present") is not False
        or value.get("lean_atom_discharged") is not False
    ):
        raise A7PhalaTdxWorkloadError(
            "A.7 replay report differs from the closed contract"
        )
    if retained and (
        value.get("artifact_bytes_match_pinned_sha256") is not True
        or value.get("artifact_sha256") != RETAINED_ARTIFACT_SHA256
        or value.get("leaf_count") != 16_191
    ):
        raise A7PhalaTdxWorkloadError(
            "A.7 replay report is not the retained production artifact"
        )
    raw = canonical_json_bytes(value)
    if len(raw) > MAX_REPORT_BYTES:
        raise A7PhalaTdxWorkloadError(
            "normalized A.7 replay report is too large"
        )
    return value


def _load_private_key(path: Path) -> int:
    """Read the dstack-derived signing scalar as 64 lowercase hex digits.

    In a real run this file is written by the container entry point from the
    dstack key-derivation endpoint and never leaves the CVM.
    """

    raw = _read(path, 128, "enclave signing key").decode("ascii", "strict").strip()
    scalar = int(_hex(raw, 64, "enclave signing key"), 16)
    if scalar == 0:
        raise A7PhalaTdxWorkloadError("enclave signing key is zero")
    return scalar


def run(args: argparse.Namespace) -> None:
    job = require_phala_tdx_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    if args.local_dry_run and os.environ.get(DRY_RUN_ENV) != "1":
        raise A7PhalaTdxWorkloadError(
            f"--local-dry-run additionally requires {DRY_RUN_ENV}=1"
        )
    if _read(args.input, len(REGISTERED_INPUT), "registered input") != REGISTERED_INPUT:
        raise A7PhalaTdxWorkloadError("registered A.7 input differs")
    artifact_sha256, _size = hash_file_once(args.artifact)
    if not args.local_dry_run and artifact_sha256 != RETAINED_ARTIFACT_SHA256:
        raise A7PhalaTdxWorkloadError("retained A.7 artifact differs")
    wheel = verify_wheel(args.wheel)
    private_key = _load_private_key(args.enclave_key)
    quote_sha256, _ = hash_file_once(args.quote)
    appraisal_sha256, _ = hash_file_once(args.quote_appraisal)
    policy_sha256, _ = hash_file_once(args.quote_appraisal_policy)
    appraiser_sha256, _ = hash_file_once(args.quote_appraisal_artifact)
    if args.work.exists():
        raise A7PhalaTdxWorkloadError("A.7 work path must be fresh")
    args.work.mkdir(mode=0o700, parents=True)
    runtime = args.work / "python-flint-runtime"
    succeeded = False
    try:
        _activate_runtime(args.wheel, runtime)
        report = _normalized_report(
            replay_a7_flint(
                args.artifact, require_retained_identity=not args.local_dry_run
            ),
            retained=not args.local_dry_run,
        )
        _write_exclusive(args.work / REPORT_PATH, canonical_json_bytes(report))
        _write_exclusive(args.output, REGISTERED_RESULT)

        from tg_verifier.phala_tdx_receipt import public_key_hex

        enclave_public_key = public_key_hex(private_key)
        fields = {
            "algorithm_id": REGISTERED_ALGORITHM_ID,
            "algorithm_hash": REGISTERED_ALGORITHM_HASH,
            "input_hash": REGISTERED_INPUT_HASH,
            "parameters_hash": REGISTERED_PARAMETERS_HASH,
            "domain_hash": REGISTERED_DOMAIN_HASH,
            "result": REGISTERED_RESULT.decode("ascii"),
            "output_hash": hash_file_once(args.output)[0],
            "challenge_nonce": job["challenge_nonce"],
            "job_binding_sha256": job["job_binding"],
            "app_id": job["app_id"],
            "compose_hash": job["compose_hash"],
            "image_digest": args.image_digest,
            "tdx_quote_sha256": quote_sha256,
            "dcap_qvl_output_sha256": appraisal_sha256,
            "dcap_qvl_policy_sha256": policy_sha256,
            "dcap_qvl_artifact_sha256": appraiser_sha256,
            "report_data_sha256": report_data_hash(
                enclave_public_key_hex=enclave_public_key,
                challenge_nonce=job["challenge_nonce"],
                job_binding=job["job_binding"],
            ),
            "issued_at": args.issued_at,
        }
        receipt = sign_receipt(private_key, fields)
        receipt["backend"] = job["backend"]
        receipt["python_flint_wheel_sha256"] = wheel["sha256"]
        receipt["a7_artifact_sha256"] = artifact_sha256
        if args.local_dry_run:
            receipt["local_dry_run"] = True
        _write_exclusive(args.receipt, canonical_json_bytes(receipt))
        succeeded = True
    finally:
        _remove_tree(runtime)
        if not succeeded:
            _remove_tree(args.work)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--algorithm-id", required=True)
    result.add_argument("--challenge", required=True)
    result.add_argument("--job-binding", required=True)
    result.add_argument("--image-digest", required=True)
    result.add_argument("--issued-at", required=True)
    result.add_argument("--input", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--receipt", type=Path, required=True)
    result.add_argument("--artifact", type=Path, required=True)
    result.add_argument("--wheel", type=Path, required=True)
    result.add_argument("--work", type=Path, required=True)
    result.add_argument("--enclave-key", type=Path, required=True)
    result.add_argument("--quote", type=Path, required=True)
    result.add_argument("--quote-appraisal", type=Path, required=True)
    result.add_argument("--quote-appraisal-policy", type=Path, required=True)
    result.add_argument("--quote-appraisal-artifact", type=Path, required=True)
    result.add_argument(
        "--local-dry-run",
        action="store_true",
        help=(
            "explicitly non-production: allow a fixture A.7 artifact.  The "
            "receipt is still only usable under the Lean dry-run enclave "
            "pin, which carries no attestation authority."
        ),
    )
    return result


def _validate_args(args: argparse.Namespace) -> None:
    if args.algorithm_id != REGISTERED_ALGORITHM_ID:
        raise A7PhalaTdxWorkloadError("algorithm id differs from registered A.7")
    _hex(args.challenge, 64, "challenge")
    _hex(args.job_binding, 64, "job binding")
    if not args.image_digest.startswith("sha256:"):
        raise A7PhalaTdxWorkloadError(
            "image digest must pin the final image as sha256:<64 hex>"
        )
    _hex(args.image_digest[7:], 64, "image digest")
    if not args.issued_at or len(args.issued_at) > 64:
        raise A7PhalaTdxWorkloadError("issued-at timestamp is malformed")
    for name in (
        "input",
        "output",
        "receipt",
        "artifact",
        "wheel",
        "work",
        "enclave_key",
        "quote",
        "quote_appraisal",
        "quote_appraisal_policy",
        "quote_appraisal_artifact",
    ):
        value = getattr(args, name)
        setattr(args, name, _safe_relative(value.as_posix(), name))


def main() -> int:
    args = parser().parse_args()
    try:
        _validate_args(args)
        run(args)
        return 0
    except (
        A7FlintReplayError,
        A7PhalaTdxWorkloadError,
        OSError,
        PhalaTdxReceiptError,
        PhalaTdxWorkerScopeError,
        PythonFlintRuntimeError,
        ValueError,
    ) as error:
        print(f"A.7 Phala TDX workload error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
