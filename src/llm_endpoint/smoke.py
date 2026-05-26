"""Offline and optional live smoke API shells."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from llm_endpoint.adapters import ProviderOutcome, ProviderOutcomeKind
from llm_endpoint.capabilities import DEFAULT_CAPABILITY_CATALOG, CapabilityCatalog
from llm_endpoint.config import LLMEndpointConfig, build_registry, validate_config
from llm_endpoint.invocation import InvocationPlan, InvocationRequest, invoke_plan
from llm_endpoint.results import FailureCode, TypedFailure, failure
from llm_endpoint.telemetry import (
    TelemetryEmitter,
    TelemetryEvent,
    TelemetryEventFamily,
    telemetry_event,
)

OFFLINE_SMOKE_VERSION = "v1"
LIVE_SMOKE_VERSION = "v1"
LIVE_SMOKE_SAFE_PROMPT = "Return exactly: OK"


class SmokeCheckName(StrEnum):
    """Machine-readable offline smoke checks."""

    CONFIG_VALIDATION = "config_validation"
    REGISTRY_BUILD = "registry_build"
    INVOCATION_PLANNING = "invocation_planning"
    CANDIDATE_BUDGET_SIMULATION = "candidate_budget_simulation"
    TELEMETRY_REDACTION = "telemetry_redaction"


class LiveSmokeStatus(StrEnum):
    """Typed optional live smoke outcomes."""

    SKIPPED = "skipped"
    PASSED = "passed"
    FAILED = "failed"


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


@dataclass(frozen=True, slots=True)
class LiveSmokeReport:
    """Optional live smoke result envelope with only redacted public fields."""

    ok: bool
    status: LiveSmokeStatus
    reason: str
    events: tuple[TelemetryEvent, ...]
    config_identity: str | None = None
    plan: InvocationPlan | None = None
    provider_outcome: ProviderOutcome | None = None
    failure: TypedFailure | None = None
    smoke_version: str = LIVE_SMOKE_VERSION

    def __post_init__(self) -> None:
        if self.smoke_version != LIVE_SMOKE_VERSION:
            raise ValueError("only live smoke version 'v1' is supported")
        if self.status is LiveSmokeStatus.PASSED and not self.ok:
            raise ValueError("passed live smoke reports must be ok")
        if (
            self.status is not LiveSmokeStatus.PASSED
            and self.ok
            and self.status is not LiveSmokeStatus.SKIPPED
        ):
            raise ValueError("only skipped or passed live smoke reports can be ok")


LiveProviderProbe = Callable[[InvocationPlan], ProviderOutcome | TypedFailure]


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
    budget_check = _candidate_budget_simulation_check(planned)
    checks.append(budget_check)
    if not budget_check.ok:
        _smoke_event(emitter, False, len(checks), registry.config_identity)
        return OfflineSmokeReport(
            ok=False,
            checks=tuple(checks),
            events=tuple(emitter.captured_events),
            config_identity=registry.config_identity,
            plan=planned,
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


def run_optional_live_smoke(
    *,
    config: LLMEndpointConfig,
    role: str,
    operation_ref: str,
    explicit_consent: bool,
    provider_probe: LiveProviderProbe | None = None,
    capability_catalog: CapabilityCatalog = DEFAULT_CAPABILITY_CATALOG,
) -> LiveSmokeReport:
    """Run an explicitly opted-in minimal live probe without exposing payloads or secrets.

    The module owns the boundary and reporting contract. The host owns the provider
    probe callback, credentials, and network behavior.
    """

    emitter = TelemetryEmitter()
    if not explicit_consent:
        event = _live_smoke_event(
            emitter,
            LiveSmokeStatus.SKIPPED,
            "explicit_consent_required",
            None,
        )
        return LiveSmokeReport(
            ok=True,
            status=LiveSmokeStatus.SKIPPED,
            reason="explicit_consent_required",
            events=(event,),
        )
    if provider_probe is None:
        event = _live_smoke_event(emitter, LiveSmokeStatus.SKIPPED, "provider_probe_required", None)
        return LiveSmokeReport(
            ok=True,
            status=LiveSmokeStatus.SKIPPED,
            reason="provider_probe_required",
            events=(event,),
        )

    plan_or_failure = invoke_plan(
        request=InvocationRequest(
            role=role,
            operation_ref=operation_ref,
            messages=({"role": "user", "content": LIVE_SMOKE_SAFE_PROMPT},),
            deadline_ms=_configured_deadline_ms(
                config=config,
                operation_ref=operation_ref,
                capability_catalog=capability_catalog,
            ),
            operation_invocation_id="live-smoke",
            request_metadata={"smoke": "live", "payload": "minimal"},
        ),
        config=config,
        capability_catalog=capability_catalog,
        telemetry_emitter=emitter,
    )
    if isinstance(plan_or_failure, TypedFailure):
        event = _live_smoke_event(emitter, LiveSmokeStatus.FAILED, plan_or_failure.code.value, None)
        return LiveSmokeReport(
            ok=False,
            status=LiveSmokeStatus.FAILED,
            reason=plan_or_failure.code.value,
            events=tuple(emitter.captured_events),
            failure=plan_or_failure,
        )

    try:
        probe_result = provider_probe(plan_or_failure)
    except Exception as exc:  # pragma: no cover - host probe behavior is external.
        typed_failure = failure(
            code=FailureCode.SMOKE_FAILED,
            message="live smoke provider probe raised",
            operation_invocation_id=plan_or_failure.operation_invocation_id,
            role=plan_or_failure.role,
            operation_ref=plan_or_failure.operation_ref,
            safe_context={"probe_exception": exc.__class__.__name__},
        )
        _live_smoke_event(
            emitter,
            LiveSmokeStatus.FAILED,
            typed_failure.code.value,
            plan_or_failure.config_identity,
        )
        return LiveSmokeReport(
            ok=False,
            status=LiveSmokeStatus.FAILED,
            reason=typed_failure.code.value,
            events=tuple(emitter.captured_events),
            config_identity=plan_or_failure.config_identity,
            plan=plan_or_failure,
            failure=typed_failure,
        )

    if isinstance(probe_result, TypedFailure):
        _live_smoke_event(
            emitter,
            LiveSmokeStatus.FAILED,
            probe_result.code.value,
            plan_or_failure.config_identity,
        )
        return LiveSmokeReport(
            ok=False,
            status=LiveSmokeStatus.FAILED,
            reason=probe_result.code.value,
            events=tuple(emitter.captured_events),
            config_identity=plan_or_failure.config_identity,
            plan=plan_or_failure,
            failure=probe_result,
        )
    if probe_result.kind is not ProviderOutcomeKind.SUCCESS:
        typed_failure = failure(
            code=probe_result.failure_code or FailureCode.PROVIDER_FAILURE,
            message="live smoke provider probe failed",
            operation_invocation_id=plan_or_failure.operation_invocation_id,
            role=plan_or_failure.role,
            operation_ref=plan_or_failure.operation_ref,
            endpoint_uid=probe_result.endpoint_uid,
            policy_fingerprint=plan_or_failure.policy_fingerprint,
            elapsed_ms=probe_result.elapsed_ms,
        )
        _live_smoke_event(
            emitter,
            LiveSmokeStatus.FAILED,
            typed_failure.code.value,
            plan_or_failure.config_identity,
        )
        return LiveSmokeReport(
            ok=False,
            status=LiveSmokeStatus.FAILED,
            reason=typed_failure.code.value,
            events=tuple(emitter.captured_events),
            config_identity=plan_or_failure.config_identity,
            plan=plan_or_failure,
            provider_outcome=probe_result,
            failure=typed_failure,
        )

    _live_smoke_event(
        emitter,
        LiveSmokeStatus.PASSED,
        "provider_probe_passed",
        plan_or_failure.config_identity,
    )
    return LiveSmokeReport(
        ok=True,
        status=LiveSmokeStatus.PASSED,
        reason="provider_probe_passed",
        events=tuple(emitter.captured_events),
        config_identity=plan_or_failure.config_identity,
        plan=plan_or_failure,
        provider_outcome=probe_result,
    )


def _configured_deadline_ms(
    *,
    config: LLMEndpointConfig,
    operation_ref: str,
    capability_catalog: CapabilityCatalog,
) -> int:
    report = validate_config(config, capability_catalog=capability_catalog)
    if not report.ok:
        return 1_000
    registry = build_registry(config, capability_catalog=capability_catalog)
    operation = registry.operations_by_ref.get(operation_ref)
    if operation is None:
        return 1_000
    return registry.policies_by_ref[operation.policy_ref].deadline_ms


def _candidate_budget_simulation_check(plan: InvocationPlan) -> SmokeCheck:
    remaining_ms = plan.deadline_ms
    budgets: list[str] = []
    overrides = dict(plan.effective_config.candidate_budget_overrides_ms or ())
    for candidate_index, endpoint_uid in enumerate(plan.endpoint_uids):
        candidate_budget_ms = _candidate_budget(
            plan,
            candidate_index,
            remaining_ms,
            overrides,
        )
        if candidate_budget_ms <= 0:
            return SmokeCheck(
                name=SmokeCheckName.CANDIDATE_BUDGET_SIMULATION,
                ok=False,
                message=f"candidate budget simulation failed for endpoint uid: {endpoint_uid}",
            )
        source = "override" if endpoint_uid in overrides else "base"
        budgets.append(f"{endpoint_uid}={candidate_budget_ms}:{source}")
        remaining_ms -= candidate_budget_ms
        if remaining_ms <= 0 and candidate_index < len(plan.endpoint_uids) - 1:
            return SmokeCheck(
                name=SmokeCheckName.CANDIDATE_BUDGET_SIMULATION,
                ok=False,
                message="candidate budget simulation exhausted deadline before pool end",
            )
    return SmokeCheck(
        name=SmokeCheckName.CANDIDATE_BUDGET_SIMULATION,
        ok=True,
        message="candidate budget simulation passed: " + ",".join(budgets),
    )


def _candidate_budget(
    plan: InvocationPlan,
    candidate_index: int,
    remaining_ms: int,
    candidate_budget_overrides: dict[str, int],
) -> int:
    candidate_budget_ms = _budget_for_uid(
        plan,
        plan.endpoint_uids[candidate_index],
        candidate_budget_overrides,
    )
    has_later_candidate = candidate_index < len(plan.endpoint_uids) - 1
    reserve = (
        _budget_for_uid(
            plan,
            plan.endpoint_uids[candidate_index + 1],
            candidate_budget_overrides,
        )
        if has_later_candidate and plan.effective_config.protect_last_eligible
        else 0
    )
    available_ms = max(1, remaining_ms - reserve)
    return min(candidate_budget_ms, available_ms)


def _budget_for_uid(
    plan: InvocationPlan,
    endpoint_uid: str,
    candidate_budget_overrides: dict[str, int],
) -> int:
    return candidate_budget_overrides.get(endpoint_uid, plan.effective_config.candidate_budget_ms)


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


def _live_smoke_event(
    emitter: TelemetryEmitter,
    status: LiveSmokeStatus,
    reason: str,
    config_identity: str | None,
) -> TelemetryEvent:
    return emitter.emit(
        telemetry_event(
            family=TelemetryEventFamily.SMOKE_RESULT,
            operation_invocation_id="live-smoke",
            attributes={
                "ok": str(status is not LiveSmokeStatus.FAILED).lower(),
                "status": status.value,
                "reason": reason,
                "config_identity": config_identity or "",
                "smoke_version": LIVE_SMOKE_VERSION,
            },
        )
    )
