# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Exact site-pin inventory for the two confidential-computing PoC campaigns.

The Azure launch preflight reports every campaign as ``site-pin-needed``
because each checked-in site example still carries redacted or placeholder
deployment identities.  That single Boolean is not actionable: it does not say
which placeholders are Azure identities that cannot exist before a
subscription does, which are ordinary local file digests, which name an
artifact that has never been written in this repository at all, and which
become mechanically derivable the moment an earlier pin is settled.

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

import json
from pathlib import Path
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
    "repository_work_missing_artifact": {
        "obtainable_before_subscription": True,
        "owner": "repository_work",
        "definition": (
            "the pin names an artifact that does not exist anywhere in this "
            "repository yet; the artifact must be written and reviewed before "
            "its digest can be taken"
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
        pin_class="build_host_derivable",
        value_kind="sha256 of the operator SSH public key file",
        note=(
            "generating the key pair is a local ssh-keygen and needs no Azure "
            "account; only its use needs one"
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
        pin_class="repository_work_missing_artifact",
        value_kind=(
            "sha256 of a measured-runner policy whose classification is "
            "'production' and whose policy_id is "
            "sparkinterval.runner.azure-cpu.production.v1"
        ),
        note=(
            "no such file exists in this repository. The only checked-in "
            "runner policy is profiles/measured_runner/"
            "development_challenge_first_v1.json, and the CPU materializer "
            "rejects any policy pin whose classification is not exactly "
            "'production'. This is repository work and it does not need a "
            "subscription, but it does need review before it is written."
        ),
        repository_source="profiles/measured_runner/development_challenge_first_v1.json",
    ),
    _pin(
        "$.policies.composite_appraisal.sha256",
        site=_CPU_SITE,
        pin_class="repository_work_missing_artifact",
        value_kind=(
            "sha256 of a composite appraisal policy whose classification is "
            "'production' and whose policy_id is "
            "sparkinterval.composite.azure-cpu.production.v1"
        ),
        note=(
            "no such file exists in this repository. The policy states which "
            "SEV-SNP measurements, launch endorsements, and MAA issuers are "
            "accepted; it necessarily references the private image measurement "
            "and therefore cannot be finalized before the image exists, even "
            "though its structure can be written now."
        ),
    ),
    _pin(
        "$.policies.evidence_verifier.sha256",
        site=_CPU_SITE,
        pin_class="repository_work_missing_artifact",
        value_kind=(
            "sha256 of an executable program named verify-azure-cpu-evidence"
        ),
        note=(
            "no such program exists in this repository. Both orchestrators "
            "pin it as an executable file and invoke it during appraisal "
            "(azure/cpu_production_orchestrator.py:870 requires the "
            "executable bit). This is squarely repository work."
        ),
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


class PocSitePinError(RuntimeError):
    """The PoC site-pin inventory could not be built exactly."""


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

    return {
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
