# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Strict resolution of content-addressed numeric corpora.

The small pin is the trust input.  A checkout is deliberately only a source
of Git objects: no accepted byte is read through its worktree.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any, BinaryIO, Mapping, Sequence
from urllib.parse import urlsplit

from .campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    parse_json_bytes,
    read_bytes_once,
    sha256_bytes,
)


PIN_KIND = "sparkinterval.pinned_numeric_corpus.v1"
MANIFEST_KIND = "sparkinterval.numeric_corpus_manifest.v1"
REPORT_KIND = "sparkinterval.verified_numeric_corpus.v1"

STATEMENT_HASH_DOMAIN = "sparkinterval/numeric-corpus-statement/v1"
PAYLOAD_ROOT_HASH_DOMAIN = "sparkinterval/numeric-corpus-payload-root/v1"
SOURCE_ROOT_HASH_DOMAIN = "sparkinterval/numeric-corpus-source-root/v1"
SNAPSHOT_KEY_HASH_DOMAIN = "sparkinterval/numeric-corpus-snapshot-key/v1"

_STATEMENT_PREFIX = STATEMENT_HASH_DOMAIN.encode("ascii") + b"\0"
_PAYLOAD_ROOT_PREFIX = PAYLOAD_ROOT_HASH_DOMAIN.encode("ascii") + b"\0"
_SOURCE_ROOT_PREFIX = SOURCE_ROOT_HASH_DOMAIN.encode("ascii") + b"\0"
_SNAPSHOT_KEY_PREFIX = SNAPSHOT_KEY_HASH_DOMAIN.encode("ascii") + b"\0"

MAX_CONTROL_BYTES = 16 * 1024 * 1024
MAX_FILES = 1_000_000
MAX_TOTAL_SIZE_BYTES = 1 << 50
MAX_INDEX = (1 << 63) - 1
MAX_VERSION = (1 << 31) - 1

