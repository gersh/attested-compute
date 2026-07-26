# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fixed-index FLINT 3.6 Platt campaign for zeta RH through the PT21 height.

The production range is represented by a formula rather than a twelve-
trillion-entry plan.  Each immutable receipt covers one consecutive index
shard, and the final artifact commits to count, prefix, and shard receipts in
that order with a domain-separated Merkle tree.  A receipt is external
finite-computation evidence, not a Lean theorem or hardware attestation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping, NoReturn

from .campaign_io import (
    CampaignIOError,
    advisory_lock,
    atomic_write_bytes,
    canonical_json_bytes,
    canonical_sha256,
    hash_file_once,
    load_json,
    parse_json_bytes,
    read_bytes_once,
    sha256_bytes,
    write_immutable_json,
)


AUTHOR = "Gershon Bialer"
ATOM = "platt-trudgian-rh-3e12"
LEAN_NAME = (
    "AnalyticNT.ChebyshevPsi."
    "finite_check_platt_trudgian_rh_zeta_3e12"
)
FLINT_COMMIT = "8d5454b96761fafe4d5a9da76a369a602f500f49"
UPSTREAM_MANIFEST_SHA256 = (
    "0500e49592cd2c912e3a0dd150e80a27c23e12d63c771b833d922f2d371f0eba"
)
SOURCE_HEIGHT = 3_000_175_332_800
SOURCE_COUNT = 12_363_153_437_138
PLATT_FIRST_INDEX = 10_000
SOURCE_SENTINEL = SOURCE_COUNT + 1
SOURCE_UPPER_EXCLUSIVE = SOURCE_SENTINEL + 1
PREFIX_LAST_INDEX = PLATT_FIRST_INDEX - 1
DEFAULT_SHARD_SPAN = 10_000_000
DEFAULT_MICRO_BATCH = 4_096
DEFAULT_PRECISION_BITS = 96
DEFAULT_FLINT_THREADS = 1
MAX_RUNNER_BYTES = 1 << 30
MAX_SOURCE_BYTES = 16 << 20
MAX_RECEIPT_BYTES = 4 << 20

PLAN_SCHEMA = "sparkinterval.tg.platt-zeta-campaign.plan.v1"
RECEIPT_SCHEMA = "sparkinterval.tg.platt-zeta-campaign.receipt.v1"
FINAL_SCHEMA = "sparkinterval.tg.platt-zeta-campaign.final.v1"
CAMPAIGN_ALGORITHM = "flint-3.6-platt-turing-index-shards-v1"
RUNNER_SCHEMA = "sparkinterval.tg.platt-zeta-shard.v1"
PLATT_ENGINE = "flint-platt-local-isolation-v1"
REPLAY_ENGINE = "flint-platt-zeta-zeros-replay-v1"
PREFIX_ENGINE = "flint-ordinary-prefix-v1"
COUNT_ENGINE = "flint-exact-zeta-nzeros-v1"

