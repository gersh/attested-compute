# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


def extract_braced_body(source: str, needle: str) -> str:
    start = source.index(needle)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening : index + 1]
    raise AssertionError(f"unterminated function body after {needle!r}")


def assert_tokens_in_order(
    test: unittest.TestCase, source: str, tokens: list[str]
) -> None:
    cursor = 0
    for token in tokens:
        next_cursor = source.find(token, cursor)
        test.assertNotEqual(
            next_cursor, -1, f"missing ordered formula token {token!r}"
        )
        cursor = next_cursor + len(token)


class PT21DDSloppyMulQualificationTests(unittest.TestCase):
    def test_source_keeps_qualification_isolated(self) -> None:
        source = (
            ROOT / "reference" / "tg_platt_dd_sloppy_mul_qualification.cu"
        ).read_text()
        production = (
            ROOT
            / "gpu"
            / "platform"
            / "h100"
            / "h100_tg_platt_windowed_dd_disk_semantic.cu"
        ).read_text()
        public_header = (
            ROOT
            / "gpu"
            / "include"
            / "sparkinterval"
            / "tg_platt_dd_transform.hpp"
        ).read_text()
        cmake = (ROOT / "CMakeLists.txt").read_text()

        self.assertIn("fast_mul_center", source)
        self.assertIn("kRnRelativeError", source)
        self.assertIn("cpp_rational", source)
        self.assertIn("SPARKINTERVAL_CUDA_FTZ_DISABLED", source)
        self.assertIn("kStatusNonfiniteIntermediate", source)
        self.assertIn("canonical_corpus_bytes", source)
        self.assertIn("json_escape(properties.name)", source)
        self.assertIn(
            "SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION", production
        )
        guarded_header = public_header[
            public_header.index(
                "#if defined("
                "SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION)"
            ) :
        ]
        self.assertIn(
            "run_source_window_sloppy_root_qualification", guarded_header
        )
        ordinary_body = production[
            production.index("void run_source_window(\n") :
            production.index("void run_source_window_tile9_qualification(")
        ]
        self.assertNotIn("sloppy_root", ordinary_body)
        self.assertEqual(
            hashlib.sha256(ordinary_body.encode()).hexdigest(),
            "89c15418506d386e2b678aef8cae3787"
            "a1934cfdf94831b1010df3b826b9ecd1",
        )
        self.assertIn(
            "dd_qualification_fast_mul_center", production
        )
        self.assertIn(
            "dd_qualification_fast_add_center", production
        )
        self.assertIn(
            "dd_disk_mul_known_y_norm_sloppy_qualification", production
        )
        production_target = cmake[
            cmake.index(
                "add_library(sparkinterval-tg-platt-dd-transform STATIC"
            ) :
            cmake.index(
                "add_executable(sparkinterval-tg-platt-dd-transform-api-smoke"
            )
        ]
        self.assertNotIn(
            "SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION",
            production_target,
        )
        qualification_target = cmake[
            cmake.index(
                "add_library(\n"
                "    sparkinterval-tg-platt-dd-sloppy-root-transform-"
                "qualification STATIC"
            ) :
            cmake.index(
                "add_executable(sparkinterval-tg-platt-event-scan-benchmark"
            )
        ]
        self.assertIn(
            "SPARKINTERVAL_ENABLE_SLOPPY_ROOT_QUALIFICATION",
            qualification_target,
        )

    def test_integrated_formula_matches_pinned_review_manifest(self) -> None:
        standalone = (
            ROOT / "reference" / "tg_platt_dd_sloppy_mul_qualification.cu"
        ).read_text()
        integrated = (
            ROOT
            / "gpu"
            / "platform"
            / "h100"
            / "h100_tg_platt_windowed_dd_disk_semantic.cu"
        ).read_text()
        bodies = {
            "standalone_add": extract_braced_body(
                standalone, "fast_add_center(DD"
            ),
            "standalone_mul": extract_braced_body(
                standalone, "fast_mul_center(DD"
            ),
            "standalone_disk": extract_braced_body(
                standalone, "disk_root_mul("
            ),
            "integrated_add": extract_braced_body(
                integrated, "dd_qualification_fast_add_center(DD"
            ),
            "integrated_mul": extract_braced_body(
                integrated, "dd_qualification_fast_mul_center(DD"
            ),
            "integrated_disk": extract_braced_body(
                integrated,
                "dd_disk_mul_known_y_norm_sloppy_qualification(",
            ),
        }
        expected_sha256 = {
            "standalone_add":
                "b58d4cb25b6799cd5c8209ea769510e4"
                "342aa4ad430d15c18f45b9265709afe2",
            "standalone_mul":
                "bb4f40b4e32cd70f44e063959d8c13bd"
                "c74d56923bcb55815f808b124d68fbf8",
            "standalone_disk":
                "8d2064517e421fd006b484ae54773931a"
                "1c3b18c9892ab5adec5711ae001c912",
            "integrated_add":
                "90d76178b24aa3bbc2ce0fcc51677e18b"
                "803e884c9f8976612e27edd37d35010",
            "integrated_mul":
                "0784cf64a9681dd591a7d2f987f979f8"
                "5fa4a5adc92a8867c9bf71f3f3713457",
            "integrated_disk":
                "15b810261c4e41d70a2dd6586d58bd3e"
                "5326a4d20dbb46dd461e93d6813d3b78",
        }
        self.assertEqual(
            {
                name: hashlib.sha256(body.encode()).hexdigest()
                for name, body in bodies.items()
            },
            expected_sha256,
        )
        assert_tokens_in_order(
            self,
            bodies["standalone_add"],
            [
                "two_sum(a.hi, b.hi)",
                "__dadd_rn(a.lo, b.lo)",
                "__dadd_rn(high.residual, low_parts)",
                "two_sum(high.sum, low)",
                "rn_error(low_parts)",
                "rn_error(low)",
                "2.0 * kFastTwoSumFloors",
            ],
        )
        assert_tokens_in_order(
            self,
            bodies["integrated_add"],
            [
                "dd_two_sum(a.hi, b.hi)",
                "__dadd_rn(a.lo, b.lo)",
                "__dadd_rn(high.residual, low_parts)",
                "dd_two_sum(high.sum, low)",
                "dd_qualification_rn_error(low_parts)",
                "dd_qualification_rn_error(low)",
                "kQualificationFastAddFloors",
            ],
        )
        for name, prefix, floor in (
            ("standalone_mul", "", "kFastTwoSumFloors"),
            (
                "integrated_mul",
                "dd_qualification_",
                "kQualificationFastMulFloors",
            ),
        ):
            two_product = (
                "two_product(a.hi, b.hi)"
                if not prefix
                else "dd_two_product(a.hi, b.hi)"
            )
            two_sum = (
                "two_sum(leading.sum, low)"
                if not prefix
                else "dd_two_sum(leading.sum, low)"
            )
            rn_error = (
                "rn_error" if not prefix
                else "dd_qualification_rn_error"
            )
            assert_tokens_in_order(
                self,
                bodies[name],
                [
                    two_product,
                    "__dmul_rn(a.hi, b.lo)",
                    "__dmul_rn(a.lo, b.hi)",
                    "__dadd_rn(cross0, cross1)",
                    "__dadd_rn(leading.residual, cross)",
                    two_sum,
                    f"{rn_error}(cross0)",
                    f"{rn_error}(cross1)",
                    f"{rn_error}(cross)",
                    f"{rn_error}(low)",
                    "__dmul_ru(fabs(a.lo), fabs(b.lo))",
                    floor,
                ],
            )
        assert_tokens_in_order(
            self,
            bodies["standalone_disk"],
            [
                "rr",
                "ii",
                "real",
                "real_error",
                "ri",
                "ir",
                "imaginary",
                "imaginary_error",
                "local_error",
                "left_norm",
                "__dmul_ru(left_norm, input.right.radius)",
                "__dmul_ru(input.right_center_norm_bound, input.left.radius)",
                "__dmul_ru(input.left.radius, input.right.radius)",
            ],
        )
        assert_tokens_in_order(
            self,
            bodies["integrated_disk"],
            [
                "rr",
                "ii",
                "re",
                "re_error",
                "ri",
                "ir",
                "im",
                "im_error",
                "local_error",
                "x_center_l1",
                "__dmul_ru(x_center_l1, y.radius)",
                "__dmul_ru(y_center_norm_upper, x.radius)",
                "__dmul_ru(x.radius, y.radius)",
            ],
        )
        for token in (
            "constexpr double kDDFloor = 0x0.0000000000001p-1022;",
            "constexpr double kRnRelativeError = 0x1.0000000000001p-53;",
            "constexpr double kFastTwoSumFloors = 6.0 * kDDFloor;",
        ):
            self.assertIn(token, standalone)
        for token in (
            "kQualificationRnRelativeError =\n"
            "    0x1.0000000000001p-53;",
            "kQualificationFastMulFloors = 6.0 * kDDFloor;",
            "kQualificationFastAddFloors = 12.0 * kDDFloor;",
        ):
            self.assertIn(token, integrated)

    @unittest.skipUnless(
        os.environ.get("TG_PLATT_DD_SLOPPY_MUL_QUALIFICATION"),
        "qualification executable is not configured",
    )
    def test_cuda_exact_dyadic_known_answers(self) -> None:
        completed = subprocess.run(
            [
                os.environ["TG_PLATT_DD_SLOPPY_MUL_QUALIFICATION"],
                "--repetitions=3",
                "--benchmark-log2=16",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        report = json.loads(completed.stdout)
        self.assertEqual(
            report["schema"],
            "sparkinterval.tg.platt-dd-sloppy-mul-qualification.v1",
        )
        self.assertTrue(report["accepted"])
        self.assertTrue(report["qualification_only"])
        self.assertFalse(report["production_transform_modified"])
        self.assertFalse(report["cuda_to_lean_refinement_claimed"])
        self.assertTrue(report["ftz_disabled_compile_contract"])
        self.assertEqual(
            set(report["build_profile"]),
            {
                "cmake_build_config",
                "ndebug_defined",
                "release_performance_build",
            },
        )
        self.assertIsInstance(
            report["build_profile"]["cmake_build_config"], str
        )
        self.assertIsInstance(
            report["build_profile"]["ndebug_defined"], bool
        )
        self.assertIsInstance(
            report["build_profile"]["release_performance_build"], bool
        )
        self.assertIsInstance(report["device_profile"], dict)
        self.assertTrue(report["device_profile"]["name"])
        self.assertTrue(report["device_profile"]["compute_capability"])
        self.assertEqual(report["corpus_count"], 8192)
        self.assertEqual(report["nonpadding_case_count"], 4113)
        self.assertEqual(report["pt21_like_case_count"], 4096)
        self.assertEqual(
            report["corpus_encoding"],
            "caseinput-v1-little-endian-iec559-binary64",
        )
        self.assertEqual(
            report["corpus_sha256"],
            "50738ee7a4b57069c074b8cbdc373ed6"
            "feb0e90991f8ec364b68b8cef725f6c7",
        )
        self.assertEqual(report["corpus_fnv1a64"], "c514385c1781a38e")
        self.assertEqual(report["expected_kernel_reject_count"], 3)
        self.assertEqual(report["expected_exact_checker_reject_count"], 1)
        self.assertEqual(report["expected_invalid_input_reason_count"], 2)
        self.assertEqual(
            report["expected_nonfinite_intermediate_reason_count"], 1
        )
        for implementation in ("full", "fast"):
            self.assertEqual(
                report[
                    f"{implementation}_expected_status_reason_match_count"
                ],
                3,
            )
            self.assertEqual(
                report[
                    f"{implementation}_expected_invalid_input_reason_match_count"
                ],
                2,
            )
            self.assertEqual(
                report[
                    f"{implementation}_expected_nonfinite_intermediate_reason_match_count"
                ],
                1,
            )
            self.assertEqual(
                report[
                    f"{implementation}_expected_exact_checker_catch_count"
                ],
                1,
            )
            self.assertEqual(
                report[
                    f"{implementation}_expected_right_norm_checker_catch_count"
                ],
                1,
            )
            self.assertEqual(
                report[f"{implementation}_expected_behavior_mismatch_count"],
                0,
            )
        self.assertEqual(report["unexpected_full_kernel_reject_count"], 0)
        self.assertEqual(report["unexpected_fast_kernel_reject_count"], 0)
        self.assertEqual(report["full_exact_dyadic_failure_count"], 0)
        self.assertEqual(report["fast_exact_dyadic_failure_count"], 0)
        self.assertTrue(report["near_tight_fast_add_exact_bound"])
        self.assertTrue(report["near_tight_fast_add_reserved_zero"])
        self.assertTrue(report["near_tight_fast_add_expected_result_bits"])
        self.assertTrue(report["near_tight_fast_add_expected_error_bits"])
        self.assertTrue(report["near_tight_fast_add_expected_exact_error"])
        self.assertEqual(report["direct_fast_mul_case_count"], 8)
        self.assertEqual(report["direct_fast_mul_exact_failure_count"], 0)
        self.assertGreaterEqual(
            report["maximum_pt21_like_radius_inflation"],
            report["p99_pt21_like_radius_inflation"],
        )
        self.assertGreaterEqual(
            report["p99_pt21_like_radius_inflation"],
            report["p90_pt21_like_radius_inflation"],
        )
        self.assertGreaterEqual(
            report["p90_pt21_like_radius_inflation"],
            report["median_pt21_like_radius_inflation"],
        )
        self.assertGreater(report["full_median_ms"], 0.0)
        self.assertGreater(report["fast_median_ms"], 0.0)
        self.assertGreater(report["median_speedup"], 0.0)
        self.assertEqual(report["benchmark_input_profile"], "pt21-like-only")
        self.assertEqual(report["full_local_bytes"], 0)
        self.assertEqual(report["fast_local_bytes"], 0)
        self.assertEqual(
            report["arithmetic_checker"],
            "independent-exact-binary64-dyadic-cpp-rational",
        )


if __name__ == "__main__":
    unittest.main()
