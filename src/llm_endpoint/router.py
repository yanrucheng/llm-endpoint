"""Deadline-aware ordered pool routing for provider execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import overload

from llm_endpoint.adapters import (
    AdapterInvocationPlan,
    ProviderAdapter,
    ProviderOutcome,
    execute_provider_attempt,
)
from llm_endpoint.callbacks import (
    SchemaContract,
    SchemaResolutionStatus,
    SchemaResolver,
    SecretResolver,
)
from llm_endpoint.config import ProviderFormat, Registry, RetryClass, StructuredOutputMode
from llm_endpoint.invocation import InvocationPlan
from llm_endpoint.normalization import normalize_provider_outcome
from llm_endpoint.results import (
    FailureCode,
    PlainTextResult,
    StructuredResult,
    TerminalResult,
    TypedFailure,
    failure,
)
from llm_endpoint.structured import (
    STRUCTURED_OUTPUT_PIPELINE_VERSION,
    StructuredOutputContext,
    normalize_structured_provider_outcome,
)
from llm_endpoint.telemetry import (
    TelemetryEmitter,
    TelemetryEvent,
    TelemetryEventFamily,
    telemetry_event,
)

ROUTER_VERSION = "v1"


class AttemptStatus(StrEnum):
    """Safe attempt states emitted by the router."""

    SKIPPED_SUPPRESSED = "skipped_suppressed"
    ATTEMPTED = "attempted"
    SUCCESS = "success"
    RETRYABLE_FAILURE = "retryable_failure"
    TERMINAL_FAILURE = "terminal_failure"
    CANCELLED = "llm.input.cancelled"
    LATE_RESPONSE_DISCARDED = "llm.invocation.late_response_discarded"


@dataclass(frozen=True, slots=True)
class AttemptTrace:
    """Redacted record for one candidate skip or provider attempt."""

    trace_id: str
    endpoint_uid: str
    status: AttemptStatus
    candidate_budget_ms: int | None = None
    elapsed_ms: int | None = None
    failure_code: FailureCode | None = None
    skip_reason: str | None = None
    suppression_protected: bool = False


@dataclass(frozen=True, slots=True)
class PoolRouteResult:
    """Terminal routing output with redacted traces and captured telemetry."""

    terminal_result: TerminalResult
    attempt_traces: tuple[AttemptTrace, ...]
    telemetry: tuple[TelemetryEvent, ...]
    router_version: str = ROUTER_VERSION

    def __post_init__(self) -> None:
        if self.router_version != ROUTER_VERSION:
            raise ValueError("only router version 'v1' is supported")


def route_invocation(
    *,
    plan: InvocationPlan,
    registry: Registry,
    adapters: Mapping[ProviderFormat | str, ProviderAdapter],
    secret_resolver: SecretResolver | None = None,
    schema_resolver: SchemaResolver | None = None,
    suppressed_endpoint_reasons: Mapping[str, str] | None = None,
    telemetry_emitter: TelemetryEmitter | None = None,
) -> PoolRouteResult:
    """Execute an invocation plan through an ordered endpoint pool."""

    emitter = telemetry_emitter or TelemetryEmitter()
    schema_or_failure = _resolve_schema(plan, schema_resolver)
    if isinstance(schema_or_failure, TypedFailure):
        emitter.emit(_failure_event(schema_or_failure))
        return _route_result(schema_or_failure, [], emitter)

    suppressed = suppressed_endpoint_reasons or {}
    traces: list[AttemptTrace] = []
    attempted = 0
    elapsed_total_ms = 0
    last_retryable_failure: TypedFailure | None = None

    for candidate_index, endpoint_uid in enumerate(plan.endpoint_uids):
        if _is_cancelled(plan):
            terminal = _cancelled_failure(
                plan,
                elapsed_total_ms=elapsed_total_ms,
                schema=schema_or_failure,
            )
            emitter.emit(_cancellation_event(terminal))
            emitter.emit(_failure_event(terminal))
            return _route_result(terminal, traces, emitter)

        if attempted >= plan.effective_config.max_attempts:
            break

        if _should_skip_suppressed(endpoint_uid, candidate_index, plan.endpoint_uids, suppressed):
            trace = _skip_trace(plan, endpoint_uid, candidate_index, suppressed[endpoint_uid])
            traces.append(trace)
            emitter.emit(_suppression_event(plan, trace))
            continue

        endpoint = registry.endpoints_by_uid[endpoint_uid]
        remaining_ms = plan.deadline_ms - elapsed_total_ms
        if remaining_ms <= 0:
            terminal = failure(
                code=FailureCode.DEADLINE_EXCEEDED,
                message="deadline elapsed before next provider attempt",
                operation_invocation_id=plan.operation_invocation_id,
                role=plan.role,
                operation_ref=plan.operation_ref,
                endpoint_uid=endpoint_uid,
                schema_contract_ref=plan.schema_contract_ref,
                schema_fingerprint=(
                    schema_or_failure.fingerprint if schema_or_failure is not None else None
                ),
                policy_fingerprint=plan.policy_fingerprint,
                elapsed_ms=elapsed_total_ms,
            )
            emitter.emit(_deadline_event(terminal))
            emitter.emit(_failure_event(terminal))
            return _route_result(terminal, traces, emitter)

        protected = endpoint_uid in suppressed
        candidate_budget_ms = _candidate_budget(plan, candidate_index, remaining_ms)
        attempt_trace_id = _trace_id(plan.operation_invocation_id, endpoint_uid, candidate_index)
        attempt_plan = AdapterInvocationPlan(
            endpoint_uid=endpoint.uid,
            provider_format=endpoint.provider_format,
            model_family=endpoint.model_family,
            model=endpoint.model,
            operation_invocation_id=plan.operation_invocation_id,
            messages=plan.messages,
            deadline_ms=plan.deadline_ms,
            candidate_budget_ms=candidate_budget_ms,
            schema_mode=plan.effective_config.structured_output_mode,
            credential_ref=endpoint.credential_ref,
            schema_contract_ref=plan.schema_contract_ref,
            policy_fingerprint=plan.policy_fingerprint,
            request_metadata=plan.request_metadata,
        )
        adapter = adapters.get(endpoint.provider_format) or adapters.get(
            endpoint.provider_format.value
        )
        if adapter is None:
            terminal = failure(
                code=FailureCode.UNSUPPORTED_PROVIDER_FORMAT,
                message="no provider adapter registered for endpoint provider_format",
                operation_invocation_id=plan.operation_invocation_id,
                role=plan.role,
                operation_ref=plan.operation_ref,
                endpoint_uid=endpoint_uid,
                schema_contract_ref=plan.schema_contract_ref,
                schema_fingerprint=(
                    schema_or_failure.fingerprint if schema_or_failure is not None else None
                ),
                policy_fingerprint=plan.policy_fingerprint,
            )
            traces.append(
                _attempt_trace(
                    trace_id=attempt_trace_id,
                    endpoint_uid=endpoint_uid,
                    candidate_budget_ms=candidate_budget_ms,
                    terminal=terminal,
                    suppression_protected=protected,
                )
            )
            emitter.emit(_failure_event(terminal))
            return _route_result(terminal, traces, emitter)

        attempted += 1
        attempt_output = execute_provider_attempt(
            plan=attempt_plan,
            adapter=adapter,
            secret_resolver=secret_resolver,
        )
        attempt_terminal: TerminalResult = _terminal_result(
            plan,
            attempt_output,
            attempt_trace_id,
            schema_or_failure,
        )
        elapsed_ms = _elapsed_ms(attempt_output, attempt_terminal)
        elapsed_total_ms += elapsed_ms

        if _is_cancelled(plan):
            cancelled_terminal = _cancelled_failure(
                plan,
                endpoint_uid=endpoint_uid,
                elapsed_total_ms=elapsed_total_ms,
                attempt_trace_id=attempt_trace_id,
                schema=schema_or_failure,
            )
            trace = _attempt_trace(
                trace_id=attempt_trace_id,
                endpoint_uid=endpoint_uid,
                candidate_budget_ms=candidate_budget_ms,
                terminal=cancelled_terminal,
                suppression_protected=protected,
            )
            traces.append(trace)
            emitter.emit(_attempt_event(plan, trace, attempt_output))
            emitter.emit(_cancellation_event(cancelled_terminal))
            emitter.emit(_late_response_event(plan, trace, attempt_output))
            emitter.emit(_failure_event(cancelled_terminal))
            return _route_result(cancelled_terminal, traces, emitter)

        if elapsed_ms > candidate_budget_ms or elapsed_total_ms > plan.deadline_ms:
            late_terminal = _late_response_failure(
                plan,
                endpoint_uid=endpoint_uid,
                elapsed_total_ms=elapsed_total_ms,
                attempt_trace_id=attempt_trace_id,
                candidate_budget_ms=candidate_budget_ms,
                schema=schema_or_failure,
            )
            trace = _attempt_trace(
                trace_id=attempt_trace_id,
                endpoint_uid=endpoint_uid,
                candidate_budget_ms=candidate_budget_ms,
                terminal=late_terminal,
                suppression_protected=protected,
            )
            traces.append(trace)
            emitter.emit(_attempt_event(plan, trace, attempt_output))
            emitter.emit(_late_response_event(plan, trace, attempt_output))
            emitter.emit(_failure_event(late_terminal))
            return _route_result(late_terminal, traces, emitter)

        trace = _attempt_trace(
            trace_id=attempt_trace_id,
            endpoint_uid=endpoint_uid,
            candidate_budget_ms=candidate_budget_ms,
            terminal=attempt_terminal,
            suppression_protected=protected,
        )
        traces.append(trace)
        emitter.emit(_attempt_event(plan, trace, attempt_output))

        if isinstance(attempt_terminal, (PlainTextResult, StructuredResult)):
            success_terminal = attempt_terminal
            emitter.emit(_success_event(plan, success_terminal, attempt_output))
            return _route_result(success_terminal, traces, emitter)

        if _is_failover_retryable(plan, attempt_terminal):
            last_retryable_failure = attempt_terminal
            if _has_failover_candidate(plan, attempted, candidate_index):
                continue
            break

        emitter.emit(_failure_event(attempt_terminal))
        return _route_result(attempt_terminal, traces, emitter)

    terminal: TypedFailure = _pool_exhausted(
        plan,
        traces,
        last_retryable_failure,
        schema=schema_or_failure,
    )
    emitter.emit(
        telemetry_event(
            family=TelemetryEventFamily.POOL_EXHAUSTED,
            operation_invocation_id=plan.operation_invocation_id,
            role=plan.role,
            operation_ref=plan.operation_ref,
            schema_contract_ref=terminal.context.schema_contract_ref,
            schema_fingerprint=terminal.context.schema_fingerprint,
            schema_resolution_status=terminal.context.schema_resolution_status,
            policy_fingerprint=plan.policy_fingerprint,
            failure_class=terminal.failure_class,
            attributes={
                "attempt_count": str(_attempt_count(traces)),
                "skipped_count": str(_skipped_count(traces)),
                "router_version": ROUTER_VERSION,
            },
        )
    )
    return _route_result(terminal, traces, emitter)


def _should_skip_suppressed(
    endpoint_uid: str,
    candidate_index: int,
    endpoint_uids: tuple[str, ...],
    suppressed: Mapping[str, str],
) -> bool:
    if endpoint_uid not in suppressed:
        return False
    return candidate_index < len(endpoint_uids) - 1


def _candidate_budget(plan: InvocationPlan, candidate_index: int, remaining_ms: int) -> int:
    has_later_candidate = candidate_index < len(plan.endpoint_uids) - 1
    reserve = (
        plan.effective_config.candidate_budget_ms
        if has_later_candidate and plan.effective_config.protect_last_eligible
        else 0
    )
    available_ms = max(1, remaining_ms - reserve)
    return min(plan.effective_config.candidate_budget_ms, available_ms)


def _terminal_result(
    plan: InvocationPlan,
    attempt_output: ProviderOutcome | TypedFailure,
    attempt_trace_id: str,
    schema: SchemaContract | None,
) -> TerminalResult:
    if isinstance(attempt_output, TypedFailure):
        return _with_schema_identity(attempt_output, schema)
    assert isinstance(attempt_output, ProviderOutcome)
    if plan.effective_config.structured_output_mode is not StructuredOutputMode.NONE:
        if schema is None:
            return failure(
                code=FailureCode.MISSING_SCHEMA_CONTRACT,
                message=(
                    "structured-output invocation requires resolved schema before normalization"
                ),
                operation_invocation_id=plan.operation_invocation_id,
                role=plan.role,
                operation_ref=plan.operation_ref,
                schema_contract_ref=plan.schema_contract_ref,
                policy_fingerprint=plan.policy_fingerprint,
                attempt_trace_id=attempt_trace_id,
            )
        return normalize_structured_provider_outcome(
            attempt_output,
            context=StructuredOutputContext(
                operation_invocation_id=plan.operation_invocation_id,
                role=plan.role,
                operation_ref=plan.operation_ref,
                endpoint_uid=attempt_output.endpoint_uid,
                policy_fingerprint=plan.policy_fingerprint,
                elapsed_ms=attempt_output.elapsed_ms,
                attempt_trace_id=attempt_trace_id,
                schema=schema,
                mode=plan.effective_config.structured_output_mode,
            ),
        )

    terminal = normalize_provider_outcome(
        attempt_output,
        operation_invocation_id=plan.operation_invocation_id,
        role=plan.role,
        operation_ref=plan.operation_ref,
        policy_fingerprint=plan.policy_fingerprint,
        attempt_trace_id=attempt_trace_id,
        plain_text_allowed=True,
    )
    return _with_schema_identity(terminal, schema)


def _resolve_schema(
    plan: InvocationPlan,
    schema_resolver: SchemaResolver | None,
) -> SchemaContract | None | TypedFailure:
    if plan.effective_config.structured_output_mode is StructuredOutputMode.NONE:
        return None
    if not plan.schema_contract_ref:
        return failure(
            code=FailureCode.MISSING_SCHEMA_CONTRACT,
            message="structured-output invocation requires a schema_contract_ref",
            operation_invocation_id=plan.operation_invocation_id,
            role=plan.role,
            operation_ref=plan.operation_ref,
            schema_contract_ref=plan.schema_contract_ref,
            policy_fingerprint=plan.policy_fingerprint,
        )
    if schema_resolver is None:
        return failure(
            code=FailureCode.UNKNOWN_SCHEMA_CONTRACT,
            message="schema resolver is required for structured-output invocation",
            operation_invocation_id=plan.operation_invocation_id,
            role=plan.role,
            operation_ref=plan.operation_ref,
            schema_contract_ref=plan.schema_contract_ref,
            schema_resolution_status=SchemaResolutionStatus.NOT_FOUND.value,
            policy_fingerprint=plan.policy_fingerprint,
            safe_context={"schema_ref": plan.schema_contract_ref},
        )
    try:
        resolution = schema_resolver(plan.schema_contract_ref)
    except Exception as exc:  # pragma: no cover - callback implementation is host-owned.
        return failure(
            code=FailureCode.UNKNOWN_SCHEMA_CONTRACT,
            message="schema resolver raised during schema resolution",
            operation_invocation_id=plan.operation_invocation_id,
            role=plan.role,
            operation_ref=plan.operation_ref,
            schema_contract_ref=plan.schema_contract_ref,
            schema_resolution_status=SchemaResolutionStatus.FAILED.value,
            policy_fingerprint=plan.policy_fingerprint,
            safe_context={
                "schema_ref": plan.schema_contract_ref,
                "resolver_exception": exc.__class__.__name__,
            },
        )
    if resolution.ref != plan.schema_contract_ref:
        return failure(
            code=FailureCode.UNKNOWN_SCHEMA_CONTRACT,
            message="schema resolver returned a mismatched ref",
            operation_invocation_id=plan.operation_invocation_id,
            role=plan.role,
            operation_ref=plan.operation_ref,
            schema_contract_ref=plan.schema_contract_ref,
            schema_fingerprint=(
                resolution.schema.fingerprint if resolution.schema is not None else None
            ),
            schema_resolution_status=resolution.status.value,
            policy_fingerprint=plan.policy_fingerprint,
            safe_context={
                "expected_schema_ref": plan.schema_contract_ref,
                "actual_schema_ref": resolution.ref,
            },
        )
    if resolution.status is not SchemaResolutionStatus.RESOLVED:
        return resolution.to_failure(
            operation_invocation_id=plan.operation_invocation_id,
            operation_ref=plan.operation_ref,
        )
    if resolution.schema is None:
        return failure(
            code=FailureCode.UNKNOWN_SCHEMA_CONTRACT,
            message="schema resolver returned resolved status without a schema",
            operation_invocation_id=plan.operation_invocation_id,
            role=plan.role,
            operation_ref=plan.operation_ref,
            schema_contract_ref=plan.schema_contract_ref,
            schema_resolution_status=SchemaResolutionStatus.RESOLVED.value,
            policy_fingerprint=plan.policy_fingerprint,
            safe_context={"schema_ref": plan.schema_contract_ref},
        )
    return resolution.schema


def _is_failover_retryable(
    plan: InvocationPlan,
    terminal: TypedFailure,
) -> bool:
    return (
        terminal.is_retryable
        and plan.effective_config.retry_class == RetryClass.RETRYABLE_AVAILABILITY_ONLY.value
    )


def _has_failover_candidate(
    plan: InvocationPlan,
    attempted: int,
    candidate_index: int,
) -> bool:
    if attempted >= plan.effective_config.max_attempts:
        return False
    return candidate_index < len(plan.endpoint_uids) - 1


def _is_cancelled(plan: InvocationPlan) -> bool:
    token = plan.cancellation_token
    if token is None:
        return False
    return token.is_cancelled()


def _cancelled_failure(
    plan: InvocationPlan,
    *,
    elapsed_total_ms: int,
    endpoint_uid: str | None = None,
    attempt_trace_id: str | None = None,
    schema: SchemaContract | None = None,
) -> TypedFailure:
    return failure(
        code=FailureCode.CANCELLED,
        message="caller cancelled the invocation",
        operation_invocation_id=plan.operation_invocation_id,
        role=plan.role,
        operation_ref=plan.operation_ref,
        endpoint_uid=endpoint_uid,
        schema_contract_ref=plan.schema_contract_ref,
        schema_fingerprint=schema.fingerprint if schema is not None else None,
        policy_fingerprint=plan.policy_fingerprint,
        elapsed_ms=elapsed_total_ms,
        attempt_trace_id=attempt_trace_id,
    )


def _late_response_failure(
    plan: InvocationPlan,
    *,
    endpoint_uid: str,
    elapsed_total_ms: int,
    attempt_trace_id: str,
    candidate_budget_ms: int,
    schema: SchemaContract | None = None,
) -> TypedFailure:
    return failure(
        code=FailureCode.LATE_RESPONSE_DISCARDED,
        message="provider response arrived after the local deadline and was discarded",
        operation_invocation_id=plan.operation_invocation_id,
        role=plan.role,
        operation_ref=plan.operation_ref,
        endpoint_uid=endpoint_uid,
        schema_contract_ref=plan.schema_contract_ref,
        schema_fingerprint=schema.fingerprint if schema is not None else None,
        policy_fingerprint=plan.policy_fingerprint,
        elapsed_ms=elapsed_total_ms,
        attempt_trace_id=attempt_trace_id,
        safe_context={
            "candidate_budget_ms": str(candidate_budget_ms),
            "deadline_ms": str(plan.deadline_ms),
        },
    )


def _pool_exhausted(
    plan: InvocationPlan,
    traces: list[AttemptTrace],
    last_retryable_failure: TypedFailure | None,
    *,
    schema: SchemaContract | None,
) -> TypedFailure:
    context = {
        "attempt_count": str(_attempt_count(traces)),
        "skipped_count": str(_skipped_count(traces)),
    }
    if last_retryable_failure is not None:
        context["last_retryable_failure"] = last_retryable_failure.code.value
    return failure(
        code=FailureCode.POOL_EXHAUSTED,
        message="endpoint pool exhausted before a successful provider outcome",
        operation_invocation_id=plan.operation_invocation_id,
        role=plan.role,
        operation_ref=plan.operation_ref,
        schema_contract_ref=plan.schema_contract_ref,
        schema_fingerprint=schema.fingerprint if schema is not None else None,
        policy_fingerprint=plan.policy_fingerprint,
        safe_context=context,
    )


def _skip_trace(
    plan: InvocationPlan,
    endpoint_uid: str,
    candidate_index: int,
    reason: str,
) -> AttemptTrace:
    return AttemptTrace(
        trace_id=_trace_id(plan.operation_invocation_id, endpoint_uid, candidate_index),
        endpoint_uid=endpoint_uid,
        status=AttemptStatus.SKIPPED_SUPPRESSED,
        skip_reason=reason,
    )


def _attempt_trace(
    *,
    trace_id: str,
    endpoint_uid: str,
    candidate_budget_ms: int,
    terminal: TerminalResult,
    suppression_protected: bool,
) -> AttemptTrace:
    if isinstance(terminal, TypedFailure):
        status = _failure_attempt_status(terminal)
        return AttemptTrace(
            trace_id=trace_id,
            endpoint_uid=endpoint_uid,
            status=status,
            candidate_budget_ms=candidate_budget_ms,
            elapsed_ms=terminal.context.elapsed_ms,
            failure_code=terminal.code,
            suppression_protected=suppression_protected,
        )
    if isinstance(terminal, (PlainTextResult, StructuredResult)):
        return AttemptTrace(
            trace_id=trace_id,
            endpoint_uid=endpoint_uid,
            status=AttemptStatus.SUCCESS,
            candidate_budget_ms=candidate_budget_ms,
            elapsed_ms=terminal.elapsed_ms,
            suppression_protected=suppression_protected,
        )
    raise TypeError("unknown terminal result type")


def _failure_attempt_status(terminal: TypedFailure) -> AttemptStatus:
    if terminal.code is FailureCode.CANCELLED:
        return AttemptStatus.CANCELLED
    if terminal.code is FailureCode.LATE_RESPONSE_DISCARDED:
        return AttemptStatus.LATE_RESPONSE_DISCARDED
    if terminal.is_retryable:
        return AttemptStatus.RETRYABLE_FAILURE
    return AttemptStatus.TERMINAL_FAILURE


def _attempt_event(
    plan: InvocationPlan,
    trace: AttemptTrace,
    attempt_output: ProviderOutcome | TypedFailure,
) -> TelemetryEvent:
    token_usage = (
        attempt_output.token_usage if isinstance(attempt_output, ProviderOutcome) else None
    )
    return telemetry_event(
        family=TelemetryEventFamily.POOL_ATTEMPT,
        operation_invocation_id=plan.operation_invocation_id,
        role=plan.role,
        operation_ref=plan.operation_ref,
        endpoint_uid=trace.endpoint_uid,
        attempt_trace_id=trace.trace_id,
        policy_fingerprint=plan.policy_fingerprint,
        elapsed_ms=trace.elapsed_ms,
        attributes={
            "status": trace.status.value,
            "candidate_budget_ms": str(trace.candidate_budget_ms or 0),
            "suppression_protected": str(trace.suppression_protected).lower(),
            "router_version": ROUTER_VERSION,
        },
        token_usage=token_usage,
    )


def _suppression_event(plan: InvocationPlan, trace: AttemptTrace) -> TelemetryEvent:
    return telemetry_event(
        family=TelemetryEventFamily.ENDPOINT_SUPPRESSED,
        operation_invocation_id=plan.operation_invocation_id,
        role=plan.role,
        operation_ref=plan.operation_ref,
        endpoint_uid=trace.endpoint_uid,
        attempt_trace_id=trace.trace_id,
        policy_fingerprint=plan.policy_fingerprint,
        attributes={
            "skip_reason": trace.skip_reason or "suppressed",
            "router_version": ROUTER_VERSION,
        },
    )


def _cancellation_event(terminal: TypedFailure) -> TelemetryEvent:
    return telemetry_event(
        family=TelemetryEventFamily.CANCELLATION,
        operation_invocation_id=terminal.context.operation_invocation_id,
        role=terminal.context.role,
        operation_ref=terminal.context.operation_ref,
        endpoint_uid=terminal.context.endpoint_uid,
        attempt_trace_id=(
            terminal.context.attempt_trace.trace_id if terminal.context.attempt_trace else None
        ),
        schema_contract_ref=terminal.context.schema_contract_ref,
        schema_fingerprint=terminal.context.schema_fingerprint,
        schema_resolution_status=terminal.context.schema_resolution_status,
        policy_fingerprint=terminal.context.policy_fingerprint,
        elapsed_ms=terminal.context.elapsed_ms,
        failure_class=terminal.failure_class,
        attributes={
            "failure_code": terminal.code.value,
            "router_version": ROUTER_VERSION,
        },
    )


def _deadline_event(terminal: TypedFailure) -> TelemetryEvent:
    return telemetry_event(
        family=TelemetryEventFamily.DEADLINE_EXCEEDED,
        operation_invocation_id=terminal.context.operation_invocation_id,
        role=terminal.context.role,
        operation_ref=terminal.context.operation_ref,
        endpoint_uid=terminal.context.endpoint_uid,
        attempt_trace_id=(
            terminal.context.attempt_trace.trace_id if terminal.context.attempt_trace else None
        ),
        schema_contract_ref=terminal.context.schema_contract_ref,
        schema_fingerprint=terminal.context.schema_fingerprint,
        schema_resolution_status=terminal.context.schema_resolution_status,
        policy_fingerprint=terminal.context.policy_fingerprint,
        elapsed_ms=terminal.context.elapsed_ms,
        failure_class=terminal.failure_class,
        attributes={
            "failure_code": terminal.code.value,
            "router_version": ROUTER_VERSION,
        },
    )


def _late_response_event(
    plan: InvocationPlan,
    trace: AttemptTrace,
    attempt_output: ProviderOutcome | TypedFailure,
) -> TelemetryEvent:
    token_usage = (
        attempt_output.token_usage if isinstance(attempt_output, ProviderOutcome) else None
    )
    return telemetry_event(
        family=TelemetryEventFamily.LATE_RESPONSE_DISCARDED,
        operation_invocation_id=plan.operation_invocation_id,
        role=plan.role,
        operation_ref=plan.operation_ref,
        endpoint_uid=trace.endpoint_uid,
        attempt_trace_id=trace.trace_id,
        schema_contract_ref=plan.schema_contract_ref,
        policy_fingerprint=plan.policy_fingerprint,
        elapsed_ms=trace.elapsed_ms,
        attributes={
            "status": trace.status.value,
            "candidate_budget_ms": str(trace.candidate_budget_ms or 0),
            "router_version": ROUTER_VERSION,
        },
        token_usage=token_usage,
    )


def _success_event(
    plan: InvocationPlan,
    terminal: PlainTextResult | StructuredResult,
    attempt_output: ProviderOutcome | TypedFailure,
) -> TelemetryEvent:
    token_usage = (
        attempt_output.token_usage if isinstance(attempt_output, ProviderOutcome) else None
    )
    attributes = {"router_version": ROUTER_VERSION}
    if isinstance(terminal, StructuredResult):
        attributes.update(
            {
                "schema_name": terminal.schema_name,
                "schema_version": terminal.schema_version,
                "schema_fingerprint": terminal.schema_fingerprint,
                "structured_output_pipeline_version": STRUCTURED_OUTPUT_PIPELINE_VERSION,
                "structured_output_mode": plan.effective_config.structured_output_mode.value,
            }
        )
    return telemetry_event(
        family=TelemetryEventFamily.SUCCESS,
        operation_invocation_id=plan.operation_invocation_id,
        role=plan.role,
        operation_ref=plan.operation_ref,
        endpoint_uid=terminal.endpoint_uid,
        schema_contract_ref=(
            plan.schema_contract_ref if isinstance(terminal, StructuredResult) else None
        ),
        schema_fingerprint=(
            terminal.schema_fingerprint if isinstance(terminal, StructuredResult) else None
        ),
        schema_resolution_status=(
            SchemaResolutionStatus.RESOLVED.value
            if isinstance(terminal, StructuredResult)
            else None
        ),
        policy_fingerprint=plan.policy_fingerprint,
        elapsed_ms=terminal.elapsed_ms,
        token_usage=token_usage,
        attributes=attributes,
    )


def _failure_event(terminal: TypedFailure) -> TelemetryEvent:
    return telemetry_event(
        family=TelemetryEventFamily.FAILURE,
        operation_invocation_id=terminal.context.operation_invocation_id,
        role=terminal.context.role,
        operation_ref=terminal.context.operation_ref,
        endpoint_uid=terminal.context.endpoint_uid,
        attempt_trace_id=(
            terminal.context.attempt_trace.trace_id if terminal.context.attempt_trace else None
        ),
        schema_contract_ref=terminal.context.schema_contract_ref,
        schema_fingerprint=terminal.context.schema_fingerprint,
        schema_resolution_status=terminal.context.schema_resolution_status,
        policy_fingerprint=terminal.context.policy_fingerprint,
        elapsed_ms=terminal.context.elapsed_ms,
        failure_class=terminal.failure_class,
        attributes={
            "failure_code": terminal.code.value,
            "retryability": terminal.retryability.value if terminal.retryability else "unknown",
            "router_version": ROUTER_VERSION,
        },
    )


def _route_result(
    terminal: TerminalResult,
    traces: list[AttemptTrace],
    emitter: TelemetryEmitter,
) -> PoolRouteResult:
    return PoolRouteResult(
        terminal_result=terminal,
        attempt_traces=tuple(traces),
        telemetry=tuple(emitter.captured_events),
    )


def _elapsed_ms(attempt_output: ProviderOutcome | TypedFailure, terminal: TerminalResult) -> int:
    if isinstance(attempt_output, ProviderOutcome):
        return attempt_output.elapsed_ms
    if isinstance(terminal, TypedFailure):
        return terminal.context.elapsed_ms or 0
    if isinstance(terminal, (PlainTextResult, StructuredResult)):
        return terminal.elapsed_ms
    raise TypeError("unknown terminal result type")


@overload
def _with_schema_identity(
    terminal: TypedFailure,
    schema: SchemaContract | None,
) -> TypedFailure: ...


@overload
def _with_schema_identity(
    terminal: PlainTextResult | StructuredResult,
    schema: SchemaContract | None,
) -> PlainTextResult | StructuredResult: ...


def _with_schema_identity(
    terminal: TerminalResult,
    schema: SchemaContract | None,
) -> TerminalResult:
    if not isinstance(terminal, TypedFailure) or schema is None:
        return terminal
    context = replace(
        terminal.context,
        schema_contract_ref=terminal.context.schema_contract_ref or schema.ref,
        schema_fingerprint=terminal.context.schema_fingerprint or schema.fingerprint,
        schema_resolution_status=(
            terminal.context.schema_resolution_status
            or SchemaResolutionStatus.RESOLVED.value
        ),
    )
    return replace(terminal, context=context)


def _attempt_count(traces: list[AttemptTrace]) -> int:
    return sum(1 for trace in traces if trace.status is not AttemptStatus.SKIPPED_SUPPRESSED)


def _skipped_count(traces: list[AttemptTrace]) -> int:
    return sum(1 for trace in traces if trace.status is AttemptStatus.SKIPPED_SUPPRESSED)


def _trace_id(invocation_id: str, endpoint_uid: str, candidate_index: int) -> str:
    return f"{invocation_id}:{candidate_index}:{endpoint_uid}"