PLAN_NAME = "campaign.json"
CAPTURED_RUNNER = "captured-platt-zeta-shard"
CAPTURED_SOURCE = "captured-tg_platt_zeta_shard.cpp"
CAPTURED_UPSTREAM = "captured-flint-3.6-platt-upstream.json"
COUNT_NAME = "count.json"
PREFIX_NAME = "prefix.json"
FINAL_NAME = "final.json"
LOCK_NAME = ".campaign.lock"
SHARD_DIRECTORY = "shards"
_SHARD_NAME = re.compile(r"receipt-([0-9]{7})\.json\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class PlattZetaCampaignError(RuntimeError):
    """A source identity, range, receipt, or replay failed closed."""


def _fail(message: str) -> NoReturn:
    raise PlattZetaCampaignError(message)


def _integer(value: object, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{name} must be an integer")
    if minimum is not None and value < minimum:
        _fail(f"{name} must be at least {minimum}")
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail(f"{name} must be a lowercase SHA-256 digest")
    return value


def _read(path: Path, limit: int, label: str) -> bytes:
    try:
        return read_bytes_once(path, limit=limit)
    except CampaignIOError as error:
        raise PlattZetaCampaignError(f"cannot read {label}: {error}") from error


def _load(path: Path) -> dict[str, Any]:
    try:
        value = load_json(path, require_canonical=True)
    except CampaignIOError as error:
        raise PlattZetaCampaignError(str(error)) from error
    if not isinstance(value, dict):
        _fail(f"artifact is not an object: {path}")
    return value


def _validate_upstream(raw: bytes) -> dict[str, Any]:
    if sha256_bytes(raw) != UPSTREAM_MANIFEST_SHA256:
        _fail("FLINT upstream manifest bytes differ from the reviewed pin")
    try:
        value = parse_json_bytes(raw, label="FLINT upstream manifest")
    except CampaignIOError as error:
        raise PlattZetaCampaignError(str(error)) from error
    if not isinstance(value, dict):
        _fail("FLINT upstream manifest must be an object")
    required = {
        "kind",
        "name",
        "repository",
        "tag",
        "commit",
        "license",
        "tracked_file_count",
        "tracked_bytes",
        "tracked_tree_hash_domain",
        "tracked_tree_sha256",
        "files",
    }
    if set(value) != required:
        _fail("FLINT upstream manifest fields changed")
    if value["kind"] != "sparkinterval.pinned_upstream_source.v1":
        _fail("FLINT upstream manifest schema changed")
    if value["tag"] != "v3.6.0" or value["commit"] != FLINT_COMMIT:
        _fail("FLINT upstream tag or commit changed")
    if value["license"] != "LGPL-3.0-or-later":
        _fail("FLINT upstream license changed")
    if (
        value["tracked_file_count"] != 10_128
        or value["tracked_bytes"] != 47_815_270
        or value["tracked_tree_hash_domain"]
        != "sparkinterval/git-tracked-source-tree/v1"
        or value["tracked_tree_sha256"]
        != "06b194b828a12c6b6c34d5c1653cadd7d9f3f3356d8f3257a293f9ccf1beade1"
    ):
        _fail("FLINT upstream tracked source-tree identity changed")
    if not isinstance(value["files"], list) or len(value["files"]) < 8:
        _fail("FLINT upstream reviewed closure is incomplete")
    for row in value["files"]:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "size_bytes"}:
            _fail("FLINT upstream file row is malformed")
        _digest(row["sha256"], "upstream file digest")
        _integer(row["size_bytes"], "upstream file size", minimum=1)
    return value


def _plan_without_digest(
    *,
    runner_sha256: str,
    runner_size: int,
    source_sha256: str,
    source_size: int,
    upstream_sha256: str,
    shard_span: int,
    micro_batch: int,
    precision_bits: int,
    flint_threads: int,
    source_upper_exclusive: int,
    mode: str,
) -> dict[str, Any]:
    work = source_upper_exclusive - PLATT_FIRST_INDEX
    shard_count = (work + shard_span - 1) // shard_span
    return {
        "schema": PLAN_SCHEMA,
        "author": AUTHOR,
        "algorithm": CAMPAIGN_ALGORITHM,
        "classification": "external_flint_analytic_computation_not_lean_proof",
        "mode": mode,
        "atom": ATOM,
        "lean_name": LEAN_NAME,
        "source": {
            "height": SOURCE_HEIGHT,
            "multiplicity_count": SOURCE_COUNT,
            "prefix_first_index": 1,
            "prefix_last_index": PREFIX_LAST_INDEX,
            "platt_first_index": PLATT_FIRST_INDEX,
            "last_included_index": SOURCE_COUNT,
            "sentinel_index": SOURCE_SENTINEL,
            "source_upper_exclusive": source_upper_exclusive,
        },
        "geometry": {
            "shard_span": shard_span,
            "shard_count": shard_count,
            "range_rule": (
                "shard i is [10000+i*span, "
                "min(source_upper_exclusive,10000+(i+1)*span))"
            ),
        },
        "configuration": {
            "micro_batch": micro_batch,
            "precision_bits": precision_bits,
            "flint_threads_per_process": flint_threads,
            "production_processes_per_ncc40ads_h100_v5": 40,
        },
        "identities": {
            "runner_sha256": runner_sha256,
            "runner_size": runner_size,
            "runner_source_sha256": source_sha256,
            "runner_source_size": source_size,
            "upstream_manifest_sha256": upstream_sha256,
            "flint_tag": "v3.6.0",
            "flint_commit": FLINT_COMMIT,
        },
        "assurance": {
            "exact_zeta_nzeros_required": mode == "full_source",
            "ordinary_prefix_required": mode == "full_source",
            "platt_turing_isolation_required": True,
            "source_sentinel_required": mode == "full_source",
            "zero_multiplicity_preserved": True,
            "simplicity_assumed": False,
            "replay_engine": REPLAY_ENGINE,
            "execution_attested": False,
            "lean_atom_discharged": False,
        },
    }


def create_plan(
    *,
    runner_sha256: str,
    runner_size: int,
    source_sha256: str,
    source_size: int,
    upstream_sha256: str,
    shard_span: int = DEFAULT_SHARD_SPAN,
    micro_batch: int = DEFAULT_MICRO_BATCH,
    precision_bits: int = DEFAULT_PRECISION_BITS,
    flint_threads: int = DEFAULT_FLINT_THREADS,
    source_upper_exclusive: int = SOURCE_UPPER_EXCLUSIVE,
    allow_bounded_test: bool = False,
) -> dict[str, Any]:
    for value, name in (
        (runner_size, "runner size"),
        (source_size, "source size"),
        (shard_span, "shard span"),
        (micro_batch, "micro batch"),
        (precision_bits, "precision bits"),
        (flint_threads, "FLINT threads"),
    ):
        _integer(value, name, minimum=1)
    for value, name in (
        (runner_sha256, "runner digest"),
        (source_sha256, "source digest"),
        (upstream_sha256, "upstream digest"),
    ):
        _digest(value, name)
    if not PLATT_FIRST_INDEX < source_upper_exclusive <= SOURCE_UPPER_EXCLUSIVE:
        _fail("source upper bound is outside the reviewed index range")
    full = source_upper_exclusive == SOURCE_UPPER_EXCLUSIVE
    if not full and not allow_bounded_test:
        _fail("a shortened campaign requires allow_bounded_test=True")
    if full and shard_span != DEFAULT_SHARD_SPAN:
        _fail("the full source uses fixed ten-million-index shards")
    if full and (micro_batch, precision_bits, flint_threads) != (
        DEFAULT_MICRO_BATCH,
        DEFAULT_PRECISION_BITS,
        DEFAULT_FLINT_THREADS,
    ):
        _fail("the full source uses the reviewed FLINT process configuration")
    plan = _plan_without_digest(
        runner_sha256=runner_sha256,
        runner_size=runner_size,
        source_sha256=source_sha256,
        source_size=source_size,
        upstream_sha256=upstream_sha256,
        shard_span=shard_span,
        micro_batch=micro_batch,
        precision_bits=precision_bits,
        flint_threads=flint_threads,
        source_upper_exclusive=source_upper_exclusive,
        mode="full_source" if full else "bounded_test",
    )
    plan["plan_sha256"] = canonical_sha256(plan)
    return plan


def validate_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, Mapping):
        _fail("campaign plan must be an object")
    document = dict(plan)
    digest = document.pop("plan_sha256", None)
    _digest(digest, "plan digest")
    if canonical_sha256(document) != digest:
        _fail("campaign plan digest is invalid")
    if document.get("schema") != PLAN_SCHEMA or document.get("author") != AUTHOR:
        _fail("campaign plan schema or author changed")
    if document.get("algorithm") != CAMPAIGN_ALGORITHM or document.get("atom") != ATOM:
        _fail("campaign plan algorithm or atom changed")
    identities = document.get("identities")
    source = document.get("source")
    geometry = document.get("geometry")
    configuration = document.get("configuration")
    assurance = document.get("assurance")
    if not all(isinstance(value, dict) for value in (
        identities, source, geometry, configuration, assurance
    )):
        _fail("campaign plan subobjects are malformed")
    assert isinstance(identities, dict)
    assert isinstance(source, dict)
    assert isinstance(geometry, dict)
    assert isinstance(configuration, dict)
    assert isinstance(assurance, dict)
    if identities.get("flint_commit") != FLINT_COMMIT or identities.get("flint_tag") != "v3.6.0":
        _fail("campaign FLINT identity changed")
    for name in ("runner_sha256", "runner_source_sha256", "upstream_manifest_sha256"):
        _digest(identities.get(name), name)
    if source.get("height") != SOURCE_HEIGHT or source.get("multiplicity_count") != SOURCE_COUNT:
        _fail("campaign source theorem constants changed")
    if source.get("platt_first_index") != PLATT_FIRST_INDEX:
        _fail("campaign Platt lower index changed")
    upper = _integer(source.get("source_upper_exclusive"), "source upper", minimum=PLATT_FIRST_INDEX + 1)
    span = _integer(geometry.get("shard_span"), "shard span", minimum=1)
    count = _integer(geometry.get("shard_count"), "shard count", minimum=1)
    if count != (upper - PLATT_FIRST_INDEX + span - 1) // span:
        _fail("campaign shard count differs from its formula")
    full = upper == SOURCE_UPPER_EXCLUSIVE
    if document.get("mode") != ("full_source" if full else "bounded_test"):
        _fail("campaign mode mislabels its range")
    if full and span != DEFAULT_SHARD_SPAN:
        _fail("full-source shard span changed")
    if assurance.get("zero_multiplicity_preserved") is not True or assurance.get("simplicity_assumed") is not False:
        _fail("campaign multiplicity policy changed")
    return {**document, "plan_sha256": digest}


