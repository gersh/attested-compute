# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Explicitly selected native fast path for the canonical PT21 v2 artifact.

``reference/tg_platt_pt21_native_artifact_builder.cpp`` recomputes the exact
same finite work as :mod:`tg_verifier.platt_pt21_fused_artifact`: it decodes
the required-sign packet, replays every DD sign, rebuilds the direct and
stationary bracket/event streams with GMP rationals, recomputes both one-sided
Turing quotients, revalidates the finished document, and emits the canonical
``sparkinterval.tg.platt-pt21-lean-block-artifact.v2`` bytes.

The Python implementation is **not** replaced.  It remains the independent
reference oracle, the differential known-answer test requires byte equality
between the two, and this module never selects the native builder implicitly:
every entry point requires a pinned executable SHA-256.

What this module still does on every accepted native response:

* pins and seals the builder image, exactly like the packet-scan fast path;
* re-derives the artifact SHA-256 with ``hashlib`` and requires it to equal the
  digest the native builder declared in its framed response, so two independent
  SHA-256 implementations must agree;
* re-parses the returned bytes with the strict duplicate-rejecting decoder and
  requires them to be canonical JSON with exactly one trailing newline; and
* requires the bound block, window centre, packet digest, and source-trace
  digest to equal the inputs this process supplied.

``full_reference_validation=True`` additionally runs the reference exact
rational validator over the returned document.  Nothing here promotes a DD
disk, an Arb interval, a sign bit, or a digest to a theorem about Hardy Z, and
no readiness, attestation, or acceptance flag is produced or changed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import time
from typing import Any

from tg_verifier.platt_pt21_lean_artifact import (
    PT21LeanArtifactError,
    SCHEMA as ARTIFACT_SCHEMA,
    UPSTREAM_COMMIT,
    validate as validate_block_artifact,
)
from tg_verifier.platt_pt21_native_scan_fastpath import (
    EXPECTED_PACKET_BYTES,
    NativeScannerIdentity,
    PT21NativeScanFastpathError,
    _lower_sha256,
    _pinned_scanner,
    _read_exact,
    _write_all,
)


STREAM_REQUEST_MAGIC = b"PT21ABQ1"
STREAM_RESPONSE_MAGIC = b"PT21ABR1"
STREAM_REQUEST_HEADER = struct.Struct("<8sIIQQQ32s32s")
STREAM_RESPONSE_HEADER = struct.Struct("<8sIIQQQQ32s32s")
MAXIMUM_TRACE_BYTES = 16 * 1024 * 1024
MAXIMUM_ARTIFACT_BYTES = 16 * 1024 * 1024

assert STREAM_REQUEST_HEADER.size == 104
assert STREAM_RESPONSE_HEADER.size == 112


class PT21NativeArtifactFastpathError(RuntimeError):
    """The pinned native artifact builder or its output failed closed."""


@dataclass(frozen=True)
class NativeBlockArtifact:
    """One canonical v2 document produced by the pinned native builder."""

    raw: bytes
    sha256: str
    value: dict[str, Any]
    block: int
    window_center: int
    required_sign_packet_sha256: str
    source_trace_sha256: str
    builder: NativeScannerIdentity
    native_seconds: float
    python_validation_seconds: float
    full_reference_validation: bool


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PT21NativeArtifactFastpathError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def revalidate_native_artifact(
    raw: bytes,
    *,
    packet_sha256: str,
    source_trace_sha256: str,
    window_center: int,
    block: int,
    full_reference_validation: bool = False,
) -> dict[str, Any]:
    """Independently recheck one native artifact document.

    This never trusts the native builder's own framing for anything that ends
    up in the retained record: the canonical form, the bound identities, and
    (optionally) the complete exact-rational contract are rechecked here.
    """

    if not raw or len(raw) > MAXIMUM_ARTIFACT_BYTES:
        raise PT21NativeArtifactFastpathError(
            "native block artifact has an invalid byte length"
        )
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PT21NativeArtifactFastpathError(
            f"native block artifact is not strict JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise PT21NativeArtifactFastpathError(
            "native block artifact must be a JSON object"
        )
    # Compared without concatenating a second multi-megabyte copy.  A
    # duplicate key cannot survive this: the canonical form emits each key
    # once, so any repetition changes the byte length.
    if raw[-1:] != b"\n" or memoryview(raw)[:-1] != memoryview(
        _canonical(value)
    ):
        raise PT21NativeArtifactFastpathError(
            "native block artifact is not canonical JSON with one newline"
        )
    if (
        value.get("schema") != ARTIFACT_SCHEMA
        or value.get("upstream_commit") != UPSTREAM_COMMIT
        or value.get("block") != block
        or value.get("window_center") != window_center
        or value.get("required_sign_packet_sha256") != packet_sha256
        or value.get("source_trace_sha256") != source_trace_sha256
    ):
        raise PT21NativeArtifactFastpathError(
            "native block artifact identities differ from the supplied inputs"
        )
    if full_reference_validation:
        try:
            validate_block_artifact(value)
        except PT21LeanArtifactError as error:
            raise PT21NativeArtifactFastpathError(
                f"native block artifact failed reference validation: {error}"
            ) from error
    return value


