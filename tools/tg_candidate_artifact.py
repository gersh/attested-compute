#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Convert or inspect fail-closed Prop1224 and Hurst Lean candidate artifacts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.azure_cpu_prop1224_workload_factory import PLAN  # noqa: E402
from tg_verifier.campaign_io import (  # noqa: E402
    CampaignIOError,
    canonical_json_bytes,
    parse_json_bytes,
)
from tg_verifier.hurst_candidate_artifact import (  # noqa: E402
    HurstCandidateArtifactError,
    arithmetic_check as hurst_arithmetic_check,
    candidate_from_replayed_campaign,
    candidate_manifest as hurst_manifest,
    decode_candidate as decode_hurst,
    encode_candidate as encode_hurst,
    require_semantic_realization as require_hurst_realization,
)
from tg_verifier.prop1224_candidate_artifact import (  # noqa: E402
    Prop1224CandidateArtifactError,
    arithmetic_check as prop1224_arithmetic_check,
    candidate_from_verified_report,
    candidate_manifest as prop1224_manifest,
    decode_candidate as decode_prop1224,
    encode_candidate as encode_prop1224,
    require_semantic_realization as require_prop1224_realization,
)


MAX_ARTIFACT_BYTES = 8 * 1024**2
MAX_REPORT_BYTES = 2 * 1024**2


class CandidateArtifactCLIError(RuntimeError):
    """A conversion would overwrite data or cross the missing semantic edge."""


def _read(path: Path, maximum: int) -> bytes:
    try:
        metadata = path.stat()
    except OSError as error:
        raise CandidateArtifactCLIError(f"cannot stat {path}: {error}") from error
    if not path.is_file() or path.is_symlink() or metadata.st_size > maximum:
        raise CandidateArtifactCLIError(f"{path} is not a bounded regular file")
    try:
        return path.read_bytes()
    except OSError as error:
        raise CandidateArtifactCLIError(f"cannot read {path}: {error}") from error


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o400)
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise CandidateArtifactCLIError(f"short write: {path}")
            view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)


def _emit(
    output: Path,
    manifest_output: Path,
    raw: bytes,
    manifest: dict[str, object],
) -> dict[str, object]:
    _write_exclusive(output, raw)
    try:
        _write_exclusive(manifest_output, canonical_json_bytes(manifest))
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return {
        "artifact": manifest["artifact"],
        "classification": "candidate-only-no-semantic-closure",
        "manifest": str(manifest_output),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    prop = commands.add_parser(
        "prop1224-from-replayed-report",
        help="convert an exact terminal merge report to the arithmetic candidate",
    )
    prop.add_argument("report", type=Path)
    prop.add_argument("output", type=Path)
    prop.add_argument("--manifest", type=Path, required=True)
    hurst = commands.add_parser(
        "hurst-from-replayed-campaign",
        help="replay a full campaign and convert its affine arithmetic chain",
    )
    hurst.add_argument("campaign", type=Path)
    hurst.add_argument("output", type=Path)
    hurst.add_argument("--manifest", type=Path, required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("kind", choices=("prop1224", "hurst"))
    inspect.add_argument("artifact", type=Path)
    promote = commands.add_parser(
        "require-semantic-realization",
        help="fail closed and list data absent from the candidate wire",
    )
    promote.add_argument("kind", choices=("prop1224", "hurst"))
    promote.add_argument("artifact", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "prop1224-from-replayed-report":
            report_raw = _read(args.report, MAX_REPORT_BYTES)
            report = parse_json_bytes(report_raw, label="terminal replay report")
            if canonical_json_bytes(report) != report_raw:
                raise CandidateArtifactCLIError(
                    "terminal replay report is not canonical JSON"
                )
            if not isinstance(report, dict):
                raise CandidateArtifactCLIError("terminal report must be an object")
            raw = encode_prop1224(
                candidate_from_verified_report(report, plan=PLAN)
            )
            result = _emit(
                args.output,
                args.manifest,
                raw,
                prop1224_manifest(args.output.name, raw),
            )
        elif args.command == "hurst-from-replayed-campaign":
            raw = encode_hurst(candidate_from_replayed_campaign(args.campaign))
            result = _emit(
                args.output,
                args.manifest,
                raw,
                hurst_manifest(args.output.name, raw),
            )
        elif args.command == "inspect":
            raw = _read(args.artifact, MAX_ARTIFACT_BYTES)
            if args.kind == "prop1224":
                certificate = decode_prop1224(raw)
                valid = prop1224_arithmetic_check(certificate)
                result = prop1224_manifest(args.artifact.name, raw)
            else:
                certificate = decode_hurst(raw)
                valid = hurst_arithmetic_check(certificate)
                result = hurst_manifest(args.artifact.name, raw)
            result["arithmetic_check"] = valid
        else:
            raw = _read(args.artifact, MAX_ARTIFACT_BYTES)
            if args.kind == "prop1224":
                decode_prop1224(raw)
                require_prop1224_realization(raw)
            else:
                decode_hurst(raw)
                require_hurst_realization(raw)
            raise AssertionError("semantic realization unexpectedly succeeded")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (
        CampaignIOError,
        CandidateArtifactCLIError,
        HurstCandidateArtifactError,
        OSError,
        Prop1224CandidateArtifactError,
        ValueError,
    ) as error:
        print(f"candidate artifact error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
