# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Auditable runtime and Azure-cost model for the thirteen TG campaigns.

This module deliberately separates measurements from projections and from
missing optimized implementations.  In particular, it never turns a bounded
benchmark into evidence for an external atom.  The price snapshot is a
convenience for planning; callers can refresh it from Microsoft's public
Retail Prices API before spending money.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import Decimal, ROUND_CEILING
from functools import lru_cache
import json
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlencode
from urllib.request import urlopen

from .azure_backend_optimizer import (
    CampaignRoute,
    PRODUCTION_MAX_COST_USD,
    PRODUCTION_MAX_WALL_HOURS,
    ResourceDemand,
    optimize_backend_catalog,
)
from .azure_target_sku_calibration import (
    TargetSKUCalibrationError,
    calibration_key,
    conservative_high_node_hours,
    validate_manifest_set,
    validation_summary as target_sku_calibration_summary,
)
from .dirichlet_compact_state_streaming_v3 import (
    source_storage_projection_v3,
)
from .goldbach_gpu_campaign import (
    ANALYTIC_10POW27_EVEN_COUNT,
    ANALYTIC_10POW27_SHARDS,
    PRODUCTION_EVEN_COUNT,
    PRODUCTION_SHARDS,
)
from .goldbach_gpu_projection import project_source_height
from .hurst_h100_affine_projection import project_hurst_h100_affine


AZURE_RETAIL_PRICES_API = "https://prices.azure.com/api/retail/prices"
AZURE_REGION = "eastus2"
NCC_SKU = "Standard_NCC40ads_H100_v5"
NCC_GPU_COUNT = 1
PRODUCTION_NODE_COUNT = 8
CPU_SKU = "Standard_DC96as_v6"
CPU_NODE_COUNT = 4
CPU_CORES_PER_NODE = 96
PRICE_SNAPSHOT_DATE = date(2026, 7, 21)
PRICE_SNAPSHOT_USD_PER_NODE_HOUR = {
    "pay_as_you_go": Decimal("6.98"),
    "spot": Decimal("1.419034"),
}
CPU_PRICE_SNAPSHOT_USD_PER_NODE_HOUR = {
    "pay_as_you_go": Decimal("4.358"),
    "spot": Decimal("0.805358"),
}

GOLDBACH_SAMPLE_EVEN_COUNT = 600_000_000
GOLDBACH_SAMPLE_SECONDS = Decimal("0.779701")
GOLDBACH_H100_SENSITIVITY_FACTORS = (
    Decimal("1"),
    Decimal("2"),
    Decimal("5"),
    Decimal("10"),
    Decimal("14.3"),
)
GOLDBACH_LADDER_RANGE_COUNT = 492_700
GOLDBACH_LADDER_MINIMUM_RECORDS_PER_RANGE = 4_503_600
GOLDBACH_LADDER_NATIVE_PROJECTED_CORE_HOURS = Decimal("12700")
GOLDBACH_LADDER_PAPER_REPORTED_CORE_HOURS = Decimal("40000")
GOLDBACH_LADDER_PYTHON_PROJECTED_CORE_HOURS = Decimal("255000")
GOLDBACH_10POW27_LADDER_RANGE_COUNT = 7_106
GOLDBACH_10POW27_LADDER_SCALE = (
    Decimal(GOLDBACH_10POW27_LADDER_RANGE_COUNT)
    / Decimal(GOLDBACH_LADDER_RANGE_COUNT)
)
GOLDBACH_10POW27_LADDER_NATIVE_PROJECTED_CORE_HOURS = (
    GOLDBACH_LADDER_NATIVE_PROJECTED_CORE_HOURS * GOLDBACH_10POW27_LADDER_SCALE
)
GOLDBACH_10POW27_LADDER_PAPER_SCALED_CORE_HOURS = (
    GOLDBACH_LADDER_PAPER_REPORTED_CORE_HOURS * GOLDBACH_10POW27_LADDER_SCALE
)
GOLDBACH_10POW27_LADDER_PYTHON_PROJECTED_CORE_HOURS = (
    GOLDBACH_LADDER_PYTHON_PROJECTED_CORE_HOURS * GOLDBACH_10POW27_LADDER_SCALE
)
HURST_AFFINE_SOURCE_ROWS = Decimal("10000000000000000")
HURST_AFFINE_SAMPLE_ROWS = Decimal("20000000")
HURST_AFFINE_LOW_RANGE_SECONDS = Decimal("2.764")
HURST_AFFINE_TERMINAL_SECONDS = Decimal("2.85")
HURST_AFFINE_SAMPLE_THREADS = Decimal("8")
ZETA_MEASURED_PROJECTED_PROCESS_HOURS = Decimal("37580948")
ZETA_PAPER_REPORTED_CORE_HOURS = Decimal("7500000")
DIRICHLET_PAPER_REPORTED_CORE_HOURS = Decimal("400000")
DIRICHLET_LARGE_Q_BATCH64_BUTTERFLIES = Decimal("15334965882246056")
DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_LOW = Decimal("1380000000")
DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_HIGH = Decimal("1400000000")
DIRICHLET_LARGE_Q_CURRENT_PREPARATION_CPU_HOURS = Decimal("533.6")
DIRICHLET_SMALL_Q_GAUSSIAN_TERMS = Decimal("1171395337603008")
DIRICHLET_SMALL_Q_GB10_GAUSSIAN_TERMS_PER_SECOND = Decimal("1800500000")
DIRICHLET_SMALL_Q_RADIX2_BUTTERFLIES = Decimal("67133929684992")
DIRICHLET_SMALL_Q_FREQUENCY_VALUES = Decimal("7078844301312")
DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_Q = 997
DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_FREQUENCIES = Decimal("65536")
DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_TERMS = Decimal("118816929")
DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_TERM_SECONDS = Decimal("0.182364")
DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_BUTTERFLIES = Decimal("2097152")
DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_DFT_SECONDS = Decimal("0.0020661")
DIRICHLET_SMALL_Q_CERTIFIED_ARB_SEEDS_PER_SECOND = Decimal("33746.7")
DIRICHLET_SMALL_Q_CERTIFIED_SEED_BYTES_PER_FREQUENCY = Decimal("88")
DIRICHLET_SMALL_Q_CERTIFIED_OBSERVED_PRE_DFT_RADIUS = Decimal("1.44e-7")
DIRICHLET_SMALL_Q_PRIMITIVE_CHARACTERS = Decimal("18477108")
DIRICHLET_SMALL_Q_FACTORED_SHARED_RECORDS = Decimal("16385441792")
DIRICHLET_SMALL_Q_FACTORED_MINIMUM_LOGICAL_BYTES = Decimal("2459841190828")
DIRICHLET_SMALL_Q_FACTORED_SERVICE_PHYSICAL_BYTES = Decimal("2459842579084")
DIRICHLET_SMALL_Q_FACTORED_LITERAL_OUTPUT_BYTES = Decimal("339784527970104")
DIRICHLET_SMALL_Q_FACTORED_REDUCED_OUTPUT_BYTES = Decimal("226995959255448")
DIRICHLET_SMALL_Q_SEMANTIC_CONTROL_RECORDS = Decimal("8116121626")
DIRICHLET_SMALL_Q_SEMANTIC_CONTROL_BYTES = Decimal("129858785904")
DIRICHLET_SMALL_Q_SEMANTIC_SIGN_ARTIFACT_BYTES = Decimal("1182271755191")
DIRICHLET_SMALL_Q_OUTPUT_REDUCER_CACHED_MB_PER_SECOND = Decimal("4943.53431879196")
DIRICHLET_SMALL_Q_OUTPUT_REDUCER_PIPE_MB_PER_SECOND = Decimal("1510.2032966033898")
DIRICHLET_SMALL_Q_FACTORED_SERVICE_BATCHES = Decimal("8971")
DIRICHLET_SMALL_Q_FACTORED_BENCHMARK_Q = 997
DIRICHLET_SMALL_Q_FACTORED_BENCHMARK_FREQUENCIES = Decimal("65536")
DIRICHLET_SMALL_Q_FACTORED_BENCHMARK_CHARACTERS = Decimal("16")
DIRICHLET_SMALL_Q_FACTORED_BENCHMARK_FAMILIES = Decimal("196624")
DIRICHLET_SMALL_Q_FACTORED_PRODUCER_SECONDS = Decimal("3.164728742")
DIRICHLET_SMALL_Q_FACTORED_CHECKER_SECONDS = Decimal("3.272058564")
DIRICHLET_SMALL_Q_FACTORED_CUDA_TERMS = Decimal("4003136")
DIRICHLET_SMALL_Q_FACTORED_CUDA_BUTTERFLIES = Decimal("8388608")
DIRICHLET_SMALL_Q_FACTORED_CUDA_SECONDS = Decimal("0.014160607")
DIRICHLET_SMALL_Q_FACTORED_SOURCE_BENCHMARK_FREQUENCIES = Decimal("2097152")
DIRICHLET_SMALL_Q_FACTORED_SOURCE_BENCHMARK_CHARACTERS = Decimal("995")
DIRICHLET_SMALL_Q_FACTORED_SOURCE_BENCHMARK_FAMILIES = Decimal("6292451")
DIRICHLET_SMALL_Q_FACTORED_SOURCE_PRODUCER_SECONDS = Decimal("110.71")
DIRICHLET_SMALL_Q_FACTORED_SOURCE_CHECKER_SECONDS = Decimal("126.369121963")
DIRICHLET_LATTICE_TAYLOR_RESIDUES = Decimal("266697737764848")
DIRICHLET_LATTICE_GB10_RESIDUES_PER_SECOND = Decimal("69602100")
DIRICHLET_LATTICE_SEED_CPU_HOURS = Decimal("2595.6")
DIRICHLET_LATTICE_RECOVERY_REFERENCE_ITEMS_PER_SECOND = Decimal("33000")
DIRICHLET_BASE_COMPLETED_SAMPLES = Decimal("196430125886102")
DIRICHLET_FACTOR8_TARGET_SAMPLES = Decimal("1571337544104271")
DIRICHLET_FACTOR8_NONALIGNED_TARGET_SAMPLES = Decimal("1374907418218169")
DIRICHLET_FACTOR8_SINC_PRODUCT_TERMS = Decimal("54996296728726760")
# Historical direct-Arb benchmark unit: one input interval accumulated into
# one synthetic sinc sum.  It is not a target-coordinate or completed-value
# rate and is retained only to expose the old dimensionally invalid model.
DIRICHLET_POSTPROCESS_INTERVALS_PER_SECOND = Decimal("100984.52814459895")
DIRICHLET_FACTOR8_FOUR_CORNER_GB10_TARGETS_PER_SECOND = Decimal(
    "212443210.25531822"
)
DIRICHLET_FACTOR8_FUSED_GB10_TARGETS_PER_SECOND = Decimal(
    "350576167.565935"
)
DIRICHLET_FACTOR8_FUSED_MEDIAN_SPEEDUP = Decimal("1.6502112124205148")
DIRICHLET_SMALL_Q_ARB_TERMS_PER_SECOND = Decimal("95641")
DIRICHLET_RESIDUE_COMPOSITION_VALUES = Decimal("266697737764848")
DIRICHLET_RESIDUE_COMPOSITION_BATCH64_INVOCATIONS = Decimal("56981100")
DIRICHLET_RESIDUE_COMPOSITION_BATCHED_VALUES_PER_SECOND_LOW = Decimal("1166000")
DIRICHLET_RESIDUE_COMPOSITION_BATCHED_VALUES_PER_SECOND_HIGH = Decimal("1303000")
DIRICHLET_RESIDUE_COMPOSITION_MATERIALIZED_BYTES = Decimal(
    "10466854601056256"
)
DIRICHLET_LARGE_Q_FUSED_BATCH_VALUES = Decimal("266697737764848")
DIRICHLET_LARGE_Q_FUSED_BATCH_INVOCATIONS = Decimal("56981100")
DIRICHLET_LARGE_Q_FUSED_OLD_ONE_T_INVOCATIONS = Decimal("3637613167")
DIRICHLET_LARGE_Q_FUSED_GB10_VALUES_PER_SECOND = Decimal("68577057")
DIRICHLET_LARGE_Q_FUSED_LATTICE_INPUT_BYTES = Decimal("5139124740685824")
DIRICHLET_LARGE_Q_FUSED_TAIL_RECOVERY_INPUT_BYTES = Decimal(
    "13083568251320320"
)
DIRICHLET_LARGE_Q_FUSED_TOTAL_INPUT_BYTES = Decimal("18263933424590240")
DIRICHLET_LARGE_Q_SEEDED_GB10_VALUES_PER_SECOND = Decimal("19424914")
DIRICHLET_LARGE_Q_SEEDED_TOTAL_INPUT_BYTES = Decimal("5180404381680112")
DIRICHLET_RECOVERY_SEED_ARTIFACT_BYTES = Decimal("96008016")
DIRICHLET_T_MAJOR_LATTICE_PAYLOAD_BYTES = Decimal("134205145088")
DIRICHLET_T_MAJOR_LATTICE_ARTIFACT_BYTES = Decimal("134214624224")
DIRICHLET_T_MAJOR_COMPACT_TOTAL_INPUT_BYTES = Decimal("41413846139376")
DIRICHLET_ROOT_ACTIVE_MODULI = Decimal("292500")
DIRICHLET_ROOT_ADDITIVE_SEEDS = Decimal("292500")
DIRICHLET_ROOT_ADDITIVE_MULTIPLICATIONS = Decimal("59962402500")
DIRICHLET_ROOT_INPUT_RECTANGLES = Decimal("40503165302")
DIRICHLET_ROOT_PRIMITIVE_RECORDS = Decimal("29547446729")
DIRICHLET_ROOT_RADIX2_BUTTERFLIES = Decimal("2645418549056")
DIRICHLET_ROOT_STREAM_BYTES = Decimal("945546375328")
DIRICHLET_ROOT_GB10_INPUT_RECTANGLES_PER_SECOND = Decimal("39200")
DIRICHLET_ROOT_GB10_NORMALIZATIONS_PER_SECOND = Decimal("26400")
DIRICHLET_ROOT_CURRENT_TWIDDLE_CPU_HOURS = Decimal("253")
DIRICHLET_ROOT_PROCESS_STARTUP_CPU_HOURS = Decimal("32")
HOURS_PER_YEAR = Decimal("8766")

ATOM_IDS = (
    "ch25-a7-boundary",
    "ch25-psi-1e13",
    "platt-head-2e4",
    "platt-trudgian-rh-3e12",
    "helfgott-prop-12-2-4",
    "cdem-squarefree",
    "cdem-table-abel",
    "mertens-hurst",
    "ramare-zuniga-lemma-6-2",
    "helfgott-platt-theorem-4-1",
    "platt-dirichlet-theorem-7-1",
    "platt-little-mertens-2-11",
    "platt-little-mertens-stronger",
)

# These are the eleven deduplicated physical campaigns materialized by
# ``h100_cluster._physical_campaign_records``.  Four logical Mobius-family
# atoms intentionally share the one Hurst campaign.
PHYSICAL_CAMPAIGN_IDS = (
    "ch25-a7-boundary",
    "ch25-psi-two-pass-v1",
    "platt-head-2e4",
    "platt-trudgian-rh-3e12",
    "helfgott-prop-12-2-4-mpfr-v1",
    "hurst-four-residuals-v1",
    "cdem-table-abel",
    "ramare-zuniga-lemma-6-2",
    "helfgott-platt-goldbach-gpu-v1",
    "platt-dirichlet-theorem-7-1",
    "ternary-goldbach-finite-below-10pow27-v1",
)


class ProductionSizingError(ValueError):
    """A price response or sizing input failed closed."""


@lru_cache(maxsize=1)
def _dirichlet_compact_v3_storage_projection() -> dict[str, Any]:
    """Recompute the exact v3 storage model once per sizing process."""

    return source_storage_projection_v3()


@dataclass(frozen=True)
class RuntimeRange:
    atom_id: str
    implementation: str
    execution_class: str
    readiness: str
    wall_hours_low: Decimal | None
    wall_hours_high: Decimal | None
    nodes: int
    basis: str
    blocks_complete_portfolio_estimate: bool = False

    def as_json(self) -> dict[str, Any]:
        value = asdict(self)
        for field in ("wall_hours_low", "wall_hours_high"):
            item = value[field]
            value[field] = None if item is None else str(item)
        return value


def _runtime_ranges() -> tuple[RuntimeRange, ...]:
    """Return the reviewed 8-node planning model.

    The ranges are intentionally broad.  Only retained full-run measurements
    use ``measured`` readiness.  ``implemented_projected`` means executable
    source exists but no Azure H100 production run has calibrated it.
    An incomplete composition of measured components is not assigned a made-up
    end-to-end runtime.
    """

    return (
        RuntimeRange(
            "ch25-a7-boundary",
            "pinned FLINT/Arb boundary replay",
            "cpu_sidecar",
            "measured",
            Decimal("0.0004"),
            Decimal("0.001"),
            1,
            "retained 16,191-leaf replay: 1.56 seconds on the DGX Spark host",
        ),
        RuntimeRange(
            "ch25-psi-1e13",
            "two-pass primesieve plus correctly-directed CRlibm log shards",
            "cpu_sharded_on_ncc",
            "implemented_projected",
            Decimal("0.5"),
            Decimal("2"),
            8,
            "20 concurrent 100-million-integer shards measured 25.93 million event-passes/s on the 20-core DGX Spark CPU; full two-pass projection is 7.415 host-hours and the Azure range awaits a 1--2-billion-event NCC pilot",
        ),
        RuntimeRange(
            "platt-head-2e4",
            "pinned FLINT indexed-zero replay",
            "cpu_sidecar",
            "measured",
            Decimal("0.034"),
            Decimal("0.04"),
            1,
            "retained full replay: approximately 124 seconds",
        ),
        RuntimeRange(
            "platt-trudgian-rh-3e12",
            "pinned FLINT 3.6 Platt indexed-zero isolation and count replay",
            "cpu_sharded_on_dc96as_v6",
            "implemented_impractical_projection",
            ZETA_MEASURED_PROJECTED_PROCESS_HOURS
            / Decimal(CPU_NODE_COUNT * CPU_CORES_PER_NODE),
            ZETA_MEASURED_PROJECTED_PROCESS_HOURS
            / Decimal(CPU_NODE_COUNT * CPU_CORES_PER_NODE),
            CPU_NODE_COUNT,
            "the pinned FLINT 3.6 count-only engine measured 4,096 source-index isolations in 44.823 seconds (91.3817 zeros/s/process); the literal source count projects to 37,580,948 process-hours, or 97,867.052 ideal wall-hours (11.164 365.25-day years) on four 96-core DC96as_v6 CPU nodes, before campaign and attestation overhead",
        ),
        RuntimeRange(
            "helfgott-prop-12-2-4",
            "four source-built MPFR/GMP worker groups with a second measured replay",
            "cpu_sidecar",
            "implemented_projected",
            Decimal("0.55"),
            Decimal("3.34"),
            4,
            "3,389,047,618 q rows; the native 192-bit MPFR/GMP pilot gives a reviewed 105.6--640 core-hour production band per replay, and the measured protocol runs two complete replays over four 96-core DC96as_v6 nodes; Azure range awaits a full-node pilot",
        ),
        RuntimeRange(
            "cdem-squarefree",
            "shared pinned Hurst segmented-Mobius two-pass campaign",
            "cpu_sharded_on_ncc",
            "implemented_projected",
            Decimal("48"),
            Decimal("528"),
            8,
            "shares the one 10^16 Mobius stream and its two independent passes with three other atoms",
        ),
        RuntimeRange(
            "cdem-table-abel",
            "reviewed OpenMP producer plus independent chunk replay",
            "cpu_sidecar",
            "measured",
            Decimal("0.036"),
            Decimal("0.06"),
            1,
            "full producer and replay measurements are under three minutes combined",
        ),
        RuntimeRange(
            "mertens-hurst",
            "shared pinned Hurst segmented-Mobius two-pass campaign",
            "cpu_sharded_on_ncc",
            "implemented_projected",
            Decimal("48"),
            Decimal("528"),
            8,
            "same physical run as cdem-squarefree and both little-Mertens atoms; local 10-billion-row shard was 7.38 seconds on GB10 CPU",
        ),
        RuntimeRange(
            "ramare-zuniga-lemma-6-2",
            "one exact CUDA prefix-chain job plus independent in-node host replay",
            "single_ncc_h100_terminal",
            "implemented_projected",
            Decimal("1"),
            Decimal("8"),
            1,
            "21 billion rows; three low- and three terminal-million GB10 samples took median 1.004 and 1.037 seconds for the producer and 0.922 and 0.897 seconds for the independent one-thread CPU replay; this is not an H100 measurement",
        ),
        RuntimeRange(
            "helfgott-platt-theorem-4-1",
            "lowered finite Goldbach campaign plus certified n=45 prime ladder",
            "eight_h100_binary_plus_cpu_ladder",
            "implemented_conditional_10pow27_handoff_unrun_h100_calibration",
            Decimal("141.004910093284"),
            Decimal("352.512275233210"),
            8,
            "conditional on the independently proved analytic crossover being wired at 10^27: the exact lowered branch has 15,624,999,999,999,999 evens and 7,106 ladder ranges; the displayed 141.00--352.51 hour band assumes 5x--2x the GB10 throughput on eight H100s, is not an H100 measurement, and no production branch has run",
        ),
        RuntimeRange(
            "platt-dirichlet-theorem-7-1",
            "certified small-q disk/DFT and persistent large-q lattice/composition/all-character/root-number components with conditional zero closure",
            "h100_or_cpu_cluster",
            "optimized_components_implemented_pipeline_incomplete",
            None,
            None,
            8,
            "the rigorous direct FLINT fallback is full-domain executable; certified small-q disk arithmetic and semantic sign reduction, persistent residue composition and all-character framing, scalable root-number production, certified lattice inputs, and conditional postprocess arithmetic have executable implementations and retained KATs, but no full source supervisor/run exists, the small-q transient-pipe/fusion and accumulated-width boundaries are unresolved, and uniform interpolation plus corrected Turing branch/normalization remain open",
            True,
        ),
        RuntimeRange(
            "platt-little-mertens-2-11",
            "shared pinned Hurst segmented-Mobius two-pass campaign",
            "cpu_sharded_on_ncc",
            "implemented_projected",
            Decimal("48"),
            Decimal("528"),
            8,
            "included without additional asymptotic work in the shared 10^16 Mobius stream",
        ),
        RuntimeRange(
            "platt-little-mertens-stronger",
            "shared pinned Hurst segmented-Mobius two-pass campaign",
            "cpu_sharded_on_ncc",
            "implemented_projected",
            Decimal("48"),
            Decimal("528"),
            8,
            "included without additional asymptotic work in the shared 10^16 Mobius stream",
        ),
    )


