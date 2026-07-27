# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""The committed dstack manifest is exactly what the generator produces.

``proof_build/ch25_a7_phala_tdx/docker-compose.yaml`` embeds the prelude's
Python source verbatim, and ``app-compose.json`` embeds that compose file
verbatim.  The embedding is what puts the prelude inside the compose hash and
therefore inside RTMR3, so the two copies must never drift: an edit to
``prelude_phala_tdx_inputs.py`` that is not regenerated would ship code that
the quote does not measure.

These are source checks.  They need no network, no Docker and no TDX.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "proof_build/ch25_a7_phala_tdx"
GENERATOR = ROOT / "tools/tg_phala_tdx_compose.py"
PRELUDE = BUILD / "prelude_phala_tdx_inputs.py"
COMPOSE = BUILD / "docker-compose.yaml"
APP_COMPOSE = BUILD / "app-compose.json"
POLICY = BUILD / "dcap-qvl-policy.json"
DCAP_SPEC = ROOT / "specifications/DCAP_QVL_0_6_1_UPSTREAM.json"

IMAGE_DIGEST = (
    "sha256:4e6029a39771bd18f9e0b9bc64017393700ce47c17a678dd93cbf0ddc17c774f"
)
IMAGE = "ghcr.io/gersh/sparkinterval-ch25-a7-phala-tdx@" + IMAGE_DIGEST


def load_yaml():
    try:
        import yaml  # noqa: PLC0415
    except ImportError:  # pragma: no cover
        return None
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


