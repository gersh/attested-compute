#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Inspect and replay ternary-Goldbach external-computation evidence.

Successful artifact checks establish only the classification printed in their
JSON result.  In particular, no command silently upgrades an external
transcript or a bounded sample into a proof of the corresponding Lean atom.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from enum import Enum
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.analytic import (  # noqa: E402
    AnalyticArtifactError,
    verify_a7_boundary_file,
    verify_prop77_flint_file,
)
from tg_verifier.a7_flint import (  # noqa: E402
    A7FlintReplayError,
    replay_a7_flint,
)
from tg_verifier.arithmetic import (  # noqa: E402
    LittleMertensBound,
    check_hurst_sample,
    check_little_mertens_sample,
    check_squarefree_sample,
    mobius_linear,
)
from tg_verifier.catalog import (  # noqa: E402
    ATOMS,
    ATOMS_BY_ID,
    CATALOG_SOURCE_COMMIT,
    CatalogError,
)
from tg_verifier.campaign_io import (  # noqa: E402
    require_azure_measured_worker_for_workload,
)
from tg_verifier.cdem_chunk_replay import (  # noqa: E402
    CDEM_CHUNK_REPLAYER_DEFAULT_SOURCE,
    CdemChunkReplayError,
    replay_cdem_production_transcript,
)
from tg_verifier.cdem_abel_artifact import write_artifact_exclusive  # noqa: E402
from tg_verifier.evidence import (  # noqa: E402
    CDEM_REGISTERED_RESULT,
    CDEM_REGISTERED_RESULT_SHA256,
    EvidenceError,
    RAMARE_RETAINED_FOCUSED_SHA256,
    RAMARE_RETAINED_RAW_SHA256,
    compare_claude_math_inventory,
    load_decimal_json,
    verify_cdem_abel_text,
    verify_cdem_abel_transcript,
    verify_ramare_zuniga_report,
)
from tg_verifier.finite_campaigns import (  # noqa: E402
    PSI_SOURCE_LIMIT,
    iter_psi_certificate,
    prop1224_first_extension_q,
    prop1224_source_q_count,
    verify_psi_chain,
)
from tg_verifier.execution import (  # noqa: E402
    ExecutionReplayError,
    build_and_run_cdem_abel,
)
from tg_verifier.mobius_cuda import (  # noqa: E402
    MobiusReceiptError,
    verify_mobius_receipt_chain,
)
from tg_verifier.r2star import (  # noqa: E402
    R2STAR_SOURCE_LIMIT,
    iter_r2star_certificate,
    verify_r2star_chain,
)
from tg_verifier.prop1224_directed import (  # noqa: E402
    create_directed_prop1224_sample,
    verify_directed_prop1224_sample,
)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _emit(value: Any, *, pretty: bool) -> None:
    print(
        json.dumps(
            _jsonable(value),
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def _catalog_record(atom: Any) -> dict[str, Any]:
    return {
        "id": atom.atom_id,
        "lean_name": atom.lean_name,
        "claim": atom.claim,
        "verifier": atom.verifier,
        "present_evidence": atom.present_evidence,
        "completion_requirement": atom.completion_requirement,
        "feasibility": atom.feasibility,
        "work_unit": atom.work_unit,
        "target_work_items": atom.target_work_items,
    }


def command_catalog(args: argparse.Namespace) -> int:
    atoms = ATOMS if args.atom is None else (ATOMS_BY_ID[args.atom],)
    _emit(
        {
            "schema_version": 1,
            "kind": "tg_external_atom_catalog",
            "atom_count": len(atoms),
            "atoms": [_catalog_record(atom) for atom in atoms],
        },
        pretty=args.pretty,
    )
    return 0


def command_sync_inventory(args: argparse.Namespace) -> int:
    _emit(
        compare_claude_math_inventory(
            args.inventory, require_card_files=args.cards
        ).as_json(),
        pretty=args.pretty,
    )
    return 0


def command_verify_a7(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    _emit(
        verify_a7_boundary_file(
            args.artifact, require_retained_identity=args.retained
        ),
        pretty=args.pretty,
    )
    return 0


_A7_RETAINED_ARTIFACT_SHA256 = (
    "ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29"
)
_A7_REGISTERED_RESULT = b"true"
_A7_REGISTERED_RESULT_SHA256 = (
    "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b"
)


def _write_a7_registered_result(
    replay: Mapping[str, Any], output: Path
) -> dict[str, Any]:
    """Exclusively write the closed A.7 result after a full pinned replay.

    The result is derived from the replay report, never accepted from a
    caller. Requiring the retained artifact identity here prevents
    ``--allow-unpinned`` from producing bytes eligible for the registered
    production invocation.
    """

    required_true = (
        "artifact_bytes_match_pinned_sha256",
        "four_edge_dyadic_cover_verified",
        "every_leaf_flint_box_recomputed",
        "every_exact_leaf_endpoint_matched",
        "all_denominator_and_zeta_nonvanishing_guards_checked",
        "strict_norm_square_bound_verified_under_flint_semantics",
        "external_analytic_verification_complete",
    )
    if (
        replay.get("accepted") is not True
        or replay.get("artifact_kind") != "ch25_a7_boundary"
        or replay.get("verification_class")
        != "complete_external_flint_arb_leaf_replay"
        or replay.get("artifact_sha256") != _A7_RETAINED_ARTIFACT_SHA256
        or replay.get("python_flint_version") != "0.9.0"
        or replay.get("flint_version") != "3.6.0"
        or replay.get("flint_release") != 30_600
        or replay.get("leaf_count") != 16_191
        or any(replay.get(field) is not True for field in required_true)
        or replay.get("ordinary_kernel_lean_proof") is not False
        or replay.get("mathlib_zeta_realization_theorem_present") is not False
        or replay.get("lean_atom_discharged") is not False
    ):
        raise EvidenceError(
            "checked A.7 replay differs from the closed registered invocation"
        )
    if hashlib.sha256(_A7_REGISTERED_RESULT).hexdigest() != (
        _A7_REGISTERED_RESULT_SHA256
    ):
        raise EvidenceError("internal A.7 registered-result identity differs")

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(_A7_REGISTERED_RESULT)
    except FileExistsError as error:
        raise EvidenceError(
            f"refusing to overwrite an existing A.7 result artifact: {output}"
        ) from error
    return {
        "path": str(output.resolve()),
        "sha256": _A7_REGISTERED_RESULT_SHA256,
        "bytes": len(_A7_REGISTERED_RESULT),
        "format": "literal_ascii_true_no_newline_v1",
    }


def command_replay_a7(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    replay = replay_a7_flint(
        args.artifact,
        require_retained_identity=not args.allow_unpinned,
    )
    if args.registered_result_output is not None:
        replay = {
            **replay,
            "registered_result_artifact": _write_a7_registered_result(
                replay, args.registered_result_output
            ),
        }
    _emit(replay, pretty=args.pretty)
    return 0


def command_verify_prop77(args: argparse.Namespace) -> int:
    _emit(verify_prop77_flint_file(args.artifact), pretty=args.pretty)
    return 0


def command_verify_ramare(args: argparse.Namespace) -> int:
    if args.retained and args.raw_report is None:
        raise ValueError("--retained requires --raw-report")
    result = verify_ramare_zuniga_report(
        args.artifact,
        args.raw_report,
        expected_focused_sha256=(
            RAMARE_RETAINED_FOCUSED_SHA256 if args.retained else None
        ),
        expected_raw_sha256=(
            RAMARE_RETAINED_RAW_SHA256 if args.retained else None
        ),
    )
    _emit(result.as_json(), pretty=args.pretty)
    return 0


def command_verify_cdem(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    result = verify_cdem_abel_transcript(args.artifact)
    _emit(result.as_json(), pretty=args.pretty)
    return 0


def command_run_cdem(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    receipt, transcript = build_and_run_cdem_abel(
        args.source,
        compiler=args.compiler,
        block_size=args.block_size,
        threads=args.threads,
        max_seconds=args.max_seconds,
        repeats=args.repeats,
    )
    if args.transcript_output is not None:
        args.transcript_output.parent.mkdir(parents=True, exist_ok=True)
        args.transcript_output.write_text(transcript, encoding="utf-8")
        receipt["transcript_output"] = str(args.transcript_output.resolve())
    _emit(receipt, pretty=args.pretty)
    return 0


def command_replay_cdem_chunks(args: argparse.Namespace) -> int:
    """Independently replay selected or all bounded-memory Abel chunks."""

    # A single production chunk spans about 10^12 recurrence rows.  The
    # number of selected chunks is therefore not a valid tiny-KAT bound.
    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    receipt = replay_cdem_production_transcript(
        args.transcript,
        indices=args.index,
        source=args.source,
        compiler=args.compiler,
        workers=args.workers,
        compile_max_seconds=args.compile_max_seconds,
        chunk_max_seconds=args.chunk_max_seconds,
    )
    _emit(receipt, pretty=args.pretty)
    return 0


def _write_cdem_registered_result(transcript: str, output: Path) -> dict[str, Any]:
    """Write the exact closed-registry result derived from checked output.

    This helper deliberately accepts the producer transcript, not a caller-
    supplied result string.  The production command invokes it only after the
    separate all-chunk replay has returned successfully.  Exclusive creation
    also prevents a pre-existing result artifact from being silently reused.
    """

    checked = verify_cdem_abel_text(transcript)
    registered_result = checked.metrics.get("registered_result")
    registered_result_sha256 = checked.metrics.get("registered_result_sha256")
    if registered_result != CDEM_REGISTERED_RESULT:
        raise EvidenceError("checked CDEM result differs from the closed Lean registry")
    if registered_result_sha256 != CDEM_REGISTERED_RESULT_SHA256:
        raise EvidenceError("checked CDEM result hash differs from the closed Lean registry")
    try:
        payload = registered_result.encode("ascii")
    except (AttributeError, UnicodeEncodeError) as error:
        raise EvidenceError("checked CDEM registered result is not ASCII text") from error
    if hashlib.sha256(payload).hexdigest() != CDEM_REGISTERED_RESULT_SHA256:
        raise EvidenceError("CDEM registered-result bytes have an unexpected SHA-256")

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as error:
        raise EvidenceError(
            f"refusing to overwrite an existing CDEM result artifact: {output}"
        ) from error
    return {
        "path": str(output.resolve()),
        "sha256": CDEM_REGISTERED_RESULT_SHA256,
        "bytes": len(payload),
        "format": "canonical_decimal_natural_no_newline_v1",
    }


def command_run_cdem_full(args: argparse.Namespace) -> int:
    """Run the reviewed producer and the separate all-chunk implementation."""

    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    receipt, transcript = build_and_run_cdem_abel(
        args.source,
        compiler=args.compiler,
        block_size=args.block_size,
        threads=args.threads,
        max_seconds=args.max_seconds,
        repeats=1,
    )
    args.transcript_output.parent.mkdir(parents=True, exist_ok=True)
    args.transcript_output.write_text(transcript, encoding="utf-8")
    replay = replay_cdem_production_transcript(
        args.transcript_output,
        source=args.replay_source,
        compiler=args.compiler,
        workers=args.workers,
        compile_max_seconds=args.compile_max_seconds,
        chunk_max_seconds=args.chunk_max_seconds,
    )
    closed_artifact = None
    if getattr(args, "artifact_output", None) is not None:
        closed_artifact = write_artifact_exclusive(
            transcript, args.artifact_output
        )
    registered_result_artifact = None
    if args.registered_result_output is not None:
        registered_result_artifact = _write_cdem_registered_result(
            transcript, args.registered_result_output
        )
    _emit(
        {
            "schema_version": 1,
            "classification": "full_external_producer_plus_independent_all_chunk_replay",
            "producer": receipt,
            "independent_replay": replay,
            "transcript_output": str(args.transcript_output.resolve()),
            "closed_lean_artifact": closed_artifact,
            "registered_result_artifact": registered_result_artifact,
            "full_source_campaign": True,
            "lean_atom_discharged": False,
        },
        pretty=args.pretty,
    )
    return 0


def command_sample_arithmetic(args: argparse.Namespace) -> int:
    limit = args.limit
    require_azure_measured_worker_for_workload(
        exact_production=False,
        work_bounds=(limit,),
    )
    mu = mobius_linear(limit)
    results: dict[str, Any] = {}
    if limit >= 33:
        results["mertens-hurst"] = check_hurst_sample(mu, 33, limit)
    results["platt-little-mertens-2-11"] = check_little_mertens_sample(
        mu, 1, limit, LittleMertensBound.SQRT_TWO_OVER_X
    )
    if limit >= 3:
        results["platt-little-mertens-stronger"] = check_little_mertens_sample(
            mu, 3, limit, LittleMertensBound.ONE_OVER_TWO_SQRT_X
        )
    if limit >= 9_243:
        results["cdem-squarefree-b1"] = check_squarefree_sample(
            mu, 9_243, limit, Fraction(151, 2_000)
        )
    if limit >= 438_429:
        results["cdem-squarefree-b2"] = check_squarefree_sample(
            mu, 438_429, limit, Fraction(57, 2_000)
        )
    _emit(
        {
            "schema_version": 1,
            "classification": "bounded_exact_sample_not_full_verification",
            "sample_limit": limit,
            "results": results,
        },
        pretty=args.pretty,
    )
    return 0


def command_verify_mobius_receipts(args: argparse.Namespace) -> int:
    reports = [load_decimal_json(path) for path in args.receipts]
    result = verify_mobius_receipt_chain(reports)
    _emit(
        {
            "schema_version": 1,
            "classification": (
                "structural_full_range_receipt_claim_not_execution_authenticated"
                if result.structurally_claims_full_source_range
                else "bounded_structural_transition_chain_not_execution_authenticated"
            ),
            "result": result,
            "producer_reports_every_row_cpu_compared": True,
            "chain_checker_replayed_rows": False,
            "execution_authenticated": False,
            "lean_atoms_discharged": False,
        },
        pretty=args.pretty,
    )
    return 0


def command_verify_psi_range(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=args.limit == PSI_SOURCE_LIMIT,
        work_bounds=(
            args.limit,
            min(args.chunk_span, args.limit),
            min(args.segment_size, args.limit),
            args.series_terms,
        ),
    )
    chunks = iter_psi_certificate(
        args.limit,
        chunk_span=args.chunk_span,
        scale_bits=args.scale_bits,
        series_terms=args.series_terms,
        segment_size=args.segment_size,
    )
    result = verify_psi_chain(
        chunks,
        expected_limit=args.limit,
        segment_size=args.segment_size,
    )
    _emit(
        {
            "schema_version": 1,
            "classification": (
                "complete_exact_external_reference_not_lean_discharge"
                if args.limit == PSI_SOURCE_LIMIT
                else "bounded_exact_sample_not_full_verification"
            ),
            "result": result,
        },
        pretty=args.pretty,
    )
    return 0


def command_verify_r2star_range(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=args.limit == R2STAR_SOURCE_LIMIT,
        work_bounds=(
            args.limit,
            min(args.block_size, args.limit),
            args.series_terms,
            args.harmonic_terms,
        ),
    )
    chunks = iter_r2star_certificate(
        args.limit,
        chunk_span=args.block_size,
        scale_bits=args.scale_bits,
        series_terms=args.series_terms,
        harmonic_terms=args.harmonic_terms,
    )
    result = verify_r2star_chain(
        chunks,
        expected_limit=args.limit,
    )
    _emit(
        {
            "schema_version": 1,
            "classification": (
                "complete_exact_external_reference_not_lean_discharge"
                if args.limit == R2STAR_SOURCE_LIMIT
                else "bounded_exact_sample_not_full_verification"
            ),
            "result": result,
        },
        pretty=args.pretty,
    )
    return 0


def command_prop1224_scheduler(args: argparse.Namespace) -> int:
    _emit(
        {
            "schema_version": 1,
            "classification": "exact_q_scheduler_only",
            "first_q": 1,
            "first_210_divisible_extension_q": prop1224_first_extension_q(),
            "terminal_sentinel": 22_000_000_000,
            "admissible_q_rows": prop1224_source_q_count(),
            "bounded_directed_rational_producer_available": True,
            "transcendental_window_semantics_verified": False,
            "lean_atom_discharged": False,
        },
        pretty=args.pretty,
    )
    return 0


def command_verify_prop1224_sample(args: argparse.Namespace) -> int:
    require_azure_measured_worker_for_workload(
        exact_production=False,
        work_bounds=(args.max_pairs, args.log_terms),
    )
    sample = create_directed_prop1224_sample(
        args.q,
        bits=args.bits,
        log_terms=args.log_terms,
        max_pairs=args.max_pairs,
    )
    checked_pairs = verify_directed_prop1224_sample(sample)
    pairs = sample.window.pairs
    if pairs:
        margins = [
            Fraction(
                pair.margin_lower_numerator,
                pair.margin_lower_denominator,
            )
            for pair in pairs
        ]
        minimum_margin = min(margins)
        minimum_index = margins.index(minimum_margin)
        minimum_at_k: int | None = pairs[minimum_index].k
        first_k: int | None = pairs[0].k
        last_k: int | None = pairs[-1].k
    else:
        minimum_margin = None
        minimum_at_k = None
        first_k = None
        last_k = None
    _emit(
        {
            "schema_version": 1,
            "classification": (
                "bounded_directed_rational_sample_not_full_verification"
            ),
            "q": sample.parameters.q,
            "prime_factors": sample.parameters.prime_factors,
            "phi_q": sample.parameters.phi_q,
            "precision_bits": sample.parameters.bits,
            "log_series_terms": sample.parameters.log_terms,
            "varpi": sample.parameters.varpi,
            "lambda": sample.parameters.lambda_,
            "conservative_first_k": first_k,
            "conservative_last_k": last_k,
            "checked_pairs": checked_pairs,
            "minimum_margin_lower": minimum_margin,
            "minimum_margin_at_k": minimum_at_k,
            "endpoint_enclosures_recomputed": (
                sample.endpoint_enclosures_recomputed
            ),
            "margin_enclosures_recomputed": sample.margin_enclosures_recomputed,
            "exact_gq_recomputed": True,
            "native_float_used_in_decisions": (
                sample.native_float_used_in_decisions
            ),
            "theorem_backed_base_intervals": {
                "euler_gamma": sample.parameters.euler_gamma,
                "ramare_ce": sample.parameters.ramare_ce,
            },
            "source_q_rows_checked": 1,
            "source_q_rows_total": prop1224_source_q_count(),
            "full_source_campaign": sample.full_source_campaign,
            "lean_realization_proved": sample.lean_realization_proved,
            "lean_atom_discharged": False,
        },
        pretty=args.pretty,
    )
    return 0


def command_audit_root(args: argparse.Namespace) -> int:
    root = args.claude_math_root.resolve()
    checks: dict[str, Any] = {}
    git_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=no"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if git_status.returncode != 0:
        raise ValueError(
            "cannot inspect claude_math tracked worktree: "
            + git_status.stderr.strip()
        )
    if git_status.stdout:
        raise ValueError(
            "claude_math tracked worktree must be clean before an exact audit"
        )
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="ascii",
        timeout=30,
    )
    if git_head.returncode != 0:
        raise ValueError(f"cannot read claude_math Git HEAD: {git_head.stderr.strip()}")
    actual_head = git_head.stdout.strip()
    if actual_head != CATALOG_SOURCE_COMMIT:
        raise ValueError(
            "claude_math checkout differs from the catalog source commit: "
            f"expected {CATALOG_SOURCE_COMMIT}, got {actual_head}"
        )
    checks["source-commit"] = {
        "accepted": True,
        "classification": "clean_tracked_worktree_at_pinned_git_head",
        "commit": actual_head,
        "tracked_worktree_clean": True,
    }
    build_freshness = subprocess.run(
        [
            "lake",
            "--rehash",
            "--log-level=error",
            "--no-build",
            "build",
            "+Math.Problems.TernaryGoldbach.Statement",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    if build_freshness.returncode != 0:
        raise ValueError(
            "ternary-Goldbach Statement build artifacts are absent or stale; "
            "run the repository's documented source build first:\n"
            + build_freshness.stdout
            + build_freshness.stderr
        )
    build_output = build_freshness.stdout + build_freshness.stderr
    checks["statement-build-freshness"] = {
        "accepted": True,
        "classification": (
            "lake_rehashed_no_build_trace_check_all_dependencies_up_to_date"
        ),
        "target": "+Math.Problems.TernaryGoldbach.Statement",
        "source_build_performed_by_audit": False,
        "all_source_traces_rehashed": True,
        "all_target_build_artifacts_reported_up_to_date": True,
        "output_sha256": hashlib.sha256(build_output.encode("utf-8")).hexdigest(),
    }
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".lean", delete=False
    ) as source:
        source.write("import Math.Problems.TernaryGoldbach.Statement\n")
        source.write(
            "#print axioms Math.Problems.TernaryGoldbach.ternary_goldbach\n"
        )
        axiom_source = Path(source.name)
    try:
        lean = subprocess.run(
            ["lake", "env", "lean", str(axiom_source)],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )
    finally:
        axiom_source.unlink(missing_ok=True)
    if lean.returncode != 0:
        raise ValueError(
            "fresh ternary-Goldbach #print axioms failed:\n"
            + lean.stdout
            + lean.stderr
        )
    lines = lean.stdout.splitlines()
    prefix = "'Math.Problems.TernaryGoldbach.ternary_goldbach' depends on axioms: ["
    if not lines or not lines[0].startswith(prefix) or not lines[-1].endswith("]"):
        raise ValueError("fresh #print axioms output has an unexpected format")
    axiom_names = [lines[0][len(prefix) :].removesuffix(",")]
    for line in lines[1:]:
        axiom_names.append(line.strip().removesuffix("]").removesuffix(","))
    base_names = {"propext", "Classical.choice", "Quot.sound"}
    external_names = {atom.lean_name for atom in ATOMS}
    present_external = external_names.intersection(axiom_names)
    native_names = [
        name for name in axiom_names if "._native.native_decide.ax_" in name
    ]
    unknown_names = [
        name
        for name in axiom_names
        if name not in base_names
        and name not in external_names
        and "._native.native_decide.ax_" not in name
    ]
    if present_external != external_names:
        missing = sorted(external_names - present_external)
        raise ValueError(f"fresh #print axioms is missing catalog atoms: {missing}")
    if unknown_names:
        raise ValueError(
            "fresh #print axioms contains uncataloged non-native atoms: "
            f"{unknown_names}"
        )
    checks["fresh-lean-axioms"] = {
        "accepted": True,
        "classification": "fresh_lean_print_axioms_partition",
        "total_axioms": len(axiom_names),
        "foundational_axioms": len(base_names.intersection(axiom_names)),
        "named_external_atoms": len(present_external),
        "generated_native_decide_axioms": len(native_names),
        "uncataloged_non_native_atoms": 0,
        "stdout_sha256": hashlib.sha256(lean.stdout.encode("utf-8")).hexdigest(),
    }
    paths = {
        "inventory": root / "problems/ternary-goldbach/citations/inventory.json",
        "a7": root / "ext/ch25_certificates/certificates/a7_boundary.json",
        "prop77": root / "ext/ch25_certificates/certificates/ch25_prop77_flint.json",
        "ramare": root
        / "problems/ternary-goldbach/ramare_zuniga_2024_lemma_6_2_full21e9.json",
        "ramare_raw": root
        / "problems/ternary-goldbach/ramare_2013_seams_full21e9.json",
    }
    checks["catalog-sync"] = compare_claude_math_inventory(
        paths["inventory"], require_card_files=True
    ).as_json()
    checks["ch25-a7-boundary"] = verify_a7_boundary_file(
        paths["a7"], require_retained_identity=True
    )
    checks["platt-head-2e4"] = verify_prop77_flint_file(paths["prop77"])
    checks["ramare-zuniga-lemma-6-2"] = verify_ramare_zuniga_report(
        paths["ramare"],
        paths["ramare_raw"],
        expected_focused_sha256=RAMARE_RETAINED_FOCUSED_SHA256,
        expected_raw_sha256=RAMARE_RETAINED_RAW_SHA256,
    ).as_json()
    if args.cdem_transcript is not None:
        checks["cdem-table-abel"] = verify_cdem_abel_transcript(
            args.cdem_transcript
        ).as_json()

    final_git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="ascii",
        timeout=30,
    )
    final_git_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=no"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if (
        final_git_head.returncode != 0
        or final_git_head.stdout.strip() != actual_head
        or final_git_status.returncode != 0
        or bool(final_git_status.stdout)
    ):
        raise ValueError("claude_math tracked source changed during the audit")
    final_build_freshness = subprocess.run(
        [
            "lake",
            "--rehash",
            "--log-level=error",
            "--no-build",
            "build",
            "+Math.Problems.TernaryGoldbach.Statement",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    if final_build_freshness.returncode != 0:
        raise ValueError(
            "ternary-Goldbach Statement build freshness changed during audit:\n"
            + final_build_freshness.stdout
            + final_build_freshness.stderr
        )
    checks["post-audit-source-stability"] = {
        "accepted": True,
        "classification": "rechecked_git_identity_and_rehashed_lake_traces",
        "commit_unchanged": True,
        "tracked_worktree_remained_clean": True,
        "statement_build_remained_up_to_date": True,
    }

    checked_ids = {
        key
        for key in checks
        if key
        not in {
            "catalog-sync",
            "source-commit",
            "statement-build-freshness",
            "fresh-lean-axioms",
            "post-audit-source-stability",
        }
    }
    status = []
    for atom in ATOMS:
        status.append(
            {
                "id": atom.atom_id,
                "artifact_check_run": atom.atom_id in checked_ids,
                "lean_atom_discharged": False,
                "remaining_requirement": atom.completion_requirement,
            }
        )
    _emit(
        {
            "schema_version": 1,
            "classification": "artifact_audit_not_lean_axiom_discharge",
            "checks": checks,
            "atoms": status,
        },
        pretty=args.pretty,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    subcommands = parser.add_subparsers(dest="command", required=True)

    catalog = subcommands.add_parser("catalog", help="print the exact 13-atom catalog")
    catalog.add_argument("--atom", choices=sorted(ATOMS_BY_ID))
    catalog.set_defaults(handler=command_catalog)

    sync = subcommands.add_parser("sync-inventory", help="compare with a Lean inventory")
    sync.add_argument("inventory", type=Path)
    sync.add_argument(
        "--cards", action="store_true", help="also require and hash all mapped card files"
    )
    sync.set_defaults(handler=command_sync_inventory)

    a7 = subcommands.add_parser("verify-a7", help="check an A.7 boundary transcript")
    a7.add_argument("artifact", type=Path)
    a7.add_argument(
        "--retained",
        action="store_true",
        help="require the exact retained ternary-Goldbach artifact bytes",
    )
    a7.set_defaults(handler=command_verify_a7)

    a7_replay = subcommands.add_parser(
        "replay-a7-flint",
        help="recompute every A.7 boundary leaf with pinned FLINT/Arb",
        description="Recompute every A.7 boundary leaf with pinned FLINT/Arb.",
    )
    a7_replay.add_argument("artifact", type=Path)
    a7_replay.add_argument(
        "--allow-unpinned",
        action="store_true",
        help="accept a structurally valid artifact other than the retained one",
    )
    a7_replay.add_argument(
        "--registered-result-output",
        type=Path,
        help=(
            "after the full pinned replay succeeds, exclusively write the "
            "literal true consumed by the closed Lean invocation"
        ),
    )
    a7_replay.set_defaults(handler=command_replay_a7)

    prop77 = subcommands.add_parser("verify-prop77", help="check a Prop. 7.7 FLINT summary")
    prop77.add_argument("artifact", type=Path)
    prop77.set_defaults(handler=command_verify_prop77)

    ramare = subcommands.add_parser("verify-ramare", help="check the R2Star report")
    ramare.add_argument("artifact", type=Path)
    ramare.add_argument("--raw-report", type=Path)
    ramare.add_argument(
        "--retained",
        action="store_true",
        help="require the exact retained focused and raw report identities",
    )
    ramare.set_defaults(handler=command_verify_ramare)

    cdem = subcommands.add_parser("verify-cdem-abel", help="check CDEM full-run output")
    cdem.add_argument("artifact", type=Path)
    cdem.set_defaults(handler=command_verify_cdem)

    cdem_run = subcommands.add_parser(
        "run-cdem-abel",
        help="compile reviewed source and replay the complete CDEM Abel recurrence",
        description=(
            "Hash and compile the reviewed CDEM source, run an independent "
            "small preflight, then replay the complete exact recurrence."
        ),
    )
    cdem_run.add_argument("source", type=Path)
    cdem_run.add_argument("--compiler", default="g++")
    cdem_run.add_argument("--block-size", type=int, default=5_000_000)
    cdem_run.add_argument("--threads", type=int, default=8)
    cdem_run.add_argument("--max-seconds", type=int, default=900)
    cdem_run.add_argument("--repeats", type=int, default=1)
    cdem_run.add_argument("--transcript-output", type=Path)
    cdem_run.set_defaults(handler=command_run_cdem)

    cdem_chunks = subcommands.add_parser(
        "replay-cdem-abel-chunks",
        help="independently replay the bounded-memory CDEM chunk transcript",
        description=(
            "Compile a separately reviewed bounded-memory implementation and "
            "recompute selected chunks, or all 1,000 chunks by default, from "
            "a complete CDEM Abel production transcript."
        ),
    )
    cdem_chunks.add_argument("transcript", type=Path)
    cdem_chunks.add_argument(
        "--source", type=Path, default=CDEM_CHUNK_REPLAYER_DEFAULT_SOURCE
    )
    cdem_chunks.add_argument("--compiler", default="g++")
    cdem_chunks.add_argument("--workers", type=int, default=8)
    cdem_chunks.add_argument("--compile-max-seconds", type=int, default=120)
    cdem_chunks.add_argument("--chunk-max-seconds", type=int, default=120)
    cdem_chunks.add_argument(
        "--index",
        type=int,
        action="append",
        help="replay this zero-based chunk index; repeat to select several",
    )
    cdem_chunks.set_defaults(handler=command_replay_cdem_chunks)

    cdem_full = subcommands.add_parser(
        "run-cdem-abel-full",
        help="run the full producer and independently replay all 1000 chunks",
    )
    cdem_full.add_argument("source", type=Path)
    cdem_full.add_argument("--replay-source", type=Path, required=True)
    cdem_full.add_argument("--compiler", default="g++")
    cdem_full.add_argument("--block-size", type=int, default=5_000_000)
    cdem_full.add_argument("--threads", type=int, default=8)
    cdem_full.add_argument("--workers", type=int, default=8)
    cdem_full.add_argument("--max-seconds", type=int, default=900)
    cdem_full.add_argument("--compile-max-seconds", type=int, default=120)
    cdem_full.add_argument("--chunk-max-seconds", type=int, default=120)
    cdem_full.add_argument("--transcript-output", type=Path, required=True)
    cdem_full.add_argument(
        "--artifact-output",
        type=Path,
        help=(
            "fresh TG-CDEM-ABEL-ARTIFACT-V1 output consumed by the closed "
            "Lean artifact parser"
        ),
    )
    cdem_full.add_argument(
        "--registered-result-output",
        type=Path,
        help=(
            "after producer and all-chunk replay succeed, exclusively write "
            "the exact canonical natural consumed by the closed Lean invocation"
        ),
    )
    cdem_full.set_defaults(handler=command_run_cdem_full)

    sample = subcommands.add_parser(
        "sample-arithmetic", help="run bounded exact CPU falsification checks"
    )
    sample.add_argument("--limit", type=int, default=64)
    sample.set_defaults(handler=command_sample_arithmetic)

    mobius_receipts = subcommands.add_parser(
        "verify-mobius-receipts",
        help="check and compose hash-linked CUDA Moebius transition receipts",
    )
    mobius_receipts.add_argument("receipts", type=Path, nargs="+")
    mobius_receipts.set_defaults(handler=command_verify_mobius_receipts)

    psi = subcommands.add_parser(
        "verify-psi-range",
        help="produce and exactly check a bounded prime-power psi stream",
    )
    psi.add_argument("--limit", type=int, default=64)
    psi.add_argument("--chunk-span", type=int, default=64)
    psi.add_argument("--segment-size", type=int, default=64)
    psi.add_argument("--scale-bits", type=int, default=128)
    psi.add_argument("--series-terms", type=int, default=48)
    psi.set_defaults(handler=command_verify_psi_range)

    r2star = subcommands.add_parser(
        "verify-r2star-range",
        help="run the exact fixed-point R2Star reference over a finite range",
    )
    r2star.add_argument("--limit", type=int, default=64)
    r2star.add_argument("--scale-bits", type=int, default=128)
    r2star.add_argument("--series-terms", type=int, default=48)
    r2star.add_argument("--harmonic-terms", type=int, default=64)
    r2star.add_argument("--block-size", type=int, default=64)
    r2star.set_defaults(handler=command_verify_r2star_range)

    prop1224 = subcommands.add_parser(
        "prop1224-scheduler",
        help="report the exact q scheduler and its remaining semantic boundary",
    )
    prop1224.set_defaults(handler=command_prop1224_scheduler)

    prop1224_sample = subcommands.add_parser(
        "verify-prop1224-sample",
        help="recompute one complete q window with directed rational arithmetic",
        description=(
            "Recompute one complete conservative Proposition 12.2.4 q window "
            "without caller-supplied endpoint or margin values. This remains "
            "a bounded sample, not the 3,389,047,618-row source campaign."
        ),
    )
    prop1224_sample.add_argument("--q", type=int, default=6_469_693_230)
    prop1224_sample.add_argument("--bits", type=int, default=144)
    prop1224_sample.add_argument("--log-terms", type=int, default=48)
    prop1224_sample.add_argument("--max-pairs", type=int, default=64)
    prop1224_sample.set_defaults(handler=command_verify_prop1224_sample)

    audit = subcommands.add_parser(
        "audit-root", help="audit locally available claude_math artifacts"
    )
    audit.add_argument("claude_math_root", type=Path)
    audit.add_argument("--cdem-transcript", type=Path)
    audit.set_defaults(handler=command_audit_root)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    positive_options = (
        "limit",
        "chunk_span",
        "segment_size",
        "scale_bits",
        "series_terms",
        "harmonic_terms",
        "block_size",
        "q",
        "bits",
        "log_terms",
        "max_pairs",
        "workers",
        "compile_max_seconds",
        "chunk_max_seconds",
    )
    if any(getattr(args, option, 1) < 1 for option in positive_options):
        parser.error("numeric range and precision options must be positive")
    try:
        return int(args.handler(args))
    except (
        A7FlintReplayError,
        AnalyticArtifactError,
        CatalogError,
        CdemChunkReplayError,
        EvidenceError,
        ExecutionReplayError,
        MobiusReceiptError,
        OSError,
        ValueError,
    ) as exc:
        _emit(
            {
                "schema_version": 1,
                "accepted": False,
                "error": str(exc),
            },
            pretty=args.pretty,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
