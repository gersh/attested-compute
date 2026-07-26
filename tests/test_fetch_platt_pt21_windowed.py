# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fetch_platt_pt21_windowed",
    ROOT / "tools" / "fetch_platt_pt21_windowed.py",
)
assert SPEC is not None and SPEC.loader is not None
FETCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FETCH)


class PlattInterpolationCorrectionTests(unittest.TestCase):
    def test_patch_and_upstream_identity_are_pinned(self) -> None:
        patch = FETCH.INTERPOLATION_CORRECTION.read_bytes()
        self.assertEqual(
            hashlib.sha256(patch).hexdigest(),
            FETCH.INTERPOLATION_CORRECTION_SHA256,
        )
        self.assertEqual(
            patch.count(b"+  arb_add(f_res,f_res,intererr,prec);"), 1
        )
        manifest = json.loads(
            (ROOT / "specifications" / "PLATT_PT21_WINDOWED_UPSTREAM.json").read_text(
                encoding="utf-8"
            )
        )
        rows = {row["path"]: row for row in manifest["files"]}
        self.assertEqual(
            rows["zeta_arb/inter.c"]["sha256"], FETCH.UPSTREAM_INTER_C_SHA256
        )
        self.assertEqual(
            rows["zeta_arb/parameters.h"]["sha256"],
            FETCH.UPSTREAM_PARAMETERS_H_SHA256,
        )
        self.assertNotEqual(
            FETCH.UPSTREAM_INTER_C_SHA256, FETCH.CORRECTED_INTER_C_SHA256
        )
        self.assertNotEqual(
            FETCH.UPSTREAM_PARAMETERS_H_SHA256,
            FETCH.CORRECTED_PARAMETERS_H_SHA256,
        )

    def test_tampered_patch_fails_before_source_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            patch = root / "tampered.patch"
            patch.write_bytes(FETCH.INTERPOLATION_CORRECTION.read_bytes() + b"\n")
            with mock.patch.object(FETCH, "INTERPOLATION_CORRECTION", patch):
                with self.assertRaisesRegex(
                    FETCH.PlattWindowedSourceError, "patch differs"
                ):
                    FETCH.prepare_corrected_source(
                        root / "missing-checkout", root / "destination"
                    )

    def test_unreviewed_inter_source_fails_before_patch(self) -> None:
        reviewed_names = (
            "Makefile",
            "arb_fft.h",
            "arb_win_zeta.h",
            "arb_zeta.c",
            "inter.c",
            "inter.h",
            "parameters.h",
            "turing.c",
            "turing.h",
            "win_zeta.c",
            "win_zeta.h",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "checkout" / "zeta_arb"
            source.mkdir(parents=True)
            for name in reviewed_names:
                (source / name).write_text("unreviewed\n", encoding="utf-8")
            with self.assertRaisesRegex(
                FETCH.PlattWindowedSourceError, "unreviewed inter.c"
            ):
                FETCH.prepare_corrected_source(
                    root / "checkout", root / "destination"
                )


if __name__ == "__main__":
    unittest.main()
