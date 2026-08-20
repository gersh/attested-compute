"""The hardening posture check must refuse a weakened compose.

This is unit-tested rather than driven through verify_run.py because it cannot
be reached that way: every evidence block is digest-checked before the compose
checks run, so a tampered document is rejected earlier.  A check that can only
be observed passing is not known to be a check at all.
"""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "attestation" / "phala"))

from verify_run import missing_posture  # noqa: E402

HARDENED = {
    "network_mode": "none",
    "read_only": True,
    "tmpfs": ["/tmp:rw,exec,nosuid,nodev,size=1g"],
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges:true"],
    "pids_limit": 512,
}


class PostureCheckTests(unittest.TestCase):
    def test_the_deployed_compose_passes(self):
        """The posture this repository actually deploys must satisfy the check."""
        compose = pathlib.Path(__file__).resolve().parents[2] / (
            "claude_math/audits/compcert/rh_phala/docker-compose.yaml")
        if not compose.exists():
            self.skipTest(f"no deployment compose at {compose}")
        text = compose.read_text()
        service = next(iter(json.loads(text[text.index("{"):])["services"].values()))
        self.assertEqual(missing_posture(service), [])

    def test_hardened_service_is_accepted(self):
        self.assertEqual(missing_posture(HARDENED), [])

    def test_each_declaration_is_load_bearing(self):
        """Dropping any one of them must be reported, by name."""
        for key in ("network_mode", "read_only", "cap_drop", "security_opt"):
            with self.subTest(dropped=key):
                weakened = {k: v for k, v in HARDENED.items() if k != key}
                self.assertIn(key, missing_posture(weakened))

    def test_a_noexec_tmpfs_is_rejected(self):
        """The trap that cost a rehearsal: Docker mounts a tmpfs noexec."""
        weakened = dict(HARDENED, tmpfs=["/tmp:rw,nosuid,nodev,size=1g"])
        self.assertIn("tmpfs /tmp exec", missing_posture(weakened))

    def test_exec_must_not_be_matched_as_a_substring(self):
        """`noexec` contains `exec`; splitting on commas is what stops that."""
        weakened = dict(HARDENED, tmpfs=["/tmp:rw,noexec,nosuid,size=1g"])
        self.assertIn("tmpfs /tmp exec", missing_posture(weakened))

    def test_a_missing_tmpfs_is_rejected(self):
        weakened = {k: v for k, v in HARDENED.items() if k != "tmpfs"}
        self.assertIn("tmpfs /tmp", missing_posture(weakened))

    def test_a_tmpfs_elsewhere_does_not_satisfy_it(self):
        weakened = dict(HARDENED, tmpfs=["/var/run:rw,exec,size=16m"])
        self.assertIn("tmpfs /tmp", missing_posture(weakened))

    def test_an_empty_service_is_rejected_entirely(self):
        self.assertEqual(len(missing_posture({})), len(HARDENED) - 2 + 1)


if __name__ == "__main__":
    unittest.main()
