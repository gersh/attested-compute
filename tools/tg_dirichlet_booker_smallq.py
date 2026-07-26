#!/usr/bin/env python3
# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Plan, produce, replay, and test Platt's small-q Gaussian/DFT stage."""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tg_verifier.dirichlet_booker_smallq import (  # noqa: E402
    DEFAULT_FREQUENCY_CHUNK_SIZE,
    DEFAULT_PRECISION_BITS,
    DEFAULT_REPLAY_GUARD_BITS,
    DEFAULT_TARGET_BITS,
    DirichletBookerSmallQError,
    assemble_character,
    benchmark,
    capability,
    known_answer_case,
    inspect_gpu_proposal,
    produce_frequency_chunk,
    replay_frequency_chunk,
    source_campaign_plan,
    source_chunk_request,
    transform_parameters,
    write_gpu_proposal_input,
)
from tg_verifier.campaign_io import (  # noqa: E402
    MeasuredWorkerScopeError,
    require_azure_measured_worker_for_workload,
)


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def _nonnegative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a nonnegative integer")
    return parsed


def _fraction(value: str) -> Fraction:
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise argparse.ArgumentTypeError("expected an exact rational") from error


def _emit(value: object, pretty: bool) -> None:
    if pretty:
        print(json.dumps(value, indent=2, sort_keys=True))
    else:
        print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--pretty", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)

    commands.add_parser("capability", help="report exact implemented boundaries")

    plan = commands.add_parser("plan", help="compute the compact source-domain plan")
    plan.add_argument("--q-start", type=_positive, default=2)
    plan.add_argument("--q-stop", type=_positive, default=10_000)
    plan.add_argument(
        "--frequency-chunk-size", type=_positive, default=DEFAULT_FREQUENCY_CHUNK_SIZE
    )
    plan.add_argument("--omit-moduli", action="store_true")

    request = commands.add_parser("request", help="materialize one source chunk request")
    request.add_argument("q", type=_positive)
    request.add_argument("character_ordinal", type=_nonnegative)
    request.add_argument("frequency_chunk_index", type=_nonnegative)
    request.add_argument(
        "--frequency-chunk-size", type=_positive, default=DEFAULT_FREQUENCY_CHUNK_SIZE
    )

    produce = commands.add_parser("produce-chunk", help="produce one rigorous Arb chunk")
    produce.add_argument("output", type=Path)
    produce.add_argument("q", type=_positive)
    produce.add_argument("conrey_number", type=_positive)
    produce.add_argument("frequency_start", type=_nonnegative)
    produce.add_argument("frequency_stop", type=_positive)
    produce.add_argument("--height", type=_fraction)
    produce.add_argument("--guard-height", type=_fraction, default=Fraction(64))
    produce.add_argument("--transform-length", type=_positive)
    produce.add_argument("--eta", type=_fraction)
    produce.add_argument("--character-ordinal", type=_nonnegative)
    produce.add_argument("--precision-bits", type=_positive, default=DEFAULT_PRECISION_BITS)
    produce.add_argument("--target-bits", type=_positive, default=DEFAULT_TARGET_BITS)

    replay = commands.add_parser("replay-chunk", help="fresh higher-precision replay")
    replay.add_argument("root", type=Path)
    replay.add_argument("--guard-bits", type=_positive, default=DEFAULT_REPLAY_GUARD_BITS)

    gpu_input = commands.add_parser(
        "gpu-input", help="write an explicitly untrusted CUDA proposal input"
    )
    gpu_input.add_argument("output", type=Path)
    gpu_input.add_argument("q", type=_positive)
    gpu_input.add_argument("conrey_number", type=_positive)
    gpu_input.add_argument("frequency_start", type=_nonnegative)
    gpu_input.add_argument("frequency_stop", type=_positive)
    gpu_input.add_argument("--height", type=_fraction, default=Fraction(1))
    gpu_input.add_argument("--guard-height", type=_fraction, default=Fraction(4))
    gpu_input.add_argument("--transform-length", type=_positive, default=1024)
    gpu_input.add_argument("--eta", type=_fraction, default=Fraction(0))
    gpu_input.add_argument("--precision-bits", type=_positive, default=DEFAULT_PRECISION_BITS)
    gpu_input.add_argument("--target-bits", type=_positive, default=DEFAULT_TARGET_BITS)

    gpu_inspect = commands.add_parser(
        "gpu-inspect", help="compare an untrusted CUDA proposal with fresh Arb"
    )
    gpu_inspect.add_argument("input", type=Path)
    gpu_inspect.add_argument("output", type=Path)
    gpu_inspect.add_argument("q", type=_positive)
    gpu_inspect.add_argument("conrey_number", type=_positive)
    gpu_inspect.add_argument("--height", type=_fraction, default=Fraction(1))
    gpu_inspect.add_argument("--guard-height", type=_fraction, default=Fraction(4))
    gpu_inspect.add_argument("--transform-length", type=_positive, default=1024)
    gpu_inspect.add_argument("--eta", type=_fraction, default=Fraction(0))
    gpu_inspect.add_argument("--precision-bits", type=_positive, default=DEFAULT_PRECISION_BITS)

    assemble = commands.add_parser("assemble", help="assemble complete frequency coverage")
    assemble.add_argument("output", type=Path)
    assemble.add_argument("chunks", type=Path, nargs="+")
    assemble.add_argument("--sample-start", type=_nonnegative, default=0)
    assemble.add_argument("--sample-stop", type=_positive)
    assemble.add_argument("--precision-bits", type=_positive, default=DEFAULT_PRECISION_BITS)
    assemble.add_argument("--no-direct-flint", action="store_true")

    kat = commands.add_parser("kat", help="run q=3,4,5 source-formula known answers")
    kat.add_argument("--output", type=Path)
    kat.add_argument("--transform-length", type=_positive, default=128)
    kat.add_argument("--sample-stop", type=_positive, default=5)

    bench = commands.add_parser("benchmark", help="benchmark the Arb frequency reference")
    bench.add_argument("--q", type=_positive, default=5)
    bench.add_argument("--conrey-number", type=_positive, default=2)
    bench.add_argument("--frequency-count", type=_positive, default=256)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capability":
            value = capability()
        elif args.command == "plan":
            value = source_campaign_plan(
                q_start=args.q_start,
                q_stop=args.q_stop,
                frequency_chunk_size=args.frequency_chunk_size,
                include_moduli=not args.omit_moduli,
            )
        elif args.command == "request":
            value = source_chunk_request(
                q=args.q,
                character_ordinal=args.character_ordinal,
                frequency_chunk_index=args.frequency_chunk_index,
                frequency_chunk_size=args.frequency_chunk_size,
            )
        elif args.command == "produce-chunk":
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(
                    args.q
                    * (args.frequency_stop - args.frequency_start),
                ),
            )
            parameters = transform_parameters(
                args.q,
                height=args.height,
                guard_height=args.guard_height,
                transform_length=args.transform_length,
                eta=args.eta,
            )
            value = produce_frequency_chunk(
                args.output,
                q=args.q,
                conrey_number=args.conrey_number,
                frequency_start=args.frequency_start,
                frequency_stop=args.frequency_stop,
                parameters=parameters,
                character_ordinal=args.character_ordinal,
                precision_bits=args.precision_bits,
                target_bits=args.target_bits,
            )
        elif args.command == "replay-chunk":
            # The replay extent is retained inside the artifact.  There is no
            # CLI-side truncation, so this route is cloud-only.
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            value = replay_frequency_chunk(args.root, guard_bits=args.guard_bits)
        elif args.command == "gpu-input":
            parameters = transform_parameters(
                args.q,
                height=args.height,
                guard_height=args.guard_height,
                transform_length=args.transform_length,
                eta=args.eta,
            )
            value = write_gpu_proposal_input(
                args.output,
                q=args.q,
                conrey_number=args.conrey_number,
                parameters=parameters,
                frequency_start=args.frequency_start,
                frequency_stop=args.frequency_stop,
                target_bits=args.target_bits,
                precision_bits=args.precision_bits,
            )
        elif args.command == "gpu-inspect":
            # The proposal carries the frequency extent; fail before opening
            # either proposal artifact rather than trusting unparsed input.
            require_azure_measured_worker_for_workload(
                exact_production=True,
                work_bounds=(),
            )
            parameters = transform_parameters(
                args.q,
                height=args.height,
                guard_height=args.guard_height,
                transform_length=args.transform_length,
                eta=args.eta,
            )
            value = inspect_gpu_proposal(
                args.input,
                args.output,
                conrey_number=args.conrey_number,
                parameters=parameters,
                precision_bits=args.precision_bits,
            )
        elif args.command == "assemble":
            if not args.no_direct_flint:
                require_azure_measured_worker_for_workload(
                    exact_production=True,
                    work_bounds=(),
                )
            value = assemble_character(
                args.output,
                args.chunks,
                sample_start=args.sample_start,
                sample_stop=args.sample_stop,
                precision_bits=args.precision_bits,
                compare_direct_flint=not args.no_direct_flint,
            )
        elif args.command == "kat":
            cases = [(3, 2), (4, 3), (5, 2), (5, 3), (5, 4)]
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(
                    sum(q for q, _conrey in cases) * args.sample_stop,
                ),
            )
            if args.output is None:
                with tempfile.TemporaryDirectory() as temporary:
                    value = {
                        "kind": "sparkinterval.tg.dirichlet_booker_smallq.kat.v1",
                        "cases": [
                            {
                                "q": q,
                                "conrey_number": conrey,
                                "result": known_answer_case(
                                    Path(temporary),
                                    q=q,
                                    conrey_number=conrey,
                                    transform_length=args.transform_length,
                                    sample_stop=args.sample_stop,
                                ),
                            }
                            for q, conrey in cases
                        ],
                    }
            else:
                args.output.mkdir(parents=True, exist_ok=True)
                if any(args.output.iterdir()):
                    raise DirichletBookerSmallQError("KAT output directory is not empty")
                value = {
                    "kind": "sparkinterval.tg.dirichlet_booker_smallq.kat.v1",
                    "cases": [
                        {
                            "q": q,
                            "conrey_number": conrey,
                            "result": known_answer_case(
                                args.output,
                                q=q,
                                conrey_number=conrey,
                                transform_length=args.transform_length,
                                sample_stop=args.sample_stop,
                            ),
                        }
                        for q, conrey in cases
                    ],
                }
        elif args.command == "benchmark":
            require_azure_measured_worker_for_workload(
                exact_production=False,
                work_bounds=(args.q * args.frequency_count,),
            )
            value = benchmark(
                q=args.q,
                conrey_number=args.conrey_number,
                frequency_count=args.frequency_count,
            )
        else:  # pragma: no cover
            raise AssertionError(args.command)
    except (
        DirichletBookerSmallQError,
        MeasuredWorkerScopeError,
        OSError,
    ) as error:
        print(f"tg_dirichlet_booker_smallq: {error}", file=sys.stderr)
        return 2
    _emit(value, args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
