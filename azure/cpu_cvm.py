#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Preflight and deploy reviewed Azure AMD SEV-SNP CPU-only CVMs.

The default is the memory-heavy ``Standard_EC96as_v6`` shape.  The
``Standard_DC96as_v6`` shape is also available as an explicit reviewed
choice.  No other SKU is admitted by this adapter.

This is a fail-closed Azure CLI adapter, not an attestation verifier.  It
checks the exact SKU shape and quota, resolves the default marketplace image
to an immutable version, requires a private subnet, and verifies the created
VM's confidential security profile.  A dry run performs no Azure queries and
never reports acceptance or capacity.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


@dataclass(frozen=True)
class SkuShape:
    vcpus: int
    memory_gib: int
    quota_markers: tuple[str, ...]


DEFAULT_SKU = "Standard_EC96as_v6"
REVIEWED_SKUS = {
    DEFAULT_SKU: SkuShape(
        vcpus=96,
        memory_gib=672,
        quota_markers=("standardecasv6family", "ecasv6family"),
    ),
    "Standard_DC96as_v6": SkuShape(
        vcpus=96,
        memory_gib=384,
        quota_markers=("standarddcasv6family", "dcasv6family"),
    ),
}

IMAGE_PUBLISHER = "Canonical"
IMAGE_OFFER = "0001-com-ubuntu-confidential-vm-jammy"
IMAGE_SKU = "22_04-lts-cvm"
OFFICIAL_LATEST_IMAGE = f"{IMAGE_PUBLISHER}:{IMAGE_OFFER}:{IMAGE_SKU}:latest"
MINIMUM_AZURE_CLI = (2, 46, 0)

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
LOCATION_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
SUBNET_ID_RE = re.compile(
    r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/"
    r"Microsoft\.Network/virtualNetworks/[^/]+/subnets/[^/]+$",
    re.IGNORECASE,
)
GALLERY_VERSION_RE = re.compile(
    r"^(?:"
    r"/CommunityGalleries/[^/]+/Images/[^/]+/versions/"
    r"|/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft\.Compute/"
    r"galleries/[^/]+/images/[^/]+/versions/"
    r")[0-9]+(?:\.[0-9]+){2}$",
    re.IGNORECASE,
)


class AzurePlanError(RuntimeError):
    """The requested Azure operation cannot prove all required preconditions."""


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


def _shape(sku: str) -> SkuShape:
    try:
        return REVIEWED_SKUS[sku]
    except KeyError as error:
        raise AzurePlanError(
            f"unreviewed CPU CVM SKU {sku!r}; choose one of {sorted(REVIEWED_SKUS)}"
        ) from error


def _validate_location(location: str) -> str:
    normalized = location.lower()
    if LOCATION_RE.fullmatch(normalized) is None:
        raise AzurePlanError(f"invalid Azure location: {location!r}")
    return normalized


def _azure_cli_version(value: Any) -> tuple[int, int, int]:
    if not isinstance(value, dict) or not isinstance(value.get("azure-cli"), str):
        raise AzurePlanError("az version output lacks the azure-cli version")
    pieces = value["azure-cli"].split(".")
    if len(pieces) < 3:
        raise AzurePlanError(f"malformed Azure CLI version: {value['azure-cli']!r}")
    try:
        return tuple(int(piece) for piece in pieces[:3])  # type: ignore[return-value]
    except ValueError as error:
        raise AzurePlanError(f"malformed Azure CLI version: {value['azure-cli']!r}") from error


def _restriction_applies(
    restriction: dict[str, Any], location: str, zone: str | None
) -> bool:
    info = restriction.get("restrictionInfo") or {}
    locations = {str(item).lower() for item in info.get("locations") or []}
    zones = {str(item) for item in info.get("zones") or []}
    values = {str(item).lower() for item in restriction.get("values") or []}
    if locations and location not in locations:
        return False
    if restriction.get("type") == "Zone" and zone is not None:
        return zone in zones or zone.lower() in values
    if restriction.get("type") == "Zone" and zone is None:
        return False
    return not values or location in values or bool(locations)


def _capability_map(sku_record: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("name")): str(item.get("value"))
        for item in sku_record.get("capabilities") or []
        if item.get("name") is not None and item.get("value") is not None
    }


