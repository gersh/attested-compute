# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Literal, resumable replay of binary Goldbach through ``4 * 10**18``.

This is deliberately unscaled reference computation.  It stores a SHA-256
transcript per chunk and independently recomputes every witness on replay.  A
digest without that recomputation is never promoted to a verified result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
from typing import Iterator

from .goldbach import is_prime_bounded


KIND = "tg_binary_goldbach_campaign_v1"
CHUNK_KIND = "tg_binary_goldbach_chunk_v1"
RESULT_KIND = "tg_binary_goldbach_result_v1"
FIRST_EVEN = 4
LAST_EVEN = 4 * 10**18
DEFAULT_SOURCE_EVENS_PER_CHUNK = 10**13
ZERO_HASH = "0" * 64


class BinaryGoldbachError(RuntimeError):
    pass


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _read(path: Path) -> object:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BinaryGoldbachError(f"invalid JSON: {path}") from exc
    if raw != _canonical(value):
        raise BinaryGoldbachError(f"noncanonical JSON: {path}")
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class Parameters:
    first_even: int = FIRST_EVEN
    last_even: int = LAST_EVEN
    evens_per_chunk: int = DEFAULT_SOURCE_EVENS_PER_CHUNK
    mode: str = "full_source"

    @property
    def even_count(self) -> int:
        return (self.last_even - self.first_even) // 2 + 1

    @property
    def chunk_count(self) -> int:
        return (self.even_count + self.evens_per_chunk - 1) // self.evens_per_chunk

    def validate(self) -> None:
        if (
            isinstance(self.first_even, bool)
            or isinstance(self.last_even, bool)
            or isinstance(self.evens_per_chunk, bool)
            or not all(isinstance(x, int) for x in (self.first_even, self.last_even, self.evens_per_chunk))
            or self.first_even < 4
            or self.first_even % 2
            or self.last_even < self.first_even
            or self.last_even % 2
            or self.last_even > (1 << 64) - 1
            or self.evens_per_chunk <= 0
        ):
            raise BinaryGoldbachError("invalid binary-Goldbach parameters")
        if self.mode not in ("full_source", "bounded_test"):
            raise BinaryGoldbachError("invalid binary-Goldbach mode")
        if self.mode == "full_source" and (
            self.first_even != FIRST_EVEN or self.last_even != LAST_EVEN
        ):
            raise BinaryGoldbachError("full_source endpoints are immutable")

    def to_json(self) -> dict[str, object]:
        self.validate()
        return {
            "chunk_count": self.chunk_count,
            "even_count": str(self.even_count),
            "evens_per_chunk": self.evens_per_chunk,
            "first_even": str(self.first_even),
            "last_even": str(self.last_even),
            "mode": self.mode,
        }

    @staticmethod
    def from_json(root: object) -> "Parameters":
        if not isinstance(root, dict) or set(root) != {
            "chunk_count", "even_count", "evens_per_chunk", "first_even", "last_even", "mode"
        }:
            raise BinaryGoldbachError("parameter field mismatch")
        for field in ("first_even", "last_even", "even_count"):
            if not isinstance(root[field], str) or not root[field].isdigit():
                raise BinaryGoldbachError(f"invalid {field}")
        if not isinstance(root["evens_per_chunk"], int) or isinstance(root["evens_per_chunk"], bool):
            raise BinaryGoldbachError("invalid evens_per_chunk")
        if not isinstance(root["mode"], str):
            raise BinaryGoldbachError("invalid mode")
        result = Parameters(
            first_even=int(root["first_even"]), last_even=int(root["last_even"]),
            evens_per_chunk=root["evens_per_chunk"], mode=root["mode"],
        )
        result.validate()
        if int(root["even_count"]) != result.even_count or root["chunk_count"] != result.chunk_count:
            raise BinaryGoldbachError("derived parameter mismatch")
        return result


def find_witness(even: int) -> tuple[int, int]:
    """Find and exactly verify one prime pair, with no probabilistic predicate."""

    if not isinstance(even, int) or isinstance(even, bool) or even < 4 or even % 2:
        raise BinaryGoldbachError("target must be an even integer at least 4")
    if even > (1 << 64) - 1:
        raise BinaryGoldbachError("target is outside deterministic primality domain")
    if even == 4:
        return 2, 2
    prime = 3
    while prime <= even // 2:
        if is_prime_bounded(prime):
            complement = even - prime
            if is_prime_bounded(complement):
                return prime, complement
        prime += 2
    raise BinaryGoldbachError(f"no binary-Goldbach witness for {even}")


def _bounds(parameters: Parameters, index: int) -> tuple[int, int, int]:
    if not 0 <= index < parameters.chunk_count:
        raise BinaryGoldbachError("chunk index outside schedule")
    offset = index * parameters.evens_per_chunk
    count = min(parameters.evens_per_chunk, parameters.even_count - offset)
    first = parameters.first_even + 2 * offset
    return first, first + 2 * (count - 1), count


