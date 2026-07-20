#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan and inspect the thirteen ternary-Goldbach external campaigns.

This control plane is deliberately fail closed.  Capability is not completed
coverage; a successful process exit is not semantic verification; and no JSON
record produced here discharges a Lean atom.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tg_verifier.campaign import (  # noqa: E402
    CampaignError,
    CampaignProfile,
    CampaignRegistry,
    STATUS_KIND,
    capability_record,
    create_plan,
    doctor_profile,
    load_registry,
    parse_input_bindings,
    validate_plan,
    verify_plan_inputs,
    verify_workspace,
    workspace_status,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    advisory_lock,
    atomic_write_bytes,
    atomic_write_json,
    canonical_sha256,
    hash_file_once,
    load_json,
    write_immutable_json,
)


def _emit(value: Any, *, pretty: bool) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
    )


def _profiles(
    registry: CampaignRegistry, atom_id: str | None
) -> tuple[CampaignProfile, ...]:
    if atom_id is None:
        return registry.profiles
    try:
        return (registry.by_id[atom_id],)
    except KeyError as exc:
        raise CampaignError(f"unknown atom id: {atom_id}") from exc


def command_capability(args: argparse.Namespace, registry: CampaignRegistry) -> int:
    profiles = _profiles(registry, args.atom)
    records = [capability_record(profile) for profile in profiles]
    _emit(
        {
            "schema_version": 1,
            "classification": "implementation_capability_not_completed_evidence",
            "registry_sha256": registry.registry_sha256,
            "source_catalog_sha256": registry.source_catalog_sha256,
            "profile_count": len(records),
            "profiles": records,
            "full_source_campaigns_completed": 0,
            "lean_atoms_discharged": 0,
        },
        pretty=args.pretty,
    )
    return 0


def _bindings_for_profile(
    profile: CampaignProfile, bindings: Mapping[str, Path]
) -> dict[str, Path]:
    ids = {item.input_id for item in profile.required_inputs}
    return {name: path for name, path in bindings.items() if name in ids}


def command_doctor(args: argparse.Namespace, registry: CampaignRegistry) -> int:
    bindings = parse_input_bindings(args.input)
    profiles = _profiles(registry, args.atom)
    all_known = {
        item.input_id for profile in profiles for item in profile.required_inputs
    }
    unknown = sorted(set(bindings) - all_known)
    if unknown:
        raise CampaignError(f"input bindings are unused by selected profiles: {unknown}")
    results = [
        doctor_profile(profile, _bindings_for_profile(profile, bindings))
        for profile in profiles
    ]
    ready = sum(bool(result["ready_for_full_campaign"]) for result in results)
    _emit(
        {
            "schema_version": 1,
            "classification": "local_prerequisite_probe_not_campaign_execution",
            "registry_sha256": registry.registry_sha256,
            "profile_count": len(results),
            "ready_for_full_campaign_count": ready,
            "results": results,
            "full_source_campaigns_completed": 0,
            "lean_atoms_discharged": 0,
        },
        pretty=args.pretty,
    )
    if args.require_ready and ready != len(results):
        return 2
    return 0


def command_plan(args: argparse.Namespace, registry: CampaignRegistry) -> int:
    profile = registry.by_id[args.atom]
    bindings = parse_input_bindings(args.input)
    workspace = args.workspace.resolve()
    plan = create_plan(
        registry,
        profile,
        bindings,
        engine_id=args.engine,
        workspace=workspace,
    )
    digest = canonical_sha256(plan)
    wrote = False
    if args.write:
        workspace.mkdir(parents=True, exist_ok=True)
        write_immutable_json(workspace / "plan.json", plan)
        wrote = True
    _emit(
        {
            "schema_version": 1,
            "classification": "immutable_full_source_plan_not_execution",
            "plan_sha256": digest,
            "plan_written": wrote,
            "plan_path": str(workspace / "plan.json") if wrote else None,
            "plan": plan,
        },
        pretty=args.pretty,
    )
    return 0


def command_status(args: argparse.Namespace, registry: CampaignRegistry) -> int:
    _emit(workspace_status(args.workspace, registry), pretty=args.pretty)
    return 0


def command_verify(args: argparse.Namespace, registry: CampaignRegistry) -> int:
    _emit(verify_workspace(args.workspace, registry), pretty=args.pretty)
    return 0


def _initial_status(
    plan: dict[str, Any], profile: CampaignProfile, plan_hash: str, state: str
) -> dict[str, Any]:
    domain = profile.full_source_domain
    return {
        "schema_version": 1,
        "kind": STATUS_KIND,
        "atom_id": profile.atom_id,
        "profile_sha256": profile.profile_sha256,
        "plan_sha256": plan_hash,
        "state": state,
        "scope": "full_source",
        "sample": False,
        "covered_lower": domain["lower"],
        "covered_upper": domain["lower"],
        "covered_work_items": 0,
        "artifacts": [],
        "semantic_verification": "not_run",
        "full_source_campaign": False,
        "lean_atom_discharged": False,
    }


def _artifact(path: Path, workspace: Path, role: str) -> dict[str, Any]:
    digest, size = hash_file_once(path)
    return {
        "path": path.relative_to(workspace).as_posix(),
        "sha256": digest,
        "size_bytes": size,
        "role": role,
    }


