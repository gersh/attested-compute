# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact site-pin inventory for the two confidential-computing PoC campaigns.

The Azure launch preflight reports every campaign as ``site-pin-needed``
because each checked-in site example still carries redacted or placeholder
deployment identities.  That single Boolean is not actionable: it does not say
which placeholders are Azure identities that cannot exist before a
subscription does, which are ordinary local file digests, which are key
material only the operator may produce, and which become mechanically
derivable the moment an earlier pin is settled.

Two of those distinctions only became visible by reading the consumers rather
than the examples, and both cut against the optimistic reading.  The
production measured-runner policy looks like pure repository work and is not:
the orchestrator requires it to carry the exact Compute Gallery image
reference, so it is image-bound.  The evidence verifier looks like a program
that must be written and is not: it already exists, already speaks the exact
argument list the orchestrator invokes, and already supports the CPU backend.

This module answers that question for exactly the two proof-of-concept
campaigns:

``cdem-table-abel``
    the only campaign whose Lean semantic binding is ``enabled``, and
    therefore the only one that can currently close an atom end to end.

``ramare-zuniga-lemma-6-2``
    the only small GPU campaign, sized at one confidential H100 node.

Everything here is read-only.  It reads the checked-in redacted examples, the
reviewed schemas, and the repository tree.  It never reads Azure credentials,
contacts Azure, materializes a job, or writes a site file.  In particular it
does not and cannot make a campaign launchable: producing an inventory of what
is missing is the opposite of declaring that nothing is missing.  Every
readiness and acceptance flag reported by ``tg_verifier.azure_launch_preflight``
is unchanged by this module's existence.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping

from tg_verifier import azure_launch_preflight
from tg_verifier.campaign_io import canonical_sha256, hash_file_once


SCHEMA_VERSION = 1
KIND = "sparkinterval.azure.tg.poc-site-pin-inventory.v1"

REPOSITORY_ROOT = azure_launch_preflight.REPOSITORY_ROOT

#: The two campaigns this inventory covers, with why each was chosen.
POC_CAMPAIGNS: dict[str, dict[str, str]] = {
    "cdem-table-abel": {
        "role": "step_1_confidential_cpu",
        "selection_reason": (
            "the only registered campaign whose Azure semantic binding state "
            "is 'enabled' (SignedResultCertificate.certifyCDEMTableAbel); the "
            "other ten are 'staged_disabled' and cannot close an atom"
        ),
    },
    "ramare-zuniga-lemma-6-2": {
        "role": "step_2_confidential_h100",
        "selection_reason": (
            "the only small GPU campaign: one NCC40ads_H100_v5 node, whereas "
            "the Goldbach GPU route is sized at eight nodes and the Dirichlet "
            "route carries no retained estimate"
        ),
    },
}

#: Classification vocabulary.  ``obtainable_before_subscription`` is the field
#: that actually matters for scheduling the operator's lead-time items.
PIN_CLASSES: dict[str, dict[str, Any]] = {
    "repository_derivable": {
        "obtainable_before_subscription": True,
        "owner": "repository_work",
        "definition": (
            "the value is a digest of checked-in repository content and is "
            "computed by this module now"
        ),
    },
    "build_host_derivable": {
        "obtainable_before_subscription": True,
        "owner": "repository_work",
        "definition": (
            "the value is a digest of a file on the materialization "
            "workstation; obtaining it is a local sha256sum and needs no "
            "Azure account, though it does need the named toolchain installed"
        ),
    },
    "operator_local_secret": {
        "obtainable_before_subscription": True,
        "owner": "operator_action",
        "definition": (
            "the value is a digest of key material the operator generates and "
            "holds. No Azure account is needed to produce it and it is not "
            "blocked on anything, but this repository must not produce it: "
            "committing a key an operator did not choose would be worse than "
            "leaving the pin empty"
        ),
    },
    "operator_identity_requires_subscription": {
        "obtainable_before_subscription": False,
        "owner": "operator_action",
        "definition": (
            "the value is an Azure identity or resource name that cannot be "
            "known until a subscription and the named resource exist"
        ),
    },
    "chained_after": {
        "obtainable_before_subscription": False,
        "owner": "mechanical_after_dependency",
        "definition": (
            "the value is the digest of a file produced by an earlier step; it "
            "is a mechanical sha256sum once that step is complete, and it is "
            "listed separately so it is never mistaken for an independent gap"
        ),
    },
}


