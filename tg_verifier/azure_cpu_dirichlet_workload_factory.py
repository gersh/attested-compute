# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed CPU fallback factory for Platt's Dirichlet Theorem 7.1.

This is the rigorous FLINT/Arb contour fallback already exposed by the source
campaign.  It is source complete but intentionally not advertised as a
practical implementation of Platt's fast lattice/FFT computation.  In
particular, constructing a package or running a bounded sample is not evidence
for the registered source claim; only a successful complete measured run can
produce the literal ``true`` result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from tg_verifier.campaign_io import canonical_json_bytes


CAMPAIGN_ID = "platt-dirichlet-theorem-7-1"
GROUP_ID = f"{CAMPAIGN_ID}::single-job"
POSTCHECK_GROUP_ID = f"{CAMPAIGN_ID}::postcheck"
Q1_CAMPAIGN_ID = "platt-trudgian-rh-3e12"
Q1_GROUP_ID = f"{Q1_CAMPAIGN_ID}::finalize-merkle-certificate"
REGISTERED_INVOCATION = "plattDirichletTheorem71ProductionV1"
REGISTERED_ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.platt-dirichlet-theorem-7-1.v1"
)
REGISTERED_ALGORITHM_DEFINITION = (
    "sparkinterval.registered-algorithm.v1\n"
    "name=ternary-goldbach-platt-dirichlet-theorem-7-1\n"
    "producer=tools/tg_dirichlet_campaign.py+tools/tg_dirichlet_flint_backend.py\n"
    "semantics=complete-source-roster-even-and-odd-grh-verification-at-platt-heights\n"
    "source-modulus-range=[1,400000]\n"
    "q2-to-q400000-primitive-character-count=29565923837\n"
    "q1-source-campaign=platt-trudgian-rh-3e12\n"
    "source-realization=external-roster-completed-l-hardy-zero-brackets-conjugation-and-total-zero-count\n"
    "finalizer-target=azure-sevsnp-cpu-after-h100-and-cpu-branches\n"
    "output=false-or-true-with-two-branch-source-evidence"
)
REGISTERED_INPUT = (
    b'{"campaign":"platt-dirichlet-theorem-7-1",'
    b'"q1_source_campaign":"platt-trudgian-rh-3e12",'
    b'"q2_to_q400000_primitive_character_count":29565923837,'
    b'"source_modulus_lower":1,"source_modulus_upper":400000}'
)
REGISTERED_PARAMETERS: dict[str, Any] = {
    "even_height": "max(10^8/q,200+7.5*10^7/q)",
    "odd_height": "max(10^8/q,200+3.75*10^7/q)",
    "q1_source_campaign": Q1_CAMPAIGN_ID,
    "source_evidence": "PlattTheorem71SourceEvidence",
}
REGISTERED_DOMAIN: dict[str, Any] = {
    "characters": "all-primitive-dirichlet-characters",
    "claim": "platt-theorem-7-1-dirichlet-verification",
    "modulus_lower": 1,
    "modulus_upper": 400_000,
    "parity_branches": ["even", "odd"],
    "zero_imag_bound": "absolute-source-height",
    "zero_real_lower_exclusive": 0,
    "zero_real_upper_exclusive": 1,
}
REGISTERED_OUTPUT = b"true"
RUNTIME_WHEEL_PATH = (
    "runtime/python_flint-0.9.0-cp310-abi3-manylinux2014_x86_64."
    "manylinux_2_17_x86_64.whl"
)
Q1_ARCHIVE_PATH = "inputs/platt-trudgian-rh-3e12.tar"
Q1_RECEIPT_PATH = "inputs/platt-trudgian-rh-3e12-receipt.json"
PREDECESSOR_CERTIFICATE_PATH = "inputs/dirichlet-source-certificate.tar"
PREDECESSOR_RECEIPT_PATH = "inputs/dirichlet-source-receipt.json"

