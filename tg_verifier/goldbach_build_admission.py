# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed build and measured-job admission for GoldbachGPU.

The production allowlist is deliberately empty until the exact Azure x86_64
compiler, runtime, executable, and materialized closure have been reviewed.
Tests may explicitly load a ``test-fixture`` admission; production callers may
not silently opt into that path.

The admitted full JSON file is content addressed by its site pin.  A separate
build-core digest is used inside the measured closure so the closure digest
does not recursively depend on an admission that itself records the expected
closure digest.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from tg_verifier.campaign_io import (
    CampaignIOError,
    canonical_json_bytes,
    hash_file_once,
    load_json,
)
from tg_verifier.goldbach_gpu_campaign import (
    EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256,
)


ADMISSION_KIND = "sparkinterval.goldbach-gpu-build-admission.v1"
RUNTIME_IDENTITY_KIND = "sparkinterval.goldbach-gpu-runtime-build-identity.v1"
RUNTIME_IMAGE_CLOSURE_KIND = (
    "sparkinterval.goldbach-gpu-runtime-image-closure.v1"
)
EXECUTION_PROJECTION_KIND = (
    "sparkinterval.goldbach10pow27-h100-execution-projection.v1"
)
SCHEMA_VERSION = 1
GOLDBACH_H100_ALGORITHM_PREFIX = (
    "sparkinterval.tg.goldbach10pow27.h100-group."
)
SIGNED_ALGORITHM_ID_TOKEN = "<signed-algorithm-id>"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
ZERO_DIGEST = "0" * 64
AZURE_IMAGE_RE = re.compile(
    r"/subscriptions/[^/]+/resourceGroups/[^/]+/providers/"
    r"Microsoft\.Compute/galleries/[^/]+/images/[^/]+/versions/"
    r"[0-9]+(?:\.[0-9]+){2}\Z"
)

# This is intentionally empty.  A real production admission becomes usable
# only after its exact canonical file digest is reviewed and added here.
REVIEWED_PRODUCTION_ADMISSION_SHA256S: frozenset[str] = frozenset()

H100_BUILD_ENVIRONMENT = {
    "HOME": "/nonexistent",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/local/cuda/bin:/usr/bin:/bin",
    "SOURCE_DATE_EPOCH": "0",
    "TZ": "UTC",
}

H100_BUILD_ARGV_TEMPLATE = (
    "nvcc",
    "-O3",
    "-std=c++17",
    "-arch=sm_90",
    "-ccbin",
    "host-cxx",
    "--threads",
    "1",
    "-I",
    "source/goldbach-gpu-hardened/include",
    (
        "-Xcompiler=-O3,-march=x86-64-v2,-mtune=generic,-fopenmp,"
        "-ffile-prefix-map=<artifact-root>=.,"
        "-fdebug-prefix-map=<artifact-root>=."
    ),
    "-Xlinker",
    "--build-id=none",
    "source/goldbach-gpu-hardened/src/goldbach.cu",
    "source/goldbach-gpu-hardened/src/prime_bitset.cpp",
    "source/goldbach-gpu-hardened/src/segmented_sieve.cpp",
    "-lgomp",
    "-o",
    "artifacts/goldbach-gpu",
)

JOB_DERIVATION_DEFINITION = (
    "sparkinterval.goldbach10pow27-h100-job-derivation.v1\n"
    "algorithm=separately-signed-and-excluded-from-projection\n"
    "algorithm-argv=must-equal-signed-id-then-normalized\n"
    "artifact-closure=kind-and-manifest-sha256\n"
    "command=exact-argv-cwd-environment-timeout\n"
    "input=exact-path-release-mode-sha256-size\n"
    "deployment=exact-backend-runner-target-trust-gpu-gate-tpm\n"
    "output=exact-contract\n"
    "trace=exact-contract-and-normalized-verifier-argv\n"
    "job=exact-id-kind-schema-parameters-domain"
)

