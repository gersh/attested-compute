#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Preflight and deploy one Azure confidential H100 per virtual machine.

This is deliberately a small Azure CLI adapter, not an alternative cloud
control plane.  It checks subscription visibility, SKU restrictions, and both
family and regional vCPU quota before creating any resource.  Allocation is
still the only authoritative capacity check Azure exposes.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


SKU = "Standard_NCC40ads_H100_v5"
VCPUS_PER_VM = 40
GPUS_PER_VM = 1
MEMORY_GB_PER_VM = 320
H100_MEMORY_GB = 94
PUBLIC_GALLERY = "cgpuimage-db870bae-5bcf-4120-9415-b841adef61d3"
UBUNTU_2204_IMAGE = "cgpu-NCC-2204-base-image"
OFFICIAL_LATEST_IMAGE = (
    f"/CommunityGalleries/{PUBLIC_GALLERY}/Images/{UBUNTU_2204_IMAGE}/versions/latest"
)
SUPPORTED_ONBOARDING_REGIONS = ("centralus", "eastus2", "westeurope")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SUBNET_ID_RE = re.compile(
    r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/"
    r"Microsoft\.Network/virtualNetworks/[^/]+/subnets/[^/]+$",
    re.IGNORECASE,
)
MARKETPLACE_IMAGE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*:[A-Za-z0-9][A-Za-z0-9._-]*:"
    r"[A-Za-z0-9][A-Za-z0-9._-]*:[0-9]+(?:\.[0-9]+){2}$"
)
GALLERY_IMAGE_RE = re.compile(
    r"^(?:"
    r"/CommunityGalleries/[^/]+/Images/[^/]+/versions/"
    r"|/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.Compute/"
    r"galleries/[^/]+/images/[^/]+/versions/"
    r")[0-9]+(?:\.[0-9]+){2}$",
    re.IGNORECASE,
)


