#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed challenge-bound workload and trace replay for finite Sqrt218."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.sqrt218_certificate import (  # noqa: E402
    Sqrt218ProducerError,
    write_certificate,
)
from tg_verifier.sqrt218_certificate_verifier import (  # noqa: E402
    Sqrt218VerificationError,
    verification_bytes,
    verify_certificate,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker,
)
from tg_verifier.sqrt218_numeric_corpus import (  # noqa: E402
    Sqrt218CorpusError,
    resolve_verified_archive,
)
from tg_verifier.sqrt218_contract import (  # noqa: E402
    ALGORITHM_ID,
    AZURE_MEASURED_PRODUCTION_CONTEXT,
    BOUND,
    canonical_json_bytes,
    parse_canonical_json,
    recomputation_run_input_bytes,
    sha256_bytes,
)


TRACE_KIND = "sparkinterval_challenge_work_trace"
TRACE_DOMAIN = b"sparkinterval.measured-work-trace.sqrt218-finite.binding.v1\0"
CERTIFICATE_PATH = Path("work/sqrt218-certificate.json")
REPORT_PATH = Path("work/sqrt218-verification.json")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
class Sqrt218MeasuredWorkloadError(RuntimeError):
    """The measured input, exact replay, output, or trace differed."""


def _require_measured_production(args: argparse.Namespace, operation: str) -> None:
    if not args.cloud_production:
        raise Sqrt218MeasuredWorkloadError(
            f"the bound-2,000,000 {operation} requires --cloud-production"
        )
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )


def _safe_relative(value: str, what: str) -> Path:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise Sqrt218MeasuredWorkloadError(f"{what} is not a safe relative path")
    return Path(*path.parts)


def _read_stable(path: Path, what: str, maximum: int) -> tuple[bytes, str]:
    if path.is_symlink() or not path.is_file():
        raise Sqrt218MeasuredWorkloadError(
            f"{what} must be a regular non-symlink file"
        )
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    size = 0
    with path.open("rb") as source:
        before = os.fstat(source.fileno())
        while block := source.read(1024 * 1024):
            size += len(block)
            if size > maximum:
                raise Sqrt218MeasuredWorkloadError(f"{what} exceeds its byte limit")
            digest.update(block)
            chunks.append(block)
        after = os.fstat(source.fileno())
    identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_size,
        item.st_mtime_ns,
    )
    if identity(before) != identity(after):
        raise Sqrt218MeasuredWorkloadError(f"{what} changed while read")
    return b"".join(chunks), digest.hexdigest()


def _read(path: Path, what: str, maximum: int) -> bytes:
    raw, _digest = _read_stable(path, what, maximum)
    return raw


def _digest_file(path: Path, what: str, maximum: int) -> tuple[str, int]:
    raw, digest = _read_stable(path, what, maximum)
    return digest, len(raw)


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise Sqrt218MeasuredWorkloadError(f"short write to {path}")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _hex(value: str, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise Sqrt218MeasuredWorkloadError(f"{what} is not lowercase SHA-256")
    return value


def _trace_digest(
    *,
    challenge: str,
    job_binding: str,
    input_sha256: str,
    result_sha256: str,
    certificate_sha256: str,
    report_sha256: str,
) -> str:
    fields = (
        ("challenge_nonce", _hex(challenge, "challenge nonce")),
        ("job_binding_sha256", _hex(job_binding, "job binding")),
        ("input_sha256", _hex(input_sha256, "input digest")),
        ("result_sha256", _hex(result_sha256, "result digest")),
        ("certificate_sha256", _hex(certificate_sha256, "certificate digest")),
        ("verification_report_sha256", _hex(report_sha256, "report digest")),
    )
    payload = bytearray(TRACE_DOMAIN)
    for name, value in fields:
        payload.extend(f"{name}={value}\n".encode("ascii"))
    return hashlib.sha256(payload).hexdigest()


def _trace_value(
    *,
    challenge: str,
    job_binding: str,
    input_sha256: str,
    result_sha256: str,
    certificate_sha256: str,
    report_sha256: str,
) -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "challenge_nonce": challenge,
        "input_sha256": input_sha256,
        "iteration_count": BOUND,
        "job_binding_sha256": job_binding,
        "kind": TRACE_KIND,
        "result_sha256": result_sha256,
        "schema_version": 1,
        "trace_sha256": _trace_digest(
            challenge=challenge,
            job_binding=job_binding,
            input_sha256=input_sha256,
            result_sha256=result_sha256,
            certificate_sha256=certificate_sha256,
            report_sha256=report_sha256,
        ),
    }


def _require_input(
    path: Path,
    snapshot_root: Path | None,
) -> tuple[bytes, str, Path | None, dict[str, Any] | None]:
    raw = _read(path, "registered Sqrt218 input", 1 << 20)
    if raw == recomputation_run_input_bytes():
        if snapshot_root is not None:
            raise Sqrt218MeasuredWorkloadError(
                "the recomputation input cannot select a numeric-corpus snapshot"
            )
        return raw, "full_recomputation", None, None
    if snapshot_root is None:
        raise Sqrt218MeasuredWorkloadError(
            "a non-recomputation input requires --numeric-corpus-snapshot"
        )
    try:
        archive, binding = resolve_verified_archive(raw, snapshot_root)
    except Sqrt218CorpusError as error:
        raise Sqrt218MeasuredWorkloadError(str(error)) from error
    return raw, "verified_numeric_corpus", archive, binding


