# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from dataclasses import replace
import unittest

from tg_verifier.transitive_child_manifest import (
    Backend,
    CHILD,
    HEADER,
    HISTORICAL_GOLDBACH_SPEC,
    Manifest,
    ManifestError,
    PLATT_DIRICHLET_SPEC,
    R2STAR_SPEC,
    ChildEntry,
    decode,
    encode,
    validate,
)


def digest(value: int) -> bytes:
    return bytes([value]) * 32


def manifest_for(spec) -> Manifest:
    children = []
    predecessor = spec.root_digest
    count = len(spec.expected_backends)
    for ordinal, backend in enumerate(spec.expected_backends):
        lower = (
            spec.source_lower
            if ordinal == 0
            else children[-1].upper
        )
        upper = (
            spec.source_upper
            if ordinal + 1 == count
            else spec.source_lower + ordinal + 1
        )
        entry = ChildEntry(
            ordinal=ordinal,
            lower=lower,
            upper=upper,
            backend=backend,
            receipt_digest=digest(4 + ordinal % 250),
            artifact_digest=digest(5 + ordinal % 250),
            result_digest=digest(6 + ordinal % 250),
            predecessor_digest=predecessor,
        )
        children.append(entry)
        predecessor = entry.receipt_digest
    return Manifest(
        campaign_tag=spec.campaign_tag,
        source_lower=spec.source_lower,
        source_upper=spec.source_upper,
        root_digest=spec.root_digest,
        children=tuple(children),
    )


class TransitiveChildManifestTests(unittest.TestCase):
    def test_r2star_exact_round_trip_and_lean_sizes(self) -> None:
        manifest = validate(manifest_for(R2STAR_SPEC), R2STAR_SPEC)
        raw = encode(manifest)
        self.assertEqual(len(raw), 62 + 149)
        self.assertEqual(HEADER.size, 62)
        self.assertEqual(CHILD.size, 149)
        self.assertEqual(decode(raw), manifest)

    def test_exact_production_topologies_are_typed(self) -> None:
        self.assertEqual(
            R2STAR_SPEC.expected_backends,
            (Backend.AZURE_NCCADS_H100_V5,),
        )
        self.assertEqual(
            len(HISTORICAL_GOLDBACH_SPEC.expected_backends), 8_512
        )
        self.assertEqual(
            HISTORICAL_GOLDBACH_SPEC.expected_backends[:8_192],
            (Backend.AZURE_NCCADS_H100_V5,) * 8_192,
        )
        self.assertEqual(
            HISTORICAL_GOLDBACH_SPEC.expected_backends[8_192:],
            (Backend.AZURE_SEVSNP_CPU,) * 320,
        )
        self.assertEqual(
            PLATT_DIRICHLET_SPEC.expected_backends,
            (Backend.AZURE_SEVSNP_CPU, Backend.AZURE_SEVSNP_CPU),
        )

    def test_truncation_trailing_bytes_and_unknown_backend_fail(self) -> None:
        raw = encode(manifest_for(R2STAR_SPEC))
        for changed in (raw[:-1], raw + b"\x00"):
            with self.assertRaises(ManifestError):
                decode(changed)
        changed = bytearray(raw)
        changed[HEADER.size + 20] = 255
        with self.assertRaisesRegex(ManifestError, "unknown backend"):
            decode(bytes(changed))

    def test_chain_and_retained_artifact_substitution_fail(self) -> None:
        manifest = manifest_for(R2STAR_SPEC)
        child = manifest.children[0]
        for changed_child in (
            replace(child, predecessor_digest=digest(99)),
            replace(child, lower=2),
            replace(child, upper=1),
            replace(child, artifact_digest=b"\x00" * 32),
        ):
            with self.assertRaises(ManifestError):
                validate(
                    replace(manifest, children=(changed_child,)), R2STAR_SPEC
                )


if __name__ == "__main__":
    unittest.main()
