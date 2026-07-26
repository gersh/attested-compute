# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Test-only context for an exact measured-worker binding.

Production workloads deliberately reject ordinary local execution. Focused
unit tests which replace every source-scale producer with bounded fixtures may
enter the same four-variable scope that the measured runner would inject.
Keeping this helper under ``tests/`` prevents a production CLI from acquiring
an escape hatch.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from types import SimpleNamespace
from typing import Iterator
from unittest import mock

from tg_verifier.campaign_io import (
    AZURE_MEASURED_WORKER_BACKEND_ENV,
    AZURE_MEASURED_WORKER_CHALLENGE_ENV,
    AZURE_MEASURED_WORKER_JOB_BINDING_ENV,
    AZURE_MEASURED_WORKER_SCOPE,
    AZURE_MEASURED_WORKER_SCOPE_ENV,
)


@contextmanager
def measured_worker_test_scope(
    arguments: SimpleNamespace,
    *,
    backend: str = "azure_sevsnp_cpu",
) -> Iterator[None]:
    """Inject the exact binding already carried by a bounded test fixture."""

    challenge = getattr(arguments, "challenge")
    job_binding = getattr(arguments, "job_binding")
    if (
        not isinstance(challenge, str)
        or len(challenge) != 64
        or not isinstance(job_binding, str)
        or len(job_binding) != 64
    ):
        raise AssertionError("test fixture lacks a canonical measured binding")
    environment = {
        AZURE_MEASURED_WORKER_SCOPE_ENV: AZURE_MEASURED_WORKER_SCOPE,
        AZURE_MEASURED_WORKER_BACKEND_ENV: backend,
        AZURE_MEASURED_WORKER_CHALLENGE_ENV: challenge,
        AZURE_MEASURED_WORKER_JOB_BINDING_ENV: job_binding,
    }
    with mock.patch.dict(os.environ, environment, clear=False):
        yield


@contextmanager
def bounded_measured_worker_test_scope(
    *,
    backend: str = "azure_sevsnp_cpu",
) -> Iterator[None]:
    """Give a bounded subprocess fixture a stable, test-only worker scope."""

    arguments = SimpleNamespace(
        challenge="1" * 64,
        job_binding="2" * 64,
    )
    with measured_worker_test_scope(arguments, backend=backend):
        yield
