#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Measured operational adapter for the one-pass Hurst affine campaign.

All four phases return operational JSON.  Even the final replay remains a
conditional certificate audit: this adapter never emits the registered
Boolean result and never claims physical row realization or a Lean theorem.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "attestation", ROOT / "tools"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from measured_run_archive import ArchiveError, create_archive  # noqa: E402
from tg_hurst_azure_measured_workload import (  # noqa: E402
    GROUP_LOCAL_WORKERS,
    GROUP_RUNNER_THREADS,
    OPERATIONAL_RESULT_KIND,
    TRACE_FIELDS,
    TRACE_ITERATIONS,
    HurstMeasuredWorkloadError,
    _copy_file,
    _entry_archive,
    _extract_export,
    _file_identity,
    _handoff,
    _operational_result,
    _restore_campaign,
    _safe_relative,
    _trace_hash,
    _validate_operational_result,
    _write_exclusive,
    _write_export_manifest,
    _write_trace,
)
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
    require_azure_measured_worker,
)
from tg_verifier.hurst_affine_campaign import (  # noqa: E402
    CONFIG_NAME,
    FINAL_NAME,
    RECEIPT_DIRECTORY,
    finalize_campaign,
    grouped_shard_indices,
    initialize_campaign,
    run_shards,
    verify_campaign,
    verify_campaign_readonly,
)


PHASES = (
    "initialize-affine",
    "affine-shards",
    "finalize-affine-certificate",
    "replay-affine-certificate",
)
CAMPAIGN_ID = "hurst-four-residuals-affine-onepass-v1"
GROUP_COUNT = 320
LEAF_COUNT = 10_000


def _expected_group(phase: str) -> str:
    return f"{CAMPAIGN_ID}::{phase}"


def _expected_handoff_keys(phase: str) -> set[tuple[str, int]]:
    if phase == "initialize-affine":
        return set()
    if phase == "affine-shards":
        return {(_expected_group("initialize-affine"), 0)}
    if phase == "finalize-affine-certificate":
        return {
            (_expected_group("affine-shards"), index)
            for index in range(GROUP_COUNT)
        }
    return {(_expected_group("finalize-affine-certificate"), 0)}


def _validate_handoff_shape(
    handoff: Mapping[str, Any], phase: str
) -> None:
    actual = {
        (entry["group_id"], entry["shard_index"])
        for entry in handoff["entries"]
    }
    expected = _expected_handoff_keys(phase)
    if actual != expected or len(handoff["entries"]) != len(expected):
        raise HurstMeasuredWorkloadError(
            "affine phase handoff does not exactly cover reviewed predecessors"
        )


def _campaign_identity(
    campaign: Path, identity: Mapping[str, Any]
) -> None:
    checked = verify_campaign_readonly(campaign)
    config = load_json(campaign / CONFIG_NAME, require_canonical=True)
    if (
        checked.runner_sha256 != identity["runner_sha256"]
        or checked.source_sha256 != identity["source_sha256"]
        or not isinstance(config, dict)
        or config.get("upstream_manifest_sha256")
        != identity["upstream_manifest_sha256"]
        or config.get("captured_runner_size") != identity["runner_size_bytes"]
        or config.get("captured_source_size") != identity["source_size_bytes"]
    ):
        raise HurstMeasuredWorkloadError(
            "retained affine campaign differs from measured source identities"
        )


def _initialize(args: argparse.Namespace, campaign: Path) -> None:
    result = initialize_campaign(
        runner=args.runner,
        runner_source=args.runner_source,
        upstream_manifest=args.upstream_manifest,
        output_directory=campaign,
    )
    if (
        result.mode != "full_source"
        or result.shard_count != LEAF_COUNT
        or result.affine_receipts != 0
        or result.complete
    ):
        raise HurstMeasuredWorkloadError(
            "affine initialization did not create the literal fresh source plan"
        )


def _single_predecessor(
    handoff: Mapping[str, Any],
    handoff_root: Path,
    *,
    source_phase: str,
    identity: Mapping[str, Any],
) -> Path:
    entries = handoff["entries"]
    if (
        len(entries) != 1
        or entries[0]["group_id"] != _expected_group(source_phase)
        or entries[0]["shard_index"] != 0
    ):
        raise HurstMeasuredWorkloadError(
            "affine phase has the wrong single predecessor"
        )
    extracted = handoff_root / f"expanded-{source_phase}"
    _extract_export(
        _entry_archive(handoff_root, entries[0]),
        extracted,
        source_phase,
        0,
        identity,
    )
    return extracted


