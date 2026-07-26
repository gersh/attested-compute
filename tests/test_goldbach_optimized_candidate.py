#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tg_verifier.campaign_io import canonical_json_bytes
from tg_verifier.goldbach_optimized_candidate import (
    EXPECTED_CROSSCHECK_SOURCE_BYTES,
    EXPECTED_CROSSCHECK_SOURCE_SHA256,
    GoldbachOptimizedCandidateError,
    _KERNELS,
    _closure_rows,
    _closure_sha256,
    _MANIFEST_DOMAIN,
    _validate_component_kat_result,
    audit_sm90_ptx,
    audit_sm90_sass,
    bounded_full_differential,
    crosscheck_goldbach_source,
    validate_candidate_package,
)


def _ptx_fixture() -> str:
    bodies = {
        "byte_count": "atom.global.add.u32 %r1, [%rd1], 1;",
        "word_owner": "st.global.u64 [%rd1], %rd2;",
        "warp_sieve": "atom.global.and.b64 %rd1, [%rd2], %rd3;",
        "tail_sieve": "atom.global.and.b64 %rd1, [%rd2], %rd3;",
        "shifted_coverage": "\n".join(
            [
                "ld.global.nc.u64 %rd1, [%rd2];",
                "ld.global.nc.u64 %rd3, [%rd4];",
                "ld.global.nc.u64 %rd5, [%rd6];",
                "or.b64 %rd7, %rd1, %rd3;",
                "or.b64 %rd8, %rd7, %rd5;",
                "st.global.u64 [%rd9], %rd8;",
            ]
        ),
        "coverage_expand": "ld.global.nc.u64 %rd1, [%rd2];",
        "packed_count": "\n".join(
            [
                "popc.b64 %r1, %rd1;",
                "atom.global.add.u32 %r2, [%rd2], %r1;",
            ]
        ),
        "fallback_phase1": "ret;",
    }
    return (
        ".version 9.0\n.target sm_90\n.address_size 64\n"
        + "\n".join(
            f".visible .entry {_KERNELS[name]}() {{\n{bodies[name]}\n}}"
            for name in _KERNELS
        )
        + "\n"
    )


def _sass_fixture() -> str:
    bodies = {
        "byte_count": "POPC R1, R2 ;\nREDG.E.ADD.STRONG.GPU x ;",
        "word_owner": "STG.E.64 [R2], R4 ;",
        "warp_sieve": "REDG.E.AND.64.STRONG.GPU x ;",
        "tail_sieve": "REDG.E.AND.64.STRONG.GPU x ;",
        "shifted_coverage": "LOP3.LUT R1, R2, R3, RZ, 0xfe, !PT ;",
        "coverage_expand": "LDG.E.64 R2, [R4] ;",
        "packed_count": (
            "POPC R1, R2 ;\nPOPC R3, R4 ;\n"
            "REDG.E.ADD.STRONG.GPU x ;"
        ),
        "fallback_phase1": "EXIT ;",
    }
    return "\t.target\tsm_90\n" + "\n".join(
        (
            f"//--------------------- .text.{_KERNELS[name]} "
            "--------------------------\n"
            f".section .text.{_KERNELS[name]}\n{bodies[name]}"
        )
        for name in _KERNELS
    )


