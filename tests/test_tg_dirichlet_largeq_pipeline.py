# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.tg_dirichlet_residue_composition_fixture import (  # noqa: E402
    rehash_job_artifact,
    write_job,
)
from tg_verifier.dirichlet_fft_pipeline_bundle import (  # noqa: E402
    build_bundle,
    replay_bundle,
)
from tg_verifier.dirichlet_lattice_cache import (  # noqa: E402
    _synthetic_row,
    build_cache_catalog,
    cache_shard_filename,
    source_cache_plan,
    write_synthetic_cache_shard,
)
from tg_verifier.dirichlet_lattice_certificates import (  # noqa: E402
    RECOVERY_HEADER,
    RECOVERY_ITEM,
)
from tg_verifier.dirichlet_lattice_stage import (  # noqa: E402
    INPUT_HEADER as LATTICE_INPUT_HEADER,
    LATTICE_CELL,
    LATTICE_ROWS,
    OUTPUT_HEADER as LATTICE_OUTPUT_HEADER,
    OUTPUT_ITEM as LATTICE_OUTPUT_ITEM,
    TAYLOR_COLUMNS,
)
from tg_verifier.dirichlet_largeq_pipeline import (  # noqa: E402
    DirichletLargeQPipelineError,
    capability,
    run_pipeline,
    validate_control_alignment,
)
from tg_verifier.dirichlet_residue_composition import (  # noqa: E402
    FRAMED_REQUEST_SCHEMA,
    canonical_json_bytes,
)
import tg_verifier.dirichlet_root_number_stage as root_stage  # noqa: E402
from tg_verifier.dirichlet_root_number_stage import (  # noqa: E402
    ROOT_ALGORITHM_ID,
    consume_transform_path,
    write_additive_input,
)
from tg_verifier.dirichlet_source_supervisor import (  # noqa: E402
    build_structural_kat_contract,
)
from tg_verifier.dirichlet_stream_zero_consumer import make_control  # noqa: E402
from tg_verifier.dirichlet_tmajor_adapter import (  # noqa: E402
    TMajorTypedBundleLaneAdapter,
)
from tg_verifier.dirichlet_tblock_bundle_supervisor import (  # noqa: E402
    run_bundle_supervisor_v2,
)
from tg_verifier.dirichlet_tblock_plan_switch_worker import (  # noqa: E402
    load_recipe,
    native_handshake,
    write_recipe,
)
import tg_verifier.dirichlet_tblock_plan_switch_worker as plan_switch_worker  # noqa: E402
from tg_verifier.dirichlet_tblock_supervisor import (  # noqa: E402
    DirichletTBlockSupervisorError,
)
from tg_verifier.dirichlet_tmajor_spool import build_lane_spool  # noqa: E402


PINNED_PYTHON = Path("/tmp/tg-flint-venv/bin/python")
MPFR_CHECKER = ROOT / "build/tg-production-kat/sparkinterval-tg-dirichlet-allchars-mpfr"
ALLCHARS = ROOT / "build/tg-production-kat/sparkinterval-tg-dirichlet-allchars"
TBLOCK_BUNDLE_WORKER = (
    ROOT / "tools/tg_dirichlet_tblock_bundle_worker.py"
)
TBLOCK_PLAN_SWITCH_WORKER = (
    ROOT / "tools/tg_dirichlet_tblock_plan_switch_worker.py"
)
PINNED_CURRENT_FLINT = (
    root_stage.FLINT_IMPORT_ERROR is None
    and root_stage.flint.__version__ == "0.9.0"
    and root_stage.flint.__FLINT_VERSION__ == "3.6.0"
)


def _upstream() -> dict[str, str]:
    return {
        "all_character_transform_input_sha256": "1" * 64,
        "finite_addback_receipt_sha256": "2" * 64,
        "lattice_tail_receipt_sha256": "3" * 64,
        "residue_adapter_receipt_sha256": "4" * 64,
    }