def _grid_block(window_center: int) -> int:
    delta = window_center - 10_000_000_504
    if delta < 0 or delta % 1_008:
        raise PT21NativeArtifactFastpathError(
            "window centre is off the PT21 source grid"
        )
    return delta // 1_008


class NativeArtifactSession:
    """One identity-pinned, ordered builder process for many blocks."""

    def __init__(
        self,
        *,
        builder: Path,
        expected_builder_sha256: str,
    ) -> None:
        descriptor = -1
        try:
            descriptor, self.builder = _pinned_scanner(
                builder, expected_builder_sha256
            )
            executable = f"/proc/self/fd/{descriptor}"
            self._process = subprocess.Popen(
                [executable, "--stream"],
                executable=executable,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=(descriptor,),
                # Buffered pipes: each framed response is read with an exact
                # byte count, and every request is explicitly flushed.  The
                # artifact payload is megabytes, so unbuffered 64 KiB reads
                # dominate the measured response time.
                bufsize=-1,
            )
        except (OSError, ValueError, PT21NativeScanFastpathError) as error:
            raise PT21NativeArtifactFastpathError(
                f"cannot start persistent pinned native builder: {error}"
            ) from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        self._request_id = 0
        self._closed = False

    def __enter__(self) -> "NativeArtifactSession":
        return self

    def __exit__(self, *_error: object) -> None:
        self.close()

    def _failure(self, message: str) -> PT21NativeArtifactFastpathError:
        if self._process.poll() is None:
            self._process.kill()
        _stdout, stderr = self._process.communicate()
        diagnostic = stderr.decode("utf-8", errors="replace").strip()
        self._closed = True
        return PT21NativeArtifactFastpathError(
            message + (f": {diagnostic}" if diagnostic else "")
        )

    def artifact(
        self,
        raw_packet: bytes,
        raw_trace: bytes,
        *,
        full_reference_validation: bool = False,
    ) -> NativeBlockArtifact:
        """Return one ordered framed document without process startup."""

        if self._closed or self._process.poll() is not None:
            raise PT21NativeArtifactFastpathError(
                "persistent native builder is not running"
            )
        if len(raw_packet) != EXPECTED_PACKET_BYTES:
            raise PT21NativeArtifactFastpathError(
                "persistent native builder packet length differs"
            )
        if not raw_trace or len(raw_trace) > MAXIMUM_TRACE_BYTES:
            raise PT21NativeArtifactFastpathError(
                "persistent native builder source-trace length differs"
            )
        if self._request_id >= 1 << 64:
            raise PT21NativeArtifactFastpathError(
                "persistent native builder request id overflows uint64"
            )
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        packet_digest = hashlib.sha256(raw_packet).digest()
        trace_digest = hashlib.sha256(raw_trace).digest()
        request = STREAM_REQUEST_HEADER.pack(
            STREAM_REQUEST_MAGIC,
            1,
            STREAM_REQUEST_HEADER.size,
            self._request_id,
            len(raw_packet),
            len(raw_trace),
            packet_digest,
            trace_digest,
        )
        started = time.perf_counter()
        try:
            _write_all(self._process.stdin, request)
            _write_all(self._process.stdin, raw_packet)
            _write_all(self._process.stdin, raw_trace)
            self._process.stdin.flush()
            response = _read_exact(
                self._process.stdout,
                STREAM_RESPONSE_HEADER.size,
                "persistent native artifact response header",
            )
            (
                magic,
                version,
                header_bytes,
                request_id,
                artifact_bytes,
                block,
                window_center,
                response_packet_sha256,
                response_artifact_sha256,
            ) = STREAM_RESPONSE_HEADER.unpack(response)
            if (
                magic != STREAM_RESPONSE_MAGIC
                or version != 1
                or header_bytes != STREAM_RESPONSE_HEADER.size
                or request_id != self._request_id
                or artifact_bytes < 1
                or artifact_bytes > MAXIMUM_ARTIFACT_BYTES
                or response_packet_sha256 != packet_digest
            ):
                raise self._failure(
                    "persistent native artifact response framing differs"
                )
            raw = _read_exact(
                self._process.stdout,
                artifact_bytes,
                "persistent native block artifact",
            )
        except (
            BrokenPipeError,
            OSError,
            PT21NativeScanFastpathError,
            PT21NativeArtifactFastpathError,
        ) as error:
            if self._closed:
                raise
            raise self._failure(
                f"persistent native builder pipe failed: {error}"
            ) from error
        native_seconds = time.perf_counter() - started
        validation_started = time.perf_counter()
        digest = hashlib.sha256(raw)
        if digest.digest() != response_artifact_sha256:
            raise self._failure(
                "persistent native artifact response digest differs"
            )
        expected_block = _grid_block(window_center)
        if block != expected_block:
            raise self._failure(
                "persistent native artifact block differs from its centre"
            )
        value = revalidate_native_artifact(
            raw,
            packet_sha256=hashlib.sha256(raw_packet).hexdigest(),
            source_trace_sha256=hashlib.sha256(raw_trace).hexdigest(),
            window_center=window_center,
            block=block,
            full_reference_validation=full_reference_validation,
        )
        self._request_id += 1
        return NativeBlockArtifact(
            raw=raw,
            sha256=digest.hexdigest(),
            value=value,
            block=block,
            window_center=window_center,
            required_sign_packet_sha256=str(
                value["required_sign_packet_sha256"]
            ),
            source_trace_sha256=str(value["source_trace_sha256"]),
            builder=self.builder,
            native_seconds=native_seconds,
            python_validation_seconds=time.perf_counter() - validation_started,
            full_reference_validation=full_reference_validation,
        )

    def close(self) -> None:
        if self._closed:
            return
        assert self._process.stdin is not None
        try:
            self._process.stdin.close()
            self._process.stdin = None
            stdout, stderr = self._process.communicate(timeout=30)
        except subprocess.TimeoutExpired as error:
            self._process.kill()
            self._process.communicate()
            self._closed = True
            raise PT21NativeArtifactFastpathError(
                "persistent native builder did not stop at framed EOF"
            ) from error
        self._closed = True
        diagnostic = stderr.decode("utf-8", errors="replace").strip()
        if self._process.returncode != 0 or stdout or diagnostic:
            raise PT21NativeArtifactFastpathError(
                "persistent native builder rejected terminal EOF"
                + (f": {diagnostic}" if diagnostic else "")
            )


