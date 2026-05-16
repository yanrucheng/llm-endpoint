"""Deterministic role-health service for operator readiness."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from llm_endpoint.adapters import ProviderAdapter
from llm_endpoint.config import ProviderFormat, Registry
from llm_endpoint.telemetry import TelemetryEvent, TelemetryEventFamily, telemetry_event

ROLE_HEALTH_VERSION = "v1"


class RoleHealthState(StrEnum):
    """Public role-health states returned by the operator health service."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    FALLBACK_ONLY = "fallback_only"
    MISSING_SECRET = "missing_secret"
    FAILING_SMOKE = "failing_smoke"
    UNCERTIFIED = "uncertified"
    SUPPRESSED = "suppressed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class EndpointHealth:
    """Deterministic health state for one role candidate endpoint."""

    endpoint_uid: str
    state: RoleHealthState
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoleHealthReport:
    """Role-level health report with redacted telemetry."""

    role: str
    state: RoleHealthState
    endpoint_health: tuple[EndpointHealth, ...]
    reasons: tuple[str, ...]
    telemetry: tuple[TelemetryEvent, ...]
    health_version: str = ROLE_HEALTH_VERSION

    def __post_init__(self) -> None:
        if self.health_version != ROLE_HEALTH_VERSION:
            raise ValueError("only role-health version 'v1' is supported")


def evaluate_role_health(
    *,
    registry: Registry,
    role: str,
    adapters: Mapping[ProviderFormat | str, ProviderAdapter],
    operation_invocation_id: str = "role-health",
    suppressed_endpoint_reasons: Mapping[str, str] | None = None,
    missing_secret_refs: frozenset[str] = frozenset(),
    failing_smoke_endpoint_uids: frozenset[str] = frozenset(),
    uncertified_endpoint_uids: frozenset[str] = frozenset(),
) -> RoleHealthReport:
    """Evaluate role health without network calls, secrets, or legacy compatibility paths."""

    suppressed = suppressed_endpoint_reasons or {}
    try:
        resolved_role = registry.resolve_role(role)
    except KeyError:
        return _report(
            role=role,
            state=RoleHealthState.UNAVAILABLE,
            endpoint_health=(),
            reasons=("unknown_role",),
            operation_invocation_id=operation_invocation_id,
        )

    endpoint_health = tuple(
        _endpoint_health(
            registry=registry,
            endpoint_uid=endpoint_uid,
            adapters=adapters,
            suppressed_endpoint_reasons=suppressed,
            missing_secret_refs=missing_secret_refs,
            failing_smoke_endpoint_uids=failing_smoke_endpoint_uids,
            uncertified_endpoint_uids=uncertified_endpoint_uids,
        )
        for endpoint_uid in resolved_role.endpoint_uids
    )
    state = _role_state(endpoint_health)
    reasons = _role_reasons(endpoint_health)
    return _report(
        role=role,
        state=state,
        endpoint_health=endpoint_health,
        reasons=reasons,
        operation_invocation_id=operation_invocation_id,
    )


def _endpoint_health(
    *,
    registry: Registry,
    endpoint_uid: str,
    adapters: Mapping[ProviderFormat | str, ProviderAdapter],
    suppressed_endpoint_reasons: Mapping[str, str],
    missing_secret_refs: frozenset[str],
    failing_smoke_endpoint_uids: frozenset[str],
    uncertified_endpoint_uids: frozenset[str],
) -> EndpointHealth:
    endpoint = registry.endpoints_by_uid[endpoint_uid]
    reasons: list[str] = []
    state = RoleHealthState.AVAILABLE

    if endpoint.provider_format not in adapters and endpoint.provider_format.value not in adapters:
        reasons.append("adapter_unregistered")
        state = RoleHealthState.UNAVAILABLE
    if endpoint.credential_ref in missing_secret_refs:
        reasons.append("missing_secret")
        state = _more_severe(state, RoleHealthState.MISSING_SECRET)
    if endpoint_uid in failing_smoke_endpoint_uids:
        reasons.append("failing_smoke")
        state = _more_severe(state, RoleHealthState.FAILING_SMOKE)
    if endpoint_uid in uncertified_endpoint_uids:
        reasons.append("uncertified")
        state = _more_severe(state, RoleHealthState.UNCERTIFIED)
    if endpoint_uid in suppressed_endpoint_reasons:
        reasons.append(f"suppressed:{suppressed_endpoint_reasons[endpoint_uid]}")
        state = _more_severe(state, RoleHealthState.SUPPRESSED)

    return EndpointHealth(
        endpoint_uid=endpoint_uid,
        state=state,
        reasons=tuple(sorted(reasons)),
    )


def _role_state(endpoint_health: tuple[EndpointHealth, ...]) -> RoleHealthState:
    if not endpoint_health:
        return RoleHealthState.UNAVAILABLE

    states = tuple(endpoint.state for endpoint in endpoint_health)
    available_count = states.count(RoleHealthState.AVAILABLE)
    if available_count == len(states):
        return RoleHealthState.AVAILABLE
    if available_count > 0:
        if available_count == 1 and endpoint_health[-1].state is RoleHealthState.AVAILABLE:
            return RoleHealthState.FALLBACK_ONLY
        return RoleHealthState.DEGRADED

    for candidate in (
        RoleHealthState.MISSING_SECRET,
        RoleHealthState.FAILING_SMOKE,
        RoleHealthState.UNCERTIFIED,
        RoleHealthState.SUPPRESSED,
    ):
        if all(state is candidate for state in states):
            return candidate
    return RoleHealthState.UNAVAILABLE


def _role_reasons(endpoint_health: tuple[EndpointHealth, ...]) -> tuple[str, ...]:
    reasons = {
        f"{endpoint.endpoint_uid}:{reason}"
        for endpoint in endpoint_health
        for reason in endpoint.reasons
    }
    return tuple(sorted(reasons))


def _more_severe(current: RoleHealthState, candidate: RoleHealthState) -> RoleHealthState:
    severity = {
        RoleHealthState.AVAILABLE: 0,
        RoleHealthState.SUPPRESSED: 1,
        RoleHealthState.UNCERTIFIED: 2,
        RoleHealthState.FAILING_SMOKE: 3,
        RoleHealthState.MISSING_SECRET: 4,
        RoleHealthState.UNAVAILABLE: 5,
    }
    return candidate if severity[candidate] > severity[current] else current


def _report(
    *,
    role: str,
    state: RoleHealthState,
    endpoint_health: tuple[EndpointHealth, ...],
    reasons: tuple[str, ...],
    operation_invocation_id: str,
) -> RoleHealthReport:
    event = telemetry_event(
        family=TelemetryEventFamily.ROLE_HEALTH,
        operation_invocation_id=operation_invocation_id,
        role=role,
        attributes={
            "state": state.value,
            "endpoint_count": str(len(endpoint_health)),
            "reason_count": str(len(reasons)),
            "role_health_version": ROLE_HEALTH_VERSION,
        },
    )
    return RoleHealthReport(
        role=role,
        state=state,
        endpoint_health=endpoint_health,
        reasons=reasons,
        telemetry=(event,),
    )