# This is the exact command presently retained by h100_cluster.py.  The
# measured command below replaces its workspace placeholders with immutable
# package-relative inputs; it does not weaken the source range.
PORTFOLIO_ARGV = (
    "${TG_PYTHON}",
    "${TG_REPOSITORY}/tools/tg_dirichlet_campaign.py",
    "source",
    "${TG_RUN_ROOT}/platt-dirichlet-theorem-7-1",
    "--q1-zeta-final",
    "${TG_RUN_ROOT}/platt-trudgian-rh-3e12/final.json",
    "--characters-per-chunk",
    "1",
)
POSTCHECK_PORTFOLIO_ARGV = (
    "${TG_PYTHON}",
    "${TG_REPOSITORY}/tools/tg_dirichlet_campaign.py",
    "verify-source",
    "${TG_RUN_ROOT}/platt-dirichlet-theorem-7-1",
    "--q1-zeta-final",
    "${TG_RUN_ROOT}/platt-trudgian-rh-3e12/final.json",
    "--registered-result-output",
    "${TG_RUN_ROOT}/platt-dirichlet-theorem-7-1/registered-result.txt",
)

FALLBACK_SOURCE_PATHS = (
    "tools/tg_dirichlet_azure_measured_workload.py",
    "tools/tg_dirichlet_campaign.py",
    "tools/tg_dirichlet_flint_backend.py",
    "tools/create_run_bundle.py",
    "tools/fetch_flint_platt.py",
    "tools/fetch_python_flint.py",
    "tools/generate_trusted_compute_lean.py",
    "tools/local_operator_signature.py",
    "tools/trusted_compute_receipt.py",
    "tools/verify_run_bundle.py",
    "tg_verifier/campaign_io.py",
    "tg_verifier/dirichlet_campaign.py",
    "tg_verifier/numeric_corpus.py",
    "tg_verifier/platt_zeta_campaign.py",
    "tg_verifier/python_flint_runtime.py",
    "tg_verifier/sqrt218_fixed_v2_receipt.py",
    "tg_verifier/zeta_zero_campaign.py",
    "attestation/measured_run_archive.py",
    "specifications/FLINT_3_6_PLATT_UPSTREAM.json",
    "specifications/PYTHON_FLINT_0_9_UPSTREAM.json",
    "profiles/verifier_keys/sparkinterval-bootstrap-rsa3072-2026-07-public.pem",
    "profiles/verifier_keys/trusted_compute_keys.json",
    "profiles/targets/azure_sevsnp_cpu.json",
    "profiles/trust/azure_sevsnp_hardware_attested.json",
)

MEASURED_WORKLOAD_IMPORT_PATHS = (
    "tools/tg_dirichlet_booker_smallq_semantic_reducer.py",
    "tg_verifier/dirichlet_allchars_stage.py",
    "tg_verifier/dirichlet_booker_smallq.py",
    "tg_verifier/dirichlet_booker_smallq_certified.py",
    "tg_verifier/dirichlet_booker_smallq_compact_v3.py",
    "tg_verifier/dirichlet_booker_smallq_factored.py",
    "tg_verifier/dirichlet_booker_smallq_output_stream.py",
    "tg_verifier/dirichlet_booker_smallq_packed_stream_v1.py",
    "tg_verifier/dirichlet_booker_smallq_semantic_reducer.py",
    "tg_verifier/dirichlet_compact_state_streaming_v3.py",
    "tg_verifier/dirichlet_fused_stage.py",
    "tg_verifier/dirichlet_largeq_batch.py",
    "tg_verifier/dirichlet_largeq_pipeline.py",
    "tg_verifier/dirichlet_lattice_cache.py",
    "tg_verifier/dirichlet_lattice_certificates.py",
    "tg_verifier/dirichlet_lattice_stage.py",
    "tg_verifier/dirichlet_recovery_seeds.py",
    "tg_verifier/dirichlet_residue_composition.py",
    "tg_verifier/dirichlet_root_catalog.py",
    "tg_verifier/dirichlet_root_number_stage.py",
    "tg_verifier/dirichlet_source_supervisor.py",
    "tg_verifier/dirichlet_stream_zero_consumer.py",
)

