#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Known-answer execution tests for the CUDA Moebius segment primitive."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.mobius_cuda import (
    MobiusReceiptError,
    _canonical_transition,
    verify_mobius_receipt,
    verify_mobius_receipt_chain,
)
from tg_verifier.mobius_campaign import run_campaign, verify_campaign


KNOWN_ROOTS = (
    (
        512,
        "0410b64cd55f5a6024b9e420e3920d9d1db944eed5c9b1dc97ebdbe5f715fb34",
        -4,
        314,
        -361587818340506630717555022,
        -361587818340506630717554710,
    ),
    (
        10_000,
        "1538f71e023af5bcea4384ea794a5cfb48e91225f3f25a03eeb203d01a8b0a6b",
        -23,
        6_083,
        -165008475646504406525207558,
        -165008475646504406525201477,
    ),
    (
        450_000,
        "01046da44b889a90c3a68efc4f2b6c942f7add7be44a8d011be6a065011f0362",
        52,
        273_558,
        9485891078195955203117526,
        9485891078195955203391082,
    ),
)


def run(command: list[str], *, success: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if success and result.returncode != 0:
        raise AssertionError(
            f"{command!r} returned {result.returncode}: {result.stderr!r}"
        )
    return result


def execute(runner: Path, *arguments: str) -> dict[str, object]:
    result = run([str(runner), *arguments, "--allow-other-device"])
    report = json.loads(result.stdout)
    verify_mobius_receipt(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", type=Path, required=True)
    args = parser.parse_args()
    if not args.runner.is_file():
        raise AssertionError(f"missing CUDA Moebius runner: {args.runner}")

    help_result = run([str(args.runner), "--help"])
    if "hash-linked state transition" not in help_result.stdout:
        raise AssertionError("runner help omits its bounded transition scope")
    malformed = run([str(args.runner), "--count", "0"], success=False)
    if malformed.returncode != 2 or "--count must lie" not in malformed.stderr:
        raise AssertionError("runner did not reject a zero-length range")
    nonroot = run([str(args.runner), "--lower", "2", "--count", "1"], success=False)
    if nonroot.returncode != 2 or "non-root segment requires" not in nonroot.stderr:
        raise AssertionError("runner accepted an unauthenticated non-root state")

    for count, digest, mertens, squarefree, little_lower, little_upper in KNOWN_ROOTS:
        report = execute(args.runner, "--lower", "1", "--count", str(count))
        expected = {
            "lower": 1,
            "upper": count,
            "record_count": count,
            "gpu_record_sha256_le_v1": digest,
            "cpu_record_sha256_le_v1": digest,
            "outgoing_mertens": mertens,
            "outgoing_squarefree": squarefree,
            "outgoing_little_mertens_lower": little_lower,
            "outgoing_little_mertens_upper": little_upper,
            "hurst_first_failure": None,
            "cdem_b1_first_not_proved_safe": None,
            "cdem_b2_first_not_proved_safe": None,
            "proves_mertens_hurst_external_atom": False,
            "proves_cdem_squarefree_external_atom": False,
            "proves_any_external_atom": False,
        }
        for name, value in expected.items():
            if report.get(name) != value:
                raise AssertionError(
                    f"root count {count}, field {name}: "
                    f"expected {value!r}, got {report.get(name)!r}"
                )

    first = execute(args.runner, "--lower", "1", "--count", "999")
    second = execute(
        args.runner,
        "--lower",
        "1000",
        "--count",
        "1001",
        "--incoming-mertens",
        str(first["outgoing_mertens"]),
        "--incoming-squarefree",
        str(first["outgoing_squarefree"]),
        "--incoming-little-mertens-lower",
        str(first["outgoing_little_mertens_lower"]),
        "--incoming-little-mertens-upper",
        str(first["outgoing_little_mertens_upper"]),
        "--previous-receipt-sha256",
        str(first["receipt_chain_sha256"]),
    )
    chain = verify_mobius_receipt_chain([first, second])
    if (chain.upper, chain.final_mertens, chain.final_squarefree) != (2000, 5, 1215):
        raise AssertionError(f"unexpected composed transition: {chain}")
    if chain.execution_authenticated or chain.rows_replayed_by_chain_checker:
        raise AssertionError("structural receipt composition overclaimed execution")
    if (
        chain.final_little_mertens_lower
        != 263002278022946840516464743
        or chain.final_little_mertens_upper
        != 263002278022946840516465956
    ):
        raise AssertionError(f"unexpected composed little-Mertens state: {chain}")
    tampered = dict(second)
    tampered["outgoing_mertens"] = int(second["outgoing_mertens"]) + 1
    try:
        verify_mobius_receipt_chain([first, tampered])
    except MobiusReceiptError:
        pass
    else:
        raise AssertionError("chain checker accepted a tampered outgoing state")

    changed_executable = dict(second)
    changed_executable["executable_sha256"] = "b" * 64
    changed_executable["receipt_chain_sha256"] = hashlib.sha256(
        _canonical_transition(changed_executable)
    ).hexdigest()
    try:
        verify_mobius_receipt_chain([first, changed_executable])
    except MobiusReceiptError:
        pass
    else:
        raise AssertionError("chain checker accepted a changed executable identity")

    for digest_field in (
        "gpu_record_sha256_le_v1",
        "cpu_record_sha256_le_v1",
        "executable_sha256",
    ):
        zero_digest = dict(first)
        zero_digest[digest_field] = "0" * 64
        if digest_field in (
            "gpu_record_sha256_le_v1",
            "cpu_record_sha256_le_v1",
        ):
            zero_digest["gpu_record_sha256_le_v1"] = "0" * 64
            zero_digest["cpu_record_sha256_le_v1"] = "0" * 64
        zero_digest["receipt_chain_sha256"] = hashlib.sha256(
            _canonical_transition(zero_digest)
        ).hexdigest()
        try:
            verify_mobius_receipt(zero_digest)
        except MobiusReceiptError:
            pass
        else:
            raise AssertionError(
                f"receipt checker accepted zero {digest_field}"
            )

    conditional_problem = execute(
        args.runner,
        "--lower",
        "9243",
        "--count",
        "1",
        "--incoming-mertens",
        "0",
        "--incoming-squarefree",
        "0",
        "--incoming-little-mertens-lower",
        "0",
        "--incoming-little-mertens-upper",
        "0",
        "--previous-receipt-sha256",
        "a" * 64,
    )
    if conditional_problem["cdem_b1_first_not_proved_safe"] is None:
        raise AssertionError("deliberately false conditional state produced no problem")
    bad_side = json.loads(json.dumps(conditional_problem))
    bad_side["cdem_b1_first_not_proved_safe"]["side"] = "invented_endpoint"
    try:
        verify_mobius_receipt(bad_side)
    except MobiusReceiptError:
        pass
    else:
        raise AssertionError("receipt checker accepted a tampered endpoint side")
    missing_status = dict(first)
    missing_status.pop("checks_hurst_source_shape_conditionally")
    try:
        verify_mobius_receipt(missing_status)
    except MobiusReceiptError:
        pass
    else:
        raise AssertionError("receipt checker accepted omitted source-shape status")

    with tempfile.TemporaryDirectory(prefix="tg-little-mertens-campaign-") as raw:
        directory = Path(raw)
        first_campaign = run_campaign(
            runner=args.runner,
            output_directory=directory,
            target="stronger",
            segment_count=500,
            allow_other_device=True,
            max_chunks=1,
        )
        if first_campaign.completed_upper != 500 or first_campaign.complete:
            raise AssertionError(f"unexpected first campaign state: {first_campaign}")
        retained = verify_campaign(directory)
        if retained.completed_upper != 500 or retained.locally_supervised_execution:
            raise AssertionError(f"unexpected retained campaign state: {retained}")
        resumed = run_campaign(
            runner=args.runner,
            output_directory=directory,
            target="stronger",
            segment_count=500,
            allow_other_device=True,
            max_chunks=1,
        )
        if resumed.completed_upper != 1_000 or resumed.receipts != 2:
            raise AssertionError(f"campaign did not resume exactly: {resumed}")

    for target, count in (("hurst", 100), ("squarefree", 450_000)):
        with tempfile.TemporaryDirectory(prefix=f"tg-{target}-campaign-") as raw:
            sampled = run_campaign(
                runner=args.runner,
                output_directory=Path(raw),
                target=target,
                segment_count=count,
                allow_other_device=True,
                max_chunks=1,
            )
            if sampled.completed_upper != count or sampled.complete:
                raise AssertionError(f"unexpected {target} sample: {sampled}")
            if target == "hurst" and not sampled.structurally_reports_no_hurst_failure:
                raise AssertionError("bounded Hurst campaign reported a failure")
            if target == "squarefree" and not (
                sampled.structurally_reports_no_cdem_b1_failure
                and sampled.structurally_reports_no_cdem_b2_failure
            ):
                raise AssertionError("bounded squarefree campaign reported a failure")

    print("CUDA Moebius segment known-answer and chain tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
