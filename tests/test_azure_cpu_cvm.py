# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    specification = importlib.util.spec_from_file_location(name, REPOSITORY / relative)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


cpu = load_module("gpu_prover_azure_cpu_cvm", "azure/cpu_cvm.py")


class AzureCpuCvmTests(unittest.TestCase):
    subscription = "00000000-0000-0000-0000-000000000000"
    subnet = (
        "/subscriptions/s/resourceGroups/network/providers/Microsoft.Network/"
        "virtualNetworks/private/subnets/compute"
    )

    @staticmethod
    def sku_record(sku: str = cpu.DEFAULT_SKU) -> dict:
        shape = cpu.REVIEWED_SKUS[sku]
        family = (
            "standardECASv6Family"
            if sku == "Standard_EC96as_v6"
            else "standardDCASv6Family"
        )
        return {
            "name": sku,
            "family": family,
            "capabilities": [
                {"name": "vCPUs", "value": str(shape.vcpus)},
                {"name": "MemoryGB", "value": str(shape.memory_gib)},
                {"name": "GPUs", "value": "0"},
                {"name": "HyperVGenerations", "value": "V2"},
            ],
            "restrictions": [],
        }

    @staticmethod
    def quota_rows(sku: str = cpu.DEFAULT_SKU, *, limit: int = 1000) -> list[dict]:
        family = (
            "standardECASv6Family"
            if sku == "Standard_EC96as_v6"
            else "standardDCASv6Family"
        )
        return [
            {
                "name": {"value": family, "localizedValue": f"{family} vCPUs"},
                "currentValue": 0,
                "limit": limit,
            },
            {
                "name": {
                    "value": "cores",
                    "localizedValue": "Total Regional vCPUs",
                },
                "currentValue": 0,
                "limit": limit,
            },
        ]

    @staticmethod
    def vm_record(sku: str, image: str) -> dict:
        publisher, offer, image_sku, version = image.split(":")
        return {
            "hardwareProfile": {"vmSize": sku},
            "networkProfile": {
                "networkInterfaces": [{"id": "/networkInterfaces/tg-cpu-000"}]
            },
            "provisioningState": "Succeeded",
            "securityProfile": {
                "securityType": "ConfidentialVM",
                "uefiSettings": {
                    "secureBootEnabled": True,
                    "vTpmEnabled": True,
                },
            },
            "storageProfile": {
                "imageReference": {
                    "publisher": publisher,
                    "offer": offer,
                    "sku": image_sku,
                    "version": version,
                },
                "osDisk": {
                    "managedDisk": {
                        "securityProfile": {
                            "securityEncryptionType": "DiskWithVMGuestState"
                        }
                    }
                },
            },
        }

    def fake_preflight_az(self, arguments):
        arguments = list(arguments)
        if arguments == ["version"]:
            return {"azure-cli": "2.77.0"}
        if arguments[:2] == ["account", "show"]:
            return {
                "id": self.subscription,
                "tenantId": "tenant-id",
                "state": "Enabled",
            }
        if arguments[:2] == ["vm", "list-skus"]:
            sku = arguments[arguments.index("--size") + 1]
            return [self.sku_record(sku)]
        if arguments[:2] == ["vm", "list-usage"]:
            sku = getattr(self, "active_sku", cpu.DEFAULT_SKU)
            return self.quota_rows(sku)
        self.fail(f"unexpected Azure command: {arguments}")

    def test_reviewed_shapes_are_exact_and_cpu_only(self) -> None:
        self.assertEqual(cpu.DEFAULT_SKU, "Standard_EC96as_v6")
        self.assertEqual(
            (cpu.REVIEWED_SKUS[cpu.DEFAULT_SKU].vcpus,
             cpu.REVIEWED_SKUS[cpu.DEFAULT_SKU].memory_gib),
            (96, 672),
        )
        self.assertEqual(
            (cpu.REVIEWED_SKUS["Standard_DC96as_v6"].vcpus,
             cpu.REVIEWED_SKUS["Standard_DC96as_v6"].memory_gib),
            (96, 384),
        )
        with self.assertRaisesRegex(cpu.AzurePlanError, "unreviewed CPU CVM SKU"):
            cpu.preflight(
                subscription=self.subscription,
                location="eastus2",
                nodes=1,
                zone=None,
                sku="Standard_E96as_v6",
                dry_run=True,
            )

    def test_preflight_dry_run_is_fail_closed_and_offline(self) -> None:
        with mock.patch.object(
            cpu, "_run_az", side_effect=AssertionError("dry run queried Azure")
        ):
            result = cpu.preflight(
                subscription=self.subscription,
                location="eastus2",
                nodes=3,
                zone="2",
                dry_run=True,
            )
        self.assertFalse(result["accepted"])
        self.assertFalse(result["capacity_guaranteed"])
        self.assertEqual(result["sku"], "Standard_EC96as_v6")
        self.assertEqual(result["required_vcpus"], 288)
        self.assertEqual(result["expected_memory_gib_per_node"], 672)
        self.assertEqual(result["expected_gpus_per_node"], 0)
        self.assertIn("list-skus", result["commands"]["sku"])
        self.assertIn("list-usage", result["commands"]["quota"])

    def test_reviewed_dc96_shape_is_an_explicit_option(self) -> None:
        result = cpu.preflight(
            subscription=self.subscription,
            location="northeurope",
            nodes=2,
            zone=None,
            sku="Standard_DC96as_v6",
            dry_run=True,
        )
        self.assertEqual(result["sku"], "Standard_DC96as_v6")
        self.assertEqual(result["expected_vcpus_per_node"], 96)
        self.assertEqual(result["expected_memory_gib_per_node"], 384)

    def test_live_preflight_checks_shape_family_and_regional_quota(self) -> None:
        self.active_sku = cpu.DEFAULT_SKU
        with mock.patch.object(cpu, "_run_az", side_effect=self.fake_preflight_az):
            result = cpu.preflight(
                subscription=self.subscription,
                location="eastus2",
                nodes=4,
                zone=None,
                dry_run=False,
            )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["vcpus_per_node"], 96)
        self.assertEqual(result["memory_gib_per_node"], 672)
        self.assertEqual(result["gpus_per_node"], 0)
        self.assertEqual(result["family_quota"]["required_vcpus"], 384)
        self.assertEqual(result["regional_quota"]["required_vcpus"], 384)
        self.assertFalse(result["capacity_guaranteed"])

    def test_sku_validation_rejects_shape_gpu_and_generation_drift(self) -> None:
        cases = (
            ("MemoryGB", "671", "unexpected.*shape"),
            ("GPUs", "1", "unexpected.*shape"),
            ("HyperVGenerations", "V1", "Generation 2"),
        )
        for capability, value, message in cases:
            with self.subTest(capability=capability):
                record = self.sku_record()
                for item in record["capabilities"]:
                    if item["name"] == capability:
                        item["value"] = value
                with self.assertRaisesRegex(cpu.AzurePlanError, message):
                    cpu._validate_sku_record(record, cpu.DEFAULT_SKU)

    def test_preflight_rejects_restriction_and_insufficient_quota(self) -> None:
        restricted = self.sku_record()
        restricted["restrictions"] = [
            {
                "type": "Location",
                "values": ["eastus2"],
                "restrictionInfo": {"locations": ["eastus2"]},
            }
        ]

        def restricted_az(arguments):
            if list(arguments) == ["version"]:
                return {"azure-cli": "2.77.0"}
            if list(arguments)[:2] == ["account", "show"]:
                return {"state": "Enabled"}
            if list(arguments)[:2] == ["vm", "list-skus"]:
                return [restricted]
            self.fail(f"unexpected command: {arguments}")

        with mock.patch.object(cpu, "_run_az", side_effect=restricted_az):
            with self.assertRaisesRegex(cpu.AzurePlanError, "is restricted"):
                cpu.preflight(
                    subscription=self.subscription,
                    location="eastus2",
                    nodes=1,
                    zone=None,
                    dry_run=False,
                )

        with self.assertRaisesRegex(cpu.AzurePlanError, "insufficient"):
            cpu._quota_summary(self.quota_rows(limit=95)[0], 96)

    def test_deploy_dry_run_requires_every_confidential_and_private_flag(self) -> None:
        process = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY / "azure/cpu_cvm.py"),
                "deploy",
                "--subscription",
                self.subscription,
                "--location",
                "eastus2",
                "--nodes",
                "2",
                "--resource-group",
                "tg-private",
                "--name-prefix",
                "tg-cpu",
                "--admin-username",
                "tgoperator",
                "--ssh-key",
                "/does/not/exist.pub",
                "--subnet-id",
                self.subnet,
                "--dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(process.stdout)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["resources_created"])
        self.assertEqual(result["resources_proven_attested"], 0)
        self.assertEqual(result["gpus_per_vm"], 0)
        self.assertEqual(len(result["vm_commands"]), 2)
        for command in result["vm_commands"]:
            self.assertIn("Standard_EC96as_v6", command)
            self.assertIn("ConfidentialVM", command)
            self.assertIn("DiskWithVMGuestState", command)
            self.assertIn("--enable-secure-boot", command)
            self.assertIn("--enable-vtpm", command)
            public_index = command.index("--public-ip-address")
            self.assertEqual(command[public_index + 1], "")
            nsg_index = command.index("--nsg")
            self.assertEqual(command[nsg_index + 1], "")

    def test_custom_images_must_pin_a_version(self) -> None:
        parser = cpu.build_parser()
        args = parser.parse_args(
            [
                "deploy",
                "--subscription",
                self.subscription,
                "--location",
                "eastus2",
                "--nodes",
                "1",
                "--resource-group",
                "tg-private",
                "--name-prefix",
                "tg-cpu",
                "--admin-username",
                "tgoperator",
                "--ssh-key",
                "/does/not/exist.pub",
                "--subnet-id",
                self.subnet,
                "--image",
                "Canonical:offer:sku:latest",
                "--dry-run",
            ]
        )
        with self.assertRaisesRegex(cpu.AzurePlanError, "pin an exact numeric version"):
            cpu.deploy(args)

        for image in (
            "/subscriptions/s/resourceGroups/r/providers/Microsoft.Compute/"
            "galleries/g/images/i/versions/latest",
            "/subscriptions/s/resourceGroups/r/providers/Microsoft.Compute/"
            "galleries/g/images/i/versions/stable",
            "relative/images/i/versions/1.2.3",
        ):
            with self.subTest(image=image), self.assertRaisesRegex(
                cpu.AzurePlanError, "numeric Compute/Community Gallery version"
            ):
                cpu._require_pinned_image(image)

        self.assertEqual(
            cpu._require_pinned_image(
                "/subscriptions/s/resourceGroups/r/providers/Microsoft.Compute/"
                "galleries/g/images/i/versions/1.2.3"
            ),
            "/subscriptions/s/resourceGroups/r/providers/Microsoft.Compute/"
            "galleries/g/images/i/versions/1.2.3",
        )

    def test_live_deploy_resolves_image_and_rechecks_created_security(self) -> None:
        exact_image = (
            f"{cpu.IMAGE_PUBLISHER}:{cpu.IMAGE_OFFER}:{cpu.IMAGE_SKU}:"
            "22.04.202607010"
        )
        with tempfile.TemporaryDirectory() as temporary:
            ssh_key = Path(temporary) / "operator.pub"
            ssh_key.write_text("ssh-ed25519 AAAATEST operator@example.invalid\n")
            args = cpu.build_parser().parse_args(
                [
                    "deploy",
                    "--subscription",
                    self.subscription,
                    "--location",
                    "eastus2",
                    "--nodes",
                    "1",
                    "--resource-group",
                    "tg-private",
                    "--name-prefix",
                    "tg-cpu",
                    "--admin-username",
                    "tgoperator",
                    "--ssh-key",
                    str(ssh_key),
                    "--subnet-id",
                    self.subnet,
                ]
            )
            seen: list[list[str]] = []

            def fake_az(arguments):
                arguments = list(arguments)
                seen.append(arguments)
                if arguments == ["version"]:
                    return {"azure-cli": "2.77.0"}
                if arguments[:2] == ["account", "show"]:
                    return {
                        "id": self.subscription,
                        "tenantId": "tenant-id",
                        "state": "Enabled",
                    }
                if arguments[:2] == ["vm", "list-skus"]:
                    return [self.sku_record()]
                if arguments[:2] == ["vm", "list-usage"]:
                    return self.quota_rows()
                if arguments[:3] == ["vm", "image", "list"]:
                    return [
                        {
                            "publisher": cpu.IMAGE_PUBLISHER,
                            "offer": cpu.IMAGE_OFFER,
                            "sku": cpu.IMAGE_SKU,
                            "version": "22.04.202606010",
                            "urn": (
                                f"{cpu.IMAGE_PUBLISHER}:{cpu.IMAGE_OFFER}:"
                                f"{cpu.IMAGE_SKU}:22.04.202606010"
                            ),
                        },
                        {
                            "publisher": cpu.IMAGE_PUBLISHER,
                            "offer": cpu.IMAGE_OFFER,
                            "sku": cpu.IMAGE_SKU,
                            "version": "22.04.202607010",
                            "urn": exact_image,
                        },
                    ]
                if arguments[:4] == ["network", "vnet", "subnet", "show"]:
                    return {
                        "id": self.subnet,
                        "defaultOutboundAccess": False,
                        "networkSecurityGroup": {"id": "/nsg/private"},
                        "routeTable": {"id": "/routes/through-firewall"},
                    }
                if arguments[:2] == ["group", "create"]:
                    return {"name": "tg-private"}
                if arguments[:2] == ["vm", "create"]:
                    self.assertIn(exact_image, arguments)
                    self.assertNotIn(cpu.OFFICIAL_LATEST_IMAGE, arguments)
                    return {
                        "id": "/subscriptions/s/vms/tg-cpu-000",
                        "privateIpAddress": "10.0.0.4",
                        "publicIpAddress": "",
                    }
                if arguments[:2] == ["vm", "show"]:
                    return self.vm_record(cpu.DEFAULT_SKU, exact_image)
                if arguments[:3] == ["network", "nic", "show"]:
                    return {
                        "id": "/networkInterfaces/tg-cpu-000",
                        "ipConfigurations": [
                            {
                                "privateIPAddress": "10.0.0.4",
                                "publicIPAddress": None,
                            }
                        ],
                    }
                self.fail(f"unexpected Azure command: {arguments}")

            with mock.patch.object(cpu, "_run_az", side_effect=fake_az):
                result = cpu.deploy(args)

        self.assertTrue(result["accepted"])
        self.assertEqual(result["resolved_image"], exact_image)
        self.assertEqual(result["resources_proven_attested"], 0)
        self.assertFalse(result["attestation_collected"])
        security = result["virtual_machines"][0]["security_profile"]
        self.assertEqual(security["security_type"], "ConfidentialVM")
        self.assertTrue(security["secure_boot"])
        self.assertTrue(security["vtpm"])
        self.assertEqual(
            security["os_disk_security_encryption_type"],
            "DiskWithVMGuestState",
        )
        self.assertTrue(any(command[:2] == ["vm", "show"] for command in seen))
        self.assertTrue(
            any(command[:3] == ["network", "nic", "show"] for command in seen)
        )

    def test_created_vm_inspection_rejects_every_security_downgrade(self) -> None:
        image = (
            f"{cpu.IMAGE_PUBLISHER}:{cpu.IMAGE_OFFER}:{cpu.IMAGE_SKU}:"
            "22.04.202607010"
        )
        original = self.vm_record(cpu.DEFAULT_SKU, image)
        cases = (
            (("securityProfile", "securityType"), "TrustedLaunch", "ConfidentialVM"),
            (("securityProfile", "uefiSettings", "secureBootEnabled"), False, "Secure Boot"),
            (("securityProfile", "uefiSettings", "vTpmEnabled"), False, "vTPM"),
            (
                (
                    "storageProfile",
                    "osDisk",
                    "managedDisk",
                    "securityProfile",
                    "securityEncryptionType",
                ),
                "VMGuestStateOnly",
                "DiskWithVMGuestState",
            ),
        )
        for path, value, message in cases:
            with self.subTest(path=path):
                record = copy.deepcopy(original)
                cursor = record
                for key in path[:-1]:
                    cursor = cursor[key]
                cursor[path[-1]] = value
                with self.assertRaisesRegex(cpu.AzurePlanError, message):
                    cpu._verify_created_vm(record, sku=cpu.DEFAULT_SKU, image=image)

        with self.assertRaisesRegex(cpu.AzurePlanError, "public IP address"):
            cpu._verify_private_nic(
                {
                    "id": "/networkInterfaces/tg-cpu-000",
                    "ipConfigurations": [
                        {
                            "privateIPAddress": "10.0.0.4",
                            "publicIPAddress": {"id": "/publicIPAddresses/bad"},
                        }
                    ],
                },
                expected_id="/networkInterfaces/tg-cpu-000",
            )

    def test_live_deploy_rejects_nonprivate_subnet_before_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ssh_key = Path(temporary) / "operator.pub"
            ssh_key.write_text("ssh-ed25519 AAAATEST operator@example.invalid\n")
            args = cpu.build_parser().parse_args(
                [
                    "deploy",
                    "--subscription",
                    self.subscription,
                    "--location",
                    "eastus2",
                    "--nodes",
                    "1",
                    "--resource-group",
                    "tg-private",
                    "--name-prefix",
                    "tg-cpu",
                    "--admin-username",
                    "tgoperator",
                    "--ssh-key",
                    str(ssh_key),
                    "--subnet-id",
                    self.subnet,
                    "--image",
                    "Canonical:offer:sku:1.2.3",
                ]
            )
            with mock.patch.object(
                cpu,
                "preflight",
                return_value={"accepted": True, "capacity_guaranteed": False},
            ), mock.patch.object(
                cpu,
                "_run_az",
                return_value={
                    "defaultOutboundAccess": True,
                    "networkSecurityGroup": {"id": "/nsg/private"},
                },
            ) as run:
                with self.assertRaisesRegex(cpu.AzurePlanError, "subnet is not private"):
                    cpu.deploy(args)
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
