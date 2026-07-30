# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Canonical, crash-safe I/O for ternary-Goldbach campaign metadata.

Campaign JSON is control-plane input.  It is therefore parsed without binary
floating point, duplicate keys, or non-finite constants.  Immutable plans are
content addressed; mutable status files are replaced atomically while holding
an advisory lock in the same directory.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Iterator


MAX_CONTROL_BYTES = 64 * 1024 * 1024
LOCAL_KAT_MAX_WORK_ITEMS = 64
AZURE_MEASURED_WORKER_SCOPE = "sparkinterval.azure-measured-worker.v1"
AZURE_MEASURED_WORKER_SCOPE_ENV = "SPARKINTERVAL_MEASURED_WORKER_SCOPE"
AZURE_MEASURED_WORKER_BACKEND_ENV = "SPARKINTERVAL_MEASURED_WORKER_BACKEND"
AZURE_MEASURED_WORKER_CHALLENGE_ENV = (
    "SPARKINTERVAL_MEASURED_WORKER_CHALLENGE_NONCE"
)
AZURE_MEASURED_WORKER_JOB_BINDING_ENV = (
    "SPARKINTERVAL_MEASURED_WORKER_JOB_BINDING_SHA256"
)
AZURE_MEASURED_WORKER_BACKENDS = frozenset(
    {"azure_ncc40ads_h100_v5", "azure_sevsnp_cpu"}
)
AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS = frozenset(
    {
        AZURE_MEASURED_WORKER_SCOPE_ENV,
        AZURE_MEASURED_WORKER_BACKEND_ENV,
        AZURE_MEASURED_WORKER_CHALLENGE_ENV,
        AZURE_MEASURED_WORKER_JOB_BINDING_ENV,
    }
)


class CampaignIOError(ValueError):
    """Campaign control data is malformed or cannot be updated safely."""


class MeasuredWorkerScopeError(CampaignIOError):
    """A production workload escaped its measured Azure worker scope."""