def _backend_optimizer_catalog(
    *,
    goldbach_binary_h100_node_hours_low: Decimal,
    goldbach_binary_h100_node_hours_high: Decimal,
    dirichlet_cpu_dc96_node_hours_low: Decimal,
    dirichlet_cpu_dc96_node_hours_high: Decimal,
    dirichlet_gpu_h100_node_hours_low: Decimal,
    dirichlet_gpu_h100_node_hours_high: Decimal,
    hurst_h100_affine_projection: Mapping[str, Any],
    target_sku_calibrations: Sequence[Mapping[str, Any]] = (),
) -> tuple[tuple[CampaignRoute, ...], list[dict[str, Any]]]:
    """Build the reviewed route matrix and its retained evidence inventory.

    ``eligible`` here means that the exact implementation has a retained
    full-run or source-shaped reference-host rate from which node-hours can be
    derived.  It does not mean that the Azure SKU itself was measured; that is
    carried separately on every demand.  GB10-to-H100 transfers and incomplete
    component compositions remain sensitivity-only and cannot win selection.
    """

    routes: list[CampaignRoute] = []
    evidence: list[dict[str, Any]] = []

    def unavailable(campaign_id: str, configuration: str, reason: str) -> None:
        routes.append(
            CampaignRoute(
                campaign_id=campaign_id,
                route_id=f"{campaign_id}:{configuration}",
                configuration_class=configuration,
                readiness="unavailable",
                demands=(),
                basis="No defensible node-hour conversion is available.",
                unavailable_reason=reason,
            )
        )

    def demand(
        resource: str,
        low: Decimal,
        high: Decimal,
        *,
        default_nodes: int,
        cap: int,
        evidence_id: str,
        calibrated: bool,
        scope: str,
        basis: str,
    ) -> ResourceDemand:
        return ResourceDemand(
            resource_class=resource,
            node_hours_low=low,
            node_hours_high=high,
            default_nodes=default_nodes,
            parallelism_cap=cap,
            evidence_id=evidence_id,
            calibrated=calibrated,
            calibration_scope=scope,
            target_sku_measured=False,
            basis=basis,
        )

    def add_cpu_campaign(
        campaign_id: str,
        *,
        evidence_id: str,
        core_hours_low: Decimal,
        core_hours_high: Decimal,
        basis: str,
        evidence_row: dict[str, Any],
        serial_node_hours: bool = False,
    ) -> None:
        evidence.append({"campaign_id": campaign_id, **evidence_row})
        if serial_node_hours:
            cpu_low, cpu_high = core_hours_low, core_hours_high
            ncc_low, ncc_high = core_hours_low, core_hours_high
            cpu_default = ncc_default = 1
            cpu_cap = ncc_cap = 1
        else:
            cpu_low = core_hours_low / Decimal(CPU_CORES_PER_NODE)
            cpu_high = core_hours_high / Decimal(CPU_CORES_PER_NODE)
            ncc_low = core_hours_low / Decimal(40)
            ncc_high = core_hours_high / Decimal(40)
            cpu_default, ncc_default = CPU_NODE_COUNT, PRODUCTION_NODE_COUNT
            cpu_cap, ncc_cap = 64, 8
        routes.extend(
            [
                CampaignRoute(
                    campaign_id,
                    f"{campaign_id}:dc96-cpu",
                    "cpu_only",
                    "eligible",
                    (
                        demand(
                            "dc96_cpu",
                            cpu_low,
                            cpu_high,
                            default_nodes=cpu_default,
                            cap=cpu_cap,
                            evidence_id=evidence_id,
                            calibrated=True,
                            scope="retained_reference_host_rate_transfer",
                            basis=basis,
                        ),
                    ),
                    "Run the measured CPU implementation on DC96as_v6 nodes.",
                ),
                CampaignRoute(
                    campaign_id,
                    f"{campaign_id}:ncc-host-cpu",
                    "h100_only",
                    "eligible",
                    (
                        demand(
                            "ncc_h100",
                            ncc_low,
                            ncc_high,
                            default_nodes=ncc_default,
                            cap=ncc_cap,
                            evidence_id=evidence_id,
                            calibrated=True,
                            scope="retained_reference_host_rate_transfer",
                            basis=(
                                basis
                                + " The H100 is idle; only the NCC host CPUs are used."
                            ),
                        ),
                    ),
                    "Run the same CPU implementation on NCC host CPUs; no GPU acceleration is claimed.",
                ),
            ]
        )
        unavailable(
            campaign_id,
            "mixed",
            "the retained implementation has no independently calibrated CPU/GPU split",
        )

    add_cpu_campaign(
        "ch25-a7-boundary",
        evidence_id="a7-full-source-replay-20260721",
        core_hours_low=Decimal("0.0004"),
        core_hours_high=Decimal("0.001"),
        serial_node_hours=True,
        basis="One retained full 16,191-leaf replay took 1.56 seconds; the range allows process startup.",
        evidence_row={
            "source_work": "16191 boundary leaves",
            "retained_measurement": "1.56 seconds full replay",
            "scope": "full_source",
        },
    )
    add_cpu_campaign(
        "ch25-psi-two-pass-v1",
        evidence_id="psi-two-pass-20-worker-source-height-pilot-20260721",
        core_hours_low=Decimal("160"),
        core_hours_high=Decimal("640"),
        basis="The retained 20-worker pilot measured 25.93 million event-passes/s; 160--640 core-hours preserves the reviewed 0.5--2 hour eight-NCC range.",
        evidence_row={
            "source_work": "100000 fixed leaves, each replayed in two passes",
            "retained_rate": "25.93 million prime-power event-passes/second across 20 reference-host workers",
            "scope": "source_height_shards",
        },
    )
    add_cpu_campaign(
        "platt-head-2e4",
        evidence_id="zeta-head-full-replay-20260721",
        core_hours_low=Decimal("0.034"),
        core_hours_high=Decimal("0.04"),
        serial_node_hours=True,
        basis="The complete pinned-FLINT replay took approximately 124 seconds.",
        evidence_row={
            "source_work": "22492 indexed zero records including the cutoff sentinel",
            "retained_measurement": "approximately 124 seconds full replay",
            "scope": "full_source",
        },
    )
    add_cpu_campaign(
        "platt-trudgian-rh-3e12",
        evidence_id="flint36-platt-4096-source-index-pilot-20260721",
        core_hours_low=ZETA_MEASURED_PROJECTED_PROCESS_HOURS,
        core_hours_high=ZETA_MEASURED_PROJECTED_PROCESS_HOURS,
        basis="12,363,153,437,138 source zeros divided by the retained 91.3817 zeros/s/process rate gives 37,580,948 process-hours.",
        evidence_row={
            "source_work": "12363153437138 multiplicity-counted zeros plus sentinel",
            "retained_rate": "91.3817 zero isolations/second/process at the source index",
            "scope": "source_height_index_sample",
        },
    )
    add_cpu_campaign(
        "helfgott-prop-12-2-4-mpfr-v1",
        evidence_id="prop1224-native-mpfr-row-pilot-20260721",
        core_hours_low=Decimal("211.2"),
        core_hours_high=Decimal("1280"),
        basis="The native MPFR/GMP runner measured 12,600--14,400 empty rows/s/core; 105.6--640 core-hours per replay retains allowance for q=1 and nonempty rows, and the measured protocol performs two complete replays.",
        evidence_row={
            "source_work": "3389047618 q rows",
            "retained_rate": "12600--14400 empty q rows/second/core",
            "scope": "source_shaped_empty_row_pilot_with_overhead_band_and_two_measured_replays",
        },
    )
    add_cpu_campaign(
        "hurst-four-residuals-v1",
        evidence_id="hurst-10b-row-shard-pilot-20260721",
        core_hours_low=Decimal("15360"),
        core_hours_high=Decimal("168960"),
        basis="A 10-billion-row shard took 7.38 seconds; 15,360--168,960 core-hours preserves the reviewed two-pass 48--528 hour eight-NCC sensitivity.",
        evidence_row={
            "source_work": "one shared two-pass Mobius stream through 10^16",
            "retained_measurement": "7.38 seconds for one 10-billion-row shard",
            "alternative_affine_measurement": "20 million rows in 2.764 seconds at the low range and 2.85 seconds near 10^16 with eight threads; byte-semantic receipts matched after elapsed time was removed",
            "h100_affine_sensitivity": hurst_h100_affine_projection,
            "scope": "source_shaped_shard",
        },
    )
    hurst_affine_core_hours_low = (
        HURST_AFFINE_SOURCE_ROWS
        / HURST_AFFINE_SAMPLE_ROWS
        * HURST_AFFINE_LOW_RANGE_SECONDS
        / Decimal(3600)
        * HURST_AFFINE_SAMPLE_THREADS
    )
    hurst_affine_core_hours_high = (
        HURST_AFFINE_SOURCE_ROWS
        / HURST_AFFINE_SAMPLE_ROWS
        * HURST_AFFINE_TERMINAL_SECONDS
        / Decimal(3600)
        * HURST_AFFINE_SAMPLE_THREADS
    )
    routes.append(
        CampaignRoute(
            "hurst-four-residuals-v1",
            "hurst-four-residuals-v1:dc96-affine-one-pass-sensitivity",
            "cpu_only",
            "sensitivity_only",
            (
                demand(
                    "dc96_cpu",
                    hurst_affine_core_hours_low / Decimal(CPU_CORES_PER_NODE),
                    hurst_affine_core_hours_high / Decimal(CPU_CORES_PER_NODE),
                    default_nodes=CPU_NODE_COUNT,
                    cap=64,
                    evidence_id="hurst-affine-guard-20m-terminal-pilots-20260721",
                    calibrated=True,
                    scope="source_shaped_affine_guard_projection",
                    basis="Conservative exact linearization of the 2.764--2.85-second eight-thread 20-million-row affine benchmarks; the one-pass campaign schema and replay are not implemented.",
                ),
            ),
            "Exact affine-guard alternative with byte-semantic equivalence, retained only as a nonproduction route sensitivity.",
        )
    )
    hurst_h100_sensitivity = hurst_h100_affine_projection[
        "h100_sensitivity"
    ]
    hurst_h100_node_hours = Decimal(
        str(hurst_h100_sensitivity["eight_worker_node_hours"])
    )
    routes.append(
        CampaignRoute(
            "hurst-four-residuals-v1",
            (
                "hurst-four-residuals-v1:"
                "h100-eight-worker-affine-gb10-sensitivity"
            ),
            "h100_only",
            "sensitivity_only",
            (
                demand(
                    "ncc_h100",
                    hurst_h100_node_hours,
                    hurst_h100_node_hours,
                    default_nodes=PRODUCTION_NODE_COUNT,
                    cap=PRODUCTION_NODE_COUNT,
                    evidence_id=(
                        "hurst-gb10-complete-device-work-"
                        "191-737ms-20260725"
                    ),
                    calibrated=False,
                    scope=(
                        "gb10_complete_device_work_to_h100_"
                        "12_3x_uncalibrated_sensitivity"
                    ),
                    basis=(
                        "The exact eight-worker affine composition partitions "
                        "9,999,000,000,000,000 source rows into eight equal "
                        "1,249,875,000,000,000-row workers. The retained "
                        "191.737 ms per 100,000,000-row GB10 complete-device-"
                        "work measurement is divided by an unmeasured 12.3x "
                        "GB10-to-H100 sensitivity. The CPU summary/verification "
                        "prefix through 10^12 and its handoff are outside this "
                        "H100-stage arithmetic. This is not target-H100 evidence "
                        "and cannot satisfy the production gate."
                    ),
                ),
            ),
            (
                "Exact eight-worker H100 topology with a GB10-derived, "
                "uncalibrated target-H100 sensitivity."
            ),
        )
    )
    add_cpu_campaign(
        "cdem-table-abel",
        evidence_id="cdem-table-abel-full-run-20260723",
        core_hours_low=Decimal("0.036"),
        core_hours_high=Decimal("0.06"),
        serial_node_hours=True,
        basis="On the local aarch64 host, the full OpenMP producer took 86.574 seconds and the independent 1,000-chunk replay used 363.411 aggregate worker-seconds across eight workers; end-to-end wall time remained under three minutes.",
        evidence_row={
            "source_work": "five-billion-step table and 1000 replay chunks",
            "retained_measurement": (
                "86.574 seconds producer; 363.411 aggregate replay "
                "worker-seconds across eight workers; under three minutes "
                "end-to-end wall time"
            ),
            "transcript_sha256": (
                "2a1d551dee2f5e8997e8e2a77a587cb6cf53b93b32854f943591163db2460123"
            ),
            "scope": "full_source_local_aarch64_not_azure_attestation",
        },
    )

    r2_campaign = "ramare-zuniga-lemma-6-2"
    evidence.append(
        {
            "campaign_id": r2_campaign,
            "source_work": "21000000000 exact factor/transition rows",
            "retained_measurement": (
                "three-repeat GB10 medians: producer 1.003546042 s at "
                "[1,1000001) and 1.036697658 s at "
                "[20999000001,21000000001); independent one-thread CPU "
                "replay 0.921640459 s and 0.897319285 s"
            ),
            "linear_sensitivity": (
                "producer 5.85--6.05 hours and one-thread replay "
                "5.23--5.38 hours for 21 billion rows"
            ),
            "scope": (
                "bounded_source-shaped_low-and-terminal_samples_on_GB10_"
                "not_H100_or_external-atom-evidence"
            ),
        }
    )
    unavailable(
        r2_campaign,
        "cpu_only",
        (
            "the exact CPU implementation is a source-wide checker of "
            "committed receipts, not a CPU receipt producer or CPU-only "
            "registered terminal"
        ),
    )
    routes.append(
        CampaignRoute(
            r2_campaign,
            f"{r2_campaign}:h100-sensitivity",
            "h100_only",
            "sensitivity_only",
            (
                demand(
                    "ncc_h100",
                    Decimal("1"),
                    Decimal("8"),
                    default_nodes=1,
                    cap=1,
                    evidence_id="r2star-gb10-low-terminal-pair-20260723",
                    calibrated=False,
                    scope="gb10_to_h100_uncalibrated_sensitivity",
                    basis=(
                        "The implemented factory is one terminal job with a "
                        "serial incoming-state chain on one NCC H100 node. "
                        "The 1--8 node-hour band is sensitivity only; no "
                        "Azure H100 rate was measured."
                    ),
                ),
            ),
            "Exact serial CUDA prefix producer plus mandatory in-node host replay.",
        )
    )
    unavailable(
        r2_campaign,
        "mixed",
        (
            "no challenge-bound cross-job transfer, DC96 replay finalizer, "
            "or combined attested registered terminal is implemented"
        ),
    )

    historical_goldbach_campaign = "helfgott-platt-goldbach-gpu-v1"
    historical_scale = (
        Decimal(PRODUCTION_EVEN_COUNT) / Decimal(ANALYTIC_10POW27_EVEN_COUNT)
    )
    evidence.append(
        {
            "campaign_id": historical_goldbach_campaign,
            "source_work": (
                f"historical source-height binary campaign: {PRODUCTION_EVEN_COUNT} "
                f"even inputs plus {GOLDBACH_LADDER_RANGE_COUNT} ladder ranges"
            ),
            "retained_rate": (
                "769525754 evens/second on GB10; source-height H100 throughput "
                "and full ladder execution are unmeasured"
            ),
            "scope": "historical_source_height_unrun_uncalibrated_sensitivity",
        }
    )
    unavailable(
        historical_goldbach_campaign,
        "cpu_only",
        "the historical source-height binary verifier has no calibrated CPU route",
    )
    routes.append(
        CampaignRoute(
            historical_goldbach_campaign,
            f"{historical_goldbach_campaign}:h100-source-height-sensitivity",
            "h100_only",
            "sensitivity_only",
            (
                demand(
                    "ncc_h100",
                    goldbach_binary_h100_node_hours_low * historical_scale,
                    goldbach_binary_h100_node_hours_high * historical_scale,
                    default_nodes=8,
                    cap=8,
                    evidence_id="goldbach-gb10-terminal-600m-pilot-20260721",
                    calibrated=False,
                    scope="historical_source_height_linear_gb10_sensitivity",
                    basis=(
                        "Linear source-height transfer of the GB10 rate; no "
                        "confidential-H100 source-height measurement exists."
                    ),
                ),
            ),
            "Historical 4e18 binary scope kept distinct from the lowered 10^27 handoff.",
        )
    )
    unavailable(
        historical_goldbach_campaign,
        "mixed",
        "historical binary and ladder branches have no calibrated joint production route",
    )

    goldbach_campaign = "ternary-goldbach-finite-below-10pow27-v1"
    evidence.append(
        {
            "campaign_id": goldbach_campaign,
            "source_work": "conditional 10^27 handoff: 15624999999999999 even inputs plus 7106 n=45 ladder ranges",
            "retained_rate": "769525754 evens/second on GB10; lowered ladder is range-count-scaled pending a production benchmark",
            "scope": "analytic_10pow27_handoff_unrun_and_uncalibrated_h100_sensitivity",
        }
    )
    unavailable(
        goldbach_campaign,
        "cpu_only",
        "the exact lowered binary verifier is CUDA and has no calibrated CPU route",
    )
    goldbach_h100 = demand(
        "ncc_h100",
        goldbach_binary_h100_node_hours_low,
        goldbach_binary_h100_node_hours_high,
        default_nodes=8,
        cap=8,
        evidence_id="goldbach-gb10-terminal-600m-pilot-20260721",
        calibrated=False,
        scope="two_to_five_x_gb10_h100_sensitivity",
        basis="The binary branch uses the provisional 5x--2x H100/GB10 band; no H100 source-height pilot exists.",
    )
    routes.append(
        CampaignRoute(
            goldbach_campaign,
            f"{goldbach_campaign}:ncc-binary-and-host-ladder-sensitivity",
            "h100_only",
            "sensitivity_only",
            (goldbach_h100,),
            "The NCC rental contains host CPUs; the projected lowered 183--577-core-hour ladder fits inside the binary sensitivity band only as an unmeasured no-contention assumption.",
        )
    )
    routes.append(
        CampaignRoute(
            goldbach_campaign,
            f"{goldbach_campaign}:h100-binary-dc96-ladder-sensitivity",
            "mixed",
            "sensitivity_only",
            (
                goldbach_h100,
                demand(
                    "dc96_cpu",
                    GOLDBACH_10POW27_LADDER_NATIVE_PROJECTED_CORE_HOURS
                    / Decimal(CPU_CORES_PER_NODE),
                    GOLDBACH_10POW27_LADDER_PAPER_SCALED_CORE_HOURS
                    / Decimal(CPU_CORES_PER_NODE),
                    default_nodes=4,
                    cap=64,
                    evidence_id="goldbach-native-ladder-bounded-projection-20260721",
                    calibrated=False,
                    scope="lowered_range_count_scaled_projection_band",
                    basis="183 projected repository core-hours to 577 range-count-scaled historical core-hours; no lowered full range was measured.",
                ),
            ),
            "Run the CUDA binary branch and CPU prime ladder concurrently on separate pools.",
        )
    )

    dirichlet_campaign = "platt-dirichlet-theorem-7-1"
    evidence.append(
        {
            "campaign_id": dirichlet_campaign,
            "source_work": "quantified small-q v3 factored and large-q component work only",
            "small_q_v3_work": {
                "legacy_character_frequency_seeds": str(
                    DIRICHLET_SMALL_Q_FREQUENCY_VALUES
                ),
                "shared_frequency_records": str(
                    DIRICHLET_SMALL_Q_FACTORED_SHARED_RECORDS
                ),
                "primitive_characters": str(
                    DIRICHLET_SMALL_Q_PRIMITIVE_CHARACTERS
                ),
                "minimum_logical_bytes": str(
                    DIRICHLET_SMALL_Q_FACTORED_MINIMUM_LOGICAL_BYTES
                ),
                "retained_checker": "196624 distinct families in 3.272058564 seconds on one reference-host process",
                "retained_cuda": "4003136 terms plus 8388608 butterflies in 0.014160607 seconds on GB10",
            },
            "retained_rate": "GB10 and host component rates listed in dirichlet_grh_boundary.quantified_component_rows; v3 source replay uses exactly 3*shared_records+primitive_characters families",
            "scope": "components_only_pipeline_and_analytic_closure_incomplete",
        }
    )
    unavailable(
        dirichlet_campaign,
        "cpu_only",
        "the rigorous FLINT fallback is executable but has no source-scale benchmark",
    )
    dirichlet_cpu_core_hours_low = (
        dirichlet_cpu_dc96_node_hours_low * Decimal(CPU_CORES_PER_NODE)
    )
    dirichlet_cpu_core_hours_high = (
        dirichlet_cpu_dc96_node_hours_high * Decimal(CPU_CORES_PER_NODE)
    )
    routes.append(
        CampaignRoute(
            dirichlet_campaign,
            f"{dirichlet_campaign}:ncc-component-sensitivity",
            "h100_only",
            "sensitivity_only",
            (
                demand(
                    "ncc_h100",
                    dirichlet_gpu_h100_node_hours_low
                    + dirichlet_cpu_core_hours_low / Decimal(40),
                    dirichlet_gpu_h100_node_hours_high
                    + dirichlet_cpu_core_hours_high / Decimal(40),
                    default_nodes=8,
                    cap=8,
                    evidence_id="dirichlet-quantified-components-20260721",
                    calibrated=False,
                    scope="incomplete_component_composition_and_uncalibrated_h100_transfer",
                    basis="Maps quantified CPU component core-hours to NCC hosts and adds the 5x--10x GB10/H100 GPU sensitivity; missing end-to-end work remains unpriced.",
                ),
            ),
            "Conditional all-component arithmetic on NCC nodes, not a full Dirichlet campaign route.",
        )
    )
    routes.append(
        CampaignRoute(
            dirichlet_campaign,
            f"{dirichlet_campaign}:mixed-component-sensitivity",
            "mixed",
            "sensitivity_only",
            (
                demand(
                    "dc96_cpu",
                    dirichlet_cpu_dc96_node_hours_low,
                    dirichlet_cpu_dc96_node_hours_high,
                    default_nodes=4,
                    cap=64,
                    evidence_id="dirichlet-host-component-rates-20260721",
                    calibrated=False,
                    scope="components_only_not_source_closed",
                    basis="Quantified host component arithmetic; certified I/O, exception work, and analytic closure remain absent.",
                ),
                demand(
                    "ncc_h100",
                    dirichlet_gpu_h100_node_hours_low,
                    dirichlet_gpu_h100_node_hours_high,
                    default_nodes=8,
                    cap=8,
                    evidence_id="dirichlet-gb10-component-rates-20260721",
                    calibrated=False,
                    scope="five_to_ten_x_gb10_h100_sensitivity",
                    basis="Quantified CUDA component work at an unmeasured 5x--10x H100/GB10 sensitivity.",
                ),
            ),
            "Conditional CPU/GPU component composition, explicitly not a source-wide campaign ETA.",
        )
    )

    order = {campaign_id: index for index, campaign_id in enumerate(PHYSICAL_CAMPAIGN_IDS)}
    routes.sort(key=lambda route: order[route.campaign_id])
    if tuple(dict.fromkeys(route.campaign_id for route in routes)) != PHYSICAL_CAMPAIGN_IDS:
        raise ProductionSizingError(
            "backend optimizer catalogue does not preserve physical campaign order"
        )
    if len(routes) < 3 * len(PHYSICAL_CAMPAIGN_IDS):
        raise ProductionSizingError(
            "backend optimizer catalogue must classify at least three routes per campaign"
        )
    calibrations = {
        calibration_key(manifest): manifest
        for manifest in target_sku_calibrations
    }
    matched: set[tuple[str, str, str]] = set()
    calibrated_routes: list[CampaignRoute] = []
    for route in routes:
        demands: list[ResourceDemand] = []
        for row in route.demands:
            key = (route.campaign_id, route.route_id, row.resource_class)
            manifest = calibrations.get(key)
            if manifest is None:
                demands.append(row)
                continue
            if manifest["target"]["region"] != AZURE_REGION:
                raise ProductionSizingError(
                    f"target-SKU calibration for {route.route_id} is not in "
                    f"the sizing region {AZURE_REGION}"
                )
            if manifest["target"]["node_count"] != row.default_nodes:
                raise ProductionSizingError(
                    f"target-SKU calibration for {route.route_id} has node_count "
                    "different from the route default"
                )
            high_num, high_den = conservative_high_node_hours(manifest)
            demand_num, demand_den = row.node_hours_high.as_integer_ratio()
            if high_num * demand_den != demand_num * high_den:
                raise ProductionSizingError(
                    f"target-SKU calibration for {route.route_id} does not bind "
                    "the route's conservative high node-hour endpoint"
                )
            matched.add(key)
            demands.append(
                replace(
                    row,
                    evidence_id=manifest["manifest_sha256"],
                    calibration_scope=(
                        "validated_target_sku_sample_with_conservative_"
                        "source_node_hour_projection"
                    ),
                    target_sku_measured=True,
                    basis=(
                        row.basis
                        + " Target-SKU timing evidence is bound by calibration "
                        + manifest["manifest_sha256"]
                        + "; its high endpoint remains a projection."
                    ),
                )
            )
        calibrated_routes.append(replace(route, demands=tuple(demands)))
    unmatched = set(calibrations) - matched
    if unmatched:
        raise ProductionSizingError(
            "target-SKU calibration does not match an exact route resource: "
            + ", ".join("/".join(key) for key in sorted(unmatched))
        )
    return tuple(calibrated_routes), evidence


