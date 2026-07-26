# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
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
    specification.loader.exec_module(module)
    return module


azure = load_module("gpu_prover_azure_ncc", "azure/ncc_h100.py")
challenges = load_module(
    "gpu_prover_azure_challenges", "azure/create_attestation_challenges.py"
)
evidence = load_module(
    "gpu_prover_azure_evidence", "attestation/collect_azure_ncc_evidence.py"
)


class AzureNccH100Tests(unittest.TestCase):
    def test_collector_resolves_bare_tools_against_fixed_path(self) -> None:
        with mock.patch.object(
            evidence.shutil, "which", return_value="/usr/bin/nvidia-smi"
        ) as which:
            self.assertEqual(evidence._which("nvidia-smi"), "/usr/bin/nvidia-smi")
        which.assert_called_once_with(
            "nvidia-smi", path=evidence.SYSTEM_EXECUTABLE_PATH
        )

    def test_collector_subprocess_drops_hostile_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            command = [
                sys.executable,
                "-c",
                (
                    "import json,os; print(json.dumps({"
                    "'ld': os.environ.get('LD_PRELOAD'),"
                    "'python': os.environ.get('PYTHONPATH'),"
                    "'nv': os.environ.get('NV_ATTESTATION_SERVICE_KEY'),"
                    "'path': os.environ.get('PATH')}))"
                ),
            ]
            with mock.patch.dict(
                os.environ,
                {
                    "LD_PRELOAD": "/attacker/preload.so",
                    "PYTHONPATH": "/attacker/modules",
                    "NV_ATTESTATION_SERVICE_KEY": "remote-secret",
                },
                clear=False,
            ):
                result = json.loads(
                    evidence._run(command, directory=root, label="sanitized")
                )
            self.assertIsNone(result["ld"])
            self.assertIsNone(result["python"])
            self.assertIsNone(result["nv"])
            self.assertEqual(result["path"], evidence.SYSTEM_EXECUTABLE_PATH)

    def test_nv_service_key_only_reaches_exact_remote_nvattest_and_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / "nvattest"
            fake.write_text(
                "#!/usr/bin/python3\n"
                "import os, sys\n"
                "secret = os.environ['NV_ATTESTATION_SERVICE_KEY']\n"
                "print(secret)\n"
                "print(secret, file=sys.stderr)\n",
                encoding="utf-8",
            )
            fake.chmod(0o700)
            exact_remote_command = [
                str(fake),
                "--log-level",
                "error",
                "--format",
                "json",
                "attest",
                "--device",
                "gpu",
                "--verifier",
                "remote",
                "--gpu-evidence-source",
                "file",
                "--nras-url",
                "https://nras.attestation.nvidia.com",
            ]
            with mock.patch.dict(
                os.environ,
                {"NV_ATTESTATION_SERVICE_KEY": "never-retain-this-secret"},
                clear=False,
            ):
                output = evidence._run(
                    exact_remote_command,
                    directory=root,
                    label="nvattest_attest",
                    include_nvidia_service_key=True,
                )
                with self.assertRaisesRegex(evidence.EvidenceError, "only to exact"):
                    evidence._run(
                        [sys.executable, "-c", "pass"],
                        directory=root,
                        label="wrong-command",
                        include_nvidia_service_key=True,
                    )
            for retained in (
                output,
                (root / "nvattest_attest.stdout.txt").read_text(),
                (root / "nvattest_attest.stderr.txt").read_text(),
            ):
                self.assertNotIn("never-retain-this-secret", retained)
                self.assertIn("<redacted-nvidia-service-key>", retained)

    def test_collector_subprocess_output_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(evidence.EvidenceError, "exceeded 1024 bytes"):
                evidence._run(
                    [sys.executable, "-c", "print('x' * 4096)"],
                    directory=root,
                    label="oversized",
                    maximum_output_bytes=1024,
                )
            self.assertLessEqual(
                (root / "oversized.stdout.txt").stat().st_size, 1024
            )

    def test_binding_nonce_has_exact_domain_and_order(self) -> None:
        challenge = "01" * 32
        statement = "a5" * 32
        expected = hashlib.sha256(
            (
                "sparkinterval.trusted-compute.result-binding.v1\n"
                f"start_challenge_sha256={challenge}\n"
                f"wire_statement_sha256={statement}\n"
            ).encode("ascii")
        ).hexdigest()
        self.assertEqual(evidence.derive_binding_nonce(challenge, statement), expected)
        self.assertNotEqual(
            evidence.derive_binding_nonce(challenge, statement),
            evidence.derive_binding_nonce(statement, challenge),
        )

    def test_maa_endpoint_must_be_explicit_exact_https_sevsnp_path(self) -> None:
        expected = (
            "https://provider.eus.attest.azure.net/attest/SevSnpVm"
            "?api-version=2022-08-01"
        )
        self.assertEqual(
            evidence.validate_maa_attestation_url(expected),
            (expected, "https://provider.eus.attest.azure.net"),
        )
        for invalid in (
            "http://provider.eus.attest.azure.net/attest/SevSnpVm?api-version=2022-08-01",
            "https://provider.eus.attest.azure.net/attest/SevSnpVm",
            "https://provider.eus.attest.azure.net/attest/SevSnpVm?api-version=latest",
            "https://provider.eus.attest.azure.net:443/attest/SevSnpVm?api-version=2022-08-01",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(evidence.EvidenceError):
                evidence.validate_maa_attestation_url(invalid)

    def test_challenges_are_canonical_unique_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "challenges"
            process = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY / "azure/create_attestation_challenges.py"),
                    "--campaign-id",
                    "campaign-1",
                    "--count",
                    "3",
                    "--output-dir",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(process.stdout)
            self.assertTrue(report["accepted"])
            loaded = [
                evidence.load_challenge(path)
                for path in sorted(output.glob("*.challenge.json"))
            ]
            self.assertEqual([item["shard_index"] for item in loaded], [0, 1, 2])
            self.assertEqual(len({item["nonce"] for item in loaded}), 3)
            self.assertTrue(all("expires_at_utc" in item for item in loaded))
            for path in output.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_preflight_dry_run_never_claims_capacity_or_acceptance(self) -> None:
        result = azure.preflight(
            subscription="00000000-0000-0000-0000-000000000000",
            location="eastus2",
            nodes=4,
            zone=None,
            dry_run=True,
        )
        self.assertFalse(result["accepted"])
        self.assertFalse(result["capacity_guaranteed"])
        self.assertEqual(result["required_vcpus"], 160)
        self.assertEqual(result["h100s"], 4)
        self.assertIn("list-skus", result["commands"]["sku"])
        self.assertIn("list-usage", result["commands"]["quota"])

    def test_deploy_dry_run_is_confidential_private_and_one_gpu_per_vm(self) -> None:
        process = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY / "azure/ncc_h100.py"),
                "deploy",
                "--subscription",
                "00000000-0000-0000-0000-000000000000",
                "--location",
                "eastus2",
                "--nodes",
                "2",
                "--resource-group",
                "tg-private",
                "--name-prefix",
                "tg-h100",
                "--admin-username",
                "tgoperator",
                "--ssh-key",
                "/does/not/exist.pub",
                "--subnet-id",
                "/subscriptions/s/resourceGroups/r/providers/Microsoft.Network/virtualNetworks/v/subnets/private",
                "--dry-run",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(process.stdout)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["h100s_per_vm"], 1)
        self.assertFalse(result["public_ip_addresses"])
        self.assertEqual(len(result["vm_commands"]), 2)
        for command in result["vm_commands"]:
            self.assertIn("Standard_NCC40ads_H100_v5", command)
            self.assertIn("ConfidentialVM", command)
            self.assertIn("DiskWithVMGuestState", command)
            self.assertIn("--enable-secure-boot", command)
            self.assertIn("--enable-vtpm", command)
            public_index = command.index("--public-ip-address")
            self.assertEqual(command[public_index + 1], "")

    def test_live_deploy_adapter_preserves_commands_and_pins_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            official_image = (
                f"/CommunityGalleries/{azure.PUBLIC_GALLERY}/Images/"
                f"{azure.UBUNTU_2204_IMAGE}/versions/4.3.3"
            )
            ssh_key = Path(temporary) / "operator.pub"
            ssh_key.write_text("ssh-ed25519 AAAATEST operator@example.invalid\n")
            parser = azure.build_parser()
            args = parser.parse_args(
                [
                    "deploy",
                    "--subscription",
                    "subscription-id",
                    "--location",
                    "eastus2",
                    "--nodes",
                    "1",
                    "--resource-group",
                    "tg-private",
                    "--name-prefix",
                    "tg-h100",
                    "--admin-username",
                    "tgoperator",
                    "--ssh-key",
                    str(ssh_key),
                    "--subnet-id",
                    "/subscriptions/s/resourceGroups/r/providers/Microsoft.Network/virtualNetworks/v/subnets/private",
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
                        "id": "subscription-id",
                        "tenantId": "tenant-id",
                        "state": "Enabled",
                    }
                if arguments[:2] == ["vm", "list-skus"]:
                    return [
                        {
                            "name": azure.SKU,
                            "family": "standardNCCadsH100v5Family",
                            "capabilities": [
                                {"name": "vCPUs", "value": "40"},
                                {"name": "GPUs", "value": "1"},
                                {"name": "MemoryGB", "value": "320"},
                                {"name": "HyperVGenerations", "value": "V2"},
                            ],
                            "restrictions": [],
                        }
                    ]
                if arguments[:2] == ["vm", "list-usage"]:
                    return [
                        {
                            "name": {
                                "value": "standardNCCads2023Family",
                                "localizedValue": "Standard NCCads2023 Family vCPUs",
                            },
                            "currentValue": 0,
                            "limit": 40,
                        },
                        {
                            "name": {
                                "value": "cores",
                                "localizedValue": "Total Regional vCPUs",
                            },
                            "currentValue": 0,
                            "limit": 40,
                        },
                    ]
                if arguments[:3] == ["sig", "image-version", "list-community"]:
                    return [
                        {
                            "id": official_image,
                            "name": "4.3.3",
                            "provisioningState": "Succeeded",
                        }
                    ]
                if arguments[:2] == ["group", "create"]:
                    self.assertEqual(arguments[-2:], ["--location", "eastus2"])
                    return {"name": "tg-private"}
                if arguments[:4] == ["network", "vnet", "subnet", "show"]:
                    return {
                        "id": args.subnet_id,
                        "defaultOutboundAccess": False,
                        "routeTable": {
                            "id": "/subscriptions/s/resourceGroups/r/providers/Microsoft.Network/routeTables/through-firewall"
                        },
                        "networkSecurityGroup": {
                            "id": "/subscriptions/s/resourceGroups/r/providers/Microsoft.Network/networkSecurityGroups/tg-private"
                        },
                    }
                if arguments[:2] == ["vm", "create"]:
                    self.assertNotIn("--only-show-errors", arguments)
                    self.assertIn(official_image, arguments)
                    return {
                        "id": "/subscriptions/s/vms/tg-h100-000",
                        "privateIpAddress": "10.0.0.4",
                        "publicIpAddress": "",
                    }
                if arguments[:2] == ["vm", "show"]:
                    vm_id = (
                        "/subscriptions/s/resourceGroups/tg-private/providers/"
                        "Microsoft.Compute/virtualMachines/tg-h100-000"
                    )
                    nic_id = (
                        "/subscriptions/s/resourceGroups/tg-private/providers/"
                        "Microsoft.Network/networkInterfaces/tg-h100-000VMNic"
                    )
                    return {
                        "hardwareProfile": {"vmSize": azure.SKU},
                        "id": vm_id,
                        "instanceView": {
                            "statuses": [
                                {"code": "ProvisioningState/succeeded"},
                                {"code": "PowerState/running"},
                            ]
                        },
                        "name": "tg-h100-000",
                        "networkProfile": {
                            "networkInterfaces": [{"id": nic_id, "primary": True}]
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
                                "communityGalleryImageId": official_image
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
                if arguments[:3] == ["network", "nic", "show"]:
                    return {
                        "id": (
                            "/subscriptions/s/resourceGroups/tg-private/providers/"
                            "Microsoft.Network/networkInterfaces/tg-h100-000VMNic"
                        ),
                        "ipConfigurations": [
                            {
                                "primary": True,
                                "privateIPAddress": "10.0.0.4",
                                "provisioningState": "Succeeded",
                                "publicIPAddress": None,
                            }
                        ],
                        "provisioningState": "Succeeded",
                        "virtualMachine": {
                            "id": (
                                "/subscriptions/s/resourceGroups/tg-private/providers/"
                                "Microsoft.Compute/virtualMachines/tg-h100-000"
                            )
                        },
                    }
                self.fail(f"unexpected Azure command: {arguments}")

            with mock.patch.object(azure, "_run_az", side_effect=fake_az):
                result = azure.deploy(args)
            self.assertTrue(result["accepted"])
            self.assertEqual(
                result["resolved_image"],
                official_image,
            )
            self.assertTrue(any(command[:2] == ["vm", "create"] for command in seen))
            self.assertTrue(any(command[:2] == ["vm", "show"] for command in seen))
            self.assertTrue(any(command[:3] == ["network", "nic", "show"] for command in seen))
            self.assertEqual(result["resources_proven_attested"], 0)

    def test_quota_requires_both_family_and_regional_headroom(self) -> None:
        rows = [
            {
                "name": {
                    "value": "standardNCCads2023Family",
                    "localizedValue": "Standard NCCads2023 Family vCPUs",
                },
                "currentValue": 40,
                "limit": 200,
            },
            {
                "name": {"value": "cores", "localizedValue": "Total Regional vCPUs"},
                "currentValue": 300,
                "limit": 500,
            },
        ]
        family = azure._quota_summary(azure._quota_row(rows, family=True), 160)
        regional = azure._quota_summary(azure._quota_row(rows, family=False), 160)
        self.assertEqual(family["available_vcpus"], 160)
        self.assertEqual(regional["available_vcpus"], 200)
        with self.assertRaisesRegex(azure.AzurePlanError, "insufficient"):
            azure._quota_summary(azure._quota_row(rows, family=True), 161)

    def test_custom_images_must_be_exact_immutable_versions(self) -> None:
        self.assertEqual(
            azure._validate_immutable_image_reference(
                "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:22.04.202607010"
            ),
            "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:22.04.202607010",
        )
        for mutable in (
            "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest",
            "/CommunityGalleries/g/Images/i/versions/latest",
            "arbitrary-image-name",
        ):
            with self.subTest(mutable=mutable), self.assertRaises(azure.AzurePlanError):
                azure._validate_immutable_image_reference(mutable)

    def test_official_image_resolution_rejects_cross_gallery_response(self) -> None:
        rows = [
            {
                "id": "/CommunityGalleries/attacker/Images/lookalike/versions/4.3.3",
                "name": "4.3.3",
                "provisioningState": "Succeeded",
            }
        ]
        with mock.patch.object(azure, "_run_az", return_value=rows):
            with self.assertRaisesRegex(azure.AzurePlanError, "no usable version"):
                azure._resolve_official_image("subscription-id", "eastus2")

    def test_challenge_rejects_more_than_one_trailing_newline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "challenge.json"
            challenge = challenges.build_challenges(
                "canonical",
                1,
                dt.datetime.now(dt.timezone.utc).replace(microsecond=0),
                60,
            )[0]
            path.write_bytes(challenges.canonical_json_bytes(challenge) + b"\n\n")
            with self.assertRaisesRegex(evidence.EvidenceError, "canonical JSON"):
                evidence.load_challenge(path)

    def test_vm_readback_rejects_disabled_vtpm(self) -> None:
        image = "/CommunityGalleries/g/Images/i/versions/4.3.3"
        value = {
            "hardwareProfile": {"vmSize": azure.SKU},
            "id": "/subscriptions/s/resourceGroups/r/providers/Microsoft.Compute/virtualMachines/v",
            "instanceView": {"statuses": [{"code": "ProvisioningState/succeeded"}]},
            "name": "v",
            "networkProfile": {
                "networkInterfaces": [
                    {
                        "id": "/subscriptions/s/resourceGroups/r/providers/Microsoft.Network/networkInterfaces/n",
                        "primary": True,
                    }
                ]
            },
            "provisioningState": "Succeeded",
            "securityProfile": {
                "securityType": "ConfidentialVM",
                "uefiSettings": {"secureBootEnabled": True, "vTpmEnabled": True},
            },
            "storageProfile": {
                "imageReference": {"communityGalleryImageId": image},
                "osDisk": {
                    "managedDisk": {
                        "securityProfile": {
                            "securityEncryptionType": "DiskWithVMGuestState"
                        }
                    }
                },
            },
        }
        bad = copy.deepcopy(value)
        bad["securityProfile"]["uefiSettings"]["vTpmEnabled"] = False
        with self.assertRaisesRegex(azure.AzurePlanError, "confidential shape"):
            azure._validate_vm_readback(bad, name="v", expected_image=image)

    def test_nic_readback_rejects_any_public_ip_resource(self) -> None:
        vm_id = "/subscriptions/s/resourceGroups/r/providers/Microsoft.Compute/virtualMachines/v"
        nic_id = "/subscriptions/s/resourceGroups/r/providers/Microsoft.Network/networkInterfaces/n"
        nic = {
            "id": nic_id,
            "ipConfigurations": [
                {
                    "primary": True,
                    "privateIPAddress": "10.1.2.3",
                    "provisioningState": "Succeeded",
                    "publicIPAddress": {"id": "/subscriptions/s/publicIPAddresses/p"},
                }
            ],
            "provisioningState": "Succeeded",
            "virtualMachine": {"id": vm_id},
        }
        with self.assertRaisesRegex(azure.AzurePlanError, "private-only"):
            azure._validate_nic_readback(nic, nic_id=nic_id, vm_id=vm_id)

    def test_preflight_rejects_malformed_account_and_sku_response_types(self) -> None:
        base = dict(
            subscription="subscription-id",
            location="eastus2",
            nodes=1,
            zone=None,
            dry_run=False,
        )
        with mock.patch.object(
            azure,
            "_run_az",
            side_effect=[{"azure-cli": "2.77.0"}, []],
        ), self.assertRaisesRegex(azure.AzurePlanError, "account response"):
            azure.preflight(**base)
        with mock.patch.object(
            azure,
            "_run_az",
            side_effect=[
                {"azure-cli": "2.77.0"},
                {"id": "subscription-id", "tenantId": "tenant-id", "state": "Enabled"},
                {"name": azure.SKU},
            ],
        ), self.assertRaisesRegex(azure.AzurePlanError, "SKU response"):
            azure.preflight(**base)

    def test_evidence_dry_run_does_not_require_root_or_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            challenge = challenges.build_challenges(
                "campaign-1", 1, dt.datetime.now(dt.timezone.utc)
            )[0]
            challenge_path = root / "challenge.json"
            challenge_path.write_bytes(challenges.canonical_json_bytes(challenge) + b"\n")
            statement = {"algorithm": "closed-v1", "nonce": challenge["nonce"]}
            statement_bytes = evidence.canonical_json_bytes(statement)
            statement_path = root / "statement.json"
            statement_path.write_bytes(statement_bytes + b"\n")
            statement_sha = hashlib.sha256(statement_bytes).hexdigest()
            process = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY / "attestation/collect_azure_ncc_evidence.py"),
                    "--challenge",
                    str(challenge_path),
                    "--backend",
                    "azure_ncc40ads_h100_v5",
                    "--statement-file",
                    str(statement_path),
                    "--statement-sha256",
                    statement_sha,
                    "--output-dir",
                    str(root / "evidence"),
                    "--maa-attestation-url",
                    (
                        "https://fixture.eus.attest.azure.net/attest/SevSnpVm"
                        "?api-version=2022-08-01"
                    ),
                    "--dry-run",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(process.stdout)
            self.assertFalse(result["accepted"])
            self.assertFalse(result["evidence_collected"])
            self.assertFalse(result["mathematical_result_proven"])
            self.assertFalse((root / "evidence").exists())
            self.assertEqual(
                result["maa_attestation_url"],
                "https://fixture.eus.attest.azure.net/attest/SevSnpVm"
                "?api-version=2022-08-01",
            )
            self.assertEqual(
                result["binding_nonce"],
                evidence.derive_binding_nonce(challenge["nonce"], statement_sha),
            )

    def test_nvidia_policy_requires_nonce_secure_boot_and_no_debug(self) -> None:
        policy = (REPOSITORY / "attestation/policies/gpu_prover_h100.rego").read_text()
        self.assertIn('result.secboot == true', policy)
        self.assertIn('result.dbgstat == "disabled"', policy)
        self.assertIn('attestation-report-nonce-match"] == true', policy)

    def test_collector_rejects_expired_and_future_challenges(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "challenge.json"
            now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
            cases = {
                "expired": challenges.build_challenges(
                    "expired", 1, now - dt.timedelta(hours=2), 60
                )[0],
                "future": challenges.build_challenges(
                    "future", 1, now + dt.timedelta(hours=1), 60
                )[0],
            }
            for label, challenge in cases.items():
                with self.subTest(label=label):
                    path.write_bytes(challenges.canonical_json_bytes(challenge) + b"\n")
                    with self.assertRaisesRegex(
                        evidence.EvidenceError, "current validity window"
                    ):
                        evidence.load_challenge(path)
        with self.assertRaisesRegex(challenges.ChallengeError, "ttl_seconds"):
            challenges.build_challenges(
                "too-long",
                1,
                dt.datetime.now(dt.timezone.utc),
                challenges.MAX_TTL_SECONDS + 1,
            )

    def test_gpu_state_rejects_h100_that_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            evidence,
            "_run",
            side_effect=[
                "0, NVIDIA H100, 9.0, 570.1, 96.00.5E.00.01\n",
                "CC status: ON\n",
                "CC Environment: PRODUCTION\n",
                "CC GPUs Ready State: Not Ready\n",
            ],
        ):
            with self.assertRaisesRegex(evidence.EvidenceError, "not Ready"):
                evidence._require_gpu_state(Path(temporary), "/fake/nvidia-smi")


if __name__ == "__main__":
    unittest.main()