def _pin(
    location: str,
    *,
    site: str,
    pin_class: str,
    value_kind: str,
    note: str,
    repository_source: str | None = None,
    depends_on: str | None = None,
) -> dict[str, Any]:
    if pin_class not in PIN_CLASSES:
        raise ValueError(f"unknown pin class: {pin_class}")
    if (pin_class == "chained_after") != (depends_on is not None):
        raise ValueError(f"chained_after requires exactly one dependency: {location}")
    return {
        "depends_on": depends_on,
        "location": location,
        "pin_class": pin_class,
        "note": note,
        "obtainable_before_subscription": PIN_CLASSES[pin_class][
            "obtainable_before_subscription"
        ],
        "owner": PIN_CLASSES[pin_class]["owner"],
        "repository_source": repository_source,
        "site_example": site,
        "value_kind": value_kind,
    }


_CPU_SITE = "azure_cpu_portfolio_materializer_site.redacted.json"
_CDEM_SITE = "azure_cpu_cdem_artifact_terminal_materializer_site.redacted.json"
_R2STAR_SITE = "azure_h100_r2star_materializer_site.redacted.json"


#: Reviewed classification of every redaction marker the launch preflight
#: reports for the two PoC campaigns.  ``build_inventory`` fails closed if the
#: checked-in examples ever carry a marker this table does not cover, or if
#: this table names a marker the examples no longer carry.  The table therefore
#: cannot silently drift away from the preflight it explains.
REVIEWED_PINS: tuple[dict[str, Any], ...] = (
    # --- examples/trusted-compute/azure_cpu_portfolio_materializer_site.redacted.json
    _pin(
        "$.azure.subscription_id",
        site=_CPU_SITE,
        pin_class="operator_identity_requires_subscription",
        value_kind="Azure subscription GUID",
        note=(
            "the root identity every other Azure pin hangs from; nothing else "
            "in this table that is marked operator-supplied can be obtained "
            "before this one exists"
        ),
    ),
    _pin(
        "$.azure.subnet_id",
        site=_CPU_SITE,
        pin_class="operator_identity_requires_subscription",
        value_kind=(
            "ARM resource id of a subnet: /subscriptions/<guid>/resourceGroups/"
            "<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<name>"
        ),
        note=(
            "the confidential VM is placed in an operator-owned private "
            "virtual network; the network must be created first"
        ),
    ),
    _pin(
        "$.azure.image",
        site=_CPU_SITE,
        pin_class="operator_identity_requires_subscription",
        value_kind=(
            "ARM resource id of an Azure Compute Gallery image *version*"
        ),
        note=(
            "the example is explicit that this must be an exact private "
            "compute-gallery image version, not a marketplace URN: the guest "
            "image is inside the measured boundary, so it has to be an "
            "immutable version the operator publishes and can re-reference"
        ),
    ),
    _pin(
        "$.azure.ssh_public_key.sha256",
        site=_CPU_SITE,
        pin_class="operator_local_secret",
        value_kind="sha256 of the operator SSH public key file",
        note=(
            "generating the key pair is a local ssh-keygen and needs no Azure "
            "account, so this pin is not on the subscription critical path. "
            "It is nonetheless the operator's action and not this "
            "repository's: the private half is a credential the operator must "
            "choose and hold."
        ),
    ),
    _pin(
        "$.managed_hsm.key_id",
        site=_CPU_SITE,
        pin_class="operator_identity_requires_subscription",
        value_kind="Managed HSM key identifier",
        note=(
            "requires a provisioned Managed HSM pool; that pool is billed "
            "continuously, not per run, and is the single largest fixed cost "
            "of the confidential path"
        ),
    ),
    _pin(
        "$.managed_hsm.key_uri",
        site=_CPU_SITE,
        pin_class="operator_identity_requires_subscription",
        value_kind=(
            "Managed HSM key *version* URI: "
            "https://<pool>.managedhsm.azure.net/keys/<name>/<32-hex-version>"
        ),
        note=(
            "the trailing version is minted by the HSM when the key is "
            "created; because this repository pins the key version immutably, "
            "rotating the key invalidates previously issued receipts, which is "
            "why the pool cannot be deprovisioned between runs"
        ),
    ),
    _pin(
        "$.managed_hsm.public_key.sha256",
        site=_CPU_SITE,
        pin_class="chained_after",
        depends_on="$.managed_hsm.key_uri",
        value_kind="sha256 of the PEM public key exported from the HSM",
        note="a local sha256sum once the HSM key version exists",
    ),
    _pin(
        "$.managed_hsm.key_manifest.sha256",
        site=_CPU_SITE,
        pin_class="chained_after",
        depends_on="$.managed_hsm.public_key.sha256",
        value_kind="sha256 of the trusted-compute verifier key manifest",
        note=(
            "the repository ships a bootstrap manifest at "
            "profiles/verifier_keys/trusted_compute_keys.json whose digest is "
            "reported below; a production run needs the same structure "
            "carrying the production HSM key, so the digest changes"
        ),
        repository_source="profiles/verifier_keys/trusted_compute_keys.json",
    ),
    _pin(
        "$.policies.runner.sha256",
        site=_CPU_SITE,
        pin_class="chained_after",
        depends_on="$.azure.image",
        value_kind=(
            "sha256 of a measured-runner policy whose classification is "
            "'production', whose production_ready is true, whose policy_id is "
            "sparkinterval.runner.azure-cpu.production.v1, and whose "
            "required_claims cover the seven production claims"
        ),
        note=(
            "this looks like pure repository work and is not. The orchestrator "
            "requires the policy to carry immutable_image_reference equal to "
            "the exact $.azure.image value, and "
            "immutable_image_reference_sha256 equal to the SHA-256 of that "
            "string, so the file is bound to an image that does not exist "
            "before the subscription does. Its full required shape and the "
            "seven required claims are reported under "
            "repository_derivable_values.operator_policy_templates, which is "
            "everything this repository can honestly supply."
        ),
        repository_source="profiles/measured_runner/development_challenge_first_v1.json",
    ),
    _pin(
        "$.policies.composite_appraisal.sha256",
        site=_CPU_SITE,
        pin_class="chained_after",
        depends_on="$.worker.maa_attestation_url",
        value_kind=(
            "sha256 of a canonical appraisal policy of kind "
            "sparkinterval_azure_evidence_appraisal_policy"
        ),
        note=(
            "the policy's maa_accepted_issuer must equal the issuer derived "
            "from its own maa_attestation_url, so it cannot be finalized "
            "before that endpoint is chosen. It additionally pins an external "
            "Azure appraiser executable and its policy by path and digest, "
            "neither of which is vendored here. For the CPU backend "
            "nvidia_appraiser must be exactly null. Required key sets are "
            "reported under repository_derivable_values."
        ),
    ),
    _pin(
        "$.policies.evidence_verifier.sha256",
        site=_CPU_SITE,
        pin_class="build_host_derivable",
        value_kind=(
            "sha256 of the installed, executable evidence verifier at the "
            "pinned operator path"
        ),
        note=(
            "this is not a program that has to be written. "
            "attestation/verify_azure_ncc_evidence.py already implements "
            "exactly the argument list the orchestrator invokes "
            "(--evidence-pack, --policy, --backend, --expected-challenge-file, "
            "--expected-start-challenge-sha256, "
            "--expected-result-binding-sha256) and already handles the "
            "azure_sevsnp_cpu backend. The pin is the digest of the operator's "
            "installed copy; if it is installed verbatim, the value is the "
            "repository digest reported under repository_derivable_values. "
            "See the silent requirement about that file's stale source pin."
        ),
        repository_source="attestation/verify_azure_ncc_evidence.py",
    ),
    _pin(
        "$.worker.maa_attestation_url",
        site=_CPU_SITE,
        pin_class="operator_identity_requires_subscription",
        value_kind="Microsoft Azure Attestation SevSnpVm endpoint URL",
        note=(
            "Azure publishes shared regional attestation endpoints whose URLs "
            "are well known and need no subscription to name. Whether the "
            "composite appraisal policy above may accept a shared provider, or "
            "must pin a dedicated provider in the operator's own tenant, is a "
            "policy decision this repository has not recorded and that cannot "
            "be settled here without an account."
        ),
    ),
    # --- examples/trusted-compute/azure_cpu_cdem_artifact_terminal_materializer_site.redacted.json
    _pin(
        "$.base_site.sha256",
        site=_CDEM_SITE,
        pin_class="chained_after",
        depends_on="$.azure.subscription_id",
        value_kind="sha256 of the finalized CPU portfolio site file",
        note=(
            "a local sha256sum of the file whose twelve pins are listed above; "
            "it is last, not first, and it changes whenever any of them does"
        ),
    ),
    _pin(
        "$.cdem.producer_certificate_archive.sha256",
        site=_CDEM_SITE,
        pin_class="chained_after",
        depends_on="$.base_site.sha256",
        value_kind="sha256 of the CDEM producer certificate tar handoff",
        note=(
            "produced by the preceding CDEM producer run, not by the operator "
            "and not by this repository; the local OpenMP producer took "
            "86.574 s, so this is a short step, but it is still a step that "
            "has to happen before the artifact-terminal job can be pinned"
        ),
    ),
    # --- examples/trusted-compute/azure_h100_r2star_materializer_site.redacted.json
    _pin(
        "$.base_campaign.sha256",
        site=_R2STAR_SITE,
        pin_class="chained_after",
        depends_on="$.azure.subscription_id",
        value_kind=(
            "sha256 of a canonical H100 orchestrator campaign config"
        ),
        note=(
            "the file's required key set is fixed by "
            "azure/h100_production_orchestrator.py CONFIG_KEYS and is reported "
            "below, so its shape is repository-derivable now; its contents "
            "repeat the same Azure and Managed HSM identities as the CPU site, "
            "so it cannot be finalized before those exist"
        ),
    ),
    _pin(
        "$.build.host_cxx.sha256",
        site=_R2STAR_SITE,
        pin_class="build_host_derivable",
        value_kind="sha256 of the host C++ compiler binary (example /usr/bin/g++)",
        note=(
            "the R2Star materializer runs a closed CUDA build with exactly "
            "this compiler, so the digest describes the materialization "
            "workstation, not the confidential VM; it needs no Azure account"
        ),
    ),
    _pin(
        "$.build.nvcc.sha256",
        site=_R2STAR_SITE,
        pin_class="build_host_derivable",
        value_kind="sha256 of the nvcc binary (example /usr/local/cuda/bin/nvcc)",
        note=(
            "needs a CUDA toolkit installed on the materialization "
            "workstation; it does not need a GPU and it does not need Azure"
        ),
    ),
    _pin(
        "$.build.python.sha256",
        site=_R2STAR_SITE,
        pin_class="build_host_derivable",
        value_kind="sha256 of the Python interpreter (example /usr/bin/python3)",
        note="a local sha256sum on the materialization workstation",
    ),
)