class GoldbachOptimizedCandidateTests(unittest.TestCase):
    def test_strict_ptx_and_sass_audits_accept_only_exact_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ptx = root / "candidate.ptx"
            sass = root / "candidate.sass"
            ptx.write_text(_ptx_fixture(), encoding="utf-8")
            sass.write_text(_sass_fixture(), encoding="utf-8")
            self.assertTrue(audit_sm90_ptx(ptx)["accepted"])
            self.assertTrue(audit_sm90_sass(sass)["accepted"])

            ptx.write_text(
                _ptx_fixture().replace("atom.global.and.b64", "and.b64", 1),
                encoding="utf-8",
            )
            with self.assertRaises(GoldbachOptimizedCandidateError):
                audit_sm90_ptx(ptx)
            sass.write_text(
                _sass_fixture().replace(
                    "REDG.E.AND.64.STRONG.GPU",
                    "REDG.E.AND.32.STRONG.GPU",
                    1,
                ),
                encoding="utf-8",
            )
            with self.assertRaises(GoldbachOptimizedCandidateError):
                audit_sm90_sass(sass)
            ptx.write_text(
                _ptx_fixture()
                + (
                    f".visible .entry {_KERNELS['word_owner']}() "
                    "{ ret; }\n"
                ),
                encoding="utf-8",
            )
            with self.assertRaises(GoldbachOptimizedCandidateError):
                audit_sm90_ptx(ptx)
            sass.write_text(
                _sass_fixture()
                + (
                    "\n//--------------------- .text."
                    f"{_KERNELS['word_owner']} --------------------------\n"
                ),
                encoding="utf-8",
            )
            with self.assertRaises(GoldbachOptimizedCandidateError):
                audit_sm90_sass(sass)

    def test_component_kat_requires_the_fixed_answer(self) -> None:
        value = {
            "accepted": True,
            "compute_capability": "12.1",
            "kind": "sparkinterval.goldbach-wheel-filter-kat.v1",
            "odd_count_per_window": 1 << 18,
            "cofactor_filter_limit": 47,
            "prime_limit": 131_071,
            "tail_prime_count": 11_942,
            "warp_parallel_cutoff": 32_749,
            "warp_prime_count": 3_203,
            "wheel_modulus": 15_015,
            "window_count": 4,
            "windows": [
                {
                    "fnv1a64": digest,
                    "q_high": high,
                    "q_low": low,
                    "set_bits": bits,
                }
                for digest, high, low, bits in (
                    ("c5a02e2b2bb2b0d0", "4524287", "4000001", 72_597),
                    ("869bd81a9a1827a4", "4680287", "4156001", 72_479),
                    (
                        "bb99908cdab9d2e6",
                        "31249998799524289",
                        "31249998799000003",
                        47_131,
                    ),
                    (
                        "ac6c9b891d576bbb",
                        "18446744073709551615",
                        "18446744073709027329",
                        47_130,
                    ),
                )
            ],
            "word_owner_cutoff": 2_039,
        }
        self.assertEqual(
            _validate_component_kat_result("wheel_filter", value), value
        )
        value["windows"][0]["fnv1a64"] = "0" * 16
        with self.assertRaises(GoldbachOptimizedCandidateError):
            _validate_component_kat_result("wheel_filter", value)

    def test_crosscheck_source_has_the_reviewed_identity_when_available(
        self,
    ) -> None:
        source = Path("/tmp/tg-goldbach-prepared-v2/src/goldbach.cu")
        if not source.is_file():
            self.skipTest("prepared GoldbachGPU source is absent")
        transformed = crosscheck_goldbach_source(
            source.read_text(encoding="utf-8")
        )
        self.assertEqual(
            len(transformed.encode("utf-8")),
            EXPECTED_CROSSCHECK_SOURCE_BYTES,
        )
        self.assertEqual(
            hashlib.sha256(transformed.encode("utf-8")).hexdigest(),
            EXPECTED_CROSSCHECK_SOURCE_SHA256,
        )
        for message in (
            "wheel-filtered sieve differs from unfiltered sieve",
            "shifted phase 1 differs from original phase 1",
            "packed missing-bit count differs from byte count",
        ):
            self.assertEqual(transformed.count(message), 1)

    def test_bounded_differential_refuses_an_unbounded_request_early(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            GoldbachOptimizedCandidateError, "600-million-even cap"
        ):
            bounded_full_differential(
                Path("/does/not/exist"),
                nvcc=Path("/does/not/exist"),
                host_cxx=Path("/does/not/exist"),
                even_start=4,
                even_limit=1_200_000_004,
            )

    def test_retained_local_package_freshly_revalidates_when_available(
        self,
    ) -> None:
        package = Path("/tmp/tg-goldbach-qualified-0725-e")
        if not package.is_dir():
            self.skipTest("retained local qualification package is absent")
        manifest = validate_candidate_package(package)
        self.assertFalse(manifest["trust_status"]["target_h100_measured"])
        self.assertFalse(
            manifest["trust_status"]["production_identity_promoted"]
        )
        self.assertEqual(manifest["build"]["arch"], "sm_90")

    def test_revalidation_rejects_a_self_hashed_artifact_pin_attack(
        self,
    ) -> None:
        package = Path("/tmp/tg-goldbach-qualified-0725-e")
        if not package.is_dir():
            self.skipTest("retained local qualification package is absent")
        with tempfile.TemporaryDirectory() as temporary:
            attacked = Path(temporary) / "candidate"
            shutil.copytree(package, attacked)
            manifest_path = attacked / "candidate-manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            manifest["artifacts"]["executable"]["sha256"] = "0" * 64
            body = dict(manifest)
            del body["manifest_sha256"]
            manifest["manifest_sha256"] = hashlib.sha256(
                _MANIFEST_DOMAIN + canonical_json_bytes(body)
            ).hexdigest()
            manifest_path.write_bytes(canonical_json_bytes(manifest))
            with self.assertRaisesRegex(
                GoldbachOptimizedCandidateError, "artifact pins differ"
            ):
                validate_candidate_package(attacked)

    def test_revalidation_rejects_a_self_hashed_script_substitution(
        self,
    ) -> None:
        package = Path("/tmp/tg-goldbach-qualified-0725-e")
        if not package.is_dir():
            self.skipTest("retained local qualification package is absent")
        with tempfile.TemporaryDirectory() as temporary:
            attacked = Path(temporary) / "candidate"
            shutil.copytree(package, attacked)
            executable = attacked / "artifacts/goldbach-gpu"
            executable.write_bytes(b"#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
            manifest_path = attacked / "candidate-manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            manifest["artifacts"]["executable"] = {
                "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "size_bytes": executable.stat().st_size,
            }
            rows = _closure_rows(attacked)
            manifest["closure_files"] = rows
            manifest["closure_sha256"] = _closure_sha256(rows)
            body = dict(manifest)
            del body["manifest_sha256"]
            manifest["manifest_sha256"] = hashlib.sha256(
                _MANIFEST_DOMAIN + canonical_json_bytes(body)
            ).hexdigest()
            manifest_path.write_bytes(canonical_json_bytes(manifest))
            with self.assertRaisesRegex(
                GoldbachOptimizedCandidateError, "64-bit.*ELF"
            ):
                validate_candidate_package(attacked)

    def test_production_validation_requires_an_external_reviewed_pin(
        self,
    ) -> None:
        package = Path("/tmp/tg-goldbach-qualified-0725-e")
        if not package.is_dir():
            self.skipTest("retained local qualification package is absent")
        manifest_file_sha256 = hashlib.sha256(
            (package / "candidate-manifest.json").read_bytes()
        ).hexdigest()
        with self.assertRaisesRegex(
            GoldbachOptimizedCandidateError, "production candidate.*unconfigured"
        ):
            validate_candidate_package(
                package,
                expected_manifest_file_sha256=manifest_file_sha256,
                require_reviewed_production=True,
            )
        with patch(
            "tg_verifier.goldbach_optimized_candidate."
            "REVIEWED_PRODUCTION_CANDIDATE_MANIFEST_FILE_SHA256S",
            frozenset({manifest_file_sha256}),
        ):
            with self.assertRaisesRegex(
                GoldbachOptimizedCandidateError, "requires an x86_64"
            ):
                validate_candidate_package(
                    package,
                    expected_manifest_file_sha256=manifest_file_sha256,
                    require_reviewed_production=True,
                )
        with self.assertRaisesRegex(
            GoldbachOptimizedCandidateError, "external file pin"
        ):
            validate_candidate_package(
                package,
                expected_manifest_file_sha256="0" * 64,
            )

    def test_external_pin_rejects_a_self_consistent_alternate_elf(
        self,
    ) -> None:
        package = Path("/tmp/tg-goldbach-qualified-0725-e")
        replacement = Path("/bin/true")
        if not package.is_dir() or not replacement.is_file():
            self.skipTest("retained package or alternate ELF is absent")
        original_manifest_file_sha256 = hashlib.sha256(
            (package / "candidate-manifest.json").read_bytes()
        ).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            attacked = Path(temporary) / "candidate"
            shutil.copytree(package, attacked)
            executable = attacked / "artifacts/goldbach-gpu"
            executable.write_bytes(replacement.read_bytes())
            executable.chmod(0o755)
            manifest_path = attacked / "candidate-manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            manifest["artifacts"]["executable"] = {
                "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "size_bytes": executable.stat().st_size,
            }
            rows = _closure_rows(attacked)
            manifest["closure_files"] = rows
            manifest["closure_sha256"] = _closure_sha256(rows)
            body = dict(manifest)
            del body["manifest_sha256"]
            manifest["manifest_sha256"] = hashlib.sha256(
                _MANIFEST_DOMAIN + canonical_json_bytes(body)
            ).hexdigest()
            manifest_path.write_bytes(canonical_json_bytes(manifest))

            # The alternate file is a structurally valid host ELF. Internal
            # candidate checks are qualification checks, not build authority.
            validate_candidate_package(attacked)
            with self.assertRaisesRegex(
                GoldbachOptimizedCandidateError, "external file pin"
            ):
                validate_candidate_package(
                    attacked,
                    expected_manifest_file_sha256=(
                        original_manifest_file_sha256
                    ),
                    require_reviewed_production=True,
                )


if __name__ == "__main__":
    unittest.main()
