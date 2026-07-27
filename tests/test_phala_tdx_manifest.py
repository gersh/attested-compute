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
CAMPAIGN_ENTRY = BUILD / "run_phala_tdx_campaign.sh"
EVIDENCE_EMITTER = BUILD / "emit_phala_tdx_evidence.py"
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

    def test_the_compose_embeds_everything_the_campaign_runs(self) -> None:
        """Whatever touches the key or the receipt must be inside RTMR3.

        The campaign container derives the signing key and decides what leaves
        the CVM, so its entry point, the deriver and the evidence emitter are
        embedded here rather than taken from the image -- the image is pinned
        by digest, but a change to these files would otherwise not move the
        compose hash without a republished image.
        """

        compose = load_yaml()
        if compose is None:  # pragma: no cover
            self.skipTest("PyYAML is unavailable")
        embedded = compose["services"]["campaign"]["entrypoint"][2]
        for source in (PRELUDE, CAMPAIGN_ENTRY, EVIDENCE_EMITTER):
            self.assertIn(
                source.read_text(encoding="utf-8"),
                embedded,
                f"{source.name} is not embedded verbatim in the campaign "
                "entry point",
            )
        # And it runs the embedded copies, not the ones baked into the image.
        self.assertNotIn("/opt/sparkinterval/run_phala_tdx_campaign.sh", embedded)

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

    def test_both_services_see_the_dstack_socket(self) -> None:
        """Deliberate, and not a relaxation of the network posture.

        The campaign container must derive the signing key itself: the key
        cannot be handed over on the shared volume, because that volume is
        disk-backed, and it cannot be handed over on a tmpfs-backed named
        volume, because such a volume is private to each container and arrives
        empty.  The socket is not network access -- `network_mode: none` still
        holds, and the next test asserts it.
        """

        for service in ("prelude", "campaign"):
            volumes = self.compose["services"][service]["volumes"]
            self.assertTrue(
                [v for v in volumes if v.startswith("/var/run/dstack.sock:")],
                f"{service} cannot reach the dstack guest agent",
            )

    def test_the_campaign_has_no_network_and_a_read_only_root(self) -> None:
        campaign = self.compose["services"]["campaign"]
        self.assertEqual(campaign["network_mode"], "none")
        self.assertIs(campaign["read_only"], True)

    def test_no_named_volume_is_tmpfs_backed(self) -> None:
        """The regression guard for the failure the first real run hit.

        A tmpfs-backed *named* volume is not shared between containers: every
        container that mounts it gets its own fresh, empty tmpfs.  The first
        run passed the whole attestation and then died with
        `job-scope.env: No such file or directory` because of it.  Cross-
        container data therefore travels on an ordinary volume, and secrets
        travel not at all.
        """

        for name, definition in (self.compose["volumes"] or {}).items():
            options = (definition or {}).get("driver_opts") or {}
            self.assertNotEqual(
                options.get("type"),
                "tmpfs",
                f"named volume {name} is tmpfs-backed, so it is NOT shared "
                "between containers and will arrive empty",
            )
            self.assertNotIn("tmpfs", str(options.get("device", "")))

    def test_the_derived_key_lives_only_on_a_container_local_tmpfs(self) -> None:
        """Service-level `tmpfs:` really is per-container; that is the point."""

        campaign = self.compose["services"]["campaign"]
        key_root = next(
            entry for entry in campaign["environment"]
            if entry.startswith("TG_ENCLAVE_KEY_ROOT=")
        ).split("=", 1)[1]
        self.assertTrue(
            [entry for entry in campaign["tmpfs"] if entry.startswith(key_root + ":")],
            f"{key_root} is not a container-local tmpfs",
        )
        # And it is not inside anything that is shared or written to disk.
        for volume in campaign["volumes"]:
            mounted = volume.split(":")[1]
            self.assertFalse(
                key_root == mounted or key_root.startswith(mounted.rstrip("/") + "/"),
                f"the key root {key_root} is inside the mounted volume {mounted}",
            )

    def test_the_campaign_derives_the_key_and_reads_no_key_file(self) -> None:
        entrypoint = self.compose["services"]["campaign"]["entrypoint"][2]
        self.assertIn("--derive-key-only", entrypoint)
        script = CAMPAIGN_ENTRY.read_text(encoding="utf-8")
        self.assertIn("--derive-key-only", script)
        self.assertIn("--enclave-key \"${ENCLAVE_KEY#/workspace/}\"", script)
        # The old contract was `require_input <input root>/enclave-signing-key.hex`.
        self.assertNotIn(
            'require_input "${INPUT_ROOT}/enclave-signing-key.hex"', script
        )
        # The prelude must not write one either.
        prelude = PRELUDE.read_text(encoding="utf-8")
        self.assertNotIn('input_root / "enclave-signing-key.hex"', prelude)

    def test_the_campaign_prints_the_evidence_and_stays_alive(self) -> None:
        """`phala cvms logs` is the only channel out of the CVM."""

        campaign = self.compose["services"]["campaign"]
        entrypoint = campaign["entrypoint"][2]
        self.assertIn("emit_phala_tdx_evidence.py", entrypoint)
        self.assertIn("--refuse-if-contains", entrypoint)
        self.assertIn('sleep "${TG_EVIDENCE_HOLD_SECONDS}"', entrypoint)
        hold = next(
            entry for entry in campaign["environment"]
            if entry.startswith("TG_EVIDENCE_HOLD_SECONDS=")
        ).split("=", 1)[1]
        self.assertGreaterEqual(int(hold), 3600)

    def test_a_failed_prelude_holds_open_but_still_fails(self) -> None:
        entrypoint = self.compose["services"]["prelude"]["entrypoint"][2]
        self.assertIn('sleep "${TG_PRELUDE_FAILURE_HOLD_SECONDS}"', entrypoint)
        self.assertIn('exit "$status"', entrypoint)
        # The hold is on the failure branch only, so a successful prelude
        # still exits promptly and the campaign still starts.
        self.assertIn('if [ "$status" -ne 0 ]; then', entrypoint)

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

    def test_the_manifest_never_enables_the_local_dry_run(self) -> None:
        """The entry point reads that marker; the manifest must never set it.

        The embedded entry point mentions the variable, because it is the
        thing that refuses to honour `--local-dry-run` without it.  What must
        not appear anywhere is an assignment of it, or the flag itself.
        """

        text = COMPOSE.read_text(encoding="utf-8")
        self.assertNotIn("SPARKINTERVAL_PHALA_TDX_LOCAL_DRY_RUN=", text)
        self.assertNotIn("--local-dry-run\n", text)
        for service in self.compose["services"].values():
            for entry in service["environment"]:
                self.assertFalse(
                    entry.startswith("SPARKINTERVAL_PHALA_TDX_LOCAL_DRY_RUN"),
                    "the manifest declares the dry-run marker",
                )

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

    def test_every_measurement_is_a_todo_or_a_well_formed_reviewed_pin(
        self,
    ) -> None:
        """No measurement may be a wildcard, a null, or a malformed value.

        The template shipped with every pin as `TODO:` until the 2026-07-27
        discovery run on Phala's prod5 host supplied the platform
        measurements.  A pin may therefore now be a real value, but only one
        of the exact shape the prelude requires: there is no wildcard, no
        null, and no short or upper-case digest.  `rt_mr3` may additionally be
        the one named sentinel, and only it -- the prelude refuses that
        sentinel for any other measurement.
        """

        digits = {
            "tee_tcb_svn": 32,
            "mr_seam": 96,
            "mr_signer_seam": 96,
            "td_attributes": 16,
            "xfam": 16,
            "mr_td": 96,
            "rt_mr0": 96,
            "rt_mr1": 96,
            "rt_mr2": 96,
            "rt_mr3": 96,
        }
        replay_sentinel = "verified-by-event-log-replay"
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(k for k in policy["measurements"] if not k.startswith("_")),
            sorted(digits),
        )
        for name, width in digits.items():
            value = policy["measurements"][name]
            self.assertIsInstance(value, str, f"measurements.{name}")
            if value.startswith("TODO:"):
                continue
            if name == "rt_mr3" and value == replay_sentinel:
                continue
            self.assertRegex(
                value,
                rf"\A[0-9a-f]{{{width}}}\Z",
                f"measurements.{name} is neither a TODO, nor the replay "
                f"sentinel, nor {width} lowercase hex digits: {value!r}",
            )
        self.assertIn(replay_sentinel, PRELUDE.read_text(encoding="utf-8"))

        qe = policy["qe_identity"]
        for name, width in (("qe_vendor_id", 32), ("mr_signer", 64)):
            value = qe[name]
            self.assertIsInstance(value, str, f"qe_identity.{name}")
            if not value.startswith("TODO:"):
                self.assertRegex(value, rf"\A[0-9a-f]{{{width}}}\Z")
        for name in ("isv_prod_id", "min_isv_svn"):
            value = qe[name]
            if isinstance(value, str):
                self.assertTrue(value.startswith("TODO:"), f"qe_identity.{name}")
            else:
                self.assertIsInstance(value, int, f"qe_identity.{name}")
                self.assertNotIsInstance(value, bool)
                self.assertGreaterEqual(value, 0)

    def test_rt_mr3_is_never_pinned_to_one_observed_boot(self) -> None:
        """It is a function of the compose bytes, so a literal is a trap."""

        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        value = policy["measurements"]["rt_mr3"]
        self.assertTrue(
            value.startswith("TODO:") or value == "verified-by-event-log-replay",
            f"rt_mr3 is pinned to a literal boot value: {value!r}",
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