def _integer_capability(
    capabilities: dict[str, str], name: str, *, default: int | None = None
) -> int:
    value = capabilities.get(name)
    if value is None:
        if default is not None:
            return default
        raise AzurePlanError(f"SKU record lacks the {name} capability")
    try:
        result = int(value)
    except ValueError as error:
        raise AzurePlanError(f"SKU capability {name} is not numeric: {value!r}") from error
    if result < 0:
        raise AzurePlanError(f"SKU capability {name} cannot be negative")
    return result


def _validate_sku_record(record: Any, sku: str) -> tuple[dict[str, str], str]:
    if not isinstance(record, dict) or record.get("name") != sku:
        raise AzurePlanError(f"Azure did not return the exact requested SKU {sku}")
    shape = _shape(sku)
    capabilities = _capability_map(record)
    vcpus = _integer_capability(capabilities, "vCPUs")
    memory = _integer_capability(capabilities, "MemoryGB")
    gpus = _integer_capability(capabilities, "GPUs", default=0)
    if (vcpus, memory, gpus) != (shape.vcpus, shape.memory_gib, 0):
        raise AzurePlanError(
            f"unexpected {sku} shape: vCPUs={vcpus}, MemoryGB={memory}, GPUs={gpus}; "
            f"expected {shape.vcpus}, {shape.memory_gib}, 0"
        )
    generations = {
        item.strip().upper()
        for item in capabilities.get("HyperVGenerations", "").split(",")
        if item.strip()
    }
    if "V2" not in generations:
        raise AzurePlanError(f"{sku} SKU record does not affirm Generation 2 support")
    family = record.get("family")
    if not isinstance(family, str) or not family:
        raise AzurePlanError("SKU record lacks a family name for quota validation")
    return capabilities, family


def _usage_name(row: dict[str, Any]) -> str:
    name = row.get("name") or {}
    return " ".join(
        str(value)
        for value in (
            name.get("value"),
            name.get("localizedValue"),
            row.get("localName"),
        )
        if value
    )


def _family_quota_row(
    rows: list[dict[str, Any]], *, family_name: str, sku: str
) -> dict[str, Any]:
    expected_family = _normalized(family_name)
    candidates = [
        row
        for row in rows
        if expected_family and expected_family in _normalized(_usage_name(row))
    ]
    if not candidates:
        markers = _shape(sku).quota_markers
        candidates = [
            row
            for row in rows
            if any(marker in _normalized(_usage_name(row)) for marker in markers)
        ]
    if len(candidates) != 1:
        raise AzurePlanError(
            f"could not identify one {family_name!r} quota row; "
            f"candidates={[_usage_name(row) for row in candidates]}"
        )
    return candidates[0]


def _regional_quota_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = []
    for row in rows:
        normalized = _normalized(_usage_name(row))
        if (
            "totalregionalvcpus" in normalized
            or "totalregionalcores" in normalized
            or normalized == "cores"
        ):
            candidates.append(row)
    if len(candidates) != 1:
        raise AzurePlanError(
            "could not identify one total regional vCPU quota row; "
            f"candidates={[_usage_name(row) for row in candidates]}"
        )
    return candidates[0]


