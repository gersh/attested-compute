# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Resumable exact producer for the CH25 Chebyshev-psi finite campaign.

Receipts retain compact event-stream commitments and directed prefix states,
not hundreds of billions of prime-power rows.  The producer verifies each
chunk before retention; ``replay_campaign`` independently regenerates the
prime powers and rational logarithms from the captured configuration.  A full
run is computationally prohibitive in this Python implementation, but the
source endpoint, coverage rule, resume state, and final strict inequality are
all executable without changing modes or silently sampling.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import platform
import re
from typing import Any, Mapping, Sequence

from . import finite_campaigns
from .campaign_io import advisory_lock, atomic_write_bytes, hash_file_once
from .evidence import EvidenceError, load_decimal_json_bytes
from .finite_campaigns import (
    PSI_ALGORITHM,
    PSI_ATOM,
    PSI_SOURCE_LIMIT,
    PsiChunk,
    create_psi_chunk,
    verify_psi_chunk,
)
from .arithmetic import ZERO_SHA256


CAMPAIGN_ALGORITHM = "psi_prime_power_resumable_campaign_v1"
EVENT_DIGEST_ENCODING = "psi-event-decimal-lines-v1"
# sum_{k >= 1} pi(floor((10^13)^(1/k))); the final nonzero term is k=43.
# This is the exact number of distinct (prime, exponent) jumps replayed by the
# source campaign, not an estimate of the number of primes.
SOURCE_EVENT_COUNT = 346_065_767_406
CONFIG_NAME = "campaign-config.json"
MANIFEST_NAME = "campaign-manifest.json"
MAX_CONTROL_BYTES = 4 << 20
_RECEIPT_NAME = re.compile(r"receipt-([0-9]{8})\.json")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class PsiCampaignError(RuntimeError):
    """A psi campaign parameter, receipt, or replay failed closed."""


@dataclass(frozen=True)
class PsiCampaignResult:
    endpoint: int
    completed_upper: int
    receipts: int
    prime_power_events: int
    complete: bool
    final_lower: int
    final_upper: int
    final_chunk_hash: str
    final_receipt_hash: str
    source_sha256: str
    locally_supervised_execution: bool
    fresh_arithmetic_replay: bool
    execution_attested: bool = False
    lean_atom_discharged: bool = False

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def _read(path: Path, label: str) -> bytes:
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_CONTROL_BYTES + 1)
    except OSError as exc:
        raise PsiCampaignError(f"cannot read {label} {path}: {exc}") from exc
    if len(raw) > MAX_CONTROL_BYTES:
        raise PsiCampaignError(f"{label} exceeds the local byte limit")
    return raw