# The measured worker imports the packed reducer at module load even when it
# executes the historical FLINT fallback.  Both packages must therefore carry
# this exact Python import closure; otherwise a source-only guest fails before
# argument parsing.  The H100 closure below adds only its runner/gate inputs.
SOURCE_PATHS = tuple(
    dict.fromkeys((*FALLBACK_SOURCE_PATHS, *MEASURED_WORKLOAD_IMPORT_PATHS))
)

PACKED_SOURCE_PATHS = tuple(
    dict.fromkeys(
        (
            *SOURCE_PATHS,
            "attestation/azure_h100_pre_run_gate.py",
            "gpu/include/sparkinterval/sha256.hpp",
            "gpu/include/sparkinterval/tg_dirichlet_booker_smallq_certified.hpp",
            "gpu/include/sparkinterval/tg_dirichlet_booker_smallq.hpp",
            "gpu/include/sparkinterval/tg_dirichlet_strict_sign_pack.cuh",
            "gpu/platform/h100/h100_tg_dirichlet_booker_smallq_certified.cu",
            "profiles/targets/azure_ncc40ads_h100_v5.json",
            "profiles/trust/azure_ncc_sevsnp_vtpm_nvidia_cc_attested.json",
        )
    )
)

PACKED_PHASE_ALGORITHM_ID = (
    "sparkinterval.tg.dirichlet.smallq-packed-compact-phase.v1"
)
PACKED_PHASE_ALGORITHM_DEFINITION = (
    "sparkinterval.azure-operational-algorithm.v1\n"
    "campaign=platt-dirichlet-theorem-7-1\n"
    "phase=smallq-packed-compact-v1\n"
    "transport=TGDBSPK1-to-TGDCSB03\n"
    "packing-location=manifest-bound\n"
    "output=canonical-operational-result-with-retained-compact-state\n"
    "source-admission=false"
)
PACKED_INPUT_KIND = "sparkinterval.azure.dirichlet-smallq-packed-inputs.v1"
PACKED_PACKING_MODE = "tgdbspk1_strict_sign_v1"
PACKED_HOST_LOCATION = "runner_host_after_full_disk_d2h_v1"
PACKED_DEVICE_LOCATION = "runner_device_after_full_dft_before_d2h_v1"
PACKED_LOCATIONS = frozenset(
    {PACKED_HOST_LOCATION, PACKED_DEVICE_LOCATION}
)
PACKED_RUNNER_PATH = (
    "artifacts/sparkinterval-h100-tg-dirichlet-booker-smallq-certified"
)
PACKED_RUNNER_SOURCE_PATH = (
    "source/gpu/platform/h100/"
    "h100_tg_dirichlet_booker_smallq_certified.cu"
)
PACKED_PLAN_PATH = "inputs/dirichlet-smallq/plan.bin"
PACKED_BATCH_DIRECTORY = "inputs/dirichlet-smallq/batches"
PACKED_CONTROL_PATH = "inputs/dirichlet-smallq/time-tail-control.bin"
PACKED_CONTROL_RECEIPT_PATH = (
    "inputs/dirichlet-smallq/time-tail-control-receipt.json"
)
PACKED_PINSET_PATH = "inputs/dirichlet-smallq/compact-v3-pinset.json"
PACKED_PREDECESSOR_RECEIPT_PATH = (
    "inputs/dirichlet-smallq/input-closure-receipt.json"
)
PACKED_WORK_PATH = "work/platt-dirichlet-theorem-7-1/smallq-packed"
PACKED_TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.dirichlet-smallq-packed.v1\n"
    "initial=SHA256(initial-domain || challenge-nonce || job-binding || input-manifest-sha256)\n"
    "step-0=SHA256(step-domain || previous || predecessor-receipt-file-sha256 || predecessor-receipt-sha256 || artifact-roster-sha256)\n"
    "step-1=SHA256(step-domain || previous || runner-sha256 || runner-source-sha256 || pinset-sha256 || source-binding-sha256)\n"
    "step-2=SHA256(step-domain || previous || terminal-packed-stream-sha256 || compact-state-sha256 || compact-receipt-file-sha256 || compact-receipt-sha256)\n"
    "step-3=SHA256(step-domain || previous || runner-stderr-sha256 || operational-result-sha256)\n"
    "verification=full-compact-state-structural-replay-without-dft-source-multiplicity-or-turing-admission"
)