def _transcript(first: int, last: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for even in range(first, last + 1, 2):
        left, right = find_witness(even)
        if left + right != even or not is_prime_bounded(left) or not is_prime_bounded(right):
            raise BinaryGoldbachError("internal witness check failed")
        digest.update(struct.pack(">QQQ", even, left, right))
        count += 1
    return digest.hexdigest(), count


def chunk_filename(index: int) -> str:
    return f"chunk-{index:012d}.json"


def initialize(directory: Path, parameters: Parameters = Parameters()) -> None:
    parameters.validate()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "chunks").mkdir(exist_ok=True)
    root = {
        "implementation_sha256": _sha(Path(__file__).resolve()),
        "kind": KIND,
        "parameters": parameters.to_json(),
        "primality_source_sha256": _sha(
            Path(__file__).resolve().with_name("goldbach.py")
        ),
    }
    path = directory / "manifest.json"
    if path.exists():
        if _read(path) != root:
            raise BinaryGoldbachError("manifest differs")
    else:
        _atomic(path, _canonical(root))


def load(directory: Path) -> Parameters:
    root = _read(directory / "manifest.json")
    if (
        not isinstance(root, dict)
        or set(root)
        != {
            "implementation_sha256",
            "kind",
            "parameters",
            "primality_source_sha256",
        }
        or root["kind"] != KIND
    ):
        raise BinaryGoldbachError("wrong manifest")
    parameters = Parameters.from_json(root["parameters"])
    expected = {
        "implementation_sha256": _sha(Path(__file__).resolve()),
        "kind": KIND,
        "parameters": parameters.to_json(),
        "primality_source_sha256": _sha(
            Path(__file__).resolve().with_name("goldbach.py")
        ),
    }
    if root != expected:
        raise BinaryGoldbachError("campaign implementation source identity changed")
    return parameters


@dataclass(frozen=True)
class State:
    parameters: Parameters
    completed_chunks: int
    previous_sha256: str
    checked_evens: int


def _verify_chunk(path: Path, parameters: Parameters, index: int, previous: str) -> str:
    root = _read(path)
    expected_keys = {"first_even", "index", "kind", "last_even", "previous_sha256", "transcript_sha256", "witness_count"}
    if not isinstance(root, dict) or set(root) != expected_keys or root["kind"] != CHUNK_KIND:
        raise BinaryGoldbachError("chunk field mismatch")
    first, last, count = _bounds(parameters, index)
    expected_transcript, replayed_count = _transcript(first, last)
    expected = {
        "first_even": str(first), "index": index, "kind": CHUNK_KIND,
        "last_even": str(last), "previous_sha256": previous,
        "transcript_sha256": expected_transcript, "witness_count": count,
    }
    if replayed_count != count or root != expected:
        raise BinaryGoldbachError("chunk does not replay exactly")
    return _sha(path)


def replay(directory: Path) -> State:
    parameters = load(directory)
    previous = ZERO_HASH
    completed = 0
    checked = 0
    for index in range(parameters.chunk_count):
        path = directory / "chunks" / chunk_filename(index)
        if not path.exists():
            break
        previous = _verify_chunk(path, parameters, index, previous)
        checked += _bounds(parameters, index)[2]
        completed += 1
    for index in range(completed + 1, parameters.chunk_count):
        if (directory / "chunks" / chunk_filename(index)).exists():
            raise BinaryGoldbachError("noncontiguous chunk files")
    return State(parameters, completed, previous, checked)


def produce_next(directory: Path, state: State) -> State:
    index = state.completed_chunks
    first, last, count = _bounds(state.parameters, index)
    transcript, actual_count = _transcript(first, last)
    if actual_count != count:
        raise BinaryGoldbachError("transcript count mismatch")
    root = {
        "first_even": str(first), "index": index, "kind": CHUNK_KIND,
        "last_even": str(last), "previous_sha256": state.previous_sha256,
        "transcript_sha256": transcript, "witness_count": count,
    }
    path = directory / "chunks" / chunk_filename(index)
    _atomic(path, _canonical(root))
    digest = _verify_chunk(path, state.parameters, index, state.previous_sha256)
    return State(state.parameters, index + 1, digest, state.checked_evens + count)


def verify_complete(directory: Path) -> dict[str, object]:
    state = replay(directory)
    if state.parameters.mode != "full_source":
        raise BinaryGoldbachError("bounded test cannot become a source result")
    if state.completed_chunks != state.parameters.chunk_count or state.checked_evens != state.parameters.even_count:
        raise BinaryGoldbachError("binary-Goldbach campaign is incomplete")
    module_hash = _sha(Path(__file__).resolve())
    return {
        "artifact_sha256": state.previous_sha256,
        "checker_sha256": module_hash,
        "every_even": True,
        "first_even": str(FIRST_EVEN),
        "kind": RESULT_KIND,
        "last_even": str(LAST_EVEN),
        "manifest_sha256": _sha(directory / "manifest.json"),
        "primality_source_sha256": _sha(
            Path(__file__).resolve().with_name("goldbach.py")
        ),
        "verified": True,
        "verification_backend": "in_repo_deterministic_u64_replay",
    }


__all__ = (
    "BinaryGoldbachError", "DEFAULT_SOURCE_EVENS_PER_CHUNK", "FIRST_EVEN", "LAST_EVEN", "Parameters", "State",
    "chunk_filename", "find_witness", "initialize", "produce_next", "replay",
    "verify_complete",
)