EXPECTED_BUILD_ARGV_SHA256 = hashlib.sha256(
    canonical_json_bytes(list(H100_BUILD_ARGV_TEMPLATE))
).hexdigest()
EXPECTED_BUILD_ENVIRONMENT_SHA256 = hashlib.sha256(
    canonical_json_bytes(H100_BUILD_ENVIRONMENT)
).hexdigest()
EXPECTED_JOB_DERIVATION_SHA256 = hashlib.sha256(
    JOB_DERIVATION_DEFINITION.encode("utf-8")
).hexdigest()

# CUDA execution cannot be made a fully static ELF closure.  These components
# are therefore admitted as one exact immutable Azure image plus the policies
# that appraise its host boot chain and NVIDIA confidential-computing state.
RUNTIME_IMAGE_COMPONENTS = (
    "ELF interpreter and transitive host DSOs (including libc, libstdc++, "
    "libgcc, libgomp, and the copied CPython runtime dependencies)",
    "CUDA user-space runtime and driver libraries",
    "NVIDIA kernel driver, GPU firmware, VBIOS, RIM, and endorsement roots",
    "Linux kernel, initramfs, bootloader, and measured immutable root image",
)

_TOP_FIELDS = {
    "classification",
    "core",
    "deployment",
    "expected_artifacts",
    "kind",
    "schema_version",
}
_CORE_FIELDS = {
    "build_argv_sha256",
    "build_environment_sha256",
    "executable",
    "host_cxx",
    "job_derivation_sha256",
    "nvcc",
    "python",
    "source_identity_sha256",
}
_TOOL_FIELDS = {"sha256", "size_bytes", "version"}
_EXECUTABLE_FIELDS = {"sha256", "size_bytes"}
_ARTIFACT_FIELDS = {
    "artifact_closure_manifest_sha256",
    "source_tree_hash",
}
_DEPLOYMENT_FIELDS = {
    "gpu_verifier",
    "immutable_image_reference",
    "immutable_image_reference_sha256",
    "nras_url",
    "nvidia_policy_sha256",
    "runner_policy_id",
    "runner_policy_sha256",
    "runtime_image_closure_sha256",
    "target_profile_id",
    "target_profile_sha256",
    "trust_profile_id",
    "trust_profile_sha256",
}
_JOB_FIELDS = {
    "algorithm",
    "artifact_closure",
    "backend",
    "command",
    "domain_coverage",
    "gpu_pre_run_gate",
    "input_artifact",
    "job_id",
    "kind",
    "output_contract",
    "parameters",
    "runner_policy",
    "schema_version",
    "target_profile",
    "tpm_policy",
    "trust_profile",
    "work_trace_contract",
}
_RUNTIME_IMAGE_CLOSURE_FIELDS = {
    "components",
    "gpu_verifier",
    "immutable_image_reference",
    "immutable_image_reference_sha256",
    "kind",
    "nras_url",
    "nvidia_policy_sha256",
    "runner_policy_id",
    "runner_policy_sha256",
    "schema_version",
    "target_profile_id",
    "target_profile_sha256",
    "trust_profile_id",
    "trust_profile_sha256",
}


class GoldbachBuildAdmissionError(ValueError):
    """A build admission, admitted file, or measured job differed."""


