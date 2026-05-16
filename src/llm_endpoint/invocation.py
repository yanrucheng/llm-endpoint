"""Public no-provider-call invocation planning facade."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from llm_endpoint.capabilities import DEFAULT_CAPABILITY_CATALOG, CapabilityCatalog
from llm_endpoint.config import (
    LLMEndpointConfig,
    Registry,
    StructuredOutputMode,
    build_registry,
    validate_config,
)
from llm_endpoint.policy import (
    CallerPolicyOverrides,
    EffectiveRuntimeConfig,
    PolicyResolution,
    resolve_policy,
)
from llm_endpoint.results import FailureCode, TypedFailure, failure
from llm_endpoint.telemetry import (
    TelemetryEmitter,
    TelemetryEvent,
    TelemetryEventFamily,
    telemetry_event,
)

INVOCATION_FACADE_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class InvocationRequest:
    """Canonical direct invocation input accepted by the public facade."""

    role: str
    operation_ref: str
    messages: Sequence[Mapping[str, Any]]
    deadline_ms: int
    schema_contract_ref: str | None = None
    caller_overrides: CallerPolicyOverrides | None = None
    request_metadata: Mapping[str, str] = field(default_factory=dict)
    operation_invocation_id: str | None = None


@dataclass(frozen=True, slots=True)
class InvocationPlan:
    """Offline endpoint plan produced before provider calls are allowed."""

    operation_invocation_id: str
    role: str
    operation_ref: str
    endpoint_uids: tuple[str, ...]
    messages: Sequence[Mapping[str, Any]]
    deadline_ms: int
    effective_config: EffectiveRuntimeConfig
    config_identity: str
    policy_fingerprint: str
    schema_contract_ref: str | None = None
    request_metadata: Mapping[str, str] = field(default_factory=dict)
    telemetry: tuple[TelemetryEvent, ...] = ()
    facade_version: str = INVOCATION_FACADE_VERSION

    def __post_init__(self) -> None:
        if self.facade_version != INVOCATION_FACADE_VERSION:
            raise ValueError("only invocation facade version 'v1' is supported")
        if not self.operation_invocation_id:
            raise ValueError("operation_invocation_id is required")
        if self.deadline_ms <= 0:
            raise ValueError("deadline_ms must be positive")


def invoke_plan(
    *,
    request: InvocationRequest,
    config: LLMEndpointConfig | None = None,
    registry: Registry | None = None,
    capability_catalog: CapabilityCatalog = DEFAULT_CAPABILITY_CATALOG,
    telemetry_emitter: TelemetryEmitter | None = None,
) -> InvocationPlan | TypedFailure:
    """Validate and plan an invocation without network, secrets, or provider calls."""

    emitter = telemetry_emitter or TelemetryEmitter()
    invocation_id = request.operation_invocation_id or _new_invocation_id()
    input_failure = _validate_request(request, invocation_id)
    if input_failure is not None:
        _emit_failure(emitter, input_failure)
        return input_failure

    if registry is None:
        if config is None:
            typed_failure = failure(
                code=FailureCode.INVALID_CONFIG,
                message="config or registry is required",
                operation_invocation_id=invocation_id,
                role=request.role,
                operation_ref=request.operation_ref,
            )
            _emit_failure(emitter, typed_failure)
            return typed_failure

        report = validate_config(config, capability_catalog=capability_catalog)
        emitter.emit(
            telemetry_event(
                family=TelemetryEventFamily.REGISTRY_VALIDATED,
                operation_invocation_id=invocation_id,
                role=request.role,
                operation_ref=request.operation_ref,
                attributes={
                    "ok": str(report.ok).lower(),
                    "error_count": str(len(report.errors)),
                    "config_identity": report.config_identity or "",
                },
            )
        )
        if not report.ok:
            typed_failure = failure(
                code=FailureCode.INVALID_CONFIG,
                message="config validation failed",
                operation_invocation_id=invocation_id,
                role=request.role,
                operation_ref=request.operation_ref,
                safe_context={"error_count": str(len(report.errors))},
            )
            _emit_failure(emitter, typed_failure)
            return typed_failure
        registry = build_registry(config, capability_catalog=capability_catalog)

    overrides_or_failure = _request_overrides(request, registry, invocation_id)
    if isinstance(overrides_or_failure, TypedFailure):
        _emit_failure(emitter, overrides_or_failure)
        return overrides_or_failure

    policy_result = resolve_policy(
        registry=registry,
        role=request.role,
        operation_ref=request.operation_ref,
        operation_invocation_id=invocation_id,
        caller_overrides=overrides_or_failure,
        capability_catalog=capability_catalog,
    )
    if isinstance(policy_result, TypedFailure):
        _emit_failure(emitter, policy_result)
        return policy_result

    emitter.emit(policy_result.telemetry)
    schema_ref_or_failure = _schema_ref(request, registry, policy_result, invocation_id)
    if isinstance(schema_ref_or_failure, TypedFailure):
        _emit_failure(emitter, schema_ref_or_failure)
        return schema_ref_or_failure

    return InvocationPlan(
        operation_invocation_id=invocation_id,
        role=policy_result.role,
        operation_ref=policy_result.operation_ref,
        endpoint_uids=policy_result.endpoint_uids,
        messages=request.messages,
        deadline_ms=request.deadline_ms,
        effective_config=policy_result.effective_config,
        config_identity=policy_result.config_identity,
        policy_fingerprint=policy_result.policy_fingerprint,
        schema_contract_ref=schema_ref_or_failure,
        request_metadata=dict(request.request_metadata),
        telemetry=tuple(emitter.captured_events),
    )


def _validate_request(request: InvocationRequest, invocation_id: str) -> TypedFailure | None:
    if not request.role:
        return failure(
            code=FailureCode.INVALID_INVOCATION,
            message="role is required",
            operation_invocation_id=invocation_id,
            operation_ref=request.operation_ref or None,
        )
    if not request.operation_ref:
        return failure(
            code=FailureCode.INVALID_INVOCATION,
            message="operation_ref is required",
            operation_invocation_id=invocation_id,
            role=request.role,
        )
    if request.deadline_ms <= 0:
        return failure(
            code=FailureCode.INVALID_INVOCATION,
            message="deadline_ms must be positive",
            operation_invocation_id=invocation_id,
            role=request.role,
            operation_ref=request.operation_ref,
        )
    if not request.messages:
        return failure(
            code=FailureCode.INVALID_INVOCATION,
            message="messages must contain at least one entry",
            operation_invocation_id=invocation_id,
            role=request.role,
            operation_ref=request.operation_ref,
        )
    for index, message in enumerate(request.messages):
        if not isinstance(message, Mapping):
            return _invalid_message(request, invocation_id, index, "message must be a mapping")
        if "role" not in message or "content" not in message:
            return _invalid_message(
                request,
                invocation_id,
                index,
                "message requires role and content keys",
            )
    return None


def _invalid_message(
    request: InvocationRequest,
    invocation_id: str,
    index: int,
    message: str,
) -> TypedFailure:
    return failure(
        code=FailureCode.INVALID_INVOCATION,
        message=message,
        operation_invocation_id=invocation_id,
        role=request.role,
        operation_ref=request.operation_ref,
        safe_context={"message_index": str(index)},
    )


def _request_overrides(
    request: InvocationRequest,
    registry: Registry,
    invocation_id: str,
) -> CallerPolicyOverrides | TypedFailure:
    try:
        policy = registry.resolve_operation_policy(request.operation_ref)
    except KeyError as exc:
        return failure(
            code=FailureCode.INVALID_INVOCATION,
            message=str(exc),
            operation_invocation_id=invocation_id,
            role=request.role,
            operation_ref=request.operation_ref,
        )
    base = request.caller_overrides or CallerPolicyOverrides()
    if base.deadline_ms is not None and base.deadline_ms != request.deadline_ms:
        return failure(
            code=FailureCode.INVALID_INVOCATION,
            message="deadline_ms must match caller_overrides.deadline_ms when both are supplied",
            operation_invocation_id=invocation_id,
            role=request.role,
            operation_ref=request.operation_ref,
        )
    deadline_override = request.deadline_ms if request.deadline_ms != policy.deadline_ms else None
    return CallerPolicyOverrides(
        deadline_ms=base.deadline_ms or deadline_override,
        max_output_tokens=base.max_output_tokens,
        reasoning_mode=base.reasoning_mode,
        candidate_budget_ms=base.candidate_budget_ms,
    )


def _schema_ref(
    request: InvocationRequest,
    registry: Registry,
    policy_result: PolicyResolution,
    invocation_id: str,
) -> str | None | TypedFailure:
    operation = registry.operations_by_ref[request.operation_ref]
    schema_ref = request.schema_contract_ref or operation.schema_contract_ref
    if policy_result.effective_config.structured_output_mode is StructuredOutputMode.NONE:
        return schema_ref
    if schema_ref:
        return schema_ref
    return failure(
        code=FailureCode.SCHEMA_NOT_FOUND,
        message="structured-output operation requires a schema_contract_ref",
        operation_invocation_id=invocation_id,
        role=request.role,
        operation_ref=request.operation_ref,
        policy_fingerprint=policy_result.policy_fingerprint,
    )


def _emit_failure(emitter: TelemetryEmitter, typed_failure: TypedFailure) -> None:
    retryability = typed_failure.retryability
    if retryability is None:
        raise ValueError("typed failures must carry retryability after normalization")
    emitter.emit(
        telemetry_event(
            family=TelemetryEventFamily.FAILURE,
            operation_invocation_id=typed_failure.context.operation_invocation_id,
            role=typed_failure.context.role,
            operation_ref=typed_failure.context.operation_ref,
            endpoint_uid=typed_failure.context.endpoint_uid,
            policy_fingerprint=typed_failure.context.policy_fingerprint,
            elapsed_ms=typed_failure.context.elapsed_ms,
            failure_class=typed_failure.failure_class,
            attributes={
                "failure_code": typed_failure.code.value,
                "retryability": retryability.value,
            },
        )
    )


def _new_invocation_id() -> str:
    return f"inv-{uuid4().hex}"