def shard_range(plan: Mapping[str, Any], index: int) -> tuple[int, int]:
    valid = validate_plan(plan)
    index = _integer(index, "shard index", minimum=0)
    count = valid["geometry"]["shard_count"]
    if index >= count:
        _fail("shard index is outside the fixed plan")
    lower = PLATT_FIRST_INDEX + index * valid["geometry"]["shard_span"]
    upper = min(
        valid["source"]["source_upper_exclusive"],
        lower + valid["geometry"]["shard_span"],
    )
    return lower, upper


def initialize_campaign(
    *,
    runner: Path,
    runner_source: Path,
    upstream_manifest: Path,
    output_directory: Path,
    shard_span: int = DEFAULT_SHARD_SPAN,
    micro_batch: int = DEFAULT_MICRO_BATCH,
    precision_bits: int = DEFAULT_PRECISION_BITS,
    flint_threads: int = DEFAULT_FLINT_THREADS,
    source_upper_exclusive: int = SOURCE_UPPER_EXCLUSIVE,
    allow_bounded_test: bool = False,
) -> dict[str, Any]:
    runner_raw = _read(runner, MAX_RUNNER_BYTES, "runner")
    source_raw = _read(runner_source, MAX_SOURCE_BYTES, "runner source")
    upstream_raw = _read(upstream_manifest, MAX_SOURCE_BYTES, "upstream manifest")
    _validate_upstream(upstream_raw)
    plan = create_plan(
        runner_sha256=sha256_bytes(runner_raw),
        runner_size=len(runner_raw),
        source_sha256=sha256_bytes(source_raw),
        source_size=len(source_raw),
        upstream_sha256=sha256_bytes(upstream_raw),
        shard_span=shard_span,
        micro_batch=micro_batch,
        precision_bits=precision_bits,
        flint_threads=flint_threads,
        source_upper_exclusive=source_upper_exclusive,
        allow_bounded_test=allow_bounded_test,
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    captures = (
        (CAPTURED_RUNNER, runner_raw),
        (CAPTURED_SOURCE, source_raw),
        (CAPTURED_UPSTREAM, upstream_raw),
    )
    try:
        with advisory_lock(output_directory / LOCK_NAME):
            for name, raw in captures:
                path = output_directory / name
                if path.exists():
                    if _read(path, len(raw), name) != raw:
                        _fail(f"captured identity changed: {name}")
                else:
                    atomic_write_bytes(path, raw)
            write_immutable_json(output_directory / PLAN_NAME, plan)
            (output_directory / CAPTURED_RUNNER).chmod(
                stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP
            )
    except CampaignIOError as error:
        raise PlattZetaCampaignError(str(error)) from error
    return campaign_status(output_directory)


def _load_setup(directory: Path) -> dict[str, Any]:
    plan = validate_plan(_load(directory / PLAN_NAME))
    identities = plan["identities"]
    for path, digest_name, size_name, limit in (
        (directory / CAPTURED_RUNNER, "runner_sha256", "runner_size", MAX_RUNNER_BYTES),
        (directory / CAPTURED_SOURCE, "runner_source_sha256", "runner_source_size", MAX_SOURCE_BYTES),
    ):
        try:
            actual = hash_file_once(path, limit=limit)
        except CampaignIOError as error:
            raise PlattZetaCampaignError(str(error)) from error
        if actual != (identities[digest_name], identities[size_name]):
            _fail(f"captured identity changed: {path.name}")
    upstream = _read(directory / CAPTURED_UPSTREAM, MAX_SOURCE_BYTES, "upstream")
    _validate_upstream(upstream)
    if sha256_bytes(upstream) != identities["upstream_manifest_sha256"]:
        _fail("captured upstream identity changed")
    return plan


def _run_runner(directory: Path, arguments: list[str]) -> dict[str, Any]:
    runner = directory / CAPTURED_RUNNER
    environment = dict(os.environ)
    completed = subprocess.run(
        [str(runner), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        _fail(f"captured FLINT runner failed: {detail}")
    if len(completed.stdout) > MAX_RECEIPT_BYTES:
        _fail("runner receipt exceeds the byte limit")
    try:
        report = parse_json_bytes(completed.stdout, label="runner receipt")
    except CampaignIOError as error:
        raise PlattZetaCampaignError(str(error)) from error
    if not isinstance(report, dict):
        _fail("runner receipt is not an object")
    return report


def _validate_common(report: Mapping[str, Any], engine: str) -> None:
    if report.get("schema") != RUNNER_SCHEMA or report.get("engine") != engine:
        _fail("runner schema or engine changed")
    if report.get("flint_version") != "3.6.0" or report.get("flint_commit") != FLINT_COMMIT:
        _fail("runner FLINT identity changed")
    if report.get("accepted") is not True:
        _fail("runner did not accept its computation")
    if report.get("execution_attested") is not False or report.get("lean_atom_discharged") is not False:
        _fail("runner made an unsafe trust-boundary claim")
    _integer(report.get("elapsed_milliseconds"), "elapsed milliseconds", minimum=0)


def validate_count_report(report: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema", "engine", "height", "multiplicity_count",
        "counted_with_multiplicity", "flint_version", "flint_commit",
        "elapsed_milliseconds", "execution_attested", "lean_atom_discharged",
        "accepted",
    }
    if set(report) != required:
        _fail("count receipt fields changed")
    _validate_common(report, COUNT_ENGINE)
    if report.get("height") != SOURCE_HEIGHT or report.get("multiplicity_count") != SOURCE_COUNT:
        _fail("exact zeta count differs from the source theorem")
    if report.get("counted_with_multiplicity") is not True:
        _fail("zeta count lost multiplicity")
    return dict(report)


def _parse_arf_dump(value: object, name: str) -> Fraction:
    if not isinstance(value, str) or value.count(" ") != 1:
        _fail(f"{name} is not a FLINT arf_dump_str value")
    mantissa_text, exponent_text = value.split(" ")
    try:
        mantissa = int(mantissa_text, 16)
        exponent = int(exponent_text, 16) if not exponent_text.startswith("-") else -int(exponent_text[1:], 16)
    except ValueError as error:
        raise PlattZetaCampaignError(f"{name} has malformed hexadecimal integers") from error
    if mantissa <= 0:
        _fail(f"{name} must be positive")
    if exponent >= 0:
        return Fraction(mantissa << exponent, 1)
    return Fraction(mantissa, 1 << (-exponent))


_STREAM_FIELDS = {
    "schema", "engine", "first_index", "last_index", "record_count",
    "micro_batch", "flint_calls", "precision_bits", "flint_threads",
    "interval_encoding", "interval_rows_sha256", "first_lower", "first_upper",
    "last_lower", "last_upper", "positive_finite_disjoint_open_intervals",
    "critical_line_certified", "counted_with_multiplicity", "simplicity_assumed",
    "included_cutoff_checked", "sentinel_cutoff_checked", "flint_version",
    "flint_commit", "elapsed_milliseconds", "execution_attested",
    "lean_atom_discharged", "accepted",
}


def validate_stream_report(
    report: Mapping[str, Any],
    *,
    engine: str,
    first_index: int,
    last_index: int,
    micro_batch: int,
    precision_bits: int,
    flint_threads: int,
) -> dict[str, Any]:
    if set(report) != _STREAM_FIELDS:
        _fail("stream receipt fields changed")
    _validate_common(report, engine)
    expected_count = last_index - first_index + 1
    if (
        report.get("first_index"), report.get("last_index"), report.get("record_count")
    ) != (first_index, last_index, expected_count):
        _fail("stream receipt range differs from the fixed request")
    if report.get("micro_batch") != micro_batch or report.get("precision_bits") != precision_bits or report.get("flint_threads") != flint_threads:
        _fail("stream receipt configuration changed")
    _integer(report.get("flint_calls"), "FLINT calls", minimum=1)
    _digest(report.get("interval_rows_sha256"), "interval stream digest")
    if report.get("interval_encoding") != "flint-3.6-dump-str":
        _fail("interval encoding changed")
    if report.get("positive_finite_disjoint_open_intervals") is not True or report.get("critical_line_certified") is not True:
        _fail("stream receipt did not certify its critical-line intervals")
    if report.get("counted_with_multiplicity") is not True or report.get("simplicity_assumed") is not False:
        _fail("stream receipt has an unsafe multiplicity policy")
    if engine == PLATT_ENGINE:
        first_lower = _parse_arf_dump(report.get("first_lower"), "first lower")
        first_upper = _parse_arf_dump(report.get("first_upper"), "first upper")
        last_lower = _parse_arf_dump(report.get("last_lower"), "last lower")
        last_upper = _parse_arf_dump(report.get("last_upper"), "last upper")
        if not (0 < first_lower < first_upper and 0 < last_lower < last_upper):
            _fail("stream endpoint intervals are reversed")
    contains_last = first_index <= SOURCE_COUNT <= last_index
    contains_sentinel = first_index <= SOURCE_SENTINEL <= last_index
    if report.get("included_cutoff_checked") is not contains_last:
        _fail("last-included cutoff check flag is wrong")
    if report.get("sentinel_cutoff_checked") is not contains_sentinel:
        _fail("sentinel cutoff check flag is wrong")
    return dict(report)


def _semantic(report: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(report)
    value.pop("elapsed_milliseconds", None)
    return value


def _receipt_wrapper(
    *, plan_sha256: str, kind: str, index: int | None, report: Mapping[str, Any]
) -> dict[str, Any]:
    semantic = _semantic(report)
    return {
        "schema": RECEIPT_SCHEMA,
        "plan_sha256": plan_sha256,
        "kind": kind,
        "index": index,
        "semantic_report": semantic,
        "semantic_sha256": canonical_sha256(semantic),
        "elapsed_milliseconds": report["elapsed_milliseconds"],
    }


def _validate_wrapper(
    wrapper: Mapping[str, Any], *, plan_sha256: str, kind: str, index: int | None
) -> dict[str, Any]:
    required = {
        "schema", "plan_sha256", "kind", "index", "semantic_report",
        "semantic_sha256", "elapsed_milliseconds",
    }
    if set(wrapper) != required or wrapper.get("schema") != RECEIPT_SCHEMA:
        _fail("campaign receipt wrapper fields changed")
    if (wrapper.get("plan_sha256"), wrapper.get("kind"), wrapper.get("index")) != (
        plan_sha256, kind, index
    ):
        _fail("campaign receipt wrapper is bound to the wrong request")
    semantic = wrapper.get("semantic_report")
    if not isinstance(semantic, dict):
        _fail("campaign semantic report is malformed")
    _digest(wrapper.get("semantic_sha256"), "semantic receipt digest")
    if canonical_sha256(semantic) != wrapper["semantic_sha256"]:
        _fail("semantic receipt digest is invalid")
    _integer(wrapper.get("elapsed_milliseconds"), "elapsed milliseconds", minimum=0)
    return semantic


def _write_receipt(path: Path, wrapper: dict[str, Any]) -> dict[str, Any]:
    try:
        write_immutable_json(path, wrapper)
    except CampaignIOError as error:
        raise PlattZetaCampaignError(str(error)) from error
    return wrapper


def run_count(directory: Path) -> dict[str, Any]:
    plan = _load_setup(directory)
    if plan["mode"] != "full_source":
        _fail("exact source count is only defined for the full campaign")
    report = _run_runner(directory, [
        "--engine", "count", "--height", str(SOURCE_HEIGHT),
        "--expected-count", str(SOURCE_COUNT),
        "--precision", str(plan["configuration"]["precision_bits"]),
        "--threads", "1",
    ])
    validate_count_report(report)
    return _write_receipt(
        directory / COUNT_NAME,
        _receipt_wrapper(plan_sha256=plan["plan_sha256"], kind="count", index=None, report=report),
    )


def run_prefix(directory: Path) -> dict[str, Any]:
    plan = _load_setup(directory)
    if plan["mode"] != "full_source":
        _fail("ordinary prefix is only defined for the full campaign")
    report = _run_runner(directory, [
        "--engine", "ordinary-prefix", "--first-index", "1",
        "--count", str(PREFIX_LAST_INDEX), "--micro-batch", str(PREFIX_LAST_INDEX),
        "--precision", str(plan["configuration"]["precision_bits"]),
        "--threads", "1",
    ])
    validate_stream_report(
        report, engine=PREFIX_ENGINE, first_index=1, last_index=PREFIX_LAST_INDEX,
        micro_batch=PREFIX_LAST_INDEX,
        precision_bits=plan["configuration"]["precision_bits"], flint_threads=1,
    )
    return _write_receipt(
        directory / PREFIX_NAME,
        _receipt_wrapper(plan_sha256=plan["plan_sha256"], kind="prefix", index=None, report=report),
    )


def run_shard(directory: Path, index: int) -> dict[str, Any]:
    plan = _load_setup(directory)
    lower, upper = shard_range(plan, index)
    configuration = plan["configuration"]
    report = _run_runner(directory, [
        "--engine", "platt-isolate", "--first-index", str(lower),
        "--count", str(upper - lower), "--micro-batch", str(configuration["micro_batch"]),
        "--precision", str(configuration["precision_bits"]),
        "--threads", str(configuration["flint_threads_per_process"]),
    ])
    validate_stream_report(
        report, engine=PLATT_ENGINE, first_index=lower, last_index=upper - 1,
        micro_batch=configuration["micro_batch"],
        precision_bits=configuration["precision_bits"],
        flint_threads=configuration["flint_threads_per_process"],
    )
    path = directory / SHARD_DIRECTORY / f"receipt-{index:07d}.json"
    return _write_receipt(
        path,
        _receipt_wrapper(plan_sha256=plan["plan_sha256"], kind="shard", index=index, report=report),
    )


def _load_count(directory: Path, plan: Mapping[str, Any]) -> dict[str, Any] | None:
    path = directory / COUNT_NAME
    if not path.exists():
        return None
    wrapper = _load(path)
    semantic = _validate_wrapper(wrapper, plan_sha256=plan["plan_sha256"], kind="count", index=None)
    report = dict(semantic)
    report["elapsed_milliseconds"] = wrapper["elapsed_milliseconds"]
    validate_count_report(report)
    return wrapper


def _load_prefix(directory: Path, plan: Mapping[str, Any]) -> dict[str, Any] | None:
    path = directory / PREFIX_NAME
    if not path.exists():
        return None
    wrapper = _load(path)
    semantic = _validate_wrapper(wrapper, plan_sha256=plan["plan_sha256"], kind="prefix", index=None)
    report = dict(semantic)
    report["elapsed_milliseconds"] = wrapper["elapsed_milliseconds"]
    validate_stream_report(
        report, engine=PREFIX_ENGINE, first_index=1, last_index=PREFIX_LAST_INDEX,
        micro_batch=PREFIX_LAST_INDEX,
        precision_bits=plan["configuration"]["precision_bits"], flint_threads=1,
    )
    return wrapper


def _shard_paths(directory: Path) -> dict[int, Path]:
    root = directory / SHARD_DIRECTORY
    if not root.exists():
        return {}
    if not root.is_dir():
        _fail("shard receipt path is not a directory")
    result: dict[int, Path] = {}
    # campaign_io deliberately retains sibling advisory-lock files.  They are
    # not receipts and are excluded by the anchored positive glob.
    for path in root.glob("receipt-*.json"):
        match = _SHARD_NAME.fullmatch(path.name)
        if match is None or not path.is_file():
            _fail(f"malformed shard receipt path: {path.name}")
        index = int(match.group(1))
        if index in result:
            _fail(f"duplicate shard receipt index {index}")
        result[index] = path
    return result


def _load_shards(directory: Path, plan: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    previous_last_upper: Fraction | None = None
    previous_index: int | None = None
    for index, path in sorted(_shard_paths(directory).items()):
        if index >= plan["geometry"]["shard_count"]:
            _fail("shard receipt index is outside the fixed plan")
        wrapper = _load(path)
        semantic = _validate_wrapper(
            wrapper, plan_sha256=plan["plan_sha256"], kind="shard", index=index
        )
        lower, upper = shard_range(plan, index)
        report = dict(semantic)
        report["elapsed_milliseconds"] = wrapper["elapsed_milliseconds"]
        validate_stream_report(
            report, engine=PLATT_ENGINE, first_index=lower, last_index=upper - 1,
            micro_batch=plan["configuration"]["micro_batch"],
            precision_bits=plan["configuration"]["precision_bits"],
            flint_threads=plan["configuration"]["flint_threads_per_process"],
        )
        if previous_index is not None and index == previous_index + 1:
            first_lower = _parse_arf_dump(report["first_lower"], "first lower")
            if previous_last_upper is not None and previous_last_upper > first_lower:
                _fail("adjacent shard boundary isolations overlap")
        previous_last_upper = _parse_arf_dump(report["last_upper"], "last upper")
        previous_index = index
        result[index] = wrapper
    return result


def _merkle_root(digests: list[str]) -> str:
    if not digests:
        _fail("cannot form an empty receipt Merkle tree")
    level = [hashlib.sha256(b"\x00" + bytes.fromhex(item)).digest() for item in digests]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(b"\x01" + level[i] + level[i + 1]).digest()
            for i in range(0, len(level), 2)
        ]
    return level[0].hex()


@dataclass(frozen=True)
class CampaignStatus:
    mode: str
    plan_sha256: str
    shard_count: int
    retained_shards: int
    count_ready: bool
    prefix_ready: bool
    complete: bool
    final_ready: bool
    merkle_root_sha256: str | None
    execution_attested: bool = False
    lean_atom_discharged: bool = False

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def campaign_status(directory: Path) -> dict[str, Any]:
    plan = _load_setup(directory)
    count = _load_count(directory, plan)
    prefix = _load_prefix(directory, plan)
    shards = _load_shards(directory, plan)
    full = plan["mode"] == "full_source"
    complete = len(shards) == plan["geometry"]["shard_count"] and (
        not full or (count is not None and prefix is not None)
    )
    root: str | None = None
    if complete:
        digests: list[str] = []
        if full:
            assert count is not None and prefix is not None
            digests += [count["semantic_sha256"], prefix["semantic_sha256"]]
        digests += [shards[index]["semantic_sha256"] for index in range(plan["geometry"]["shard_count"])]
        root = _merkle_root(digests)
    final_ready = (directory / FINAL_NAME).is_file()
    if final_ready:
        final = _load(directory / FINAL_NAME)
        if not complete or final != _expected_final(plan, root):
            _fail("final artifact differs from retained complete receipts")
    return CampaignStatus(
        mode=plan["mode"], plan_sha256=plan["plan_sha256"],
        shard_count=plan["geometry"]["shard_count"], retained_shards=len(shards),
        count_ready=count is not None, prefix_ready=prefix is not None,
        complete=complete, final_ready=final_ready, merkle_root_sha256=root,
    ).as_json()


def _expected_final(plan: Mapping[str, Any], root: str | None) -> dict[str, Any]:
    if root is None:
        _fail("a final artifact requires a complete receipt Merkle root")
    return {
        "schema": FINAL_SCHEMA,
        "author": AUTHOR,
        "atom": ATOM,
        "plan_sha256": plan["plan_sha256"],
        "height": SOURCE_HEIGHT if plan["mode"] == "full_source" else None,
        "multiplicity_count": SOURCE_COUNT if plan["mode"] == "full_source" else None,
        "covered_platt_first_index": PLATT_FIRST_INDEX,
        "covered_upper_exclusive": plan["source"]["source_upper_exclusive"],
        "shard_count": plan["geometry"]["shard_count"],
        "receipt_merkle_rule": "sha256(00||leaf-digest), sha256(01||left||right), duplicate odd right",
        "receipt_merkle_root_sha256": root,
        "zero_multiplicity_preserved": True,
        "simplicity_assumed": False,
        "execution_attested": False,
        "lean_atom_discharged": False,
    }


def finalize_campaign(directory: Path) -> dict[str, Any]:
    status = campaign_status(directory)
    if not status["complete"]:
        _fail("campaign is incomplete")
    plan = _load_setup(directory)
    final = _expected_final(plan, status["merkle_root_sha256"])
    try:
        write_immutable_json(directory / FINAL_NAME, final)
    except CampaignIOError as error:
        raise PlattZetaCampaignError(str(error)) from error
    return campaign_status(directory)


def replay_shard(directory: Path, index: int, *, refined: bool = False) -> dict[str, Any]:
    plan = _load_setup(directory)
    paths = _shard_paths(directory)
    if index not in paths:
        _fail("cannot replay an absent shard receipt")
    retained = _load(paths[index])
    semantic = _validate_wrapper(
        retained, plan_sha256=plan["plan_sha256"], kind="shard", index=index
    )
    lower, upper = shard_range(plan, index)
    configuration = plan["configuration"]
    engine_argument = "platt-zeta-replay" if refined else "platt-isolate"
    # Refined replay is intentionally bounded: it is an audit sample of the
    # named acb_dirichlet_platt_zeta_zeros API, not a byte-identical replay of
    # the count-only isolation encoding.
    count = upper - lower
    if refined:
        count = min(count, 100)
    report = _run_runner(directory, [
        "--engine", engine_argument, "--first-index", str(lower),
        "--count", str(count), "--micro-batch", str(configuration["micro_batch"]),
        "--precision", str(configuration["precision_bits"]),
        "--threads", str(configuration["flint_threads_per_process"]),
    ])
    if refined:
        validate_stream_report(
            report, engine=REPLAY_ENGINE, first_index=lower, last_index=lower + count - 1,
            micro_batch=configuration["micro_batch"],
            precision_bits=configuration["precision_bits"],
            flint_threads=configuration["flint_threads_per_process"],
        )
        return {
            "accepted": True,
            "classification": "refined_named-api-audit-sample",
            "index": index,
            "sample_records": count,
            "interval_rows_sha256": report["interval_rows_sha256"],
            "lean_atom_discharged": False,
        }
    validate_stream_report(
        report, engine=PLATT_ENGINE, first_index=lower, last_index=upper - 1,
        micro_batch=configuration["micro_batch"],
        precision_bits=configuration["precision_bits"],
        flint_threads=configuration["flint_threads_per_process"],
    )
    replay_semantic = _semantic(report)
    if canonical_sha256(replay_semantic) != retained["semantic_sha256"] or replay_semantic != semantic:
        _fail("fresh shard replay differs from the retained semantic receipt")
    return {
        "accepted": True,
        "classification": "byte-independent-semantic-flint-replay",
        "index": index,
        "semantic_sha256": retained["semantic_sha256"],
        "lean_atom_discharged": False,
    }