def _quota_summary(row: dict[str, Any], required: int) -> dict[str, Any]:
    current = row.get("currentValue")
    limit = row.get("limit")
    if (
        not isinstance(current, int)
        or isinstance(current, bool)
        or not isinstance(limit, int)
        or isinstance(limit, bool)
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


def _preflight_commands(
    subscription: str, location: str, sku: str
) -> dict[str, list[str]]:
    return {
        "azure_cli_version": _command(["version"]),
        "account": _command(
            ["account", "show", "--subscription", subscription]
        ),
        "sku": _command(
            [
                "vm",
                "list-skus",
                "--subscription",
                subscription,
                "--location",
                location,
                "--size",
                sku,
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


def preflight(
    *,
    subscription: str,
    location: str,
    nodes: int,
    zone: str | None,
    sku: str = DEFAULT_SKU,
    dry_run: bool,
) -> dict[str, Any]:
    if not isinstance(nodes, int) or isinstance(nodes, bool) or nodes < 1:
        raise AzurePlanError("nodes must be a positive integer")
    shape = _shape(sku)
    location = _validate_location(location)
    if zone is not None and zone not in {"1", "2", "3"}:
        raise AzurePlanError("zone must be 1, 2, or 3")
    required = nodes * shape.vcpus
    commands = _preflight_commands(subscription, location, sku)
    if dry_run:
        return {
            "accepted": False,
            "classification": "dry_run_only_no_azure_state_checked",
            "sku": sku,
            "expected_vcpus_per_node": shape.vcpus,
            "expected_memory_gib_per_node": shape.memory_gib,
            "expected_gpus_per_node": 0,
            "location": location,
            "zone": zone,
            "nodes": nodes,
            "required_vcpus": required,
            "commands": commands,
            "capacity_guaranteed": False,
        }

    cli_version = _azure_cli_version(_run_az(["version"]))
    if cli_version < MINIMUM_AZURE_CLI:
        raise AzurePlanError(
            "Azure CPU CVM deployment requires Azure CLI >= "
            f"{'.'.join(str(piece) for piece in MINIMUM_AZURE_CLI)}; "
            f"found {cli_version}"
        )
    account = _run_az(["account", "show", "--subscription", subscription])
    if not isinstance(account, dict) or account.get("state") != "Enabled":
        state = account.get("state") if isinstance(account, dict) else None
        raise AzurePlanError(f"subscription is not enabled: {state!r}")
    skus = _run_az(
        [
            "vm",
            "list-skus",
            "--subscription",
            subscription,
            "--location",
            location,
            "--size",
            sku,
            "--all",
        ]
    )
    if not isinstance(skus, list):
        raise AzurePlanError("Azure SKU query did not return an array")
    matches = [row for row in skus if isinstance(row, dict) and row.get("name") == sku]
    if len(matches) != 1:
        raise AzurePlanError(
            f"Azure returned {len(matches)} exact {sku} records in {location}"
        )
    record = matches[0]
    applicable = [
        restriction
        for restriction in record.get("restrictions") or []
        if isinstance(restriction, dict)
        and _restriction_applies(restriction, location, zone)
    ]
    if applicable:
        raise AzurePlanError(
            f"{sku} is restricted for this subscription/location/zone: {applicable}"
        )
    _capabilities, family_name = _validate_sku_record(record, sku)
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
    if not isinstance(quota_rows, list):
        raise AzurePlanError("Azure quota query did not return an array")
    family_quota = _quota_summary(
        _family_quota_row(quota_rows, family_name=family_name, sku=sku),
        required,
    )
    regional_quota = _quota_summary(_regional_quota_row(quota_rows), required)
    return {
        "accepted": True,
        "classification": "azure_cpu_cvm_control_plane_preflight_passed",
        "subscription_id": account.get("id"),
        "tenant_id": account.get("tenantId"),
        "azure_cli_version": ".".join(str(piece) for piece in cli_version),
        "sku": sku,
        "sku_family": family_name,
        "location": location,
        "zone": zone,
        "nodes": nodes,
        "vcpus_per_node": shape.vcpus,
        "memory_gib_per_node": shape.memory_gib,
        "gpus_per_node": 0,
        "family_quota": family_quota,
        "regional_quota": regional_quota,
        "capacity_guaranteed": False,
    }


def _image_resolution_arguments(subscription: str, location: str) -> list[str]:
    return [
        "vm",
        "image",
        "list",
        "--subscription",
        subscription,
        "--location",
        location,
        "--publisher",
        IMAGE_PUBLISHER,
        "--offer",
        IMAGE_OFFER,
        "--sku",
        IMAGE_SKU,
        "--all",
    ]


def _image_version_key(value: str) -> tuple[int, ...]:
    pieces = value.split(".")
    if not pieces or any(not piece.isdigit() for piece in pieces):
        return ()
    return tuple(int(piece) for piece in pieces)


def _resolve_official_image(subscription: str, location: str) -> str:
    rows = _run_az(_image_resolution_arguments(subscription, location))
    if not isinstance(rows, list):
        raise AzurePlanError("official CVM image query did not return an array")
    usable: list[tuple[tuple[int, ...], str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        version = row.get("version")
        urn = row.get("urn")
        if not isinstance(version, str) or not isinstance(urn, str):
            continue
        key = _image_version_key(version)
        expected_urn = f"{IMAGE_PUBLISHER}:{IMAGE_OFFER}:{IMAGE_SKU}:{version}"
        if (
            not key
            or urn != expected_urn
            or row.get("publisher") != IMAGE_PUBLISHER
            or row.get("offer") != IMAGE_OFFER
            or row.get("sku") != IMAGE_SKU
            or row.get("provisioningState", "Succeeded") != "Succeeded"
        ):
            continue
        usable.append((key, urn))
    if not usable:
        raise AzurePlanError("official Ubuntu 22.04 CVM image has no usable exact version")
    return max(usable)[1]


def _require_pinned_image(image: str) -> str:
    if image.count(":") == 3:
        version = image.rsplit(":", 1)[1]
        if version.lower() == "latest" or not _image_version_key(version):
            raise AzurePlanError(
                "marketplace image must pin an exact numeric version, not latest"
            )
        return image
    if GALLERY_VERSION_RE.fullmatch(image) is None:
        raise AzurePlanError(
            "image must be an exact marketplace URN or a numeric "
            "Compute/Community Gallery version resource ID"
        )
    return image


def _vm_create_arguments(
    *,
    subscription: str,
    resource_group: str,
    name: str,
    location: str,
    zone: str | None,
    image: str,
    sku: str,
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
        sku,
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
        "--storage-sku",
        "Premium_LRS",
        "--subnet",
        subnet_id,
        "--public-ip-address",
        "",
        "--nsg",
        "",
        "--tags",
        "gpu-prover=trusted-compute",
        "gpu-prover-backend=azure-sevsnp-cpu",
        f"gpu-prover-sku={sku}",
    ]
    if zone is not None:
        arguments.extend(["--zone", zone])
    return arguments


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _expected_image_reference(image: str) -> dict[str, str]:
    if image.count(":") == 3:
        publisher, offer, sku, version = image.split(":")
        return {
            "publisher": publisher,
            "offer": offer,
            "sku": sku,
            "version": version,
        }
    return {"id": image}


def _verify_created_vm(record: Any, *, sku: str, image: str) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise AzurePlanError("created VM inspection did not return an object")
    if _nested(record, "hardwareProfile", "vmSize") != sku:
        raise AzurePlanError("created VM does not have the requested exact SKU")
    if _nested(record, "securityProfile", "securityType") != "ConfidentialVM":
        raise AzurePlanError("created VM is not classified as ConfidentialVM")
    if _nested(record, "securityProfile", "uefiSettings", "secureBootEnabled") is not True:
        raise AzurePlanError("created VM does not affirm Secure Boot")
    if _nested(record, "securityProfile", "uefiSettings", "vTpmEnabled") is not True:
        raise AzurePlanError("created VM does not affirm vTPM")
    encryption = _nested(
        record,
        "storageProfile",
        "osDisk",
        "managedDisk",
        "securityProfile",
        "securityEncryptionType",
    )
    if encryption != "DiskWithVMGuestState":
        raise AzurePlanError(
            "created VM OS disk does not affirm DiskWithVMGuestState encryption"
        )
    if record.get("provisioningState") != "Succeeded":
        raise AzurePlanError(
            f"created VM provisioning is not successful: {record.get('provisioningState')!r}"
        )
    actual_image = _nested(record, "storageProfile", "imageReference")
    expected_image = _expected_image_reference(image)
    if not isinstance(actual_image, dict) or any(
        actual_image.get(key) != value for key, value in expected_image.items()
    ):
        raise AzurePlanError("created VM image reference differs from the pinned image")
    interfaces = _nested(record, "networkProfile", "networkInterfaces")
    if not isinstance(interfaces, list) or len(interfaces) != 1:
        raise AzurePlanError("created VM must have exactly one inspected network interface")
    interface_id = interfaces[0].get("id") if isinstance(interfaces[0], dict) else None
    if not isinstance(interface_id, str) or not interface_id:
        raise AzurePlanError("created VM network interface has no resource ID")
    return {
        "security_type": "ConfidentialVM",
        "secure_boot": True,
        "vtpm": True,
        "os_disk_security_encryption_type": "DiskWithVMGuestState",
        "image_reference": expected_image,
        "network_interface_id": interface_id,
    }


def _verify_private_nic(record: Any, *, expected_id: str) -> list[str]:
    if not isinstance(record, dict):
        raise AzurePlanError("network-interface inspection did not return an object")
    actual_id = record.get("id")
    if not isinstance(actual_id, str) or actual_id.lower() != expected_id.lower():
        raise AzurePlanError("network-interface inspection returned the wrong resource")
    configurations = record.get("ipConfigurations")
    if not isinstance(configurations, list) or not configurations:
        raise AzurePlanError("network interface has no IP configuration")
    private_addresses: list[str] = []
    for configuration in configurations:
        if not isinstance(configuration, dict):
            raise AzurePlanError("network interface has a malformed IP configuration")
        if configuration.get("publicIPAddress") is not None:
            raise AzurePlanError("network interface has a public IP address resource")
        private = configuration.get("privateIPAddress")
        if not isinstance(private, str) or not private:
            raise AzurePlanError("network interface does not affirm a private IP address")
        private_addresses.append(private)
    return private_addresses


def _validate_deploy_arguments(args: argparse.Namespace) -> tuple[str, SkuShape]:
    for value, what in (
        (args.resource_group, "resource group"),
        (args.name_prefix, "name prefix"),
        (args.admin_username, "admin username"),
    ):
        if NAME_RE.fullmatch(value) is None:
            raise AzurePlanError(f"invalid {what}: {value!r}")
    if args.nodes > 999:
        raise AzurePlanError("nodes above 999 require a reviewed naming/sharding plan")
    if args.os_disk_size_gb < 64:
        raise AzurePlanError("OS disk must be at least 64 GiB")
    if SUBNET_ID_RE.fullmatch(args.subnet_id) is None:
        raise AzurePlanError("subnet-id must be a complete Azure subnet resource ID")
    if not args.dry_run and not args.ssh_key.is_file():
        raise AzurePlanError(f"SSH public key is not a file: {args.ssh_key}")
    return _validate_location(args.location), _shape(args.sku)


def deploy(args: argparse.Namespace) -> dict[str, Any]:
    location, shape = _validate_deploy_arguments(args)
    checked = preflight(
        subscription=args.subscription,
        location=location,
        nodes=args.nodes,
        zone=args.zone,
        sku=args.sku,
        dry_run=args.dry_run,
    )
    if args.image == OFFICIAL_LATEST_IMAGE:
        image = (
            "<resolved-canonical-cvm-image-version>"
            if args.dry_run
            else _resolve_official_image(args.subscription, location)
        )
    else:
        image = _require_pinned_image(args.image)

    names = [f"{args.name_prefix}-{index:03d}" for index in range(args.nodes)]
    group_arguments = [
        "group",
        "create",
        "--subscription",
        args.subscription,
        "--name",
        args.resource_group,
        "--location",
        location,
    ]
    create_arguments = [
        _vm_create_arguments(
            subscription=args.subscription,
            resource_group=args.resource_group,
            name=name,
            location=location,
            zone=args.zone,
            image=image,
            sku=args.sku,
            admin_username=args.admin_username,
            ssh_key=args.ssh_key,
            subnet_id=args.subnet_id,
            os_disk_size_gb=args.os_disk_size_gb,
        )
        for name in names
    ]
    subnet_arguments = [
        "network",
        "vnet",
        "subnet",
        "show",
        "--subscription",
        args.subscription,
        "--ids",
        args.subnet_id,
    ]
    if args.dry_run:
        return {
            "accepted": False,
            "classification": "dry_run_only_no_resources_created",
            "preflight": checked,
            "resolved_image": image,
            "image_resolution_command": _command(
                _image_resolution_arguments(args.subscription, location)
            ),
            "resource_group_command": _command(group_arguments),
            "subnet_inspection_command": _command(subnet_arguments),
            "vm_commands": [_command(arguments) for arguments in create_arguments],
            "sku": args.sku,
            "vcpus_per_vm": shape.vcpus,
            "memory_gib_per_vm": shape.memory_gib,
            "gpus_per_vm": 0,
            "public_ip_addresses": False,
            "capacity_guaranteed": False,
            "resources_created": False,
            "resources_proven_attested": 0,
        }

    subnet = _run_az(subnet_arguments)
    if not isinstance(subnet, dict):
        raise AzurePlanError("subnet inspection did not return an object")
    network_security_group = subnet.get("networkSecurityGroup")
    if not isinstance(network_security_group, dict) or not isinstance(
        network_security_group.get("id"), str
    ):
        raise AzurePlanError("private subnet has no subnet-level network security group")
    if subnet.get("defaultOutboundAccess") is not False:
        raise AzurePlanError(
            "subnet is not private: defaultOutboundAccess must be explicitly false"
        )
    nat_gateway = subnet.get("natGateway")
    route_table = subnet.get("routeTable")
    nat_gateway_id = nat_gateway.get("id") if isinstance(nat_gateway, dict) else None
    route_table_id = route_table.get("id") if isinstance(route_table, dict) else None
    if not isinstance(nat_gateway_id, str) and not isinstance(route_table_id, str):
        raise AzurePlanError(
            "private subnet has no explicit NAT gateway or reviewed route table"
        )

    _run_az(group_arguments)
    created: list[dict[str, Any]] = []
    for name, arguments in zip(names, create_arguments, strict=True):
        response = _run_az(arguments)
        if not isinstance(response, dict):
            raise AzurePlanError(f"Azure VM creation returned no object for {name}")
        if response.get("publicIpAddress") not in (None, ""):
            raise AzurePlanError(f"Azure unexpectedly assigned a public IP to {name}")
        inspection = _run_az(
            [
                "vm",
                "show",
                "--subscription",
                args.subscription,
                "--resource-group",
                args.resource_group,
                "--name",
                name,
            ]
        )
        security = _verify_created_vm(inspection, sku=args.sku, image=image)
        private_addresses = _verify_private_nic(
            _run_az(
                [
                    "network",
                    "nic",
                    "show",
                    "--subscription",
                    args.subscription,
                    "--ids",
                    security["network_interface_id"],
                ]
            ),
            expected_id=security["network_interface_id"],
        )
        created.append(
            {
                "name": name,
                "id": response.get("id"),
                "private_ip_addresses": private_addresses,
                "public_ip_address": None,
                "security_profile": security,
            }
        )
    return {
        "accepted": True,
        "classification": "azure_cpu_confidential_vms_created_and_inspected",
        "preflight": checked,
        "resolved_image": image,
        "resource_group": args.resource_group,
        "subnet_id": args.subnet_id,
        "subnet_network_security_group_id": network_security_group["id"],
        "subnet_default_outbound_access": False,
        "subnet_nat_gateway_id": nat_gateway_id,
        "subnet_route_table_id": route_table_id,
        "sku": args.sku,
        "vcpus_per_vm": shape.vcpus,
        "memory_gib_per_vm": shape.memory_gib,
        "gpus_per_vm": 0,
        "virtual_machines": created,
        "public_ip_addresses": False,
        "attestation_collected": False,
        "resources_proven_attested": 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--subscription", required=True)
    common.add_argument("--location", required=True)
    common.add_argument("--nodes", type=int, required=True)
    common.add_argument("--zone", choices=("1", "2", "3"))
    common.add_argument("--sku", choices=tuple(REVIEWED_SKUS), default=DEFAULT_SKU)
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
        help="existing private subnet protected by a reviewed NSG and egress path",
    )
    create.add_argument("--image", default=OFFICIAL_LATEST_IMAGE)
    create.add_argument("--os-disk-size-gb", type=int, default=128)
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
                sku=args.sku,
                dry_run=args.dry_run,
            )
        else:
            result = deploy(args)
        print(canonical_json(result))
        return 0 if result.get("accepted") or args.dry_run else 2
    except (AzurePlanError, OSError, ValueError) as error:
        print(
            canonical_json(
                {
                    "accepted": False,
                    "classification": "azure_cpu_cvm_operation_failed_closed",
                    "error": str(error),
                    "resources_proven_attested": 0,
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