def _lower_hex256(value: str, what: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise MeasuredWorkerScopeError(f"{what} must be lowercase SHA-256")
    return value


def azure_measured_worker_environment(
    environment: dict[str, str],
    *,
    backend: str,
    challenge_nonce: str,
    job_binding: str,
) -> dict[str, str]:
    """Return the exact environment for one measured production child.

    These variables are injected by ``azure/measured_runner.py`` only after it
    has validated the challenge, job, immutable closure, profiles, runner
    policy, and PCR start binding.  They are an execution-scope guard against
    accidentally launching production arithmetic through an ordinary local
    CLI.  They are not attestation evidence and never replace independent
    appraisal of the measured-run transcript.
    """

    if not isinstance(environment, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in environment.items()
    ):
        raise MeasuredWorkerScopeError(
            "measured child environment must map strings to strings"
        )
    overlap = AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS.intersection(environment)
    if overlap:
        raise MeasuredWorkerScopeError(
            "job environment attempts to set runner-reserved execution scope: "
            + ", ".join(sorted(overlap))
        )
    if backend not in AZURE_MEASURED_WORKER_BACKENDS:
        raise MeasuredWorkerScopeError(
            f"unsupported measured Azure worker backend: {backend!r}"
        )
    challenge = _lower_hex256(challenge_nonce, "challenge nonce")
    binding = _lower_hex256(job_binding, "job binding")
    return {
        **environment,
        AZURE_MEASURED_WORKER_SCOPE_ENV: AZURE_MEASURED_WORKER_SCOPE,
        AZURE_MEASURED_WORKER_BACKEND_ENV: backend,
        AZURE_MEASURED_WORKER_CHALLENGE_ENV: challenge,
        AZURE_MEASURED_WORKER_JOB_BINDING_ENV: binding,
    }


def require_azure_measured_worker(
    *,
    challenge_nonce: str,
    job_binding: str,
    environment: dict[str, str] | None = None,
) -> str:
    """Fail closed unless this call is the runner-bound Azure worker.

    Normal local development must use symbolic/static checks or a dedicated
    tiny KAT with every finite bound at most 64.  Production workload CLIs
    call this before either their producer or independent replay path.
    """

    challenge = _lower_hex256(challenge_nonce, "challenge nonce")
    binding = _lower_hex256(job_binding, "job binding")
    actual = os.environ if environment is None else environment
    expected = {
        AZURE_MEASURED_WORKER_SCOPE_ENV: AZURE_MEASURED_WORKER_SCOPE,
        AZURE_MEASURED_WORKER_CHALLENGE_ENV: challenge,
        AZURE_MEASURED_WORKER_JOB_BINDING_ENV: binding,
    }
    for key, value in expected.items():
        if actual.get(key) != value:
            raise MeasuredWorkerScopeError(
                "production arithmetic/replay is cloud-only: the exact "
                f"measured-runner binding is absent or mismatched ({key})"
            )
    backend = actual.get(AZURE_MEASURED_WORKER_BACKEND_ENV)
    if backend not in AZURE_MEASURED_WORKER_BACKENDS:
        raise MeasuredWorkerScopeError(
            "production arithmetic/replay is cloud-only: measured Azure "
            "worker backend is absent or unsupported"
        )
    return backend


def require_azure_measured_worker_for_workload(
    *,
    exact_production: bool,
    work_bounds: tuple[int, ...],
    environment: dict[str, str] | None = None,
) -> str | None:
    """Keep production and non-tiny finite work inside a measured Azure child.

    ``work_bounds`` contains counts or spans, never absolute mathematical
    endpoints.  A non-production KAT is local only when every supplied bound
    is at most 64.  Metadata-only commands do not call this function.

    The measured runner owns the four reserved environment variables and
    rejects attempts by a job to preseed them.  This helper consumes that
    injected binding and delegates the actual scope check to
    :func:`require_azure_measured_worker`.  Like the underlying scope guard,
    this prevents accidental dispatch; the signed measured-run transcript is
    still the security evidence.
    """

    if not isinstance(exact_production, bool):
        raise MeasuredWorkerScopeError("exact_production must be Boolean")
    if (
        not isinstance(work_bounds, tuple)
        or any(
            isinstance(bound, bool) or not isinstance(bound, int) or bound < 0
            for bound in work_bounds
        )
    ):
        raise MeasuredWorkerScopeError(
            "finite workload bounds must be nonnegative integers"
        )
    if not exact_production and not work_bounds:
        raise MeasuredWorkerScopeError(
            "non-production arithmetic must declare at least one finite "
            "workload bound"
        )
    if not exact_production and all(
        bound <= LOCAL_KAT_MAX_WORK_ITEMS for bound in work_bounds
    ):
        return None

    actual = os.environ if environment is None else environment
    challenge = actual.get(AZURE_MEASURED_WORKER_CHALLENGE_ENV)
    binding = actual.get(AZURE_MEASURED_WORKER_JOB_BINDING_ENV)
    if not isinstance(challenge, str) or not isinstance(binding, str):
        raise MeasuredWorkerScopeError(
            "production arithmetic/replay is cloud-only: measured-runner "
            "challenge or job binding is absent"
        )
    return require_azure_measured_worker(
        challenge_nonce=challenge,
        job_binding=binding,
        environment=actual,
    )


# ---------------------------------------------------------------------------
# Phala/dstack Intel TDX acceptance route
#
# This is a SEPARATE, EXPLICITLY NAMED acceptance path.  It shares no code,
# no environment variable, no scope string, and no exception type with the
# Azure route above, and it never calls -- and is never called by -- any
# ``require_azure_measured_worker*`` function.  A defect confined to the
# functions below therefore cannot admit a job that the Azure route would
# have rejected: an Azure workload CLI does not import them.
#
# Neither route is attestation evidence.  Both are execution-scope guards
# that stop production arithmetic from being dispatched by accident.  For the
# TDX route the security evidence is the retained Intel TDX quote, its
# external ``dcap-qvl`` appraisal, and the enclave-signed receipt.
# ---------------------------------------------------------------------------

PHALA_TDX_WORKER_SCOPE = "sparkinterval.phala-tdx-measured-worker.v1"
PHALA_TDX_WORKER_SCOPE_ENV = "SPARKINTERVAL_PHALA_TDX_WORKER_SCOPE"
PHALA_TDX_WORKER_BACKEND_ENV = "SPARKINTERVAL_PHALA_TDX_WORKER_BACKEND"
PHALA_TDX_WORKER_CHALLENGE_ENV = (
    "SPARKINTERVAL_PHALA_TDX_WORKER_CHALLENGE_NONCE"
)
PHALA_TDX_WORKER_JOB_BINDING_ENV = (
    "SPARKINTERVAL_PHALA_TDX_WORKER_JOB_BINDING_SHA256"
)
PHALA_TDX_WORKER_APP_ID_ENV = "SPARKINTERVAL_PHALA_TDX_WORKER_APP_ID"
PHALA_TDX_WORKER_COMPOSE_HASH_ENV = (
    "SPARKINTERVAL_PHALA_TDX_WORKER_COMPOSE_HASH"
)
PHALA_TDX_WORKER_BACKENDS = frozenset({"phala_dstack_tdx_cpu"})
PHALA_TDX_WORKER_ENVIRONMENT_KEYS = frozenset(
    {
        PHALA_TDX_WORKER_SCOPE_ENV,
        PHALA_TDX_WORKER_BACKEND_ENV,
        PHALA_TDX_WORKER_CHALLENGE_ENV,
        PHALA_TDX_WORKER_JOB_BINDING_ENV,
        PHALA_TDX_WORKER_APP_ID_ENV,
        PHALA_TDX_WORKER_COMPOSE_HASH_ENV,
    }
)


class PhalaTdxWorkerScopeError(CampaignIOError):
    """A production workload escaped its Phala/dstack TDX job scope."""


def _phala_tdx_lower_hex(value: object, length: int, what: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PhalaTdxWorkerScopeError(
            f"{what} must be {length} lowercase hexadecimal digits"
        )
    return value


def phala_tdx_worker_environment(
    environment: dict[str, str],
    *,
    backend: str,
    challenge_nonce: str,
    job_binding: str,
    app_id: str,
    compose_hash: str,
) -> dict[str, str]:
    """Return the exact environment for one Phala/dstack TDX campaign job.

    These variables are written by the dstack app-compose entry point after
    the launcher has fixed the campaign challenge, the job binding, the
    dstack application identity, and the app-compose hash that the TDX quote
    measures.  A job may not preseed them.
    """

    if not isinstance(environment, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in environment.items()
    ):
        raise PhalaTdxWorkerScopeError(
            "TDX job environment must map strings to strings"
        )
    overlap = PHALA_TDX_WORKER_ENVIRONMENT_KEYS.intersection(environment)
    if overlap:
        raise PhalaTdxWorkerScopeError(
            "job environment attempts to set launcher-reserved TDX scope: "
            + ", ".join(sorted(overlap))
        )
    azure_overlap = AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS.intersection(
        environment
    )
    if azure_overlap:
        raise PhalaTdxWorkerScopeError(
            "TDX job environment must not carry Azure measured-runner scope: "
            + ", ".join(sorted(azure_overlap))
        )
    if backend not in PHALA_TDX_WORKER_BACKENDS:
        raise PhalaTdxWorkerScopeError(
            f"unsupported Phala TDX worker backend: {backend!r}"
        )
    challenge = _phala_tdx_lower_hex(challenge_nonce, 64, "challenge nonce")
    binding = _phala_tdx_lower_hex(job_binding, 64, "job binding")
    application = _phala_tdx_lower_hex(app_id, 40, "dstack app id")
    compose = _phala_tdx_lower_hex(compose_hash, 64, "app-compose hash")
    return {
        **environment,
        PHALA_TDX_WORKER_SCOPE_ENV: PHALA_TDX_WORKER_SCOPE,
        PHALA_TDX_WORKER_BACKEND_ENV: backend,
        PHALA_TDX_WORKER_CHALLENGE_ENV: challenge,
        PHALA_TDX_WORKER_JOB_BINDING_ENV: binding,
        PHALA_TDX_WORKER_APP_ID_ENV: application,
        PHALA_TDX_WORKER_COMPOSE_HASH_ENV: compose,
    }


def require_phala_tdx_worker(
    *,
    challenge_nonce: str,
    job_binding: str,
    environment: dict[str, str] | None = None,
) -> dict[str, str]:
    """Fail closed unless this call is the dstack-bound TDX campaign job.

    Returns the accepted backend, dstack application id, and app-compose hash
    so the caller can bind them into the enclave-signed receipt.  This
    function never inspects, and never falls back to, the Azure
    measured-runner variables: a TDX job that carries Azure runner scope is
    rejected outright rather than silently accepted by either route.
    """

    challenge = _phala_tdx_lower_hex(challenge_nonce, 64, "challenge nonce")
    binding = _phala_tdx_lower_hex(job_binding, 64, "job binding")
    actual = os.environ if environment is None else environment
    mixed = AZURE_MEASURED_WORKER_ENVIRONMENT_KEYS.intersection(actual)
    if mixed:
        raise PhalaTdxWorkerScopeError(
            "refusing a mixed-scope job: Azure measured-runner variables are "
            "present in a Phala TDX job: " + ", ".join(sorted(mixed))
        )
    expected = {
        PHALA_TDX_WORKER_SCOPE_ENV: PHALA_TDX_WORKER_SCOPE,
        PHALA_TDX_WORKER_CHALLENGE_ENV: challenge,
        PHALA_TDX_WORKER_JOB_BINDING_ENV: binding,
    }
    for key, value in expected.items():
        if actual.get(key) != value:
            raise PhalaTdxWorkerScopeError(
                "production arithmetic/replay is enclave-only: the exact "
                f"dstack TDX job binding is absent or mismatched ({key})"
            )
    backend = actual.get(PHALA_TDX_WORKER_BACKEND_ENV)
    if backend not in PHALA_TDX_WORKER_BACKENDS:
        raise PhalaTdxWorkerScopeError(
            "production arithmetic/replay is enclave-only: Phala TDX worker "
            "backend is absent or unsupported"
        )
    return {
        "backend": backend,
        "app_id": _phala_tdx_lower_hex(
            actual.get(PHALA_TDX_WORKER_APP_ID_ENV), 40, "dstack app id"
        ),
        "compose_hash": _phala_tdx_lower_hex(
            actual.get(PHALA_TDX_WORKER_COMPOSE_HASH_ENV),
            64,
            "app-compose hash",
        ),
        "challenge_nonce": challenge,
        "job_binding": binding,
    }


def require_phala_tdx_worker_for_workload(
    *,
    exact_production: bool,
    work_bounds: tuple[int, ...],
    environment: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """Keep production and non-tiny finite work inside a dstack TDX job.

    The local-KAT allowance matches the Azure route's rule -- a non-production
    known-answer test whose every declared finite bound is at most
    ``LOCAL_KAT_MAX_WORK_ITEMS`` needs no enclave -- but the rule is restated
    here rather than shared, so that changing one route can never change the
    other.
    """

    if not isinstance(exact_production, bool):
        raise PhalaTdxWorkerScopeError("exact_production must be Boolean")
    if not isinstance(work_bounds, tuple) or any(
        isinstance(bound, bool) or not isinstance(bound, int) or bound < 0
        for bound in work_bounds
    ):
        raise PhalaTdxWorkerScopeError(
            "finite workload bounds must be nonnegative integers"
        )
    if not exact_production and not work_bounds:
        raise PhalaTdxWorkerScopeError(
            "non-production arithmetic must declare at least one finite "
            "workload bound"
        )
    if not exact_production and all(
        bound <= LOCAL_KAT_MAX_WORK_ITEMS for bound in work_bounds
    ):
        return None

    actual = os.environ if environment is None else environment
    challenge = actual.get(PHALA_TDX_WORKER_CHALLENGE_ENV)
    binding = actual.get(PHALA_TDX_WORKER_JOB_BINDING_ENV)
    if not isinstance(challenge, str) or not isinstance(binding, str):
        raise PhalaTdxWorkerScopeError(
            "production arithmetic/replay is enclave-only: dstack TDX "
            "challenge or job binding is absent"
        )
    return require_phala_tdx_worker(
        challenge_nonce=challenge,
        job_binding=binding,
        environment=actual,
    )


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CampaignIOError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_number(token: str) -> None:
    raise CampaignIOError(f"floating-point JSON is forbidden: {token}")


def _validate_json_value(value: Any, *, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        raise CampaignIOError(f"floating-point value is forbidden at {path}")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CampaignIOError(f"non-string object key at {path}")
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise CampaignIOError(f"unsupported JSON value at {path}: {type(value).__name__}")


def parse_json_bytes(raw: bytes, *, label: str = "JSON") -> Any:
    """Parse captured bytes once, rejecting duplicate keys and all floats."""

    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise CampaignIOError(f"cannot parse {label}: {exc}") from exc
    _validate_json_value(value)
    return value


def read_bytes_once(path: Path, *, limit: int = MAX_CONTROL_BYTES) -> bytes:
    """Read at most ``limit`` bytes from one opened regular file."""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise CampaignIOError("byte limit must be a positive integer")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise CampaignIOError(f"control path is not a regular file: {path}")
            chunks: list[bytes] = []
            total = 0
            while total <= limit:
                chunk = os.read(descriptor, min(1 << 20, limit + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise CampaignIOError(f"cannot read {path}: {exc}") from exc
    if len(raw) > limit:
        raise CampaignIOError(f"control file exceeds {limit} bytes: {path}")
    return raw


def load_json(path: Path, *, require_canonical: bool = False) -> Any:
    """Read and parse one JSON file, optionally requiring canonical bytes."""

    raw = read_bytes_once(path)
    value = parse_json_bytes(raw, label=str(path))
    if require_canonical and raw != canonical_json_bytes(value):
        raise CampaignIOError(f"JSON is not in canonical form: {path}")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Return the unique UTF-8 encoding used for immutable campaign records."""

    _validate_json_value(value)
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def hash_file_once(path: Path, *, limit: int | None = None) -> tuple[str, int]:
    """Hash one opened regular file, optionally enforcing a size ceiling."""

    digest = hashlib.sha256()
    total = 0
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise CampaignIOError(f"path is not a regular file: {path}")
            while True:
                chunk = os.read(descriptor, 1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if limit is not None and total > limit:
                    raise CampaignIOError(f"file exceeds {limit} bytes: {path}")
                digest.update(chunk)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise CampaignIOError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest(), total


@contextmanager
def advisory_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock on ``path`` until the context exits."""

    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise CampaignIOError(f"cannot open lock {path}: {exc}") from exc
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _replace_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", dir=path.parent, delete=False
        ) as output:
            temporary_name = output.name
            os.fchmod(output.fileno(), 0o600)
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise CampaignIOError(f"cannot atomically write {path}: {exc}") from exc
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def atomic_write_json(path: Path, value: Any) -> str:
    """Atomically replace mutable canonical JSON under a sibling lock."""

    raw = canonical_json_bytes(value)
    lock_path = path.with_name(f".{path.name}.lock")
    with advisory_lock(lock_path):
        _replace_bytes(path, raw)
    return sha256_bytes(raw)


def atomic_write_bytes(path: Path, raw: bytes) -> str:
    """Atomically replace a byte artifact under a sibling advisory lock."""

    if not isinstance(raw, bytes):
        raise CampaignIOError("atomic byte output must be bytes")
    lock_path = path.with_name(f".{path.name}.lock")
    with advisory_lock(lock_path):
        _replace_bytes(path, raw)
    return sha256_bytes(raw)


def write_immutable_json(path: Path, value: Any) -> str:
    """Create a content-addressed canonical record, refusing changed bytes."""

    raw = canonical_json_bytes(value)
    digest = sha256_bytes(raw)
    lock_path = path.with_name(f".{path.name}.lock")
    with advisory_lock(lock_path):
        if path.exists():
            existing = read_bytes_once(path)
            if existing != raw:
                raise CampaignIOError(
                    f"immutable record already exists with different bytes: {path}"
                )
            return digest
        _replace_bytes(path, raw)
    return digest
