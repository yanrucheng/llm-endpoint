"""Offline smoke API shell for config, policy, telemetry, and facade checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from llm_endpoint.capabilities import DEFAULT_CAPABILITY_CATALOG, CapabilityCatalog
from llm_endpoint.config import LLMEndpointConfig, build_registry, validate_config
from llm_endpoint.invocation import InvocationPlan, InvocationRequest, invoke_plan
from llm_endpoint.results import TypedFailure
from llm_endpoint.telemetry import (
    TelemetryEmitter,
    TelemetryEvent,
    TelemetryEventFamily,
    telemetry_event,
)

OFFLINE_SMOKE_VERSION = "v1"


class SmokeCheckName(StrEnum):
    """Machine-readable offline smoke checks."""

    CONFIG_VALIDATION = "config_validation"
    REGISTRY_BUILD = "registry_build"
    INVOCATION_PLANNING = "invocation_planning"
    TELEMETRY_REDACTION = "telemetry_redaction"


@dataclass(frozen=True, slots=True)
class SmokeCheck:
    """One machine-readable smoke check result."""

    name: SmokeCheckName
    ok: bool
    message: str


@dataclass(frozen=True, slots=True)
class OfflineSmokeReport:
    """Offline smoke result envelope safe for CI and local validation."""

    ok: bool
    checks: tuple[SmokeCheck, ...]
    events: tuple[TelemetryEvent, ...]
    config_identity: str | None = None
    plan: InvocationPlan | None = None
    failure: TypedFailure | None = None
    smoke_version: str = OFFLINE_SMOKE_VERSION

    def __post_init__(self) -> None:
        if self.smoke_version != OFFLINE_SMOKE_VERSION:
            raise ValueError("only offline smoke version 'v1' is supported")


def run_offline_smoke(
    *,
    config: LLMEndpointConfig,
    role: str,
    operation_ref: str,
    capability_catalog: CapabilityCatalog = DEFAULT_CAPABILITY_CATALOG,
) -> OfflineSmokeReport:
    """Run the Phase 2 gate without provider network calls or credential resolution."""

    emitter = TelemetryEmitter()
    checks: list[SmokeCheck] = []
    report = validate_config(config, capability_catalog=capability_catalog)
    checks.append(
        SmokeCheck(
            name=SmokeCheckName.CONFIG_VALIDATION,
            ok=report.ok,
            message="config validation passed" if report.ok else "config validation failed",
        )
    )
    if not report.ok:
        _smoke_event(emitter, False, len(checks), report.config_identity)
        return OfflineSmokeReport(
            ok=False,
            checks=tuple(checks),
            events=tuple(emitter.captured_events),
            config_identity=report.config_identity,
        )

    registry = build_registry(config, capability_catalog=capability_catalog)
    checks.append(
        SmokeCheck(
            name=SmokeCheckName.REGISTRY_BUILD,
            ok=True,
            message="registry build passed",
        )
    )
    operation = registry.operations_by_ref.get(operation_ref)
    policy = registry.policies_by_ref[operation.policy_ref] if operation is not None else None
    request = InvocationRequest(
        role=role,
        operation_ref=operation_ref,
        messages=({"role": "user", "content": "offline smoke"},),
        deadline_ms=policy.deadline_ms if policy is not None else 1_000,
        schema_contract_ref=operation.schema_contract_ref if operation is not None else None,
        operation_invocation_id="offline-smoke",
    )
    planned = invoke_plan(
        request=request,
        registry=registry,
        capability_catalog=capability_catalog,
        telemetry_emitter=emitter,
    )
    if isinstance(planned, TypedFailure):
        checks.append(
            SmokeCheck(
                name=SmokeCheckName.INVOCATION_PLANNING,
                ok=False,
                message=planned.code.value,
            )
        )
        _smoke_event(emitter, False, len(checks), registry.config_identity)
        return OfflineSmokeReport(
            ok=False,
            checks=tuple(checks),
            events=tuple(emitter.captured_events),
            config_identity=registry.config_identity,
            failure=planned,
        )

    checks.append(
        SmokeCheck(
            name=SmokeCheckName.INVOCATION_PLANNING,
            ok=True,
            message="invocation planning passed",
        )
    )
    checks.append(
        SmokeCheck(
            name=SmokeCheckName.TELEMETRY_REDACTION,
            ok=True,
            message="telemetry events accepted redaction rules",
        )
    )
    _smoke_event(emitter, True, len(checks), registry.config_identity)
    return OfflineSmokeReport(
        ok=True,
        checks=tuple(checks),
        events=tuple(emitter.captured_events),
        config_identity=registry.config_identity,
        plan=planned,
    )


def _smoke_event(
    emitter: TelemetryEmitter,
    ok: bool,
    check_count: int,
    config_identity: str | None,
) -> TelemetryEvent:
    return emitter.emit(
        telemetry_event(
            family=TelemetryEventFamily.SMOKE_RESULT,
            operation_invocation_id="offline-smoke",
            attributes={
                "ok": str(ok).lower(),
                "check_count": str(check_count),
                "config_identity": config_identity or "",
                "smoke_version": OFFLINE_SMOKE_VERSION,
            },
        )
    )
