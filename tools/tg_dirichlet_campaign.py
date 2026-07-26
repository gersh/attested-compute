#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan, run, and replay Platt Theorem 7.1 Dirichlet-GRH campaigns.

The repository supplies exact primitive-character/range scheduling and a
fail-closed resumable certificate boundary.  A full run additionally requires
producer and checker executables implementing the documented rigorous
completed-L and Turing/argument-principle protocols.  The existing
``run_grh_poc.py`` evaluator is useful for bounded moderate-height work, but
its numeric Turing sanity check is intentionally not accepted here.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.dirichlet_campaign import (  # noqa: E402
    ATOM_ID,
    SOURCE_MAX_Q,
    SOURCE_MIN_Q,
    DirichletCampaignError,
    ScheduleIndex,
    atomic_write,
    canonical_json_bytes,
    capability_report,
    factor_prime_powers,
    finalize_campaign,
    initialize_campaign,
    load_canonical_json,
    primitive_character_count,
    primitive_character_descriptor,
    rerun_external_checkers,
    run_campaign,
    source_height,
    verify_campaign,
)
from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)


def _positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def _nonnegative(text: str) -> int:
    try:
        value = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if value < 0:
        raise argparse.ArgumentTypeError("must be nonnegative")
    return value


def _emit(value: object, pretty: bool) -> None:
    print(
        json.dumps(
            value,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def _write_registered_result(path: Path) -> None:
    """Create literal ``true`` once, after complete source replay succeeds."""

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    for optional in ("O_CLOEXEC", "O_NOFOLLOW"):
        flags |= getattr(os, optional, 0)
    descriptor = os.open(path, flags, 0o400)
    try:
        raw = b"true"
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short registered-result write")
            view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def command_capability(args: argparse.Namespace) -> None:
    _emit(capability_report(), args.pretty)


def command_modulus(args: argparse.Namespace) -> None:
    height = source_height(args.q)
    _emit(
        {
            "q": args.q,
            "factorization": [
                {"prime": prime, "exponent": exponent}
                for prime, exponent in factor_prime_powers(args.q)
            ],
            "primitive_character_count": primitive_character_count(args.q),
            "absolute_height": {
                "numerator": height.numerator,
                "denominator": height.denominator,
            },
        },
        args.pretty,
    )


def command_describe(args: argparse.Namespace) -> None:
    descriptor = primitive_character_descriptor(args.q, args.ordinal)
    height = source_height(args.q)
    _emit(
        {
            **descriptor,
            "absolute_height": {
                "numerator": height.numerator,
                "denominator": height.denominator,
            },
        },
        args.pretty,
    )


def command_schedule(args: argparse.Namespace) -> None:
    schedule = ScheduleIndex.build(args.q_start, args.q_stop)
    _emit(
        {
            "q_start": schedule.q_start,
            "q_stop": schedule.q_stop,
            "total_primitive_characters": schedule.total_characters,
            "nonzero_character_moduli": schedule.nonzero_moduli,
            "schedule_sha256": schedule.schedule_sha256,
        },
        args.pretty,
    )


def command_init(args: argparse.Namespace) -> None:
    _emit(
        initialize_campaign(
            args.root,
            producer=args.producer,
            checker=args.checker,
            characters_per_chunk=args.characters_per_chunk,
            mode=args.mode,
            q_start=args.q_start,
            q_stop=args.q_stop,
        ),
        args.pretty,
    )


def _guard_campaign_arithmetic() -> None:
    """Keep arbitrary pinned backends out of ordinary local CLI execution."""

    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )


def command_run(args: argparse.Namespace) -> None:
    _guard_campaign_arithmetic()
    _emit(
        run_campaign(args.root, max_chunks=args.max_chunks, timeout=args.timeout),
        args.pretty,
    )


def command_verify(args: argparse.Namespace) -> None:
    if args.rerun_checker:
        _guard_campaign_arithmetic()
        result = rerun_external_checkers(args.root, timeout=args.timeout)
    else:
        result = verify_campaign(args.root, require_complete=args.require_complete)
    _emit(result, args.pretty)


def command_finalize(args: argparse.Namespace) -> None:
    _emit(finalize_campaign(args.root), args.pretty)


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _q1_zeta_requirement(input_path: Path) -> dict[str, object]:
    from tg_verifier.zeta_zero_campaign import (
        PLATT_TRUDGIAN_RH_3E12,
        verify_campaign as verify_zeta_campaign,
    )

    # The unified campaign planner binds regular files, not enormous campaign
    # directories.  Accept final.json directly and infer its sibling campaign;
    # retain the directory spelling as a backwards-compatible CLI convenience.
    if input_path.is_dir():
        root = input_path
    else:
        if input_path.name != "final.json":
            raise DirichletCampaignError(
                "q=1 zeta input must be a completed campaign directory or final.json"
            )
        root = input_path.parent
    if input_path.is_file() and input_path.resolve() != (root / "final.json").resolve():
        raise DirichletCampaignError("q=1 zeta final artifact path is not canonical")
    state = verify_zeta_campaign(root, require_complete=True)
    if state["profile"] != PLATT_TRUDGIAN_RH_3E12.name:
        raise DirichletCampaignError(
            "q=1 requires the completed platt-trudgian-rh-3e12 zeta campaign"
        )
    return {
        "kind": "sparkinterval.tg.dirichlet_campaign.q1_zeta_requirement.v1",
        "q": 1,
        "required_height": {"numerator": 100_000_000, "denominator": 1},
        "supplied_profile": state["profile"],
        "supplied_height": PLATT_TRUDGIAN_RH_3E12.height,
        "zeta_campaign_sha256": state["campaign_sha256"],
        "zeta_final_sha256": state["final_sha256"],
        "zeta_plan_file_sha256": _file_sha256(root / "campaign.json"),
        "zeta_final_file_sha256": _file_sha256(root / "final.json"),
        "classification": "required_complete_external_zeta_campaign_boundary",
        "fresh_flint_replay_in_this_command": False,
        "lean_atom_discharged": False,
    }


def _source_document(
    q1: dict[str, object], q2_final: dict[str, object]
) -> dict[str, object]:
    return {
        "kind": "sparkinterval.tg.dirichlet_campaign.source_composition.v1",
        "schema_version": 1,
        "atom_id": ATOM_ID,
        "classification": "complete_external_q1_zeta_plus_q2_dirichlet_composition",
        "q1": q1,
        "q2_through_400000": {
            "paper_character_count": q2_final["characters_covered"],
            "terminal_chain_sha256": q2_final["terminal_chain_sha256"],
            "schedule_sha256": q2_final["schedule_sha256"],
            "coverage_class": q2_final["coverage_class"],
        },
        "exact_positive_conductor_domain_covered": True,
        "external_flint_semantics_trusted": True,
        "lean_realization_proved": False,
        "lean_atom_discharged": False,
    }


def _validate_retained_source_requirement(
    path: Path, q1: dict[str, object]
) -> dict[str, object]:
    value = load_canonical_json(path)
    if not isinstance(value, dict) or set(value) != {
        "kind",
        "q1_zeta",
        "reference_backend_limits",
    }:
        raise DirichletCampaignError(
            "retained q1-zeta-requirement.json fields differ"
        )
    if value["kind"] != "sparkinterval.tg.dirichlet_campaign.source_requirement.v1":
        raise DirichletCampaignError("retained source requirement kind differs")
    if value["q1_zeta"] != q1:
        raise DirichletCampaignError(
            "retained q1 zeta identity differs from supplied campaign"
        )
    limits = value["reference_backend_limits"]
    expected_limit_fields = {
        "maximum_precision_bits",
        "maximum_contour_depth",
        "maximum_contour_evaluations",
        "maximum_grid_refinements",
    }
    if not isinstance(limits, dict) or set(limits) != expected_limit_fields:
        raise DirichletCampaignError("retained reference backend limits differ")
    for name, limit in limits.items():
        minimum = 0 if name in {
            "maximum_contour_evaluations",
            "maximum_grid_refinements",
        } else 1
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < minimum:
            raise DirichletCampaignError(
                f"retained reference backend limit {name} is malformed"
            )
    return value


def command_source(args: argparse.Namespace) -> None:
    """Compose q=1 zeta evidence with the full q>=2 reference campaign."""

    require_azure_measured_worker_for_workload(
        exact_production=True,
        work_bounds=(),
    )
    os.environ["TG_DIRICHLET_FLINT_MAX_PRECISION"] = str(
        args.reference_max_precision
    )
    os.environ["TG_DIRICHLET_FLINT_MAX_CONTOUR_DEPTH"] = str(
        args.reference_max_contour_depth
    )
    os.environ["TG_DIRICHLET_FLINT_MAX_CONTOUR_EVALUATIONS"] = str(
        args.reference_max_contour_evaluations
    )
    os.environ["TG_DIRICHLET_FLINT_MAX_GRID_REFINEMENTS"] = str(
        args.reference_max_grid_refinements
    )
    q1 = _q1_zeta_requirement(args.q1_zeta_input.resolve())
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    plan_path = root / "campaign.json"
    backend = REPOSITORY_ROOT / "tools" / "tg_dirichlet_flint_backend.py"
    if not plan_path.exists():
        if any(root.iterdir()):
            raise DirichletCampaignError(
                "source workspace is nonempty but has no campaign.json"
            )
        initialize_campaign(
            root,
            producer=backend,
            checker=backend,
            characters_per_chunk=args.characters_per_chunk,
            mode="full_source",
            q_start=SOURCE_MIN_Q,
            q_stop=SOURCE_MAX_Q,
        )
    source_requirement = {
        "kind": "sparkinterval.tg.dirichlet_campaign.source_requirement.v1",
        "q1_zeta": q1,
        "reference_backend_limits": {
            "maximum_precision_bits": args.reference_max_precision,
            "maximum_contour_depth": args.reference_max_contour_depth,
            "maximum_contour_evaluations": args.reference_max_contour_evaluations,
            "maximum_grid_refinements": args.reference_max_grid_refinements,
        },
    }
    requirement_path = root / "q1-zeta-requirement.json"
    requirement_raw = canonical_json_bytes(source_requirement)
    if requirement_path.exists():
        if requirement_path.read_bytes() != requirement_raw:
            raise DirichletCampaignError(
                "q=1 zeta campaign identity changed across resume"
            )
    else:
        atomic_write(requirement_path, requirement_raw)

    state = run_campaign(
        root, max_chunks=args.max_chunks, timeout=args.timeout
    )
    if not state["complete"]:
        _emit(
            {
                **state,
                "q1_zeta_requirement_verified": True,
                "source_composition_complete": False,
            },
            args.pretty,
        )
        raise DirichletCampaignError(
            "source campaign remains incomplete; resume with the same command"
        )
    # verify_campaign has already compared this retained document with the
    # replayed chain.  Load it without rewriting so tampering cannot be
    # silently repaired by the verifier.
    q2_final = load_canonical_json(root / "final.json")
    source_final = _source_document(q1, q2_final)
    source_path = root / "source-final.json"
    source_raw = canonical_json_bytes(source_final)
    if source_path.exists() and source_path.read_bytes() != source_raw:
        raise DirichletCampaignError("retained source-final.json differs from replay")
    atomic_write(source_path, source_raw)
    _emit(source_final, args.pretty)


def command_verify_source(args: argparse.Namespace) -> None:
    """Recheck both campaigns and the two files composing the source atom."""

    if args.registered_result_output is not None:
        require_azure_measured_worker_for_workload(
            exact_production=True,
            work_bounds=(),
        )
    root = args.root.resolve()
    q1 = _q1_zeta_requirement(args.q1_zeta_input.resolve())
    requirement_path = root / "q1-zeta-requirement.json"
    _validate_retained_source_requirement(requirement_path, q1)
    state = verify_campaign(root, require_complete=True)
    if (
        not state["complete"]
        or not state["final_present"]
        or state.get("mode") != "full_source"
        or state.get("q_start") != SOURCE_MIN_Q
        or state.get("q_stop") != SOURCE_MAX_Q
        or state.get("characters_total") != 29_565_923_837
        or state.get("characters_covered") != 29_565_923_837
    ):
        raise DirichletCampaignError("q=2..400000 campaign is not complete")
    if args.registered_result_output is not None:
        replay = rerun_external_checkers(root)
        if (
            replay.get("complete") is not True
            or replay.get("final_present") is not True
            or replay.get("fresh_checker_replay_performed") is not True
            or replay.get("fresh_external_checker_replays") != state.get(
                "chunks"
            )
        ):
            raise DirichletCampaignError(
                "registered Dirichlet output requires every retained checker "
                "to replay"
            )
    q2_final = finalize_campaign(root)
    expected = _source_document(q1, q2_final)
    source_path = root / "source-final.json"
    if source_path.read_bytes() != canonical_json_bytes(expected):
        raise DirichletCampaignError("source-final.json differs from fresh composition")
    if args.registered_result_output is not None:
        # This path is the legacy portfolio terminal: it emits no registered
        # result until q=1, every q>=2 checker, and the exact composition have
        # all been revalidated.
        _write_registered_result(args.registered_result_output)
    _emit(
        {
            **expected,
            "classification": "complete_source_composition_structurally_reverified",
            "q1_campaign_reverified": True,
            "q2_campaign_reverified": True,
            "fresh_flint_replay_performed": False,
        },
        args.pretty,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capability = subparsers.add_parser("capability")
    capability.set_defaults(func=command_capability)

    modulus = subparsers.add_parser("modulus")
    modulus.add_argument("q", type=_positive)
    modulus.set_defaults(func=command_modulus)

    describe = subparsers.add_parser("describe")
    describe.add_argument("--q", type=_positive, required=True)
    describe.add_argument("--ordinal", type=_nonnegative, required=True)
    describe.set_defaults(func=command_describe)

    schedule = subparsers.add_parser("schedule")
    schedule.add_argument("--q-start", type=_positive, default=SOURCE_MIN_Q)
    schedule.add_argument("--q-stop", type=_positive, default=SOURCE_MAX_Q)
    schedule.set_defaults(func=command_schedule)

    initialize = subparsers.add_parser("init")
    initialize.add_argument("root", type=Path)
    initialize.add_argument("--producer", type=Path, required=True)
    initialize.add_argument("--checker", type=Path, required=True)
    initialize.add_argument("--characters-per-chunk", type=_positive, default=1_000_000)
    initialize.add_argument(
        "--mode", choices=("full_source", "bounded_sample"), default="full_source"
    )
    initialize.add_argument("--q-start", type=_positive, default=SOURCE_MIN_Q)
    initialize.add_argument("--q-stop", type=_positive, default=SOURCE_MAX_Q)
    initialize.set_defaults(func=command_init)

    run = subparsers.add_parser("run")
    run.add_argument("root", type=Path)
    run.add_argument("--max-chunks", type=_positive)
    run.add_argument("--timeout", type=_positive)
    run.set_defaults(func=command_run)

    verify = subparsers.add_parser("verify")
    verify.add_argument("root", type=Path)
    verify.add_argument("--require-complete", action="store_true")
    verify.add_argument("--rerun-checker", action="store_true")
    verify.add_argument("--timeout", type=_positive)
    verify.set_defaults(func=command_verify)

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("root", type=Path)
    finalize.set_defaults(func=command_finalize)

    source = subparsers.add_parser(
        "source",
        help=(
            "from an empty workspace, compose the required q=1 zeta campaign "
            "with the full slow FLINT q=2..400000 campaign"
        ),
    )
    source.add_argument("root", type=Path)
    source.add_argument(
        "--q1-zeta-final",
        "--q1-zeta-campaign",
        dest="q1_zeta_input",
        type=Path,
        required=True,
        help=(
            "completed zeta-3e12 final.json (preferred), or its campaign "
            "directory for backwards compatibility"
        ),
    )
    source.add_argument("--characters-per-chunk", type=_positive, default=1)
    source.add_argument("--max-chunks", type=_positive)
    source.add_argument("--timeout", type=_positive)
    source.add_argument("--reference-max-precision", type=_positive, default=16_384)
    source.add_argument(
        "--reference-max-contour-depth", type=_positive, default=96
    )
    source.add_argument(
        "--reference-max-contour-evaluations", type=_nonnegative, default=0
    )
    source.add_argument(
        "--reference-max-grid-refinements", type=_nonnegative, default=24
    )
    source.set_defaults(func=command_source)

    verify_source = subparsers.add_parser(
        "verify-source",
        help="recheck q=1, q>=2, and the exact retained source composition",
    )
    verify_source.add_argument("root", type=Path)
    verify_source.add_argument(
        "--q1-zeta-final",
        "--q1-zeta-campaign",
        dest="q1_zeta_input",
        type=Path,
        required=True,
    )
    verify_source.add_argument(
        "--registered-result-output",
        type=Path,
        help=(
            "exclusively create literal `true` after complete q=1/q>=2 "
            "source replay"
        ),
    )
    verify_source.set_defaults(func=command_verify_source)

    args = parser.parse_args()
    try:
        args.func(args)
    except (DirichletCampaignError, MeasuredWorkerScopeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2 if isinstance(error, MeasuredWorkerScopeError) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
