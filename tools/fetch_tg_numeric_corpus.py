#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fetch or resolve, verify, and optionally materialize a pinned numeric corpus."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.campaign_io import canonical_json_bytes  # noqa: E402
from tg_verifier.numeric_corpus import (  # noqa: E402
    NumericCorpusError,
    fetch_pinned_repository,
    load_pin,
    materialize_git_corpus,
    verify_git_corpus,
)


def _run(
    pin_path: Path,
    *,
    checkout: Path | None,
    cache_root: Path | None,
) -> dict[str, object]:
    pin = load_pin(pin_path)

    def verify(resolver: Path) -> dict[str, object]:
        if cache_root is None:
            return verify_git_corpus(resolver, pin)
        return materialize_git_corpus(resolver, pin, cache_root)

    if checkout is not None:
        return verify(checkout)
    with tempfile.TemporaryDirectory(prefix="numeric-corpus-fetch-") as temporary:
        resolver = Path(temporary) / "resolver.git"
        fetch_pinned_repository(pin, resolver)
        return verify(resolver)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pin", type=Path, help="trusted canonical consumer pin")
    parser.add_argument(
        "--checkout",
        type=Path,
        help=(
            "existing Git checkout or bare repository used only to resolve "
            "the pinned commit's objects"
        ),
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        help=(
            "optional private mode-0700 directory for an atomically published "
            "read-only snapshot"
        ),
    )
    arguments = parser.parse_args()
    try:
        report = _run(
            arguments.pin,
            checkout=arguments.checkout,
            cache_root=arguments.cache_root,
        )
        sys.stdout.buffer.write(canonical_json_bytes(report))
        return 0
    except (NumericCorpusError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