def _exact(value: Any, fields: set[str], what: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        actual = set(value) if isinstance(value, dict) else set()
        raise GoldbachBuildAdmissionError(
            f"{what} has wrong fields "
            f"(missing={sorted(fields - actual)}, "
            f"unexpected={sorted(actual - fields)})"
        )
    return value


def _digest(value: Any, what: str) -> str:
    if (
        not isinstance(value, str)
        or SHA256_RE.fullmatch(value) is None
        or value == ZERO_DIGEST
    ):
        raise GoldbachBuildAdmissionError(
            f"{what} must be a nonzero lowercase SHA-256 digest"
        )
    return value


def _size(value: Any, what: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 < value <= 2**63 - 1
    ):
        raise GoldbachBuildAdmissionError(f"{what} must be a positive file size")
    return value


def _text(value: Any, what: str, *, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum
        or "\x00" in value
    ):
        raise GoldbachBuildAdmissionError(f"{what} must be nonempty bounded text")
    return value


def _tool(value: Any, what: str) -> dict[str, Any]:
    row = _exact(value, _TOOL_FIELDS, what)
    return {
        "sha256": _digest(row["sha256"], f"{what} SHA-256"),
        "size_bytes": _size(row["size_bytes"], f"{what} size"),
        "version": _text(row["version"], f"{what} version"),
    }


def _executable(value: Any) -> dict[str, Any]:
    row = _exact(value, _EXECUTABLE_FIELDS, "admitted GoldbachGPU executable")
    return {
        "sha256": _digest(row["sha256"], "GoldbachGPU executable SHA-256"),
        "size_bytes": _size(row["size_bytes"], "GoldbachGPU executable size"),
    }


@dataclass(frozen=True)
class GoldbachBuildAdmission:
    admission_sha256: str
    admission_size_bytes: int
    classification: str
    core: dict[str, Any]
    build_identity_sha256: str
    deployment: dict[str, str]
    expected_artifacts: dict[str, str]

    def runtime_identity(self) -> dict[str, Any]:
        return {
            "build_identity_sha256": self.build_identity_sha256,
            "core": copy.deepcopy(self.core),
            "kind": RUNTIME_IDENTITY_KIND,
            "schema_version": SCHEMA_VERSION,
        }

    def admitted_file(self, role: str) -> dict[str, Any]:
        if role not in {"python", "nvcc", "host_cxx", "executable"}:
            raise GoldbachBuildAdmissionError(f"unknown admitted file role: {role}")
        return copy.deepcopy(self.core[role])

    def runtime_image_closure(self) -> dict[str, Any]:
        return runtime_image_closure_value(self.deployment)


def runtime_image_closure_value(
    deployment: Mapping[str, str],
) -> dict[str, Any]:
    """Canonical dynamic-runtime boundary committed by the admission."""

    return {
        "components": list(RUNTIME_IMAGE_COMPONENTS),
        "gpu_verifier": deployment["gpu_verifier"],
        "immutable_image_reference": deployment["immutable_image_reference"],
        "immutable_image_reference_sha256": deployment[
            "immutable_image_reference_sha256"
        ],
        "kind": RUNTIME_IMAGE_CLOSURE_KIND,
        "nras_url": deployment["nras_url"],
        "nvidia_policy_sha256": deployment["nvidia_policy_sha256"],
        "runner_policy_id": deployment["runner_policy_id"],
        "runner_policy_sha256": deployment["runner_policy_sha256"],
        "schema_version": SCHEMA_VERSION,
        "target_profile_id": deployment["target_profile_id"],
        "target_profile_sha256": deployment["target_profile_sha256"],
        "trust_profile_id": deployment["trust_profile_id"],
        "trust_profile_sha256": deployment["trust_profile_sha256"],
    }


def verify_runtime_image_closure(
    value: Any, expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate the exact dynamic-runtime/image identity used inside a job."""

    row = _exact(
        value, _RUNTIME_IMAGE_CLOSURE_FIELDS, "Goldbach runtime image closure"
    )
    if (
        row["kind"] != RUNTIME_IMAGE_CLOSURE_KIND
        or row["schema_version"] != SCHEMA_VERSION
        or row["components"] != list(RUNTIME_IMAGE_COMPONENTS)
    ):
        raise GoldbachBuildAdmissionError(
            "unsupported Goldbach runtime image closure"
        )
    image = _text(row["immutable_image_reference"], "runtime image reference")
    if AZURE_IMAGE_RE.fullmatch(image) is None:
        raise GoldbachBuildAdmissionError(
            "runtime closure does not name an exact Azure image version"
        )
    image_sha256 = _digest(
        row["immutable_image_reference_sha256"], "runtime image reference"
    )
    if image_sha256 != hashlib.sha256(image.encode("utf-8")).hexdigest():
        raise GoldbachBuildAdmissionError("runtime image reference digest differs")
    for field in (
        "nvidia_policy_sha256",
        "runner_policy_sha256",
        "target_profile_sha256",
        "trust_profile_sha256",
    ):
        _digest(row[field], f"runtime closure {field}")
    for field in (
        "gpu_verifier",
        "nras_url",
        "runner_policy_id",
        "target_profile_id",
        "trust_profile_id",
    ):
        _text(row[field], f"runtime closure {field}")
    if (
        row["target_profile_id"] != "azure_ncc40ads_h100_v5"
        or row["trust_profile_id"]
        != "azure_ncc_sevsnp_vtpm_nvidia_cc_attested"
    ):
        raise GoldbachBuildAdmissionError(
            "runtime closure target/trust profile differs"
        )
    result = copy.deepcopy(row)
    actual_sha256 = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    if (
        expected_sha256 is not None
        and actual_sha256 != _digest(
            expected_sha256, "expected runtime image closure"
        )
    ):
        raise GoldbachBuildAdmissionError(
            "runtime image closure differs from its admitted digest"
        )
    return result


def load_build_admission(
    path: Path,
    *,
    expected_sha256: str | None = None,
    allow_test_fixture: bool = False,
) -> GoldbachBuildAdmission:
    """Load one canonical admission and enforce the empty production allowlist."""

    try:
        value = load_json(path, require_canonical=True)
        file_sha256, file_size = hash_file_once(path, limit=4 * 1024 * 1024)
    except (CampaignIOError, OSError, ValueError) as error:
        raise GoldbachBuildAdmissionError(
            f"cannot load canonical Goldbach build admission: {error}"
        ) from error
    if expected_sha256 is not None and file_sha256 != _digest(
        expected_sha256, "admission pin"
    ):
        raise GoldbachBuildAdmissionError(
            "Goldbach build admission differs from its content-addressed pin"
        )
    top = _exact(value, _TOP_FIELDS, "Goldbach build admission")
    if top["kind"] != ADMISSION_KIND or top["schema_version"] != SCHEMA_VERSION:
        raise GoldbachBuildAdmissionError(
            "unsupported Goldbach build admission kind/version"
        )
    classification = top["classification"]
    if classification == "reviewed-production":
        if file_sha256 not in REVIEWED_PRODUCTION_ADMISSION_SHA256S:
            raise GoldbachBuildAdmissionError(
                "production Goldbach build admission is unconfigured; "
                "review exact Azure x86_64 artifacts before populating the allowlist"
            )
    elif classification == "test-fixture":
        if not allow_test_fixture:
            raise GoldbachBuildAdmissionError(
                "test Goldbach build admission requires explicit test-only authority"
            )
    else:
        raise GoldbachBuildAdmissionError(
            "Goldbach build admission classification is unsupported"
        )

    raw_core = _exact(top["core"], _CORE_FIELDS, "Goldbach build core")
    source_identity = _digest(
        raw_core["source_identity_sha256"], "hardened source identity"
    )
    if source_identity != EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256:
        raise GoldbachBuildAdmissionError(
            "admission does not bind the active hardened source identity"
        )
    core = {
        "build_argv_sha256": _digest(
            raw_core["build_argv_sha256"], "canonical build argv"
        ),
        "build_environment_sha256": _digest(
            raw_core["build_environment_sha256"], "canonical build environment"
        ),
        "executable": _executable(raw_core["executable"]),
        "host_cxx": _tool(raw_core["host_cxx"], "host C++ compiler"),
        "job_derivation_sha256": _digest(
            raw_core["job_derivation_sha256"], "job derivation"
        ),
        "nvcc": _tool(raw_core["nvcc"], "NVCC"),
        "python": _tool(raw_core["python"], "Python runtime"),
        "source_identity_sha256": source_identity,
    }
    if core["build_argv_sha256"] != EXPECTED_BUILD_ARGV_SHA256:
        raise GoldbachBuildAdmissionError("admitted build argv derivation changed")
    if core["build_environment_sha256"] != EXPECTED_BUILD_ENVIRONMENT_SHA256:
        raise GoldbachBuildAdmissionError(
            "admitted build environment derivation changed"
        )
    if core["job_derivation_sha256"] != EXPECTED_JOB_DERIVATION_SHA256:
        raise GoldbachBuildAdmissionError("admitted measured-job derivation changed")

    raw_artifacts = _exact(
        top["expected_artifacts"], _ARTIFACT_FIELDS, "expected H100 artifacts"
    )
    expected_artifacts = {
        key: _digest(raw_artifacts[key], f"expected {key}")
        for key in sorted(_ARTIFACT_FIELDS)
    }
    raw_deployment = _exact(
        top["deployment"], _DEPLOYMENT_FIELDS, "admitted H100 deployment"
    )
    image_reference = _text(
        raw_deployment["immutable_image_reference"],
        "immutable Azure image reference",
    )
    if AZURE_IMAGE_RE.fullmatch(image_reference) is None:
        raise GoldbachBuildAdmissionError(
            "admission does not name an exact versioned Azure Compute Gallery image"
        )
    deployment = {
        "gpu_verifier": _text(raw_deployment["gpu_verifier"], "GPU verifier"),
        "immutable_image_reference": image_reference,
        "immutable_image_reference_sha256": _digest(
            raw_deployment["immutable_image_reference_sha256"],
            "immutable Azure image reference",
        ),
        "nras_url": _text(raw_deployment["nras_url"], "NRAS URL"),
        "nvidia_policy_sha256": _digest(
            raw_deployment["nvidia_policy_sha256"], "NVIDIA policy"
        ),
        "runner_policy_id": _text(
            raw_deployment["runner_policy_id"], "runner policy ID"
        ),
        "runner_policy_sha256": _digest(
            raw_deployment["runner_policy_sha256"], "runner policy"
        ),
        "runtime_image_closure_sha256": _digest(
            raw_deployment["runtime_image_closure_sha256"],
            "runtime image closure",
        ),
        "target_profile_id": _text(
            raw_deployment["target_profile_id"], "target profile ID"
        ),
        "target_profile_sha256": _digest(
            raw_deployment["target_profile_sha256"], "target profile"
        ),
        "trust_profile_id": _text(
            raw_deployment["trust_profile_id"], "trust profile ID"
        ),
        "trust_profile_sha256": _digest(
            raw_deployment["trust_profile_sha256"], "trust profile"
        ),
    }
    if deployment["target_profile_id"] != "azure_ncc40ads_h100_v5":
        raise GoldbachBuildAdmissionError("admission target profile is not Azure H100")
    if (
        deployment["trust_profile_id"]
        != "azure_ncc_sevsnp_vtpm_nvidia_cc_attested"
    ):
        raise GoldbachBuildAdmissionError(
            "admission trust profile is not the reviewed Azure H100 profile"
        )
    if deployment["immutable_image_reference_sha256"] != hashlib.sha256(
        image_reference.encode("utf-8")
    ).hexdigest():
        raise GoldbachBuildAdmissionError(
            "immutable Azure image reference digest differs"
        )
    if deployment["runtime_image_closure_sha256"] != hashlib.sha256(
        canonical_json_bytes(runtime_image_closure_value(deployment))
    ).hexdigest():
        raise GoldbachBuildAdmissionError(
            "admitted dynamic runtime/image closure digest differs"
        )

    build_identity = hashlib.sha256(canonical_json_bytes(core)).hexdigest()
    return GoldbachBuildAdmission(
        admission_sha256=file_sha256,
        admission_size_bytes=file_size,
        classification=classification,
        core=core,
        build_identity_sha256=build_identity,
        deployment=deployment,
        expected_artifacts=expected_artifacts,
    )


def verify_admitted_pin(
    admission: GoldbachBuildAdmission,
    role: str,
    pin: Mapping[str, Any],
) -> None:
    expected = admission.admitted_file(role)
    if (
        not isinstance(pin, Mapping)
        or pin.get("sha256") != expected["sha256"]
        or pin.get("size_bytes") != expected["size_bytes"]
    ):
        raise GoldbachBuildAdmissionError(
            f"{role} pin differs from the reviewed Goldbach build admission"
        )


def verify_admitted_file(
    admission: GoldbachBuildAdmission,
    role: str,
    path: Path,
) -> None:
    expected = admission.admitted_file(role)
    try:
        actual = hash_file_once(path)
    except CampaignIOError as error:
        raise GoldbachBuildAdmissionError(str(error)) from error
    if actual != (expected["sha256"], expected["size_bytes"]):
        raise GoldbachBuildAdmissionError(
            f"{role} file differs from the reviewed Goldbach build admission"
        )


def verify_runtime_identity(
    value: Any, expected_build_identity_sha256: str | None = None,
) -> dict[str, Any]:
    row = _exact(
        value,
        {"build_identity_sha256", "core", "kind", "schema_version"},
        "Goldbach runtime build identity",
    )
    if row["kind"] != RUNTIME_IDENTITY_KIND or row["schema_version"] != 1:
        raise GoldbachBuildAdmissionError(
            "unsupported Goldbach runtime identity kind/version"
        )
    # Reuse the exact core structural validation without admitting a second
    # control-file classification.  The fixed derivation hashes remain checked.
    core = _exact(row["core"], _CORE_FIELDS, "runtime Goldbach build core")
    for key in ("build_argv_sha256", "build_environment_sha256", "job_derivation_sha256"):
        _digest(core[key], f"runtime {key}")
    if core["build_argv_sha256"] != EXPECTED_BUILD_ARGV_SHA256:
        raise GoldbachBuildAdmissionError("runtime build argv derivation changed")
    if core["build_environment_sha256"] != EXPECTED_BUILD_ENVIRONMENT_SHA256:
        raise GoldbachBuildAdmissionError(
            "runtime build environment derivation changed"
        )
    if core["job_derivation_sha256"] != EXPECTED_JOB_DERIVATION_SHA256:
        raise GoldbachBuildAdmissionError("runtime job derivation changed")
    if (
        _digest(core["source_identity_sha256"], "runtime source identity")
        != EXPECTED_HARDENED_SOURCE_IDENTITY_SHA256
    ):
        raise GoldbachBuildAdmissionError("runtime hardened source identity changed")
    _tool(core["python"], "runtime Python")
    _tool(core["nvcc"], "runtime NVCC")
    _tool(core["host_cxx"], "runtime host C++ compiler")
    _executable(core["executable"])
    identity = hashlib.sha256(canonical_json_bytes(core)).hexdigest()
    if row["build_identity_sha256"] != identity:
        raise GoldbachBuildAdmissionError("runtime build identity digest differs")
    if (
        expected_build_identity_sha256 is not None
        and identity != _digest(
            expected_build_identity_sha256, "expected runtime build identity"
        )
    ):
        raise GoldbachBuildAdmissionError("runtime build identity is not admitted")
    return copy.deepcopy(row)


def _normalize_algorithm_id_argv(
    argv: Any, algorithm_id: str, what: str,
) -> list[str]:
    if (
        not isinstance(argv, Sequence)
        or isinstance(argv, (str, bytes))
        or not all(isinstance(item, str) for item in argv)
    ):
        raise GoldbachBuildAdmissionError(f"{what} must be a string argv")
    result = list(argv)
    positions = [
        index for index, value in enumerate(result) if value == "--algorithm-id"
    ]
    if len(positions) != 1 or positions[0] + 1 >= len(result):
        raise GoldbachBuildAdmissionError(
            f"{what} must contain exactly one --algorithm-id value"
        )
    position = positions[0] + 1
    if result[position] != algorithm_id:
        raise GoldbachBuildAdmissionError(
            f"{what} algorithm ID differs from the signed job algorithm"
        )
    result[position] = SIGNED_ALGORITHM_ID_TOKEN
    return result


def goldbach_execution_projection(job: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact non-circular operational projection of one H100 job."""

    exact_job = _exact(job, _JOB_FIELDS, "measured Goldbach job")
    algorithm = _exact(
        exact_job["algorithm"],
        {"algorithm_id", "canonical_definition", "definition_sha256"},
        "measured Goldbach algorithm",
    )
    algorithm_id = algorithm["algorithm_id"]
    if (
        not isinstance(algorithm_id, str)
        or not algorithm_id.startswith(GOLDBACH_H100_ALGORITHM_PREFIX)
    ):
        raise GoldbachBuildAdmissionError(
            "execution projection dispatch is not a reviewed Goldbach algorithm"
        )
    projected = {
        key: copy.deepcopy(exact_job[key])
        for key in sorted(_JOB_FIELDS - {"algorithm"})
    }
    closure = _exact(
        projected["artifact_closure"],
        {"closure_kind", "files", "manifest_sha256"},
        "Goldbach artifact closure",
    )
    projected["artifact_closure"] = {
        "closure_kind": closure["closure_kind"],
        "manifest_sha256": _digest(
            closure["manifest_sha256"], "Goldbach artifact closure"
        ),
    }
    command = projected["command"]
    if not isinstance(command, dict) or "argv" not in command:
        raise GoldbachBuildAdmissionError("Goldbach command is malformed")
    command["argv"] = _normalize_algorithm_id_argv(
        command["argv"], algorithm_id, "Goldbach command"
    )
    trace = projected["work_trace_contract"]
    if not isinstance(trace, dict) or "verifier_argv" not in trace:
        raise GoldbachBuildAdmissionError(
            "Goldbach trace verifier contract is malformed"
        )
    trace["verifier_argv"] = _normalize_algorithm_id_argv(
        trace["verifier_argv"], algorithm_id, "Goldbach trace verifier"
    )
    return {
        "job": projected,
        "kind": EXECUTION_PROJECTION_KIND,
        "schema_version": SCHEMA_VERSION,
    }


def goldbach_execution_projection_bytes(job: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(goldbach_execution_projection(job))


def goldbach_execution_projection_sha256(job: Mapping[str, Any]) -> str:
    return hashlib.sha256(goldbach_execution_projection_bytes(job)).hexdigest()


__all__ = [
    "ADMISSION_KIND",
    "EXECUTION_PROJECTION_KIND",
    "EXPECTED_BUILD_ARGV_SHA256",
    "EXPECTED_BUILD_ENVIRONMENT_SHA256",
    "EXPECTED_JOB_DERIVATION_SHA256",
    "GOLDBACH_H100_ALGORITHM_PREFIX",
    "GoldbachBuildAdmission",
    "GoldbachBuildAdmissionError",
    "H100_BUILD_ARGV_TEMPLATE",
    "H100_BUILD_ENVIRONMENT",
    "JOB_DERIVATION_DEFINITION",
    "REVIEWED_PRODUCTION_ADMISSION_SHA256S",
    "RUNTIME_IDENTITY_KIND",
    "RUNTIME_IMAGE_CLOSURE_KIND",
    "RUNTIME_IMAGE_COMPONENTS",
    "SIGNED_ALGORITHM_ID_TOKEN",
    "goldbach_execution_projection",
    "goldbach_execution_projection_bytes",
    "goldbach_execution_projection_sha256",
    "load_build_admission",
    "runtime_image_closure_value",
    "verify_admitted_file",
    "verify_admitted_pin",
    "verify_runtime_identity",
    "verify_runtime_image_closure",
]