def _export_subset(
    campaign: Path, export: Path, group_index: int
) -> None:
    destination = export / "payload" / RECEIPT_DIRECTORY
    destination.mkdir(mode=0o700, parents=True)
    for leaf in grouped_shard_indices(
        campaign, group_index=group_index, group_count=GROUP_COUNT
    ):
        source = (
            campaign
            / RECEIPT_DIRECTORY
            / f"receipt-{leaf:08d}.json"
        )
        _copy_file(source, destination / source.name)


def _import_leaf_exports(
    handoff: Mapping[str, Any],
    handoff_root: Path,
    campaign: Path,
    identity: Mapping[str, Any],
) -> None:
    destination = campaign / RECEIPT_DIRECTORY
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    for entry in sorted(
        handoff["entries"], key=lambda row: row["shard_index"]
    ):
        index = entry["shard_index"]
        extracted = handoff_root / f"expanded-affine-{index:03d}"
        _extract_export(
            _entry_archive(handoff_root, entry),
            extracted,
            "affine-shards",
            index,
            identity,
        )
        source = extracted / "payload" / RECEIPT_DIRECTORY
        wanted = {
            f"receipt-{leaf:08d}.json"
            for leaf in range(index, LEAF_COUNT, GROUP_COUNT)
        }
        files = (
            {path.name for path in source.iterdir() if path.is_file()}
            if source.is_dir()
            else set()
        )
        if files != wanted:
            raise HurstMeasuredWorkloadError(
                "affine leaf export differs from its exact strided group"
            )
        for name in sorted(files):
            _copy_file(source / name, destination / name)
        shutil.rmtree(extracted)


def _verify_complete_conditional_campaign(
    campaign: Path, *, readonly: bool = False
) -> None:
    result = (
        verify_campaign_readonly(campaign)
        if readonly
        else verify_campaign(campaign)
    )
    if (
        not result.complete
        or not result.full_source_range
        or result.affine_receipts != LEAF_COUNT
        or not result.all_root_derived_inputs_in_all_atom_guards
        or result.source_rows_replayed_independently
        or not result.physical_row_realization_pending
        or result.execution_attested
        or result.lean_atoms_discharged
        or not (campaign / FINAL_NAME).is_file()
    ):
        raise HurstMeasuredWorkloadError(
            "affine campaign replay crossed or failed its conditional boundary"
        )


