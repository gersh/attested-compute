# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Native Helfgott--Platt Proth producer with independent Python replay.

The C++/GMP executable is an untrusted producer.  This module rejects its
output unless every compact record replays with Python's exact Jacobi and
modular-power operations, then writes the already established ``.tggl`` range
format and its independent range receipt.  A native ``complete=false`` result
is an explicit request for a separately certified general prime; it is never
silently converted into a primality assertion.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import BinaryIO, Iterator, Mapping

from .goldbach_campaign import (
    CampaignError,
    CampaignParameters,
    PROTH_EXPONENT,
    Rung,
    SOURCE_PROTH_WITNESSES,
    SOURCE_SIEVE_BOUND,
    ZERO_HASH,
    _install_immutable_range,
    _produce_boundary_rung,
    _produce_certified_prime,
    _write_immutable_json,
    canonical_json_bytes,
    campaign_atom_id,
    ANALYTIC_10POW27_MODE,
    analytic_10pow27_parameters,
    check_proth,
    emit_independent_receipt,
    independent_group_bounds,
    independent_range_filename,
    load_campaign,
    sha256_file,
    write_range_file,
)


MAGIC = b"TGNPLD1\n"
SEGMENT_KIND = "tg_goldbach_native_proth_segment_v1"
REPORT_KIND = "tg_goldbach_native_proth_report_v1"
NATIVE_RECEIPT_KIND = "tg_goldbach_native_range_producer_receipt_v1"
NATIVE_GROUP_KIND = "tg_goldbach_native_worker_group_result_v1"
NATIVE_SCHEMA = "tg_goldbach_native_ladder_v1"
SOURCE_RELATIVE_PATH = "reference/tg_goldbach_ladder_native.cpp"
MAX_HEADER_BYTES = 1 << 20
_NATIVE_RECEIPT_DOMAIN = b"tg/goldbach-ladder/native-producer-receipt/v1\x00"


def _source_path() -> Path:
    return Path(__file__).resolve().parents[1] / SOURCE_RELATIVE_PATH


def native_receipt_filename(index: int) -> str:
    return f"native-producer-{index:06d}.json"


def _decimal(value: object, field: str) -> int:
    if (
        not isinstance(value, str)
        or not value
        or not value.isascii()
        or not value.isdigit()
        or (len(value) > 1 and value[0] == "0")
    ):
        raise CampaignError(f"native {field} must be a canonical decimal string")
    return int(value)