def _report(
    certificate_path: Path,
    *,
    input_path: Path,
    input_mode: str,
    corpus_binding: dict[str, Any] | None,
) -> dict[str, Any]:
    report = verify_certificate(
        certificate_path,
        run_input_path=input_path if input_mode == "full_recomputation" else None,
        require_production=True,
        execution_context=AZURE_MEASURED_PRODUCTION_CONTEXT,
    )
    report["input_mode"] = input_mode
    report["numeric_corpus"] = corpus_binding
    return report


def run(args: argparse.Namespace) -> None:
    _require_measured_production(args, "workload")
    input_path = _safe_relative(args.input, "input path")
    output_path = _safe_relative(args.output, "output path")
    trace_path = _safe_relative(args.trace, "trace path")
    certificate_path = _safe_relative(args.certificate, "certificate path")
    report_path = _safe_relative(args.report, "report path")
    snapshot_root = (
        _safe_relative(args.numeric_corpus_snapshot, "numeric-corpus snapshot")
        if args.numeric_corpus_snapshot is not None
        else None
    )
    if len({input_path, output_path, trace_path, certificate_path, report_path}) != 5:
        raise Sqrt218MeasuredWorkloadError("measured paths must be distinct")
    input_raw, input_mode, corpus_archive, corpus_binding = _require_input(
        input_path, snapshot_root
    )
    if input_mode == "full_recomputation":
        write_certificate(
            certificate_path,
            BOUND,
            execution_context=AZURE_MEASURED_PRODUCTION_CONTEXT,
        )
        selected_certificate = certificate_path
    else:
        assert corpus_archive is not None
        selected_certificate = corpus_archive
    report = _report(
        selected_certificate,
        input_path=input_path,
        input_mode=input_mode,
        corpus_binding=corpus_binding,
    )
    report_raw = verification_bytes(report)
    _write_exclusive(report_path, report_raw)
    result_raw = b"true"
    _write_exclusive(output_path, result_raw)
    certificate_sha256, _ = _digest_file(
        selected_certificate, "Sqrt218 certificate", 256 * 1024 * 1024
    )
    trace = _trace_value(
        challenge=args.challenge,
        job_binding=args.job_binding,
        input_sha256=sha256_bytes(input_raw),
        result_sha256=sha256_bytes(result_raw),
        certificate_sha256=certificate_sha256,
        report_sha256=sha256_bytes(report_raw),
    )
    _write_exclusive(trace_path, canonical_json_bytes(trace))


def verify_trace(args: argparse.Namespace) -> None:
    _require_measured_production(args, "trace replay")
    input_path = _safe_relative(args.input, "input path")
    output_path = _safe_relative(args.output, "output path")
    trace_path = _safe_relative(args.trace, "trace path")
    certificate_path = _safe_relative(args.certificate, "certificate path")
    report_path = _safe_relative(args.report, "report path")
    snapshot_root = (
        _safe_relative(args.numeric_corpus_snapshot, "numeric-corpus snapshot")
        if args.numeric_corpus_snapshot is not None
        else None
    )
    input_raw, input_mode, corpus_archive, corpus_binding = _require_input(
        input_path, snapshot_root
    )
    selected_certificate = (
        certificate_path
        if input_mode == "full_recomputation"
        else corpus_archive
    )
    assert selected_certificate is not None
    result_raw = _read(output_path, "registered Sqrt218 result", 16)
    if result_raw != b"true":
        raise Sqrt218MeasuredWorkloadError("registered result is not exact ASCII true")
    fresh_report = _report(
        selected_certificate,
        input_path=input_path,
        input_mode=input_mode,
        corpus_binding=corpus_binding,
    )
    fresh_report_raw = verification_bytes(fresh_report)
    retained_report_raw = _read(
        report_path, "retained Sqrt218 verification", 1 << 20
    )
    if retained_report_raw != fresh_report_raw:
        raise Sqrt218MeasuredWorkloadError(
            "retained verification report differs from independent replay"
        )
    certificate_sha256, _ = _digest_file(
        selected_certificate, "Sqrt218 certificate", 256 * 1024 * 1024
    )
    expected = _trace_value(
        challenge=args.challenge,
        job_binding=args.job_binding,
        input_sha256=sha256_bytes(input_raw),
        result_sha256=sha256_bytes(result_raw),
        certificate_sha256=certificate_sha256,
        report_sha256=sha256_bytes(fresh_report_raw),
    )
    trace_raw = _read(trace_path, "Sqrt218 work trace", 1 << 20)
    try:
        actual = parse_canonical_json(
            trace_raw, what="Sqrt218 work trace", maximum_bytes=1 << 20
        )
    except ValueError as error:
        raise Sqrt218MeasuredWorkloadError(str(error)) from error
    if actual != expected:
        raise Sqrt218MeasuredWorkloadError(
            "work trace differs from challenge-bound full replay"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "verify-trace"))
    parser.add_argument(
        "--cloud-production",
        action="store_true",
        help="Explicitly select the cloud-only bound-2,000,000 path.",
    )
    parser.add_argument("--challenge", required=True)
    parser.add_argument("--job-binding", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument(
        "--certificate", default=CERTIFICATE_PATH.as_posix()
    )
    parser.add_argument("--report", default=REPORT_PATH.as_posix())
    parser.add_argument(
        "--numeric-corpus-snapshot",
        help=(
            "Verified read-only snapshot root. Required when the exact input "
            "artifact is a pinned numeric-corpus record."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        (run if args.mode == "run" else verify_trace)(args)
        return 0
    except (
        OSError,
        Sqrt218MeasuredWorkloadError,
        Sqrt218ProducerError,
        Sqrt218VerificationError,
        Sqrt218CorpusError,
        ValueError,
    ) as error:
        print(f"sqrt218 measured workload: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