def _price_filter(sku: str = NCC_SKU) -> str:
    return (
        "serviceName eq 'Virtual Machines' and "
        f"armSkuName eq '{sku}' and armRegionName eq '{AZURE_REGION}'"
    )


def retail_prices_url(sku: str = NCC_SKU) -> str:
    if sku not in {NCC_SKU, CPU_SKU}:
        raise ProductionSizingError(f"unsupported Azure sizing SKU: {sku}")
    return AZURE_RETAIL_PRICES_API + "?" + urlencode({"$filter": _price_filter(sku)})


def parse_retail_prices(
    response: object, *, sku: str = NCC_SKU
) -> dict[str, Decimal]:
    """Extract current Linux consumption and spot prices from an API page."""

    if sku not in {NCC_SKU, CPU_SKU}:
        raise ProductionSizingError(f"unsupported Azure sizing SKU: {sku}")
    if not isinstance(response, dict) or not isinstance(response.get("Items"), list):
        raise ProductionSizingError("Azure price response has no Items array")
    selected: dict[str, tuple[str, Decimal]] = {}
    for item in response["Items"]:
        if not isinstance(item, dict):
            continue
        if (
            item.get("armSkuName") != sku
            or item.get("armRegionName") != AZURE_REGION
            or item.get("currencyCode") != "USD"
            or item.get("type") != "Consumption"
            or item.get("unitOfMeasure") != "1 Hour"
            or " Win" in str(item.get("productName", ""))
            or "Low Priority" in str(item.get("skuName", ""))
        ):
            continue
        sku_name = item.get("skuName")
        price = item.get("retailPrice")
        effective = item.get("effectiveStartDate")
        if not isinstance(sku_name, str) or not isinstance(effective, str):
            continue
        try:
            decimal_price = Decimal(str(price))
        except Exception:
            continue
        if decimal_price <= 0:
            continue
        name = "spot" if sku_name.endswith(" Spot") else "pay_as_you_go"
        old = selected.get(name)
        if old is None or effective > old[0]:
            selected[name] = (effective, decimal_price)
    if set(selected) != {"pay_as_you_go", "spot"}:
        raise ProductionSizingError("Azure response lacks unique Linux PAYG and spot rates")
    return {name: selected[name][1] for name in sorted(selected)}


def fetch_retail_prices(
    opener: Callable[..., Any] = urlopen,
    *,
    sku: str = NCC_SKU,
) -> dict[str, Decimal]:
    with opener(retail_prices_url(sku), timeout=30) as response:
        return parse_retail_prices(json.load(response), sku=sku)


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _dominant_campaign_budget_review(
    optimizer: Mapping[str, Any],
) -> dict[str, Any]:
    """Machine-readable one-week/$10k audit of the three dominant atoms.

    The record deliberately distinguishes fresh computation, imported source
    artifacts, and incomplete optimized components.  A publication or an
    aggregate status page is never promoted to a replayable artifact.
    """

    route_matrix = optimizer.get("route_matrix")
    if not isinstance(route_matrix, list):
        raise ProductionSizingError("backend optimizer has no route matrix")

    def target_sku_measured(campaign_id: str) -> bool:
        return any(
            demand.get("target_sku_measured") is True
            for row in route_matrix
            if isinstance(row, dict) and row.get("campaign_id") == campaign_id
            for demand in row.get("demands", [])
            if isinstance(demand, dict)
        )

    def route_summary(campaign_id: str) -> dict[str, Any]:
        rows = [
            row
            for row in route_matrix
            if isinstance(row, dict) and row.get("campaign_id") == campaign_id
        ]
        if not rows:
            raise ProductionSizingError(
                f"dominant campaign is absent from optimizer: {campaign_id}"
            )
        priced = [row for row in rows if row.get("cost_usd") is not None]
        best_wall = None
        if priced:
            best_wall = min(
                Decimal(
                    row["production_gate"][
                        "best_ideal_wall_hours_within_caps"
                    ]["high"]
                )
                for row in priced
            )
        return {
            "best_priced_high_wall_hours_within_caps": (
                None if best_wall is None else str(best_wall)
            ),
            "any_route_budget_feasible": {
                price_class: any(
                    row["production_gate"]["budget_feasible"][price_class]
                    for row in rows
                )
                for price_class in ("pay_as_you_go", "spot")
            },
            "any_route_production_ready": {
                price_class: any(
                    row["production_gate"]["production_ready"][price_class]
                    for row in rows
                )
                for price_class in ("pay_as_you_go", "spot")
            },
            "routes": [
                {
                    "route_id": row["route_id"],
                    "readiness": row["readiness"],
                    "production_gate": row["production_gate"],
                }
                for row in rows
            ],
        }

    campaigns = {
        "platt-trudgian-rh-3e12": {
            "claim_scope": {
                "height": 3_000_175_332_800,
                "multiplicity_counted_zeros": 12_363_153_437_138,
                "sentinel_required": True,
            },
            "fresh_compute": {
                "algorithm": "pinned FLINT 3.6 Platt/Turing indexed isolation",
                "projected_process_hours": str(
                    ZETA_MEASURED_PROJECTED_PROCESS_HOURS
                ),
                "source_closed": True,
                "within_budget": False,
            },
            "artifact_replay": {
                "primary_public_route": "https://beta.lmfdb.org/data/riemann-zeta-zeros/",
                "status": "insufficient_scope",
                "reason": "LMFDB publishes rigorous Platt zero blocks, but not the exact 12,363,153,437,138-zero PT21 source range and sentinel required here.",
                "promotion_requirements": [
                    "author- or archive-published exact PT21 block inventory",
                    "cryptographic digest and byte size for every block",
                    "multiplicity-preserving parser and exact gap-free index coverage",
                    "Turing completeness/count metadata through the source sentinel",
                ],
                "bounded_or_partial_artifact_can_promote": False,
            },
            "optimizer": route_summary("platt-trudgian-rh-3e12"),
        },
        "helfgott-platt-goldbach-gpu-v1": {
            "claim_scope": {
                "binary_even_start": 4,
                "binary_even_limit": 4_000_000_000_000_000_000,
                "binary_even_count": str(PRODUCTION_EVEN_COUNT),
                "ladder_range_count": GOLDBACH_LADDER_RANGE_COUNT,
                "both_branches_required": True,
            },
            "fresh_compute": {
                "binary_algorithm": "hardened source-height CUDA GoldbachGPU",
                "ladder_algorithm": "native GMP Proth/Pocklington producer plus independent replay",
                "source_closed": True,
                "h100_target_rate_measured": target_sku_measured(
                    "helfgott-platt-goldbach-gpu-v1"
                ),
                "within_budget": False,
            },
            "analytic_10pow27_handoff": {
                "status": "implemented_unrun_h100_calibration_required",
                "binary_even_start": 4,
                "binary_even_limit": 31_250_000_000_000_000,
                "binary_even_count": str(ANALYTIC_10POW27_EVEN_COUNT),
                "binary_shards": ANALYTIC_10POW27_SHARDS,
                "ladder_range_count": GOLDBACH_10POW27_LADDER_RANGE_COUNT,
                "ladder_proth_exponent": 45,
                "semantic_target_inclusive": str(10**27),
                "requires_proved_analytic_crossover_integration": True,
                "production_receipts_present": False,
                "h100_calibration_passed": target_sku_measured(
                    "ternary-goldbach-finite-below-10pow27-v1"
                ),
            },
            "artifact_replay": {
                "primary_public_route": "https://sweet.ua.pt/tos/goldbach.html",
                "status": "aggregate_status_not_replay_certificate",
                "reason": "The authors report complete interval status and aggregate checks, but the public page is not a gap-free authenticated per-interval witness bundle consumable by this verifier.",
                "promotion_requirements": [
                    "exact 4e18 interval inventory and immutable result objects",
                    "independent checker semantics for every interval",
                    "complete Helfgott-Platt ladder artifacts or fresh ladder replay",
                    "exact reduction binding the two artifact families",
                ],
                "citation_alone_can_promote": False,
            },
            "optimizer": route_summary("helfgott-platt-goldbach-gpu-v1"),
        },
        "ternary-goldbach-finite-below-10pow27-v1": {
            "claim_scope": {
                "binary_even_start": 4,
                "binary_even_limit": 31_250_000_000_000_000,
                "binary_even_count": str(ANALYTIC_10POW27_EVEN_COUNT),
                "binary_shards": ANALYTIC_10POW27_SHARDS,
                "h100_groups": 8_192,
                "binary_leaves_per_group": 8,
                "ladder_range_count": GOLDBACH_10POW27_LADDER_RANGE_COUNT,
                "semantic_target_inclusive": str(10**27),
                "both_branches_required": True,
            },
            "fresh_compute": {
                "binary_algorithm": (
                    "65,536 hardened lowered GoldbachGPU leaves in 8,192 "
                    "challenge-first H100 groups"
                ),
                "ladder_algorithm": (
                    "7,106 native GMP n=45 ranges with independent reduction"
                ),
                "source_closed": True,
                "measured_job_factories_complete": True,
                "production_receipts_present": False,
                "h100_target_rate_measured": target_sku_measured(
                    "ternary-goldbach-finite-below-10pow27-v1"
                ),
                "within_budget": False,
            },
            "sizing_boundary": {
                "binary_basis": (
                    "retained 769525754 evens/second GB10 rate transferred at "
                    "an unmeasured 2x--5x H100 sensitivity"
                ),
                "ladder_core_hours_low": str(
                    GOLDBACH_10POW27_LADDER_NATIVE_PROJECTED_CORE_HOURS
                ),
                "ladder_core_hours_high": str(
                    GOLDBACH_10POW27_LADDER_PAPER_SCALED_CORE_HOURS
                ),
                "classification": (
                    "exact_work_count_projection_not_h100_measurement_or_completed_run"
                ),
            },
            "optimizer": route_summary(
                "ternary-goldbach-finite-below-10pow27-v1"
            ),
        },
        "platt-dirichlet-theorem-7-1": {
            "claim_scope": {
                "q_min": 2,
                "q_max": 400_000,
                "primitive_character_count": 29_565_923_837,
                "q_one_zeta_prerequisite": True,
            },
            "fresh_compute": {
                "reference_algorithm": "rigorous FLINT argument-principle fallback",
                "optimized_components": "certified lattice, fused Taylor/composition, all-character transforms, roots, small-q disk DFT, conditional zero closure",
                "source_closed": False,
                "within_budget": False,
                "dominant_missing_work": [
                    "source-wide useful-width proof and exception policy",
                    "completed-L/Hardy evaluator realization",
                    "uniform interpolation and theorem-level realization of the corrected reflected paired-Turing closure",
                    "source-scale certified input/replay transport",
                ],
            },
            "artifact_replay": {
                "primary_public_route": "https://arxiv.org/abs/1305.3087",
                "status": "paper_only_no_full_machine_artifact_identified",
                "promotion_requirements": [
                    "exact primitive-character roster and parity-height inventory",
                    "all zero brackets with multiplicity and completeness data",
                    "pinned parser/checker semantics and cryptographic file inventory",
                    "q=1 zeta prerequisite artifact",
                ],
                "paper_statement_can_promote": False,
            },
            "optimizer": route_summary("platt-dirichlet-theorem-7-1"),
        },
    }
    return {
        "schema": "sparkinterval.tg.dominant-campaign-budget-review.v1",
        "hard_limits": {
            "wall_hours": optimizer["production_budget"][
                "hard_max_wall_hours"
            ],
            "cost_usd": optimizer["production_budget"]["hard_max_cost_usd"],
            "high_endpoints_control": True,
        },
        "campaigns": campaigns,
        "all_three_production_ready": {
            price_class: all(
                row["optimizer"]["any_route_production_ready"][price_class]
                for row in campaigns.values()
            )
            for price_class in ("pay_as_you_go", "spot")
        },
        "conclusion": "no_current_source-closed_route_meets_the_one-week_10000-usd_release_gate",
    }