#: Requirements that block a launch but that the preflight's redaction scan
#: cannot see, because the checked-in example already carries a concrete,
#: non-placeholder value that is nonetheless wrong, unsatisfiable, or merely
#: unreviewed for a production run.  These are the traps: an operator who
#: cleared all eighteen markers above would still not be able to launch.
SILENT_REQUIREMENTS: tuple[dict[str, Any], ...] = (
    {
        "campaign_id": "cdem-table-abel",
        "location": "$.policies.evidence_verifier",
        "owner": "repository_work",
        "requirement": (
            "attestation/verify_azure_ncc_evidence.py must import; on this "
            "branch it does not, because its pinned digest for "
            "tg_verifier/goldbach_gpu_campaign.py is stale"
        ),
        "why_invisible": (
            "no gate in this repository executes the evidence verifier. It "
            "self-pins the digests of eight measured modules and raises at "
            "import time if any differs; seven currently match and one does "
            "not, so the CPU appraisal step of the proof of concept would fail "
            "on first contact. Re-pinning is a review decision about the "
            "attestation trust surface and is deliberately not done here."
        ),
        "source": "attestation/verify_azure_ncc_evidence.py:43-81",
    },
    {
        "campaign_id": "ramare-zuniga-lemma-6-2",
        "location": "$.build.boost_include_root",
        "owner": "operator_action",
        "requirement": (
            "must be a Boost 1.83.0 header tree whose reviewed identity is "
            "exactly 15653 headers, 149594508 bytes, tree sha256 "
            "7ecf4808a419bd489f930c685320cf2745e46c6bc5591122c26773386214d8e2"
        ),
        "why_invisible": (
            "the example carries a plausible concrete path "
            "(/srv/sparkinterval-source/boost-1.83.0), so no redaction marker "
            "fires, but the tree it must point at is not vendored in this "
            "repository and must be fetched and verified separately"
        ),
        "source": "tg_verifier/azure_h100_r2star_materializer.py:96-100",
    },
    {
        "campaign_id": "cdem-table-abel",
        "location": "$.azure.sku",
        "owner": "operator_action",
        "requirement": (
            "review whether Standard_EC96as_v6 is intended; the retained "
            "sizing model prices Standard_DC96as_v6"
        ),
        "why_invisible": (
            "both are real confidential SKUs and neither is redacted, so the "
            "marker scan is silent, but the checked-in example names the "
            "memory-optimized EC96as_v6 while "
            "tg_verifier/azure_production_sizing.py prices the "
            "general-purpose DC96as_v6 at $4.358 on demand and $0.805358 "
            "spot. One of the two is wrong and this repository does not say "
            "which."
        ),
        "source": (
            "examples/trusted-compute/"
            "azure_cpu_portfolio_materializer_site.redacted.json vs "
            "tg_verifier/azure_production_sizing.py:64"
        ),
    },
    {
        "campaign_id": "cdem-table-abel",
        "location": "$.azure.nodes",
        "owner": "repository_work",
        "requirement": "must be exactly 1",
        "why_invisible": (
            "the example already says 1, so nothing fires; recorded here "
            "because the constraint is a hard orchestrator assertion and an "
            "operator scaling the file up would fail closed at deploy time"
        ),
        "source": "azure/cpu_production_orchestrator.py:755",
    },
    {
        "campaign_id": "cdem-table-abel",
        "location": "$.cdem.challenge_ttl_seconds",
        "owner": "operator_action",
        "requirement": (
            "the reviewed schema admits only 140401..604800 seconds, and the "
            "orchestrator separately requires ttl > job timeout + 3 h of "
            "evidence-collection margin"
        ),
        "why_invisible": (
            "the example's 172800 is inside the band, so no marker fires. It "
            "is worth stating anyway because the CDEM compute is about 87 "
            "seconds: the challenge must stay valid for at least 39 hours for "
            "a job that runs for a minute and a half, so the attestation "
            "freshness window, not the compute, sizes the operator's "
            "scheduling."
        ),
        "source": (
            "schemas/azure-cpu-cdem-artifact-terminal-materializer-site."
            "schema.json and azure/cpu_production_orchestrator.py:853-857"
        ),
    },
    {
        "campaign_id": "cdem-table-abel",
        "location": "$.output_root",
        "owner": "operator_action",
        "requirement": (
            "must not already exist and must resolve outside the repository"
        ),
        "why_invisible": (
            "a concrete path is present, so no marker fires; the freshness "
            "check happens only when the materializer runs"
        ),
        "source": "tg_verifier/azure_cpu_portfolio_materializer.py:165-167",
    },
    {
        "campaign_id": "ramare-zuniga-lemma-6-2",
        "location": "$.output_root",
        "owner": "operator_action",
        "requirement": "must resolve outside the repository",
        "why_invisible": "same as above",
        "source": "tg_verifier/azure_h100_r2star_materializer.py:209-217",
    },
)


