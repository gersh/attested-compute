# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed t-block service seam for the large-q Dirichlet pipeline.

One authenticated ``TGDLQSP1`` lane is kept open while each at-most-64-row
block is streamed exactly once to one long-lived worker.  A request describes
the exact active fixed-q roster by a public formula instead of materializing
the 76,770,217-line q-major manifest.  The worker protocol is deliberately
stricter than the currently available fixed-q all-character service:
production admission requires an explicitly pinned multi-q worker.

Receipts from this module are execution/accounting evidence only.  They do not
claim CUDA execution, completed-L zero completeness, Turing completeness,
attestation, or discharge of Platt's external atom.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
from typing import Any, BinaryIO, Mapping, NoReturn, Sequence

from tg_verifier.dirichlet_lattice_cache import (
    canonical_json_bytes,
)
from tg_verifier.dirichlet_lattice_stage import (
    SOURCE_SAMPLE_DENOMINATOR,
    SOURCE_SAMPLE_NUMERATOR,
    maximum_t_index,
)
from tg_verifier.dirichlet_source_supervisor import (
    FFT_BATCH_SIZE,
    SOURCE_CONTRACT_CLASSIFICATION,
)
from tg_verifier.dirichlet_tmajor_spool import (
    AuthenticatedQContiguousSpool,
)


AUTHOR = "Gershon Bialer"
ATOM_ID = "platt-dirichlet-theorem-7-1"
ALGORITHM_ID = "platt-dirichlet-t-block-supervisor-v1"
WORKER_ALGORITHM_ID = "platt-dirichlet-t-block-worker-v1"

HANDSHAKE_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock_worker.handshake.v1"
)
REQUEST_SCHEMA = "sparkinterval.tg.dirichlet_tblock_worker.request.v1"
RESPONSE_SCHEMA = "sparkinterval.tg.dirichlet_tblock_worker.response.v1"
CHECKPOINT_SCHEMA = (
    "sparkinterval.tg.dirichlet_tblock_supervisor.checkpoint.v1"
)
RECEIPT_SCHEMA = "sparkinterval.tg.dirichlet_tblock_supervisor.receipt.v1"

PRODUCTION_WORKER_CLASSIFICATION = (
    "production_multi_q_t_block_worker"
)
STRUCTURAL_WORKER_CLASSIFICATION = (
    "bounded_structural_protocol_harness_not_source_evidence"
)
PRODUCTION_RECEIPT_CLASSIFICATION = (
    "production_pipeline_transport_receipt_not_zero_closure"
)
STRUCTURAL_RECEIPT_CLASSIFICATION = (
    "bounded_structural_pipeline_transport_kat_not_source_evidence"
)

ACTIVE_Q_PREDICATE_ID = (
    "q_in_closed_contract_range_and_first_t_le_maximum_t_index_v1"
)
TARGET_DESCRIPTOR_ID = "fft_batch_descriptor_v1"

INITIAL_CHECKPOINT_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tblock-supervisor/checkpoint-initial/v1\0"
)
CHECKPOINT_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tblock-supervisor/checkpoint-chain/v1\0"
)
INITIAL_RESULT_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tblock-worker/result-initial/v1\0"
)
RESULT_CHAIN_DOMAIN = (
    b"sparkinterval/tg/dirichlet-tblock-worker/result-chain/v1\0"
)

MAXIMUM_CONTROL_LINE_BYTES = 1024 * 1024
MAXIMUM_STDERR_TAIL_BYTES = 64 * 1024
CHECKPOINT_NAME_WIDTH = 8

_HEX = frozenset("0123456789abcdef")


class DirichletTBlockSupervisorError(RuntimeError):
    """A worker, block, checkpoint, or exact roster failed closed."""


def _fail(message: str) -> NoReturn:
    raise DirichletTBlockSupervisorError(message)


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        _fail(f"{label} is not a lowercase SHA-256 digest")
    return value