def build_sizing_report(
    *,
    prices: dict[str, Decimal] | None = None,
    cpu_prices: dict[str, Decimal] | None = None,
    deadline_hours: Decimal | None = None,
    max_cpu_nodes: int = 64,
    max_h100_nodes: int = PRODUCTION_NODE_COUNT,
    production_max_wall_hours: Decimal = PRODUCTION_MAX_WALL_HOURS,
    production_max_cost_usd: Decimal = PRODUCTION_MAX_COST_USD,
    target_sku_calibrations: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        checked_target_calibrations = validate_manifest_set(
            target_sku_calibrations
        )
    except TargetSKUCalibrationError as error:
        raise ProductionSizingError(
            f"invalid target-SKU calibration manifest: {error}"
        ) from error
    rates = PRICE_SNAPSHOT_USD_PER_NODE_HOUR if prices is None else prices
    cpu_rates = (
        CPU_PRICE_SNAPSHOT_USD_PER_NODE_HOUR
        if cpu_prices is None
        else cpu_prices
    )
    for name, price_map in (("prices", rates), ("cpu_prices", cpu_rates)):
        if set(price_map) != {"pay_as_you_go", "spot"}:
            raise ProductionSizingError(
                f"{name} must contain pay_as_you_go and spot"
            )
        if any(
            not isinstance(rate, Decimal) or rate <= 0
            for rate in price_map.values()
        ):
            raise ProductionSizingError(f"{name} must be positive Decimal values")
    ranges = _runtime_ranges()
    if tuple(row.atom_id for row in ranges) != ATOM_IDS:
        raise ProductionSizingError("runtime model does not cover the exact atom order")
    dirichlet_compact_v3_storage = _dirichlet_compact_v3_storage_projection()
    blockers = [row.atom_id for row in ranges if row.blocks_complete_portfolio_estimate]
    # Four logical atoms share one physical Hurst/Mobius pass.  Counting those
    # rows independently would overstate both runtime and price by three full
    # 10^16 campaigns.  Zeta and Goldbach are excluded from the short practical
    # subset because their literal source projections take years.  Dirichlet is
    # excluded because its implemented components do not yet compose into a
    # production-closed source-scale engine with a defensible ETA.
    practical_physical_atom_ids = (
        "ch25-a7-boundary",
        "ch25-psi-1e13",
        "platt-head-2e4",
        "helfgott-prop-12-2-4",
        "mertens-hurst",
        "cdem-table-abel",
        "ramare-zuniga-lemma-6-2",
    )
    by_atom = {row.atom_id: row for row in ranges}
    practical_rows = [by_atom[atom_id] for atom_id in practical_physical_atom_ids]
    if any(
        row.wall_hours_low is None or row.wall_hours_high is None
        for row in practical_rows
    ):
        raise ProductionSizingError("practical subset contains an unpriced campaign")
    serialized_low = sum(
        (row.wall_hours_low for row in practical_rows), start=Decimal(0)
    )
    serialized_high = sum(
        (row.wall_hours_high for row in practical_rows), start=Decimal(0)
    )
    # The practical jobs can use CPU and GPU resources concurrently.  Taking
    # only the longest row is an optimistic scheduling envelope, not a measured
    # co-location claim.
    overlapped_low = max(row.wall_hours_low for row in practical_rows)
    overlapped_high = max(row.wall_hours_high for row in practical_rows)

    ncc_hourly_cost = {
        name: Decimal(PRODUCTION_NODE_COUNT) * rate for name, rate in rates.items()
    }
    cpu_hourly_cost = {
        name: Decimal(CPU_NODE_COUNT) * rate for name, rate in cpu_rates.items()
    }
    one_ncc_hourly_cost = dict(rates)

    def _cost_range(
        low: Decimal,
        high: Decimal,
        hourly: Mapping[str, Decimal],
    ) -> dict[str, dict[str, str]]:
        return {
            name: {
                "low": _money(low * rate),
                "high": _money(high * rate),
            }
            for name, rate in hourly.items()
        }

    def _mixed_cost_range(
        low: Decimal,
        high: Decimal,
    ) -> dict[str, dict[str, str]]:
        # The CPU cluster is conservatively kept for the whole envelope; one
        # NCC node is added for the 1--8 hour R2Star GPU campaign.  Goldbach is
        # deliberately absent from this practical subset.
        return {
            name: {
                "low": _money(
                    low * cpu_hourly_cost[name]
                    + Decimal(1) * one_ncc_hourly_cost[name]
                ),
                "high": _money(
                    high * cpu_hourly_cost[name]
                    + Decimal(8) * one_ncc_hourly_cost[name]
                ),
            }
            for name in ("pay_as_you_go", "spot")
        }

    zeta = by_atom["platt-trudgian-rh-3e12"]
    assert zeta.wall_hours_low is not None and zeta.wall_hours_high is not None
    zeta_process_hours = ZETA_MEASURED_PROJECTED_PROCESS_HOURS
    zeta_cpu_cluster_hours = zeta_process_hours / Decimal(
        CPU_NODE_COUNT * CPU_CORES_PER_NODE
    )
    zeta_ncc_host_hours = zeta_process_hours / Decimal(
        PRODUCTION_NODE_COUNT * 40
    )
    zeta_historical_cpu_hours = ZETA_PAPER_REPORTED_CORE_HOURS / Decimal(
        CPU_NODE_COUNT * CPU_CORES_PER_NODE
    )
    historical_goldbach_projection = project_source_height(
        sample_even_count=GOLDBACH_SAMPLE_EVEN_COUNT,
        sample_seconds=GOLDBACH_SAMPLE_SECONDS,
        speedups=GOLDBACH_H100_SENSITIVITY_FACTORS,
        cluster_gpu_count=PRODUCTION_NODE_COUNT,
    )
    goldbach_projection = project_source_height(
        sample_even_count=GOLDBACH_SAMPLE_EVEN_COUNT,
        sample_seconds=GOLDBACH_SAMPLE_SECONDS,
        speedups=GOLDBACH_H100_SENSITIVITY_FACTORS,
        cluster_gpu_count=PRODUCTION_NODE_COUNT,
        production_even_count=ANALYTIC_10POW27_EVEN_COUNT,
        production_shards=ANALYTIC_10POW27_SHARDS,
    )
    goldbach_rows: list[dict[str, Any]] = []
    for raw_row in goldbach_projection["rows"]:
        if not isinstance(raw_row, dict):
            raise ProductionSizingError("Goldbach projection emitted a malformed row")
        wall_hours = Decimal(str(raw_row["cluster_wall_hours"]))
        goldbach_rows.append(
            {
                **raw_row,
                "eight_ncc_compute_cost_usd": _cost_range(
                    wall_hours, wall_hours, ncc_hourly_cost
                ),
            }
        )

    historical_goldbach_rows: list[dict[str, Any]] = []
    for raw_row in historical_goldbach_projection["rows"]:
        if not isinstance(raw_row, dict):
            raise ProductionSizingError(
                "historical Goldbach projection emitted a malformed row"
            )
        wall_hours = Decimal(str(raw_row["cluster_wall_hours"]))
        historical_goldbach_rows.append(
            {
                **raw_row,
                "eight_ncc_compute_cost_usd": _cost_range(
                    wall_hours, wall_hours, ncc_hourly_cost
                ),
            }
        )

    ladder_core_hour_models = {
        "compiled_native_bounded_projection": (
            GOLDBACH_10POW27_LADDER_NATIVE_PROJECTED_CORE_HOURS,
            "7,106/492,700 scaling of the source-height bounded native-producer/replay linearization; no full lowered range or general-prime fallback was measured",
        ),
        "paper_report_scaled_by_range_count": (
            GOLDBACH_10POW27_LADDER_PAPER_SCALED_CORE_HOURS,
            "historical complete-campaign core-hours multiplied by 7,106/492,700; a comparison, not a measured lowered run",
        ),
        "python_reference_bounded_projection": (
            GOLDBACH_10POW27_LADDER_PYTHON_PROJECTED_CORE_HOURS,
            "7,106/492,700 scaling of the exact Python source-height bounded linearization; retained only as a slow reference",
        ),
    }
    ladder_rows: dict[str, dict[str, Any]] = {}
    for name, (core_hours, basis) in ladder_core_hour_models.items():
        wall_hours = core_hours / Decimal(CPU_NODE_COUNT * CPU_CORES_PER_NODE)
        ladder_rows[name] = {
            "core_hours": str(core_hours),
            "ideal_four_dc96as_v6_wall_hours": str(wall_hours),
            "ideal_four_dc96as_v6_cost_usd": _cost_range(
                wall_hours, wall_hours, cpu_hourly_cost
            ),
            "basis": basis,
        }

    dirichlet_historical_cpu_hours = DIRICHLET_PAPER_REPORTED_CORE_HOURS / Decimal(
        CPU_NODE_COUNT * CPU_CORES_PER_NODE
    )
    dirichlet_large_q_transform_gb10_wall = {
        "low": DIRICHLET_LARGE_Q_BATCH64_BUTTERFLIES
        / DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_HIGH
        / Decimal(3600 * PRODUCTION_NODE_COUNT),
        "high": DIRICHLET_LARGE_Q_BATCH64_BUTTERFLIES
        / DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_LOW
        / Decimal(3600 * PRODUCTION_NODE_COUNT),
    }
    # Keep the old midpoint-proposal arithmetic so the report can state the
    # exact before/after impact of the certified-v2 component.  The old value
    # is a planning baseline only; it is not an admissible interval result.
    dirichlet_small_q_midpoint_proposal_gpu_wall = (
        DIRICHLET_SMALL_Q_GAUSSIAN_TERMS
        / DIRICHLET_SMALL_Q_GB10_GAUSSIAN_TERMS_PER_SECOND
        / Decimal(3600 * PRODUCTION_NODE_COUNT)
    )
    dirichlet_small_q_old_dft_sensitivity_wall = {
        "low": DIRICHLET_SMALL_Q_RADIX2_BUTTERFLIES
        / DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_HIGH
        / Decimal(3600 * PRODUCTION_NODE_COUNT),
        "high": DIRICHLET_SMALL_Q_RADIX2_BUTTERFLIES
        / DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_LOW
        / Decimal(3600 * PRODUCTION_NODE_COUNT),
    }
    dirichlet_small_q_certified_terms_per_second = (
        DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_TERMS
        / DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_TERM_SECONDS
    )
    dirichlet_small_q_certified_butterflies_per_second = (
        DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_BUTTERFLIES
        / DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_DFT_SECONDS
    )
    dirichlet_small_q_certified_gpu_walls = {
        "finite_disk_recurrence": DIRICHLET_SMALL_Q_GAUSSIAN_TERMS
        / dirichlet_small_q_certified_terms_per_second
        / Decimal(3600 * PRODUCTION_NODE_COUNT),
        "persistent_radix2_dft": DIRICHLET_SMALL_Q_RADIX2_BUTTERFLIES
        / dirichlet_small_q_certified_butterflies_per_second
        / Decimal(3600 * PRODUCTION_NODE_COUNT),
    }
    dirichlet_small_q_certified_equal_gb10_wall = sum(
        dirichlet_small_q_certified_gpu_walls.values(), start=Decimal(0)
    )
    dirichlet_small_q_v2_seed_replay_cpu_wall = (
        DIRICHLET_SMALL_Q_FREQUENCY_VALUES
        / DIRICHLET_SMALL_Q_CERTIFIED_ARB_SEEDS_PER_SECOND
        / Decimal(3600 * CPU_NODE_COUNT * CPU_CORES_PER_NODE)
    )
    dirichlet_small_q_v2_seed_payload_bytes = (
        DIRICHLET_SMALL_Q_FREQUENCY_VALUES
        * DIRICHLET_SMALL_Q_CERTIFIED_SEED_BYTES_PER_FREQUENCY
    )
    dirichlet_small_q_factored_family_work = (
        Decimal(3) * DIRICHLET_SMALL_Q_FACTORED_SHARED_RECORDS
        + DIRICHLET_SMALL_Q_PRIMITIVE_CHARACTERS
    )
    dirichlet_small_q_factored_retained_checker_families_per_second = (
        DIRICHLET_SMALL_Q_FACTORED_BENCHMARK_FAMILIES
        / DIRICHLET_SMALL_Q_FACTORED_CHECKER_SECONDS
    )
    dirichlet_small_q_factored_retained_producer_families_per_second = (
        DIRICHLET_SMALL_Q_FACTORED_BENCHMARK_FAMILIES
        / DIRICHLET_SMALL_Q_FACTORED_PRODUCER_SECONDS
    )
    dirichlet_small_q_factored_checker_families_per_second = (
        DIRICHLET_SMALL_Q_FACTORED_SOURCE_BENCHMARK_FAMILIES
        / DIRICHLET_SMALL_Q_FACTORED_SOURCE_CHECKER_SECONDS
    )
    dirichlet_small_q_factored_producer_families_per_second = (
        DIRICHLET_SMALL_Q_FACTORED_SOURCE_BENCHMARK_FAMILIES
        / DIRICHLET_SMALL_Q_FACTORED_SOURCE_PRODUCER_SECONDS
    )
    dirichlet_small_q_factored_replay_cpu_wall = (
        dirichlet_small_q_factored_family_work
        / dirichlet_small_q_factored_checker_families_per_second
        / Decimal(3600 * CPU_NODE_COUNT * CPU_CORES_PER_NODE)
    )
    dirichlet_small_q_factored_payload_reduction = (
        dirichlet_small_q_v2_seed_payload_bytes
        / DIRICHLET_SMALL_Q_FACTORED_MINIMUM_LOGICAL_BYTES
    )
    dirichlet_small_q_factored_cardinality_reduction = (
        DIRICHLET_SMALL_Q_FREQUENCY_VALUES
        / DIRICHLET_SMALL_Q_FACTORED_SHARED_RECORDS
    )
    # The retained v3 CUDA measurement reports the finite recurrence and DFT
    # together.  Their operations are not interchangeable, so this total-work
    # transfer is kept as one source-shaped sensitivity instead of inventing
    # separate per-stage rates.
    dirichlet_small_q_factored_cuda_sample_work = (
        DIRICHLET_SMALL_Q_FACTORED_CUDA_TERMS
        + DIRICHLET_SMALL_Q_FACTORED_CUDA_BUTTERFLIES
    )
    dirichlet_small_q_factored_cuda_source_work = (
        DIRICHLET_SMALL_Q_GAUSSIAN_TERMS
        + DIRICHLET_SMALL_Q_RADIX2_BUTTERFLIES
    )
    dirichlet_small_q_factored_cuda_work_per_second = (
        dirichlet_small_q_factored_cuda_sample_work
        / DIRICHLET_SMALL_Q_FACTORED_CUDA_SECONDS
    )
    dirichlet_small_q_factored_equal_gb10_wall = (
        dirichlet_small_q_factored_cuda_source_work
        / dirichlet_small_q_factored_cuda_work_per_second
        / Decimal(3600 * PRODUCTION_NODE_COUNT)
    )
    dirichlet_lattice_taylor_gb10_wall = (
        DIRICHLET_LATTICE_TAYLOR_RESIDUES
        / DIRICHLET_LATTICE_GB10_RESIDUES_PER_SECOND
        / Decimal(3600 * PRODUCTION_NODE_COUNT)
    )
    dirichlet_residue_composition_cpu_walls = {
        "low": DIRICHLET_RESIDUE_COMPOSITION_VALUES
        / DIRICHLET_RESIDUE_COMPOSITION_BATCHED_VALUES_PER_SECOND_HIGH
        / Decimal(3600 * CPU_NODE_COUNT * CPU_CORES_PER_NODE),
        "high": DIRICHLET_RESIDUE_COMPOSITION_VALUES
        / DIRICHLET_RESIDUE_COMPOSITION_BATCHED_VALUES_PER_SECOND_LOW
        / Decimal(3600 * CPU_NODE_COUNT * CPU_CORES_PER_NODE),
    }
    dirichlet_large_q_fused_equal_gb10_wall = (
        DIRICHLET_LARGE_Q_FUSED_BATCH_VALUES
        / DIRICHLET_LARGE_Q_FUSED_GB10_VALUES_PER_SECOND
        / Decimal(3600 * PRODUCTION_NODE_COUNT)
    )
    dirichlet_large_q_fused_h100_sensitivity = {
        "low": dirichlet_large_q_fused_equal_gb10_wall / Decimal(10),
        "high": dirichlet_large_q_fused_equal_gb10_wall / Decimal(5),
    }
    dirichlet_large_q_seeded_equal_gb10_wall = (
        DIRICHLET_LARGE_Q_FUSED_BATCH_VALUES
        / DIRICHLET_LARGE_Q_SEEDED_GB10_VALUES_PER_SECOND
        / Decimal(3600 * PRODUCTION_NODE_COUNT)
    )
    dirichlet_large_q_seeded_h100_sensitivity = {
        "low": dirichlet_large_q_seeded_equal_gb10_wall / Decimal(10),
        "high": dirichlet_large_q_seeded_equal_gb10_wall / Decimal(5),
    }
    dirichlet_root_input_cpu_core_hours = (
        DIRICHLET_ROOT_INPUT_RECTANGLES
        / DIRICHLET_ROOT_GB10_INPUT_RECTANGLES_PER_SECOND
        / Decimal(3600)
    )
    dirichlet_root_normalization_cpu_core_hours = (
        DIRICHLET_ROOT_PRIMITIVE_RECORDS
        / DIRICHLET_ROOT_GB10_NORMALIZATIONS_PER_SECOND
        / Decimal(3600)
    )
    dirichlet_root_cpu_wall = (
        dirichlet_root_input_cpu_core_hours
        + dirichlet_root_normalization_cpu_core_hours
        + DIRICHLET_ROOT_CURRENT_TWIDDLE_CPU_HOURS
        + DIRICHLET_ROOT_PROCESS_STARTUP_CPU_HOURS
    ) / Decimal(CPU_NODE_COUNT * CPU_CORES_PER_NODE)
    dirichlet_root_equal_gb10_gpu_walls = {
        "low": DIRICHLET_ROOT_RADIX2_BUTTERFLIES
        / DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_HIGH
        / Decimal(3600 * PRODUCTION_NODE_COUNT),
        "high": DIRICHLET_ROOT_RADIX2_BUTTERFLIES
        / DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_LOW
        / Decimal(3600 * PRODUCTION_NODE_COUNT),
    }
    dirichlet_cpu_reference_walls_before = {
        "lattice_seed_generation": DIRICHLET_LATTICE_SEED_CPU_HOURS
        / Decimal(CPU_NODE_COUNT * CPU_CORES_PER_NODE),
        "finite_recovery_every_residue": DIRICHLET_LATTICE_TAYLOR_RESIDUES
        / DIRICHLET_LATTICE_RECOVERY_REFERENCE_ITEMS_PER_SECOND
        / Decimal(3600 * CPU_NODE_COUNT * CPU_CORES_PER_NODE),
        "small_q_every_gaussian_term": DIRICHLET_SMALL_Q_GAUSSIAN_TERMS
        / DIRICHLET_SMALL_Q_ARB_TERMS_PER_SECOND
        / Decimal(3600 * CPU_NODE_COUNT * CPU_CORES_PER_NODE),
        "historical_invalid_factor8_targets_divided_by_sinc_terms_per_second": (
            DIRICHLET_FACTOR8_TARGET_SAMPLES
        )
        / DIRICHLET_POSTPROCESS_INTERVALS_PER_SECOND
        / Decimal(3600 * CPU_NODE_COUNT * CPU_CORES_PER_NODE),
    }
    dirichlet_cpu_reference_walls_after_common = {
        key: value
        for key, value in dirichlet_cpu_reference_walls_before.items()
        if key
        not in {
            "small_q_every_gaussian_term",
            "historical_invalid_factor8_targets_divided_by_sinc_terms_per_second",
        }
    }
    dirichlet_cpu_reference_walls_after_common.update(
        {
            "small_q_v3_independent_factored_family_replay": (
                dirichlet_small_q_factored_replay_cpu_wall
            ),
            "large_q_root_number_inputs_normalization_and_current_plan_prep": (
                dirichlet_root_cpu_wall
            ),
        }
    )
    dirichlet_cpu_reference_serial_wall_before = sum(
        dirichlet_cpu_reference_walls_before.values(), start=Decimal(0)
    )
    dirichlet_cpu_reference_serial_wall_after = {
        name: sum(
            dirichlet_cpu_reference_walls_after_common.values(),
            start=Decimal(0),
        )
        + composition_wall
        for name, composition_wall in dirichlet_residue_composition_cpu_walls.items()
    }
    dirichlet_cpu_reference_walls_after_v2_common = {
        key: value
        for key, value in dirichlet_cpu_reference_walls_after_common.items()
        if key != "small_q_v3_independent_factored_family_replay"
    }
    dirichlet_cpu_reference_walls_after_v2_common[
        "small_q_v2_independent_seed_replay"
    ] = dirichlet_small_q_v2_seed_replay_cpu_wall
    dirichlet_cpu_reference_serial_wall_after_v2 = {
        name: sum(
            dirichlet_cpu_reference_walls_after_v2_common.values(),
            start=Decimal(0),
        )
        + composition_wall
        for name, composition_wall in dirichlet_residue_composition_cpu_walls.items()
    }
    dirichlet_gpu_component_wall_before_low = (
        dirichlet_large_q_transform_gb10_wall["low"] / Decimal(10)
        + DIRICHLET_LARGE_Q_CURRENT_PREPARATION_CPU_HOURS
        / Decimal(PRODUCTION_NODE_COUNT)
        + dirichlet_lattice_taylor_gb10_wall / Decimal(10)
        + dirichlet_small_q_midpoint_proposal_gpu_wall / Decimal(10)
        + dirichlet_small_q_old_dft_sensitivity_wall["low"] / Decimal(10)
    )
    dirichlet_gpu_component_wall_before_high = (
        dirichlet_large_q_transform_gb10_wall["high"] / Decimal(5)
        + DIRICHLET_LARGE_Q_CURRENT_PREPARATION_CPU_HOURS
        / Decimal(PRODUCTION_NODE_COUNT)
        + dirichlet_lattice_taylor_gb10_wall / Decimal(5)
        + dirichlet_small_q_midpoint_proposal_gpu_wall / Decimal(5)
        + dirichlet_small_q_old_dft_sensitivity_wall["high"] / Decimal(5)
    )
    dirichlet_factor8_fused_equal_gb10_wall = (
        DIRICHLET_FACTOR8_TARGET_SAMPLES
        / DIRICHLET_FACTOR8_FUSED_GB10_TARGETS_PER_SECOND
        / Decimal(3600 * PRODUCTION_NODE_COUNT)
    )
    dirichlet_factor8_fused_h100_sensitivity = {
        "low": dirichlet_factor8_fused_equal_gb10_wall / Decimal(10),
        "high": dirichlet_factor8_fused_equal_gb10_wall / Decimal(5),
    }
    dirichlet_gpu_component_wall_after_low = (
        dirichlet_large_q_transform_gb10_wall["low"] / Decimal(10)
        + DIRICHLET_LARGE_Q_CURRENT_PREPARATION_CPU_HOURS
        / Decimal(PRODUCTION_NODE_COUNT)
        + dirichlet_lattice_taylor_gb10_wall / Decimal(10)
        + dirichlet_small_q_factored_equal_gb10_wall / Decimal(10)
        + dirichlet_root_equal_gb10_gpu_walls["low"] / Decimal(10)
        + dirichlet_factor8_fused_h100_sensitivity["low"]
    )
    dirichlet_gpu_component_wall_after_high = (
        dirichlet_large_q_transform_gb10_wall["high"] / Decimal(5)
        + DIRICHLET_LARGE_Q_CURRENT_PREPARATION_CPU_HOURS
        / Decimal(PRODUCTION_NODE_COUNT)
        + dirichlet_lattice_taylor_gb10_wall / Decimal(5)
        + dirichlet_small_q_factored_equal_gb10_wall / Decimal(5)
        + dirichlet_root_equal_gb10_gpu_walls["high"] / Decimal(5)
        + dirichlet_factor8_fused_h100_sensitivity["high"]
    )
    dirichlet_gpu_component_wall_after_v2_low = (
        dirichlet_large_q_transform_gb10_wall["low"] / Decimal(10)
        + DIRICHLET_LARGE_Q_CURRENT_PREPARATION_CPU_HOURS
        / Decimal(PRODUCTION_NODE_COUNT)
        + dirichlet_lattice_taylor_gb10_wall / Decimal(10)
        + dirichlet_small_q_certified_equal_gb10_wall / Decimal(10)
        + dirichlet_root_equal_gb10_gpu_walls["low"] / Decimal(10)
        + dirichlet_factor8_fused_h100_sensitivity["low"]
    )
    dirichlet_gpu_component_wall_after_v2_high = (
        dirichlet_large_q_transform_gb10_wall["high"] / Decimal(5)
        + DIRICHLET_LARGE_Q_CURRENT_PREPARATION_CPU_HOURS
        / Decimal(PRODUCTION_NODE_COUNT)
        + dirichlet_lattice_taylor_gb10_wall / Decimal(5)
        + dirichlet_small_q_certified_equal_gb10_wall / Decimal(5)
        + dirichlet_root_equal_gb10_gpu_walls["high"] / Decimal(5)
        + dirichlet_factor8_fused_h100_sensitivity["high"]
    )

    def _dirichlet_component_cost(
        cpu_low: Decimal,
        cpu_high: Decimal,
        gpu_low: Decimal,
        gpu_high: Decimal,
    ) -> dict[str, dict[str, str]]:
        return {
            name: {
                "low": _money(
                    cpu_low * cpu_hourly_cost[name]
                    + gpu_low * ncc_hourly_cost[name]
                ),
                "high": _money(
                    cpu_high * cpu_hourly_cost[name]
                    + gpu_high * ncc_hourly_cost[name]
                ),
            }
            for name in ("pay_as_you_go", "spot")
        }

    dirichlet_component_cost_before = _dirichlet_component_cost(
        dirichlet_cpu_reference_serial_wall_before,
        dirichlet_cpu_reference_serial_wall_before,
        dirichlet_gpu_component_wall_before_low,
        dirichlet_gpu_component_wall_before_high,
    )
    dirichlet_component_cost_after = _dirichlet_component_cost(
        dirichlet_cpu_reference_serial_wall_after["low"],
        dirichlet_cpu_reference_serial_wall_after["high"],
        dirichlet_gpu_component_wall_after_low,
        dirichlet_gpu_component_wall_after_high,
    )
    dirichlet_component_cost_after_v2 = _dirichlet_component_cost(
        dirichlet_cpu_reference_serial_wall_after_v2["low"],
        dirichlet_cpu_reference_serial_wall_after_v2["high"],
        dirichlet_gpu_component_wall_after_v2_low,
        dirichlet_gpu_component_wall_after_v2_high,
    )
    dirichlet_component_cost_reduction = {
        name: {
            # Cross the endpoints: this is the range of defensible savings,
            # not subtraction of two independently selected point estimates.
            "low": _money(
                Decimal(dirichlet_component_cost_before[name]["low"])
                - Decimal(dirichlet_component_cost_after[name]["high"])
            ),
            "high": _money(
                Decimal(dirichlet_component_cost_before[name]["high"])
                - Decimal(dirichlet_component_cost_after[name]["low"])
            ),
        }
        for name in ("pay_as_you_go", "spot")
    }
    dirichlet_component_cost_reduction_vs_v2 = {
        name: {
            "low": _money(
                Decimal(dirichlet_component_cost_after_v2[name]["low"])
                - Decimal(dirichlet_component_cost_after[name]["high"])
            ),
            "high": _money(
                Decimal(dirichlet_component_cost_after_v2[name]["high"])
                - Decimal(dirichlet_component_cost_after[name]["low"])
            ),
        }
        for name in ("pay_as_you_go", "spot")
    }
    dirichlet_quantified_component_rows = [
        {
            "component_id": "large-q-all-character-framed-transform",
            "source_work": str(DIRICHLET_LARGE_Q_BATCH64_BUTTERFLIES),
            "work_unit": "directed_interval_radix2_butterflies",
            "source_work_is_exact": True,
            "measurement_device": "NVIDIA_GB10",
            "measured_rate_per_second": {
                "low": str(DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_LOW),
                "high": str(DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_HIGH),
            },
            "ideal_cluster": "8_equal_throughput_gpus",
            "ideal_cluster_wall_hours": {
                name: str(value)
                for name, value in dirichlet_large_q_transform_gb10_wall.items()
            },
            "persistent_service_ready": True,
            "h100_measurement_available": False,
        },
        {
            "component_id": "large-q-persistent-residue-composition",
            "source_work": str(DIRICHLET_RESIDUE_COMPOSITION_VALUES),
            "work_unit": "residue_interval_compositions",
            "source_work_is_exact": True,
            "measurement_device": "DGX_Spark_host_process",
            "measured_rate_per_second": {
                "low": str(
                    DIRICHLET_RESIDUE_COMPOSITION_BATCHED_VALUES_PER_SECOND_LOW
                ),
                "high": str(
                    DIRICHLET_RESIDUE_COMPOSITION_BATCHED_VALUES_PER_SECOND_HIGH
                ),
            },
            "ideal_cluster": "384_independent_cpu_processes",
            "ideal_cluster_wall_hours": {
                name: str(value)
                for name, value in dirichlet_residue_composition_cpu_walls.items()
            },
            "persistent_service_ready": True,
            "source_scale_performance_validated": False,
        },
        {
            "component_id": "large-q-fused-certified-box-batch-alternative",
            "source_work": str(DIRICHLET_LARGE_Q_FUSED_BATCH_VALUES),
            "work_unit": "fused_taylor_and_residue_composition_values",
            "source_work_is_exact": True,
            "batch_invocations": str(DIRICHLET_LARGE_Q_FUSED_BATCH_INVOCATIONS),
            "maximum_ordinates_per_batch": 64,
            "measurement_device": "NVIDIA_GB10",
            "measured_rate_per_second": str(
                DIRICHLET_LARGE_Q_FUSED_GB10_VALUES_PER_SECOND
            ),
            "ideal_cluster": "8_equal_throughput_gpus",
            "ideal_cluster_wall_hours": str(
                dirichlet_large_q_fused_equal_gb10_wall
            ),
            "five_to_ten_x_h100_sensitivity_wall_hours": {
                name: str(value)
                for name, value in dirichlet_large_q_fused_h100_sensitivity.items()
            },
            "literal_certified_input_bytes": str(
                DIRICHLET_LARGE_Q_FUSED_TOTAL_INPUT_BYTES
            ),
            "included_in_component_revision_totals": False,
            "alternative_to": [
                "large-q-lattice-taylor",
                "large-q-persistent-residue-composition",
            ],
            "source_performance_ready": False,
            "h100_measurement_available": False,
        },
        {
            "component_id": "large-q-root-additive-input",
            "source_work": str(DIRICHLET_ROOT_INPUT_RECTANGLES),
            "work_unit": "certified_additive_input_rectangles",
            "source_work_is_exact": True,
            "measurement_device": "DGX_Spark_host_process",
            "measured_rate_per_second": str(
                DIRICHLET_ROOT_GB10_INPUT_RECTANGLES_PER_SECOND
            ),
            "ideal_cluster": "384_independent_cpu_processes",
            "ideal_cluster_wall_hours": str(
                dirichlet_root_input_cpu_core_hours
                / Decimal(CPU_NODE_COUNT * CPU_CORES_PER_NODE)
            ),
            "source_scale_performance_validated": False,
        },
        {
            "component_id": "large-q-root-primitive-normalization",
            "source_work": str(DIRICHLET_ROOT_PRIMITIVE_RECORDS),
            "work_unit": "primitive_root_phase_records",
            "source_work_is_exact": True,
            "measurement_device": "DGX_Spark_host_process",
            "measured_rate_per_second": str(
                DIRICHLET_ROOT_GB10_NORMALIZATIONS_PER_SECOND
            ),
            "ideal_cluster": "384_independent_cpu_processes",
            "ideal_cluster_wall_hours": str(
                dirichlet_root_normalization_cpu_core_hours
                / Decimal(CPU_NODE_COUNT * CPU_CORES_PER_NODE)
            ),
            "source_scale_performance_validated": False,
        },
        {
            "component_id": "large-q-root-all-character-transform",
            "source_work": str(DIRICHLET_ROOT_RADIX2_BUTTERFLIES),
            "work_unit": "directed_interval_radix2_butterflies",
            "source_work_is_exact": True,
            "measurement_device": "NVIDIA_GB10_rate_transferred_from_TGDAFF",
            "measured_rate_per_second": {
                "low": str(DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_LOW),
                "high": str(DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_HIGH),
            },
            "ideal_cluster": "8_equal_throughput_gpus",
            "ideal_cluster_wall_hours": {
                name: str(value)
                for name, value in dirichlet_root_equal_gb10_gpu_walls.items()
            },
            "h100_measurement_available": False,
        },
        {
            "component_id": "small-q-v3-factored-cuda-finite-plus-dft",
            "source_work": str(dirichlet_small_q_factored_cuda_source_work),
            "work_unit": "mixed_finite_terms_plus_radix2_butterflies",
            "source_work_is_exact": False,
            "source_work_status": "finite-term count is a planning estimate; butterfly count is exact",
            "source_finite_gaussian_terms": str(
                DIRICHLET_SMALL_Q_GAUSSIAN_TERMS
            ),
            "source_radix2_butterflies": str(
                DIRICHLET_SMALL_Q_RADIX2_BUTTERFLIES
            ),
            "measurement_device": "NVIDIA_GB10",
            "measurement_finite_gaussian_terms": str(
                DIRICHLET_SMALL_Q_FACTORED_CUDA_TERMS
            ),
            "measurement_radix2_butterflies": str(
                DIRICHLET_SMALL_Q_FACTORED_CUDA_BUTTERFLIES
            ),
            "measurement_seconds": str(DIRICHLET_SMALL_Q_FACTORED_CUDA_SECONDS),
            "measured_combined_work_items_per_second": str(
                dirichlet_small_q_factored_cuda_work_per_second
            ),
            "ideal_cluster": "8_equal_throughput_gpus",
            "ideal_cluster_wall_hours": str(
                dirichlet_small_q_factored_equal_gb10_wall
            ),
            "factored_cuda_consumer_implemented": True,
            "q_persistent_source_service_implemented": True,
            "source_service_physical_input_bytes": str(
                DIRICHLET_SMALL_Q_FACTORED_SERVICE_PHYSICAL_BYTES
            ),
            "literal_diagnostic_output_bytes": str(
                DIRICHLET_SMALL_Q_FACTORED_LITERAL_OUTPUT_BYTES
            ),
            "source_sample_only_stream_bytes": str(
                DIRICHLET_SMALL_Q_FACTORED_REDUCED_OUTPUT_BYTES
            ),
            "compact_downstream_reducer_implemented": True,
            "compact_reducer_scope": "coverage_and_integrity_only",
            "semantic_time_tail_sign_reducer_implemented": True,
            "semantic_time_tail_control_records": str(
                DIRICHLET_SMALL_Q_SEMANTIC_CONTROL_RECORDS
            ),
            "semantic_time_tail_control_bytes": str(
                DIRICHLET_SMALL_Q_SEMANTIC_CONTROL_BYTES
            ),
            "semantic_two_bit_sign_artifact_bytes": str(
                DIRICHLET_SMALL_Q_SEMANTIC_SIGN_ARTIFACT_BYTES
            ),
            "semantic_reducer_cuda_fused": False,
            "semantic_reducer_source_performance_measured": False,
            "semantic_reducer_multiplicity_inference_performed": False,
            "local_cached_stream_megabytes_per_second": str(
                DIRICHLET_SMALL_Q_OUTPUT_REDUCER_CACHED_MB_PER_SECOND
            ),
            "local_pipe_stream_megabytes_per_second": str(
                DIRICHLET_SMALL_Q_OUTPUT_REDUCER_PIPE_MB_PER_SECOND
            ),
            "source_wide_width_closure_proved": False,
            "h100_measurement_available": False,
        },
        {
            "component_id": "small-q-v3-independent-factored-family-replay",
            "source_work": str(dirichlet_small_q_factored_family_work),
            "work_unit": "three_shared_families_per_frequency_plus_character_families",
            "source_work_is_exact": True,
            "measurement_device": "DGX_Spark_host_process",
            "measurement_work": str(
                DIRICHLET_SMALL_Q_FACTORED_SOURCE_BENCHMARK_FAMILIES
            ),
            "measurement_seconds": str(
                DIRICHLET_SMALL_Q_FACTORED_SOURCE_CHECKER_SECONDS
            ),
            "measured_rate_per_second": str(
                dirichlet_small_q_factored_checker_families_per_second
            ),
            "ideal_cluster": "384_independent_cpu_processes",
            "ideal_cluster_wall_hours": str(
                dirichlet_small_q_factored_replay_cpu_wall
            ),
            "producer_generation_included": False,
            "q_persistent_source_service_implemented": True,
            "source_wide_width_closure_proved": False,
            "source_scale_performance_validated": False,
            "source_parameter_single_q_benchmark_available": True,
        },
    ]
    conditional_rows = []
    procurement_rows = []
    conditional_component_rows = []
    for goldbach_row in goldbach_rows:
        goldbach_hours = Decimal(str(goldbach_row["cluster_wall_hours"]))
        goldbach_factor = str(
            goldbach_row["equal_throughput_factor_vs_measured_gpu"]
        )
        ideal_wall_hours = max(
            goldbach_hours,
            zeta_cpu_cluster_hours,
            overlapped_high,
            GOLDBACH_10POW27_LADDER_PAPER_SCALED_CORE_HOURS
            / Decimal(CPU_NODE_COUNT * CPU_CORES_PER_NODE),
        )
        conditional_rows.append(
            {
                "goldbach_equal_throughput_factor_vs_gb10": goldbach_row[
                    "equal_throughput_factor_vs_measured_gpu"
                ],
                "goldbach_eight_ncc_wall_hours": str(goldbach_hours),
                "literal_flint_zeta_four_dc96as_v6_wall_hours": str(
                    zeta_cpu_cluster_hours
                ),
                "ideal_concurrent_wall_hours_before_dirichlet": str(
                    ideal_wall_hours
                ),
                "ideal_concurrent_wall_years_before_dirichlet": str(
                    ideal_wall_hours / HOURS_PER_YEAR
                ),
                "dominant_binary_plus_zeta_compute_cost_usd": {
                    name: _money(
                        goldbach_hours * ncc_hourly_cost[name]
                        + zeta_cpu_cluster_hours * cpu_hourly_cost[name]
                    )
                    for name in ("pay_as_you_go", "spot")
                },
            }
        )
        component_concurrent_wall = max(
            goldbach_hours,
            zeta_cpu_cluster_hours,
            dirichlet_cpu_reference_serial_wall_after["high"],
            overlapped_high,
        )
        component_shared_cpu_wall = max(
            goldbach_hours,
            zeta_cpu_cluster_hours
            + dirichlet_cpu_reference_serial_wall_after["high"],
            overlapped_high,
        )
        conditional_component_rows.append(
            {
                "goldbach_equal_throughput_factor_vs_gb10": goldbach_factor,
                "independent_cpu_pools_concurrent_wall_hours": str(
                    component_concurrent_wall
                ),
                "independent_cpu_pools_concurrent_wall_years": str(
                    component_concurrent_wall / HOURS_PER_YEAR
                ),
                "one_shared_four_node_cpu_pool_wall_hours": str(
                    component_shared_cpu_wall
                ),
                "one_shared_four_node_cpu_pool_wall_years": str(
                    component_shared_cpu_wall / HOURS_PER_YEAR
                ),
                "dominant_compute_cost_usd": {
                    name: {
                        "low": _money(
                            goldbach_hours * ncc_hourly_cost[name]
                            + zeta_cpu_cluster_hours * cpu_hourly_cost[name]
                            + dirichlet_cpu_reference_serial_wall_after["low"]
                            * cpu_hourly_cost[name]
                            + dirichlet_gpu_component_wall_after_low
                            * ncc_hourly_cost[name]
                        ),
                        "high": _money(
                            goldbach_hours * ncc_hourly_cost[name]
                            + zeta_cpu_cluster_hours * cpu_hourly_cost[name]
                            + dirichlet_cpu_reference_serial_wall_after["high"]
                            * cpu_hourly_cost[name]
                            + dirichlet_gpu_component_wall_after_high
                            * ncc_hourly_cost[name]
                        ),
                    }
                    for name in ("pay_as_you_go", "spot")
                },
            }
        )
        # Two to five times the retained GB10 throughput is the deliberately
        # conservative procurement band until a real confidential-H100 pilot
        # replaces it.  Scale DC96 nodes so the literal zeta replay does not
        # become slower than that Goldbach row.  This remains a conditional
        # known-work forecast: the incomplete Dirichlet production pipeline is
        # not assigned zero time in any full-portfolio claim.
        if goldbach_factor in {"2", "5"}:
            cpu_nodes = int(
                (
                    zeta_process_hours
                    / (Decimal(CPU_CORES_PER_NODE) * goldbach_hours)
                ).to_integral_value(rounding=ROUND_CEILING)
            )
            balanced_zeta_hours = zeta_process_hours / Decimal(
                cpu_nodes * CPU_CORES_PER_NODE
            )
            known_wall_hours = max(
                goldbach_hours,
                balanced_zeta_hours,
                overlapped_high,
                GOLDBACH_10POW27_LADDER_NATIVE_PROJECTED_CORE_HOURS
                / Decimal(cpu_nodes * CPU_CORES_PER_NODE),
            )
            procurement_rows.append(
                {
                    "goldbach_equal_throughput_factor_vs_gb10": goldbach_factor,
                    "eight_ncc_wall_hours": str(goldbach_hours),
                    "balanced_dc96as_v6_nodes": cpu_nodes,
                    "literal_zeta_wall_hours": str(balanced_zeta_hours),
                    "conditional_known_work_wall_hours": str(known_wall_hours),
                    "conditional_known_work_wall_years": str(
                        known_wall_hours / HOURS_PER_YEAR
                    ),
                    "dominant_binary_plus_zeta_compute_cost_usd": {
                        name: _money(
                            goldbach_hours * ncc_hourly_cost[name]
                            + balanced_zeta_hours
                            * Decimal(cpu_nodes)
                            * cpu_rates[name]
                        )
                        for name in ("pay_as_you_go", "spot")
                    },
                }
            )

    hurst_affine_core_hours = {
        "low": HURST_AFFINE_SOURCE_ROWS
        / HURST_AFFINE_SAMPLE_ROWS
        * HURST_AFFINE_LOW_RANGE_SECONDS
        / Decimal(3600)
        * HURST_AFFINE_SAMPLE_THREADS,
        "high": HURST_AFFINE_SOURCE_ROWS
        / HURST_AFFINE_SAMPLE_ROWS
        * HURST_AFFINE_TERMINAL_SECONDS
        / Decimal(3600)
        * HURST_AFFINE_SAMPLE_THREADS,
    }
    hurst_affine_four_dc96_wall = {
        name: value / Decimal(CPU_NODE_COUNT * CPU_CORES_PER_NODE)
        for name, value in hurst_affine_core_hours.items()
    }
    goldbach_by_factor = {
        str(row["equal_throughput_factor_vs_measured_gpu"]): row
        for row in goldbach_rows
    }
    hurst_h100_affine_projection = project_hurst_h100_affine()
    hurst_h100_affine_wall_hours = Decimal(
        str(
            hurst_h100_affine_projection["h100_sensitivity"][
                "eight_worker_wall_hours"
            ]
        )
    )
    optimizer_routes, optimizer_evidence = _backend_optimizer_catalog(
        goldbach_binary_h100_node_hours_low=(
            Decimal(str(goldbach_by_factor["5"]["cluster_wall_hours"]))
            * Decimal(PRODUCTION_NODE_COUNT)
        ),
        goldbach_binary_h100_node_hours_high=(
            Decimal(str(goldbach_by_factor["2"]["cluster_wall_hours"]))
            * Decimal(PRODUCTION_NODE_COUNT)
        ),
        dirichlet_cpu_dc96_node_hours_low=(
            dirichlet_cpu_reference_serial_wall_after["low"]
            * Decimal(CPU_NODE_COUNT)
        ),
        dirichlet_cpu_dc96_node_hours_high=(
            dirichlet_cpu_reference_serial_wall_after["high"]
            * Decimal(CPU_NODE_COUNT)
        ),
        dirichlet_gpu_h100_node_hours_low=(
            dirichlet_gpu_component_wall_after_low
            * Decimal(PRODUCTION_NODE_COUNT)
        ),
        dirichlet_gpu_h100_node_hours_high=(
            dirichlet_gpu_component_wall_after_high
            * Decimal(PRODUCTION_NODE_COUNT)
        ),
        hurst_h100_affine_projection=hurst_h100_affine_projection,
        target_sku_calibrations=checked_target_calibrations,
    )
    backend_optimizer = optimize_backend_catalog(
        physical_campaign_ids=PHYSICAL_CAMPAIGN_IDS,
        routes=optimizer_routes,
        h100_prices=rates,
        cpu_prices=cpu_rates,
        deadline_hours=deadline_hours,
        max_cpu_nodes=max_cpu_nodes,
        max_h100_nodes=max_h100_nodes,
        production_max_wall_hours=production_max_wall_hours,
        production_max_cost_usd=production_max_cost_usd,
    )
    backend_optimizer["calibration_evidence"] = optimizer_evidence
    backend_optimizer["target_sku_calibration_manifests"] = [
        target_sku_calibration_summary(manifest)
        for manifest in checked_target_calibrations
    ]
    backend_optimizer["target_sku_calibration_manifest_count"] = len(
        checked_target_calibrations
    )
    backend_optimizer["price_snapshot"] = {
        "date": PRICE_SNAPSHOT_DATE.isoformat(),
        "region": AZURE_REGION,
        "dc96as_v6_usd_per_node_hour": {
            name: str(rate) for name, rate in cpu_rates.items()
        },
        "ncc40ads_h100_v5_usd_per_node_hour": {
            name: str(rate) for name, rate in rates.items()
        },
    }
    lowered_goldbach_target_sku_measured = any(
        demand.get("target_sku_measured") is True
        for route in backend_optimizer["route_matrix"]
        if route["campaign_id"]
        == "ternary-goldbach-finite-below-10pow27-v1"
        for demand in route["demands"]
    )
    dominant_campaign_budget_review = _dominant_campaign_budget_review(
        backend_optimizer
    )
    return {
        "schema": "sparkinterval.tg.azure-production-sizing.v2",
        "classification": "planning_projection_not_execution_or_mathematical_evidence",
        "source_scope": "all_13_named_ternary_goldbach_external_atoms",
        "dominant_campaign_budget_review": dominant_campaign_budget_review,
        "azure": {
            "region": AZURE_REGION,
            "sku": NCC_SKU,
            "gpu_per_node": NCC_GPU_COUNT,
            "production_nodes": PRODUCTION_NODE_COUNT,
            "price_source": AZURE_RETAIL_PRICES_API,
            "price_snapshot_date": PRICE_SNAPSHOT_DATE.isoformat(),
            "usd_per_node_hour": {name: str(rate) for name, rate in rates.items()},
            "cpu_sidecar_cluster": {
                "sku": CPU_SKU,
                "nodes": CPU_NODE_COUNT,
                "cores_per_node": CPU_CORES_PER_NODE,
                "total_cores": CPU_NODE_COUNT * CPU_CORES_PER_NODE,
                "usd_per_node_hour": {
                    name: str(rate) for name, rate in cpu_rates.items()
                },
            },
        },
        "campaigns": [row.as_json() for row in ranges],
        "backend_optimizer": backend_optimizer,
        "complete_portfolio_prediction_available": not blockers,
        "optimized_engine_blockers": blockers,
        "planning_envelopes": {
            "practical_10_logical_atoms": {
                "logical_atoms": [
                    atom_id
                    for atom_id in ATOM_IDS
                    if atom_id
                    not in {
                        "platt-trudgian-rh-3e12",
                        "platt-dirichlet-theorem-7-1",
                        "helfgott-platt-theorem-4-1",
                    }
                ],
                "physical_campaign_representatives": list(
                    practical_physical_atom_ids
                ),
                "shared_campaign_aliases": {
                    "mertens-hurst": [
                        "cdem-squarefree",
                        "platt-little-mertens-2-11",
                        "platt-little-mertens-stronger",
                    ]
                },
                "optimistic_cpu_gpu_overlap_wall_hours": {
                    "low": str(overlapped_low),
                    "high": str(overlapped_high),
                },
                "serialized_on_one_eight_node_pool_wall_hours": {
                    "low": str(serialized_low),
                    "high": str(serialized_high),
                },
                "optimistic_cpu_gpu_overlap_cost_usd": _cost_range(
                    overlapped_low, overlapped_high, ncc_hourly_cost
                ),
                "serialized_cost_usd": _cost_range(
                    serialized_low, serialized_high, ncc_hourly_cost
                ),
                "mixed_four_cpu_nodes_plus_one_h100_cost_usd":
                    _mixed_cost_range(overlapped_low, overlapped_high),
                "classification": "projection_before_azure_h100_calibration",
            },
            "hurst_affine_guard_alternative": {
                "source_rows": str(HURST_AFFINE_SOURCE_ROWS),
                "retained_benchmarks": {
                    "rows": str(HURST_AFFINE_SAMPLE_ROWS),
                    "threads": str(HURST_AFFINE_SAMPLE_THREADS),
                    "low_range_seconds": str(HURST_AFFINE_LOW_RANGE_SECONDS),
                    "terminal_near_1e16_seconds": str(
                        HURST_AFFINE_TERMINAL_SECONDS
                    ),
                    "old_low_range_seconds": "32.28",
                    "old_terminal_seconds": "23.35",
                    "byte_semantic_receipts_equal_after_elapsed_time_removed": True,
                },
                "source_shaped_core_hours": {
                    name: str(value)
                    for name, value in hurst_affine_core_hours.items()
                },
                "ideal_four_dc96as_v6_wall_hours": {
                    name: str(value)
                    for name, value in hurst_affine_four_dc96_wall.items()
                },
                "production_two_pass_route_replaced": False,
                "one_pass_campaign_schema_and_replay_implemented": True,
                "included_in_practical_or_portfolio_totals": False,
                "classification": "calibrated_source_shaped_affine_sensitivity_not_production_campaign_eta",
            },
            "hurst_h100_affine_eight_worker_sensitivity": {
                **hurst_h100_affine_projection,
                "eight_ncc_compute_cost_usd": _cost_range(
                    hurst_h100_affine_wall_hours,
                    hurst_h100_affine_wall_hours,
                    ncc_hourly_cost,
                ),
                "optimizer_route_id": (
                    "hurst-four-residuals-v1:"
                    "h100-eight-worker-affine-gb10-sensitivity"
                ),
                "arithmetic_time_below_168_hours": (
                    hurst_h100_affine_wall_hours
                    <= production_max_wall_hours
                ),
                "production_ready": False,
                "projection_scope": "terminal_h100_stage_only",
                "complete_hybrid_campaign_eta_available": False,
                "budget_interpretation": (
                    "Arithmetic-only time and cost are planning sensitivities. "
                    "They cover only the terminal H100 stage and exclude the "
                    "CPU summary/verification prefix and handoff, startup, "
                    "receipts, replay, checkpointing, retries, and attestation. "
                    "They cannot pass the release gate without retained "
                    "target-H100 calibration."
                ),
            },
            "literal_zeta_rh_campaign_alone": {
                "literal_flint_process_hours": str(zeta_process_hours),
                "four_dc96as_v6_wall_hours": str(zeta_cpu_cluster_hours),
                "four_dc96as_v6_wall_years": str(
                    zeta_cpu_cluster_hours / HOURS_PER_YEAR
                ),
                "four_dc96as_v6_cost_usd": _cost_range(
                    zeta_cpu_cluster_hours,
                    zeta_cpu_cluster_hours,
                    cpu_hourly_cost,
                ),
                "eight_ncc_host_cpu_wall_hours": str(zeta_ncc_host_hours),
                "eight_ncc_host_cpu_cost_usd": _cost_range(
                    zeta_ncc_host_hours, zeta_ncc_host_hours, ncc_hourly_cost
                ),
                "classification": "impractical_projection_from_source_height_flint_benchmark",
                "historical_optimized_reference": {
                    "source": "Platt--Trudgian 2021 reported 7.5 million core-hours",
                    "core_hours": str(ZETA_PAPER_REPORTED_CORE_HOURS),
                    "ideal_wall_hours_on_320_cores": "23437.5",
                    "ideal_wall_hours_on_384_cores": str(
                        zeta_historical_cpu_hours
                    ),
                    "ideal_four_dc96as_v6_cost_usd": _cost_range(
                        zeta_historical_cpu_hours,
                        zeta_historical_cpu_hours,
                        cpu_hourly_cost,
                    ),
                    "classification": "historical_comparison_not_current_engine_eta",
                },
            },
            "goldbach_binary_h100_sensitivity": {
                "benchmark": {
                    "measured_gpu": "NVIDIA GB10",
                    "production_profile": "analytic_10pow27",
                    "source_even_count": str(ANALYTIC_10POW27_EVEN_COUNT),
                    "sample_even_count": str(GOLDBACH_SAMPLE_EVEN_COUNT),
                    "sample_seconds_median": str(GOLDBACH_SAMPLE_SECONDS),
                    "sample_throughput_evens_per_second": goldbach_projection[
                        "measured_even_per_second"
                    ],
                    "classification": "terminal_source_height_local_measurement",
                },
                "production_checkpoint_leaf_count": ANALYTIC_10POW27_SHARDS,
                "rows": goldbach_rows,
                "roofline_endpoint_basis": "14.3 is 3.9 TB/s H100-NVL bandwidth divided by 273 GB/s DGX-Spark bandwidth; atomic and integer work can prevent attaining it",
                "classification": "active_10pow27_handoff_sensitivity_only_not_an_h100_prediction",
                "calibration_gate": {
                    "passed": lowered_goldbach_target_sku_measured,
                    "required": "measured source-height throughput from the exact production executable on the selected Azure H100 confidential SKU",
                    "effect": "no budget or one-week claim may be promoted until this gate passes",
                },
            },
            "goldbach_historical_source_comparison": {
                "production_profile": "helfgott_platt_8_875e30_historical_reconstruction",
                "source_even_count": str(PRODUCTION_EVEN_COUNT),
                "production_checkpoint_leaf_count": PRODUCTION_SHARDS,
                "rows": historical_goldbach_rows,
                "classification": "preserved_historical_comparison_not_active_handoff",
            },
            "goldbach_prime_ladder_cpu_boundary": {
                "production_profile": "analytic_10pow27",
                "range_count": GOLDBACH_10POW27_LADDER_RANGE_COUNT,
                "minimum_records_per_range": GOLDBACH_LADDER_MINIMUM_RECORDS_PER_RANGE,
                "minimum_total_records": str(
                    GOLDBACH_10POW27_LADDER_RANGE_COUNT
                    * GOLDBACH_LADDER_MINIMUM_RECORDS_PER_RANGE
                ),
                "models": ladder_rows,
                "classification": "separate_cpu_campaign_with_no_completed_repository_source_run",
                "nonclaims": [
                    "All lowered ladder rows are range-count-scaled projections, not a full-range measurement.",
                    "General-prime fallback, durable multi-terabyte I/O, scheduling, retry, and attestation overhead are excluded.",
                    "The binary Goldbach campaign and prime ladder must both finish and replay before their shared atom can be realized.",
                ],
            },
            "dirichlet_grh_boundary": {
                "optimized_all_character_engine_available": True,
                "optimized_component_process_graph_available": True,
                "optimized_end_to_end_pipeline_available": False,
                "direct_flint_fallback": {
                    "status": "full-domain executable but not source-scale benchmarked",
                    "role": "rigorous argument-principle fallback independent of the cited Turing display",
                },
                "quantified_component_rows": dirichlet_quantified_component_rows,
                "large_q_all_character_transform": {
                    "batch64_butterflies": str(
                        DIRICHLET_LARGE_Q_BATCH64_BUTTERFLIES
                    ),
                    "batch64_invocations": str(
                        DIRICHLET_RESIDUE_COMPOSITION_BATCH64_INVOCATIONS
                    ),
                    "measured_gb10_butterflies_per_second": {
                        "low": str(
                            DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_LOW
                        ),
                        "high": str(
                            DIRICHLET_LARGE_Q_GB10_BUTTERFLIES_PER_SECOND_HIGH
                        ),
                    },
                    "ideal_eight_equal_gb10_wall_hours": {
                        name: str(value)
                        for name, value in dirichlet_large_q_transform_gb10_wall.items()
                    },
                    "current_host_preparation_ideal_eight_node_wall_hours": str(
                        DIRICHLET_LARGE_Q_CURRENT_PREPARATION_CPU_HOURS
                        / Decimal(PRODUCTION_NODE_COUNT)
                    ),
                    "five_to_ten_x_h100_sensitivity_including_preparation_wall_hours": {
                        "low": str(
                            dirichlet_large_q_transform_gb10_wall["low"]
                            / Decimal(10)
                            + DIRICHLET_LARGE_Q_CURRENT_PREPARATION_CPU_HOURS
                            / Decimal(PRODUCTION_NODE_COUNT)
                        ),
                        "high": str(
                            dirichlet_large_q_transform_gb10_wall["high"]
                            / Decimal(5)
                            + DIRICHLET_LARGE_Q_CURRENT_PREPARATION_CPU_HOURS
                            / Decimal(PRODUCTION_NODE_COUNT)
                        ),
                    },
                    "persistent_framed_service": {
                        "implemented": True,
                        "one_q_plan_retained": True,
                        "legacy_rolling_child_process_launches_avoided": str(
                            Decimal(2)
                            * DIRICHLET_RESIDUE_COMPOSITION_BATCH64_INVOCATIONS
                        ),
                        "arithmetic_projection_changed": False,
                        "component_process_graph_wired": True,
                        "full_source_supervisor_wired": False,
                    },
                    "classification": "implemented_component_projection_not_h100_measurement_or_full_pipeline_eta",
                },
                "large_q_lattice_taylor": {
                    "residue_reconstructions": str(
                        DIRICHLET_LATTICE_TAYLOR_RESIDUES
                    ),
                    "measured_gb10_residues_per_second": str(
                        DIRICHLET_LATTICE_GB10_RESIDUES_PER_SECOND
                    ),
                    "ideal_eight_equal_gb10_wall_hours": str(
                        dirichlet_lattice_taylor_gb10_wall
                    ),
                    "classification": "implemented_conditional_component_projection",
                },
                "large_q_fused_certified_box_batch_alternative": {
                    "arithmetic_roster_version": (
                        "primitive-dirichlet-moduli-q-mod-4-ne-2-v2"
                    ),
                    "maximum_ordinates_per_batch": 64,
                    "old_one_ordinate_jobs": str(
                        DIRICHLET_LARGE_Q_FUSED_OLD_ONE_T_INVOCATIONS
                    ),
                    "fused_batch_invocations": str(
                        DIRICHLET_LARGE_Q_FUSED_BATCH_INVOCATIONS
                    ),
                    "fused_taylor_and_composition_values": str(
                        DIRICHLET_LARGE_Q_FUSED_BATCH_VALUES
                    ),
                    "retained_gb10_benchmark": {
                        "q": 10001,
                        "batch_count": 64,
                        "measured_values_per_second": str(
                            DIRICHLET_LARGE_Q_FUSED_GB10_VALUES_PER_SECOND
                        ),
                        "classification": "source_shaped_synthetic_box_kernel_measurement_not_h100_or_source_execution",
                    },
                    "ideal_eight_equal_gb10_wall_hours": str(
                        dirichlet_large_q_fused_equal_gb10_wall
                    ),
                    "five_to_ten_x_h100_sensitivity_wall_hours": {
                        name: str(value)
                        for name, value in dirichlet_large_q_fused_h100_sensitivity.items()
                    },
                    "literal_certified_input_boundary": {
                        "repeated_hurwitz_lattice_bytes": str(
                            DIRICHLET_LARGE_Q_FUSED_LATTICE_INPUT_BYTES
                        ),
                        "tail_plus_finite_recovery_box_bytes": str(
                            DIRICHLET_LARGE_Q_FUSED_TAIL_RECOVERY_INPUT_BYTES
                        ),
                        "total_bytes_including_descriptors_factors_and_headers": str(
                            DIRICHLET_LARGE_Q_FUSED_TOTAL_INPUT_BYTES
                        ),
                    },
                    "literal_certified_input_boundary_roster_version": (
                        "legacy-v1-all-modulus-model-not-v2-production-input"
                    ),
                    "alternative_to_separate_lattice_taylor_and_residue_composition": True,
                    "included_in_component_revision_totals": False,
                    "certified_box_producer_integrated": False,
                    "source_scale_io_plan_implemented": False,
                    "source_performance_ready": False,
                    "h100_measurement_available": False,
                    "warning": "the 13.5--27.1 hour H100 sensitivity is fused CUDA arithmetic only; generation, independent replay, and transport of the legacy-V1 18.264-PB certified input boundary are excluded",
                    "classification": "implemented_alternative_fused_component_not_source_eta_or_h100_measurement",
                },
                "large_q_seeded_fused_batch_current": {
                    "arithmetic_roster_version": (
                        "primitive-dirichlet-moduli-q-mod-4-ne-2-v2"
                    ),
                    "maximum_ordinates_per_batch": 64,
                    "fused_batch_invocations": str(
                        DIRICHLET_LARGE_Q_FUSED_BATCH_INVOCATIONS
                    ),
                    "fused_taylor_composition_and_recovery_values": str(
                        DIRICHLET_LARGE_Q_FUSED_BATCH_VALUES
                    ),
                    "retained_gb10_benchmark": {
                        "q": 10001,
                        "batch_count": 64,
                        "measured_values_per_second": str(
                            DIRICHLET_LARGE_Q_SEEDED_GB10_VALUES_PER_SECOND
                        ),
                        "includes_directed_finite_recovery_recurrence": True,
                        "classification": "source_shaped_compact_seeded_kernel_measurement_not_h100_or_source_execution",
                    },
                    "ideal_eight_equal_gb10_wall_hours": str(
                        dirichlet_large_q_seeded_equal_gb10_wall
                    ),
                    "five_to_ten_x_h100_sensitivity_wall_hours": {
                        name: str(value)
                        for name, value in dirichlet_large_q_seeded_h100_sensitivity.items()
                    },
                    "logical_input_boundary_bytes": str(
                        DIRICHLET_LARGE_Q_SEEDED_TOTAL_INPUT_BYTES
                    ),
                    "logical_input_boundary_roster_version": (
                        "legacy-v1-all-modulus-model-superseded-by-direct-v2"
                    ),
                    "finite_recovery_seed_artifact_bytes": str(
                        DIRICHLET_RECOVERY_SEED_ARTIFACT_BYTES
                    ),
                    "full_seed_generation_and_320_bit_replay_completed_locally": True,
                    "t_major_hurwitz_lattice_cache_contract_implemented": True,
                    "t_major_hurwitz_lattice_replay_repacker_implemented": True,
                    "t_major_hurwitz_lattice_payload_bytes": str(
                        DIRICHLET_T_MAJOR_LATTICE_PAYLOAD_BYTES
                    ),
                    "t_major_hurwitz_lattice_artifact_bytes": str(
                        DIRICHLET_T_MAJOR_LATTICE_ARTIFACT_BYTES
                    ),
                    "t_major_compact_total_input_bytes": str(
                        DIRICHLET_T_MAJOR_COMPACT_TOTAL_INPUT_BYTES
                    ),
                    "former_t_major_descriptor_repeated_input_bytes": str(
                        DIRICHLET_T_MAJOR_COMPACT_TOTAL_INPUT_BYTES
                    ),
                    "direct_t_major_cuda_input_bytes": "286556459000",
                    "direct_t_major_input_including_recovery_seeds": "286652467016",
                    "direct_t_major_roster_version": (
                        "primitive-dirichlet-moduli-q-mod-4-ne-2-v2"
                    ),
                    "source_wide_supervisor_plan_implemented": True,
                    "source_wide_fixed_q_fft_batch_count": "56981100",
                    "source_root_catalog_contract_implemented": True,
                    "source_root_catalog_generated_and_audited": False,
                    "t_major_hurwitz_lattice_cache_broadcast_implemented": True,
                    "t_major_cuda_output_integrated_into_multi_q_fft_lane": False,
                    "typed_fft_receipt_bundle_implemented": True,
                    "t_major_typed_bundle_admission_adapter_implemented": True,
                    "typed_bundle_lattice_payload_to_cache_row_binding_implemented": True,
                    "typed_fft_receipt_bundle_integrated_into_t_major_lane": False,
                    "t_major_zero_state_adapter_implemented": False,
                    "source_wide_interval_usefulness_proved": False,
                    "included_in_component_revision_totals": False,
                    "source_performance_ready": False,
                    "h100_measurement_available": False,
                    "warning": "the 47.7--95.4 hour H100 sensitivity is seeded fused CUDA arithmetic only; the primitive-only V2 direct row-resident t-major component reduces exact binary input to 286.556 GB plus 96.008 MB of recovery seeds and has only bounded GB10 KAT evidence. The cache is not populated, the mixed-q output is not wired into FFT/completed-L/zero closure, and replay, attestation, and Azure overhead are excluded",
                    "classification": "implemented_compact_seeded_component_not_source_eta_or_h100_measurement",
                },
                "small_q_factored_disk_dft_v3": {
                    "active_component_model": True,
                    "legacy_v2_character_frequency_seeds": str(
                        DIRICHLET_SMALL_Q_FREQUENCY_VALUES
                    ),
                    "factored_v3_shared_frequency_records": str(
                        DIRICHLET_SMALL_Q_FACTORED_SHARED_RECORDS
                    ),
                    "primitive_characters": str(
                        DIRICHLET_SMALL_Q_PRIMITIVE_CHARACTERS
                    ),
                    "independent_family_work_equation": (
                        "3 * shared_frequency_records + primitive_characters"
                    ),
                    "independent_family_work": str(
                        dirichlet_small_q_factored_family_work
                    ),
                    "seed_cardinality_reduction_ratio": str(
                        dirichlet_small_q_factored_cardinality_reduction
                    ),
                    "legacy_v2_seed_bytes": str(
                        dirichlet_small_q_v2_seed_payload_bytes
                    ),
                    "factored_v3_minimum_logical_bytes": str(
                        DIRICHLET_SMALL_Q_FACTORED_MINIMUM_LOGICAL_BYTES
                    ),
                    "factored_v3_service_physical_bytes": str(
                        DIRICHLET_SMALL_Q_FACTORED_SERVICE_PHYSICAL_BYTES
                    ),
                    "factored_v3_service_batch_count": str(
                        DIRICHLET_SMALL_Q_FACTORED_SERVICE_BATCHES
                    ),
                    "literal_service_output_bytes": str(
                        DIRICHLET_SMALL_Q_FACTORED_LITERAL_OUTPUT_BYTES
                    ),
                    "source_sample_only_service_output_bytes": str(
                        DIRICHLET_SMALL_Q_FACTORED_REDUCED_OUTPUT_BYTES
                    ),
                    "streaming_integrity_reducer": {
                        "implemented": True,
                        "persistent_raw_output_bytes": "0",
                        "local_cached_megabytes_per_second": str(
                            DIRICHLET_SMALL_Q_OUTPUT_REDUCER_CACHED_MB_PER_SECOND
                        ),
                        "local_pipe_megabytes_per_second": str(
                            DIRICHLET_SMALL_Q_OUTPUT_REDUCER_PIPE_MB_PER_SECOND
                        ),
                        "single_stream_reduced_output_projection_hours": str(
                            DIRICHLET_SMALL_Q_FACTORED_REDUCED_OUTPUT_BYTES
                            / DIRICHLET_SMALL_Q_OUTPUT_REDUCER_PIPE_MB_PER_SECOND
                            / Decimal(1000000)
                            / Decimal(3600)
                        ),
                        "ideal_eight_independent_stream_projection_hours": str(
                            DIRICHLET_SMALL_Q_FACTORED_REDUCED_OUTPUT_BYTES
                            / DIRICHLET_SMALL_Q_OUTPUT_REDUCER_PIPE_MB_PER_SECOND
                            / Decimal(1000000)
                            / Decimal(3600 * PRODUCTION_NODE_COUNT)
                        ),
                        "eight_stream_scaling_measured": False,
                        "classification": "coverage_and_integrity_only_not_arithmetic_or_atom_evidence",
                    },
                    "payload_reduction_ratio": str(
                        dirichlet_small_q_factored_payload_reduction
                    ),
                    "retained_q997_factored_seed_benchmark": {
                        "q": DIRICHLET_SMALL_Q_FACTORED_BENCHMARK_Q,
                        "frequency_count": str(
                            DIRICHLET_SMALL_Q_FACTORED_BENCHMARK_FREQUENCIES
                        ),
                        "character_count": str(
                            DIRICHLET_SMALL_Q_FACTORED_BENCHMARK_CHARACTERS
                        ),
                        "distinct_families": str(
                            DIRICHLET_SMALL_Q_FACTORED_BENCHMARK_FAMILIES
                        ),
                        "producer_seconds": str(
                            DIRICHLET_SMALL_Q_FACTORED_PRODUCER_SECONDS
                        ),
                        "producer_families_per_second": str(
                            dirichlet_small_q_factored_retained_producer_families_per_second
                        ),
                        "independent_checker_seconds": str(
                            DIRICHLET_SMALL_Q_FACTORED_CHECKER_SECONDS
                        ),
                        "independent_checker_families_per_second": str(
                            dirichlet_small_q_factored_retained_checker_families_per_second
                        ),
                        "classification": "source_shaped_factored_seed_frame_not_source_execution",
                    },
                    "source_parameter_q997_service_benchmark": {
                        "q": DIRICHLET_SMALL_Q_FACTORED_BENCHMARK_Q,
                        "frequency_count": str(
                            DIRICHLET_SMALL_Q_FACTORED_SOURCE_BENCHMARK_FREQUENCIES
                        ),
                        "character_count": str(
                            DIRICHLET_SMALL_Q_FACTORED_SOURCE_BENCHMARK_CHARACTERS
                        ),
                        "distinct_families": str(
                            DIRICHLET_SMALL_Q_FACTORED_SOURCE_BENCHMARK_FAMILIES
                        ),
                        "producer_wall_seconds": str(
                            DIRICHLET_SMALL_Q_FACTORED_SOURCE_PRODUCER_SECONDS
                        ),
                        "producer_families_per_second": str(
                            dirichlet_small_q_factored_producer_families_per_second
                        ),
                        "independent_checker_seconds": str(
                            DIRICHLET_SMALL_Q_FACTORED_SOURCE_CHECKER_SECONDS
                        ),
                        "independent_checker_families_per_second": str(
                            dirichlet_small_q_factored_checker_families_per_second
                        ),
                        "classification": "one_complete_source_parameter_q_plan_and_replay_not_full_campaign",
                    },
                    "independent_checker_source_projection": {
                        "ideal_four_dc96as_v6_wall_hours": str(
                            dirichlet_small_q_factored_replay_cpu_wall
                        ),
                        "formula": "(3 * 16385441792 + 18477108) / measured_checker_families_per_second / 3600 / 384",
                        "producer_generation_included": False,
                        "source_scale_performance_validated": False,
                    },
                    "retained_q997_factored_cuda_benchmark": {
                        "finite_gaussian_terms": str(
                            DIRICHLET_SMALL_Q_FACTORED_CUDA_TERMS
                        ),
                        "radix2_butterflies": str(
                            DIRICHLET_SMALL_Q_FACTORED_CUDA_BUTTERFLIES
                        ),
                        "finite_plus_dft_seconds": str(
                            DIRICHLET_SMALL_Q_FACTORED_CUDA_SECONDS
                        ),
                        "combined_work_items_per_second": str(
                            dirichlet_small_q_factored_cuda_work_per_second
                        ),
                        "classification": "source_shaped_gb10_combined_stage_not_h100_measurement",
                    },
                    "source_cuda_work": {
                        "finite_gaussian_terms": str(
                            DIRICHLET_SMALL_Q_GAUSSIAN_TERMS
                        ),
                        "finite_gaussian_terms_is_planning_estimate": True,
                        "radix2_butterflies": str(
                            DIRICHLET_SMALL_Q_RADIX2_BUTTERFLIES
                        ),
                        "radix2_butterflies_is_exact": True,
                    },
                    "ideal_eight_equal_gb10_wall_hours": str(
                        dirichlet_small_q_factored_equal_gb10_wall
                    ),
                    "five_to_ten_x_h100_sensitivity_wall_hours": {
                        "low": str(
                            dirichlet_small_q_factored_equal_gb10_wall
                            / Decimal(10)
                        ),
                        "high": str(
                            dirichlet_small_q_factored_equal_gb10_wall
                            / Decimal(5)
                        ),
                    },
                    "factored_cuda_consumer_implemented": True,
                    "independent_factored_checker_implemented": True,
                    "q_persistent_source_service_implemented": True,
                    "compact_downstream_reducer_implemented": True,
                    "semantic_time_tail_sign_reducer_implemented": True,
                    "semantic_time_tail_control_records": str(
                        DIRICHLET_SMALL_Q_SEMANTIC_CONTROL_RECORDS
                    ),
                    "semantic_time_tail_control_bytes": str(
                        DIRICHLET_SMALL_Q_SEMANTIC_CONTROL_BYTES
                    ),
                    "semantic_two_bit_sign_artifact_bytes": str(
                        DIRICHLET_SMALL_Q_SEMANTIC_SIGN_ARTIFACT_BYTES
                    ),
                    "semantic_reducer_cuda_fused": False,
                    "semantic_reducer_source_performance_measured": False,
                    "semantic_reducer_requires_higher_precision_control_replay": True,
                    "semantic_reducer_preserves_ambiguous_samples": True,
                    "semantic_reducer_multiplicity_inference_performed": False,
                    "source_streaming_compact_v3": {
                        "implemented": True,
                        "raw_disk_stream_persisted": False,
                        "packed_sign_family_persisted": False,
                        "primitive_character_count": (
                            dirichlet_compact_v3_storage[
                                "primitive_character_count"
                            ]
                        ),
                        "primitive_character_sample_count": (
                            dirichlet_compact_v3_storage[
                                "primitive_character_sample_count"
                            ]
                        ),
                        "final_dense_byte_floor_without_q_or_page_padding": (
                            dirichlet_compact_v3_storage[
                                "final_dense_byte_floor_without_q_or_page_padding"
                            ]
                        ),
                        "final_canonical_wire_bytes_without_ambiguity_ranges": (
                            dirichlet_compact_v3_storage[
                                "final_canonical_wire_bytes_without_ambiguity_ranges"
                            ]
                        ),
                        "eight_lane_dense_byte_floor_total": (
                            dirichlet_compact_v3_storage[
                                "eight_lane_dense_byte_floor_total"
                            ]
                        ),
                        "eight_lane_canonical_wire_byte_total_without_ambiguity_ranges": (
                            sum(
                                dirichlet_compact_v3_storage[
                                    "eight_lane_canonical_wire_bytes_without_ambiguity_ranges"
                                ]
                            )
                        ),
                        "ambiguity_density_measured": (
                            dirichlet_compact_v3_storage[
                                "ambiguity_density_measured"
                            ]
                        ),
                        "source_scale_storage_admitted": (
                            dirichlet_compact_v3_storage[
                                "source_scale_storage_admitted"
                            ]
                        ),
                        "projection_sha256": (
                            dirichlet_compact_v3_storage[
                                "projection_sha256"
                            ]
                        ),
                        "classification": (
                            "exact_formulaic_dense_storage_projection_"
                            "with_unmeasured_sparse_ambiguities"
                        ),
                    },
                    "source_wide_post_dft_width_usefulness_proved": False,
                    "external_atom_discharged": False,
                    "warning": "the q-level semantic reducer now joins a completely replayed even/odd time-tail control with every character/sample disk and feeds exact negative/positive/ambiguous codes directly into a roughly 63-GB final dense state instead of persisting either the 226.996-TB disk stream or 1.182-TB packed-sign family; however the disk rows still cross the transient pipe because CUDA fusion is absent, sparse ambiguity density and source-scale timing are unmeasured, and source-wide post-DFT width closure remains absent",
                    "classification": "active_factored_v3_component_projection_not_source_eta_or_h100_measurement",
                },
                "small_q_certified_disk_dft_v2": {
                    "active_component_model": False,
                    "superseded_by": "small_q_factored_disk_dft_v3",
                    "finite_gaussian_terms": str(
                        DIRICHLET_SMALL_Q_GAUSSIAN_TERMS
                    ),
                    "finite_gaussian_terms_is_planning_estimate": True,
                    "frequency_values_and_independently_replayed_seeds": str(
                        DIRICHLET_SMALL_Q_FREQUENCY_VALUES
                    ),
                    "radix2_butterflies": str(
                        DIRICHLET_SMALL_Q_RADIX2_BUTTERFLIES
                    ),
                    "retained_gb10_benchmark": {
                        "q": DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_Q,
                        "frequency_prefix": str(
                            DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_FREQUENCIES
                        ),
                        "finite_gaussian_terms": str(
                            DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_TERMS
                        ),
                        "finite_disk_seconds": str(
                            DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_TERM_SECONDS
                        ),
                        "finite_disk_terms_per_second": str(
                            dirichlet_small_q_certified_terms_per_second
                        ),
                        "radix2_butterflies": str(
                            DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_BUTTERFLIES
                        ),
                        "persistent_dft_seconds": str(
                            DIRICHLET_SMALL_Q_CERTIFIED_BENCHMARK_DFT_SECONDS
                        ),
                        "persistent_dft_butterflies_per_second": str(
                            dirichlet_small_q_certified_butterflies_per_second
                        ),
                        "classification": "source_like_prefix_on_gb10_not_h100_measurement",
                    },
                    "ideal_eight_equal_gb10_wall_hours": {
                        name: str(value)
                        for name, value in {
                            **dirichlet_small_q_certified_gpu_walls,
                            "combined": dirichlet_small_q_certified_equal_gb10_wall,
                        }.items()
                    },
                    "five_to_ten_x_h100_sensitivity_wall_hours": {
                        "low": str(
                            dirichlet_small_q_certified_equal_gb10_wall
                            / Decimal(10)
                        ),
                        "high": str(
                            dirichlet_small_q_certified_equal_gb10_wall
                            / Decimal(5)
                        ),
                    },
                    "bandwidth_roofline_14_3x_wall_hours": str(
                        dirichlet_small_q_certified_equal_gb10_wall
                        / Decimal("14.3")
                    ),
                    "independent_arb_seed_replay": {
                        "measured_frequencies_per_second": str(
                            DIRICHLET_SMALL_Q_CERTIFIED_ARB_SEEDS_PER_SECOND
                        ),
                        "ideal_four_dc96as_v6_wall_hours": str(
                            dirichlet_small_q_v2_seed_replay_cpu_wall
                        ),
                        "producer_generation_not_included": True,
                    },
                    "minimum_seed_payload_bytes": str(
                        dirichlet_small_q_v2_seed_payload_bytes
                    ),
                    "observed_source_like_pre_dft_disk_radius": str(
                        DIRICHLET_SMALL_Q_CERTIFIED_OBSERVED_PRE_DFT_RADIUS
                    ),
                    "source_wide_post_dft_width_usefulness_proved": False,
                    "warning": "the rigorous v2 disk kernel and independent O(frequency) seed checker are implemented, but 622.9 TB of seed payload and unproved accumulated/scaled output widths prevent a source-performance-ready claim",
                    "classification": "superseded_v2_comparison_not_active_component_model",
                },
                "large_q_residue_composition": {
                    "residue_compositions": str(
                        DIRICHLET_RESIDUE_COMPOSITION_VALUES
                    ),
                    "batch64_invocations": str(
                        DIRICHLET_RESIDUE_COMPOSITION_BATCH64_INVOCATIONS
                    ),
                    "materialized_transform_input_bytes_avoided_by_streaming": str(
                        DIRICHLET_RESIDUE_COMPOSITION_MATERIALIZED_BYTES
                    ),
                    "measured_batched_values_per_second": {
                        "low": str(
                            DIRICHLET_RESIDUE_COMPOSITION_BATCHED_VALUES_PER_SECOND_LOW
                        ),
                        "high": str(
                            DIRICHLET_RESIDUE_COMPOSITION_BATCHED_VALUES_PER_SECOND_HIGH
                        ),
                    },
                    "ideal_384_process_wall_hours": {
                        name: str(value)
                        for name, value in dirichlet_residue_composition_cpu_walls.items()
                    },
                    "persistent_framed_producer_ready": True,
                    "source_scale_performance_validated": False,
                    "classification": "implemented_persistent_component_with_ideal_cpu_scaling_sensitivity",
                },
                "large_q_root_number_stage": {
                    "active_moduli": str(DIRICHLET_ROOT_ACTIVE_MODULI),
                    "additive_transcendental_seeds": str(
                        DIRICHLET_ROOT_ADDITIVE_SEEDS
                    ),
                    "additive_recurrence_complex_multiplications": str(
                        DIRICHLET_ROOT_ADDITIVE_MULTIPLICATIONS
                    ),
                    "unit_group_input_rectangles": str(
                        DIRICHLET_ROOT_INPUT_RECTANGLES
                    ),
                    "primitive_root_records": str(
                        DIRICHLET_ROOT_PRIMITIVE_RECORDS
                    ),
                    "radix2_butterflies": str(
                        DIRICHLET_ROOT_RADIX2_BUTTERFLIES
                    ),
                    "unstreamed_root_bytes": str(DIRICHLET_ROOT_STREAM_BYTES),
                    "measured_gb10_cpu_rates": {
                        "additive_rectangles_per_second": str(
                            DIRICHLET_ROOT_GB10_INPUT_RECTANGLES_PER_SECOND
                        ),
                        "primitive_normalizations_per_second": str(
                            DIRICHLET_ROOT_GB10_NORMALIZATIONS_PER_SECOND
                        ),
                    },
                    "projected_cpu_core_hours": {
                        "additive_input": str(dirichlet_root_input_cpu_core_hours),
                        "primitive_normalization": str(
                            dirichlet_root_normalization_cpu_core_hours
                        ),
                        "current_per_q_twiddle_preparation": str(
                            DIRICHLET_ROOT_CURRENT_TWIDDLE_CPU_HOURS
                        ),
                        "per_process_startup": str(
                            DIRICHLET_ROOT_PROCESS_STARTUP_CPU_HOURS
                        ),
                    },
                    "ideal_four_dc96as_v6_cpu_wall_hours": str(
                        dirichlet_root_cpu_wall
                    ),
                    "ideal_eight_equal_gb10_gpu_wall_hours": {
                        name: str(value)
                        for name, value in dirichlet_root_equal_gb10_gpu_walls.items()
                    },
                    "five_to_ten_x_h100_gpu_sensitivity_wall_hours": {
                        "low": str(
                            dirichlet_root_equal_gb10_gpu_walls["low"]
                            / Decimal(10)
                        ),
                        "high": str(
                            dirichlet_root_equal_gb10_gpu_walls["high"]
                            / Decimal(5)
                        ),
                    },
                    "persistent_bounded_protocol_ready": True,
                    "consumer_artifact_integration_ready": True,
                    "source_performance_ready": False,
                    "classification": "implemented_source_scalable_component_projection_not_h100_measurement_or_zero_closure",
                },
                "routine_factor8_postprocess": {
                    "base_grid_completed_value_intervals": str(
                        DIRICHLET_BASE_COMPLETED_SAMPLES
                    ),
                    "factor8_target_grid_samples": str(
                        DIRICHLET_FACTOR8_TARGET_SAMPLES
                    ),
                    "aligned_targets_reusing_base_intervals": str(
                        DIRICHLET_BASE_COMPLETED_SAMPLES
                    ),
                    "nonaligned_interpolated_targets": str(
                        DIRICHLET_FACTOR8_NONALIGNED_TARGET_SAMPLES
                    ),
                    "forty_tap_interval_products": str(
                        DIRICHLET_FACTOR8_SINC_PRODUCT_TERMS
                    ),
                    "retired_cpu_sensitivity": {
                        "synthetic_sinc_input_terms_per_second": str(
                            DIRICHLET_POSTPROCESS_INTERVALS_PER_SECOND
                        ),
                        "former_target_count_divided_by_term_rate_wall_hours": str(
                            dirichlet_cpu_reference_walls_before[
                                "historical_invalid_factor8_targets_divided_by_sinc_terms_per_second"
                            ]
                        ),
                        "classification": (
                            "dimensionally_invalid_historical_comparison_not_"
                            "included_in_active_component_totals"
                        ),
                    },
                    "retained_gb10_benchmark": {
                        "base_completed_intervals_per_trial": 1048576,
                        "target_samples_per_trial": 8388288,
                        "trials": 3,
                        "repetitions_per_trial": 50,
                        "four_corner_median_target_samples_per_second": str(
                            DIRICHLET_FACTOR8_FOUR_CORNER_GB10_TARGETS_PER_SECOND
                        ),
                        "signed_coefficient_fused_median_target_samples_per_second": str(
                            DIRICHLET_FACTOR8_FUSED_GB10_TARGETS_PER_SECOND
                        ),
                        "median_paired_speedup": str(
                            DIRICHLET_FACTOR8_FUSED_MEDIAN_SPEEDUP
                        ),
                        "output_artifacts_byte_identical_every_trial": True,
                        "bounded_exact_rational_strict_sign_replay": True,
                        "classification": (
                            "synthetic_gb10_kernel_measurement_not_h100_or_"
                            "source_execution"
                        ),
                    },
                    "ideal_eight_equal_gb10_wall_hours": str(
                        dirichlet_factor8_fused_equal_gb10_wall
                    ),
                    "five_to_ten_x_h100_sensitivity_wall_hours": {
                        name: str(value)
                        for name, value in dirichlet_factor8_fused_h100_sensitivity.items()
                    },
                    "coefficient_artifact_complete_arb_replay": True,
                    "bounded_strict_sign_exact_rational_replay": True,
                    "strict_sm90_build_available": True,
                    "h100_measurement_available": False,
                    "source_scale_input_stream_integrated": False,
                    "uniform_interpolation_error_proved": False,
                    "physical_cuda_refinement_proved": False,
                    "production_ready": False,
                    "external_atom_discharged": False,
                    "projection_excludes": [
                        "upstream completed-L construction",
                        "input generation and transfer",
                        "boundary padding and exception factors 32, 128, and 512",
                        "uniform interpolation-error proof",
                        "zero multiplicity and Turing closure",
                        "attestation and independent source replay",
                    ],
                    "classification": (
                        "implemented_bounded_arithmetic_component_not_h100_"
                        "calibration_source_run_or_grh_closure"
                    ),
                },
                "literal_cpu_reference_sensitivities": {
                    "before_certified_v2_and_stream_components": {
                        name: {
                            "ideal_four_dc96as_v6_wall_hours": str(value),
                            "ideal_four_dc96as_v6_wall_years": str(
                                value / HOURS_PER_YEAR
                            ),
                        }
                        for name, value in dirichlet_cpu_reference_walls_before.items()
                    },
                    "after_common_components": {
                        name: {
                            "ideal_four_dc96as_v6_wall_hours": str(value),
                            "ideal_four_dc96as_v6_wall_years": str(
                                value / HOURS_PER_YEAR
                            ),
                        }
                        for name, value in dirichlet_cpu_reference_walls_after_common.items()
                    },
                    "residue_composition_range": {
                        name: str(value)
                        for name, value in dirichlet_residue_composition_cpu_walls.items()
                    },
                },
                "selected_character_fused_stage": {
                    "measured_gb10_group_points_per_second": "43026000",
                    "direct_all_character_source_group_points": "47631269684196653160",
                    "role": "sparse audit/exception oracle, not the all-character production algorithm",
                },
                "implemented_but_conditional": [
                    "certified Arb Hurwitz-lattice seeds and finite addback",
                    "fully replayed 96-MB finite-recovery recurrence seed table and compact fused CUDA consumer",
                    "project-derived exact-rational Taylor tail",
                    "directed CUDA lattice Taylor reconstruction",
                    "all-character CRT/Bluestein directed interval transform with MPFR replay",
                    "persistent framed residue composition and all-character transform services",
                    "alternative q-persistent fused large-q Taylor/composition CUDA batches",
                    "source-scalable all-character root-number transform and bounded artifact stream",
                    "small-q v3 factored directed disk recurrence/DFT with independent Arb family replay",
                    "q-level small-q higher-precision-replayed parity time-tail controls and exact two-bit sign/ambiguity reduction",
                    "routine factor-eight directed forty-tap convolution, compact sign packing, Arb coefficient replay, and exact-rational bounded strict-sign checker",
                    "completed-L, finite sinc, exception, and paired-Turing arithmetic",
                ],
                "missing_for_source_scale": [
                    "full-source supervisor integrating certified box and seed producers with the existing persistent composer, transform, root artifacts, and completed-L consumer graph",
                    "authenticated t-major Hurwitz-lattice cache/broadcast graph for the remaining 5.180-PB compact fused large-q input boundary",
                    "CUDA-side fusion and source-scale timing for the implemented semantic time-periodization/sign reducer, whose current input is the 226.996-TB source-sample pipe",
                    "persistent completed-value input and compact cross-shard event integration for the routine factor-eight CUDA reducer",
                    "source-wide proof that certified small-q disk widths remain useful after the complete DFT and scaling",
                    "uniform proof of the accepted manuscript interpolation error over every source case",
                    "theorem-level review and Lean realization of the corrected reflected Theorem 3.2 upper bound",
                    "source-wide exception/window-shift policy, execution, and independent replay",
                ],
                "historical_optimized_reference": {
                    "source": "Platt reported approximately 400,000 core-hours",
                    "core_hours": str(DIRICHLET_PAPER_REPORTED_CORE_HOURS),
                    "ideal_four_dc96as_v6_wall_hours": str(
                        dirichlet_historical_cpu_hours
                    ),
                    "ideal_four_dc96as_v6_cost_usd": _cost_range(
                        dirichlet_historical_cpu_hours,
                        dirichlet_historical_cpu_hours,
                        cpu_hourly_cost,
                    ),
                    "classification": "historical_comparison_not_current_engine_eta",
                },
            },
            "conditional_known_work_before_dirichlet": {
                "rows": conditional_rows,
                "interpretation": "ideal concurrent wall time for the current literal FLINT zeta projection, Goldbach binary sensitivity, the historical 40,000-core-hour ladder scale, and the practical subset; Dirichlet contributes zero time only for this counterfactual",
                "cost_scope": "dominant binary-Goldbach and literal-FLINT-zeta compute only; ladder, other campaigns, storage, attestation, retries, and Dirichlet are excluded",
                "classification": "counterfactual_sensitivity_not_complete_portfolio_eta",
            },
            "procurement_working_band_before_dirichlet": {
                "rows": procurement_rows,
                "interpretation": "use the 2x--5x H100/GB10 sensitivity as a provisional budget band and add enough 96-core CPU nodes that the literal zeta replay does not lengthen it",
                "cost_scope": "dominant binary-Goldbach and literal-FLINT-zeta compute only; ladder, other campaigns, storage, attestation, retries, and Dirichlet are excluded",
                "classification": "provisional_procurement_forecast_pending_h100_pilot_not_complete_portfolio_eta",
            },
            "conditional_all13_component_engineering_sensitivity": {
                "rows": conditional_component_rows,
                "dirichlet_gpu_component_wall_hours": {
                    "low": str(dirichlet_gpu_component_wall_after_low),
                    "high": str(dirichlet_gpu_component_wall_after_high),
                },
                "dirichlet_literal_cpu_reference_serial_wall_hours": str(
                    dirichlet_cpu_reference_serial_wall_after["high"]
                ),
                "dirichlet_literal_cpu_reference_serial_wall_hours_range": {
                    name: str(value)
                    for name, value in dirichlet_cpu_reference_serial_wall_after.items()
                },
                "dirichlet_component_model_revision": {
                    "before_certified_v2_and_stream_components": {
                        "cpu_384_core_serial_wall_hours": {
                            "low": str(dirichlet_cpu_reference_serial_wall_before),
                            "high": str(dirichlet_cpu_reference_serial_wall_before),
                        },
                        "gpu_8_device_five_to_ten_x_sensitivity_wall_hours": {
                            "low": str(dirichlet_gpu_component_wall_before_low),
                            "high": str(dirichlet_gpu_component_wall_before_high),
                        },
                        "ideal_concurrent_wall_hours": {
                            "low": str(
                                max(
                                    dirichlet_cpu_reference_serial_wall_before,
                                    dirichlet_gpu_component_wall_before_low,
                                )
                            ),
                            "high": str(
                                max(
                                    dirichlet_cpu_reference_serial_wall_before,
                                    dirichlet_gpu_component_wall_before_high,
                                )
                            ),
                        },
                        "serialized_wall_hours": {
                            "low": str(
                                dirichlet_cpu_reference_serial_wall_before
                                + dirichlet_gpu_component_wall_before_low
                            ),
                            "high": str(
                                dirichlet_cpu_reference_serial_wall_before
                                + dirichlet_gpu_component_wall_before_high
                            ),
                        },
                        "compute_cost_usd": dirichlet_component_cost_before,
                        "classification": "superseded_conditional_component_model_for_comparison_only",
                    },
                    "after_certified_v2_and_stream_components": {
                        "cpu_384_core_serial_wall_hours": {
                            name: str(value)
                            for name, value in dirichlet_cpu_reference_serial_wall_after_v2.items()
                        },
                        "gpu_8_device_five_to_ten_x_sensitivity_wall_hours": {
                            "low": str(dirichlet_gpu_component_wall_after_v2_low),
                            "high": str(dirichlet_gpu_component_wall_after_v2_high),
                        },
                        "ideal_concurrent_wall_hours": {
                            "low": str(
                                max(
                                    dirichlet_cpu_reference_serial_wall_after_v2["low"],
                                    dirichlet_gpu_component_wall_after_v2_low,
                                )
                            ),
                            "high": str(
                                max(
                                    dirichlet_cpu_reference_serial_wall_after_v2["high"],
                                    dirichlet_gpu_component_wall_after_v2_high,
                                )
                            ),
                        },
                        "serialized_wall_hours": {
                            "low": str(
                                dirichlet_cpu_reference_serial_wall_after_v2["low"]
                                + dirichlet_gpu_component_wall_after_v2_low
                            ),
                            "high": str(
                                dirichlet_cpu_reference_serial_wall_after_v2["high"]
                                + dirichlet_gpu_component_wall_after_v2_high
                            ),
                        },
                        "compute_cost_usd": dirichlet_component_cost_after_v2,
                        "active_component_model": False,
                        "superseded_by": "after_factored_v3_and_stream_components",
                        "classification": "superseded_v2_conditional_component_model_for_comparison_only",
                    },
                    "after_factored_v3_and_stream_components": {
                        "cpu_384_core_serial_wall_hours": {
                            name: str(value)
                            for name, value in dirichlet_cpu_reference_serial_wall_after.items()
                        },
                        "gpu_8_device_five_to_ten_x_sensitivity_wall_hours": {
                            "low": str(dirichlet_gpu_component_wall_after_low),
                            "high": str(dirichlet_gpu_component_wall_after_high),
                        },
                        "ideal_concurrent_wall_hours": {
                            "low": str(
                                max(
                                    dirichlet_cpu_reference_serial_wall_after["low"],
                                    dirichlet_gpu_component_wall_after_low,
                                )
                            ),
                            "high": str(
                                max(
                                    dirichlet_cpu_reference_serial_wall_after["high"],
                                    dirichlet_gpu_component_wall_after_high,
                                )
                            ),
                        },
                        "serialized_wall_hours": {
                            "low": str(
                                dirichlet_cpu_reference_serial_wall_after["low"]
                                + dirichlet_gpu_component_wall_after_low
                            ),
                            "high": str(
                                dirichlet_cpu_reference_serial_wall_after["high"]
                                + dirichlet_gpu_component_wall_after_high
                            ),
                        },
                        "compute_cost_usd": dirichlet_component_cost_after,
                        "conditional_compute_cost_reduction_vs_before_usd": (
                            dirichlet_component_cost_reduction
                        ),
                        "conditional_compute_cost_reduction_vs_v2_usd": (
                            dirichlet_component_cost_reduction_vs_v2
                        ),
                        "active_component_model": True,
                        "classification": "conditional_ideal_scaling_sensitivity_not_source_eta",
                    },
                    "alternative_fused_large_q_arithmetic": {
                        "replaces_if_its_input_boundary_is_closed": [
                            "large-q directed lattice Taylor GPU arithmetic",
                            "large-q persistent CPU residue composition",
                        ],
                        "eight_equal_gb10_wall_hours": str(
                            dirichlet_large_q_fused_equal_gb10_wall
                        ),
                        "eight_h100_five_to_ten_x_sensitivity_wall_hours": {
                            name: str(value)
                            for name, value in dirichlet_large_q_fused_h100_sensitivity.items()
                        },
                        "literal_certified_input_bytes": str(
                            DIRICHLET_LARGE_Q_FUSED_TOTAL_INPUT_BYTES
                        ),
                        "substituted_into_before_or_after_totals": False,
                        "reason_not_substituted": "certified box generation/replay and the 18.264-PB logical streaming plan are not implemented or benchmarked source-wide",
                        "classification": "alternative_arithmetic_sensitivity_not_end_to_end_runtime",
                    },
                    "current_seeded_fused_large_q_arithmetic": {
                        "replaces_if_its_remaining_input_boundary_is_closed": [
                            "large-q directed lattice Taylor GPU arithmetic",
                            "large-q persistent CPU residue composition",
                        ],
                        "eight_equal_gb10_wall_hours": str(
                            dirichlet_large_q_seeded_equal_gb10_wall
                        ),
                        "eight_h100_five_to_ten_x_sensitivity_wall_hours": {
                            name: str(value)
                            for name, value in dirichlet_large_q_seeded_h100_sensitivity.items()
                        },
                        "logical_input_bytes": str(
                            DIRICHLET_LARGE_Q_SEEDED_TOTAL_INPUT_BYTES
                        ),
                        "finite_recovery_seed_artifact_bytes": str(
                            DIRICHLET_RECOVERY_SEED_ARTIFACT_BYTES
                        ),
                        "substituted_into_before_or_after_totals": False,
                        "reason_not_substituted": "the 125-GiB t-major cache format, reader, replay repacker, and broadcast schedule are implemented, but the source cache is not populated and the schedule is not CUDA-integrated or measured source-wide",
                        "classification": "current_seeded_arithmetic_sensitivity_not_end_to_end_runtime",
                    },
                    "comparison_scope": "quantified component arithmetic only; the active v3 model factors the small-q seed boundary into shared frequency/parity families plus character phases, while the v2 151.7-hour/622.9-TB model remains visible only for comparison",
                },
                "interpretation": "engineering budget obtained by summing measured component work at ideal linear scaling: 10x/5x H100-vs-GB10 sensitivity for implemented Dirichlet GPU arithmetic, one source-shaped small-q v3 factored-family Arb replay, persistent residue composition, root-number production, remaining literal four-node CPU sensitivities, literal FLINT zeta, and each Goldbach row",
                "cost_scope": "dominant Goldbach, zeta, and currently quantified Dirichlet components; storage, retries, attestation, remaining integration, unquantified exceptions, and the practical short campaigns are excluded",
                "missing_conditions": [
                    "the persistent component graph, fully replayed finite-recovery seeds, and t-major lattice cache contract are wired as components, but no populated source cache or CUDA broadcast supervisor integrates them into one fail-closed campaign",
                    "the q-persistent small-q service and semantic time-tail/sign reducer are implemented, but CUDA fusion/source-scale timing for the 226.996-TB input pipe and source-wide interval-width usefulness are not closed",
                    "the interpolation bound and theorem-level reflected Turing bridge remain unresolved",
                    "no Azure H100 component has been calibrated",
                ],
                "classification": "conditional_component_sensitivity_not_complete_portfolio_eta",
            },
            "all_13_logical_atoms": {
                "available": False,
                "reason": "the persistent Dirichlet component graph, certified small-q arithmetic, scalable root-number artifacts, and fully replayed finite-recovery seed path are implemented, but t-major Hurwitz-lattice supply, the small-q width boundary, uniform interpolation proof, and corrected Turing branch are not production-closed; component sensitivities are therefore not a defensible full-atom ETA, and Goldbach still needs an Azure H100 calibration",
            },
        },
        "cost_formula": {
            "eight_node_usd_per_wall_hour": {
                name: _money(Decimal(PRODUCTION_NODE_COUNT) * rate)
                for name, rate in rates.items()
            },
            "eight_node_usd_per_wall_day": {
                name: _money(Decimal(24 * PRODUCTION_NODE_COUNT) * rate)
                for name, rate in rates.items()
            },
            "four_cpu_node_usd_per_wall_hour": {
                name: _money(Decimal(CPU_NODE_COUNT) * rate)
                for name, rate in cpu_rates.items()
            },
            "four_cpu_node_usd_per_wall_day": {
                name: _money(Decimal(24 * CPU_NODE_COUNT) * rate)
                for name, rate in cpu_rates.items()
            },
            "excludes": [
                "Managed HSM lifetime",
                "storage and egress",
                "CPU-only capacity beyond the modeled four-DC96as-v6 cluster",
                "capacity delays",
                "spot eviction/replay overhead",
            ],
        },
        "nonclaims": [
            "No projected range is a completed finite computation.",
            "A successful external run does not by itself discharge a Lean atom.",
            "Every Goldbach sensitivity row is arithmetic from a GB10 source-height benchmark, not an H100 measurement or promised speedup.",
            "The current zeta estimate assumes ideal distribution across 384 DC96as-v6 cores and excludes orchestration overhead.",
            "The 14.3x Goldbach endpoint is a memory-bandwidth roofline ratio, not a runtime multiplier for atomic and integer-heavy code.",
            "No full-portfolio ETA is asserted while the optimized Dirichlet-GRH component pipeline and its analytic closure conditions remain incomplete.",
        ],
    }