def build_block_artifact_native(
    *,
    required_sign_packet: Path,
    source_trace: Path,
    builder: Path,
    expected_builder_sha256: str,
    full_reference_validation: bool = False,
) -> NativeBlockArtifact:
    """Run one pinned one-shot native build and independently recheck it."""

    _lower_sha256(expected_builder_sha256, "expected native builder SHA-256")
    raw_packet = _regular_bytes(required_sign_packet, "required-sign packet")
    raw_trace = _regular_bytes(source_trace, "source trace")
    descriptor = -1
    try:
        descriptor, identity = _pinned_scanner(
            builder, expected_builder_sha256
        )
        executable = f"/proc/self/fd/{descriptor}"
        started = time.perf_counter()
        completed = subprocess.run(
            [
                executable,
                "--required-sign-packet",
                str(required_sign_packet),
                "--source-trace",
                str(source_trace),
            ],
            executable=executable,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            pass_fds=(descriptor,),
            check=False,
        )
        native_seconds = time.perf_counter() - started
    except (OSError, ValueError, PT21NativeScanFastpathError) as error:
        raise PT21NativeArtifactFastpathError(
            f"cannot run the pinned native builder: {error}"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    diagnostic = completed.stderr.decode("utf-8", errors="replace").strip()
    if completed.returncode != 0 or diagnostic:
        raise PT21NativeArtifactFastpathError(
            "pinned native builder failed closed"
            + (f": {diagnostic}" if diagnostic else "")
        )
    raw = completed.stdout
    validation_started = time.perf_counter()
    packet_sha256 = hashlib.sha256(raw_packet).hexdigest()
    trace_sha256 = hashlib.sha256(raw_trace).hexdigest()
    window_center = _window_center(raw_packet)
    block = _grid_block(window_center)
    value = revalidate_native_artifact(
        raw,
        packet_sha256=packet_sha256,
        source_trace_sha256=trace_sha256,
        window_center=window_center,
        block=block,
        full_reference_validation=full_reference_validation,
    )
    return NativeBlockArtifact(
        raw=raw,
        sha256=hashlib.sha256(raw).hexdigest(),
        value=value,
        block=block,
        window_center=window_center,
        required_sign_packet_sha256=packet_sha256,
        source_trace_sha256=trace_sha256,
        builder=identity,
        native_seconds=native_seconds,
        python_validation_seconds=time.perf_counter() - validation_started,
        full_reference_validation=full_reference_validation,
    )


def _window_center(raw_packet: bytes) -> int:
    if len(raw_packet) != EXPECTED_PACKET_BYTES:
        raise PT21NativeArtifactFastpathError(
            "required-sign packet byte length differs"
        )
    return int.from_bytes(raw_packet[48:56], "little")


def _regular_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PT21NativeArtifactFastpathError(
            f"{label} is not a regular file: {path}"
        )
    raw = path.read_bytes()
    if not raw:
        raise PT21NativeArtifactFastpathError(f"{label} is empty")
    return raw


__all__ = [
    "MAXIMUM_ARTIFACT_BYTES",
    "MAXIMUM_TRACE_BYTES",
    "NativeArtifactSession",
    "NativeBlockArtifact",
    "PT21NativeArtifactFastpathError",
    "STREAM_REQUEST_HEADER",
    "STREAM_REQUEST_MAGIC",
    "STREAM_RESPONSE_HEADER",
    "STREAM_RESPONSE_MAGIC",
    "build_block_artifact_native",
    "revalidate_native_artifact",
]