def _hex_digest(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CampaignError(f"native {field} must be a lowercase SHA-256 digest")
    return value


def _read_u64_le(stream: BinaryIO) -> int:
    raw = stream.read(8)
    if len(raw) != 8:
        raise CampaignError("truncated native protocol header length")
    return int.from_bytes(raw, "little")


def _read_u64_varint(stream: BinaryIO) -> int:
    value = 0
    for offset in range(10):
        raw = stream.read(1)
        if len(raw) != 1:
            raise CampaignError("truncated native protocol varint")
        octet = raw[0]
        if offset == 9 and octet > 1:
            raise CampaignError("native protocol varint exceeds uint64")
        value |= (octet & 0x7F) << (7 * offset)
        if octet < 0x80:
            if offset and octet == 0:
                raise CampaignError("noncanonical native protocol varint")
            return value
    raise CampaignError("native protocol varint exceeds uint64")


@dataclass(frozen=True)
class NativeHeader:
    anchor_number: int
    complete: bool
    coverage_step: int
    gmp_version: str
    hole_lower_exclusive: int | None
    hole_upper_inclusive: int | None
    last_number: int
    proth_exponent: int
    record_count: int
    source_sha256: str
    target_number: int


@dataclass(frozen=True)
class NativeRun:
    """One immutable native segment plus its noncertificate run statistics."""

    path: Path
    header: NativeHeader
    protocol_sha256: str
    report: Mapping[str, object]
    runner_sha256: str

    def checked_rungs(self) -> Iterator[Rung]:
        """Replay every GMP-produced rung independently with Python integers."""

        with self.path.open("rb") as stream:
            header = _read_header(stream)
            if header != self.header:
                raise CampaignError("native protocol header changed after invocation")
            previous_k = 0
            previous_number = header.anchor_number
            for _ordinal in range(header.record_count):
                delta = _read_u64_varint(stream)
                if delta == 0 or previous_k > (1 << 64) - 1 - delta:
                    raise CampaignError("native rung k is not strictly increasing")
                k = previous_k + delta
                raw_witness = stream.read(1)
                if len(raw_witness) != 1:
                    raise CampaignError("truncated native Proth witness")
                witness = raw_witness[0]
                proth_power = 1 << header.proth_exponent
                if not 0 < k < proth_power:
                    raise CampaignError("native rung violates 0 < k < 2^n")
                number = k * proth_power + 1
                if not previous_number < number <= previous_number + header.coverage_step:
                    raise CampaignError("native rung violates exact ladder coverage")
                if witness not in SOURCE_PROTH_WITNESSES:
                    raise CampaignError("native rung uses an unapproved source witness")
                if not check_proth(number, witness, header.proth_exponent):
                    raise CampaignError("native Proth certificate failed independent replay")
                previous_k = k
                previous_number = number
                kind = "proth52" if header.proth_exponent == PROTH_EXPONENT else "proth"
                yield Rung(number, kind, witness=witness)
            if stream.read(1):
                raise CampaignError("native protocol has trailing bytes")
        if previous_number != header.last_number:
            raise CampaignError("native protocol last-number summary is false")
        if header.complete:
            if header.target_number - previous_number > header.coverage_step:
                raise CampaignError("native complete flag leaves a ladder gap")
        else:
            if (
                header.hole_lower_exclusive != previous_number
                or header.hole_upper_inclusive
                != previous_number + header.coverage_step
                or header.target_number - previous_number <= header.coverage_step
            ):
                raise CampaignError("native general-prime obligation is malformed")


def _read_header(stream: BinaryIO) -> NativeHeader:
    if stream.read(len(MAGIC)) != MAGIC:
        raise CampaignError("wrong native Goldbach protocol magic")
    header_length = _read_u64_le(stream)
    if not 1 <= header_length <= MAX_HEADER_BYTES:
        raise CampaignError("invalid native protocol header length")
    raw = stream.read(header_length)
    if len(raw) != header_length:
        raise CampaignError("truncated native protocol header")
    try:
        root = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignError("invalid native protocol JSON header") from exc
    if raw != canonical_json_bytes(root):
        raise CampaignError("native protocol JSON header is not canonical")
    expected = {
        "anchor_number",
        "complete",
        "coverage_step",
        "gmp_version",
        "hole_lower_exclusive",
        "hole_upper_inclusive",
        "kind",
        "last_number",
        "proth_exponent",
        "record_count",
        "sieve_bound",
        "source_sha256",
        "target_number",
        "witnesses",
    }
    if not isinstance(root, dict) or set(root) != expected:
        raise CampaignError("native protocol header field set mismatch")
    exponent = root["proth_exponent"]
    if (
        root["kind"] != SEGMENT_KIND
        or root["sieve_bound"] != SOURCE_SIEVE_BOUND
        or root["witnesses"] != list(SOURCE_PROTH_WITNESSES)
    ):
        raise CampaignError("native protocol source constants mismatch")
    complete = root["complete"]
    count = root["record_count"]
    version = root["gmp_version"]
    if (
        not isinstance(complete, bool)
        or not isinstance(exponent, int)
        or isinstance(exponent, bool)
        or not 1 <= exponent <= 63
        or not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        or not isinstance(version, str)
        or not version
        or len(version) > 64
        or not version.isascii()
    ):
        raise CampaignError("native protocol metadata type mismatch")
    hole_lower = root["hole_lower_exclusive"]
    hole_upper = root["hole_upper_inclusive"]
    if complete:
        if hole_lower is not None or hole_upper is not None:
            raise CampaignError("complete native segment reports a hole")
        parsed_lower = None
        parsed_upper = None
    else:
        parsed_lower = _decimal(hole_lower, "hole_lower_exclusive")
        parsed_upper = _decimal(hole_upper, "hole_upper_inclusive")
    return NativeHeader(
        anchor_number=_decimal(root["anchor_number"], "anchor_number"),
        complete=complete,
        coverage_step=_decimal(root["coverage_step"], "coverage_step"),
        gmp_version=version,
        hole_lower_exclusive=parsed_lower,
        hole_upper_inclusive=parsed_upper,
        last_number=_decimal(root["last_number"], "last_number"),
        proth_exponent=exponent,
        record_count=count,
        source_sha256=_hex_digest(root["source_sha256"], "source_sha256"),
        target_number=_decimal(root["target_number"], "target_number"),
    )


def read_native_header(path: Path) -> NativeHeader:
    with path.open("rb") as stream:
        return _read_header(stream)


def _validate_report(root: object, header: NativeHeader) -> Mapping[str, object]:
    expected = {
        "blocks_sieved",
        "candidates_examined",
        "candidates_sieved",
        "complete",
        "elapsed_seconds",
        "kind",
        "record_count",
        "sieve_survivors_tested",
    }
    if not isinstance(root, dict) or set(root) != expected:
        raise CampaignError("native runner report field set mismatch")
    counters = (
        "blocks_sieved",
        "candidates_examined",
        "candidates_sieved",
        "record_count",
        "sieve_survivors_tested",
    )
    if any(
        not isinstance(root[field], int)
        or isinstance(root[field], bool)
        or root[field] < 0
        for field in counters
    ):
        raise CampaignError("native runner report has an invalid counter")
    elapsed = root["elapsed_seconds"]
    try:
        parsed_elapsed = float(elapsed) if isinstance(elapsed, str) else -1.0
    except ValueError as exc:
        raise CampaignError("native runner elapsed time is invalid") from exc
    if (
        root["kind"] != REPORT_KIND
        or root["complete"] is not header.complete
        or root["record_count"] != header.record_count
        or not parsed_elapsed >= 0.0
    ):
        raise CampaignError("native runner report contradicts its protocol")
    return root


@contextmanager
def invoke_native_segment(
    runner: Path,
    *,
    anchor_number: int,
    target_number: int,
    coverage_step: int,
    proth_exponent: int = PROTH_EXPONENT,
    sieve_block_candidates: int = 1 << 24,
    temporary_parent: Path | None = None,
) -> Iterator[NativeRun]:
    """Run one native segment and bind/replay its deterministic protocol."""

    runner = runner.resolve()
    source = _source_path()
    if not runner.is_file() or not os.access(runner, os.X_OK):
        raise CampaignError("native ladder runner must be an executable file")
    if not source.is_file():
        raise CampaignError("reviewed native ladder source is missing")
    source_hash = sha256_file(source)
    runner_hash = sha256_file(runner)
    with tempfile.TemporaryDirectory(
        prefix="tg-goldbach-native-", dir=temporary_parent
    ) as temporary:
        protocol = Path(temporary) / "segment.tgnp"
        completed = subprocess.run(
            [
                str(runner),
                "--anchor-number",
                str(anchor_number),
                "--target-number",
                str(target_number),
                "--coverage-step",
                str(coverage_step),
                "--proth-exponent",
                str(proth_exponent),
                "--sieve-block-candidates",
                str(sieve_block_candidates),
                "--output",
                str(protocol),
            ],
            check=False,
            capture_output=True,
            timeout=24 * 3600,
        )
        if completed.returncode != 0 or completed.stderr:
            message = completed.stderr.decode("utf-8", errors="replace").strip()
            raise CampaignError(f"native ladder runner failed: {message}")
        if not protocol.is_file():
            raise CampaignError("native ladder runner omitted its protocol")
        header = read_native_header(protocol)
        if (
            header.anchor_number != anchor_number
            or header.target_number != target_number
            or header.coverage_step != coverage_step
            or header.proth_exponent != proth_exponent
        ):
            raise CampaignError("native runner changed the requested segment")
        if header.source_sha256 != source_hash:
            raise CampaignError(
                "native runner was not rebuilt from the reviewed source identity"
            )
        try:
            report_raw = json.loads(completed.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CampaignError("native runner did not emit one JSON report") from exc
        if completed.stdout != canonical_json_bytes(report_raw):
            raise CampaignError("native runner report is not canonical JSON")
        report = _validate_report(report_raw, header)
        run = NativeRun(
            path=protocol,
            header=header,
            protocol_sha256=sha256_file(protocol),
            report=report,
            runner_sha256=runner_hash,
        )
        yield run


def _native_receipt_core(
    *,
    directory: Path,
    index: int,
    range_receipt: Mapping[str, object],
    runner_hash: str,
    source_hash: str,
    segment_hashes: list[str],
    segment_headers: list[NativeHeader],
    general_gap_count: int,
) -> dict[str, object]:
    return {
        "atom_id": campaign_atom_id(load_campaign(directory)),
        "execution_attested": False,
        "general_prime_gap_count": general_gap_count,
        "index": index,
        "kind": NATIVE_RECEIPT_KIND,
        "native_protocol_sha256s": segment_hashes,
        "native_segment_count": len(segment_hashes),
        "producer_complete": True,
        "range_file_sha256": range_receipt["range_file_sha256"],
        "range_receipt_sha256": range_receipt["receipt_sha256"],
        "reviewed_source_path": SOURCE_RELATIVE_PATH,
        "reviewed_source_sha256": source_hash,
        "runner_sha256": runner_hash,
        "schema": NATIVE_SCHEMA,
        "segment_gmp_versions": sorted(
            {header.gmp_version for header in segment_headers}
        ),
        "verification_note": (
            "Every native Proth record was independently replayed with Python "
            "integer arithmetic before the ordinary range receipt was emitted."
        ),
    }


def _validate_native_receipt(
    path: Path, *, index: int, range_receipt: Mapping[str, object], runner: Path
) -> dict[str, object]:
    raw = path.read_bytes()
    try:
        root = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CampaignError("invalid native producer receipt JSON") from exc
    if raw != canonical_json_bytes(root) or not isinstance(root, dict):
        raise CampaignError("native producer receipt is not canonical JSON")
    digest = root.get("native_receipt_sha256")
    core = dict(root)
    core.pop("native_receipt_sha256", None)
    expected_digest = hashlib.sha256(
        _NATIVE_RECEIPT_DOMAIN + canonical_json_bytes(core)
    ).hexdigest()
    if digest != expected_digest:
        raise CampaignError("native producer receipt digest mismatch")
    if (
        core.get("kind") != NATIVE_RECEIPT_KIND
        or core.get("schema") != NATIVE_SCHEMA
        or core.get("index") != index
        or core.get("range_receipt_sha256") != range_receipt["receipt_sha256"]
        or core.get("range_file_sha256") != range_receipt["range_file_sha256"]
        or core.get("runner_sha256") != sha256_file(runner.resolve())
        or core.get("reviewed_source_sha256") != sha256_file(_source_path())
    ):
        raise CampaignError("native producer receipt identity mismatch")
    return root


def produce_native_independent_range(
    directory: Path,
    index: int,
    *,
    runner: Path,
    general_prime_producer: Path | None = None,
    external_prime_checker: Path | None = None,
    builtin_pocklington: bool = True,
    sieve_block_candidates: int = 1 << 24,
) -> tuple[dict[str, object], dict[str, object]]:
    """Produce one fixed source range through the native Proth stage.

    The returned pair is ``(ordinary_range_receipt, native_producer_receipt)``.
    The ordinary receipt remains exactly the input consumed by the existing
    ordered reducer.
    """

    directory = directory.resolve()
    runner = runner.resolve()
    parameters = load_campaign(directory)
    if parameters not in (CampaignParameters(), analytic_10pow27_parameters()):
        raise CampaignError(
            "native ladder worker accepts only a reviewed production profile"
        )
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < parameters.range_count:
        raise CampaignError("native range index is outside the source campaign")
    if not 1024 <= sieve_block_candidates <= 1 << 30:
        raise CampaignError("native sieve block must lie in [1024,1073741824]")
    destination = directory / "independent-ranges" / independent_range_filename(index)
    native_receipt_path = directory / "native-producer-receipts" / native_receipt_filename(index)
    if destination.exists():
        ordinary = emit_independent_receipt(
            directory, index, external_prime_checker=external_prime_checker
        )
        if not native_receipt_path.is_file():
            raise CampaignError(
                "existing range has no native producer receipt; replay it with check-range"
            )
        native = _validate_native_receipt(
            native_receipt_path, index=index, range_receipt=ordinary, runner=runner
        )
        return ordinary, native

    first = _produce_boundary_rung(
        directory,
        parameters,
        index,
        general_prime_producer=general_prime_producer,
        external_prime_checker=external_prime_checker,
        builtin_pocklington=builtin_pocklington,
    )
    last = _produce_boundary_rung(
        directory,
        parameters,
        index + 1,
        general_prime_producer=general_prime_producer,
        external_prime_checker=external_prime_checker,
        builtin_pocklington=builtin_pocklington,
    )
    if last.number <= first.number:
        raise CampaignError("native formulaic boundary primes are not increasing")
    coverage_step = parameters.binary_last_even - parameters.binary_first_even + 2
    segment_hashes: list[str] = []
    segment_headers: list[NativeHeader] = []
    general_gap_count = 0

    def rungs() -> Iterator[Rung]:
        nonlocal general_gap_count
        current = first
        yield current
        while last.number - current.number > coverage_step:
            with invoke_native_segment(
                runner,
                anchor_number=current.number,
                target_number=last.number,
                coverage_step=coverage_step,
                proth_exponent=parameters.proth_exponent,
                sieve_block_candidates=sieve_block_candidates,
                temporary_parent=destination.parent,
            ) as native_run:
                segment_hashes.append(native_run.protocol_sha256)
                segment_headers.append(native_run.header)
                for rung in native_run.checked_rungs():
                    current = rung
                    yield rung
                if native_run.header.complete:
                    break
                # The independent replay above established only that the
                # native producer found no accepted source-form rung.  This
                # call must return an exact Pocklington/ECPP certificate (or
                # fail); it is never allowed to invent a probable prime.
                candidate = _produce_certified_prime(
                    directory,
                    parameters,
                    current.number,
                    current.number + coverage_step + 1,
                    general_prime_producer=general_prime_producer,
                    external_prime_checker=external_prime_checker,
                    builtin_pocklington=builtin_pocklington,
                )
                if candidate.certificate_kind in ("proth52", "proth"):
                    raise CampaignError(
                        "native producer missed a source Proth rung found by replay"
                    )
                if not current.number < candidate.number <= current.number + coverage_step:
                    raise CampaignError("certified general prime does not close native gap")
                general_gap_count += 1
                current = candidate
                yield current
        yield last

    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.native.", dir=destination.parent
    )
    os.close(temporary_fd)
    os.unlink(temporary_name)
    temporary = Path(temporary_name)
    try:
        write_range_file(
            temporary,
            parameters=parameters,
            index=index,
            previous_range_sha256=ZERO_HASH,
            rungs=rungs(),
        )
        _install_immutable_range(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    ordinary = emit_independent_receipt(
        directory, index, external_prime_checker=external_prime_checker
    )
    runner_hash = sha256_file(runner)
    source_hash = sha256_file(_source_path())
    core = _native_receipt_core(
        directory=directory,
        index=index,
        range_receipt=ordinary,
        runner_hash=runner_hash,
        source_hash=source_hash,
        segment_hashes=segment_hashes,
        segment_headers=segment_headers,
        general_gap_count=general_gap_count,
    )
    native = dict(core)
    native["native_receipt_sha256"] = hashlib.sha256(
        _NATIVE_RECEIPT_DOMAIN + canonical_json_bytes(core)
    ).hexdigest()
    native_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    _write_immutable_json(native_receipt_path, native)
    return ordinary, native


def _group_worker(arguments: tuple[object, ...]) -> tuple[dict[str, object], dict[str, object]]:
    (
        directory,
        index,
        runner,
        general_prime_producer,
        external_prime_checker,
        builtin_pocklington,
        sieve_block_candidates,
    ) = arguments
    return produce_native_independent_range(
        Path(str(directory)),
        int(index),
        runner=Path(str(runner)),
        general_prime_producer=(
            None
            if general_prime_producer is None
            else Path(str(general_prime_producer))
        ),
        external_prime_checker=(
            None
            if external_prime_checker is None
            else Path(str(external_prime_checker))
        ),
        builtin_pocklington=bool(builtin_pocklington),
        sieve_block_candidates=int(sieve_block_candidates),
    )


def produce_native_group(
    directory: Path,
    *,
    runner: Path,
    group_index: int,
    group_count: int,
    local_workers: int = 1,
    general_prime_producer: Path | None = None,
    external_prime_checker: Path | None = None,
    builtin_pocklington: bool = True,
    sieve_block_candidates: int = 1 << 24,
) -> dict[str, object]:
    """Run a bounded CPU pool over one formulaic array group."""

    parameters = load_campaign(directory)
    if parameters not in (CampaignParameters(), analytic_10pow27_parameters()):
        raise CampaignError("native worker groups require a reviewed production profile")
    lower, upper = independent_group_bounds(
        parameters.range_count, group_index, group_count
    )
    if not isinstance(local_workers, int) or isinstance(local_workers, bool) or not 1 <= local_workers <= 256:
        raise CampaignError("local_workers must lie in [1,256]")
    arguments = [
        (
            str(directory.resolve()),
            index,
            str(runner.resolve()),
            None if general_prime_producer is None else str(general_prime_producer.resolve()),
            None if external_prime_checker is None else str(external_prime_checker.resolve()),
            builtin_pocklington,
            sieve_block_candidates,
        )
        for index in range(lower, upper)
    ]
    by_index: dict[int, tuple[dict[str, object], dict[str, object]]] = {}
    if local_workers == 1:
        for arguments_for_index in arguments:
            result = _group_worker(arguments_for_index)
            by_index[int(result[0]["index"])] = result
    else:
        with ProcessPoolExecutor(max_workers=local_workers) as pool:
            futures = {
                pool.submit(_group_worker, arguments_for_index): int(arguments_for_index[1])
                for arguments_for_index in arguments
            }
            for future in as_completed(futures):
                result = future.result()
                by_index[int(result[0]["index"])] = result
    if set(by_index) != set(range(lower, upper)):
        raise CampaignError("native worker group omitted a formulaic range")
    return {
        "classification": parameters.mode,
        "first_range_index": lower,
        "group_count": group_count,
        "group_index": group_index,
        "kind": NATIVE_GROUP_KIND,
        "last_range_index": upper - 1,
        "local_workers": local_workers,
        "native_receipt_sha256s": [
            by_index[index][1]["native_receipt_sha256"]
            for index in range(lower, upper)
        ],
        "range_count": upper - lower,
        "range_receipt_sha256s": [
            by_index[index][0]["receipt_sha256"] for index in range(lower, upper)
        ],
        "schema": NATIVE_SCHEMA,
    }


__all__ = [
    "MAGIC",
    "NATIVE_GROUP_KIND",
    "NATIVE_RECEIPT_KIND",
    "NATIVE_SCHEMA",
    "NativeHeader",
    "NativeRun",
    "invoke_native_segment",
    "native_receipt_filename",
    "produce_native_group",
    "produce_native_independent_range",
    "read_native_header",
]
