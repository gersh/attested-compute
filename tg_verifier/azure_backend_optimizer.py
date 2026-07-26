# Copyright (c) 2026 Gershon Bialer. All rights reserved.
# SPDX-License-Identifier: MIT

"""Fail-closed Azure backend selection for physical TG campaigns.

The optimizer works in node-hours, not in guessed machine-speed multipliers.
Domain code supplies a reviewed route catalogue whose node-hour ranges are
derived from retained measurements.  Routes with no calibration may be shown
as sensitivities, but they are never selected by the cost optimizer.

The scheduling model is intentionally small and auditable: every campaign is
given a dedicated elastic pool, independent resource branches of a mixed route
may overlap, and scaling is ideal up to an explicit cap.  Storage, queueing,
retries, and attestation are outside this arithmetic model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_CEILING
from typing import Any, Mapping, Sequence


RESOURCE_CLASSES = ("dc96_cpu", "ncc_h100")
CONFIGURATION_CLASSES = ("cpu_only", "h100_only", "mixed")
ROUTE_READINESS = ("eligible", "sensitivity_only", "unavailable")
PRICE_CLASSES = ("pay_as_you_go", "spot")

# Hard release gates for the requested production campaign.  Callers may ask
# the optimizer to explore a shorter deadline or a smaller budget, but may not
# relax these ceilings and still receive ``production_ready = true``.
PRODUCTION_MAX_WALL_HOURS = Decimal("168")
PRODUCTION_MAX_COST_USD = Decimal("10000")


class BackendOptimizationError(ValueError):
    """A route catalogue or optimization request failed closed."""


@dataclass(frozen=True)
class ResourceDemand:
    """One independently scalable resource branch of a campaign route."""

    resource_class: str
    node_hours_low: Decimal
    node_hours_high: Decimal
    default_nodes: int
    parallelism_cap: int
    evidence_id: str
    calibrated: bool
    calibration_scope: str
    target_sku_measured: bool
    basis: str

    def as_json(self) -> dict[str, Any]:
        value = asdict(self)
        value["node_hours_low"] = str(self.node_hours_low)
        value["node_hours_high"] = str(self.node_hours_high)
        return value


@dataclass(frozen=True)
class CampaignRoute:
    """A CPU-only, H100-node-only, or mixed route for one campaign."""

    campaign_id: str
    route_id: str
    configuration_class: str
    readiness: str
    demands: tuple[ResourceDemand, ...]
    basis: str
    unavailable_reason: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "route_id": self.route_id,
            "configuration_class": self.configuration_class,
            "readiness": self.readiness,
            "demands": [item.as_json() for item in self.demands],
            "basis": self.basis,
            "unavailable_reason": self.unavailable_reason,
        }


def _positive_prices(name: str, value: Mapping[str, Decimal]) -> None:
    if set(value) != set(PRICE_CLASSES):
        raise BackendOptimizationError(
            f"{name} must contain exactly pay_as_you_go and spot"
        )
    if any(not isinstance(rate, Decimal) or rate <= 0 for rate in value.values()):
        raise BackendOptimizationError(f"{name} rates must be positive Decimal values")


def _validate_catalog(
    physical_campaign_ids: Sequence[str], routes: Sequence[CampaignRoute]
) -> None:
    if not physical_campaign_ids or len(set(physical_campaign_ids)) != len(
        physical_campaign_ids
    ):
        raise BackendOptimizationError(
            "physical campaign identifiers must be nonempty and unique"
        )
    expected = set(physical_campaign_ids)
    keys: set[tuple[str, str]] = set()
    classes: dict[str, set[str]] = {campaign_id: set() for campaign_id in expected}
    for route in routes:
        if route.campaign_id not in expected:
            raise BackendOptimizationError(
                f"route {route.route_id} names an unknown physical campaign"
            )
        key = (route.campaign_id, route.route_id)
        if key in keys:
            raise BackendOptimizationError(f"duplicate route: {key}")
        keys.add(key)
        if route.configuration_class not in CONFIGURATION_CLASSES:
            raise BackendOptimizationError(
                f"{route.route_id} has an unknown configuration class"
            )
        if route.readiness not in ROUTE_READINESS:
            raise BackendOptimizationError(
                f"{route.route_id} has an unknown readiness class"
            )
        classes[route.campaign_id].add(route.configuration_class)
        if route.readiness == "unavailable":
            if route.demands or not route.unavailable_reason:
                raise BackendOptimizationError(
                    f"unavailable route {route.route_id} must have no demands and a reason"
                )
            continue
        if not route.demands:
            raise BackendOptimizationError(
                f"priced route {route.route_id} has no resource demand"
            )
        resources: set[str] = set()
        for demand in route.demands:
            if demand.resource_class not in RESOURCE_CLASSES:
                raise BackendOptimizationError(
                    f"{route.route_id} has an unknown resource class"
                )
            if demand.resource_class in resources:
                raise BackendOptimizationError(
                    f"{route.route_id} repeats one resource class; aggregate it first"
                )
            resources.add(demand.resource_class)
            if (
                not isinstance(demand.node_hours_low, Decimal)
                or not isinstance(demand.node_hours_high, Decimal)
                or demand.node_hours_low <= 0
                or demand.node_hours_high < demand.node_hours_low
            ):
                raise BackendOptimizationError(
                    f"{route.route_id} has an invalid node-hour range"
                )
            if (
                demand.default_nodes < 1
                or demand.parallelism_cap < demand.default_nodes
            ):
                raise BackendOptimizationError(
                    f"{route.route_id} has invalid default/capacity nodes"
                )
            if not demand.evidence_id or not demand.calibration_scope:
                raise BackendOptimizationError(
                    f"{route.route_id} lacks named calibration evidence"
                )
            # This is the key fail-closed rule.  Sensitivity rows may carry
            # explicitly uncalibrated work, but optimizer-eligible rows may not.
            if route.readiness == "eligible" and not demand.calibrated:
                raise BackendOptimizationError(
                    f"eligible route {route.route_id} contains uncalibrated demand"
                )
        expected_resources = {
            "cpu_only": {"dc96_cpu"},
            "h100_only": {"ncc_h100"},
            "mixed": {"dc96_cpu", "ncc_h100"},
        }[route.configuration_class]
        if resources != expected_resources:
            raise BackendOptimizationError(
                f"{route.route_id} resources do not match its configuration class"
            )
    for campaign_id, present in classes.items():
        if present != set(CONFIGURATION_CLASSES):
            raise BackendOptimizationError(
                f"{campaign_id} must explicitly classify CPU-only, H100-only, and mixed routes"
            )


def _ceil_ratio(numerator: Decimal, denominator: Decimal) -> int:
    return int((numerator / denominator).to_integral_value(rounding=ROUND_CEILING))


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _evaluate_route(
    route: CampaignRoute,
    *,
    deadline_hours: Decimal | None,
    max_cpu_nodes: int,
    max_h100_nodes: int,
    cpu_prices: Mapping[str, Decimal],
    h100_prices: Mapping[str, Decimal],
    production_max_wall_hours: Decimal,
    production_max_cost_usd: Decimal,
) -> dict[str, Any]:
    result = route.as_json()
    if route.readiness == "unavailable":
        result.update(
            {
                "optimizer_eligible": False,
                "deadline_feasible": False,
                "cost_usd": None,
                "schedule": None,
                "production_gate": {
                    "max_wall_hours": str(production_max_wall_hours),
                    "max_cost_usd": str(production_max_cost_usd),
                    "budget_feasible": {
                        price_class: False for price_class in PRICE_CLASSES
                    },
                    "production_ready": {
                        price_class: False for price_class in PRICE_CLASSES
                    },
                    "blockers": ["route_unavailable"],
                },
            }
        )
        return result

    schedules: list[dict[str, Any]] = []
    branch_walls_low: list[Decimal] = []
    branch_walls_high: list[Decimal] = []
    feasible = True
    for demand in route.demands:
        configured_cap = (
            max_cpu_nodes
            if demand.resource_class == "dc96_cpu"
            else max_h100_nodes
        )
        cap = min(configured_cap, demand.parallelism_cap)
        if deadline_hours is None:
            nodes_low = nodes_high = min(demand.default_nodes, cap)
        else:
            nodes_low = max(1, _ceil_ratio(demand.node_hours_low, deadline_hours))
            nodes_high = max(1, _ceil_ratio(demand.node_hours_high, deadline_hours))
        branch_feasible = nodes_high <= cap
        feasible = feasible and branch_feasible
        wall_low = demand.node_hours_low / Decimal(nodes_low)
        wall_high = demand.node_hours_high / Decimal(nodes_high)
        branch_walls_low.append(wall_low)
        branch_walls_high.append(wall_high)
        schedules.append(
            {
                "resource_class": demand.resource_class,
                "configured_parallelism_cap": cap,
                "nodes_required": {
                    "low_work": nodes_low,
                    "high_work": nodes_high,
                },
                "ideal_wall_hours_at_required_width": {
                    "low": str(wall_low),
                    "high": str(wall_high),
                },
                "deadline_feasible": branch_feasible,
            }
        )
    # Keep exact Decimal costs for every release decision.  The human-facing
    # cost table is rounded to cents, but rounding must never turn (for
    # example) 10000.004 USD into a route that passes a 10000 USD hard cap.
    raw_costs: dict[str, dict[str, Decimal]] = {}
    costs: dict[str, dict[str, str]] = {}
    for price_class in PRICE_CLASSES:
        low = Decimal(0)
        high = Decimal(0)
        for demand in route.demands:
            prices = (
                cpu_prices
                if demand.resource_class == "dc96_cpu"
                else h100_prices
            )
            low += demand.node_hours_low * prices[price_class]
            high += demand.node_hours_high * prices[price_class]
        raw_costs[price_class] = {"low": low, "high": high}
        costs[price_class] = {"low": _money(low), "high": _money(high)}

    # This is the fastest ideal schedule admitted by the route's own
    # parallelism caps and by the caller's resource caps.  The production
    # deadline gate is evaluated against the high-work endpoint; a favorable
    # low endpoint can never promote a route.
    best_wall_low = Decimal(0)
    best_wall_high = Decimal(0)
    for demand in route.demands:
        configured_cap = (
            max_cpu_nodes
            if demand.resource_class == "dc96_cpu"
            else max_h100_nodes
        )
        cap = min(configured_cap, demand.parallelism_cap)
        best_wall_low = max(best_wall_low, demand.node_hours_low / Decimal(cap))
        best_wall_high = max(best_wall_high, demand.node_hours_high / Decimal(cap))
    time_within_budget = best_wall_high <= production_max_wall_hours
    calibrated = route.readiness == "eligible" and all(
        demand.calibrated for demand in route.demands
    )
    target_measured = all(demand.target_sku_measured for demand in route.demands)
    budget_feasible = {
        price_class: time_within_budget
        and raw_costs[price_class]["high"] <= production_max_cost_usd
        for price_class in PRICE_CLASSES
    }
    production_ready = {
        price_class: calibrated and target_measured and budget_feasible[price_class]
        for price_class in PRICE_CLASSES
    }
    production_blockers: list[str] = []
    if not calibrated:
        production_blockers.append("route_not_source_closed_and_calibrated")
    if not target_measured:
        production_blockers.append("target_sku_not_measured")
    if not time_within_budget:
        production_blockers.append("high_work_endpoint_exceeds_wall_limit")
    result.update(
        {
            "optimizer_eligible": route.readiness == "eligible" and feasible,
            "deadline_feasible": feasible,
            "cost_usd": costs,
            "schedule": {
                "deadline_hours": (
                    None if deadline_hours is None else str(deadline_hours)
                ),
                "resource_branches_overlap": True,
                "ideal_route_wall_hours": {
                    "low": str(max(branch_walls_low)),
                    "high": str(max(branch_walls_high)),
                },
                "branches": schedules,
            },
            "production_gate": {
                "max_wall_hours": str(production_max_wall_hours),
                "max_cost_usd": str(production_max_cost_usd),
                "best_ideal_wall_hours_within_caps": {
                    "low": str(best_wall_low),
                    "high": str(best_wall_high),
                },
                "time_budget_feasible": time_within_budget,
                "high_cost_usd_unrounded": {
                    price_class: str(raw_costs[price_class]["high"])
                    for price_class in PRICE_CLASSES
                },
                "budget_feasible": budget_feasible,
                "source_closed_and_calibrated": calibrated,
                "target_sku_measured": target_measured,
                "production_ready": production_ready,
                "blockers": production_blockers,
                "blockers_by_price": {
                    price_class: [
                        *production_blockers,
                        *(
                            ["high_cost_endpoint_exceeds_cost_limit"]
                            if raw_costs[price_class]["high"]
                            > production_max_cost_usd
                            else []
                        ),
                    ]
                    for price_class in PRICE_CLASSES
                },
            },
        }
    )
    return result


def _choose_for_price(
    campaign_ids: Sequence[str],
    evaluated: Sequence[dict[str, Any]],
    *,
    allowed_classes: set[str],
    price_class: str,
    production_max_wall_hours: Decimal,
    production_max_cost_usd: Decimal,
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    partial_low = Decimal(0)
    partial_high = Decimal(0)
    for campaign_id in campaign_ids:
        campaign_rows = [
            row
            for row in evaluated
            if row["campaign_id"] == campaign_id
            and row["configuration_class"] in allowed_classes
        ]
        eligible = [row for row in campaign_rows if row["optimizer_eligible"]]
        if not eligible:
            blockers.append(
                {
                    "campaign_id": campaign_id,
                    "reason": "no calibrated deadline-feasible route in this configuration",
                    "route_statuses": [
                        {
                            "route_id": row["route_id"],
                            "readiness": row["readiness"],
                            "deadline_feasible": row["deadline_feasible"],
                            "unavailable_reason": row["unavailable_reason"],
                        }
                        for row in campaign_rows
                    ],
                }
            )
            continue
        minimax = min(
            eligible,
            key=lambda row: Decimal(row["cost_usd"][price_class]["high"]),
        )
        minimax_high = Decimal(minimax["cost_usd"][price_class]["high"])
        plausibly_optimal = [
            row["route_id"]
            for row in eligible
            if Decimal(row["cost_usd"][price_class]["low"]) <= minimax_high
        ]
        cost = minimax["cost_usd"][price_class]
        partial_low += Decimal(cost["low"])
        partial_high += Decimal(cost["high"])
        decisions.append(
            {
                "campaign_id": campaign_id,
                "minimax_route_id": minimax["route_id"],
                "minimax_cost_usd": cost,
                "plausibly_optimal_route_ids": plausibly_optimal,
                "cost_order_resolved": len(plausibly_optimal) == 1,
            }
        )
    complete = not blockers
    result: dict[str, Any] = {
        "available": complete,
        "price_class": price_class,
        "decisions": decisions,
        "blockers": blockers,
        "covered_campaign_count": len(decisions),
        "partial_covered_cost_usd": {
            "low": _money(partial_low),
            "high": _money(partial_high),
        },
    }
    if complete:
        result["optimized_complete_portfolio_cost_usd"] = {
            "low": _money(partial_low),
            "high": _money(partial_high),
        }
    else:
        result["optimized_complete_portfolio_cost_usd"] = None

    # A cost optimization is not a release authorization.  Re-run the choice
    # against the hard route gates and then enforce the *portfolio* cost cap on
    # the sum of all selected campaigns.  Independent pools may overlap, so
    # the portfolio wall is the maximum selected route wall, not the sum.
    production_decisions: list[dict[str, Any]] = []
    production_blockers: list[dict[str, Any]] = []
    production_cost = Decimal(0)
    production_wall = Decimal(0)
    for campaign_id in campaign_ids:
        campaign_rows = [
            row
            for row in evaluated
            if row["campaign_id"] == campaign_id
            and row["configuration_class"] in allowed_classes
        ]
        candidates = [
            row
            for row in campaign_rows
            if row["production_gate"]["production_ready"][price_class]
        ]
        if not candidates:
            production_blockers.append(
                {
                    "campaign_id": campaign_id,
                    "reason": "no route passes source, target-measurement, time, and per-route cost gates",
                    "route_gates": [
                        {
                            "route_id": row["route_id"],
                            "blockers": row["production_gate"].get(
                                "blockers_by_price", {}
                            ).get(
                                price_class,
                                row["production_gate"]["blockers"],
                            ),
                        }
                        for row in campaign_rows
                    ],
                }
            )
            continue
        selected = min(
            candidates,
            key=lambda row: Decimal(row["cost_usd"][price_class]["high"]),
        )
        high_cost = Decimal(
            selected["production_gate"]["high_cost_usd_unrounded"][price_class]
        )
        high_wall = Decimal(
            selected["production_gate"]["best_ideal_wall_hours_within_caps"][
                "high"
            ]
        )
        production_cost += high_cost
        production_wall = max(production_wall, high_wall)
        production_decisions.append(
            {
                "campaign_id": campaign_id,
                "route_id": selected["route_id"],
                "high_cost_usd": _money(high_cost),
                "high_wall_hours": str(high_wall),
            }
        )
    portfolio_cost_feasible = production_cost <= production_max_cost_usd
    portfolio_time_feasible = production_wall <= production_max_wall_hours
    result["production_gate"] = {
        "hard_max_wall_hours": str(production_max_wall_hours),
        "hard_max_cost_usd": str(production_max_cost_usd),
        "high_endpoints_control": True,
        "selected_routes": production_decisions,
        "campaign_blockers": production_blockers,
        "portfolio_high_cost_usd": _money(production_cost),
        "portfolio_high_wall_hours": str(production_wall),
        "portfolio_cost_feasible": portfolio_cost_feasible,
        "portfolio_time_feasible": portfolio_time_feasible,
        "production_ready": (
            not production_blockers
            and portfolio_cost_feasible
            and portfolio_time_feasible
        ),
    }
    return result


def optimize_backend_catalog(
    *,
    physical_campaign_ids: Sequence[str],
    routes: Sequence[CampaignRoute],
    h100_prices: Mapping[str, Decimal],
    cpu_prices: Mapping[str, Decimal],
    deadline_hours: Decimal | None = None,
    max_cpu_nodes: int = 64,
    max_h100_nodes: int = 8,
    production_max_wall_hours: Decimal = PRODUCTION_MAX_WALL_HOURS,
    production_max_cost_usd: Decimal = PRODUCTION_MAX_COST_USD,
) -> dict[str, Any]:
    """Evaluate and cost a reviewed route catalogue.

    The return value includes sensitivity-only routes, but selection considers
    only ``eligible`` routes.  This makes an absent target calibration a
    visible blocker instead of an implicit speed assumption.
    """

    _positive_prices("h100_prices", h100_prices)
    _positive_prices("cpu_prices", cpu_prices)
    if deadline_hours is not None and (
        not isinstance(deadline_hours, Decimal) or deadline_hours <= 0
    ):
        raise BackendOptimizationError("deadline_hours must be a positive Decimal")
    if max_cpu_nodes < 1 or max_h100_nodes < 1:
        raise BackendOptimizationError("resource node caps must be positive")
    if (
        not isinstance(production_max_wall_hours, Decimal)
        or not production_max_wall_hours.is_finite()
        or production_max_wall_hours <= 0
        or production_max_wall_hours > PRODUCTION_MAX_WALL_HOURS
    ):
        raise BackendOptimizationError(
            "production_max_wall_hours must be a positive Decimal at most 168"
        )
    if (
        not isinstance(production_max_cost_usd, Decimal)
        or not production_max_cost_usd.is_finite()
        or production_max_cost_usd <= 0
        or production_max_cost_usd > PRODUCTION_MAX_COST_USD
    ):
        raise BackendOptimizationError(
            "production_max_cost_usd must be a positive Decimal at most 10000"
        )
    _validate_catalog(physical_campaign_ids, routes)
    evaluated = [
        _evaluate_route(
            route,
            deadline_hours=deadline_hours,
            max_cpu_nodes=max_cpu_nodes,
            max_h100_nodes=max_h100_nodes,
            cpu_prices=cpu_prices,
            h100_prices=h100_prices,
            production_max_wall_hours=production_max_wall_hours,
            production_max_cost_usd=production_max_cost_usd,
        )
        for route in routes
    ]
    scenarios = {
        "cpu_only": {"cpu_only"},
        "h100_only": {"h100_only"},
        "mixed_flexible": set(CONFIGURATION_CLASSES),
    }
    comparisons = {
        scenario: {
            price_class: _choose_for_price(
                physical_campaign_ids,
                evaluated,
                allowed_classes=allowed,
                price_class=price_class,
                production_max_wall_hours=production_max_wall_hours,
                production_max_cost_usd=production_max_cost_usd,
            )
            for price_class in PRICE_CLASSES
        }
        for scenario, allowed in scenarios.items()
    }
    flexible_blockers = comparisons["mixed_flexible"]["pay_as_you_go"][
        "blockers"
    ]
    return {
        "schema": "sparkinterval.tg.azure-backend-optimizer.v1",
        "classification": "cost_and_deadline_sensitivity_not_execution_or_capacity_quote",
        "physical_campaign_count": len(physical_campaign_ids),
        "physical_campaign_ids": list(physical_campaign_ids),
        "deadline_hours": None if deadline_hours is None else str(deadline_hours),
        "resource_caps": {
            "dc96_cpu_nodes": max_cpu_nodes,
            "ncc_h100_nodes": max_h100_nodes,
        },
        "production_budget": {
            "hard_max_wall_hours": str(production_max_wall_hours),
            "hard_max_cost_usd": str(production_max_cost_usd),
            "limits_may_only_be_tightened": True,
            "route_readiness_field": "route_matrix[].production_gate.production_ready",
            "high_endpoints_control": True,
        },
        "route_matrix": evaluated,
        "configuration_comparison": comparisons,
        "complete_portfolio_optimization_available": not flexible_blockers,
        "complete_portfolio_blockers": [
            row["campaign_id"] for row in flexible_blockers
        ],
        "selection_policy": {
            "uncalibrated_routes_selected": False,
            "sensitivity_only_routes_selected": False,
            "objective": "minimum upper endpoint of retained compute-cost range",
            "overlapping_cost_ranges": (
                "retain every plausibly optimal route and mark cost_order_resolved=false"
            ),
            "deadline_rule": (
                "ceil(high node-hours/deadline) within the explicit route and user caps"
            ),
            "mixed_branch_rule": "independent CPU and H100 resource branches may overlap",
            "production_ready_rule": (
                "source-closed calibrated route, target-SKU measurement, high-work "
                "wall <= 168 hours, and high cost <= 10000 USD"
            ),
        },
        "nonclaims": [
            "A source-host benchmark is not a target-SKU benchmark.",
            "Ideal node-hour scaling excludes storage, retries, queueing, attestation, and contention.",
            "Spot price arithmetic is not a capacity or interruption guarantee.",
            "Sensitivity-only component arithmetic is not a complete campaign ETA.",
        ],
    }
