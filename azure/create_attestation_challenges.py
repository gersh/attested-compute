#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Create fresh off-VM challenges for an Azure trusted-compute campaign."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import secrets
import sys
from typing import Any


KIND = "gpu_prover_azure_run_challenge"
SCHEMA_VERSION = 1
CAMPAIGN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
DEFAULT_TTL_SECONDS = 24 * 60 * 60
MAX_TTL_SECONDS = 7 * 24 * 60 * 60


class ChallengeError(ValueError):
    """A challenge request is not safe or well formed."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_challenges(
    campaign_id: str,
    count: int,
    issued_at: dt.datetime,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> list[dict[str, Any]]:
    if CAMPAIGN_RE.fullmatch(campaign_id) is None:
        raise ChallengeError("invalid campaign id")
    if count < 1 or count > 999:
        raise ChallengeError("count must be in [1, 999]")
    if issued_at.tzinfo is None:
        raise ChallengeError("issued_at must be timezone-aware")
    if (
        not isinstance(ttl_seconds, int)
        or isinstance(ttl_seconds, bool)
        or not 1 <= ttl_seconds <= MAX_TTL_SECONDS
    ):
        raise ChallengeError(f"ttl_seconds must be in [1, {MAX_TTL_SECONDS}]")
    issued_at = issued_at.astimezone(dt.timezone.utc).replace(microsecond=0)
    expires_at = issued_at + dt.timedelta(seconds=ttl_seconds)
    timestamp = issued_at.isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    expiration = expires_at.isoformat(timespec="seconds").replace("+00:00", "Z")
    return [
        {
            "campaign_id": campaign_id,
            "expires_at_utc": expiration,
            "issued_at_utc": timestamp,
            "kind": KIND,
            "nonce": secrets.token_hex(32),
            "schema_version": SCHEMA_VERSION,
            "shard_index": index,
        }
        for index in range(count)
    ]


def write_new_file(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--ttl-seconds",
        type=int,
        default=DEFAULT_TTL_SECONDS,
        help=f"challenge lifetime, at most {MAX_TTL_SECONDS} seconds",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        challenges = build_challenges(
            args.campaign_id,
            args.count,
            dt.datetime.now(dt.timezone.utc),
            args.ttl_seconds,
        )
        if args.dry_run:
            print(
                json.dumps(
                    {
                        "accepted": False,
                        "classification": "dry_run_challenges_not_persisted",
                        "campaign_id": args.campaign_id,
                        "count": args.count,
                        "output_dir": str(args.output_dir),
                        "ttl_seconds": args.ttl_seconds,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0
        args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        for challenge in challenges:
            write_new_file(
                args.output_dir / f"shard-{challenge['shard_index']:03d}.challenge.json",
                canonical_json_bytes(challenge),
            )
        print(
            json.dumps(
                {
                    "accepted": True,
                    "classification": "fresh_challenges_persisted_off_vm",
                    "campaign_id": args.campaign_id,
                    "count": args.count,
                    "output_dir": str(args.output_dir),
                    "ttl_seconds": args.ttl_seconds,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except (ChallengeError, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "classification": "challenge_generation_failed_closed",
                    "error": str(error),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
