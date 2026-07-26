# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Small shared contract for the optimized Goldbach H100 calibration job."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


INPUT_KIND = "sparkinterval.goldbach-optimized-h100-calibration-input.v1"
RESULT_KIND = "sparkinterval.goldbach-optimized-h100-calibration-result.v1"
TRACE_KIND = "sparkinterval_challenge_work_trace"
ALGORITHM_PREFIX = (
    "sparkinterval.tg.goldbach-optimized-h100-calibration."
)
CLASSIFICATION = (
    "bounded-target-sku-performance-calibration-not-production-run"
)
TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.goldbach-optimized-h100-calibration.v1\n"
    "initial=SHA256(challenge-job-input-candidate-executable)\n"
    "step=SHA256(previous-result-all-stdout)\n"
    "verification=independent-canonical-result-and-runner-stdout-replay"
)
INITIAL_DOMAIN = (
    b"sparkinterval/tg/goldbach-optimized-calibration/trace-initial/v1\x00"
)
STEP_DOMAIN = (
    b"sparkinterval/tg/goldbach-optimized-calibration/trace-step/v1\x00"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_REPETITIONS = 7
MAX_WARMUPS = 3
MAX_SAMPLE_EVEN_COUNT = 20_000_000_000
DEFAULT_SAMPLE_EVEN_LIMIT = 31_250_000_000_000_000
DEFAULT_SAMPLE_EVEN_COUNT = 20_000_000_000
DEFAULT_SAMPLE_EVEN_START = (
    DEFAULT_SAMPLE_EVEN_LIMIT - 2 * (DEFAULT_SAMPLE_EVEN_COUNT - 1)
)


class GoldbachCalibrationContractError(ValueError):
    """A calibration input or shared identity is malformed."""


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: Any, what: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise GoldbachCalibrationContractError(
            f"{what} must be lowercase SHA-256 hex"
        )
    return value


def validate_input(value: object) -> dict[str, Any]:
    fields = {
        "candidate",
        "classification",
        "domain",
        "kind",
        "repetitions",
        "schema_version",
        "warmups",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise GoldbachCalibrationContractError(
            "calibration input has wrong fields"
        )
    if (
        value["kind"] != INPUT_KIND
        or value["schema_version"] != 1
        or value["classification"] != CLASSIFICATION
    ):
        raise GoldbachCalibrationContractError(
            "calibration input kind/classification differs"
        )
    candidate_fields = {
        "candidate_closure_sha256",
        "candidate_manifest_sha256",
        "cubin_sha256",
        "executable_sha256",
        "executable_size_bytes",
        "ptx_sha256",
        "sass_sha256",
        "source_identity_sha256",
    }
    candidate = value["candidate"]
    if not isinstance(candidate, dict) or set(candidate) != candidate_fields:
        raise GoldbachCalibrationContractError(
            "calibration candidate identity has wrong fields"
        )
    for name in candidate_fields - {"executable_size_bytes"}:
        _digest(candidate[name], f"candidate.{name}")
    size = candidate["executable_size_bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise GoldbachCalibrationContractError(
            "candidate executable size must be positive"
        )
    domain = value["domain"]
    domain_fields = {
        "even_count",
        "even_limit_inclusive",
        "even_start_inclusive",
    }
    if not isinstance(domain, dict) or set(domain) != domain_fields:
        raise GoldbachCalibrationContractError(
            "calibration domain has wrong fields"
        )
    start = domain["even_start_inclusive"]
    limit = domain["even_limit_inclusive"]
    count = domain["even_count"]
    if (
        any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in (start, limit, count)
        )
        or start < 4
        or start % 2
        or limit < start
        or limit % 2
        or count != (limit - start) // 2 + 1
        or not 1 <= count <= MAX_SAMPLE_EVEN_COUNT
    ):
        raise GoldbachCalibrationContractError(
            "calibration domain is not a bounded nonempty even range"
        )
    warmups = value["warmups"]
    repetitions = value["repetitions"]
    if (
        isinstance(warmups, bool)
        or not isinstance(warmups, int)
        or not 0 <= warmups <= MAX_WARMUPS
        or isinstance(repetitions, bool)
        or not isinstance(repetitions, int)
        or repetitions not in (1, 3, 5, 7)
    ):
        raise GoldbachCalibrationContractError(
            "calibration warmup/repetition count differs"
        )
    return value


def algorithm_definition(value: object) -> str:
    checked = validate_input(value)
    candidate = checked["candidate"]
    domain = checked["domain"]
    return (
        "sparkinterval.azure-calibration-algorithm.v1\n"
        "classification=bounded-target-sku-performance-calibration-only\n"
        f"candidate-manifest-sha256={candidate['candidate_manifest_sha256']}\n"
        f"candidate-closure-sha256={candidate['candidate_closure_sha256']}\n"
        f"source-identity-sha256={candidate['source_identity_sha256']}\n"
        f"executable-sha256={candidate['executable_sha256']}\n"
        f"ptx-sha256={candidate['ptx_sha256']}\n"
        f"cubin-sha256={candidate['cubin_sha256']}\n"
        f"sass-sha256={candidate['sass_sha256']}\n"
        f"even-start={domain['even_start_inclusive']}\n"
        f"even-limit={domain['even_limit_inclusive']}\n"
        f"even-count={domain['even_count']}\n"
        f"warmups={checked['warmups']}\n"
        f"repetitions={checked['repetitions']}\n"
        "semantics=run-exact-candidate-and-strictly-parse-each-success-transcript\n"
        "authority=no-production-no-receipt-no-Lean-atom"
    )


def algorithm_identity(value: object) -> dict[str, str]:
    definition = algorithm_definition(value)
    digest = hashlib.sha256(definition.encode("utf-8")).hexdigest()
    return {
        "algorithm_id": ALGORITHM_PREFIX + digest,
        "canonical_definition": definition,
        "definition_sha256": digest,
    }


def parameters_value(value: object) -> dict[str, int]:
    checked = validate_input(value)
    return {
        "cuda_visible_device": 0,
        "repetitions": checked["repetitions"],
        "warmups": checked["warmups"],
    }


def trace_sha256(
    *,
    challenge_nonce: str,
    job_binding_sha256: str,
    input_sha256: str,
    executable_sha256: str,
    result_sha256: str,
    stdout_sha256s: list[str],
) -> str:
    for item, what in (
        (challenge_nonce, "challenge nonce"),
        (job_binding_sha256, "job binding"),
        (input_sha256, "input"),
        (executable_sha256, "executable"),
        (result_sha256, "result"),
    ):
        _digest(item, what)
    if not stdout_sha256s:
        raise GoldbachCalibrationContractError(
            "trace needs at least one retained stdout hash"
        )
    for index, item in enumerate(stdout_sha256s):
        _digest(item, f"stdout hash {index}")
    initial = hashlib.sha256(
        INITIAL_DOMAIN
        + bytes.fromhex(challenge_nonce)
        + bytes.fromhex(job_binding_sha256)
        + bytes.fromhex(input_sha256)
        + bytes.fromhex(executable_sha256)
    ).digest()
    return hashlib.sha256(
        STEP_DOMAIN
        + initial
        + bytes.fromhex(result_sha256)
        + b"".join(bytes.fromhex(item) for item in stdout_sha256s)
    ).hexdigest()


__all__ = [
    "ALGORITHM_PREFIX",
    "CLASSIFICATION",
    "DEFAULT_SAMPLE_EVEN_COUNT",
    "DEFAULT_SAMPLE_EVEN_LIMIT",
    "DEFAULT_SAMPLE_EVEN_START",
    "GoldbachCalibrationContractError",
    "INPUT_KIND",
    "MAX_SAMPLE_EVEN_COUNT",
    "RESULT_KIND",
    "TRACE_DEFINITION",
    "TRACE_KIND",
    "algorithm_definition",
    "algorithm_identity",
    "canonical_json_bytes",
    "parameters_value",
    "sha256_bytes",
    "trace_sha256",
    "validate_input",
]
