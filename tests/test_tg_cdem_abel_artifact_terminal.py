# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from azure.measured_runner import WORK_TRACE_KEYS
from tg_verifier.cdem_abel_artifact import ARTIFACT_HEADER


ROOT = Path(__file__).resolve().parents[1]
SIGNED_TARGET = 324_880_457_633_740
ABSOLUTE_TARGET = 48_710_223_109_607_260_068_028
CHUNK_COUNT = 1_000
CHUNK_BYTES = 195
FIXED_BYTES = 68


def natural(value: int) -> bytes:
    return value.to_bytes(32, "little")


def integer(value: int) -> bytes:
    return bytes((1 if value < 0 else 0,)) + natural(abs(value))


def synthetic_production_shape_artifact() -> bytes:
    """A parser/protocol fixture, not CDEM arithmetic evidence."""

    output = bytearray(ARTIFACT_HEADER)
    output.extend(natural(SIGNED_TARGET))
    output.extend(natural(ABSOLUTE_TARGET))
    output.extend(CHUNK_COUNT.to_bytes(4, "little"))
    for index in range(CHUNK_COUNT):
        low = index * 5_000_000 + 1
        high = (index + 1) * 5_000_000
        output.extend(natural(low))
        output.extend(natural(high))
        output.extend(integer(0))
        output.extend(integer(112 if index == CHUNK_COUNT - 1 else 0))
        output.extend(integer(SIGNED_TARGET if index == 0 else 0))
        output.extend(natural(ABSOLUTE_TARGET if index == 0 else 0))
    return bytes(output)


FAKE_REPLAYER = r"""
#include <charconv>
#include <cstdint>
#include <iostream>
#include <string_view>

bool parse(std::string_view text, std::uint64_t& value) {
  const auto result =
      std::from_chars(text.data(), text.data() + text.size(), value);
  return result.ec == std::errc{} &&
         result.ptr == text.data() + text.size();
}

int main(int argc, char** argv) {
  if (argc != 5) return 2;
  std::uint64_t low = 0;
  if (!parse(argv[2], low)) return 2;
  const bool first = low == 1;
  const bool last = low == 4995000001ULL;
  std::cout << "SCHEMA=CDEM_ABEL_CHUNK_REPLAY_V1\n";
  std::cout << "K=199330\n";
  std::cout << "LOW=" << argv[2] << "\n";
  std::cout << "HIGH=" << argv[3] << "\n";
  std::cout << "BEFORE=" << argv[4] << "\n";
  std::cout << "DELTA_SUM=" << (last ? "112" : "0") << "\n";
  std::cout << "AFTER=" << (last ? "112" : "0") << "\n";
  std::cout << "U_INC_UPPER_NUM="
            << (first ? "324880457633740" : "0") << "\n";
  std::cout << "V_INC_UPPER_NUM="
            << (first ? "48710223109607260068028" : "0") << "\n";
  std::cout << "TOTAL_VARIATION="
            << (first ? "1678512305" : "0") << "\n";
  std::cout << "WEIGHT_SCALE=1000000000000000000\n";
  return 0;
}
"""


class CdemAbelArtifactTerminalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = shutil.which("g++")
        if compiler is None:
            raise unittest.SkipTest("g++ is required for the terminal test")
        cls._build = tempfile.TemporaryDirectory()
        build = Path(cls._build.name)
        cls.terminal = build / "tg-cdem-abel-artifact-terminal"
        subprocess.run(
            [
                compiler,
                "-std=c++20",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pthread",
                f"-I{ROOT / 'gpu/include'}",
                str(ROOT / "reference/tg_cdem_abel_artifact_terminal.cpp"),
                "-o",
                str(cls.terminal),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        fake_source = build / "bounded_protocol_stub.cpp"
        fake_source.write_text(textwrap.dedent(FAKE_REPLAYER), encoding="utf-8")
        cls.fake_replayer = build / "bounded-protocol-stub"
        subprocess.run(
            [
                compiler,
                "-std=c++20",
                "-O0",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(fake_source),
                "-o",
                str(cls.fake_replayer),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        cls.fake_sha256 = hashlib.sha256(
            cls.fake_replayer.read_bytes()
        ).hexdigest()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._build.cleanup()

    def invoke(
        self,
        directory: Path,
        *arguments: str,
        success: bool = True,
        timeout: int = 60,
    ) -> subprocess.CompletedProcess[bytes]:
        completed = subprocess.run(
            [str(self.terminal), *arguments],
            cwd=directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if success:
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            self.assertEqual(completed.stderr, b"")
        else:
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stdout, b"")
            self.assertIn(
                b"tg_cdem_abel_artifact_terminal:", completed.stderr
            )
        return completed

    def test_strict_parser_accepts_only_the_exact_production_frame(self) -> None:
        artifact = synthetic_production_shape_artifact()
        self.assertEqual(
            len(artifact),
            len(ARTIFACT_HEADER) + FIXED_BYTES + CHUNK_COUNT * CHUNK_BYTES,
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "artifact.bin"
            source.write_bytes(artifact)
            completed = self.invoke(
                directory,
                "--validate-artifact",
                "--input",
                source.name,
            )
            report = json.loads(completed.stdout)
            self.assertEqual(report["chunk_count"], CHUNK_COUNT)
            self.assertEqual(
                report["artifact_sha256"], hashlib.sha256(artifact).hexdigest()
            )
            self.assertEqual(
                report["mode"], "non_authorizing_artifact_validation"
            )
            self.assertFalse(report["source_claim_ready"])

            row_zero = len(ARTIFACT_HEADER) + FIXED_BYTES
            mutations: dict[str, bytes] = {
                "suffix": artifact + b"x",
                "truncation": artifact[:-1],
                "header": bytes((artifact[0] ^ 1,)) + artifact[1:],
                "target": (
                    artifact[: len(ARTIFACT_HEADER)]
                    + bytes((artifact[len(ARTIFACT_HEADER)] ^ 1,))
                    + artifact[len(ARTIFACT_HEADER) + 1 :]
                ),
                "count": (
                    artifact[: len(ARTIFACT_HEADER) + 64]
                    + (999).to_bytes(4, "little")
                    + artifact[len(ARTIFACT_HEADER) + 68 :]
                ),
                "topology": (
                    artifact[:row_zero]
                    + natural(2)
                    + artifact[row_zero + 32 :]
                ),
                "negative_zero": (
                    artifact[: row_zero + 64]
                    + b"\x01"
                    + b"\x00" * 32
                    + artifact[row_zero + 97 :]
                ),
                "reduction": (
                    artifact[: row_zero + 130]
                    + integer(SIGNED_TARGET - 1)
                    + artifact[row_zero + 163 :]
                ),
            }
            for name, malformed in mutations.items():
                with self.subTest(name=name):
                    source.write_bytes(malformed)
                    self.invoke(
                        directory,
                        "--validate-artifact",
                        "--input",
                        source.name,
                        success=False,
                    )

    def test_bounded_protocol_stub_exercises_publication_and_trace_replay(
        self,
    ) -> None:
        """Exercise 1,000 child handoffs without doing the CDEM computation."""

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "artifact.bin").write_bytes(
                synthetic_production_shape_artifact()
            )
            shutil.copyfile(
                self.fake_replayer, directory / "bounded-protocol-stub"
            )
            os.chmod(directory / "bounded-protocol-stub", 0o500)
            common = [
                "--challenge",
                "a" * 64,
                "--input",
                "artifact.bin",
                "--job-binding",
                "b" * 64,
                "--output",
                "registered-result.txt",
                "--replayer-sha256",
                self.fake_sha256,
                "--scratch",
                "scratch",
                "--trace",
                "trace.json",
            ]
            completed = self.invoke(
                directory,
                "--run",
                *common,
                "--replayer",
                "bounded-protocol-stub",
                "--workers",
                "64",
            )
            self.assertEqual(completed.stdout, b"")
            self.assertEqual(
                (directory / "registered-result.txt").read_bytes(),
                b"2372685835387717172679029560108650251645442524",
            )
            trace = json.loads((directory / "trace.json").read_bytes())
            self.assertEqual(set(trace), WORK_TRACE_KEYS)
            self.assertEqual(trace["iteration_count"], CHUNK_COUNT + 1)
            self.assertEqual(trace["challenge_nonce"], "a" * 64)
            self.assertEqual(trace["job_binding_sha256"], "b" * 64)
            self.assertEqual(
                trace["input_sha256"],
                hashlib.sha256(
                    synthetic_production_shape_artifact()
                ).hexdigest(),
            )
            self.invoke(directory, "--verify-trace", *common)

            replay = directory / "scratch/replay-999.stdout"
            replay.write_bytes(replay.read_bytes() + b"x")
            self.invoke(
                directory,
                "--verify-trace",
                *common,
                success=False,
            )

    def test_invalid_input_cannot_publish_result_or_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "artifact.bin").write_bytes(
                synthetic_production_shape_artifact()[:-1]
            )
            self.invoke(
                directory,
                "--run",
                "--challenge",
                "a" * 64,
                "--input",
                "artifact.bin",
                "--job-binding",
                "b" * 64,
                "--output",
                "registered-result.txt",
                "--replayer-sha256",
                "c" * 64,
                "--scratch",
                "scratch",
                "--trace",
                "trace.json",
                "--replayer",
                "missing-replayer",
                "--workers",
                "64",
                success=False,
            )
            self.assertFalse((directory / "registered-result.txt").exists())
            self.assertFalse((directory / "trace.json").exists())
            self.assertFalse((directory / "scratch").exists())

    def test_source_uses_no_shell_execution_path(self) -> None:
        source = (
            ROOT / "reference/tg_cdem_abel_artifact_terminal.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("posix_spawn(", source)
        self.assertIn("O_EXCL", source)
        self.assertNotIn("std::system(", source)
        self.assertNotIn("popen(", source)
        self.assertNotIn("/bin/sh", source)


if __name__ == "__main__":
    unittest.main()
