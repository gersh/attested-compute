# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed wire contract for the finite computation behind Helfgott (2.18).

This module contains only protocol constants, canonical JSON helpers, and the
source-shaped production input.  The producer and the independent verifier
deliberately keep their arithmetic implementations in separate modules.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


RUN_INPUT_KIND = "sparkinterval.sqrt218-finite-run-input.v1"
CERTIFICATE_KIND = "sparkinterval.sqrt218-finite-certificate.v1"
VERIFICATION_KIND = "sparkinterval.sqrt218-finite-verification.v1"
ALGORITHM_ID = "sparkinterval.ternary-goldbach.sqrt218-finite.v1"
SCHEMA_VERSION = 1

BOUND = 2_000_000
LOCAL_KAT_MAX_BOUND = 64
AZURE_MEASURED_PRODUCTION_CONTEXT = "azure_sevsnp_measured_production_v1"
REUSED_BOUND = 1_517_397
SCALE = 281_474_976_710_656
RECIPROCAL_SCALE = 1_073_741_824
LOG_SEED_AT = 30
LOG_DEPTH = 14

EXPECTED_PRIME_COUNT = 148_933
EXPECTED_REUSED_PRIME_COUNT = 115_408
EXPECTED_TAIL_PRIME_COUNT = 33_525
EXPECTED_POWER_EVENT_COUNT = 149_235
EXPECTED_PROPER_POWER_COUNT = 302
EXPECTED_MINIMUM_HEAD_SLACK = 77_167_896_433_454_640_411_789_476
EXPECTED_MINIMUM_HEAD_N = 6_397
EXPECTED_ANCHOR_SLACK = 2_134_933_357_595_048_382_226_455_716
EXPECTED_FINAL_WEIGHTED_UPPER = 854_091_852_238_662_506_255_905_837
EXPECTED_FINAL_PSI_LOWER = 562_949_761_260_501_289_147
EXPECTED_PRATT_SHA256 = (
    "46b67778699d196eec624ba71f8fc07de9d0218afbd0a0930c2113e37ddbfd07"
)
EXPECTED_LAYOUT_SHA256 = (
    "c7a559cf7dd1a38c97e73b224a4021a44c62f68d2ad17f1a50a31f72c1ca1055"
)
EXPECTED_FIXED_SHA256 = (
    "0eda447334b59b886d3d2b70e3aed3a8375823dbc1180e190e0ad67517e9c559"
)

SOURCE_STATEMENT = (
    "For the complete prime and prime-power rosters through 2,000,000, "
    "the directed scale-2^48 prime-log ladder and scale-2^30 reciprocal-"
    "square-root scan satisfy every integer head guard in Helfgott (2.18) "
    "and its endpoint Abel anchor, with the exact pinned final state."
)
LEAN_CLAIM = (
    "SparkInterval.TernaryGoldbach.Sqrt218SourceSemantics.SourceClaim"
)
CORPUS_CLAIM_ID = "helfgott.sqrt218.finite"
CORPUS_ID = "ternary-goldbach.sqrt218.certificate"
CORPUS_COVERAGE_ID = "sqrt218_certificate_archive"
CORPUS_ROLE = "sqrt218_certificate_archive"
CORPUS_ENCODING = "canonical_json_sqrt218_finite_certificate_v1"
CORPUS_PARAMETERS = {
    "bound": "2000000",
    "log_depth": "14",
    "log_seed_count": "30",
    "log_scale": "281474976710656",
    "reciprocal_scale": "1073741824",
}
CORPUS_COMMITMENTS = (
    (
        "fixed_scan",
        "sparkinterval/sqrt218/fixed-scan/v1",
        EXPECTED_FIXED_SHA256,
    ),
    (
        "pratt_rows",
        "sparkinterval/sqrt218/pratt-rows/v1",
        EXPECTED_PRATT_SHA256,
    ),
    (
        "prime_power_layout",
        "sparkinterval/sqrt218/prime-power-layout/v1",
        EXPECTED_LAYOUT_SHA256,
    ),
)

ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v1\n"
    "name=ternary-goldbach-sqrt218-finite\n"
    "bound=2000000\n"
    "prime-roster=complete-eratosthenes-and-lucas-pratt-witnesses\n"
    "prime-powers=all-powers-p^k-with-k-positive-and-p^k-at-most-bound\n"
    "log-enclosure=scale-2^48-seed-30-rational-ladder-depth-14\n"
    "reciprocal-sqrt=scale-2^30-rational-lower-and-upper-bounds\n"
    "scan=ordered-prime-power-fixed-point-prefix-with-every-head-guard\n"
    "terminal=exact-final-state-and-endpoint-abel-anchor\n"
    "result=canonical-ascii-true-only-after-independent-full-archive-replay"
)

TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.sqrt218-finite.v1\n"
    "archive=canonical-json-complete-prime-pratt-log-and-prime-power-rows\n"
    "verification=independent-prime-sieve-pratt-layout-log-and-full-prefix-replay\n"
    "trace=SHA256(domain-separated challenge,job,input,result,archive,report bindings)\n"
    "iteration-count=2000000"
)


def require_replay_scope(
    bound: int,
    *,
    execution_context: str | None,
) -> None:
    """Reject expensive replay unless it is the exact measured Azure job.

    Ordinary local callers are intentionally limited to the bound-64 KAT
    envelope.  There is no supported intermediate "large sample" profile:
    anything above 64 must be the exact production bound and must arrive
    through the explicitly selected measured-production context.
    """

    if bound <= LOCAL_KAT_MAX_BOUND:
        return
    if (
        bound != BOUND
        or execution_context != AZURE_MEASURED_PRODUCTION_CONTEXT
    ):
        raise ValueError(
            "Sqrt218 replay above bound 64 is disabled for ordinary local "
            "execution; bound 2,000,000 requires the Azure measured-production "
            "context"
        )

# Declarative operational IR used for source review and future translation
# validation.  It is intentionally architecture-neutral: no x86 binary
# refinement theorem currently exists for the Python implementation.
OPERATIONAL_STATE_MACHINE = {
    "arithmetic": {
        "integer": "mathematical_unbounded_integer",
        "sha256": "fips_180_4_sha256_over_exact_ascii_transcripts",
    },
    "bound": BOUND,
    "kind": "sparkinterval.sqrt218-operational-state-machine.v1",
    "phases": [
        "validate_exact_registered_input",
        "resolve_verified_numeric_corpus_or_generate_archive",
        "enumerate_complete_prime_roster",
        "verify_complete_p_minus_one_factorizations_and_lucas_witnesses",
        "advance_directed_scale_2_pow_48_log_ladder",
        "enumerate_complete_ordered_prime_power_roster",
        "scan_every_integer_prefix_head_guard",
        "check_endpoint_abel_anchor",
        "independently_replay_complete_archive",
        "emit_exact_ascii_true_and_challenge_bound_trace",
    ],
    "state": [
        "next_integer",
        "next_prime_power_event",
        "weighted_upper",
        "psi_lower",
        "minimum_head_slack",
        "minimum_head_n",
    ],
    "terminal_pins": {
        "anchor_slack": EXPECTED_ANCHOR_SLACK,
        "final_psi_lower": EXPECTED_FINAL_PSI_LOWER,
        "final_weighted_upper": EXPECTED_FINAL_WEIGHTED_UPPER,
        "fixed_scan_sha256": EXPECTED_FIXED_SHA256,
        "layout_sha256": EXPECTED_LAYOUT_SHA256,
        "minimum_head_n": EXPECTED_MINIMUM_HEAD_N,
        "minimum_head_slack": EXPECTED_MINIMUM_HEAD_SLACK,
        "power_event_count": EXPECTED_POWER_EVENT_COUNT,
        "pratt_sha256": EXPECTED_PRATT_SHA256,
        "prime_count": EXPECTED_PRIME_COUNT,
        "proper_power_count": EXPECTED_PROPER_POWER_COUNT,
    },
}

BOUND_64_KAT = {
    "bound": 64,
    "certificate_sha256": (
        "cc96f30214a37997c1b55fc54454b81aaec2af40fc3abd7a1836a445c8b32db7"
    ),
    "summary": {
        "anchor_slack": 1_827_919_267_695_019_450_126_414_852,
        "final_psi_lower": 17_545_453_039_958_061,
        "final_weighted_upper": 4_042_561_916_560_806_435_406_959,
        "fixed_scan_sha256": (
            "2602667871a09f8bfa10336da7bf3af6d95e0633f1653907acbb1d08e83154f3"
        ),
        "layout_sha256": (
            "b664585bf5149d9c19bc7ae7c8e4ea687d11b679c95bc1bc131d4e2ddfeb3e10"
        ),
        "minimum_head_n": 47,
        "minimum_head_slack": 225_416_760_203_369_680_291_933_014,
        "power_event_count": 27,
        "pratt_sha256": (
            "23a7fc04b8d35f444e0ad34b38097ff5059fbdeea1aef0e2c10af737c827f688"
        ),
        "prime_count": 18,
        "proper_power_count": 9,
        "reused_prime_count": 18,
        "tail_prime_count": 0,
    },
}