class DirichletLargeQPipelineStructuralTest(unittest.TestCase):
    def _controls(self, root: Path) -> tuple[Path, Path, Path]:
        first_job, _ = write_job(root / "first", t_indices=(127, 128))
        second_job, _ = write_job(root / "second", t_indices=(129, 130))
        composition = root / "composition.ndjson"
        consumer = root / "consumer.ndjson"
        composition.write_bytes(
            b"".join(
                canonical_json_bytes(
                    {
                        "schema": FRAMED_REQUEST_SCHEMA,
                        "schema_version": 1,
                        "job": str(job),
                        "receipt": str(root / f"composition-{index}.json"),
                    }
                )
                for index, job in enumerate((first_job, second_job))
            )
        )
        consumer.write_bytes(
            b"".join(
                canonical_json_bytes(
                    make_control(
                        frame_index=index,
                        q=10_001,
                        batch_count=2,
                        first_t_numerator=635 + 10 * index,
                        t_denominator=64,
                        t_step_numerator=5,
                        upstream_receipts=_upstream(),
                        root_number_mode=ROOT_ALGORITHM_ID,
                    )
                )
                for index in range(2)
            )
        )
        return composition, consumer, first_job

    def test_preflight_binds_every_frame_and_rejects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            composition, consumer, _job = self._controls(root)
            result = validate_control_alignment(
                composition,
                consumer,
                base=root,
                maximum_batch_count=2,
                allow_synthetic_kat=True,
            )
            self.assertEqual(result.q, 10_001)
            self.assertEqual(result.frame_count, 2)
            self.assertEqual(result.slice_count, 4)
            self.assertEqual(result.value_count, 39_168)
            self.assertEqual(result.first_t_numerator, 635)
            self.assertEqual(result.stop_t_numerator, 655)
            self.assertEqual(result.t_denominator, 64)
            self.assertEqual(result.t_step_numerator, 5)

            rows = consumer.read_bytes().splitlines(keepends=True)
            changed = json.loads(rows[1])
            changed["first_t_numerator"] += 5
            rows[1] = canonical_json_bytes(changed)
            consumer.write_bytes(b"".join(rows))
            with self.assertRaisesRegex(
                DirichletLargeQPipelineError, "differs from its composition"
            ):
                validate_control_alignment(
                    composition,
                    consumer,
                    base=root,
                    maximum_batch_count=2,
                    allow_synthetic_kat=True,
                )

    def test_capability_does_not_claim_the_atom(self) -> None:
        result = capability()
        self.assertTrue(result["production_component_graph_ready"])
        self.assertFalse(result["external_atom_discharged"])
        self.assertFalse(result["zero_completeness_claimed"])