def run(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    input_sha256, _ = hash_file_once(args.input)
    identity = _file_identity(args)
    handoff, handoff_root = _handoff(
        args.handoff, args.phase, args.group_index, identity
    )
    _validate_handoff_shape(handoff, args.phase)
    if args.work.exists():
        raise HurstMeasuredWorkloadError(
            "Hurst affine work directory must be fresh"
        )
    args.work.mkdir(mode=0o700, parents=True)
    campaign = args.work / "campaign"
    export = args.work / "export"
    export.mkdir(mode=0o700)
    succeeded = False
    try:
        if args.phase in (
            "initialize-affine",
            "finalize-affine-certificate",
        ):
            _initialize(args, campaign)

        if args.phase == "initialize-affine":
            if handoff["entries"]:
                raise HurstMeasuredWorkloadError(
                    "affine initialization takes no predecessor"
                )
            _campaign_identity(campaign, identity)
            shutil.copytree(campaign, export / "campaign")
        elif args.phase == "affine-shards":
            predecessor = _single_predecessor(
                handoff,
                handoff_root,
                source_phase="initialize-affine",
                identity=identity,
            )
            _restore_campaign(predecessor, campaign)
            _campaign_identity(campaign, identity)
            run_shards(
                campaign,
                shard_indices=grouped_shard_indices(
                    campaign,
                    group_index=args.group_index,
                    group_count=GROUP_COUNT,
                ),
                workers=GROUP_LOCAL_WORKERS,
                runner_threads=GROUP_RUNNER_THREADS,
            )
            _campaign_identity(campaign, identity)
            _export_subset(campaign, export, args.group_index)
        elif args.phase == "finalize-affine-certificate":
            _import_leaf_exports(
                handoff, handoff_root, campaign, identity
            )
            result = finalize_campaign(campaign)
            if (
                not result.complete
                or not result.full_source_range
                or result.affine_receipts != LEAF_COUNT
            ):
                raise HurstMeasuredWorkloadError(
                    "affine finalizer did not close exact source coverage"
                )
            _verify_complete_conditional_campaign(campaign)
            _campaign_identity(campaign, identity)
            shutil.copytree(campaign, export / "campaign")
        elif args.phase == "replay-affine-certificate":
            predecessor = _single_predecessor(
                handoff,
                handoff_root,
                source_phase="finalize-affine-certificate",
                identity=identity,
            )
            _restore_campaign(predecessor, campaign)
            _campaign_identity(campaign, identity)
            _verify_complete_conditional_campaign(campaign)
            shutil.copytree(campaign, export / "campaign")
        else:  # pragma: no cover
            raise HurstMeasuredWorkloadError("unsupported affine phase")

        retained_manifest = _write_export_manifest(
            export, args.phase, args.group_index, identity
        )
        retained_archive = args.work / "retained-export.tar"
        create_archive(export, retained_archive)
        retained_sha256, retained_size = hash_file_once(retained_archive)
        _write_exclusive(
            args.output,
            canonical_json_bytes(
                _operational_result(
                    args,
                    identity,
                    retained_sha256,
                    retained_size,
                    retained_manifest["tree_sha256"],
                )
            ),
        )
        result_sha256, _ = hash_file_once(args.output)
        _write_trace(
            args,
            input_sha256=input_sha256,
            identity=identity,
            retained_sha256=retained_sha256,
            retained_tree_sha256=retained_manifest["tree_sha256"],
            result_sha256=result_sha256,
            candidate=None,
        )
        succeeded = True
    finally:
        shutil.rmtree(handoff_root, ignore_errors=True)
        shutil.rmtree(campaign, ignore_errors=True)
        shutil.rmtree(export, ignore_errors=True)
        if not succeeded:
            shutil.rmtree(args.work, ignore_errors=True)


def _copy_subset_into_campaign(
    retained: Path,
    campaign: Path,
    *,
    group_index: int,
) -> None:
    source = retained / "payload" / RECEIPT_DIRECTORY
    wanted = {
        f"receipt-{leaf:08d}.json"
        for leaf in range(group_index, LEAF_COUNT, GROUP_COUNT)
    }
    files = (
        {path.name for path in source.iterdir() if path.is_file()}
        if source.is_dir()
        else set()
    )
    if files != wanted:
        raise HurstMeasuredWorkloadError(
            "replayed affine export has the wrong exact leaf set"
        )
    destination = campaign / RECEIPT_DIRECTORY
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in sorted(files):
        _copy_file(source / name, destination / name)


def verify_trace(args: argparse.Namespace) -> None:
    require_azure_measured_worker(
        challenge_nonce=args.challenge,
        job_binding=args.job_binding,
    )
    input_sha256, _ = hash_file_once(args.input)
    result_sha256, _ = hash_file_once(args.output)
    identity = _file_identity(args)
    temporary = Path(
        tempfile.mkdtemp(prefix=".hurst-affine-trace-", dir=args.trace.parent)
    )
    handoff_root: Path | None = None
    try:
        handoff, handoff_root = _handoff(
            args.handoff, args.phase, args.group_index, identity
        )
        _validate_handoff_shape(handoff, args.phase)
        result = _validate_operational_result(
            load_json(args.output, require_canonical=True),
            args,
            identity,
        )
        retained_archive = args.work / "retained-export.tar"
        if hash_file_once(retained_archive) != (
            result["retained_export_sha256"],
            result["retained_export_size_bytes"],
        ):
            raise HurstMeasuredWorkloadError(
                "affine retained export differs from result pin"
            )
        retained = temporary / "retained"
        manifest = _extract_export(
            retained_archive,
            retained,
            args.phase,
            args.group_index,
            identity,
        )
        if manifest["tree_sha256"] != result["retained_tree_sha256"]:
            raise HurstMeasuredWorkloadError(
                "affine retained tree differs from result pin"
            )

        if args.phase == "initialize-affine":
            _campaign_identity(retained / "campaign", identity)
            checked = verify_campaign_readonly(retained / "campaign")
            if checked.affine_receipts != 0 or checked.complete:
                raise HurstMeasuredWorkloadError(
                    "affine initialization export is not fresh"
                )
        elif args.phase == "affine-shards":
            predecessor = _single_predecessor(
                handoff,
                handoff_root,
                source_phase="initialize-affine",
                identity=identity,
            )
            campaign = temporary / "campaign"
            _restore_campaign(predecessor, campaign)
            _copy_subset_into_campaign(
                retained, campaign, group_index=args.group_index
            )
            checked = verify_campaign_readonly(campaign)
            expected_count = len(
                range(args.group_index, LEAF_COUNT, GROUP_COUNT)
            )
            if checked.affine_receipts != expected_count or checked.complete:
                raise HurstMeasuredWorkloadError(
                    "affine shard export failed independent receipt replay"
                )
        else:
            _verify_complete_conditional_campaign(
                retained / "campaign", readonly=True
            )
            _campaign_identity(retained / "campaign", identity)

        retained_sha256, _ = hash_file_once(retained_archive)
        expected = {
            "algorithm_id": args.algorithm_id,
            "challenge_nonce": args.challenge,
            "input_sha256": input_sha256,
            "iteration_count": TRACE_ITERATIONS,
            "job_binding_sha256": args.job_binding,
            "kind": "sparkinterval_challenge_work_trace",
            "result_sha256": result_sha256,
            "schema_version": 1,
            "trace_sha256": _trace_hash(
                phase=args.phase,
                group_index=args.group_index,
                challenge=args.challenge,
                job_binding=args.job_binding,
                input_sha256=input_sha256,
                identity=identity,
                retained_sha256=retained_sha256,
                retained_tree_sha256=manifest["tree_sha256"],
                result_sha256=result_sha256,
                candidate=None,
            ),
        }
        actual = load_json(args.trace, require_canonical=True)
        if set(expected) != TRACE_FIELDS or actual != expected:
            raise HurstMeasuredWorkloadError(
                "Hurst affine challenge work trace differs"
            )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
        if handoff_root is not None:
            shutil.rmtree(handoff_root, ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("mode", choices=("run", "verify-trace"))
    result.add_argument("--phase", choices=PHASES, required=True)
    result.add_argument("--group-index", type=int, required=True)
    result.add_argument("--algorithm-id", required=True)
    result.add_argument("--challenge", required=True)
    result.add_argument("--job-binding", required=True)
    result.add_argument("--input", type=Path, required=True)
    result.add_argument("--handoff", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--trace", type=Path, required=True)
    result.add_argument("--work", type=Path, required=True)
    result.add_argument("--runner", type=Path, required=True)
    result.add_argument("--runner-source", type=Path, required=True)
    result.add_argument("--upstream-manifest", type=Path, required=True)
    return result


def _validate_args(args: argparse.Namespace) -> None:
    from tg_hurst_azure_measured_workload import _hex

    _hex(args.challenge, "challenge")
    _hex(args.job_binding, "job binding")
    _hex(args.algorithm_id.rsplit(".", 1)[-1], "algorithm instance suffix")
    for name in (
        "input",
        "handoff",
        "output",
        "trace",
        "work",
        "runner",
        "runner_source",
        "upstream_manifest",
    ):
        value = getattr(args, name)
        setattr(args, name, _safe_relative(value.as_posix(), name))
    if args.phase == "affine-shards":
        if not 0 <= args.group_index < GROUP_COUNT:
            raise HurstMeasuredWorkloadError(
                "affine worker group index must be in [0,320)"
            )
    elif args.group_index != 0:
        raise HurstMeasuredWorkloadError(
            "single-job affine phase requires group index zero"
        )


def main() -> int:
    args = parser().parse_args()
    try:
        require_azure_measured_worker(
            challenge_nonce=args.challenge,
            job_binding=args.job_binding,
        )
        _validate_args(args)
        if args.mode == "run":
            run(args)
        else:
            verify_trace(args)
    except (
        HurstMeasuredWorkloadError,
        ArchiveError,
        CampaignIOError,
        OSError,
        ValueError,
    ) as error:
        print(f"Hurst affine measured workload error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
