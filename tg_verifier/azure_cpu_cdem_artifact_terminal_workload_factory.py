# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Closed second-stage CPU factory for the CDEM artifact-input terminal.

This factory is deliberately separate from the existing one-stage CDEM
factory.  The producer's complete ``TG-CDEM-ABEL-ARTIFACT-V1`` frame is the
measured input to this stage.  No registered Lean invocation is attached:
successful execution yields a reviewable operational receipt, not a theorem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CAMPAIGN_ID = "cdem-table-abel-artifact-terminal-v1"
FACTORY_ID = "cdem_table_abel_artifact_terminal_static_cpu_v1"
ALGORITHM_ID = (
    "sparkinterval.ternary-goldbach.cdem-table-abel.artifact-terminal.v1"
)
ALGORITHM_DEFINITION = (
    "sparkinterval.azure-operational-algorithm.v1\n"
    "campaign=cdem-table-abel\n"
    "stage=artifact-input-terminal-v1\n"
    "input=complete-TG-CDEM-ABEL-ARTIFACT-V1-frame\n"
    "terminal=reference/tg_cdem_abel_artifact_terminal.cpp\n"
    "replayer=reference/tg_cdem_abel_chunk_replay.cpp\n"
    "semantics=strict-artifact-parse-and-independent-replay-of-all-1000-rows\n"
    "replayer-binding=exact-static-elf-sha256-in-argv-and-trace\n"
    "output=canonical-legacy-registered-result\n"
    "source-admission=false\n"
    "lean-theorem-emission=false"
)
PARAMETERS: dict[str, Any] = {
    "artifact_format": "TG-CDEM-ABEL-ARTIFACT-V1",
    "chunk_count": 1_000,
    "replay_workers": 64,
    "weight_scale": 1_000_000_000_000_000_000,
}
DOMAIN: dict[str, Any] = {
    "claim": "artifact-structure-and-independent-cdem-recurrence-replay",
    "index_lower": 1,
    "index_upper": 5_000_000_000,
    "prefix_upper": 199_330,
    "source_claim_admitted": False,
}
RESULT = b"2372685835387717172679029560108650251645442524"
TRACE_DEFINITION = (
    "sparkinterval.challenge-work-trace.cdem-abel-artifact-terminal.v1\n"
    "initial=SHA256(initial-domain || challenge-nonce || job-binding || "
    "artifact-sha256 || replayer-elf-sha256)\n"
    "steps-0-through-999=SHA256(step-domain || previous || chunk-index || "
    "artifact-row-sha256 || exact-replay-stdout-sha256)\n"
    "step-1000=SHA256(step-domain || previous || total-variation || "
    "registered-result-sha256)\n"
    "verification=pinned-terminal-rereads-artifact-result-captured-replayer-and-"
    "all-2000-captured-replay-streams"
)
SOURCE_PATHS = (
    "reference/tg_cdem_abel_artifact_terminal.cpp",
    "reference/tg_cdem_abel_chunk_replay.cpp",
    "gpu/include/sparkinterval/sha256.hpp",
)
INPUT_PATH = "input/cdem-abel-artifact.bin"
OUTPUT_PATH = "output/registered-result.txt"
TRACE_PATH = "output/work-trace.json"
SCRATCH_PATH = "work/cdem-abel-artifact-terminal"
TERMINAL_PATH = "artifacts/tg_cdem_abel_artifact_terminal"
REPLAYER_PATH = "artifacts/tg_cdem_abel_chunk_replay"
PRODUCER_CERTIFICATE_PATH = "dependencies/cdem-producer-certificate.tar"
PRODUCER_RECEIPT_PATH = "dependencies/cdem-producer-receipt.json"
PRODUCER_BINDING_PATH = "dependencies/cdem-producer-binding.json"
PRODUCER_VERIFIER_MANIFEST_PATH = (
    "dependencies/cdem-producer-verifier-keys.json"
)
PRODUCER_VERIFIER_PUBLIC_KEY_PATH = (
    "dependencies/cdem-producer-verifier-public.pem"
)


@dataclass(frozen=True)
class CdemArtifactTerminalFactory:
    factory_id: str = FACTORY_ID
    campaign_id: str = CAMPAIGN_ID
    algorithm_id: str = ALGORITHM_ID
    algorithm_definition: str = ALGORITHM_DEFINITION
    parameters: dict[str, Any] = field(
        default_factory=lambda: dict(PARAMETERS)
    )
    domain: dict[str, Any] = field(default_factory=lambda: dict(DOMAIN))
    source_paths: tuple[str, ...] = SOURCE_PATHS
    trace_definition: str = TRACE_DEFINITION
    trace_iterations: int = 1_001
    timeout_seconds: int = 36 * 60 * 60
    output_format: str = "canonical_decimal_natural_no_newline_v1"
    output_maximum_bytes: int = 64

    def command_argv(self, replayer_sha256: str) -> tuple[str, ...]:
        return (
            TERMINAL_PATH,
            "--run",
            "--challenge",
            "@challenge@",
            "--input",
            "@input@",
            "--job-binding",
            "@job_binding@",
            "--output",
            "@output@",
            "--replayer-sha256",
            replayer_sha256,
            "--scratch",
            SCRATCH_PATH,
            "--trace",
            "@trace@",
            "--replayer",
            REPLAYER_PATH,
            "--workers",
            "64",
        )

    def trace_verifier_argv(self, replayer_sha256: str) -> tuple[str, ...]:
        return (
            TERMINAL_PATH,
            "--verify-trace",
            "--challenge",
            "@challenge@",
            "--input",
            "@input@",
            "--job-binding",
            "@job_binding@",
            "--output",
            "@output@",
            "--replayer-sha256",
            replayer_sha256,
            "--scratch",
            SCRATCH_PATH,
            "--trace",
            "@trace@",
        )


CDEM_ARTIFACT_TERMINAL_FACTORY = CdemArtifactTerminalFactory()


__all__ = [
    "ALGORITHM_DEFINITION",
    "ALGORITHM_ID",
    "CAMPAIGN_ID",
    "CDEM_ARTIFACT_TERMINAL_FACTORY",
    "CdemArtifactTerminalFactory",
    "DOMAIN",
    "FACTORY_ID",
    "INPUT_PATH",
    "OUTPUT_PATH",
    "PARAMETERS",
    "PRODUCER_BINDING_PATH",
    "PRODUCER_CERTIFICATE_PATH",
    "PRODUCER_RECEIPT_PATH",
    "PRODUCER_VERIFIER_MANIFEST_PATH",
    "PRODUCER_VERIFIER_PUBLIC_KEY_PATH",
    "REPLAYER_PATH",
    "RESULT",
    "SCRATCH_PATH",
    "SOURCE_PATHS",
    "TERMINAL_PATH",
    "TRACE_DEFINITION",
    "TRACE_PATH",
]
