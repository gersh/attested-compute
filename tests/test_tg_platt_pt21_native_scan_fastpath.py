# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from tests.test_tg_platt_pt21_native_record_adapter import (
    required_packet,
    point,
    stationary_trace,
    turing_inputs,
    worker,
)
from tg_verifier.platt_pt21_fused_artifact import (
    _is_stationary_candidate_exact,
)
from tg_verifier.platt_pt21_native_record_adapter import (
    PT21NativeRecordAdapterError,
    adapt_block,
    adapt_block_native_scan_fastpath,
    adapt_block_native_scan_session,
    worker_identity,
)
from tg_verifier.platt_pt21_native_scan_fastpath import (
    CERTIFICATE_DOMAIN,
    CERTIFICATE_HEADER,
    NativeScanSession,
    PT21NativeScanFastpathError,
    STREAM_REQUEST_HEADER,
    STREAM_REQUEST_MAGIC,
    STREAM_RANGES,
    _pinned_scanner,
    arithmetic_range_report,
    run_native_scan_certificate,
    scan_required_sign_packet,
    scan_required_sign_packet_with_session,
    validate_native_scan_certificate,
)
from tg_verifier.platt_required_sign_packet import (
    HEADER,
    REQUIRED_COUNT,
    SAMPLE,
    _fnv1a,
    load_required_sign_packet,
)


def _rewrite_samples(
    path: Path, replacements: dict[int, tuple[float, float, float]]
) -> bytes:
    raw = bytearray(path.read_bytes())
    fields = list(HEADER.unpack_from(raw))
    sample_start = HEADER.size
    sample_bytes = REQUIRED_COUNT * SAMPLE.size
    sign_start = sample_start + sample_bytes
    signs = bytearray((REQUIRED_COUNT + 7) // 8)
    for index in range(REQUIRED_COUNT):
        offset = index - 12_870
        if offset in replacements:
            high, low, radius = replacements[offset]
            SAMPLE.pack_into(
                raw,
                sample_start + index * SAMPLE.size,
                high,
                low,
                radius,
            )
        else:
            high, _low, _radius = SAMPLE.unpack_from(
                raw, sample_start + index * SAMPLE.size
            )
        if high > 0.0:
            signs[index // 8] |= 1 << (index % 8)
    raw[sign_start:] = signs
    fields[14] = _fnv1a(bytes(raw[sample_start:sign_start]))
    fields[15] = _fnv1a(bytes(signs))
    raw[: HEADER.size] = HEADER.pack(*fields)
    path.write_bytes(raw)
    return bytes(raw)


def _reference_lists(
    path: Path,
) -> tuple[
    tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]],
    tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]],
]:
    packet = load_required_sign_packet(path)
    direct: list[tuple[int, ...]] = []
    stationary: list[tuple[int, ...]] = []
    for lower, upper in STREAM_RANGES:
        direct.append(
            tuple(
                offset
                for offset in range(lower, upper)
                if packet.samples[offset + 12_870].positive
                != packet.samples[offset + 1 + 12_870].positive
            )
        )
        stationary.append(
            tuple(
                offset
                for offset in range(lower, upper - 1)
                if _is_stationary_candidate_exact(
                    packet.samples, offset
                )
            )
        )
    return (
        (direct[0], direct[1], direct[2]),
        (stationary[0], stationary[1], stationary[2]),
    )