#: Mirrored from attestation/verify_azure_ncc_evidence.py and
#: azure/cpu_production_orchestrator.py so the inventory can report the exact
#: required shape of the two operator policy files without importing a module
#: that self-pins its dependencies and may refuse to load.
_COMPOSITE_POLICY_KEYS = frozenset(
    {"allowed_backends", "azure_appraiser", "kind", "nvidia_appraiser", "schema_version"}
)
_AZURE_APPRAISER_POLICY_KEYS = frozenset(
    {
        "executable_path",
        "executable_sha256",
        "maa_accepted_audience",
        "maa_accepted_issuer",
        "maa_accepted_provider",
        "maa_attestation_url",
        "policy_path",
        "policy_sha256",
        "timeout_seconds",
    }
)
_PRODUCTION_RUNNER_CLAIMS = frozenset(
    {
        "challenge_dependent_work_trace",
        "challenge_received_before_pcr_start",
        "exact_argv_without_shell",
        "fresh_exclusive_output",
        "immutable_image_and_runtime_closure",
        "ordered_pcr23_start_and_result_extensions",
        "retained_off_vm_challenge_match",
    }
)


class PocSitePinError(RuntimeError):
    """The PoC site-pin inventory could not be built exactly."""


def _verifier_imports_cleanly() -> dict[str, Any]:
    """Report whether the evidence verifier's self-pins currently hold.

    The verifier raises at import time if any pinned measured module differs.
    That check is correct and must not be relaxed here, so this only observes
    it: the inventory reports the blocker rather than working around it.
    """

    import subprocess

    try:
        completed = subprocess.run(
            [sys.executable, "attestation/verify_azure_ncc_evidence.py", "--help"],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"ok": False, "detail": str(error)}
    if completed.returncode == 0:
        return {"ok": True, "detail": None}
    tail = (completed.stderr.strip() or completed.stdout.strip()).splitlines()
    return {"ok": False, "detail": tail[-1] if tail else "nonzero --help exit"}


