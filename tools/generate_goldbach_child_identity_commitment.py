#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Verify every nonterminal Goldbach receipt and write its terminal commitment.

Run this after all 8,517 nonterminal nodes finish and before materializing the
terminal CPU job.  The resulting canonical file is copied into that job's
artifact closure, so the terminal signed statement commits the complete child
identity set through its ``kernel_manifest_hash``.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "tools", ROOT / "attestation", ROOT / "azure"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from generate_goldbach_terminal_registration import (  # noqa: E402
    GoldbachTerminalGeneratorError,
    load_child_identities,
)
from tg_verifier.campaign_io import canonical_json_bytes  # noqa: E402
from tg_verifier.goldbach_build_admission import (  # noqa: E402
    GoldbachBuildAdmissionError,
    load_build_admission,
)
from tg_verifier.goldbach_terminal_identity import (  # noqa: E402
    GoldbachTerminalIdentityError,
    child_identity_commitment,
)


def _write_all_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o400,
    )
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write while publishing child commitment")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--build-admission", type=Path, required=True)
    result.add_argument("--child-index", type=Path, required=True)
    result.add_argument("--key-manifest", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument(
        "--allow-test-fixture", action="store_true", help=argparse.SUPPRESS
    )
    result.add_argument(
        "--allow-development-key", action="store_true", help=argparse.SUPPRESS
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        admission = load_build_admission(
            args.build_admission,
            allow_test_fixture=args.allow_test_fixture,
        )
        identities = load_child_identities(
            args.child_index,
            key_manifest=args.key_manifest,
            admission=admission,
            allow_development_key=args.allow_development_key,
        )
        commitment = child_identity_commitment(
            identities,
            build_admission_sha256=admission.admission_sha256,
            build_identity_sha256=admission.build_identity_sha256,
            h100_executable_sha256=admission.core["executable"]["sha256"],
            h100_runtime_image_closure_sha256=admission.deployment[
                "runtime_image_closure_sha256"
            ],
        )
        _write_all_exclusive(args.output, canonical_json_bytes(commitment))
        print(
            "verified all nonterminal receipts and wrote the terminal child "
            f"identity commitment ({commitment['child_identities_sha256']})"
        )
        return 0
    except (
        GoldbachBuildAdmissionError,
        GoldbachTerminalGeneratorError,
        GoldbachTerminalIdentityError,
        OSError,
        ValueError,
    ) as error:
        print(f"Goldbach child commitment error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