def _parse(raw: bytes, label: str) -> dict[str, Any]:
    try:
        return load_decimal_json_bytes(raw, label=label)
    except EvidenceError as exc:
        raise PsiCampaignError(str(exc)) from exc


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise PsiCampaignError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _integer(value: object, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PsiCampaignError(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise PsiCampaignError(f"{name} must be at least {minimum}")
    return value


def _source_sha256() -> str:
    digest, _ = hash_file_once(Path(finite_campaigns.__file__).resolve())
    return digest


def _validate_parameters(
    chunk_span: int,
    scale_bits: int,
    series_terms: int,
    segment_size: int,
    max_chunks: int | None,
) -> None:
    for value, name, lower, upper in (
        (chunk_span, "chunk_span", 1, 100_000_000),
        (scale_bits, "scale_bits", 1, 4_096),
        (series_terms, "series_terms", 1, 4_096),
        (segment_size, "segment_size", 1, 100_000_000),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
            raise PsiCampaignError(f"{name} must lie in [{lower}, {upper}]")
    if max_chunks is not None and (
        isinstance(max_chunks, bool)
        or not isinstance(max_chunks, int)
        or max_chunks < 1
    ):
        raise PsiCampaignError("max_chunks must be positive or null")


def _expected_config(
    *, chunk_span: int, scale_bits: int, series_terms: int, segment_size: int
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "algorithm": CAMPAIGN_ALGORITHM,
        "classification": "resumable_exact_external_computation_not_lean_proof",
        "atom_id": PSI_ATOM,
        "chunk_algorithm": PSI_ALGORITHM,
        "endpoint": PSI_SOURCE_LIMIT,
        "source_prime_power_event_count": SOURCE_EVENT_COUNT,
        "chunk_span": chunk_span,
        "scale_bits": scale_bits,
        "series_terms": series_terms,
        "segment_size": segment_size,
        "event_digest_encoding": EVENT_DIGEST_ENCODING,
        "finite_campaigns_source_sha256": _source_sha256(),
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
    }


def _initialize_or_check(
    output_directory: Path,
    *, chunk_span: int,
    scale_bits: int,
    series_terms: int,
    segment_size: int,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    config_path = output_directory / CONFIG_NAME
    expected = _expected_config(
        chunk_span=chunk_span,
        scale_bits=scale_bits,
        series_terms=series_terms,
        segment_size=segment_size,
    )
    if config_path.exists():
        config = _parse(_read(config_path, "config"), str(config_path))
        if config != expected:
            raise PsiCampaignError("resume configuration or source identity changed")
    else:
        atomic_write_bytes(config_path, _json_bytes(expected))
    return expected


def _event_digest(chunk: PsiChunk) -> str:
    digest = hashlib.sha256()
    digest.update(EVENT_DIGEST_ENCODING.encode("ascii") + b"\0")
    for event in chunk.events:
        digest.update(
            (
                f"{event.value}:{event.prime}:{event.exponent}:"
                f"{event.log_lower}:{event.log_upper}\n"
            ).encode("ascii")
        )
    return digest.hexdigest()


def _receipt_body(
    chunk: PsiChunk,
    *, event_count: int,
    event_digest: str,
    previous_receipt_hash: str,
    source_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "algorithm": CAMPAIGN_ALGORITHM,
        "classification": "exact_verified_chunk_local_execution_not_lean_proof",
        "atom_id": PSI_ATOM,
        "lower": chunk.lower,
        "upper": chunk.upper,
        "scale_bits": chunk.scale_bits,
        "series_terms": chunk.series_terms,
        "incoming_lower": chunk.incoming_lower,
        "incoming_upper": chunk.incoming_upper,
        "outgoing_lower": chunk.outgoing_lower,
        "outgoing_upper": chunk.outgoing_upper,
        "event_count": event_count,
        "event_digest_encoding": EVENT_DIGEST_ENCODING,
        "event_digest": event_digest,
        "previous_chunk_hash": chunk.previous_hash,
        "chunk_record_hash": chunk.record_hash,
        "previous_receipt_hash": previous_receipt_hash,
        "finite_campaigns_source_sha256": source_sha256,
        "producer_replayed_every_event_and_envelope": True,
        "execution_attested": False,
        "lean_atom_discharged": False,
    }


def _make_receipt(
    chunk: PsiChunk, *, event_count: int, previous_receipt_hash: str, source_sha256: str
) -> dict[str, Any]:
    body = _receipt_body(
        chunk,
        event_count=event_count,
        event_digest=_event_digest(chunk),
        previous_receipt_hash=previous_receipt_hash,
        source_sha256=source_sha256,
    )
    return {**body, "receipt_hash": _sha256(_json_bytes(body))}


def _validate_receipt(report: Mapping[str, Any]) -> None:
    expected_fields = set(
        _receipt_body(
            PsiChunk(2, 3, 1, 1, 0, 0, 0, 0, (), ZERO_SHA256, ZERO_SHA256),
            event_count=0,
            event_digest=ZERO_SHA256,
            previous_receipt_hash=ZERO_SHA256,
            source_sha256=ZERO_SHA256,
        )
    ) | {"receipt_hash"}
    if not isinstance(report, Mapping) or set(report) != expected_fields:
        raise PsiCampaignError("receipt fields changed")
    if report.get("schema_version") != 1 or report.get("algorithm") != CAMPAIGN_ALGORITHM:
        raise PsiCampaignError("unsupported receipt schema or algorithm")
    if report.get("classification") != "exact_verified_chunk_local_execution_not_lean_proof":
        raise PsiCampaignError("receipt classification changed")
    if report.get("atom_id") != PSI_ATOM:
        raise PsiCampaignError("receipt atom changed")
    lower = _integer(report.get("lower"), "lower", minimum=2)
    upper = _integer(report.get("upper"), "upper", minimum=3)
    if not lower < upper <= PSI_SOURCE_LIMIT + 1:
        raise PsiCampaignError("receipt range is outside the source domain")
    for name in (
        "scale_bits",
        "series_terms",
        "incoming_lower",
        "incoming_upper",
        "outgoing_lower",
        "outgoing_upper",
        "event_count",
    ):
        _integer(report.get(name), name, minimum=0)
    if report["scale_bits"] < 1 or report["series_terms"] < 1:
        raise PsiCampaignError("receipt numerical configuration is invalid")
    if report["incoming_lower"] > report["incoming_upper"] or (
        report["outgoing_lower"] > report["outgoing_upper"]
    ):
        raise PsiCampaignError("receipt directed state is reversed")
    if report.get("event_digest_encoding") != EVENT_DIGEST_ENCODING:
        raise PsiCampaignError("event digest encoding changed")
    for name in (
        "event_digest",
        "previous_chunk_hash",
        "chunk_record_hash",
        "previous_receipt_hash",
        "finite_campaigns_source_sha256",
        "receipt_hash",
    ):
        _digest(report.get(name), name)
    for name in ("execution_attested", "lean_atom_discharged"):
        if report.get(name) is not False:
            raise PsiCampaignError(f"unsafe receipt claim in {name}")
    if report.get("producer_replayed_every_event_and_envelope") is not True:
        raise PsiCampaignError("producer replay assertion is absent")
    body = {key: value for key, value in report.items() if key != "receipt_hash"}
    if report["receipt_hash"] != _sha256(_json_bytes(body)):
        raise PsiCampaignError("receipt canonical hash is invalid")


def _paths(output_directory: Path) -> list[Path]:
    indexed: list[tuple[int, Path]] = []
    for path in output_directory.glob("receipt-*.json"):
        match = _RECEIPT_NAME.fullmatch(path.name)
        if match is None or not path.is_file():
            raise PsiCampaignError(f"malformed receipt path {path.name!r}")
        indexed.append((int(match.group(1)), path))
    indexed.sort()
    if [index for index, _ in indexed] != list(range(len(indexed))):
        raise PsiCampaignError("receipt indices are not consecutive")
    return [path for _, path in indexed]


def _load_receipts(output_directory: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in _paths(output_directory):
        report = _parse(_read(path, "receipt"), str(path))
        _validate_receipt(report)
        result.append(report)
    return result


def _check_chain(reports: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> None:
    previous: Mapping[str, Any] | None = None
    for index, report in enumerate(reports):
        _validate_receipt(report)
        expected_lower = 2 if previous is None else previous["upper"]
        if report["lower"] != expected_lower:
            raise PsiCampaignError(f"receipt {index} breaks range coverage")
        expected_span = min(config["chunk_span"], PSI_SOURCE_LIMIT - expected_lower + 1)
        if report["upper"] - report["lower"] != expected_span:
            raise PsiCampaignError(f"receipt {index} has the wrong chunk span")
        expected_state = (0, 0) if previous is None else (
            previous["outgoing_lower"],
            previous["outgoing_upper"],
        )
        expected_chunk_hash = ZERO_SHA256 if previous is None else previous["chunk_record_hash"]
        expected_receipt_hash = ZERO_SHA256 if previous is None else previous["receipt_hash"]
        if (report["incoming_lower"], report["incoming_upper"]) != expected_state:
            raise PsiCampaignError(f"receipt {index} breaks directed state linkage")
        if report["previous_chunk_hash"] != expected_chunk_hash or (
            report["previous_receipt_hash"] != expected_receipt_hash
        ):
            raise PsiCampaignError(f"receipt {index} breaks hash linkage")
        if (report["scale_bits"], report["series_terms"]) != (
            config["scale_bits"],
            config["series_terms"],
        ):
            raise PsiCampaignError(f"receipt {index} changes the configuration")
        if report["finite_campaigns_source_sha256"] != config["finite_campaigns_source_sha256"]:
            raise PsiCampaignError(f"receipt {index} changes the source identity")
        previous = report


def _terminal_holds(report: Mapping[str, Any], config: Mapping[str, Any]) -> bool:
    if report["upper"] != PSI_SOURCE_LIMIT + 1:
        return False
    scale = 1 << config["scale_bits"]
    difference = PSI_SOURCE_LIMIT * scale - report["outgoing_lower"]
    return difference <= 0 or (
        difference * difference < 2 * PSI_SOURCE_LIMIT * scale * scale
    )


def _result(
    config: Mapping[str, Any], reports: Sequence[Mapping[str, Any]], *, local: bool, replay: bool
) -> PsiCampaignResult:
    last = None if not reports else reports[-1]
    completed = 1 if last is None else last["upper"] - 1
    event_count = sum(report["event_count"] for report in reports)
    complete = (
        last is not None
        and completed == PSI_SOURCE_LIMIT
        and event_count == SOURCE_EVENT_COUNT
        and _terminal_holds(last, config)
    )
    return PsiCampaignResult(
        endpoint=PSI_SOURCE_LIMIT,
        completed_upper=completed,
        receipts=len(reports),
        prime_power_events=event_count,
        complete=complete,
        final_lower=0 if last is None else last["outgoing_lower"],
        final_upper=0 if last is None else last["outgoing_upper"],
        final_chunk_hash=ZERO_SHA256 if last is None else last["chunk_record_hash"],
        final_receipt_hash=ZERO_SHA256 if last is None else last["receipt_hash"],
        source_sha256=config["finite_campaigns_source_sha256"],
        locally_supervised_execution=local,
        fresh_arithmetic_replay=replay,
    )


def _load_config(output_directory: Path) -> dict[str, Any]:
    path = output_directory / CONFIG_NAME
    config = _parse(_read(path, "config"), str(path))
    required = set(_expected_config(chunk_span=1, scale_bits=1, series_terms=1, segment_size=1))
    if set(config) != required:
        raise PsiCampaignError("campaign config fields changed")
    _validate_parameters(
        config.get("chunk_span"),
        config.get("scale_bits"),
        config.get("series_terms"),
        config.get("segment_size"),
        None,
    )
    expected = _expected_config(
        chunk_span=config["chunk_span"],
        scale_bits=config["scale_bits"],
        series_terms=config["series_terms"],
        segment_size=config["segment_size"],
    )
    if config != expected:
        raise PsiCampaignError("campaign config or arithmetic source changed")
    return config


def verify_campaign(output_directory: Path) -> PsiCampaignResult:
    """Verify compact receipt structure and the gap-free state/hash chain."""

    config = _load_config(output_directory)
    reports = _load_receipts(output_directory)
    _check_chain(reports, config)
    result = _result(config, reports, local=False, replay=False)
    manifest_path = output_directory / MANIFEST_NAME
    if manifest_path.exists():
        manifest = _parse(_read(manifest_path, "manifest"), str(manifest_path))
        expected = result.as_json()
        expected["locally_supervised_execution"] = True
        if manifest not in (result.as_json(), expected):
            raise PsiCampaignError("campaign manifest disagrees with receipts")
    return result


def replay_campaign(
    output_directory: Path, *, max_chunks: int | None = None
) -> PsiCampaignResult:
    """Regenerate and compare every selected compact receipt from integers."""

    if max_chunks is not None and (
        isinstance(max_chunks, bool)
        or not isinstance(max_chunks, int)
        or max_chunks < 1
    ):
        raise PsiCampaignError("max_chunks must be positive or null")
    config = _load_config(output_directory)
    reports = _load_receipts(output_directory)
    _check_chain(reports, config)
    selected = reports if max_chunks is None else reports[:max_chunks]
    for index, report in enumerate(selected):
        chunk = create_psi_chunk(
            lower=report["lower"],
            upper=report["upper"],
            scale_bits=config["scale_bits"],
            series_terms=config["series_terms"],
            incoming_lower=report["incoming_lower"],
            incoming_upper=report["incoming_upper"],
            previous_hash=report["previous_chunk_hash"],
            segment_size=config["segment_size"],
        )
        events, _, _ = verify_psi_chunk(chunk, segment_size=config["segment_size"])
        expected = _make_receipt(
            chunk,
            event_count=events,
            previous_receipt_hash=report["previous_receipt_hash"],
            source_sha256=config["finite_campaigns_source_sha256"],
        )
        if report != expected:
            raise PsiCampaignError(f"fresh arithmetic replay differs at chunk {index}")
    replayed_every_retained_receipt = bool(reports) and len(selected) == len(reports)
    return _result(
        config,
        reports,
        local=False,
        replay=replayed_every_retained_receipt,
    )


def run_campaign(
    output_directory: Path,
    *,
    chunk_span: int = 1_000_000,
    scale_bits: int = 128,
    series_terms: int = 48,
    segment_size: int = 1_000_000,
    max_chunks: int | None = None,
) -> PsiCampaignResult:
    """Start or resume the literal source-range exact Python campaign."""

    _validate_parameters(chunk_span, scale_bits, series_terms, segment_size, max_chunks)
    output_directory.mkdir(parents=True, exist_ok=True)
    with advisory_lock(output_directory / ".psi-campaign.lock"):
        config = _initialize_or_check(
            output_directory,
            chunk_span=chunk_span,
            scale_bits=scale_bits,
            series_terms=series_terms,
            segment_size=segment_size,
        )
        reports = _load_receipts(output_directory)
        _check_chain(reports, config)
        chunks_run = 0
        while (not reports or reports[-1]["upper"] <= PSI_SOURCE_LIMIT) and (
            max_chunks is None or chunks_run < max_chunks
        ):
            lower = 2 if not reports else reports[-1]["upper"]
            if lower > PSI_SOURCE_LIMIT:
                break
            upper = min(PSI_SOURCE_LIMIT + 1, lower + chunk_span)
            chunk = create_psi_chunk(
                lower=lower,
                upper=upper,
                scale_bits=scale_bits,
                series_terms=series_terms,
                incoming_lower=0 if not reports else reports[-1]["outgoing_lower"],
                incoming_upper=0 if not reports else reports[-1]["outgoing_upper"],
                previous_hash=ZERO_SHA256 if not reports else reports[-1]["chunk_record_hash"],
                segment_size=segment_size,
            )
            event_count, _, _ = verify_psi_chunk(chunk, segment_size=segment_size)
            report = _make_receipt(
                chunk,
                event_count=event_count,
                previous_receipt_hash=ZERO_SHA256 if not reports else reports[-1]["receipt_hash"],
                source_sha256=config["finite_campaigns_source_sha256"],
            )
            _validate_receipt(report)
            path = output_directory / f"receipt-{len(reports):08d}.json"
            if path.exists():
                raise PsiCampaignError("refusing to replace an existing receipt")
            atomic_write_bytes(path, _json_bytes(report))
            reports.append(report)
            chunks_run += 1
        _check_chain(reports, config)
        result = _result(config, reports, local=True, replay=False)
        atomic_write_bytes(output_directory / MANIFEST_NAME, _json_bytes(result.as_json()))
        return result