@unittest.skipUnless(
    PINNED_PYTHON.is_file()
    and PINNED_CURRENT_FLINT
    and MPFR_CHECKER.is_file()
    and ALLCHARS.is_file(),
    "requires pinned FLINT, MPFR checker, and CUDA allchars runner",
)
class DirichletLargeQPipelineProcessKat(unittest.TestCase):
    @staticmethod
    def _contract(
        root: Path,
        *,
        t_rows: int = 2,
        q_stop: int = 10_001,
    ) -> Path:
        root.mkdir(parents=True)
        cache = root / "cache"
        cache.mkdir()
        plan = source_cache_plan(
            t_index_stop_exclusive=t_rows,
            t_indices_per_shard=t_rows,
        )
        write_synthetic_cache_shard(
            cache / cache_shard_filename(0),
            plan=plan,
            shard_index=0,
        )
        catalog = cache / "catalog.json"
        build_cache_catalog(
            catalog,
            cache,
            plan=plan,
            require_replayed_receipts=False,
        )
        contract = root / "contract.json"
        build_structural_kat_contract(
            contract,
            cache_root=cache,
            cache_catalog=catalog,
            lane_count=1,
            recovery_artifact_sha256="a" * 64,
            recovery_replay_sha256="b" * 64,
            q_tile_size=1,
            q_start=10_001,
            q_stop=q_stop,
        )
        return contract

    @staticmethod
    def _hull_every_box_with_exact_zero(
        path: Path,
        *,
        header: object,
        item: object,
    ) -> None:
        """Outwardly widen each existing rectangle by its hull with {0}."""

        raw = bytearray(path.read_bytes())
        header_size = header.size
        item_size = item.size
        if (len(raw) - header_size) % item_size:
            raise AssertionError("fixture interval artifact geometry differs")
        for offset in range(header_size, len(raw), item_size):
            fields = list(item.unpack_from(raw, offset))
            fields[-4] = min(fields[-4], 0.0)
            fields[-3] = max(fields[-3], 0.0)
            fields[-2] = min(fields[-2], 0.0)
            fields[-1] = max(fields[-1], 0.0)
            item.pack_into(raw, offset, *fields)
        path.write_bytes(raw)

    def _actual_pipeline_fixture(
        self,
        root: Path,
        *,
        hull_with_zero: bool,
    ) -> tuple[Path, Path]:
        contract = self._contract(root)
        job, frames = write_job(root / "job", t_indices=(0, 1))
        payload_start = LATTICE_INPUT_HEADER.size
        payload_stop = (
            payload_start
            + LATTICE_ROWS * TAYLOR_COLUMNS * LATTICE_CELL.size
        )
        for frame_index, (t_index, frame) in enumerate(
            zip((0, 1), frames)
        ):
            lattice_input = frame["lattice_input"]
            raw = bytearray(lattice_input.read_bytes())
            raw[payload_start:payload_stop] = _synthetic_row(t_index)
            lattice_input.write_bytes(raw)
            rehash_job_artifact(job, frame_index, "lattice_input")
            if hull_with_zero:
                self._hull_every_box_with_exact_zero(
                    frame["lattice_output"],
                    header=LATTICE_OUTPUT_HEADER,
                    item=LATTICE_OUTPUT_ITEM,
                )
                self._hull_every_box_with_exact_zero(
                    frame["finite_recovery"],
                    header=RECOVERY_HEADER,
                    item=RECOVERY_ITEM,
                )
                rehash_job_artifact(job, frame_index, "lattice_output")
                rehash_job_artifact(job, frame_index, "finite_recovery")

        composition = root / "composition.ndjson"
        composition.write_bytes(
            canonical_json_bytes(
                {
                    "schema": FRAMED_REQUEST_SCHEMA,
                    "schema_version": 1,
                    "job": str(job),
                    "receipt": str(root / "composition-receipt.json"),
                }
            )
        )
        consumer = root / "consumer.ndjson"
        consumer.write_bytes(
            canonical_json_bytes(
                make_control(
                    frame_index=0,
                    q=10_001,
                    batch_count=2,
                    first_t_numerator=0,
                    t_denominator=64,
                    t_step_numerator=5,
                    upstream_receipts=_upstream(),
                    root_number_mode=ROOT_ALGORITHM_ID,
                )
            )
        )
        additive = write_additive_input(
            root / "root-input.bin", q=10_001, precision=192
        )
        subprocess.run(
            [
                str(MPFR_CHECKER),
                "compute",
                str(root / "root-input.bin"),
                str(root / "root-transform.bin"),
                "192",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        consume_transform_path(
            root / "root-transform.bin",
            root / "roots.bin",
            root / "roots.json",
            q=10_001,
            additive_receipt=additive,
            precision=192,
        )
        pipeline = root / "pipeline-receipt.json"
        run_pipeline(
            composition_controls=composition,
            consumer_controls=consumer,
            control_base=root,
            composer_python=PINNED_PYTHON,
            composer_tool=ROOT / "tools/tg_dirichlet_residue_composition.py",
            allchars_runner=ALLCHARS,
            consumer_python=PINNED_PYTHON,
            consumer_tool=ROOT / "tools/tg_dirichlet_stream_zero_consumer.py",
            root_artifact=root / "roots.bin",
            root_receipt=root / "roots.json",
            output_directory=root / "pipeline",
            pipeline_receipt=pipeline,
            maximum_batch_count=2,
            device=0,
            precision=192,
            allow_synthetic_kat=True,
        )
        return contract, pipeline

    def _native_plan_switch_target(
        self,
        root: Path,
        *,
        sequence_index: int,
        q: int,
        t_indices: tuple[int, ...],
        root_artifacts: dict[int, tuple[Path, Path]],
    ) -> dict[str, object]:
        target_root = (
            root
            / "target-inputs"
            / f"block-{sequence_index:08d}"
            / f"q-{q:06d}"
        )
        job, frames = write_job(
            target_root / "job",
            q=q,
            t_indices=t_indices,
        )
        payload_start = LATTICE_INPUT_HEADER.size
        payload_stop = (
            payload_start
            + LATTICE_ROWS * TAYLOR_COLUMNS * LATTICE_CELL.size
        )
        for frame_index, (t_index, frame) in enumerate(
            zip(t_indices, frames)
        ):
            lattice_input = frame["lattice_input"]
            raw = bytearray(lattice_input.read_bytes())
            raw[payload_start:payload_stop] = _synthetic_row(t_index)
            lattice_input.write_bytes(raw)
            rehash_job_artifact(job, frame_index, "lattice_input")
            self._hull_every_box_with_exact_zero(
                frame["lattice_output"],
                header=LATTICE_OUTPUT_HEADER,
                item=LATTICE_OUTPUT_ITEM,
            )
            self._hull_every_box_with_exact_zero(
                frame["finite_recovery"],
                header=RECOVERY_HEADER,
                item=RECOVERY_ITEM,
            )
            rehash_job_artifact(job, frame_index, "lattice_output")
            rehash_job_artifact(job, frame_index, "finite_recovery")

        composition = target_root / "composition.ndjson"
        composition.write_bytes(
            canonical_json_bytes(
                {
                    "schema": FRAMED_REQUEST_SCHEMA,
                    "schema_version": 1,
                    "job": str(job),
                    "receipt": str(
                        target_root / "composition-receipt.json"
                    ),
                }
            )
        )
        consumer = target_root / "consumer.ndjson"
        consumer.write_bytes(
            canonical_json_bytes(
                make_control(
                    frame_index=0,
                    q=q,
                    batch_count=len(t_indices),
                    first_t_numerator=5 * t_indices[0],
                    t_denominator=64,
                    t_step_numerator=5,
                    upstream_receipts=_upstream(),
                    root_number_mode=ROOT_ALGORITHM_ID,
                )
            )
        )
        if q not in root_artifacts:
            roots = root / "target-inputs" / f"roots-q-{q:06d}"
            roots.mkdir(parents=True)
            additive = write_additive_input(
                roots / "root-input.bin", q=q, precision=192
            )
            subprocess.run(
                [
                    str(MPFR_CHECKER),
                    "compute",
                    str(roots / "root-input.bin"),
                    str(roots / "root-transform.bin"),
                    "192",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            consume_transform_path(
                roots / "root-transform.bin",
                roots / "roots.bin",
                roots / "roots.json",
                q=q,
                additive_receipt=additive,
                precision=192,
            )
            root_artifacts[q] = (
                roots / "roots.bin",
                roots / "roots.json",
            )
        root_artifact, root_receipt = root_artifacts[q]
        return {
            "sequence_index": sequence_index,
            "q": q,
            "first_t_index": t_indices[0],
            "t_index_stop_exclusive": t_indices[-1] + 1,
            "control_base": target_root,
            "composition_controls": composition,
            "consumer_controls": consumer,
            "root_artifact": root_artifact,
            "root_receipt": root_receipt,
        }

    def test_three_persistent_processes_bind_their_streams(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, _ = write_job(root / "job", t_indices=(127, 128))
            composition = root / "composition.ndjson"
            composition.write_bytes(
                canonical_json_bytes(
                    {
                        "schema": FRAMED_REQUEST_SCHEMA,
                        "schema_version": 1,
                        "job": str(job),
                        "receipt": str(root / "composition-receipt.json"),
                    }
                )
            )
            consumer_control = root / "consumer.ndjson"
            consumer_control.write_bytes(
                canonical_json_bytes(
                    make_control(
                        frame_index=0,
                        q=10_001,
                        batch_count=2,
                        first_t_numerator=635,
                        t_denominator=64,
                        t_step_numerator=5,
                        upstream_receipts=_upstream(),
                        root_number_mode=ROOT_ALGORITHM_ID,
                    )
                )
            )

            additive = write_additive_input(
                root / "root-input.bin", q=10_001, precision=192
            )
            subprocess.run(
                [
                    str(MPFR_CHECKER),
                    "compute",
                    str(root / "root-input.bin"),
                    str(root / "root-transform.bin"),
                    "192",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            consume_transform_path(
                root / "root-transform.bin",
                root / "roots.bin",
                root / "roots.json",
                q=10_001,
                additive_receipt=additive,
                precision=192,
            )

            fake_consumer = root / "fake-consumer.py"
            fake_consumer.write_text(
                """#!/usr/bin/env python3
import hashlib,json,pathlib,struct,sys
args=sys.argv
control=pathlib.Path(args[2]); events=pathlib.Path(args[4]); receipt=pathlib.Path(args[5])
raw=sys.stdin.buffer.read(); off=0; frames=0; values=0; H=struct.Struct('<8sIIIIQQQQ')
while off < len(raw):
 h=H.unpack_from(raw,off); off += H.size + h[6]*32; frames += 1; values += h[6]
if off != len(raw): raise SystemExit(3)
events.write_bytes(b'{}\\n')
r={'control_stream_sha256':hashlib.sha256(control.read_bytes()).hexdigest(),'external_atom_discharged':False,'frame_count':frames,'root_number_artifact_supplied':True,'root_number_mode':'tgdaff-all-character-gauss-root-phase-v1','source_performance_ready':True,'transform_stream_sha256':hashlib.sha256(raw).hexdigest(),'value_count':values}
enc=lambda x:(json.dumps(x,sort_keys=True,separators=(',',':'))+'\\n').encode()
r['receipt_sha256']=hashlib.sha256(enc(r)).hexdigest(); receipt.write_bytes(enc(r)); print('{}')
""",
                encoding="utf-8",
            )
            result = run_pipeline(
                composition_controls=composition,
                consumer_controls=consumer_control,
                control_base=root,
                composer_python=Path(sys.executable),
                composer_tool=ROOT / "tools/tg_dirichlet_residue_composition.py",
                allchars_runner=ALLCHARS,
                consumer_python=Path(sys.executable),
                consumer_tool=fake_consumer,
                root_artifact=root / "roots.bin",
                root_receipt=root / "roots.json",
                output_directory=root / "pipeline",
                pipeline_receipt=root / "pipeline-receipt.json",
                maximum_batch_count=2,
                device=0,
                precision=192,
                allow_synthetic_kat=True,
            )
            self.assertTrue(result["stream_bindings_verified"])
            self.assertEqual(
                result["process_return_codes"],
                {"composer": 0, "transform": 0, "consumer": 0},
            )
            self.assertFalse(result["external_atom_discharged"])

    def test_real_consumer_rejects_narrow_fixture_then_accepts_zero_hull(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(
                DirichletLargeQPipelineError,
                "persistent pipeline process failed",
            ):
                self._actual_pipeline_fixture(
                    root / "narrow", hull_with_zero=False
                )
            narrow_stderr = (
                root / "narrow" / "pipeline" / "consumer.stderr"
            ).read_text("utf-8")
            self.assertIn(
                "completed-L imaginary rectangle does not contain zero",
                narrow_stderr,
            )

            contract, pipeline = self._actual_pipeline_fixture(
                root / "zero-hull", hull_with_zero=True
            )
            bundle_path = root / "zero-hull" / "typed-bundle.json"
            bundle = build_bundle(
                bundle_path,
                contract_path=contract,
                lane_index=0,
                q=10_001,
                first_t_index=0,
                pipeline_receipt_path=pipeline,
                allow_structural_kat=True,
            )
            replay = replay_bundle(
                bundle_path,
                contract_path=contract,
                allow_structural_kat=True,
                expected_bundle_sha256=bundle["bundle_sha256"],
            )
            self.assertTrue(replay["accepted"])
            adapter = TMajorTypedBundleLaneAdapter(
                contract,
                lane_index=0,
                allow_structural_kat=True,
            )
            adapter.authenticate_all_rows()
            admission = adapter.accept_bundle(
                bundle_path,
                expected_bundle_sha256=bundle["bundle_sha256"],
            )
            lane = adapter.finish_lane()
            self.assertTrue(
                admission["decisions"][
                    "typed_bundle_fresh_replay_accepted"
                ]
            )
            self.assertEqual(lane["typed_bundle_admission_count"], 1)
            self.assertFalse(
                lane["decisions"]["external_atom_discharged"]
            )

    def test_tblock_v2_transports_replays_and_admits_real_fixed_q_bundle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract, pipeline = self._actual_pipeline_fixture(
                root / "real-fixed-q", hull_with_zero=True
            )
            bundle_path = root / "real-fixed-q" / "typed-bundle.json"
            bundle = build_bundle(
                bundle_path,
                contract_path=contract,
                lane_index=0,
                q=10_001,
                first_t_index=0,
                pipeline_receipt_path=pipeline,
                allow_structural_kat=True,
            )
            spool_path = root / "lane-0.spool"
            spool_receipt_path = root / "lane-0.spool.receipt.json"
            spool_receipt = build_lane_spool(
                spool_path,
                spool_receipt_path,
                contract_path=contract,
                lane_index=0,
                allow_structural_kat=True,
            )

            def command(*extra: str) -> list[str]:
                return [
                    sys.executable,
                    str(TBLOCK_BUNDLE_WORKER),
                    "--bundle-frame",
                    f"0:{bundle_path.resolve()}",
                    *extra,
                ]

            completed = run_bundle_supervisor_v2(
                root / "v2.receipt.json",
                root / "v2-checkpoints",
                contract_path=contract,
                spool_receipt_path=spool_receipt_path,
                expected_spool_receipt_sha256=spool_receipt[
                    "receipt_sha256"
                ],
                worker_command=command(),
                allow_structural_kat=True,
            )
            self.assertTrue(completed["complete"])
            self.assertEqual(completed["completed_block_count"], 1)
            self.assertEqual(completed["active_q_target_count"], 1)
            self.assertTrue(
                completed["decisions"][
                    "actual_length_framed_typed_bundle_bytes_received"
                ]
            )
            self.assertTrue(
                completed["decisions"][
                    "all_typed_bundles_freshly_replayed"
                ]
            )
            self.assertTrue(
                completed["decisions"][
                    "all_typed_bundles_admitted_by_existing_tmajor_adapter"
                ]
            )
            self.assertFalse(
                completed["decisions"]["real_multi_q_worker_implemented"]
            )
            self.assertFalse(
                completed["decisions"]["external_atom_discharged"]
            )
            checkpoint = json.loads(
                (
                    root
                    / "v2-checkpoints"
                    / "block-00000000.checkpoint.json"
                ).read_bytes()
            )
            self.assertEqual(
                checkpoint["staged_typed_bundles"][0][
                    "transport_sha256"
                ],
                hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                checkpoint["staged_typed_bundles"][0]["bundle_sha256"],
                bundle["bundle_sha256"],
            )
            self.assertTrue(
                checkpoint["supervisor_result"][
                    "checkpoint_permitted_after_admission"
                ]
            )
            resumed = run_bundle_supervisor_v2(
                root / "v2-resumed.receipt.json",
                root / "v2-checkpoints",
                contract_path=contract,
                spool_receipt_path=spool_receipt_path,
                expected_spool_receipt_sha256=spool_receipt[
                    "receipt_sha256"
                ],
                worker_command=command(),
                allow_structural_kat=True,
                expected_checkpoint_chain_sha256=completed[
                    "checkpoint_chain_sha256"
                ],
            )
            self.assertTrue(resumed["complete"])
            self.assertEqual(
                resumed["worker_result_chain_sha256"],
                completed["worker_result_chain_sha256"],
            )

            attacks = {
                "substitution": "--substitute-frame-on-sequence",
                "truncation": "--truncate-frame-on-sequence",
                "reorder": "--reorder-frame-on-sequence",
                "worker-lie": "--lie-admission-on-sequence",
            }
            for name, option in attacks.items():
                with self.subTest(attack=name):
                    attack_root = root / name
                    with self.assertRaises(
                        DirichletTBlockSupervisorError
                    ):
                        run_bundle_supervisor_v2(
                            attack_root / "receipt.json",
                            attack_root / "checkpoints",
                            contract_path=contract,
                            spool_receipt_path=spool_receipt_path,
                            expected_spool_receipt_sha256=spool_receipt[
                                "receipt_sha256"
                            ],
                            worker_command=command(option, "0"),
                            allow_structural_kat=True,
                        )
                    self.assertEqual(
                        list(
                            (attack_root / "checkpoints").glob(
                                "block-*.checkpoint.json"
                            )
                        ),
                        [],
                    )
                    self.assertFalse(
                        (attack_root / "receipt.json").exists()
                    )

    def test_native_multi_q_plan_switch_worker_small_kat_and_attacks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = self._contract(root / "campaign", q_stop=10_003)
            root_artifacts: dict[int, tuple[Path, Path]] = {}
            targets = [
                self._native_plan_switch_target(
                    root / "campaign",
                    sequence_index=0,
                    q=q,
                    t_indices=(0, 1),
                    root_artifacts=root_artifacts,
                )
                for q in range(10_001, 10_004)
            ]
            recipe_path = root / "campaign" / "plan-switch-recipe.json"
            recipe = write_recipe(
                recipe_path,
                contract_path=contract,
                runtime={
                    "composer_python": PINNED_PYTHON,
                    "composer_tool": (
                        ROOT / "tools/tg_dirichlet_residue_composition.py"
                    ),
                    "allchars_runner": ALLCHARS,
                    "consumer_python": PINNED_PYTHON,
                    "consumer_tool": (
                        ROOT / "tools/tg_dirichlet_stream_zero_consumer.py"
                    ),
                },
                targets=targets,
                allow_synthetic_kat=True,
                maximum_batch_count=2,
                precision=192,
            )
            _loaded, _runtime, runtime_sha256 = load_recipe(recipe_path)
            handshake = native_handshake(
                Path(plan_switch_worker.__file__),
                launcher_path=TBLOCK_PLAN_SWITCH_WORKER,
                recipe=recipe,
                runtime_artifacts_sha256=runtime_sha256,
            )
            spool_path = root / "campaign" / "lane-0.spool"
            spool_receipt_path = (
                root / "campaign" / "lane-0.spool.receipt.json"
            )
            spool_receipt = build_lane_spool(
                spool_path,
                spool_receipt_path,
                contract_path=contract,
                lane_index=0,
                allow_structural_kat=True,
            )
            worker_output = root / "campaign" / "worker-output"

            def command(*extra: str) -> list[str]:
                return [
                    sys.executable,
                    str(TBLOCK_PLAN_SWITCH_WORKER),
                    str(recipe_path),
                    str(worker_output),
                    *extra,
                ]

            def supervise(
                output: Path,
                checkpoints: Path,
                *extra: str,
            ) -> dict[str, object]:
                return run_bundle_supervisor_v2(
                    output,
                    checkpoints,
                    contract_path=contract,
                    spool_receipt_path=spool_receipt_path,
                    expected_spool_receipt_sha256=spool_receipt[
                        "receipt_sha256"
                    ],
                    worker_command=command(*extra),
                    allow_structural_kat=True,
                    allow_native_plan_switch_kat=True,
                    expected_worker_recipe_sha256=recipe[
                        "recipe_sha256"
                    ],
                    expected_runtime_artifacts_sha256=runtime_sha256,
                    expected_worker_handshake_sha256=handshake[
                        "handshake_sha256"
                    ],
                    expected_worker_implementation_sha256=handshake[
                        "worker_implementation_sha256"
                    ],
                )

            completed = supervise(
                root / "campaign" / "supervisor.receipt.json",
                root / "campaign" / "checkpoints",
            )
            self.assertTrue(completed["complete"])
            self.assertEqual(completed["active_q_target_count"], 3)
            self.assertEqual(
                completed["bundle_output_order"],
                "t_block_major_then_q",
            )
            self.assertTrue(
                completed["decisions"][
                    "real_multi_q_plan_switch_worker_executed"
                ]
            )
            self.assertFalse(
                completed["decisions"]["source_evidence_produced"]
            )
            self.assertFalse(
                completed["decisions"]["trusted_execution_attested"]
            )
            self.assertFalse(
                completed["decisions"]["zero_completeness_claimed"]
            )
            checkpoint = json.loads(
                (
                    root
                    / "campaign"
                    / "checkpoints"
                    / "block-00000000.checkpoint.json"
                ).read_bytes()
            )
            execution = checkpoint["response"]["native_execution"]
            self.assertEqual(
                execution["q_sequence"], [10_001, 10_002, 10_003]
            )
            self.assertEqual(execution["generated_target_count"], 3)
            self.assertEqual(execution["plan_load_count"], 3)
            self.assertEqual(execution["plan_switch_count"], 2)
            self.assertEqual(len(execution["target_timings"]), 3)
            for timing in execution["target_timings"]:
                self.assertGreater(timing["composer_wall_seconds"], 0)
                self.assertGreaterEqual(
                    timing["allchars_execution_seconds"], 0
                )
                self.assertGreater(
                    timing["flint_consumer_wall_seconds"], 0
                )

            attacks = {
                "reordered-q": ("--reverse-output-on-sequence", "0"),
                "substituted-frame": (
                    "--substitute-bundle-on-sequence",
                    "0",
                ),
                "truncated-frame": (
                    "--truncate-frame-on-sequence",
                    "0",
                ),
                "worker-plan-lie": (
                    "--lie-plan-switch-on-sequence",
                    "0",
                ),
            }
            for name, extra in attacks.items():
                with self.subTest(attack=name):
                    attack_root = root / "campaign" / name
                    with self.assertRaises(
                        DirichletTBlockSupervisorError
                    ):
                        supervise(
                            attack_root / "receipt.json",
                            attack_root / "checkpoints",
                            *extra,
                        )
                    self.assertEqual(
                        list(
                            (attack_root / "checkpoints").glob(
                                "block-*.checkpoint.json"
                            )
                        ),
                        [],
                    )
                    self.assertFalse(
                        (attack_root / "receipt.json").exists()
                    )

    def test_native_multi_q_plan_switch_worker_medium_two_block_order(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            campaign = root / "campaign"
            contract = self._contract(
                campaign,
                t_rows=65,
                q_stop=10_002,
            )
            root_artifacts: dict[int, tuple[Path, Path]] = {}
            targets = [
                self._native_plan_switch_target(
                    campaign,
                    sequence_index=sequence,
                    q=q,
                    t_indices=t_indices,
                    root_artifacts=root_artifacts,
                )
                for sequence, t_indices in (
                    (0, tuple(range(64))),
                    (1, (64,)),
                )
                for q in (10_001, 10_002)
            ]
            recipe_path = campaign / "plan-switch-recipe.json"
            recipe = write_recipe(
                recipe_path,
                contract_path=contract,
                runtime={
                    "composer_python": PINNED_PYTHON,
                    "composer_tool": (
                        ROOT / "tools/tg_dirichlet_residue_composition.py"
                    ),
                    "allchars_runner": ALLCHARS,
                    "consumer_python": PINNED_PYTHON,
                    "consumer_tool": (
                        ROOT / "tools/tg_dirichlet_stream_zero_consumer.py"
                    ),
                },
                targets=targets,
                maximum_batch_count=64,
                precision=192,
            )
            _loaded, _runtime, runtime_sha256 = load_recipe(recipe_path)
            handshake = native_handshake(
                Path(plan_switch_worker.__file__),
                launcher_path=TBLOCK_PLAN_SWITCH_WORKER,
                recipe=recipe,
                runtime_artifacts_sha256=runtime_sha256,
            )
            spool_receipt_path = campaign / "lane-0.spool.receipt.json"
            spool_receipt = build_lane_spool(
                campaign / "lane-0.spool",
                spool_receipt_path,
                contract_path=contract,
                lane_index=0,
                allow_structural_kat=True,
            )
            worker_output = campaign / "worker-output"
            checkpoints = campaign / "checkpoints"
            completed = run_bundle_supervisor_v2(
                campaign / "receipt.json",
                checkpoints,
                contract_path=contract,
                spool_receipt_path=spool_receipt_path,
                expected_spool_receipt_sha256=spool_receipt[
                    "receipt_sha256"
                ],
                worker_command=[
                    sys.executable,
                    str(TBLOCK_PLAN_SWITCH_WORKER),
                    str(recipe_path),
                    str(worker_output),
                ],
                allow_structural_kat=True,
                allow_native_plan_switch_kat=True,
                expected_worker_recipe_sha256=recipe[
                    "recipe_sha256"
                ],
                expected_runtime_artifacts_sha256=runtime_sha256,
                expected_worker_handshake_sha256=handshake[
                    "handshake_sha256"
                ],
                expected_worker_implementation_sha256=handshake[
                    "worker_implementation_sha256"
                ],
            )
            self.assertTrue(completed["complete"])
            self.assertEqual(completed["completed_block_count"], 2)
            self.assertEqual(completed["active_q_target_count"], 4)
            self.assertEqual(
                completed["adapter_lane_receipt"]["target_order"],
                "t_block_major_then_q",
            )
            checkpoint_zero = json.loads(
                (
                    checkpoints / "block-00000000.checkpoint.json"
                ).read_bytes()
            )
            checkpoint_one = json.loads(
                (
                    checkpoints / "block-00000001.checkpoint.json"
                ).read_bytes()
            )
            self.assertEqual(
                checkpoint_zero["response"]["native_execution"][
                    "q_sequence"
                ],
                [10_001, 10_002],
            )
            self.assertEqual(
                [
                    artifact["admission"]["target"]["first_t_index"]
                    for artifact in checkpoint_zero[
                        "staged_typed_bundles"
                    ]
                    + checkpoint_one["staged_typed_bundles"]
                ],
                [0, 0, 64, 64],
            )
            transitions_zero = checkpoint_zero[
                "compact_state_transitions"
            ]
            transitions_one = checkpoint_one[
                "compact_state_transitions"
            ]
            self.assertEqual(len(transitions_zero), 2)
            self.assertEqual(len(transitions_one), 2)
            self.assertEqual(
                [row["q"] for row in transitions_zero],
                [10_001, 10_002],
            )
            self.assertEqual(
                [row["q"] for row in transitions_one],
                [10_001, 10_002],
            )
            self.assertTrue(
                all(
                    row["state_before_sha256"] is None
                    for row in transitions_zero
                )
            )
            self.assertEqual(
                [
                    row["state_before_sha256"]
                    for row in transitions_one
                ],
                [
                    row["state_after_sha256"]
                    for row in transitions_zero
                ],
            )
            self.assertTrue(
                all(
                    row[
                        "exact_q_roster_grid_and_adjacency_validated"
                    ]
                    for row in transitions_zero + transitions_one
                )
            )
            self.assertEqual(completed["compact_state_transition_count"], 4)
            self.assertEqual(completed["compact_state_q_count"], 2)
            self.assertEqual(
                [row["q"] for row in completed["compact_state_heads"]],
                [10_001, 10_002],
            )
            self.assertTrue(
                completed["decisions"][
                    "compact_q_state_binary_checkpoint_resume_integrated"
                ]
            )
            self.assertTrue(
                completed["decisions"]["exact_ambiguity_ranges_retained"]
            )
            self.assertTrue(
                completed["decisions"][
                    "ordered_bracket_records_retained"
                ]
            )
            self.assertFalse(
                completed["decisions"]["turing_completeness_claimed"]
            )

            def resume(label: str) -> dict[str, object]:
                return run_bundle_supervisor_v2(
                    campaign / f"resume-{label}.receipt.json",
                    checkpoints,
                    contract_path=contract,
                    spool_receipt_path=spool_receipt_path,
                    expected_spool_receipt_sha256=spool_receipt[
                        "receipt_sha256"
                    ],
                    worker_command=[
                        sys.executable,
                        str(TBLOCK_PLAN_SWITCH_WORKER),
                        str(recipe_path),
                        str(worker_output),
                    ],
                    allow_structural_kat=True,
                    allow_native_plan_switch_kat=True,
                    expected_worker_recipe_sha256=recipe[
                        "recipe_sha256"
                    ],
                    expected_runtime_artifacts_sha256=runtime_sha256,
                    expected_worker_handshake_sha256=handshake[
                        "handshake_sha256"
                    ],
                    expected_worker_implementation_sha256=handshake[
                        "worker_implementation_sha256"
                    ],
                    expected_checkpoint_chain_sha256=completed[
                        "checkpoint_chain_sha256"
                    ],
                )

            state_record = transitions_one[0]["state_after_binary"]
            state_path = Path(state_record["path"])
            state_raw = state_path.read_bytes()
            state_path.write_bytes(state_raw[:-1])
            with self.assertRaises(DirichletTBlockSupervisorError):
                resume("truncated-state")
            state_path.write_bytes(state_raw)

            substituted = bytearray(state_raw)
            substituted[-1] ^= 1
            state_path.write_bytes(substituted)
            with self.assertRaises(DirichletTBlockSupervisorError):
                resume("substituted-state")
            state_path.write_bytes(state_raw)

            header_bytes = state_record["header_bytes"]
            record_bytes = state_record["character_record_bytes"]
            reordered = (
                state_raw[:header_bytes]
                + state_raw[
                    header_bytes + record_bytes :
                    header_bytes + 2 * record_bytes
                ]
                + state_raw[header_bytes : header_bytes + record_bytes]
                + state_raw[header_bytes + 2 * record_bytes :]
            )
            # TGDCSB02 gives even identical all-ambiguous character records
            # distinct canonical sparse offsets, so ordinal reordering is
            # visible and fails replay.
            self.assertNotEqual(reordered, state_raw)
            state_path.write_bytes(reordered)
            with self.assertRaises(DirichletTBlockSupervisorError):
                resume("reordered-state")
            state_path.write_bytes(state_raw)

            resumed = resume("accepted-state")
            self.assertTrue(resumed["complete"])
            self.assertEqual(
                resumed["compact_state_heads"],
                completed["compact_state_heads"],
            )

            zero_path = checkpoints / "block-00000000.checkpoint.json"
            one_path = checkpoints / "block-00000001.checkpoint.json"
            zero_raw, one_raw = zero_path.read_bytes(), one_path.read_bytes()
            try:
                zero_path.write_bytes(one_raw)
                one_path.write_bytes(zero_raw)
                with self.assertRaisesRegex(
                    DirichletTBlockSupervisorError,
                    "substituted|reordered",
                ):
                    run_bundle_supervisor_v2(
                        campaign / "reordered-block-receipt.json",
                        checkpoints,
                        contract_path=contract,
                        spool_receipt_path=spool_receipt_path,
                        expected_spool_receipt_sha256=spool_receipt[
                            "receipt_sha256"
                        ],
                        worker_command=[
                            sys.executable,
                            str(TBLOCK_PLAN_SWITCH_WORKER),
                            str(recipe_path),
                            str(worker_output),
                        ],
                        allow_structural_kat=True,
                        allow_native_plan_switch_kat=True,
                        expected_worker_recipe_sha256=recipe[
                            "recipe_sha256"
                        ],
                        expected_runtime_artifacts_sha256=runtime_sha256,
                        expected_worker_handshake_sha256=handshake[
                            "handshake_sha256"
                        ],
                        expected_worker_implementation_sha256=handshake[
                            "worker_implementation_sha256"
                        ],
                        expected_checkpoint_chain_sha256=completed[
                            "checkpoint_chain_sha256"
                        ],
                    )
            finally:
                zero_path.write_bytes(zero_raw)
                one_path.write_bytes(one_raw)


if __name__ == "__main__":
    unittest.main()