def _run_plan(
    args: argparse.Namespace,
    registry: CampaignRegistry,
    *,
    resume: bool,
) -> int:
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    lock_path = workspace / ".campaign.lock"
    with advisory_lock(lock_path):
        plan = load_json(workspace / "plan.json", require_canonical=True)
        plan, profile, engine = validate_plan(plan, registry, workspace=workspace)
        verify_plan_inputs(plan)
        plan_hash = canonical_sha256(plan)
        status_path = workspace / "status.json"
        prior = workspace_status(workspace, registry)
        if prior["state"] == "invalid":
            raise CampaignError(f"cannot execute invalid workspace: {prior['error']}")
        if resume:
            if not engine.supports_resume:
                raise CampaignError(
                    f"engine {engine.engine_id} has no honest resume adapter"
                )
            if prior["state"] not in {"running", "paused", "failed"}:
                raise CampaignError(
                    "resume requires an interrupted, paused, or failed status"
                )
        elif prior["state"] != "planned":
            raise CampaignError(
                "run requires a new immutable plan with no existing status"
            )
        atomic_write_json(
            status_path, _initial_status(plan, profile, plan_hash, "running")
        )
        completed = subprocess.run(
            plan["invocation"],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
        )
        stdout_path = workspace / "engine.stdout"
        stderr_path = workspace / "engine.stderr"
        atomic_write_bytes(stdout_path, completed.stdout)
        atomic_write_bytes(stderr_path, completed.stderr)
        artifacts = [
            _artifact(stdout_path, workspace, "engine_stdout"),
            _artifact(stderr_path, workspace, "engine_stderr"),
        ]
        transcript = workspace / "transcript.txt"
        if transcript.is_file():
            artifacts.append(_artifact(transcript, workspace, "producer_transcript"))
        status = _initial_status(
            plan,
            profile,
            plan_hash,
            "execution_complete" if completed.returncode == 0 else "failed",
        )
        status["artifacts"] = artifacts
        atomic_write_json(status_path, status)
    _emit(
        {
            "schema_version": 1,
            "classification": "engine_execution_not_semantic_verification",
            "accepted": completed.returncode == 0,
            "atom_id": profile.atom_id,
            "engine_id": engine.engine_id,
            "exit_code": completed.returncode,
            "status_path": str(status_path),
            "semantic_verification": "not_run",
            "full_source_campaign": False,
            "lean_atom_discharged": False,
        },
        pretty=args.pretty,
    )
    return 0 if completed.returncode == 0 else 2


def command_run(args: argparse.Namespace, registry: CampaignRegistry) -> int:
    return _run_plan(args, registry, resume=False)


def command_resume(args: argparse.Namespace, registry: CampaignRegistry) -> int:
    return _run_plan(args, registry, resume=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    parser.add_argument(
        "--profiles",
        type=Path,
        help="alternate strict campaign-profile registry (mainly for audits/tests)",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    capability = subcommands.add_parser(
        "capability", help="report implementation capability for exactly 13 atoms"
    )
    capability.add_argument("--atom")
    capability.set_defaults(handler=command_capability)

    doctor = subcommands.add_parser(
        "doctor", help="probe required local inputs without running a campaign"
    )
    doctor.add_argument("--atom")
    doctor.add_argument("--input", action="append", default=[], metavar="NAME=PATH")
    doctor.add_argument("--require-ready", action="store_true")
    doctor.set_defaults(handler=command_doctor)

    plan = subcommands.add_parser(
        "plan", help="construct a hash-bound full-source plan; samples are rejected"
    )
    plan.add_argument("atom")
    plan.add_argument("--workspace", required=True, type=Path)
    plan.add_argument("--engine")
    plan.add_argument("--input", action="append", default=[], metavar="NAME=PATH")
    plan.add_argument(
        "--write", action="store_true", help="write immutable canonical plan.json"
    )
    plan.set_defaults(handler=command_plan)

    status = subcommands.add_parser(
        "status", help="inspect a workspace without trusting self-reported completion"
    )
    status.add_argument("workspace", type=Path)
    status.set_defaults(handler=command_status)

    verify = subcommands.add_parser(
        "verify", help="verify plan/status/artifact integrity (not theorem semantics)"
    )
    verify.add_argument("workspace", type=Path)
    verify.set_defaults(handler=command_verify)

    run = subcommands.add_parser(
        "run", help="execute a ready full-source plan without claiming verification"
    )
    run.add_argument("workspace", type=Path)
    run.set_defaults(handler=command_run)

    resume = subcommands.add_parser(
        "resume", help="resume only an engine that explicitly supports exact resume"
    )
    resume.add_argument("workspace", type=Path)
    resume.set_defaults(handler=command_resume)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        registry = load_registry(args.profiles) if args.profiles else load_registry()
        return int(args.handler(args, registry))
    except (
        CampaignError,
        CampaignIOError,
        KeyError,
        OSError,
        subprocess.SubprocessError,
        ValueError,
    ) as exc:
        _emit(
            {
                "schema_version": 1,
                "accepted": False,
                "error": str(exc),
                "full_source_campaign": False,
                "lean_atom_discharged": False,
            },
            pretty=getattr(args, "pretty", False),
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