def _integer(
    value: object,
    label: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{label} is below {minimum}")
    if maximum is not None and value > maximum:
        _fail(f"{label} is above {maximum}")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    _fail(f"non-finite JSON value is forbidden: {value}")


def _canonical_line(raw: bytes, *, label: str) -> dict[str, Any]:
    if not raw or len(raw) > MAXIMUM_CONTROL_LINE_BYTES:
        _fail(f"{label} is empty or exceeds its fixed bound")
    try:
        value = json.loads(
            raw,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DirichletTBlockSupervisorError(
            f"invalid {label} JSON"
        ) from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        _fail(f"{label} is not one canonical JSON line")
    return value


def _self_hash(
    value: Mapping[str, Any],
    field: str,
    *,
    label: str,
) -> str:
    body = dict(value)
    claimed = _digest(body.pop(field, None), f"{label}.{field}")
    if claimed != hashlib.sha256(canonical_json_bytes(body)).hexdigest():
        _fail(f"{label} self-hash differs")
    return claimed


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        _fail(f"refusing to replace immutable output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(canonical_json_bytes(dict(value)))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(
            path.parent, getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _read_regular_canonical(path: Path, *, label: str) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DirichletTBlockSupervisorError(
            f"cannot open {label} without following a final symlink"
        ) from error
    with os.fdopen(descriptor, "rb") as source:
        status = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_size <= 0
            or status.st_size > MAXIMUM_CONTROL_LINE_BYTES
        ):
            _fail(f"{label} size is outside its fixed bound")
        return _canonical_line(source.read(), label=label)


def _chain(domain: bytes, before: str, value: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(domain)
    digest.update(bytes.fromhex(_digest(before, "chain predecessor")))
    digest.update(hashlib.sha256(canonical_json_bytes(dict(value))).digest())
    return digest.hexdigest()


def initial_result_chain(
    *,
    source_contract_sha256: str,
    spool_receipt_sha256: str,
    lane_index: int,
    handshake_sha256: str,
) -> str:
    digest = hashlib.sha256(INITIAL_RESULT_CHAIN_DOMAIN)
    digest.update(bytes.fromhex(_digest(source_contract_sha256, "contract")))
    digest.update(bytes.fromhex(_digest(spool_receipt_sha256, "spool receipt")))
    digest.update(_integer(lane_index, "lane index", minimum=0).to_bytes(4, "little"))
    digest.update(bytes.fromhex(_digest(handshake_sha256, "worker handshake")))
    return digest.hexdigest()


def extend_result_chain(
    *,
    before: str,
    request_sha256: str,
    payload_stream_sha256: str,
    typed_bundle_count: int,
    typed_bundle_chain_sha256: str,
) -> str:
    identity = {
        "request_sha256": _digest(request_sha256, "request"),
        "payload_stream_sha256": _digest(
            payload_stream_sha256, "payload stream"
        ),
        "typed_bundle_count": _integer(
            typed_bundle_count, "typed bundle count", minimum=0
        ),
        "typed_bundle_chain_sha256": _digest(
            typed_bundle_chain_sha256, "typed bundle chain"
        ),
    }
    return _chain(RESULT_CHAIN_DOMAIN, before, identity)


@dataclass(frozen=True)
class _RosterIndex:
    q_start: int
    q_stop: int
    maxima_histogram: tuple[int, ...]
    suffix_count: tuple[int, ...]

    @classmethod
    def build(cls, q_start: int, q_stop: int) -> "_RosterIndex":
        maxima = [maximum_t_index(q) for q in range(q_start, q_stop + 1)]
        upper = max(maxima)
        histogram = [0] * (upper + 1)
        for value in maxima:
            histogram[value] += 1
        suffix = [0] * (upper + 2)
        for value in range(upper, -1, -1):
            suffix[value] = suffix[value + 1] + histogram[value]
        return cls(q_start, q_stop, tuple(histogram), tuple(suffix))

    def block_counts(self, first_t_index: int, stop: int) -> tuple[int, int]:
        if first_t_index >= len(self.suffix_count) - 1:
            return 0, 0
        active = self.suffix_count[first_t_index]
        references = 0
        for maximum in range(first_t_index, min(stop - 1, len(self.maxima_histogram))):
            references += (
                self.maxima_histogram[maximum]
                * (maximum - first_t_index + 1)
            )
        if stop - 1 < len(self.suffix_count):
            references += self.suffix_count[stop - 1] * (stop - first_t_index)
        return active, references

    def lane_counts(self, lane_start: int, lane_stop: int) -> tuple[int, int]:
        targets = 0
        references = 0
        for first in range(lane_start, lane_stop, FFT_BATCH_SIZE):
            stop = min(lane_stop, first + FFT_BATCH_SIZE)
            block_targets, block_references = self.block_counts(first, stop)
            targets += block_targets
            references += block_references
        return targets, references


def target_roster(
    spool: AuthenticatedQContiguousSpool,
    *,
    first_t_index: int,
    t_index_stop_exclusive: int,
    index: _RosterIndex | None = None,
) -> dict[str, Any]:
    """Return a constant-size exact description of every active q target."""

    schedule = spool.contract["schedule"]
    q_start = _integer(
        schedule.get("q_start_inclusive"), "q start", minimum=10_001
    )
    q_stop = _integer(
        schedule.get("q_stop_inclusive"), "q stop", minimum=q_start
    )
    if index is None:
        index = _RosterIndex.build(q_start, q_stop)
    if index.q_start != q_start or index.q_stop != q_stop:
        _fail("target-roster index belongs to another q range")
    active_count, row_references = index.block_counts(
        first_t_index, t_index_stop_exclusive
    )
    formula = {
        "source_contract_sha256": spool.contract["contract_sha256"],
        "lane_index": spool.lane_index,
        "q_start_inclusive": q_start,
        "q_stop_inclusive": q_stop,
        "q_iteration_order": "strictly_increasing",
        "active_q_predicate_id": ACTIVE_Q_PREDICATE_ID,
        "active_q_predicate": (
            "first_t_index <= maximum_t_index(q)"
        ),
        "maximum_t_index_equation": (
            "floor(max(100000000,200*q+(75000000 if q even "
            "else 37500000))*64/(5*q))"
        ),
        "target_descriptor_id": TARGET_DESCRIPTOR_ID,
        "target_batch_stop_equation": (
            "min(t_index_stop_exclusive,maximum_t_index(q)+1)"
        ),
        "first_t_index": first_t_index,
        "t_index_stop_exclusive": t_index_stop_exclusive,
        "sample_numerator": SOURCE_SAMPLE_NUMERATOR,
        "sample_denominator": SOURCE_SAMPLE_DENOMINATOR,
    }
    return {
        **formula,
        "active_q_count": active_count,
        "target_row_reference_count": row_references,
        "target_roster_formula_sha256": hashlib.sha256(
            canonical_json_bytes(formula)
        ).hexdigest(),
    }


def _request(
    spool: AuthenticatedQContiguousSpool,
    *,
    sequence_index: int,
    first_t_index: int,
    t_index_stop_exclusive: int,
    result_chain_before: str,
    roster_index: _RosterIndex,
) -> dict[str, Any]:
    row_source = spool.block_row_source(
        first_t_index=first_t_index,
        t_index_stop_exclusive=t_index_stop_exclusive,
    )
    rows = {
        key: row_source[key]
        for key in (
            "row_payload_bytes",
            "row_count",
            "first_t_index",
            "t_index_stop_exclusive",
            "rows",
            "row_bindings_sha256",
        )
    }
    body: dict[str, Any] = {
        "schema": REQUEST_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "sequence_index": sequence_index,
        "source_contract_sha256": spool.contract["contract_sha256"],
        "spool_receipt_sha256": spool.receipt_sha256,
        "lane_index": spool.lane_index,
        "row_block": rows,
        "target_roster": target_roster(
            spool,
            first_t_index=first_t_index,
            t_index_stop_exclusive=t_index_stop_exclusive,
            index=roster_index,
        ),
        "result_chain_before": _digest(
            result_chain_before, "result-chain predecessor"
        ),
    }
    request = dict(body)
    request["request_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return request


def validate_worker_handshake(
    value: Mapping[str, Any],
    *,
    production_contract: bool,
    allow_structural_kat: bool,
    expected_handshake_sha256: str | None,
    expected_implementation_sha256: str | None = None,
) -> dict[str, Any]:
    handshake = dict(value)
    claimed = _self_hash(
        handshake, "handshake_sha256", label="worker handshake"
    )
    required = {
        "schema",
        "schema_version",
        "author",
        "atom_id",
        "algorithm_id",
        "classification",
        "worker_id",
        "worker_implementation_sha256",
        "capabilities",
        "claims",
        "handshake_sha256",
    }
    if (
        set(handshake) != required
        or handshake.get("schema") != HANDSHAKE_SCHEMA
        or handshake.get("schema_version") != 1
        or handshake.get("author") != AUTHOR
        or handshake.get("atom_id") != ATOM_ID
        or handshake.get("algorithm_id") != WORKER_ALGORITHM_ID
        or not isinstance(handshake.get("worker_id"), str)
        or not handshake.get("worker_id")
    ):
        _fail("worker handshake identity or fields differ")
    _digest(
        handshake.get("worker_implementation_sha256"),
        "worker implementation",
    )
    capabilities = handshake.get("capabilities")
    claims = handshake.get("claims")
    required_capabilities = {
        "accepts_one_authenticated_t_block_payload",
        "derives_exact_active_q_roster_formulaically",
        "multi_q_target_iteration",
        "multi_q_plan_switching",
        "resumable_idempotent_outputs",
        "actual_residue_composer",
        "actual_all_character_transform",
        "actual_completed_l_consumer",
        "typed_bundle_emission",
        "adapter_compatible_output",
        "framed_typed_bundle_bytes_to_supervisor",
    }
    required_claims = {
        "cuda_execution_attested",
        "completed_l_zero_completeness",
        "turing_completeness",
        "trusted_execution_attested",
        "external_atom_discharged",
    }
    if (
        not isinstance(capabilities, dict)
        or set(capabilities) != required_capabilities
        or any(type(item) is not bool for item in capabilities.values())
        or not isinstance(claims, dict)
        or set(claims) != required_claims
        or any(item is not False for item in claims.values())
    ):
        _fail("worker capability or claim fields differ")
    classification = handshake.get("classification")
    if production_contract:
        if (
            expected_handshake_sha256 is None
            or expected_implementation_sha256 is None
        ):
            _fail(
                "production t-block worker requires externally pinned "
                "implementation and handshake digests"
            )
        if claimed != _digest(
            expected_handshake_sha256, "expected worker handshake"
        ):
            _fail("production worker handshake differs from its external pin")
        if classification != PRODUCTION_WORKER_CLASSIFICATION:
            _fail(
                "production admission requires a production multi-q t-block "
                "worker; the current fixed-q all-character service is "
                "incompatible"
            )
        if handshake["worker_implementation_sha256"] != _digest(
            expected_implementation_sha256,
            "expected worker implementation",
        ):
            _fail(
                "production worker implementation differs from its external "
                "pin"
            )
        production_requirements = (
            "accepts_one_authenticated_t_block_payload",
            "derives_exact_active_q_roster_formulaically",
            "multi_q_target_iteration",
            "multi_q_plan_switching",
            "resumable_idempotent_outputs",
            "actual_residue_composer",
            "actual_all_character_transform",
            "actual_completed_l_consumer",
            "typed_bundle_emission",
            "adapter_compatible_output",
            "framed_typed_bundle_bytes_to_supervisor",
        )
        if any(capabilities[key] is not True for key in production_requirements):
            _fail(
                "production worker lacks the complete multi-q composition, "
                "transform, completed-L, typed-bundle, or adapter capability"
            )
        # An all-true handshake and opaque result digest are not evidence that
        # the advertised services ran.  Production stays closed until this
        # supervisor consumes the framed bundle bytes, freshly replays every
        # bundle, and admits them through TMajorTypedBundleLaneAdapter in exact
        # q-major order.  A later attestation must bind both external pins and
        # the request/result chains.
        _fail(
            "production admission is disabled: framed typed-bundle bytes are "
            "not yet freshly replayed and admitted by the supervisor/adapter"
        )
    else:
        if not allow_structural_kat:
            _fail("structural t-block worker requires explicit authorization")
        if classification != STRUCTURAL_WORKER_CLASSIFICATION:
            _fail("structural contract requires the bounded structural worker")
        if not (
            capabilities["accepts_one_authenticated_t_block_payload"]
            and capabilities[
                "derives_exact_active_q_roster_formulaically"
            ]
            and capabilities["multi_q_target_iteration"]
            and capabilities["resumable_idempotent_outputs"]
        ):
            _fail("structural worker lacks the required protocol capabilities")
    return handshake


def _validate_response(
    value: Mapping[str, Any],
    *,
    request: Mapping[str, Any],
    handshake: Mapping[str, Any],
    payload_stream_sha256: str,
) -> dict[str, Any]:
    response = dict(value)
    _self_hash(response, "response_sha256", label="worker response")
    required = {
        "schema",
        "schema_version",
        "author",
        "atom_id",
        "algorithm_id",
        "status",
        "sequence_index",
        "request_sha256",
        "payload_stream_sha256",
        "active_q_count",
        "target_row_reference_count",
        "target_roster_formula_sha256",
        "typed_bundle_count",
        "typed_bundle_chain_sha256",
        "result_chain_before",
        "result_chain_after",
        "services_executed",
        "claims",
        "response_sha256",
    }
    if (
        set(response) != required
        or response.get("schema") != RESPONSE_SCHEMA
        or response.get("schema_version") != 1
        or response.get("author") != AUTHOR
        or response.get("atom_id") != ATOM_ID
        or response.get("algorithm_id") != WORKER_ALGORITHM_ID
        or response.get("status") != "completed"
    ):
        _fail("worker response identity, fields, or status differ")
    roster = request["target_roster"]
    exact_echoes = {
        "sequence_index": request["sequence_index"],
        "request_sha256": request["request_sha256"],
        "payload_stream_sha256": payload_stream_sha256,
        "active_q_count": roster["active_q_count"],
        "target_row_reference_count": roster[
            "target_row_reference_count"
        ],
        "target_roster_formula_sha256": roster[
            "target_roster_formula_sha256"
        ],
        "result_chain_before": request["result_chain_before"],
    }
    for field, expected in exact_echoes.items():
        if response.get(field) != expected:
            _fail(f"worker response {field} differs from the exact request")
    services = response.get("services_executed")
    claims = response.get("claims")
    expected_services = {
        "residue_composer": handshake["capabilities"][
            "actual_residue_composer"
        ],
        "all_character_transform": handshake["capabilities"][
            "actual_all_character_transform"
        ],
        "completed_l_consumer": handshake["capabilities"][
            "actual_completed_l_consumer"
        ],
        "typed_bundle_builder_and_replay": handshake["capabilities"][
            "typed_bundle_emission"
        ],
        "tmajor_adapter": handshake["capabilities"][
            "adapter_compatible_output"
        ],
    }
    if services != expected_services or claims != handshake["claims"]:
        _fail("worker response service or claim boundary differs")
    typed_bundle_count = _integer(
        response.get("typed_bundle_count"),
        "typed bundle count",
        minimum=0,
    )
    if handshake["capabilities"]["typed_bundle_emission"]:
        if typed_bundle_count != roster["active_q_count"]:
            _fail("typed-bundle worker did not cover every active q target")
    elif typed_bundle_count != 0:
        _fail("structural protocol worker claimed unimplemented typed bundles")
    typed_chain = _digest(
        response.get("typed_bundle_chain_sha256"), "typed bundle chain"
    )
    expected_after = extend_result_chain(
        before=request["result_chain_before"],
        request_sha256=request["request_sha256"],
        payload_stream_sha256=payload_stream_sha256,
        typed_bundle_count=typed_bundle_count,
        typed_bundle_chain_sha256=typed_chain,
    )
    if response.get("result_chain_after") != expected_after:
        _fail("worker result-chain transition differs")
    return response


class _Worker:
    def __init__(self, command: Sequence[str]) -> None:
        if not command or any(
            not isinstance(item, str) or not item for item in command
        ):
            _fail("worker command is empty or malformed")
        self._stderr_file = tempfile.TemporaryFile()
        self.process = subprocess.Popen(
            list(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_file,
            start_new_session=True,
        )
        if self.process.stdin is None or self.process.stdout is None:
            self.cancel()
            _fail("worker pipes were not created")
        self.input: BinaryIO = self.process.stdin
        self.output: BinaryIO = self.process.stdout

    def read_line(self, *, label: str) -> dict[str, Any]:
        raw = self.output.readline(MAXIMUM_CONTROL_LINE_BYTES + 1)
        if len(raw) > MAXIMUM_CONTROL_LINE_BYTES:
            _fail(f"{label} exceeds its fixed line bound")
        if not raw:
            code = self.process.poll()
            _fail(
                f"worker closed before {label}; exit={code}; "
                f"stderr={self.stderr_tail()!r}"
            )
        return _canonical_line(raw, label=label)

    def read_exact(self, length: int, *, label: str) -> bytes:
        """Read one bounded binary frame without accepting a short stream."""

        length = _integer(length, f"{label} length", minimum=1)
        pieces: list[bytes] = []
        retained = 0
        while retained < length:
            piece = self.output.read(length - retained)
            if not piece:
                code = self.process.poll()
                _fail(
                    f"worker closed during {label}; exit={code}; "
                    f"received={retained}; expected={length}; "
                    f"stderr={self.stderr_tail()!r}"
                )
            pieces.append(piece)
            retained += len(piece)
        return b"".join(pieces)

    def stderr_tail(self) -> str:
        self._stderr_file.flush()
        self._stderr_file.seek(0, os.SEEK_END)
        size = self._stderr_file.tell()
        self._stderr_file.seek(max(0, size - MAXIMUM_STDERR_TAIL_BYTES))
        return self._stderr_file.read().decode("utf-8", "replace")

    def cancel(self) -> None:
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait()
        try:
            self.input.close()
        except (AttributeError, BrokenPipeError, OSError):
            pass
        try:
            self.output.close()
        except (AttributeError, OSError):
            pass
        self._stderr_file.close()

    def finish(self) -> None:
        try:
            self.input.close()
        except BrokenPipeError:
            pass
        code = self.process.wait()
        trailing = self.output.read(1)
        if code != 0 or trailing:
            _fail(
                f"worker did not finish cleanly; exit={code}; "
                f"trailing_stdout={bool(trailing)}; "
                f"stderr={self.stderr_tail()!r}"
            )
        self.output.close()
        self._stderr_file.close()


def _checkpoint_path(directory: Path, sequence_index: int) -> Path:
    return directory / (
        f"block-{sequence_index:0{CHECKPOINT_NAME_WIDTH}d}.checkpoint.json"
    )


def _checkpoint_initial(
    spool: AuthenticatedQContiguousSpool,
    handshake_sha256: str,
) -> str:
    digest = hashlib.sha256(INITIAL_CHECKPOINT_CHAIN_DOMAIN)
    digest.update(bytes.fromhex(spool.contract["contract_sha256"]))
    digest.update(bytes.fromhex(spool.receipt_sha256))
    digest.update(spool.lane_index.to_bytes(4, "little"))
    digest.update(bytes.fromhex(handshake_sha256))
    return digest.hexdigest()


def _checkpoint(
    *,
    request: Mapping[str, Any],
    response: Mapping[str, Any],
    checkpoint_chain_before: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema": CHECKPOINT_SCHEMA,
        "schema_version": 1,
        "author": AUTHOR,
        "atom_id": ATOM_ID,
        "algorithm_id": ALGORITHM_ID,
        "sequence_index": request["sequence_index"],
        "checkpoint_chain_before": checkpoint_chain_before,
        "request": dict(request),
        "response": dict(response),
    }
    body["checkpoint_chain_after"] = _chain(
        CHECKPOINT_CHAIN_DOMAIN, checkpoint_chain_before, body
    )
    result = dict(body)
    result["checkpoint_sha256"] = hashlib.sha256(
        canonical_json_bytes(body)
    ).hexdigest()
    return result


def _existing_checkpoint_paths(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    if not directory.is_dir() or directory.is_symlink():
        _fail("checkpoint root is not a non-symlink directory")
    paths = sorted(directory.glob("block-*.checkpoint.json"))
    expected_names = {
        _checkpoint_path(directory, index).name
        for index in range(len(paths))
    }
    if {path.name for path in paths} != expected_names:
        _fail("checkpoint sequence has a skip, duplicate, or malformed name")
    return paths


def _resume_checkpoints(
    directory: Path,
    *,
    spool: AuthenticatedQContiguousSpool,
    handshake: Mapping[str, Any],
    roster_index: _RosterIndex,
    expected_checkpoint_chain_sha256: str | None,
) -> tuple[int, str, str, int, int]:
    handshake_sha256 = handshake["handshake_sha256"]
    checkpoint_chain = _checkpoint_initial(spool, handshake_sha256)
    result_chain = initial_result_chain(
        source_contract_sha256=spool.contract["contract_sha256"],
        spool_receipt_sha256=spool.receipt_sha256,
        lane_index=spool.lane_index,
        handshake_sha256=handshake_sha256,
    )
    total_targets = 0
    total_references = 0
    paths = _existing_checkpoint_paths(directory)
    for sequence_index, path in enumerate(paths):
        value = _read_regular_canonical(path, label="t-block checkpoint")
        _self_hash(value, "checkpoint_sha256", label="t-block checkpoint")
        first = spool.lane_start + sequence_index * FFT_BATCH_SIZE
        if first >= spool.lane_stop:
            _fail("checkpoint sequence extends beyond the exact lane")
        stop = min(spool.lane_stop, first + FFT_BATCH_SIZE)
        expected_request = _request(
            spool,
            sequence_index=sequence_index,
            first_t_index=first,
            t_index_stop_exclusive=stop,
            result_chain_before=result_chain,
            roster_index=roster_index,
        )
        request = value.get("request")
        response = value.get("response")
        if not isinstance(request, dict) or not isinstance(response, dict):
            _fail("checkpoint request or response is malformed")
        if request != expected_request:
            _fail("checkpoint request is substituted, skipped, or reordered")
        expected_checkpoint = _checkpoint(
            request=request,
            response=response,
            checkpoint_chain_before=checkpoint_chain,
        )
        if value != expected_checkpoint:
            _fail("checkpoint chain or immutable body differs")
        # The prior process already hashed the transmitted payload.  Resume
        # binds that value through the immutable checkpoint rather than
        # rereading completed 64-MiB blocks.
        _validate_response(
            response,
            request=request,
            handshake=handshake,
            payload_stream_sha256=response.get("payload_stream_sha256"),
        )
        checkpoint_chain = value["checkpoint_chain_after"]
        result_chain = response["result_chain_after"]
        total_targets += request["target_roster"]["active_q_count"]
        total_references += request["target_roster"][
            "target_row_reference_count"
        ]
    if expected_checkpoint_chain_sha256 is not None:
        if checkpoint_chain != _digest(
            expected_checkpoint_chain_sha256,
            "expected resumed checkpoint head",
        ):
            _fail("resumed checkpoint head differs from its external pin")
    return (
        len(paths),
        checkpoint_chain,
        result_chain,
        total_targets,
        total_references,
    )


def run_supervisor(
    output_receipt_path: Path,
    checkpoint_directory: Path,
    *,
    contract_path: Path,
    spool_receipt_path: Path,
    expected_spool_receipt_sha256: str,
    worker_command: Sequence[str],
    allow_structural_kat: bool = False,
    expected_contract_sha256: str | None = None,
    expected_worker_handshake_sha256: str | None = None,
    expected_worker_implementation_sha256: str | None = None,
    expected_checkpoint_chain_sha256: str | None = None,
    stop_after_blocks: int | None = None,
) -> dict[str, Any]:
    """Run or resume one lane with one-request-at-a-time backpressure."""

    if output_receipt_path.exists():
        _fail("final supervisor receipt already exists")
    if stop_after_blocks is not None:
        _integer(stop_after_blocks, "stop-after block count", minimum=1)
    checkpoint_directory.mkdir(parents=True, exist_ok=True)
    worker: _Worker | None = None
    with AuthenticatedQContiguousSpool(
        spool_receipt_path,
        contract_path=contract_path,
        expected_receipt_sha256=expected_spool_receipt_sha256,
        allow_structural_kat=allow_structural_kat,
        expected_contract_sha256=expected_contract_sha256,
    ) as spool:
        production = (
            spool.contract["classification"]
            == SOURCE_CONTRACT_CLASSIFICATION
        )
        schedule = spool.contract["schedule"]
        roster_index = _RosterIndex.build(
            schedule["q_start_inclusive"], schedule["q_stop_inclusive"]
        )
        worker = _Worker(worker_command)
        try:
            raw_handshake = worker.read_line(label="worker handshake")
            handshake = validate_worker_handshake(
                raw_handshake,
                production_contract=production,
                allow_structural_kat=allow_structural_kat,
                expected_handshake_sha256=(
                    expected_worker_handshake_sha256
                ),
                expected_implementation_sha256=(
                    expected_worker_implementation_sha256
                ),
            )
            if (
                production
                and _existing_checkpoint_paths(checkpoint_directory)
                and expected_checkpoint_chain_sha256 is None
            ):
                _fail(
                    "production resume requires an externally pinned "
                    "checkpoint-chain head"
                )
            (
                next_sequence,
                checkpoint_chain,
                result_chain,
                total_targets,
                total_references,
            ) = _resume_checkpoints(
                checkpoint_directory,
                spool=spool,
                handshake=handshake,
                roster_index=roster_index,
                expected_checkpoint_chain_sha256=(
                    expected_checkpoint_chain_sha256
                ),
            )
            total_blocks = (
                spool.lane_stop
                - spool.lane_start
                + FFT_BATCH_SIZE
                - 1
            ) // FFT_BATCH_SIZE
            processed_this_invocation = 0
            for sequence_index in range(next_sequence, total_blocks):
                if (
                    stop_after_blocks is not None
                    and processed_this_invocation >= stop_after_blocks
                ):
                    break
                first = spool.lane_start + sequence_index * FFT_BATCH_SIZE
                stop = min(spool.lane_stop, first + FFT_BATCH_SIZE)
                request = _request(
                    spool,
                    sequence_index=sequence_index,
                    first_t_index=first,
                    t_index_stop_exclusive=stop,
                    result_chain_before=result_chain,
                    roster_index=roster_index,
                )
                try:
                    worker.input.write(canonical_json_bytes(request))
                    payload_stream = hashlib.sha256()
                    observed_rows = 0
                    for t_index, payload in spool.iter_block_rows(
                        first_t_index=first,
                        t_index_stop_exclusive=stop,
                    ):
                        expected_row = request["row_block"]["rows"][
                            observed_rows
                        ]
                        if (
                            t_index != expected_row["t_index"]
                        ):
                            _fail(
                                "streamed block differs from its request-bound "
                                "row roster"
                            )
                        worker.input.write(payload)
                        payload_stream.update(payload)
                        observed_rows += 1
                    if observed_rows != request["row_block"]["row_count"]:
                        _fail("streamed block row count differs")
                    worker.input.flush()
                except (BrokenPipeError, OSError) as error:
                    raise DirichletTBlockSupervisorError(
                        "worker input closed during a t-block request"
                    ) from error
                response = _validate_response(
                    worker.read_line(label="worker response"),
                    request=request,
                    handshake=handshake,
                    payload_stream_sha256=payload_stream.hexdigest(),
                )
                checkpoint = _checkpoint(
                    request=request,
                    response=response,
                    checkpoint_chain_before=checkpoint_chain,
                )
                _atomic_json(
                    _checkpoint_path(checkpoint_directory, sequence_index),
                    checkpoint,
                )
                checkpoint_chain = checkpoint["checkpoint_chain_after"]
                result_chain = response["result_chain_after"]
                total_targets += request["target_roster"]["active_q_count"]
                total_references += request["target_roster"][
                    "target_row_reference_count"
                ]
                processed_this_invocation += 1

            completed_blocks = next_sequence + processed_this_invocation
            completed = completed_blocks == total_blocks
            expected_targets, expected_references = roster_index.lane_counts(
                spool.lane_start, spool.lane_stop
            )
            lane_record = spool.contract["schedule"]["lane_inventory"][
                "lanes"
            ][spool.lane_index]
            if (
                expected_targets
                != lane_record[
                    "q_contiguous_fft_batch_invocations_if_transposed"
                ]
            ):
                _fail(
                    "formulaic t-block target total differs from the source "
                    "contract lane inventory"
                )
            if completed and (
                total_targets != expected_targets
                or total_references != expected_references
            ):
                _fail("completed t-block coverage totals differ")
            worker.finish()
            worker = None
            body: dict[str, Any] = {
                "schema": RECEIPT_SCHEMA,
                "schema_version": 1,
                "author": AUTHOR,
                "atom_id": ATOM_ID,
                "algorithm_id": ALGORITHM_ID,
                "classification": (
                    PRODUCTION_RECEIPT_CLASSIFICATION
                    if production
                    else STRUCTURAL_RECEIPT_CLASSIFICATION
                ),
                "source_contract_sha256": spool.contract[
                    "contract_sha256"
                ],
                "spool_receipt_sha256": spool.receipt_sha256,
                "lane_index": spool.lane_index,
                "worker_handshake_sha256": handshake[
                    "handshake_sha256"
                ],
                "expected_block_count": total_blocks,
                "expected_active_q_target_count": expected_targets,
                "expected_target_row_reference_count": expected_references,
                "completed_block_count": completed_blocks,
                "active_q_target_count": total_targets,
                "target_row_reference_count": total_references,
                "checkpoint_chain_sha256": checkpoint_chain,
                "worker_result_chain_sha256": result_chain,
                "complete": completed,
                "decisions": {
                    "spool_opened_and_authenticated_once": True,
                    "each_new_block_streamed_once": True,
                    "one_request_at_a_time_backpressure": True,
                    "hash_chained_resumable_checkpoints": True,
                    "exact_active_q_roster_formula_bound": True,
                    "q_major_line_manifest_materialized": False,
                    "source_scale_run_completed": production and completed,
                    "row_resident_cuda_kernel_attested": False,
                    "completed_l_zero_completeness_claimed": False,
                    "turing_completeness_claimed": False,
                    "trusted_execution_attested": False,
                    "external_atom_discharged": False,
                },
            }
            receipt = dict(body)
            receipt["receipt_sha256"] = hashlib.sha256(
                canonical_json_bytes(body)
            ).hexdigest()
            if completed:
                _atomic_json(output_receipt_path, receipt)
            return receipt
        except BaseException:
            if worker is not None:
                worker.cancel()
            raise


def capability() -> dict[str, Any]:
    return {
        "algorithm_id": ALGORITHM_ID,
        "authenticated_spool_opened_once": True,
        "bounded_t_block_streamed_once": True,
        "constant_size_exact_q_roster_formula": True,
        "q_major_76770217_line_manifest_required": False,
        "subprocess_backpressure_and_cancellation": True,
        "immutable_hash_chained_resume_checkpoints": True,
        "production_requires_pinned_multi_q_worker": True,
        "production_requires_pinned_worker_implementation": True,
        "production_framed_bundle_byte_replay_implemented": False,
        "production_adapter_admission_implemented": False,
        "bounded_protocol_v2_framed_bundle_byte_replay_implemented": True,
        "bounded_protocol_v2_adapter_admission_implemented": True,
        "bounded_protocol_v2_checkpoints_only_after_admission": True,
        "production_admission_enabled": False,
        "current_fixed_q_allchars_service_production_compatible": False,
        "row_resident_cuda_kernel_implemented": True,
        "row_resident_cuda_worker_integrated_with_this_supervisor": False,
        "completed_l_zero_state_persistence_implemented": False,
        "turing_completeness_claimed": False,
        "trusted_execution_attested": False,
        "external_atom_discharged": False,
    }