_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_HASH_DOMAIN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:-]{0,255}\Z")
_LEAN_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,1023}\Z")
_PATH_RE = re.compile(r"[A-Za-z0-9._/-]{1,1024}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_OBJECT_ID_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_GIT_VERSION_RE = re.compile(r"git version ([0-9]+)\.([0-9]+)(?:\.([0-9]+))?")
_ZERO_SHA256 = "0" * 64
_ZERO_COMMIT = "0" * 40

_PIN_FIELDS = {"expected", "kind", "pin_id", "repository", "schema_version"}
_PIN_REPOSITORY_FIELDS = {
    "commit",
    "manifest_path",
    "manifest_sha256",
    "manifest_size_bytes",
    "url",
}
_PIN_EXPECTED_FIELDS = {
    "claim_id",
    "claim_version",
    "corpus_id",
    "corpus_version",
    "payload_file_count",
    "payload_root_sha256",
    "payload_total_size_bytes",
    "source_root_sha256",
    "statement_sha256",
}
_MANIFEST_FIELDS = {
    "claim",
    "corpus_id",
    "corpus_version",
    "coverage",
    "kind",
    "parameters",
    "payload_prefix",
    "payload_root",
    "payloads",
    "schema_version",
    "semantic_commitments",
    "source_files",
    "source_root",
}
_CLAIM_FIELDS = {
    "claim_id",
    "claim_version",
    "lean_theorem",
    "lean_type",
    "statement",
    "statement_encoding",
    "statement_sha256",
}
_COVERAGE_FIELDS = {
    "axis",
    "coverage_id",
    "index_start",
    "index_stop",
    "role",
}
_PAYLOAD_FIELDS = {
    "coverage_id",
    "encoding",
    "index_start",
    "index_stop",
    "path",
    "role",
    "row_count",
    "sha256",
    "size_bytes",
}
_SOURCE_FIELDS = {"executable", "path", "role", "sha256", "size_bytes"}
_ROOT_FIELDS = {"file_count", "hash_domain", "sha256", "total_size_bytes"}
_COMMITMENT_FIELDS = {"hash_domain", "name", "sha256"}


class NumericCorpusError(ValueError):
    """A pin, manifest, Git resolver, or private snapshot is invalid."""


def _fail(message: str) -> None:
    raise NumericCorpusError(message)


def _object(value: Any, label: str, fields: set[str] | None = None) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(f"{label} must be an object")
    if fields is not None:
        actual = set(value)
        missing = sorted(fields - actual)
        extra = sorted(actual - fields)
        if missing or extra:
            details: list[str] = []
            if missing:
                details.append(f"missing {missing}")
            if extra:
                details.append(f"unexpected {extra}")
            _fail(f"{label} has invalid fields: {', '.join(details)}")
    return value


def _array(
    value: Any,
    label: str,
    *,
    minimum: int = 0,
    maximum: int = MAX_FILES,
) -> list[Any]:
    if type(value) is not list:
        _fail(f"{label} must be an array")
    if not minimum <= len(value) <= maximum:
        _fail(f"{label} must contain between {minimum} and {maximum} entries")
    return value


def _string(
    value: Any,
    label: str,
    *,
    minimum: int = 1,
    maximum: int,
) -> str:
    if type(value) is not str:
        _fail(f"{label} must be a string")
    if not minimum <= len(value) <= maximum:
        _fail(f"{label} length must be between {minimum} and {maximum}")
    return value


def _integer(
    value: Any,
    label: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if type(value) is not int:
        _fail(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        _fail(f"{label} must be between {minimum} and {maximum}")
    return value


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        _fail(f"{label} must be a boolean")
    return value


def _identifier(value: Any, label: str) -> str:
    text = _string(value, label, maximum=128)
    if _ID_RE.fullmatch(text) is None:
        _fail(f"{label} is not a portable identifier")
    return text


def _hash_domain(value: Any, label: str) -> str:
    text = _string(value, label, maximum=256)
    if _HASH_DOMAIN_RE.fullmatch(text) is None:
        _fail(f"{label} is not a valid hash domain")
    return text


def _lean_name(value: Any, label: str) -> str:
    text = _string(value, label, maximum=1024)
    if _LEAN_NAME_RE.fullmatch(text) is None:
        _fail(f"{label} is not a fully qualified Lean name")
    return text


def _sha256(value: Any, label: str) -> str:
    text = _string(value, label, minimum=64, maximum=64)
    if _SHA256_RE.fullmatch(text) is None:
        _fail(f"{label} must be 64 lowercase hexadecimal digits")
    if text == _ZERO_SHA256:
        _fail(f"{label} uses the reserved all-zero placeholder")
    return text


def _commit(value: Any, label: str) -> str:
    text = _string(value, label, minimum=40, maximum=40)
    if _COMMIT_RE.fullmatch(text) is None:
        _fail(f"{label} must be a full 40-digit lowercase Git commit ID")
    if text == _ZERO_COMMIT:
        _fail(f"{label} uses the reserved all-zero placeholder")
    return text


def _version(value: Any, label: str) -> int:
    return _integer(value, label, minimum=1, maximum=MAX_VERSION)


def _index(value: Any, label: str) -> int:
    return _integer(value, label, minimum=0, maximum=MAX_INDEX)


def _positive_size(value: Any, label: str) -> int:
    return _integer(value, label, minimum=1, maximum=MAX_TOTAL_SIZE_BYTES)


def _safe_path(value: Any, label: str) -> str:
    text = _string(value, label, maximum=1024)
    if _PATH_RE.fullmatch(text) is None:
        _fail(f"{label} is not a restricted ASCII repository-relative path")
    if "\\" in text or text.startswith("/") or text.endswith("/"):
        _fail(f"{label} must be a normalized relative POSIX path")
    components = text.split("/")
    if any(component in {"", ".", ".."} for component in components):
        _fail(f"{label} contains an empty, dot, or parent component")
    if str(PurePosixPath(text)) != text:
        _fail(f"{label} is not normalized")
    return text


def _require_prefix_free_paths(paths: Sequence[str], label: str) -> None:
    ordered = sorted(paths)
    for first, second in zip(ordered, ordered[1:]):
        if second.startswith(first + "/"):
            _fail(
                f"{label} contains file path {first!r} as an ancestor "
                f"of {second!r}"
            )


def _https_repository_url(value: Any, label: str) -> str:
    text = _string(value, label, minimum=12, maximum=2048)
    if any(ord(character) < 0x21 or ord(character) > 0x7E for character in text):
        _fail(f"{label} must contain printable ASCII without whitespace")
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError as exc:
        raise NumericCorpusError(f"{label} is not a valid URL: {exc}") from exc
    if parsed.scheme != "https":
        _fail(f"{label} must use https")
    if (
        not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        _fail(f"{label} must not contain credentials, a query, or a fragment")
    if parsed.hostname is None or "." not in parsed.hostname:
        _fail(f"{label} must contain a fully qualified host name")
    if port not in {None, 443}:
        _fail(f"{label} may use only the default HTTPS port")
    if not parsed.path or parsed.path == "/" or any(ord(char) < 0x20 for char in text):
        _fail(f"{label} must identify a repository path")
    return text


def statement_sha256(statement: str) -> str:
    """Hash the exact source-shaped statement with protocol domain separation."""

    if type(statement) is not str:
        _fail("statement must be a string")
    try:
        encoded = statement.encode("utf-8")
    except UnicodeError as exc:
        raise NumericCorpusError("statement is not valid Unicode scalar text") from exc
    return hashlib.sha256(_STATEMENT_PREFIX + encoded).hexdigest()


def payload_root_sha256(payloads: Sequence[Mapping[str, Any]]) -> str:
    """Hash the complete ordered payload-record array."""

    return hashlib.sha256(
        _PAYLOAD_ROOT_PREFIX + canonical_json_bytes(list(payloads))
    ).hexdigest()


def source_root_sha256(source_files: Sequence[Mapping[str, Any]]) -> str:
    """Hash the complete ordered source-record array."""

    return hashlib.sha256(
        _SOURCE_ROOT_PREFIX + canonical_json_bytes(list(source_files))
    ).hexdigest()


def snapshot_key_sha256(pin_value: Mapping[str, Any]) -> str:
    """Address a snapshot by both manifest contents and its in-tree path."""

    pin = validate_pin(pin_value)
    identity = {
        "manifest_path": pin["repository"]["manifest_path"],
        "manifest_sha256": pin["repository"]["manifest_sha256"],
    }
    return hashlib.sha256(
        _SNAPSHOT_KEY_PREFIX + canonical_json_bytes(identity)
    ).hexdigest()


def validate_pin(value: Any) -> dict[str, Any]:
    """Validate all context-free requirements of a consumer pin."""

    pin = _object(value, "pin", _PIN_FIELDS)
    if pin["kind"] != PIN_KIND:
        _fail(f"pin.kind must be {PIN_KIND!r}")
    if pin["schema_version"] != 1:
        _fail("pin.schema_version must be 1")
    _identifier(pin["pin_id"], "pin.pin_id")

    repository = _object(
        pin["repository"], "pin.repository", _PIN_REPOSITORY_FIELDS
    )
    _https_repository_url(repository["url"], "pin.repository.url")
    _commit(repository["commit"], "pin.repository.commit")
    _safe_path(repository["manifest_path"], "pin.repository.manifest_path")
    _sha256(repository["manifest_sha256"], "pin.repository.manifest_sha256")
    _integer(
        repository["manifest_size_bytes"],
        "pin.repository.manifest_size_bytes",
        minimum=1,
        maximum=MAX_CONTROL_BYTES,
    )

    expected = _object(pin["expected"], "pin.expected", _PIN_EXPECTED_FIELDS)
    _identifier(expected["claim_id"], "pin.expected.claim_id")
    _version(expected["claim_version"], "pin.expected.claim_version")
    _identifier(expected["corpus_id"], "pin.expected.corpus_id")
    _version(expected["corpus_version"], "pin.expected.corpus_version")
    _integer(
        expected["payload_file_count"],
        "pin.expected.payload_file_count",
        minimum=1,
        maximum=MAX_FILES,
    )
    _sha256(
        expected["payload_root_sha256"],
        "pin.expected.payload_root_sha256",
    )
    _positive_size(
        expected["payload_total_size_bytes"],
        "pin.expected.payload_total_size_bytes",
    )
    _sha256(expected["source_root_sha256"], "pin.expected.source_root_sha256")
    _sha256(expected["statement_sha256"], "pin.expected.statement_sha256")
    return pin


def _validate_root(
    value: Any,
    label: str,
    *,
    expected_domain: str,
    records: list[dict[str, Any]],
    computed_sha256: str,
) -> None:
    root = _object(value, label, _ROOT_FIELDS)
    if _hash_domain(root["hash_domain"], f"{label}.hash_domain") != expected_domain:
        _fail(f"{label}.hash_domain must be {expected_domain!r}")
    file_count = _integer(
        root["file_count"],
        f"{label}.file_count",
        minimum=1,
        maximum=MAX_FILES,
    )
    total_size = _positive_size(
        root["total_size_bytes"], f"{label}.total_size_bytes"
    )
    digest = _sha256(root["sha256"], f"{label}.sha256")
    actual_total = sum(record["size_bytes"] for record in records)
    if file_count != len(records):
        _fail(f"{label}.file_count does not match the complete record list")
    if total_size != actual_total:
        _fail(f"{label}.total_size_bytes does not match the complete record list")
    if actual_total > MAX_TOTAL_SIZE_BYTES:
        _fail(f"{label} exceeds the protocol total-size limit")
    if digest != computed_sha256:
        _fail(f"{label}.sha256 does not match its complete ordered record list")


def validate_manifest(value: Any) -> dict[str, Any]:
    """Validate a manifest, including deterministic ordering and exact ranges."""

    manifest = _object(value, "manifest", _MANIFEST_FIELDS)
    if manifest["kind"] != MANIFEST_KIND:
        _fail(f"manifest.kind must be {MANIFEST_KIND!r}")
    if manifest["schema_version"] != 1:
        _fail("manifest.schema_version must be 1")
    _identifier(manifest["corpus_id"], "manifest.corpus_id")
    _version(manifest["corpus_version"], "manifest.corpus_version")

    claim = _object(manifest["claim"], "manifest.claim", _CLAIM_FIELDS)
    _identifier(claim["claim_id"], "manifest.claim.claim_id")
    _version(claim["claim_version"], "manifest.claim.claim_version")
    _lean_name(claim["lean_theorem"], "manifest.claim.lean_theorem")
    _lean_name(claim["lean_type"], "manifest.claim.lean_type")
    statement = _string(
        claim["statement"],
        "manifest.claim.statement",
        minimum=1,
        maximum=65536,
    )
    if "\0" in statement:
        _fail("manifest.claim.statement may not contain NUL")
    if claim["statement_encoding"] != "utf8-exact-v1":
        _fail("manifest.claim.statement_encoding must be 'utf8-exact-v1'")
    statement_digest = _sha256(
        claim["statement_sha256"], "manifest.claim.statement_sha256"
    )
    if statement_digest != statement_sha256(statement):
        _fail("manifest.claim.statement_sha256 does not match the exact statement")

    parameters = _object(manifest["parameters"], "manifest.parameters")
    if not 1 <= len(parameters) <= 10_000:
        _fail("manifest.parameters must contain between 1 and 10000 entries")
    for key, item in parameters.items():
        _identifier(key, f"manifest.parameters key {key!r}")
        _string(
            item,
            f"manifest.parameters[{key!r}]",
            minimum=0,
            maximum=4096,
        )

    payload_prefix = _safe_path(
        manifest["payload_prefix"], "manifest.payload_prefix"
    )

    coverage_records = _array(
        manifest["coverage"], "manifest.coverage", minimum=1, maximum=10_000
    )
    coverages: dict[str, dict[str, Any]] = {}
    coverage_order: list[str] = []
    for index, item in enumerate(coverage_records):
        label = f"manifest.coverage[{index}]"
        coverage = _object(item, label, _COVERAGE_FIELDS)
        coverage_id = _identifier(coverage["coverage_id"], f"{label}.coverage_id")
        _identifier(coverage["axis"], f"{label}.axis")
        _identifier(coverage["role"], f"{label}.role")
        start = _index(coverage["index_start"], f"{label}.index_start")
        stop = _index(coverage["index_stop"], f"{label}.index_stop")
        if start >= stop:
            _fail(f"{label} must be a nonempty half-open interval")
        if coverage_id in coverages:
            _fail(f"duplicate coverage_id {coverage_id!r}")
        coverages[coverage_id] = coverage
        coverage_order.append(coverage_id)
    if coverage_order != sorted(coverage_order):
        _fail("manifest.coverage must be ordered by coverage_id")

    payload_values = _array(
        manifest["payloads"], "manifest.payloads", minimum=1, maximum=MAX_FILES
    )
    payloads: list[dict[str, Any]] = []
    payload_paths: set[str] = set()
    payload_order: list[tuple[str, int, int, str]] = []
    by_coverage: dict[str, list[dict[str, Any]]] = {
        coverage_id: [] for coverage_id in coverages
    }
    prefix = payload_prefix + "/"
    for index, item in enumerate(payload_values):
        label = f"manifest.payloads[{index}]"
        payload = _object(item, label, _PAYLOAD_FIELDS)
        coverage_id = _identifier(payload["coverage_id"], f"{label}.coverage_id")
        if coverage_id not in coverages:
            _fail(f"{label}.coverage_id names no declared coverage")
        _identifier(payload["encoding"], f"{label}.encoding")
        role = _identifier(payload["role"], f"{label}.role")
        start = _index(payload["index_start"], f"{label}.index_start")
        stop = _index(payload["index_stop"], f"{label}.index_stop")
        if start >= stop:
            _fail(f"{label} must be a nonempty half-open interval")
        rows = _integer(
            payload["row_count"],
            f"{label}.row_count",
            minimum=1,
            maximum=MAX_INDEX,
        )
        if rows != stop - start:
            _fail(f"{label}.row_count must equal index_stop - index_start")
        path = _safe_path(payload["path"], f"{label}.path")
        if not path.startswith(prefix):
            _fail(f"{label}.path must be strictly beneath manifest.payload_prefix")
        if path in payload_paths:
            _fail(f"duplicate payload path {path!r}")
        payload_paths.add(path)
        _sha256(payload["sha256"], f"{label}.sha256")
        _positive_size(payload["size_bytes"], f"{label}.size_bytes")
        coverage = coverages[coverage_id]
        if role != coverage["role"]:
            _fail(f"{label}.role does not match its coverage role")
        payloads.append(payload)
        by_coverage[coverage_id].append(payload)
        payload_order.append((coverage_id, start, stop, path))
    if payload_order != sorted(payload_order):
        _fail(
            "manifest.payloads must be ordered by "
            "(coverage_id, index_start, index_stop, path)"
        )

    for coverage_id in coverage_order:
        coverage = coverages[coverage_id]
        shards = by_coverage[coverage_id]
        if not shards:
            _fail(f"coverage {coverage_id!r} has no payload shards")
        cursor = coverage["index_start"]
        for shard in shards:
            if shard["index_start"] != cursor:
                relation = "overlap" if shard["index_start"] < cursor else "gap"
                _fail(f"coverage {coverage_id!r} has a shard {relation} at {cursor}")
            cursor = shard["index_stop"]
        if cursor != coverage["index_stop"]:
            _fail(
                f"coverage {coverage_id!r} payloads stop at {cursor}, "
                f"not {coverage['index_stop']}"
            )

    source_values = _array(
        manifest["source_files"],
        "manifest.source_files",
        minimum=1,
        maximum=MAX_FILES,
    )
    sources: list[dict[str, Any]] = []
    source_paths: list[str] = []
    all_paths = set(payload_paths)
    for index, item in enumerate(source_values):
        label = f"manifest.source_files[{index}]"
        source = _object(item, label, _SOURCE_FIELDS)
        path = _safe_path(source["path"], f"{label}.path")
        if path in all_paths:
            _fail(f"duplicate manifest file path {path!r}")
        all_paths.add(path)
        source_paths.append(path)
        _identifier(source["role"], f"{label}.role")
        _boolean(source["executable"], f"{label}.executable")
        _sha256(source["sha256"], f"{label}.sha256")
        _positive_size(source["size_bytes"], f"{label}.size_bytes")
        sources.append(source)
    if source_paths != sorted(source_paths):
        _fail("manifest.source_files must be ordered by path")
    _require_prefix_free_paths(sorted(all_paths), "manifest file paths")

    commitment_values = _array(
        manifest["semantic_commitments"],
        "manifest.semantic_commitments",
        maximum=10_000,
    )
    commitment_names: list[str] = []
    for index, item in enumerate(commitment_values):
        label = f"manifest.semantic_commitments[{index}]"
        commitment = _object(item, label, _COMMITMENT_FIELDS)
        name = _identifier(commitment["name"], f"{label}.name")
        _hash_domain(commitment["hash_domain"], f"{label}.hash_domain")
        _sha256(commitment["sha256"], f"{label}.sha256")
        commitment_names.append(name)
    if len(set(commitment_names)) != len(commitment_names):
        _fail("manifest.semantic_commitments contains duplicate names")
    if commitment_names != sorted(commitment_names):
        _fail("manifest.semantic_commitments must be ordered by name")

    _validate_root(
        manifest["payload_root"],
        "manifest.payload_root",
        expected_domain=PAYLOAD_ROOT_HASH_DOMAIN,
        records=payloads,
        computed_sha256=payload_root_sha256(payloads),
    )
    _validate_root(
        manifest["source_root"],
        "manifest.source_root",
        expected_domain=SOURCE_ROOT_HASH_DOMAIN,
        records=sources,
        computed_sha256=source_root_sha256(sources),
    )
    return manifest


def validate_pin_manifest(
    pin_value: Any, manifest_value: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate a pin and manifest and bind every repeated expectation."""

    pin = validate_pin(pin_value)
    manifest = validate_manifest(manifest_value)
    expected = pin["expected"]
    claim = manifest["claim"]
    comparisons = {
        "claim_id": claim["claim_id"],
        "claim_version": claim["claim_version"],
        "corpus_id": manifest["corpus_id"],
        "corpus_version": manifest["corpus_version"],
        "payload_file_count": manifest["payload_root"]["file_count"],
        "payload_root_sha256": manifest["payload_root"]["sha256"],
        "payload_total_size_bytes": manifest["payload_root"]["total_size_bytes"],
        "source_root_sha256": manifest["source_root"]["sha256"],
        "statement_sha256": claim["statement_sha256"],
    }
    for field, actual in comparisons.items():
        if expected[field] != actual:
            _fail(f"pin.expected.{field} does not match the manifest")
    manifest_path = pin["repository"]["manifest_path"]
    referenced_paths = {
        record["path"] for record in manifest["payloads"]
    } | {record["path"] for record in manifest["source_files"]}
    if manifest_path in referenced_paths:
        _fail("the manifest path must be distinct from every referenced file")
    _require_prefix_free_paths(
        [manifest_path, *referenced_paths],
        "manifest and referenced file paths",
    )
    return pin, manifest


def _parse_canonical(raw: bytes, label: str, *, limit: int) -> Any:
    if len(raw) > limit:
        _fail(f"{label} exceeds {limit} bytes")
    try:
        value = parse_json_bytes(raw, label=label)
        canonical = canonical_json_bytes(value)
    except (ValueError, RecursionError, TypeError, OverflowError) as exc:
        raise NumericCorpusError(f"cannot parse canonical {label}: {exc}") from exc
    if raw != canonical:
        _fail(f"{label} is not canonical JSON")
    return value


def parse_pin_bytes(raw: bytes, *, label: str = "numeric-corpus pin") -> dict[str, Any]:
    pin = _parse_canonical(raw, label, limit=MAX_CONTROL_BYTES)
    return validate_pin(pin)


def parse_manifest_bytes(
    raw: bytes,
    *,
    pin: Mapping[str, Any] | None = None,
    label: str = "numeric-corpus manifest",
) -> dict[str, Any]:
    manifest = _parse_canonical(raw, label, limit=MAX_CONTROL_BYTES)
    if pin is None:
        return validate_manifest(manifest)
    _, checked_manifest = validate_pin_manifest(pin, manifest)
    return checked_manifest


def load_pin(path: Path | str) -> dict[str, Any]:
    pin_path = Path(path)
    try:
        raw = read_bytes_once(pin_path, limit=MAX_CONTROL_BYTES)
    except CampaignIOError as exc:
        raise NumericCorpusError(str(exc)) from exc
    return parse_pin_bytes(raw, label=str(pin_path))


def load_manifest(
    path: Path | str, *, pin: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    manifest_path = Path(path)
    try:
        raw = read_bytes_once(manifest_path, limit=MAX_CONTROL_BYTES)
    except CampaignIOError as exc:
        raise NumericCorpusError(str(exc)) from exc
    return parse_manifest_bytes(raw, pin=pin, label=str(manifest_path))


def _git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C",
            "LC_ALL": "C",
            "TZ": "UTC",
        }
    )
    return environment


def _git_command(arguments: Sequence[str]) -> list[str]:
    return [
        "git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "protocol.file.allow=never",
        "-c",
        "protocol.ext.allow=never",
        *arguments,
    ]


def _run_git(arguments: Sequence[str], *, label: str) -> bytes:
    try:
        completed = subprocess.run(
            _git_command(arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=_git_environment(),
        )
    except OSError as exc:
        raise NumericCorpusError(f"cannot execute Git while {label}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        if len(detail) > 1000:
            detail = detail[:1000] + "..."
        _fail(f"Git failed while {label}: {detail or 'no diagnostic'}")
    return completed.stdout


@lru_cache(maxsize=1)
def _require_safe_git_version() -> None:
    """Require a Git release that honors GIT_NO_LAZY_FETCH."""

    raw = _run_git(["--version"], label="checking Git lazy-fetch protection")
    try:
        text = raw.decode("ascii", "strict").strip()
    except UnicodeError as exc:
        raise NumericCorpusError("Git returned a non-ASCII version string") from exc
    match = _GIT_VERSION_RE.match(text)
    if match is None:
        _fail(f"cannot establish the installed Git version from {text!r}")
    version = tuple(int(part or "0") for part in match.groups())
    if version < (2, 43, 0):
        _fail(
            "numeric-corpus resolution requires Git 2.43 or newer so "
            "GIT_NO_LAZY_FETCH fails closed for untrusted promisor repositories"
        )


def _resolver_path(checkout: Path | str) -> Path:
    path = Path(checkout)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise NumericCorpusError(f"cannot inspect Git resolver {path}: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail(f"Git resolver must be a non-symlink directory: {path}")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise NumericCorpusError(f"cannot resolve Git resolver {path}: {exc}") from exc


def _verify_commit(repo: Path, commit: str) -> None:
    raw = _run_git(
        ["-C", str(repo), "rev-parse", "--verify", f"{commit}^{{commit}}"],
        label="resolving the pinned commit",
    )
    resolved = raw.decode("ascii", "strict").strip()
    if resolved != commit:
        _fail("the resolver did not return the exact pinned commit")


@dataclass(frozen=True)
class _GitBlob:
    path: str
    object_id: str
    mode: str
    size_bytes: int


def _tree_blob(repo: Path, commit: str, path: str, expected_mode: str) -> _GitBlob:
    raw = _run_git(
        ["-C", str(repo), "ls-tree", "-z", "--full-tree", commit, "--", path],
        label=f"inspecting committed path {path!r}",
    )
    records = [record for record in raw.split(b"\0") if record]
    if len(records) != 1:
        _fail(f"committed path {path!r} does not resolve to exactly one tree entry")
    try:
        metadata_raw, encoded_path = records[0].split(b"\t", 1)
        mode_raw, type_raw, object_raw = metadata_raw.split(b" ", 2)
        actual_path = encoded_path.decode("ascii")
        mode = mode_raw.decode("ascii")
        object_type = type_raw.decode("ascii")
        object_id = object_raw.decode("ascii")
    except (ValueError, UnicodeError) as exc:
        raise NumericCorpusError(
            f"Git returned malformed tree metadata for {path!r}"
        ) from exc
    if actual_path != path:
        _fail(f"Git returned an aliased path for {path!r}")
    if object_type != "blob" or mode != expected_mode:
        _fail(
            f"committed path {path!r} must be a {expected_mode} regular blob, "
            f"not {mode} {object_type}"
        )
    if _OBJECT_ID_RE.fullmatch(object_id) is None:
        _fail(f"Git returned an invalid object ID for {path!r}")
    size_raw = _run_git(
        ["-C", str(repo), "cat-file", "-s", object_id],
        label=f"measuring committed path {path!r}",
    )
    try:
        size = int(size_raw.decode("ascii", "strict").strip())
    except (ValueError, UnicodeError) as exc:
        raise NumericCorpusError(f"Git returned an invalid size for {path!r}") from exc
    if size < 0:
        _fail(f"Git returned a negative size for {path!r}")
    return _GitBlob(path=path, object_id=object_id, mode=mode, size_bytes=size)


def _stream_blob(
    repo: Path,
    blob: _GitBlob,
    *,
    expected_sha256: str,
    expected_size: int,
    output: BinaryIO | None = None,
) -> None:
    if blob.size_bytes != expected_size:
        _fail(
            f"committed blob {blob.path!r} has size {blob.size_bytes}, "
            f"expected {expected_size}"
        )
    command = _git_command(
        ["-C", str(repo), "cat-file", "blob", blob.object_id]
    )
    digest = hashlib.sha256()
    total = 0
    with tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=stderr,
                env=_git_environment(),
            )
        except OSError as exc:
            raise NumericCorpusError(
                f"cannot execute Git while reading {blob.path!r}: {exc}"
            ) from exc
        assert process.stdout is not None
        try:
            try:
                while True:
                    chunk = process.stdout.read(1 << 20)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > expected_size:
                        _fail(
                            f"committed blob {blob.path!r} "
                            "exceeds its declared size"
                        )
                    digest.update(chunk)
                    if output is not None:
                        output.write(chunk)
                return_code = process.wait()
            except BaseException:
                if process.poll() is None:
                    process.kill()
                process.wait()
                raise
        finally:
            process.stdout.close()
        if return_code != 0:
            stderr.seek(0)
            detail = stderr.read(1000).decode("utf-8", "replace").strip()
            _fail(
                f"Git failed while reading committed blob {blob.path!r}: "
                f"{detail or 'no diagnostic'}"
            )
    if total != expected_size:
        _fail(
            f"committed blob {blob.path!r} produced {total} bytes, "
            f"expected {expected_size}"
        )
    if digest.hexdigest() != expected_sha256:
        _fail(f"committed blob {blob.path!r} does not match its SHA-256")


def _read_manifest_blob(
    repo: Path, blob: _GitBlob, pin: Mapping[str, Any]
) -> bytes:
    repository = pin["repository"]
    expected_size = repository["manifest_size_bytes"]
    if blob.size_bytes != expected_size:
        _fail("the committed manifest size does not match the pin")
    buffer = io.BytesIO()
    _stream_blob(
        repo,
        blob,
        expected_sha256=repository["manifest_sha256"],
        expected_size=expected_size,
        output=buffer,
    )
    return buffer.getvalue()


@dataclass(frozen=True)
class _GitCorpus:
    repo: Path
    pin: dict[str, Any]
    manifest: dict[str, Any]
    manifest_raw: bytes
    manifest_blob: _GitBlob
    payload_blobs: tuple[_GitBlob, ...]
    source_blobs: tuple[_GitBlob, ...]


def _prepare_git_corpus(
    checkout: Path | str, pin_value: Mapping[str, Any]
) -> _GitCorpus:
    _require_safe_git_version()
    pin = validate_pin(pin_value)
    repo = _resolver_path(checkout)
    commit = pin["repository"]["commit"]
    _verify_commit(repo, commit)
    manifest_path = pin["repository"]["manifest_path"]
    manifest_blob = _tree_blob(repo, commit, manifest_path, "100644")
    manifest_raw = _read_manifest_blob(repo, manifest_blob, pin)
    if len(manifest_raw) != pin["repository"]["manifest_size_bytes"]:
        _fail("the committed manifest byte count changed while it was read")
    if sha256_bytes(manifest_raw) != pin["repository"]["manifest_sha256"]:
        _fail("the committed manifest digest changed while it was read")
    manifest = parse_manifest_bytes(
        manifest_raw,
        pin=pin,
        label=f"{commit}:{manifest_path}",
    )

    payload_blobs: list[_GitBlob] = []
    for record in manifest["payloads"]:
        blob = _tree_blob(repo, commit, record["path"], "100644")
        if blob.size_bytes != record["size_bytes"]:
            _fail(f"committed payload {record['path']!r} has the wrong size")
        payload_blobs.append(blob)
    source_blobs: list[_GitBlob] = []
    for record in manifest["source_files"]:
        mode = "100755" if record["executable"] else "100644"
        blob = _tree_blob(repo, commit, record["path"], mode)
        if blob.size_bytes != record["size_bytes"]:
            _fail(f"committed source {record['path']!r} has the wrong size")
        source_blobs.append(blob)
    return _GitCorpus(
        repo=repo,
        pin=pin,
        manifest=manifest,
        manifest_raw=manifest_raw,
        manifest_blob=manifest_blob,
        payload_blobs=tuple(payload_blobs),
        source_blobs=tuple(source_blobs),
    )


def _report(corpus: _GitCorpus, *, materialized: bool) -> dict[str, Any]:
    manifest = corpus.manifest
    pin = corpus.pin
    return {
        "accepted": True,
        "claim_id": manifest["claim"]["claim_id"],
        "claim_version": manifest["claim"]["claim_version"],
        "commit": pin["repository"]["commit"],
        "corpus_id": manifest["corpus_id"],
        "corpus_version": manifest["corpus_version"],
        "kind": REPORT_KIND,
        "manifest_sha256": pin["repository"]["manifest_sha256"],
        "materialized": materialized,
        "payload_file_count": manifest["payload_root"]["file_count"],
        "payload_root_sha256": manifest["payload_root"]["sha256"],
        "payload_total_size_bytes": manifest["payload_root"]["total_size_bytes"],
        "pin_id": pin["pin_id"],
        "source_file_count": manifest["source_root"]["file_count"],
        "source_root_sha256": manifest["source_root"]["sha256"],
        "source_total_size_bytes": manifest["source_root"]["total_size_bytes"],
        "snapshot_key_sha256": snapshot_key_sha256(pin),
        "statement_sha256": manifest["claim"]["statement_sha256"],
    }


def _verify_git_files(corpus: _GitCorpus) -> None:
    for record, blob in zip(
        corpus.manifest["payloads"], corpus.payload_blobs, strict=True
    ):
        _stream_blob(
            corpus.repo,
            blob,
            expected_sha256=record["sha256"],
            expected_size=record["size_bytes"],
        )
    for record, blob in zip(
        corpus.manifest["source_files"], corpus.source_blobs, strict=True
    ):
        _stream_blob(
            corpus.repo,
            blob,
            expected_sha256=record["sha256"],
            expected_size=record["size_bytes"],
        )


def verify_git_corpus(
    checkout: Path | str, pin_value: Mapping[str, Any]
) -> dict[str, Any]:
    """Verify every referenced byte from one exact commit's Git objects."""

    corpus = _prepare_git_corpus(checkout, pin_value)
    _verify_git_files(corpus)
    return _report(corpus, materialized=False)


def _expected_snapshot_files(
    pin: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, tuple[str, int, int]]:
    result = {
        pin["repository"]["manifest_path"]: (
            pin["repository"]["manifest_sha256"],
            pin["repository"]["manifest_size_bytes"],
            0o444,
        )
    }
    for record in manifest["payloads"]:
        result[record["path"]] = (record["sha256"], record["size_bytes"], 0o444)
    for record in manifest["source_files"]:
        result[record["path"]] = (
            record["sha256"],
            record["size_bytes"],
            0o555 if record["executable"] else 0o444,
        )
    return result


def _expected_snapshot_directories(paths: Sequence[str]) -> set[str]:
    result: set[str] = set()
    for path in paths:
        parent = PurePosixPath(path).parent
        while str(parent) != ".":
            result.add(str(parent))
            parent = parent.parent
    return result


def _snapshot_inventory(root: Path) -> tuple[set[str], set[str]]:
    try:
        root_status = root.lstat()
    except OSError as exc:
        raise NumericCorpusError(f"cannot inspect snapshot {root}: {exc}") from exc
    if stat.S_ISLNK(root_status.st_mode) or not stat.S_ISDIR(root_status.st_mode):
        _fail(f"snapshot root must be a non-symlink directory: {root}")
    if stat.S_IMODE(root_status.st_mode) != 0o555:
        _fail("snapshot root must have read-only mode 0555")

    directories: set[str] = set()
    files: set[str] = set()
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in directory_names:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            status = path.lstat()
            if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
                _fail(f"snapshot contains a non-directory entry at {relative!r}")
            if stat.S_IMODE(status.st_mode) != 0o555:
                _fail(f"snapshot directory {relative!r} must have mode 0555")
            directories.add(relative)
        for name in file_names:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            status = path.lstat()
            if (
                stat.S_ISLNK(status.st_mode)
                or not stat.S_ISREG(status.st_mode)
                or status.st_nlink != 1
            ):
                _fail(
                    f"snapshot file {relative!r} must be a single-link regular file"
                )
            files.add(relative)
    return directories, files


def _hash_snapshot_file(
    path: Path, *, expected_size: int, expected_mode: int
) -> str:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise NumericCorpusError(f"cannot open snapshot file {path}: {exc}") from exc
    digest = hashlib.sha256()
    total = 0
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            _fail(f"snapshot file is not a single-link regular file: {path}")
        if stat.S_IMODE(metadata.st_mode) != expected_mode:
            _fail(
                f"snapshot file {path} has mode "
                f"{stat.S_IMODE(metadata.st_mode):04o}, expected {expected_mode:04o}"
            )
        if metadata.st_size != expected_size:
            _fail(f"snapshot file {path} has the wrong size")
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            total += len(chunk)
            if total > expected_size:
                _fail(f"snapshot file {path} exceeds its declared size")
            digest.update(chunk)
    finally:
        os.close(descriptor)
    if total != expected_size:
        _fail(f"snapshot file {path} produced the wrong byte count")
    return digest.hexdigest()


def verify_snapshot(
    snapshot: Path | str,
    pin_value: Mapping[str, Any],
    manifest_value: Mapping[str, Any],
) -> dict[str, Any]:
    """Audit a private snapshot's exact tree, modes, sizes, and hashes."""

    pin, manifest = validate_pin_manifest(pin_value, manifest_value)
    root = Path(snapshot)
    expected = _expected_snapshot_files(pin, manifest)
    expected_directories = _expected_snapshot_directories(list(expected))
    directories, files = _snapshot_inventory(root)
    if directories != expected_directories:
        missing = sorted(expected_directories - directories)
        extra = sorted(directories - expected_directories)
        _fail(f"snapshot directory set mismatch: missing={missing}, extra={extra}")
    if files != set(expected):
        missing = sorted(set(expected) - files)
        extra = sorted(files - set(expected))
        _fail(f"snapshot file set mismatch: missing={missing}, extra={extra}")
    for relative, (digest, size, mode) in expected.items():
        actual_digest = _hash_snapshot_file(
            root / PurePosixPath(relative),
            expected_size=size,
            expected_mode=mode,
        )
        if actual_digest != digest:
            _fail(f"snapshot file {relative!r} does not match its SHA-256")
    try:
        manifest_raw = read_bytes_once(
            root / PurePosixPath(pin["repository"]["manifest_path"]),
            limit=MAX_CONTROL_BYTES,
        )
    except CampaignIOError as exc:
        raise NumericCorpusError(str(exc)) from exc
    parsed = parse_manifest_bytes(
        manifest_raw,
        pin=pin,
        label="snapshot manifest",
    )
    if parsed != manifest:
        _fail("snapshot manifest value differs from the validated manifest")
    return {
        "accepted": True,
        "kind": "sparkinterval.verified_numeric_corpus_snapshot.v1",
        "manifest_sha256": pin["repository"]["manifest_sha256"],
        "payload_root_sha256": manifest["payload_root"]["sha256"],
        "source_root_sha256": manifest["source_root"]["sha256"],
    }


def _open_new_snapshot_file(path: Path, mode: int) -> BinaryIO:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
        os.fchmod(descriptor, mode)
        return os.fdopen(descriptor, "wb", closefd=True)
    except OSError as exc:
        raise NumericCorpusError(f"cannot create snapshot file {path}: {exc}") from exc


def _write_exact_bytes(path: Path, raw: bytes, mode: int) -> None:
    with _open_new_snapshot_file(path, 0o600) as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
        os.fchmod(output.fileno(), mode)


def _make_tree_read_only(root: Path) -> None:
    directories: list[Path] = [root]
    for current, names, _ in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in names:
            path = current_path / name
            status = path.lstat()
            if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
                _fail(f"snapshot staging tree contains an unsafe directory: {path}")
            directories.append(path)
    for directory in reversed(directories):
        directory.chmod(0o555)


def _remove_staging_tree(path: Path) -> None:
    def repair(function: Any, item: str, _: Any) -> None:
        try:
            os.chmod(item, 0o700)
            function(item)
        except OSError:
            pass

    if path.exists():
        shutil.rmtree(path, onerror=repair)


def materialize_git_corpus(
    checkout: Path | str,
    pin_value: Mapping[str, Any],
    cache_root: Path | str,
) -> dict[str, Any]:
    """Verify and atomically publish a private, read-only snapshot."""

    corpus = _prepare_git_corpus(checkout, pin_value)
    root = Path(cache_root)
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root_status = root.lstat()
    except OSError as exc:
        raise NumericCorpusError(f"cannot prepare snapshot cache {root}: {exc}") from exc
    if stat.S_ISLNK(root_status.st_mode) or not stat.S_ISDIR(root_status.st_mode):
        _fail(f"snapshot cache must be a non-symlink directory: {root}")
    if stat.S_IMODE(root_status.st_mode) != 0o700:
        _fail("snapshot cache must be a private directory with mode 0700")
    destination = root / snapshot_key_sha256(corpus.pin)
    if destination.exists() or destination.is_symlink():
        _verify_git_files(corpus)
        verify_snapshot(destination, corpus.pin, corpus.manifest)
        return _report(corpus, materialized=True)

    staging: Path | None = Path(
        tempfile.mkdtemp(prefix=".numeric-corpus-", dir=root)
    )
    try:
        assert staging is not None
        manifest_path = staging / PurePosixPath(
            corpus.pin["repository"]["manifest_path"]
        )
        _write_exact_bytes(manifest_path, corpus.manifest_raw, 0o444)
        for record, blob in zip(
            corpus.manifest["payloads"], corpus.payload_blobs, strict=True
        ):
            path = staging / PurePosixPath(record["path"])
            with _open_new_snapshot_file(path, 0o600) as output:
                _stream_blob(
                    corpus.repo,
                    blob,
                    expected_sha256=record["sha256"],
                    expected_size=record["size_bytes"],
                    output=output,
                )
                output.flush()
                os.fsync(output.fileno())
                os.fchmod(output.fileno(), 0o444)
        for record, blob in zip(
            corpus.manifest["source_files"], corpus.source_blobs, strict=True
        ):
            path = staging / PurePosixPath(record["path"])
            final_mode = 0o555 if record["executable"] else 0o444
            with _open_new_snapshot_file(path, 0o600) as output:
                _stream_blob(
                    corpus.repo,
                    blob,
                    expected_sha256=record["sha256"],
                    expected_size=record["size_bytes"],
                    output=output,
                )
                output.flush()
                os.fsync(output.fileno())
                os.fchmod(output.fileno(), final_mode)
        _make_tree_read_only(staging)
        verify_snapshot(staging, corpus.pin, corpus.manifest)
        try:
            staging.rename(destination)
            staging = None
        except FileExistsError:
            verify_snapshot(destination, corpus.pin, corpus.manifest)
        return _report(corpus, materialized=True)
    finally:
        if staging is not None:
            _remove_staging_tree(staging)


def fetch_pinned_repository(
    pin_value: Mapping[str, Any], destination: Path | str
) -> Path:
    """Fetch exactly the pinned commit into a fresh bare resolver repository."""

    _require_safe_git_version()
    pin = validate_pin(pin_value)
    target = Path(destination).absolute()
    if target.exists() or target.is_symlink():
        _fail(f"fetch destination must not already exist: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["init", "--bare", str(target)], label="creating a bare resolver")
    repository = pin["repository"]
    _run_git(
        [
            "-c",
            "fetch.fsckObjects=true",
            "-C",
            str(target),
            "fetch",
            "--no-tags",
            "--depth=1",
            repository["url"],
            repository["commit"],
        ],
        label="fetching the exact pinned commit",
    )
    fetched = _run_git(
        ["-C", str(target), "rev-parse", "--verify", "FETCH_HEAD^{commit}"],
        label="checking the fetched commit",
    ).decode("ascii", "strict").strip()
    if fetched != repository["commit"]:
        _fail("the remote did not return the exact pinned commit")
    _verify_commit(target, repository["commit"])
    return target