def _command(mode: str) -> tuple[str, ...]:
    return (
        "artifacts/python3",
        "-I",
        "tools/tg_dirichlet_azure_measured_workload.py",
        mode,
        "--algorithm-id",
        REGISTERED_ALGORITHM_ID,
        "--challenge",
        "@challenge@",
        "--job-binding",
        "@job_binding@",
        "--input",
        "@input@",
        "--output",
        "@output@",
        "--trace",
        "@trace@",
        "--wheel",
        RUNTIME_WHEEL_PATH,
        "--q1-archive",
        Q1_ARCHIVE_PATH,
        "--q1-receipt",
        Q1_RECEIPT_PATH,
        "--work",
        "work/platt-dirichlet-theorem-7-1",
    )


def _postcheck_command(mode: str) -> tuple[str, ...]:
    return (
        "artifacts/python3",
        "-I",
        "tools/tg_dirichlet_azure_measured_workload.py",
        mode,
        "--algorithm-id",
        REGISTERED_ALGORITHM_ID,
        "--challenge",
        "@challenge@",
        "--job-binding",
        "@job_binding@",
        "--input",
        "@input@",
        "--output",
        "@output@",
        "--trace",
        "@trace@",
        "--wheel",
        RUNTIME_WHEEL_PATH,
        "--predecessor-certificate",
        PREDECESSOR_CERTIFICATE_PATH,
        "--predecessor-receipt",
        PREDECESSOR_RECEIPT_PATH,
        "--work",
        "work/platt-dirichlet-theorem-7-1-postcheck",
    )


@dataclass(frozen=True)
class DirichletCPUWorkloadFactory:
    factory_id: str = "platt_dirichlet_full_source_flint_x86_cpu_v1"
    group_id: str = GROUP_ID
    registered_invocation: str = REGISTERED_INVOCATION
    portfolio_argv: tuple[str, ...] = PORTFOLIO_ARGV
    algorithm_id: str = REGISTERED_ALGORITHM_ID
    algorithm_definition: str = REGISTERED_ALGORITHM_DEFINITION
    input_bytes: bytes = REGISTERED_INPUT
    parameters: dict[str, Any] | None = None
    domain: dict[str, Any] | None = None
    command_argv: tuple[str, ...] = _command("run")
    trace_verifier_argv: tuple[str, ...] = _command("verify-trace")
    # Azure's CPU operator caps a challenge at seven days.  This timeout makes
    # the package valid but is not an ETA: the raw-contour fallback is expected
    # to exceed it at source scale and therefore remains a readiness blocker.
    timeout_seconds: int = 6 * 24 * 60 * 60
    trace_iterations: int = 4
    output_format: str = "opaque_bytes_v1"
    output_maximum_bytes: int = 16
    source_paths: tuple[str, ...] = SOURCE_PATHS

    def __post_init__(self) -> None:
        if self.parameters is None:
            object.__setattr__(self, "parameters", dict(REGISTERED_PARAMETERS))
        if self.domain is None:
            object.__setattr__(self, "domain", dict(REGISTERED_DOMAIN))


DIRICHLET_FACTORY = DirichletCPUWorkloadFactory()


@dataclass(frozen=True)
class DirichletPostcheckCPUWorkloadFactory(DirichletCPUWorkloadFactory):
    factory_id: str = "platt_dirichlet_retained_postcheck_x86_cpu_v1"
    group_id: str = POSTCHECK_GROUP_ID
    portfolio_argv: tuple[str, ...] = POSTCHECK_PORTFOLIO_ARGV
    command_argv: tuple[str, ...] = _postcheck_command("postcheck")
    trace_verifier_argv: tuple[str, ...] = _postcheck_command(
        "verify-postcheck-trace"
    )
    timeout_seconds: int = 6 * 24 * 60 * 60
    trace_iterations: int = 4


