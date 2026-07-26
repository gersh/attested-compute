#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fetch or verify the pinned python-flint 0.9.0 source and x86 wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.python_flint_runtime import (  # noqa: E402
    PythonFlintRuntimeError,
    load_pin,
    verify_checkout,
    verify_wheel,
)


def _git(argv: list[str], *, cwd: Path | None = None) -> None:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )
    if completed.returncode != 0:
        raise PythonFlintRuntimeError(
            (completed.stderr or completed.stdout)[-3000:].decode("utf-8", "replace")
        )


def fetch_source(checkout: Path, pin: dict[str, object]) -> None:
    if checkout.exists():
        return
    checkout.parent.mkdir(parents=True, exist_ok=True)
    _git(["git", "clone", "--no-checkout", str(pin["repository"]), str(checkout)])
    _git(["git", "checkout", "--detach", str(pin["commit"])], cwd=checkout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    try:
        pin = load_pin()
        if args.fetch:
            fetch_source(args.checkout, pin)
            # Download to a filename fixed by the pin. A differently named
            # destination is deliberately rejected by verify_wheel.
            runtime = pin["runtime_wheel"]
            assert isinstance(runtime, dict)
            if args.wheel.name != runtime["filename"]:
                raise PythonFlintRuntimeError("wheel destination filename differs from pin")
            if not args.wheel.exists():
                args.wheel.parent.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(str(runtime["source_url"]), timeout=300) as response:
                    raw = response.read(int(runtime["size_bytes"]) + 1)
                if (
                    len(raw) != runtime["size_bytes"]
                    or hashlib.sha256(raw).hexdigest() != runtime["sha256"]
                ):
                    raise PythonFlintRuntimeError("downloaded wheel differs from its pin")
                descriptor = args.wheel.open("xb")
                with descriptor:
                    descriptor.write(raw)
        source = verify_checkout(args.checkout, pin)
        wheel = verify_wheel(args.wheel, pin)
        print(
            json.dumps(
                {"accepted": True, "source": source, "wheel": wheel},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except (OSError, PythonFlintRuntimeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
