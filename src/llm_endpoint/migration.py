"""Zero BC migration readiness helpers for direct invocation adoption."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from llm_endpoint.capabilities import DEFAULT_CAPABILITY_CATALOG, CapabilityCatalog
from llm_endpoint.config import LLMEndpointConfig, Registry
from llm_endpoint.invocation import InvocationPlan, InvocationRequest, invoke_plan
from llm_endpoint.results import FailureCode, TypedFailure, failure
from llm_endpoint.telemetry import TelemetryEmitter

MIGRATION_READINESS_VERSION = "v1"

FORBIDDEN_LEGACY_FIELDS = frozenset(
    {
        "api_key",
        "base_url",
        "deployment",
        "legacy_provider",
        "model",
        "provider",
        "raw_provider_tuple",
    }
)


@dataclass(frozen=True, slots=True)
class DirectMigrationRequest:
    """Direct-API migration input; legacy facade fields are rejected, not translated."""

    request: InvocationRequest
    source_callsite: str
    legacy_fields: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DirectMigrationReport:
    """Readiness report for moving a call site to the canonical invocation facade."""

    ok: bool
    source_callsite: str
    diagnostics: tuple[str, ...]
    plan: InvocationPlan | None = None
    failure: TypedFailure | None = None
    migration_version: str = MIGRATION_READINESS_VERSION

    def __post_init__(self) -> None:
        if self.migration_version != MIGRATION_READINESS_VERSION:
            raise ValueError("only migration readiness version 'v1' is supported")
        if self.ok == (self.plan is None):
            raise ValueError("successful migration reports require a plan")
        if self.ok and self.failure is not None:
            raise ValueError("successful migration reports cannot carry a failure")
        if not self.ok and self.failure is None:
            raise ValueError("failed migration reports require a typed failure")


def assess_direct_migration(
    *,
    migration_request: DirectMigrationRequest,
    config: LLMEndpointConfig | None = None,
    registry: Registry | None = None,
    capability_catalog: CapabilityCatalog = DEFAULT_CAPABILITY_CATALOG,
    telemetry_emitter: TelemetryEmitter | None = None,
) -> DirectMigrationReport:
    """Validate a call-site migration by delegating only to the canonical direct API."""

    legacy_failure = _legacy_field_failure(migration_request)
    if legacy_failure is not None:
        return DirectMigrationReport(
            ok=False,
            source_callsite=migration_request.source_callsite,
            diagnostics=("remove_legacy_provider_tuple", "use_invocation_request"),
            failure=legacy_failure,
        )

    result = invoke_plan(
        request=migration_request.request,
        config=config,
        registry=registry,
        capability_catalog=capability_catalog,
        telemetry_emitter=telemetry_emitter,
    )
    if isinstance(result, TypedFailure):
        return DirectMigrationReport(
            ok=False,
            source_callsite=migration_request.source_callsite,
            diagnostics=("canonical_invocation_not_ready",),
            failure=result,
        )

    return DirectMigrationReport(
        ok=True,
        source_callsite=migration_request.source_callsite,
        diagnostics=("canonical_direct_api_ready", "no_compatibility_facade"),
        plan=result,
    )


def _legacy_field_failure(migration_request: DirectMigrationRequest) -> TypedFailure | None:
    legacy_keys = frozenset(migration_request.legacy_fields)
    forbidden_keys = tuple(sorted(legacy_keys & FORBIDDEN_LEGACY_FIELDS))
    if not forbidden_keys:
        return None

    request = migration_request.request
    return failure(
        code=FailureCode.UNSUPPORTED_RUNTIME_KNOB,
        message="legacy provider fields are prohibited under Zero BC migration",
        operation_invocation_id=request.operation_invocation_id or "migration-readiness",
        role=request.role or None,
        operation_ref=request.operation_ref or None,
        remediation_hint="Move the call site to InvocationRequest and host config.",
        safe_context={
            "source_callsite": migration_request.source_callsite,
            "legacy_field_count": str(len(forbidden_keys)),
        },
    )