class PT21NativeScanFastpathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        supplied = os.environ.get("TG_PLATT_PT21_NATIVE_SCAN_FASTPATH")
        if not supplied:
            raise unittest.SkipTest(
                "TG_PLATT_PT21_NATIVE_SCAN_FASTPATH is not configured"
            )
        cls.scanner = Path(supplied)
        if not cls.scanner.is_file() or not os.access(cls.scanner, os.X_OK):
            raise unittest.SkipTest(
                "TG_PLATT_PT21_NATIVE_SCAN_FASTPATH is not executable"
            )
        cls.scanner_sha256 = hashlib.sha256(
            cls.scanner.read_bytes()
        ).hexdigest()

    def scan(self, packet: Path):
        return scan_required_sign_packet(
            packet,
            scanner=self.scanner,
            expected_scanner_sha256=self.scanner_sha256,
        )

    def test_byte_identical_pt21blk1_and_all_ephemeral_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = required_packet(directory, 0)
            stationary = stationary_trace(directory, 0)
            turing = turing_inputs(directory, packet, 0, 1)
            identity = worker_identity(worker(directory))
            reference = adapt_block(
                required_sign_packet=packet,
                stationary_trace=stationary,
                turing_inputs=turing,
                worker=identity,
            )
            qualified = adapt_block_native_scan_fastpath(
                required_sign_packet=packet,
                stationary_trace=stationary,
                turing_inputs=turing,
                worker=identity,
                native_scanner=self.scanner,
                expected_native_scanner_sha256=self.scanner_sha256,
            )
            self.assertEqual(qualified.adapted.record, reference.record)
            self.assertEqual(
                qualified.adapted.source_trace, reference.source_trace
            )
            self.assertEqual(
                qualified.adapted.block_artifact, reference.block_artifact
            )
            self.assertEqual(
                qualified.scan.scanner.sha256, self.scanner_sha256
            )
            self.assertEqual(
                qualified.scan.packet_sha256,
                hashlib.sha256(packet.read_bytes()).hexdigest(),
            )

    def test_large_dyadic_turing_tail_remains_exact_and_byte_identical(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = required_packet(directory, 0)
            stationary = stationary_trace(directory, 0)
            turing = turing_inputs(directory, packet, 0, 1)
            value = json.loads(turing.read_bytes())
            pi = Fraction((1 << 200) + 1, 1 << 199)
            self.assertGreater(pi.denominator.bit_length(), 128)
            common = Fraction(21)
            for side in ("lower", "upper"):
                raw_side = value["inputs"][side]
                a = raw_side["interval"]["a"]
                b = raw_side["interval"]["b"]
                log_term = Fraction(-(a + b), 4) * 21
                raw_side["values"]["pi"] = point(pi)
                raw_side["values"]["im_gamma_integral"] = point(
                    common * pi - log_term
                )
            turing.write_bytes(
                json.dumps(
                    value, sort_keys=True, separators=(",", ":")
                ).encode()
                + b"\n"
            )
            identity = worker_identity(worker(directory))
            reference = adapt_block(
                required_sign_packet=packet,
                stationary_trace=stationary,
                turing_inputs=turing,
                worker=identity,
            )
            qualified = adapt_block_native_scan_fastpath(
                required_sign_packet=packet,
                stationary_trace=stationary,
                turing_inputs=turing,
                worker=identity,
                native_scanner=self.scanner,
                expected_native_scanner_sha256=self.scanner_sha256,
            )
            self.assertEqual(qualified.adapted.record, reference.record)
            self.assertEqual(
                qualified.adapted.block_artifact, reference.block_artifact
            )

    def test_adversarial_boundaries_extremes_and_exact_fallback(self) -> None:
        cases = (
            {
                -12_800: (2.0, 0.0, 0.0),
                -12_799: (-2.0, 0.0, 0.0),
                -12_288: (3.0, 0.0, 0.0),
                12_287: (4.0, 0.0, 0.0),
                12_288: (-4.0, 0.0, 0.0),
                12_799: (5.0, 0.0, 0.0),
                12_800: (-5.0, 0.0, 0.0),
            },
            {
                -1_001: (2.0, 0.0, 0.0),
                -1_000: (1.0, 0.0, 0.0),
                -999: (2.0, 0.0, 0.0),
                999: (-2.0, 0.0, 0.0),
                1_000: (-1.0, 0.0, 0.0),
                1_001: (-2.0, 0.0, 0.0),
            },
            {
                -101: (1.0, 2.0**-53, 0.0),
                -100: (1.0, 0.0, 0.0),
                -99: (1.0, 2.0**-53, 0.0),
                99: (
                    float.fromhex("0x0.0000000000002p-1022"),
                    0.0,
                    0.0,
                ),
                100: (
                    float.fromhex("0x0.0000000000001p-1022"),
                    0.0,
                    0.0,
                ),
                101: (
                    float.fromhex("0x0.0000000000002p-1022"),
                    0.0,
                    0.0,
                ),
                299: (
                    float.fromhex("0x1.fffffffffffffp+1023"),
                    0.0,
                    0.0,
                ),
                300: (
                    float.fromhex("0x1.ffffffffffffep+1023"),
                    0.0,
                    0.0,
                ),
                301: (
                    float.fromhex("0x1.fffffffffffffp+1023"),
                    0.0,
                    0.0,
                ),
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for index, replacements in enumerate(cases):
                with self.subTest(case=index):
                    packet = required_packet(directory, index)
                    _rewrite_samples(packet, replacements)
                    scan = self.scan(packet)
                    direct, stationary = _reference_lists(packet)
                    self.assertEqual(scan.direct_offsets, direct)
                    self.assertEqual(scan.stationary_offsets, stationary)
                    if index == 2:
                        self.assertGreaterEqual(
                            scan.exact_fraction_fallback_count, 3
                        )
                    packet.unlink()

    def test_certificate_and_identity_tampering_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = required_packet(directory, 0)
            raw = packet.read_bytes()
            certificate, identity, _seconds = run_native_scan_certificate(
                raw,
                scanner=self.scanner,
                expected_scanner_sha256=self.scanner_sha256,
            )
            mutations = (
                certificate[:-1],
                bytes([certificate[0] ^ 1]) + certificate[1:],
                certificate[: CERTIFICATE_HEADER.size]
                + bytes([certificate[CERTIFICATE_HEADER.size] ^ 1])
                + certificate[CERTIFICATE_HEADER.size + 1 :],
            )
            for mutation in mutations:
                with self.subTest(length=len(mutation)):
                    with self.assertRaises(PT21NativeScanFastpathError):
                        validate_native_scan_certificate(
                            raw, mutation, scanner=identity
                        )

            forged = bytearray(certificate)
            body = bytearray(forged[CERTIFICATE_HEADER.size :])
            first_offset = struct.unpack_from("<i", body)[0]
            struct.pack_into("<i", body, 0, first_offset + 1)
            forged[128:160] = hashlib.sha256(body).digest()
            forged[160:192] = hashlib.sha256(
                CERTIFICATE_DOMAIN + forged[:160] + body
            ).digest()
            with self.assertRaises(PT21NativeScanFastpathError):
                validate_native_scan_certificate(
                    raw,
                    bytes(forged[: CERTIFICATE_HEADER.size] + body),
                    scanner=identity,
                )

            with self.assertRaises(PT21NativeScanFastpathError):
                self.scan(packet.with_name("missing.bin"))
            with self.assertRaises(PT21NativeScanFastpathError):
                scan_required_sign_packet(
                    packet,
                    scanner=self.scanner,
                    expected_scanner_sha256="00" * 32,
                )
            alias = directory / "scanner-link"
            alias.symlink_to(self.scanner)
            with self.assertRaises(PT21NativeScanFastpathError):
                scan_required_sign_packet(
                    packet,
                    scanner=alias,
                    expected_scanner_sha256=self.scanner_sha256,
                )

    def test_persistent_ordered_session_matches_one_shot_certificates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packets = (
                required_packet(directory, 0),
                required_packet(directory, 1),
            )
            stationary = stationary_trace(directory, 0)
            turing = turing_inputs(directory, packets[0], 0, 1)
            identity = worker_identity(worker(directory))
            reference = adapt_block(
                required_sign_packet=packets[0],
                stationary_trace=stationary,
                turing_inputs=turing,
                worker=identity,
            )
            expected = tuple(self.scan(packet) for packet in packets)
            with NativeScanSession(
                scanner=self.scanner,
                expected_scanner_sha256=self.scanner_sha256,
            ) as session:
                first = scan_required_sign_packet_with_session(
                    packets[0], session=session
                )
                second = scan_required_sign_packet_with_session(
                    packets[1], session=session
                )
                repeated = scan_required_sign_packet_with_session(
                    packets[0], session=session
                )
                adapted = adapt_block_native_scan_session(
                    required_sign_packet=packets[0],
                    stationary_trace=stationary,
                    turing_inputs=turing,
                    worker=identity,
                    session=session,
                )
            self.assertEqual(first.certificate, expected[0].certificate)
            self.assertEqual(second.certificate, expected[1].certificate)
            self.assertEqual(repeated.certificate, first.certificate)
            self.assertEqual(first.scanner.sha256, self.scanner_sha256)
            self.assertEqual(adapted.adapted.record, reference.record)

    def test_same_inode_mutation_cannot_change_sealed_executed_image(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = required_packet(directory, 0)
            copied = directory / "mutable-scanner"
            shutil.copyfile(self.scanner, copied)
            copied.chmod(0o700)
            expected = hashlib.sha256(copied.read_bytes()).hexdigest()
            descriptor, identity = _pinned_scanner(copied, expected)
            try:
                # Mutate the very same source inode after pinning.  Execution
                # still comes from the independently hashed and sealed memfd.
                with copied.open("r+b") as stream:
                    stream.seek(0)
                    stream.write(b"not-an-elf")
                    stream.flush()
                    os.fsync(stream.fileno())
                with self.assertRaises(OSError):
                    os.write(descriptor, b"x")
                executable = f"/proc/self/fd/{descriptor}"
                completed = subprocess.run(
                    [executable],
                    executable=executable,
                    input=packet.read_bytes(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    pass_fds=(descriptor,),
                    check=False,
                    timeout=30,
                )
            finally:
                os.close(descriptor)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(completed.stderr)
            self.assertNotEqual(
                hashlib.sha256(copied.read_bytes()).hexdigest(), expected
            )
            self.assertTrue(identity.sealed_memfd_execution)
            self.assertEqual(identity.source_path_sha256, expected)
            self.assertEqual(identity.sealed_image_sha256, expected)
            validate_native_scan_certificate(
                packet.read_bytes(), completed.stdout, scanner=identity
            )

    def test_persistent_native_stream_framing_tamper_fails_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packet = required_packet(Path(temporary), 0).read_bytes()
            digest = hashlib.sha256(packet).digest()
            valid_header = STREAM_REQUEST_HEADER.pack(
                STREAM_REQUEST_MAGIC,
                1,
                STREAM_REQUEST_HEADER.size,
                0,
                len(packet),
                digest,
            )
            mutations = (
                b"x",
                bytes([valid_header[0] ^ 1]) + valid_header[1:] + packet,
                STREAM_REQUEST_HEADER.pack(
                    STREAM_REQUEST_MAGIC,
                    1,
                    STREAM_REQUEST_HEADER.size,
                    1,
                    len(packet),
                    digest,
                )
                + packet,
                STREAM_REQUEST_HEADER.pack(
                    STREAM_REQUEST_MAGIC,
                    1,
                    STREAM_REQUEST_HEADER.size,
                    0,
                    len(packet),
                    bytes(32),
                )
                + packet,
            )
            for index, mutation in enumerate(mutations):
                with self.subTest(case=index):
                    completed = subprocess.run(
                        [str(self.scanner), "--stream"],
                        input=mutation,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                        timeout=30,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertFalse(completed.stdout)
                    self.assertTrue(completed.stderr)

    def test_packet_sign_checksum_and_certificate_packet_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = required_packet(directory, 0)
            raw = bytearray(packet.read_bytes())
            certificate, identity, _seconds = run_native_scan_certificate(
                bytes(raw),
                scanner=self.scanner,
                expected_scanner_sha256=self.scanner_sha256,
            )
            sign_start = HEADER.size + REQUIRED_COUNT * SAMPLE.size
            raw[sign_start] ^= 1
            with self.assertRaises(PT21NativeScanFastpathError):
                run_native_scan_certificate(
                    bytes(raw),
                    scanner=self.scanner,
                    expected_scanner_sha256=self.scanner_sha256,
                )
            with self.assertRaises(PT21NativeScanFastpathError):
                validate_native_scan_certificate(
                    bytes(raw), certificate, scanner=identity
                )

            # Recompute the packet's redundant FNV field so the native scanner
            # reaches and rejects the independent DD/sign relationship.
            fields = list(HEADER.unpack_from(raw))
            fields[15] = _fnv1a(bytes(raw[sign_start:]))
            raw[: HEADER.size] = HEADER.pack(*fields)
            with self.assertRaises(PT21NativeScanFastpathError):
                run_native_scan_certificate(
                    bytes(raw),
                    scanner=self.scanner,
                    expected_scanner_sha256=self.scanner_sha256,
                )

    def test_standalone_validator_recomputes_redundant_fnv_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = required_packet(directory, 0)
            original = packet.read_bytes()
            certificate, identity, _seconds = run_native_scan_certificate(
                original,
                scanner=self.scanner,
                expected_scanner_sha256=self.scanner_sha256,
            )

            # This versioned wire checksum is redundant with the packet
            # SHA-256, but it is still part of PT21SGN1.  A standalone
            # certificate is unkeyed, so an attacker can update all of its
            # ordinary hashes after changing the declared checksum.  The
            # exported validator must independently reject that packet.
            forged_packet = bytearray(original)
            packet_fields = list(HEADER.unpack_from(forged_packet))
            packet_fields[14] ^= 1  # declared PT21SGN1 v1 wire checksum
            forged_packet[: HEADER.size] = HEADER.pack(*packet_fields)

            certificate_fields = list(
                CERTIFICATE_HEADER.unpack_from(certificate)
            )
            body = certificate[CERTIFICATE_HEADER.size :]
            certificate_fields[16] = packet_fields[14]
            certificate_fields[18] = hashlib.sha256(forged_packet).digest()
            certificate_fields[20] = bytes(32)
            forged_header = bytearray(
                CERTIFICATE_HEADER.pack(*certificate_fields)
            )
            forged_header[160:192] = hashlib.sha256(
                CERTIFICATE_DOMAIN + forged_header[:160] + body
            ).digest()
            forged_certificate = bytes(forged_header) + body

            with self.assertRaisesRegex(
                PT21NativeScanFastpathError,
                "wire checksum differs",
            ):
                validate_native_scan_certificate(
                    bytes(forged_packet),
                    forged_certificate,
                    scanner=identity,
                )
            with self.assertRaisesRegex(
                PT21NativeScanFastpathError,
                "payload checksum differs",
            ):
                run_native_scan_certificate(
                    bytes(forged_packet),
                    scanner=self.scanner,
                    expected_scanner_sha256=self.scanner_sha256,
                )

    def test_fixed_width_range_audit_requires_arbitrary_precision(self) -> None:
        report = arithmetic_range_report()
        self.assertEqual(report["minimum_subnormal_denominator_bits"], 1075)
        self.assertEqual(report["maximum_finite_integer_bits"], 1024)
        self.assertFalse(
            report["int128_sufficient_for_all_accepted_binary64"]
        )
        self.assertEqual(report["native_exact_backend"], "gmp-mpq")
        self.assertFalse(report["source_claim_ready"])

    def test_fastpath_never_implicitly_replaces_reference_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            packet = required_packet(directory, 0)
            stationary = stationary_trace(directory, 0)
            turing = turing_inputs(directory, packet, 0, 1)
            with self.assertRaises(PT21NativeRecordAdapterError):
                adapt_block_native_scan_fastpath(
                    required_sign_packet=packet,
                    stationary_trace=stationary,
                    turing_inputs=turing,
                    worker=worker(directory),
                    native_scanner=self.scanner,
                    expected_native_scanner_sha256="00" * 32,
                )


if __name__ == "__main__":
    unittest.main()