DIRICHLET_POSTCHECK_FACTORY = DirichletPostcheckCPUWorkloadFactory()


def _packed_command(mode: str) -> tuple[str, ...]:
    return (
        "artifacts/python3",
        "-I",
        "tools/tg_dirichlet_azure_measured_workload.py",
        mode,
        "--algorithm-id",
        PACKED_PHASE_ALGORITHM_ID,
        "--challenge",
        "@challenge@",
        "--job-binding",
        "@job_binding@",
        "--input",
        "@input@",
        "--output",
        "@output@",
        "--trace",
        "@trace@",
        "--runner",
        PACKED_RUNNER_PATH,
        "--runner-source",
        PACKED_RUNNER_SOURCE_PATH,
        "--plan",
        PACKED_PLAN_PATH,
        "--batch-directory",
        PACKED_BATCH_DIRECTORY,
        "--control",
        PACKED_CONTROL_PATH,
        "--control-receipt",
        PACKED_CONTROL_RECEIPT_PATH,
        "--pinset",
        PACKED_PINSET_PATH,
        "--predecessor-receipt",
        PACKED_PREDECESSOR_RECEIPT_PATH,
        "--runner-timeout-seconds",
        str(6 * 24 * 60 * 60),
        "--work",
        PACKED_WORK_PATH,
    )


@dataclass(frozen=True)
class DirichletPackedOperationalWorkloadFactory:
    """One manifest-bound, nonterminal H100 packed-sign phase."""

    factory_id: str
    q: int
    terminal: bool
    registered_invocation: None
    backend: str
    algorithm_id: str
    algorithm_definition: str
    input_bytes: bytes
    parameters: dict[str, Any]
    domain: dict[str, Any]
    command_argv: tuple[str, ...]
    trace_verifier_argv: tuple[str, ...]
    timeout_seconds: int
    trace_iterations: int
    trace_definition: str
    output_format: str
    output_maximum_bytes: int
    source_paths: tuple[str, ...]