# Exact scale-2^48 seed boxes used by the ordinary Lean certificate.
LOG_SEEDS_30: tuple[tuple[int, int], ...] = (
    (0, 0),
    (195103586431999, 195103586572737),
    (309231868028532, 309231868693940),
    (390207172863998, 390207173145474),
    (453016498773239, 453016499054997),
    (504335454460532, 504335455266677),
    (547725013666734, 547725014089229),
    (585310759295998, 585310759718211),
    (618463736514181, 618463736936676),
    (648120085205239, 648120085627734),
    (674947515845858, 674947516268353),
    (699439040892531, 699439041839414),
    (721969060362613, 721969060925845),
    (742828600098734, 742828600661966),
    (762248366993738, 762248367556971),
    (780414345727997, 780414346290948),
    (797478659741748, 797478660304980),
    (813567322946180, 813567323509412),
    (828785892793963, 828785893357196),
    (843223671637238, 843223672200471),
    (856956881960417, 856956882523649),
    (870051102277858, 870051102841090),
    (882563161108618, 882563161679169),
    (894542627324530, 894542628412151),
    (906032997473296, 906032998177266),
    (917072646794612, 917072647498582),
    (927695604734679, 927695605438649),
    (937932186530733, 937932187234703),
    (947809514957280, 947809515661250),
    (957351953425738, 957351954129708),
)


class Sqrt218ContractError(ValueError):
    """A wire value does not satisfy the closed Sqrt218 protocol."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the project's canonical UTF-8 JSON encoding, without a newline."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise Sqrt218ContractError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def parse_canonical_json(raw: bytes, *, what: str, maximum_bytes: int) -> Any:
    if not isinstance(raw, bytes) or len(raw) > maximum_bytes:
        raise Sqrt218ContractError(f"{what} exceeds its byte limit")
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                Sqrt218ContractError(f"non-finite JSON number: {token}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise Sqrt218ContractError(f"{what} is not strict UTF-8 JSON: {error}") from error
    if canonical_json_bytes(value) != raw:
        raise Sqrt218ContractError(f"{what} is not canonical JSON")
    return value


def recomputation_run_input() -> dict[str, Any]:
    """Return the closed V1 full-recomputation input.

    This is not the future corpus-backed production input.  A real production
    corpus pin necessarily has a different, versioned input digest.
    """

    return {
        "bound": BOUND,
        "claim_id": "helfgott-sqrt218-finite-v1",
        "expected": {
            "anchor_slack": EXPECTED_ANCHOR_SLACK,
            "final_psi_lower": EXPECTED_FINAL_PSI_LOWER,
            "final_weighted_upper": EXPECTED_FINAL_WEIGHTED_UPPER,
            "fixed_scan_sha256": EXPECTED_FIXED_SHA256,
            "layout_sha256": EXPECTED_LAYOUT_SHA256,
            "minimum_head_n": EXPECTED_MINIMUM_HEAD_N,
            "minimum_head_slack": EXPECTED_MINIMUM_HEAD_SLACK,
            "power_event_count": EXPECTED_POWER_EVENT_COUNT,
            "pratt_sha256": EXPECTED_PRATT_SHA256,
            "prime_count": EXPECTED_PRIME_COUNT,
            "proper_power_count": EXPECTED_PROPER_POWER_COUNT,
            "reused_prime_count": EXPECTED_REUSED_PRIME_COUNT,
            "tail_prime_count": EXPECTED_TAIL_PRIME_COUNT,
        },
        "kind": RUN_INPUT_KIND,
        "lean_claim": LEAN_CLAIM,
        "log_depth": LOG_DEPTH,
        "log_scale": SCALE,
        "reciprocal_scale": RECIPROCAL_SCALE,
        "schema_version": SCHEMA_VERSION,
        "source_statement": SOURCE_STATEMENT,
    }


def recomputation_run_input_bytes() -> bytes:
    return canonical_json_bytes(recomputation_run_input())


# Compatibility names for the already registered V1 digest.  New code should
# use the explicit recomputation names above.
def production_run_input() -> dict[str, Any]:
    return recomputation_run_input()


def production_run_input_bytes() -> bytes:
    return recomputation_run_input_bytes()