def _site_example_paths(campaign_id: str) -> list[str]:
    program = azure_launch_preflight._load_json(
        azure_launch_preflight.PROGRAM_READINESS_PATH,
        "external-program readiness inventory",
    )
    rows = azure_launch_preflight._rows_by_campaign(
        program, "external-program readiness"
    )
    row = rows.get(campaign_id)
    if row is None:
        raise PocSitePinError(f"unknown campaign: {campaign_id}")
    return list(row["azure"]["site_examples"])


def _observed_markers(relative: str) -> list[str]:
    """Return marker locations using the launch preflight's own scanner."""

    value = azure_launch_preflight._load_json(
        REPOSITORY_ROOT / relative, f"site example {relative}"
    )
    return [
        marker.rsplit("=", 1)[0]
        for marker in azure_launch_preflight._redaction_markers(value)
    ]


def _repository_file_rows(relatives: Iterable[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in sorted(relatives):
        path = REPOSITORY_ROOT / relative
        if not path.is_file():
            raise PocSitePinError(f"reviewed workload source is absent: {relative}")
        digest, size = hash_file_once(path)
        rows.append({"path": relative, "sha256": digest, "size_bytes": size})
    return rows


def _repository_derivable_values() -> dict[str, Any]:
    """Compute every value this repository can settle without an account."""

    from tg_verifier.azure_cpu_workload_factory import CDEM_FACTORY
    from tg_verifier.azure_h100_r2star_workload_factory import SOURCE_PATHS

    import sys

    for directory in (REPOSITORY_ROOT / "azure",):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    import cpu_production_orchestrator as cpu_operator  # noqa: E402
    import h100_production_orchestrator as h100_operator  # noqa: E402

    cdem_rows = _repository_file_rows(CDEM_FACTORY.source_paths)
    r2star_rows = _repository_file_rows(SOURCE_PATHS)
    key_manifest = REPOSITORY_ROOT / "profiles/verifier_keys/trusted_compute_keys.json"
    key_digest, key_size = hash_file_once(key_manifest)
    runner_profile = (
        REPOSITORY_ROOT / "profiles/measured_runner/development_challenge_first_v1.json"
    )
    runner_digest, runner_size = hash_file_once(runner_profile)

    verifier = REPOSITORY_ROOT / "attestation/verify_azure_ncc_evidence.py"
    verifier_digest, verifier_size = hash_file_once(verifier)
    target_profile = REPOSITORY_ROOT / "profiles/targets/azure_sevsnp_cpu.json"
    trust_profile = (
        REPOSITORY_ROOT / "profiles/trust/azure_sevsnp_hardware_attested.json"
    )
    target_digest, target_size = hash_file_once(target_profile)
    trust_digest, trust_size = hash_file_once(trust_profile)

    return {
        "evidence_verifier_reference": {
            "argument_list": [
                "--evidence-pack",
                "--policy",
                "--backend",
                "--expected-challenge-file",
                "--expected-start-challenge-sha256",
                "--expected-result-binding-sha256",
            ],
            "executable_in_repository": os.access(verifier, os.X_OK),
            "imports_cleanly": _verifier_imports_cleanly(),
            "path": "attestation/verify_azure_ncc_evidence.py",
            "sha256": verifier_digest,
            "size_bytes": verifier_size,
            "supported_backends": ["azure_sevsnp_cpu", "azure_ncc40ads_h100_v5"],
            "what": (
                "the value $.policies.evidence_verifier.sha256 must carry if "
                "the operator installs this repository program verbatim at "
                "the pinned path"
            ),
        },
        "operator_policy_templates": {
            "composite_appraisal": {
                "azure_appraiser_required_keys": sorted(
                    _AZURE_APPRAISER_POLICY_KEYS
                ),
                "cpu_backend_constraint": (
                    "nvidia_appraiser must be exactly null for "
                    "azure_sevsnp_cpu"
                ),
                "kind": "sparkinterval_azure_evidence_appraisal_policy",
                "required_keys": sorted(_COMPOSITE_POLICY_KEYS),
                "schema_version": 1,
            },
            "measured_runner": {
                "image_bound_keys": [
                    "immutable_image_reference",
                    "immutable_image_reference_sha256",
                ],
                "kind": "sparkinterval_measured_runner_policy",
                "required_claims": sorted(_PRODUCTION_RUNNER_CLAIMS),
                "required_classification": "production",
                "required_policy_id": "sparkinterval.runner.azure-cpu.production.v1",
                "schema_version": 1,
            },
            "what": (
                "the exact shapes the two policy files must have. This "
                "repository can supply the shapes and cannot supply the "
                "values, because both files are bound to identities that do "
                "not exist before the subscription does."
            ),
        },
        "sevsnp_cpu_profiles": {
            "target": {
                "path": "profiles/targets/azure_sevsnp_cpu.json",
                "sha256": target_digest,
                "size_bytes": target_size,
            },
            "trust": {
                "path": "profiles/trust/azure_sevsnp_hardware_attested.json",
                "sha256": trust_digest,
                "size_bytes": trust_size,
            },
            "what": (
                "the target and trust profile digests the materializer places "
                "in the transcript appraisal policy's allowlists; they are "
                "repository content and are settled now"
            ),
        },
        "cdem_table_abel_reviewed_source_closure": {
            "file_count": len(cdem_rows),
            "files": cdem_rows,
            "rows_sha256": canonical_sha256(cdem_rows),
            "total_bytes": sum(row["size_bytes"] for row in cdem_rows),
            "what": (
                "the exact reviewed source files the CDEM CPU workload factory "
                "closes over; the materializer refuses to package a tree whose "
                "digests differ from the clean git repository closure, so "
                "confirming these before launch removes one whole class of "
                "late failure"
            ),
        },
        "h100_campaign_config_required_keys": sorted(h100_operator.CONFIG_KEYS),
        "cpu_campaign_config_required_keys": sorted(cpu_operator.CONFIG_KEYS),
        "cpu_site_azure_required_keys": sorted(cpu_operator.AZURE_KEYS),
        "cpu_site_managed_hsm_required_keys": sorted(cpu_operator.HSM_KEYS),
        "operator_output_required_keys": sorted(cpu_operator.OUTPUT_KEYS),
        "bootstrap_verifier_key_manifest": {
            "path": "profiles/verifier_keys/trusted_compute_keys.json",
            "sha256": key_digest,
            "size_bytes": key_size,
            "what": (
                "candidate value for $.managed_hsm.key_manifest.sha256 only if "
                "the operator deliberately runs against the checked-in "
                "bootstrap key; a production run needs the production HSM key "
                "and therefore a different digest"
            ),
        },
        "development_runner_policy": {
            "path": "profiles/measured_runner/development_challenge_first_v1.json",
            "sha256": runner_digest,
            "size_bytes": runner_size,
            "what": (
                "the only measured-runner policy in this repository; it is NOT "
                "a valid value for $.policies.runner.sha256 because that pin "
                "requires classification 'production'"
            ),
        },
        "ramare_zuniga_reviewed_source_closure": {
            "file_count": len(r2star_rows),
            "files": r2star_rows,
            "rows_sha256": canonical_sha256(r2star_rows),
            "total_bytes": sum(row["size_bytes"] for row in r2star_rows),
            "what": (
                "the exact reviewed source files the R2Star H100 workload "
                "factory closes over; same reasoning as the CDEM closure above"
            ),
        },
    }


def build_inventory() -> dict[str, Any]:
    """Return the exact placeholder inventory for the two PoC campaigns.

    Fails closed if the checked-in site examples and the reviewed
    classification table have drifted apart in either direction.
    """

    by_site: dict[str, list[dict[str, Any]]] = {}
    for pin in REVIEWED_PINS:
        by_site.setdefault(pin["site_example"], []).append(pin)

    campaigns: list[dict[str, Any]] = []
    reviewed_locations: set[tuple[str, str]] = set()
    observed_locations: set[tuple[str, str]] = set()

    for campaign_id, meta in POC_CAMPAIGNS.items():
        site_relatives = _site_example_paths(campaign_id)
        sites: list[dict[str, Any]] = []
        for relative in site_relatives:
            name = Path(relative).name
            observed = _observed_markers(relative)
            reviewed = by_site.get(name, [])
            observed_locations.update((name, location) for location in observed)
            reviewed_locations.update((name, pin["location"]) for pin in reviewed)
            sites.append(
                {
                    "example": relative,
                    "marker_count": len(observed),
                    "pins": sorted(reviewed, key=lambda row: row["location"]),
                    "schema": (
                        "schemas/"
                        + azure_launch_preflight.SITE_SCHEMA_BY_EXAMPLE[name]
                    ),
                }
            )
        pins = [pin for site in sites for pin in site["pins"]]
        campaigns.append(
            {
                "campaign_id": campaign_id,
                "pin_count": len(pins),
                "pins_blocked_on_subscription": sum(
                    pin["obtainable_before_subscription"] is False for pin in pins
                ),
                "pins_obtainable_now": sum(
                    pin["obtainable_before_subscription"] is True for pin in pins
                ),
                "role": meta["role"],
                "selection_reason": meta["selection_reason"],
                "silent_requirements": [
                    row
                    for row in SILENT_REQUIREMENTS
                    if row["campaign_id"] == campaign_id
                ],
                "site_examples": sites,
            }
        )

    if reviewed_locations != observed_locations:
        missing = sorted(observed_locations - reviewed_locations)
        stale = sorted(reviewed_locations - observed_locations)
        raise PocSitePinError(
            "the reviewed pin table and the checked-in site examples have "
            f"drifted (unclassified={missing}, stale={stale})"
        )

    all_pins = [pin for campaign in campaigns for site in campaign["site_examples"]
                for pin in site["pins"]]
    by_class: dict[str, int] = {name: 0 for name in PIN_CLASSES}
    for pin in all_pins:
        by_class[pin["pin_class"]] += 1

    return {
        "accepted": False,
        "campaigns": campaigns,
        "classification": (
            "read_only_site_pin_inventory_not_a_site_configuration_and_not_"
            "launch_authorization"
        ),
        "kind": KIND,
        "nonclaims": [
            "No Azure resource was inspected, created, or changed.",
            "No credential was read and none is required to run this tool.",
            "This inventory is not a site file and cannot be launched.",
            "No readiness or acceptance flag is altered by this report; the "
            "launch preflight still reports both campaigns as site-pin-needed.",
            "A repository-derivable digest is a source identity, not evidence "
            "that any computation ran.",
        ],
        "pin_class_definitions": PIN_CLASSES,
        "repository_derivable_values": _repository_derivable_values(),
        "schema_version": SCHEMA_VERSION,
        "summary": {
            "distinct_pin_locations": len(observed_locations),
            "pin_class_counts": by_class,
            "pins_blocked_on_subscription": sum(
                pin["obtainable_before_subscription"] is False for pin in all_pins
            ),
            "pins_obtainable_now": sum(
                pin["obtainable_before_subscription"] is True for pin in all_pins
            ),
            "silent_requirement_count": len(SILENT_REQUIREMENTS),
            "total_pins": len(all_pins),
        },
    }


__all__ = [
    "KIND",
    "PIN_CLASSES",
    "POC_CAMPAIGNS",
    "PocSitePinError",
    "REVIEWED_PINS",
    "SCHEMA_VERSION",
    "SILENT_REQUIREMENTS",
    "build_inventory",
]