def make_packed_phase_factory(
    manifest: Mapping[str, Any],
) -> DirichletPackedOperationalWorkloadFactory:
    """Create a measured-job identity from one authenticated input manifest.

    This is intentionally not selected by ``factory_for_portfolio_group``.
    The current public portfolio has no honest source-wide small-q input
    materialization phase yet.  A materializer may use this factory only
    after it has copied and revalidated the exact signed manifest closure.
    """

    required = {
        "artifact_roster_sha256",
        "artifacts",
        "compact_source_binding_sha256",
        "dft_arithmetic_containment_realized",
        "full_source_span",
        "kind",
        "packing_location",
        "packing_mode",
        "pinset_sha256",
        "production_ready",
        "q",
        "schema_version",
        "source_admission_enabled",
        "structural_bounded_span_kat",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != required:
        raise ValueError("packed Dirichlet factory manifest fields differ")
    q = manifest["q"]
    if (
        isinstance(q, bool)
        or not isinstance(q, int)
        or not 2 <= q <= 10_000
        or manifest["kind"] != PACKED_INPUT_KIND
        or manifest["schema_version"] != 1
        or manifest["packing_mode"] != PACKED_PACKING_MODE
        or manifest["packing_location"] not in PACKED_LOCATIONS
        or manifest["full_source_span"] is not True
        or manifest["structural_bounded_span_kat"] is not False
        or manifest["dft_arithmetic_containment_realized"] is not False
        or manifest["source_admission_enabled"] is not False
        or manifest["production_ready"] is not False
    ):
        raise ValueError(
            "packed Dirichlet factory requires an exact reviewed host/device "
            "packing location and the full-span, non-admitting mode"
        )
    for field in (
        "artifact_roster_sha256",
        "compact_source_binding_sha256",
        "pinset_sha256",
    ):
        value = manifest[field]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(f"packed Dirichlet {field} is not SHA-256")
    input_bytes = canonical_json_bytes(dict(manifest))
    device_mode = manifest["packing_location"] == PACKED_DEVICE_LOCATION
    location_label = "device" if device_mode else "host"
    parameters = {
        "artifact_roster_sha256": manifest["artifact_roster_sha256"],
        "compact_source_binding_sha256": manifest[
            "compact_source_binding_sha256"
        ],
        "packing_location": manifest["packing_location"],
        "packing_mode": manifest["packing_mode"],
        "pinset_sha256": manifest["pinset_sha256"],
        "runner_packing_stage": (
            "after_full_dft_before_disk_device_to_host_copy"
            if device_mode
            else "after_full_disk_device_to_host_copy"
        ),
    }
    domain = {
        "campaign": CAMPAIGN_ID,
        "full_source_span": True,
        "packing_location": manifest["packing_location"],
        "q": q,
        "semantic_class": "operational_compact_state_only",
        "source_admission_enabled": False,
    }
    return DirichletPackedOperationalWorkloadFactory(
        factory_id=(
            f"platt_dirichlet_smallq_packed_q{q}_h100_"
            f"{location_label}_v1"
        ),
        q=q,
        terminal=False,
        registered_invocation=None,
        backend="azure_ncc40ads_h100_v5",
        algorithm_id=PACKED_PHASE_ALGORITHM_ID,
        algorithm_definition=PACKED_PHASE_ALGORITHM_DEFINITION,
        input_bytes=input_bytes,
        parameters=parameters,
        domain=domain,
        command_argv=_packed_command("run-packed-smallq"),
        trace_verifier_argv=_packed_command(
            "verify-packed-smallq-trace"
        ),
        timeout_seconds=6 * 24 * 60 * 60,
        trace_iterations=4,
        trace_definition=PACKED_TRACE_DEFINITION,
        output_format="opaque_bytes_v1",
        output_maximum_bytes=1024 * 1024,
        source_paths=PACKED_SOURCE_PATHS,
    )


def factory_for_portfolio_group(
    group: Mapping[str, Any], shard_index: int = 0,
) -> DirichletCPUWorkloadFactory | None:
    if shard_index != 0:
        return None
    if group.get("group_id") == POSTCHECK_GROUP_ID:
        factory = DIRICHLET_POSTCHECK_FACTORY
        if (
            group.get("campaign_id") != CAMPAIGN_ID
            or group.get("phase_id") != "postcheck"
            or group.get("backend_class") != "cpu_exact_sidecar"
            or group.get("receipt_backend") != "azure_sevsnp_cpu"
            or group.get("owner_atom_id") != CAMPAIGN_ID
            or group.get("operator_adapter")
            != "azure/cpu_production_orchestrator.py"
            or group.get("shard_count") != 1
            or group.get("terminal") is not True
            or tuple(group.get("depends_on", ())) != (GROUP_ID,)
            or tuple(group.get("command_template", ()))
            != factory.portfolio_argv
        ):
            return None
        semantic = group.get("semantic_binding")
        if semantic is not None and (
            not isinstance(semantic, Mapping)
            or semantic.get("registered_invocation") != REGISTERED_INVOCATION
        ):
            return None
        return factory
    factory = DIRICHLET_FACTORY
    if (
        group.get("campaign_id") != CAMPAIGN_ID
        or group.get("group_id") != GROUP_ID
        or group.get("phase_id") != "single-job"
        or group.get("backend_class") != "cpu_flint_sidecar"
        or group.get("receipt_backend") != "azure_sevsnp_cpu"
        or group.get("owner_atom_id") != CAMPAIGN_ID
        or group.get("operator_adapter") != "azure/cpu_production_orchestrator.py"
        or group.get("shard_count") != 1
        # The retained portfolio adds a separately authenticated structural
        # postcheck after this source job, so the source group is nonterminal.
        or group.get("terminal") is not False
        or tuple(group.get("depends_on", ())) != (Q1_GROUP_ID,)
        or tuple(group.get("command_template", ())) != factory.portfolio_argv
    ):
        return None
    semantic = group.get("semantic_binding")
    if semantic is not None and (
        not isinstance(semantic, Mapping)
        or semantic.get("registered_invocation") != REGISTERED_INVOCATION
    ):
        return None
    return factory


def source_reviewed_materializer_available(group: Mapping[str, Any]) -> bool:
    return factory_for_portfolio_group(group, 0) is not None


def postcheck_materializer_blocker(group: Mapping[str, Any]) -> str | None:
    """Reject a near-match to the exact authenticated postcheck factory."""

    if (
        group.get("campaign_id") == CAMPAIGN_ID
        and group.get("group_id") == POSTCHECK_GROUP_ID
        and group.get("phase_id") == "postcheck"
        and group.get("backend_class") == "cpu_exact_sidecar"
        and group.get("receipt_backend") == "azure_sevsnp_cpu"
        and group.get("owner_atom_id") == CAMPAIGN_ID
        and group.get("operator_adapter") == "azure/cpu_production_orchestrator.py"
        and group.get("shard_count") == 1
        and group.get("terminal") is True
        and tuple(group.get("depends_on", ())) == (GROUP_ID,)
    ):
        if factory_for_portfolio_group(group, 0) is not None:
            return None
        return "postcheck group differs from its authenticated archive factory"
    return None


def expected_registered_hashes() -> dict[str, str]:
    canonical = lambda value: json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "algorithm_hash": hashlib.sha256(
            REGISTERED_ALGORITHM_DEFINITION.encode("utf-8")
        ).hexdigest(),
        "algorithm_id": REGISTERED_ALGORITHM_ID,
        "domain_hash": hashlib.sha256(canonical(REGISTERED_DOMAIN)).hexdigest(),
        "input_hash": hashlib.sha256(REGISTERED_INPUT).hexdigest(),
        "output_hash": hashlib.sha256(REGISTERED_OUTPUT).hexdigest(),
        "parameters_hash": hashlib.sha256(
            canonical(REGISTERED_PARAMETERS)
        ).hexdigest(),
    }