class AzurePlanError(RuntimeError):
    """The deployment cannot be shown to satisfy its preconditions."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalized(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _run_az(arguments: Sequence[str]) -> Any:
    command = ["az", *arguments, "--only-show-errors", "--output", "json"]
    try:
        process = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError as error:
        raise AzurePlanError("Azure CLI 'az' is not installed") from error
    except subprocess.TimeoutExpired as error:
        raise AzurePlanError(f"Azure CLI timed out: {' '.join(command)}") from error
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip() or "no diagnostic"
        raise AzurePlanError(f"Azure CLI failed ({process.returncode}): {detail}")
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise AzurePlanError("Azure CLI did not return valid JSON") from error


def _command(arguments: Sequence[str]) -> list[str]:
    return ["az", *arguments, "--only-show-errors", "--output", "json"]


def _azure_cli_version(value: Any) -> tuple[int, int, int]:
    if not isinstance(value, dict) or not isinstance(value.get("azure-cli"), str):
        raise AzurePlanError("az version output lacks the azure-cli version")
    pieces = value["azure-cli"].split(".")
    if len(pieces) < 3:
        raise AzurePlanError(f"malformed Azure CLI version: {value['azure-cli']!r}")
    try:
        return tuple(int(piece) for piece in pieces[:3])  # type: ignore[return-value]
    except (TypeError, ValueError) as error:
        raise AzurePlanError(f"malformed Azure CLI version: {value['azure-cli']!r}") from error


def _restriction_applies(restriction: dict[str, Any], location: str, zone: str | None) -> bool:
    info = restriction.get("restrictionInfo")
    if info is None:
        info = {}
    if not isinstance(info, dict):
        raise AzurePlanError("SKU restrictionInfo is not an object")
    raw_locations = info.get("locations") or []
    raw_zones = info.get("zones") or []
    raw_values = restriction.get("values") or []
    if any(not isinstance(items, list) for items in (raw_locations, raw_zones, raw_values)):
        raise AzurePlanError("SKU restriction locations/zones/values are not arrays")
    locations = {str(item).lower() for item in raw_locations}
    zones = {str(item) for item in raw_zones}
    values = {str(item).lower() for item in raw_values}
    if locations and location.lower() not in locations:
        return False
    if restriction.get("type") == "Zone" and zone is not None:
        return zone in zones or zone.lower() in values
    if restriction.get("type") == "Zone" and zone is None:
        # A zonal restriction does not rule out the entire region. Azure can
        # choose an unrestricted zone when no zone was requested.
        return False
    return not values or location.lower() in values or bool(locations)


def _capability_map(sku: dict[str, Any]) -> dict[str, str]:
    raw = sku.get("capabilities")
    if not isinstance(raw, list) or not raw:
        raise AzurePlanError("SKU record lacks a nonempty capabilities array")
    result: dict[str, str] = {}
    for item in raw:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("value"), str)
            or not item["name"]
            or not item["value"]
            or item["name"] in result
        ):
            raise AzurePlanError("SKU record has a malformed or duplicate capability")
        result[item["name"]] = item["value"]
    return result


def _usage_name(row: dict[str, Any]) -> str:
    name = row.get("name")
    if not isinstance(name, dict):
        raise AzurePlanError("Azure quota row name is not an object")
    return " ".join(
        str(value)
        for value in (name.get("value"), name.get("localizedValue"), row.get("localName"))
        if value
    )


def _quota_row(rows: list[dict[str, Any]], *, family: bool) -> dict[str, Any]:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise AzurePlanError("Azure quota response must be an array of objects")
    candidates: list[dict[str, Any]] = []
    for row in rows:
        normalized = _normalized(_usage_name(row))
        if family:
            if "nccads2023" in normalized or "ncch100" in normalized:
                candidates.append(row)
        elif (
            "totalregionalvcpus" in normalized
            or "totalregionalcores" in normalized
            or normalized == "cores"
        ):
            candidates.append(row)
    if not candidates and family:
        for row in rows:
            normalized = _normalized(_usage_name(row))
            if "ncc" in normalized and "family" in normalized:
                candidates.append(row)
    if len(candidates) != 1:
        category = "Standard NCCads2023 Family vCPUs" if family else "total regional vCPUs"
        names = [_usage_name(row) for row in candidates]
        raise AzurePlanError(f"could not identify one {category} quota row; candidates={names}")
    return candidates[0]


def _quota_summary(row: dict[str, Any], required: int) -> dict[str, Any]:
    current = row.get("currentValue")
    limit = row.get("limit")
    if (
        not isinstance(current, int)
        or isinstance(current, bool)
        or not isinstance(limit, int)
        or isinstance(limit, bool)
        or current < 0
        or limit < 0
        or current > limit
    ):
        raise AzurePlanError(f"invalid quota values in {_usage_name(row)!r}")
    available = limit - current
    if available < required:
        raise AzurePlanError(
            f"insufficient {_usage_name(row)}: need {required}, available {available} "
            f"(current={current}, limit={limit})"
        )
    return {
        "name": _usage_name(row),
        "current_vcpus": current,
        "limit_vcpus": limit,
        "available_vcpus": available,
        "required_vcpus": required,
    }


def preflight(
    *, subscription: str, location: str, nodes: int, zone: str | None, dry_run: bool
) -> dict[str, Any]:
    if not isinstance(nodes, int) or isinstance(nodes, bool) or nodes < 1:
        raise AzurePlanError("nodes must be positive")
    location = location.lower()
    if location not in SUPPORTED_ONBOARDING_REGIONS:
        raise AzurePlanError(
            f"{location!r} is not in Azure's published NCC onboarding region set: "
            f"{', '.join(SUPPORTED_ONBOARDING_REGIONS)}"
        )
    if zone is not None and zone not in {"1", "2", "3"}:
        raise AzurePlanError("zone must be 1, 2, or 3")
    required = nodes * VCPUS_PER_VM
    commands = {
        "azure_cli_version": _command(["version"]),
        "account": _command(["account", "show", "--subscription", subscription]),
        "sku": _command(
            [
                "vm",
                "list-skus",
                "--subscription",
                subscription,
                "--location",
                location,
                "--size",
                SKU,
                "--all",
            ]
        ),
        "quota": _command(
            [
                "vm",
                "list-usage",
                "--subscription",
                subscription,
                "--location",
                location,
            ]
        ),
    }
    if dry_run:
        return {
            "accepted": False,
            "classification": "dry_run_only_no_azure_state_checked",
            "sku": SKU,
            "location": location,
            "zone": zone,
            "nodes": nodes,
            "h100s": nodes,
            "memory_gb_per_node": MEMORY_GB_PER_VM,
            "required_vcpus": required,
            "commands": commands,
            "capacity_guaranteed": False,
            "resources_proven_attested": 0,
        }

    cli_version = _azure_cli_version(_run_az(["version"]))
    if cli_version < (2, 46, 0):
        raise AzurePlanError(
            f"Azure confidential-GPU onboarding requires Azure CLI >= 2.46.0; found {cli_version}"
        )
    account = _run_az(["account", "show", "--subscription", subscription])
    if (
        not isinstance(account, dict)
        or not isinstance(account.get("id"), str)
        or not account["id"]
        or not isinstance(account.get("tenantId"), str)
        or not account["tenantId"]
        or not isinstance(account.get("state"), str)
        or account["id"].lower() != subscription.lower()
    ):
        raise AzurePlanError("Azure account response is malformed")
    if account.get("state") != "Enabled":
        raise AzurePlanError(f"subscription is not enabled: {account.get('state')!r}")
    skus = _run_az(
        [
            "vm",
            "list-skus",
            "--subscription",
            subscription,
            "--location",
            location,
            "--size",
            SKU,
            "--all",
        ]
    )
    if not isinstance(skus, list) or any(not isinstance(row, dict) for row in skus):
        raise AzurePlanError("Azure SKU response must be an array of objects")
    matches = [row for row in skus if row.get("name") == SKU]
    if len(matches) != 1:
        raise AzurePlanError(f"Azure returned {len(matches)} exact {SKU} records in {location}")
    sku = matches[0]
    if not isinstance(sku.get("family"), str) or not sku["family"]:
        raise AzurePlanError("SKU record lacks a family name")
    restrictions = sku.get("restrictions")
    if not isinstance(restrictions, list) or any(
        not isinstance(restriction, dict) for restriction in restrictions
    ):
        raise AzurePlanError("SKU record has a malformed restrictions array")
    applicable = [
        restriction
        for restriction in restrictions
        if _restriction_applies(restriction, location, zone)
    ]
    if applicable:
        raise AzurePlanError(f"{SKU} is restricted for this subscription/location/zone: {applicable}")
    capabilities = _capability_map(sku)
    try:
        vcpus = int(capabilities["vCPUs"])
        gpus = int(capabilities["GPUs"])
        memory_gb = int(capabilities["MemoryGB"])
    except (KeyError, ValueError) as error:
        raise AzurePlanError(
            "SKU record lacks numeric vCPUs/GPUs/MemoryGB capabilities"
        ) from error
    generations = {item.strip() for item in capabilities.get("HyperVGenerations", "").split(",")}
    if generations != {"V2"}:
        raise AzurePlanError(
            f"unexpected {SKU} Hyper-V generations: {sorted(generations)}; expected only V2"
        )
    gpu_memory_values = [
        value
        for name, value in capabilities.items()
        if _normalized(name) in {"gpumemorygb", "acceleratormemorygb"}
    ]
    if len(gpu_memory_values) > 1:
        raise AzurePlanError("SKU exposes ambiguous accelerator-memory capabilities")
    accelerator_memory_gb: int | None = None
    if gpu_memory_values:
        try:
            accelerator_memory_gb = int(gpu_memory_values[0])
        except ValueError as error:
            raise AzurePlanError("SKU accelerator-memory capability is not numeric") from error
        if accelerator_memory_gb != H100_MEMORY_GB:
            raise AzurePlanError(
                f"unexpected H100 memory capability: {accelerator_memory_gb} GB; "
                f"expected {H100_MEMORY_GB} GB"
            )
    if (
        vcpus != VCPUS_PER_VM
        or gpus != GPUS_PER_VM
        or memory_gb != MEMORY_GB_PER_VM
    ):
        raise AzurePlanError(
            f"unexpected {SKU} shape: vCPUs={vcpus}, GPUs={gpus}, MemoryGB={memory_gb}; "
            f"expected {VCPUS_PER_VM}, {GPUS_PER_VM}, and {MEMORY_GB_PER_VM}"
        )
    quota_rows = _run_az(
        [
            "vm",
            "list-usage",
            "--subscription",
            subscription,
            "--location",
            location,
        ]
    )
    if not isinstance(quota_rows, list) or any(
        not isinstance(row, dict) for row in quota_rows
    ):
        raise AzurePlanError("Azure quota response must be an array of objects")
    family = _quota_summary(_quota_row(quota_rows, family=True), required)
    regional = _quota_summary(_quota_row(quota_rows, family=False), required)
    return {
        "accepted": True,
        "classification": "azure_control_plane_preflight_passed",
        "subscription_id": account.get("id"),
        "tenant_id": account.get("tenantId"),
        "azure_cli_version": ".".join(str(piece) for piece in cli_version),
        "sku": SKU,
        "sku_family": sku.get("family"),
        "location": location,
        "zone": zone,
        "nodes": nodes,
        "h100s": nodes,
        "vcpus_per_node": VCPUS_PER_VM,
        "gpus_per_node": GPUS_PER_VM,
        "memory_gb_per_node": MEMORY_GB_PER_VM,
        "accelerator_memory_capability_exposed": accelerator_memory_gb is not None,
        "accelerator_memory_gb": accelerator_memory_gb,
        "family_quota": family,
        "regional_quota": regional,
        "capacity_guaranteed": False,
        "resources_proven_attested": 0,
    }


def _validate_immutable_image_reference(value: str) -> str:
    if MARKETPLACE_IMAGE_RE.fullmatch(value) or GALLERY_IMAGE_RE.fullmatch(value):
        return value
    raise AzurePlanError(
        "image must be an exact marketplace publisher:offer:sku:numeric-version URN "
        "or a Compute/Community Gallery /versions/<major.minor.patch> resource ID"
    )


def _resolve_official_image(subscription: str, location: str) -> str:
    versions = _run_az(
        [
            "sig",
            "image-version",
            "list-community",
            "--subscription",
            subscription,
            "--location",
            location,
            "--public-gallery-name",
            PUBLIC_GALLERY,
            "--gallery-image-definition",
            UBUNTU_2204_IMAGE,
        ]
    )
    if not isinstance(versions, list) or any(not isinstance(row, dict) for row in versions):
        raise AzurePlanError("community image-version response must be an array of objects")

    def version_key(row: dict[str, Any]) -> tuple[int, int, int]:
        name = str(row.get("name", ""))
        pieces = name.split(".")
        if len(pieces) != 3 or any(not piece.isdigit() for piece in pieces):
            return (-1, -1, -1)
        return tuple(int(piece) for piece in pieces)  # type: ignore[return-value]

    def is_exact_official_id(row: dict[str, Any]) -> bool:
        image_id = row.get("id")
        version = row.get("name")
        if not isinstance(image_id, str) or not isinstance(version, str):
            return False
        expected = (
            f"/CommunityGalleries/{PUBLIC_GALLERY}/Images/{UBUNTU_2204_IMAGE}"
            f"/versions/{version}"
        )
        return image_id.casefold() == expected.casefold()

    usable = [
        row
        for row in versions
        if version_key(row) >= (0, 0, 0)
        and row.get("provisioningState") == "Succeeded"
        and is_exact_official_id(row)
    ]
    if not usable:
        raise AzurePlanError("official NCC Ubuntu 22.04 community image has no usable version")
    return _validate_immutable_image_reference(str(max(usable, key=version_key)["id"]))


def _vm_create_arguments(
    *,
    subscription: str,
    resource_group: str,
    name: str,
    location: str,
    zone: str | None,
    image: str,
    admin_username: str,
    ssh_key: Path,
    subnet_id: str,
    os_disk_size_gb: int,
) -> list[str]:
    arguments = [
        "vm",
        "create",
        "--subscription",
        subscription,
        "--resource-group",
        resource_group,
        "--name",
        name,
        "--location",
        location,
        "--image",
        image,
        "--size",
        SKU,
        "--admin-username",
        admin_username,
        "--authentication-type",
        "ssh",
        "--ssh-key-values",
        str(ssh_key),
        "--security-type",
        "ConfidentialVM",
        "--os-disk-security-encryption-type",
        "DiskWithVMGuestState",
        "--enable-secure-boot",
        "true",
        "--enable-vtpm",
        "true",
        "--os-disk-size-gb",
        str(os_disk_size_gb),
        "--subnet",
        subnet_id,
        "--public-ip-address",
        "",
        "--nsg",
        "",
        "--accept-term",
        "--tags",
        "gpu-prover=trusted-compute",
        "gpu-prover-shape=one-h100-per-vm",
    ]
    if zone is not None:
        arguments.extend(["--zone", zone])
    return arguments


def _image_readback_matches(reference: Any, expected: str) -> bool:
    if not isinstance(reference, dict):
        return False
    if MARKETPLACE_IMAGE_RE.fullmatch(expected):
        publisher, offer, sku, version = expected.split(":")
        observed_version = reference.get("exactVersion", reference.get("version"))
        return (
            reference.get("publisher") == publisher
            and reference.get("offer") == offer
            and reference.get("sku") == sku
            and observed_version == version
        )
    identifiers = [
        reference.get(name)
        for name in ("id", "communityGalleryImageId", "sharedGalleryImageId")
        if reference.get(name) is not None
    ]
    return bool(identifiers) and all(
        isinstance(value, str) and value.lower() == expected.lower()
        for value in identifiers
    )


def _validate_vm_readback(
    value: Any, *, name: str, expected_image: str
) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise AzurePlanError(f"VM readback for {name} is not an object")
    vm_id = value.get("id")
    if not isinstance(vm_id, str) or not vm_id:
        raise AzurePlanError(f"VM readback for {name} lacks an ID")
    hardware = value.get("hardwareProfile")
    security = value.get("securityProfile")
    storage = value.get("storageProfile")
    network = value.get("networkProfile")
    if not all(isinstance(item, dict) for item in (hardware, security, storage, network)):
        raise AzurePlanError(f"VM readback for {name} lacks required profiles")
    uefi = security.get("uefiSettings")
    os_disk = storage.get("osDisk")
    image_reference = storage.get("imageReference")
    if not isinstance(uefi, dict) or not isinstance(os_disk, dict):
        raise AzurePlanError(f"VM readback for {name} lacks UEFI or OS-disk state")
    managed_disk = os_disk.get("managedDisk")
    disk_security = (
        managed_disk.get("securityProfile") if isinstance(managed_disk, dict) else None
    )
    if (
        value.get("name") != name
        or value.get("provisioningState") != "Succeeded"
        or hardware.get("vmSize") != SKU
        or security.get("securityType") != "ConfidentialVM"
        or uefi.get("secureBootEnabled") is not True
        or uefi.get("vTpmEnabled") is not True
        or not isinstance(disk_security, dict)
        or disk_security.get("securityEncryptionType") != "DiskWithVMGuestState"
        or not _image_readback_matches(image_reference, expected_image)
    ):
        raise AzurePlanError(
            f"VM readback for {name} does not prove the exact confidential shape/image"
        )
    instance_view = value.get("instanceView")
    statuses = instance_view.get("statuses") if isinstance(instance_view, dict) else None
    if not isinstance(statuses, list) or any(not isinstance(row, dict) for row in statuses):
        raise AzurePlanError(f"VM readback for {name} lacks instance-view statuses")
    provisioning_codes = [
        row.get("code")
        for row in statuses
        if isinstance(row.get("code"), str)
        and row["code"].lower().startswith("provisioningstate/")
    ]
    if provisioning_codes != ["ProvisioningState/succeeded"]:
        raise AzurePlanError(f"VM {name} instance provisioning did not succeed exactly")
    interfaces = network.get("networkInterfaces")
    if (
        not isinstance(interfaces, list)
        or len(interfaces) != 1
        or not isinstance(interfaces[0], dict)
        or not isinstance(interfaces[0].get("id"), str)
        or interfaces[0].get("primary") is not True
    ):
        raise AzurePlanError(f"VM {name} does not have exactly one identified primary NIC")
    return vm_id, interfaces[0]["id"]


def _validate_nic_readback(value: Any, *, nic_id: str, vm_id: str) -> str:
    if not isinstance(value, dict):
        raise AzurePlanError("NIC readback is not an object")
    attached_vm = value.get("virtualMachine")
    configurations = value.get("ipConfigurations")
    if (
        not isinstance(value.get("id"), str)
        or value["id"].lower() != nic_id.lower()
        or value.get("provisioningState") != "Succeeded"
        or not isinstance(attached_vm, dict)
        or not isinstance(attached_vm.get("id"), str)
        or attached_vm["id"].lower() != vm_id.lower()
        or not isinstance(configurations, list)
        or len(configurations) != 1
        or not isinstance(configurations[0], dict)
    ):
        raise AzurePlanError("NIC readback does not prove one successfully attached interface")
    configuration = configurations[0]
    address = configuration.get("privateIPAddress")
    try:
        parsed_address = ipaddress.ip_address(address)
    except (TypeError, ValueError) as error:
        raise AzurePlanError("NIC readback lacks a valid private IP address") from error
    if (
        not isinstance(parsed_address, ipaddress.IPv4Address)
        or not parsed_address.is_private
        or configuration.get("primary") is not True
        or configuration.get("provisioningState") != "Succeeded"
        or configuration.get("publicIPAddress") is not None
    ):
        raise AzurePlanError("NIC readback does not prove a private-only primary IPv4 address")
    return str(parsed_address)


def deploy(args: argparse.Namespace) -> dict[str, Any]:
    for value, what in (
        (args.resource_group, "resource group"),
        (args.name_prefix, "name prefix"),
        (args.admin_username, "admin username"),
    ):
        if NAME_RE.fullmatch(value) is None:
            raise AzurePlanError(f"invalid {what}: {value!r}")
    if args.nodes > 999:
        raise AzurePlanError("nodes above 999 require a reviewed naming/sharding plan")
    if args.os_disk_size_gb < 100:
        raise AzurePlanError("OS disk must be at least 100 GiB")
    if SUBNET_ID_RE.fullmatch(args.subnet_id) is None:
        raise AzurePlanError("subnet-id must be a complete Azure subnet resource ID")
    if not args.dry_run and not args.ssh_key.is_file():
        raise AzurePlanError(f"SSH public key is not a file: {args.ssh_key}")
    checked = preflight(
        subscription=args.subscription,
        location=args.location,
        nodes=args.nodes,
        zone=args.zone,
        dry_run=args.dry_run,
    )
    if args.image == OFFICIAL_LATEST_IMAGE:
        image = (
            "<resolved-official-community-image-version>"
            if args.dry_run
            else _resolve_official_image(args.subscription, args.location)
        )
    else:
        image = _validate_immutable_image_reference(args.image)
    names = [f"{args.name_prefix}-{index:03d}" for index in range(args.nodes)]
    group = _command(
        [
            "group",
            "create",
            "--subscription",
            args.subscription,
            "--name",
            args.resource_group,
            "--location",
            args.location,
        ]
    )
    create_commands = [
        _command(
            _vm_create_arguments(
                subscription=args.subscription,
                resource_group=args.resource_group,
                name=name,
                location=args.location,
                zone=args.zone,
                image=image,
                admin_username=args.admin_username,
                ssh_key=args.ssh_key,
                subnet_id=args.subnet_id,
                os_disk_size_gb=args.os_disk_size_gb,
            )
        )
        for name in names
    ]
    if args.dry_run:
        return {
            "accepted": False,
            "classification": "dry_run_only_no_resources_created",
            "preflight": checked,
            "resolved_image": image,
            "image_resolution_command": _command(
                [
                    "sig",
                    "image-version",
                    "list-community",
                    "--subscription",
                    args.subscription,
                    "--location",
                    args.location,
                    "--public-gallery-name",
                    PUBLIC_GALLERY,
                    "--gallery-image-definition",
                    UBUNTU_2204_IMAGE,
                ]
            ),
            "resource_group_command": group,
            "subnet_inspection_command": _command(
                [
                    "network",
                    "vnet",
                    "subnet",
                    "show",
                    "--subscription",
                    args.subscription,
                    "--ids",
                    args.subnet_id,
                ]
            ),
            "vm_commands": create_commands,
            "public_ip_addresses": False,
            "h100s_per_vm": 1,
            "capacity_guaranteed": False,
            "resources_proven_attested": 0,
        }

    subnet = _run_az(
        [
            "network",
            "vnet",
            "subnet",
            "show",
            "--subscription",
            args.subscription,
            "--ids",
            args.subnet_id,
        ]
    )
    if not isinstance(subnet, dict):
        raise AzurePlanError("subnet readback is not an object")
    network_security_group = subnet.get("networkSecurityGroup")
    if not isinstance(network_security_group, dict) or not isinstance(
        network_security_group.get("id"), str
    ) or not network_security_group["id"]:
        raise AzurePlanError("private subnet has no subnet-level network security group")
    if subnet.get("defaultOutboundAccess") is not False:
        raise AzurePlanError(
            "subnet is not private: defaultOutboundAccess must be explicitly false"
        )
    nat_gateway = subnet.get("natGateway")
    route_table = subnet.get("routeTable")
    nat_gateway_id = nat_gateway.get("id") if isinstance(nat_gateway, dict) else None
    route_table_id = route_table.get("id") if isinstance(route_table, dict) else None
    has_nat_gateway = isinstance(nat_gateway_id, str) and bool(nat_gateway_id)
    has_route_table = isinstance(route_table_id, str) and bool(route_table_id)
    if not (has_nat_gateway or has_route_table):
        raise AzurePlanError(
            "private subnet has no explicit NAT gateway or reviewed route table for MAA/NRAS egress"
        )
    if not has_nat_gateway:
        nat_gateway_id = None
    if not has_route_table:
        route_table_id = None
    _run_az(group[1:-3])
    created: list[dict[str, Any]] = []
    for name, arguments in zip(names, create_commands, strict=True):
        # Sequential allocation intentionally makes the exact failed shard
        # visible and avoids turning a partial allocation into a claimed run.
        _run_az(arguments[1:-3])
        vm = _run_az(
            [
                "vm",
                "show",
                "--subscription",
                args.subscription,
                "--resource-group",
                args.resource_group,
                "--name",
                name,
                "--expand",
                "instanceView",
            ]
        )
        vm_id, nic_id = _validate_vm_readback(
            vm, name=name, expected_image=image
        )
        nic = _run_az(
            [
                "network",
                "nic",
                "show",
                "--subscription",
                args.subscription,
                "--ids",
                nic_id,
            ]
        )
        private_address = _validate_nic_readback(nic, nic_id=nic_id, vm_id=vm_id)
        created.append(
            {
                "name": name,
                "id": vm_id,
                "nic_id": nic_id,
                "private_ip_address": private_address,
                "public_ip_address_resource_id": None,
                "provisioning_state": "Succeeded",
                "security_type": "ConfidentialVM",
                "secure_boot_enabled": True,
                "vtpm_enabled": True,
                "os_disk_security_encryption_type": "DiskWithVMGuestState",
                "image": image,
                "sku": SKU,
            }
        )
    return {
        "accepted": True,
        "classification": "azure_ncc_h100_vms_created",
        "preflight": checked,
        "resolved_image": image,
        "resource_group": args.resource_group,
        "subnet_id": args.subnet_id,
        "subnet_network_security_group_id": network_security_group["id"],
        "subnet_default_outbound_access": False,
        "subnet_nat_gateway_id": nat_gateway_id,
        "subnet_route_table_id": route_table_id,
        "virtual_machines": created,
        "h100s_per_vm": 1,
        "public_ip_addresses": False,
        "attestation_collected": False,
        "resources_proven_attested": 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--subscription", required=True)
    common.add_argument("--location", required=True, choices=SUPPORTED_ONBOARDING_REGIONS)
    common.add_argument("--nodes", type=int, required=True)
    common.add_argument("--zone", choices=("1", "2", "3"))
    common.add_argument("--dry-run", action="store_true")

    check = subparsers.add_parser("preflight", parents=[common])
    check.set_defaults(handler="preflight")

    create = subparsers.add_parser("deploy", parents=[common])
    create.add_argument("--resource-group", required=True)
    create.add_argument("--name-prefix", required=True)
    create.add_argument("--admin-username", required=True)
    create.add_argument("--ssh-key", required=True, type=Path)
    create.add_argument(
        "--subnet-id",
        required=True,
        help="existing subnet protected by the reviewed NSG/NAT/Bastion policy",
    )
    create.add_argument("--image", default=OFFICIAL_LATEST_IMAGE)
    create.add_argument("--os-disk-size-gb", type=int, default=100)
    create.set_defaults(handler="deploy")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.handler == "preflight":
            result = preflight(
                subscription=args.subscription,
                location=args.location,
                nodes=args.nodes,
                zone=args.zone,
                dry_run=args.dry_run,
            )
        else:
            result = deploy(args)
        print(canonical_json(result))
        return 0 if result.get("accepted") else (0 if args.dry_run else 2)
    except (AzurePlanError, OSError, ValueError) as error:
        print(
            canonical_json(
                {
                    "accepted": False,
                    "classification": "azure_ncc_h100_operation_failed_closed",
                    "error": str(error),
                    "resources_proven_attested": 0,
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