class ManifestGenerationTests(unittest.TestCase):
    def test_committed_manifest_matches_the_generator(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    "--template",
                    "--out-dir",
                    scratch,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            for name, committed in (
                ("docker-compose.yaml", COMPOSE),
                ("app-compose.json", APP_COMPOSE),
            ):
                self.assertEqual(
                    (Path(scratch) / name).read_bytes(),
                    committed.read_bytes(),
                    f"{name} is stale; re-run "
                    "`python3 tools/tg_phala_tdx_compose.py --template`",
                )

    def test_the_compose_embeds_the_prelude_verbatim(self) -> None:
        """The measured copy must be the repository copy, byte for byte.

        The compose file carries the prelude inside a YAML block scalar, so
        the comparison is against the parsed scalar rather than the raw file
        text: the raw text is the same bytes plus a uniform indent.
        """

        compose = load_yaml()
        if compose is None:  # pragma: no cover
            self.skipTest("PyYAML is unavailable")
        embedded = compose["services"]["prelude"]["entrypoint"][2]
        self.assertIn(PRELUDE.read_text(encoding="utf-8"), embedded)

    def test_the_app_compose_embeds_the_compose_verbatim(self) -> None:
        document = json.loads(APP_COMPOSE.read_text(encoding="utf-8"))
        self.assertEqual(
            document["docker_compose_file"], COMPOSE.read_text(encoding="utf-8")
        )

    def test_the_reported_compose_hash_is_the_file_digest(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(GENERATOR), "--template", "--print-only"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        match = re.search(r"compose_hash\)\s*:\s*([0-9a-f]{64})", completed.stdout)
        assert match
        self.assertEqual(
            match.group(1),
            hashlib.sha256(APP_COMPOSE.read_bytes()).hexdigest(),
        )


class ManifestContentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compose = load_yaml()
        if self.compose is None:  # pragma: no cover
            self.skipTest("PyYAML is unavailable")

    def test_the_image_is_referenced_by_digest_never_by_tag(self) -> None:
        text = COMPOSE.read_text(encoding="utf-8")
        for service in self.compose["services"].values():
            self.assertEqual(service["image"], IMAGE)
            self.assertIn("@sha256:", service["image"])
        self.assertNotIn(
            "sparkinterval-ch25-a7-phala-tdx:", text,
            "the manifest references the image by tag somewhere",
        )

    def test_the_campaign_waits_for_the_prelude_to_succeed(self) -> None:
        depends = self.compose["services"]["campaign"]["depends_on"]
        self.assertEqual(
            depends["prelude"]["condition"], "service_completed_successfully"
        )

    def test_only_the_prelude_sees_the_dstack_socket(self) -> None:
        prelude = self.compose["services"]["prelude"]["volumes"]
        campaign = self.compose["services"]["campaign"]["volumes"]
        self.assertIn("/var/run/dstack.sock:/var/run/dstack.sock", prelude)
        self.assertFalse([v for v in campaign if "dstack.sock" in v])

    def test_the_campaign_has_no_network_and_a_read_only_root(self) -> None:
        campaign = self.compose["services"]["campaign"]
        self.assertEqual(campaign["network_mode"], "none")
        self.assertIs(campaign["read_only"], True)

    def test_the_staging_volume_is_a_tmpfs(self) -> None:
        """The derived signing key must never reach the CVM's disk."""

        staging = self.compose["volumes"]["campaign-staging"]
        self.assertEqual(staging["driver_opts"]["type"], "tmpfs")

    def test_the_six_worker_variables_are_set(self) -> None:
        for service in ("prelude", "campaign"):
            environment = self.compose["services"][service]["environment"]
            joined = "\n".join(environment)
            for name in (
                "SPARKINTERVAL_PHALA_TDX_WORKER_SCOPE",
                "SPARKINTERVAL_PHALA_TDX_WORKER_BACKEND",
                "SPARKINTERVAL_PHALA_TDX_WORKER_CHALLENGE_NONCE",
                "SPARKINTERVAL_PHALA_TDX_WORKER_JOB_BINDING_SHA256",
                "TG_FINAL_IMAGE_REFERENCE",
                "TG_ISSUED_AT",
            ):
                self.assertIn(name + "=", joined, f"{service} lacks {name}")
        # The remaining two cannot be literals: the compose hash is the digest
        # of the document that would have to contain it.  The prelude reads
        # them from the guest agent, checks them against what RTMR3 attests,
        # and the campaign shim sources them from job-scope.env.
        for service in ("prelude", "campaign"):
            joined = "\n".join(self.compose["services"][service]["environment"])
            self.assertNotIn("SPARKINTERVAL_PHALA_TDX_WORKER_APP_ID=", joined)
            self.assertNotIn("SPARKINTERVAL_PHALA_TDX_WORKER_COMPOSE_HASH=", joined)
        self.assertIn(
            "job-scope.env",
            self.compose["services"]["campaign"]["entrypoint"][2],
        )

    def test_the_template_challenge_is_a_refusal_sentinel(self) -> None:
        """A committed template must not be deployable as-is."""

        sys.path.insert(0, str(ROOT))
        from tg_verifier.campaign_io import (  # noqa: PLC0415
            PhalaTdxWorkerScopeError,
            require_phala_tdx_worker,
        )

        joined = "\n".join(self.compose["services"]["campaign"]["environment"])
        match = re.search(
            r"SPARKINTERVAL_PHALA_TDX_WORKER_CHALLENGE_NONCE=(\S+)", joined
        )
        assert match
        with self.assertRaises(PhalaTdxWorkerScopeError):
            require_phala_tdx_worker(
                challenge_nonce=match.group(1),
                job_binding=match.group(1),
                environment={},
            )

    def test_no_local_dry_run_marker_anywhere_in_the_manifest(self) -> None:
        text = COMPOSE.read_text(encoding="utf-8")
        self.assertNotIn("SPARKINTERVAL_PHALA_TDX_LOCAL_DRY_RUN", text)

    def test_the_app_compose_declares_the_unmeasured_inputs(self) -> None:
        document = json.loads(APP_COMPOSE.read_text(encoding="utf-8"))
        self.assertEqual(document["runner"], "docker-compose")
        self.assertEqual(
            sorted(document["allowed_envs"]),
            ["TG_A7_ARTIFACT_URL", "TG_DCAP_QVL_POLICY_B64"],
        )
        self.assertIs(document["no_instance_id"], True)
        self.assertIs(document["public_logs"], False)


class AppraiserPinTests(unittest.TestCase):
    def test_the_prelude_and_the_specification_pin_the_same_binary(self) -> None:
        spec = json.loads(DCAP_SPEC.read_text(encoding="utf-8"))
        asset = spec["assets"][spec["selected_asset"]]
        source = PRELUDE.read_text(encoding="utf-8")
        self.assertIn(f'DCAP_QVL_SHA256 = (\n    "{asset["sha256"]}"\n)', source)
        self.assertIn(asset["url"].rsplit("/", 1)[-1], source)
        self.assertIn(spec["commit"], source)
        self.assertIn(spec["version"], source)

    def test_the_policy_template_pins_the_same_binary(self) -> None:
        spec = json.loads(DCAP_SPEC.read_text(encoding="utf-8"))
        asset = spec["assets"][spec["selected_asset"]]
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        self.assertEqual(policy["appraiser"]["sha256"], asset["sha256"])
        self.assertEqual(policy["appraiser"]["commit"], spec["commit"])

    def test_the_policy_template_ships_with_discovery_off(self) -> None:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        self.assertIs(policy["first_run_measurement_discovery"], False)

    def test_every_measurement_in_the_template_is_an_explicit_todo(self) -> None:
        """No measurement may be a wildcard, a null, or a fabricated value."""

        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        for section in ("measurements", "qe_identity"):
            for name, value in policy[section].items():
                if name.startswith("_"):
                    continue
                self.assertIsInstance(value, str, f"{section}.{name}")
                self.assertTrue(
                    value.startswith("TODO:"),
                    f"{section}.{name} is neither a TODO nor reviewed: {value!r}",
                )

    def test_the_template_accepts_no_advisory_and_only_uptodate(self) -> None:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        self.assertEqual(policy["tcb"]["accepted_advisory_ids"], [])
        for key in (
            "allowed_statuses",
            "allowed_platform_statuses",
            "allowed_qe_statuses",
        ):
            self.assertEqual(policy["tcb"][key], ["UpToDate"])

    def test_the_prelude_pins_the_retained_artifact_digest(self) -> None:
        source = PRELUDE.read_text(encoding="utf-8")
        self.assertIn(
            "ccc11cecdc398c9d0a9bcf2b1bd4994399557985fe17bc216f0a40eb8eb49f29",
            source,
        )
        self.assertIn("RETAINED_ARTIFACT_BYTES = 1_494_999", source)


if __name__ == "__main__":
    unittest.main()