__all__ = [
    "CAMPAIGN_ID",
    "DIRICHLET_FACTORY",
    "DIRICHLET_POSTCHECK_FACTORY",
    "DirichletPackedOperationalWorkloadFactory",
    "GROUP_ID",
    "PACKED_BATCH_DIRECTORY",
    "PACKED_CONTROL_PATH",
    "PACKED_CONTROL_RECEIPT_PATH",
    "PACKED_DEVICE_LOCATION",
    "PACKED_HOST_LOCATION",
    "PACKED_INPUT_KIND",
    "PACKED_LOCATIONS",
    "PACKED_PACKING_MODE",
    "PACKED_PHASE_ALGORITHM_DEFINITION",
    "PACKED_PHASE_ALGORITHM_ID",
    "PACKED_PINSET_PATH",
    "PACKED_PLAN_PATH",
    "PACKED_PREDECESSOR_RECEIPT_PATH",
    "PACKED_RUNNER_PATH",
    "PACKED_RUNNER_SOURCE_PATH",
    "PACKED_SOURCE_PATHS",
    "PACKED_TRACE_DEFINITION",
    "PACKED_WORK_PATH",
    "POSTCHECK_GROUP_ID",
    "PREDECESSOR_CERTIFICATE_PATH",
    "PREDECESSOR_RECEIPT_PATH",
    "Q1_ARCHIVE_PATH",
    "Q1_RECEIPT_PATH",
    "Q1_GROUP_ID",
    "REGISTERED_INVOCATION",
    "RUNTIME_WHEEL_PATH",
    "SOURCE_PATHS",
    "expected_registered_hashes",
    "factory_for_portfolio_group",
    "make_packed_phase_factory",
    "postcheck_materializer_blocker",
    "source_reviewed_materializer_available",
]
