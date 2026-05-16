"""Runtime policy resolution with provenance and hard-cap enforcement."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum

from llm_endpoint.capabilities import DEFAULT_CAPABILITY_CATALOG, CapabilityCatalog
from llm_endpoint.config import (
    LLMEndpointConfig,
    OperationRuntimePolicy,
    ReasoningMode,
    Registry,
    StructuredOutputMode,
    build_registry,
)
from llm_endpoint.results import FailureCode, TypedFailure, failure
from llm_endpoint.telemetry import TelemetryEvent, TelemetryEventFamily, telemetry_event

POLICY_RESOLVER_VERSION = "v1"


class PolicyField(StrEnum):
    """Runtime fields allowed in effective policy output."""

    DEADLINE_MS = "deadline_ms"
    MAX_OUTPUT_TOKENS = "max_output_tokens"
    REASONING_MODE = "reasoning_mode"
    CANDIDATE_BUDGET_MS = "candidate_budget_ms"
    FAILOVER_RESERVE_MS = "failover_reserve_ms"
    STRUCTURED_OUTPUT_MODE = "structured_output_mode"
    RETRY_CLASS = "retry_class"
    MAX_ATTEMPTS = "max_attempts"


class PolicySource(StrEnum):
    """Where an effective policy field came from."""

    POLICY = "policy"
    CALLER_OVERRIDE = "caller_override"
    DERIVED = "derived"


@dataclass(frozen=True, slots=True)
class CallerPolicyOverrides:
    """Safe caller overrides accepted only when the operation policy allows them."""

    deadline_ms: int | None = None
    max_output_tokens: int | None = None
    reasoning_mode: ReasoningMode | None = None
    candidate_budget_ms: int | None = None


@dataclass(frozen=True, slots=True)
class EffectiveRuntimeConfig:
    """Immutable resolved runtime values used by routing and adapters."""

    deadline_ms: int
    max_output_tokens: int
    reasoning_mode: ReasoningMode
    candidate_budget_ms: int
    failover_reserve_ms: int
    structured_output_mode: StructuredOutputMode
    retry_class: str
    max_attempts: int


@dataclass(frozen=True, slots=True)
class PolicyResolution:
    """Successful policy resolution result."""

    role: str
    operation_ref: str
    endpoint_uids: tuple[str, ...]
    effective_config: EffectiveRuntimeConfig
    provenance: dict[str, PolicySource]
    policy_fingerprint: str
    config_identity: str
    telemetry: TelemetryEvent


def resolve_policy(
    *,
    config: LLMEndpointConfig | None = None,
    registry: Registry | None = None,
    role: str,
    operation_ref: str,
    operation_invocation_id: str,
    caller_overrides: CallerPolicyOverrides | None = None,
    capability_catalog: CapabilityCatalog = DEFAULT_CAPABILITY_CATALOG,
) -> PolicyResolution | TypedFailure:
    """Resolve runtime policy or return a typed failure with safe diagnostics."""

    if registry is None:
        if config is None:
            raise ValueError("config or registry is required")
        registry = build_registry(config, capability_catalog=capability_catalog)

    try:
        resolved_role = registry.resolve_role(role)
    except KeyError as exc:
        return failure(
            code=FailureCode.UNKNOWN_ROLE,
            message=str(exc),
            operation_invocation_id=operation_invocation_id,
            role=role,
            operation_ref=operation_ref,
        )
    try:
        policy = registry.resolve_operation_policy(operation_ref)
    except KeyError as exc:
        return failure(
            code=FailureCode.UNKNOWN_ENTRYPOINT,
            message=str(exc),
            operation_invocation_id=operation_invocation_id,
            role=role,
            operation_ref=operation_ref,
        )

    overrides = caller_overrides or CallerPolicyOverrides()
    if overrides != CallerPolicyOverrides() and not policy.allow_caller_overrides:
        return failure(
            code=FailureCode.UNSUPPORTED_RUNTIME_KNOB,
            message="caller overrides are not allowed for this operation policy",
            operation_invocation_id=operation_invocation_id,
            role=role,
            operation_ref=operation_ref,
        )

    effective = _effective_config(policy, overrides)
    validation_failure = _validate_effective_config(
        registry=registry,
        role=role,
        operation_ref=operation_ref,
        operation_invocation_id=operation_invocation_id,
        endpoint_uids=resolved_role.endpoint_uids,
        effective=effective,
        capability_catalog=capability_catalog,
    )
    if validation_failure is not None:
        return validation_failure

    provenance = _provenance(policy, overrides)
    fingerprint = policy_fingerprint(
        effective_config=effective,
        provenance=provenance,
        config_identity=registry.config_identity,
        role=role,
        operation_ref=operation_ref,
        endpoint_uids=resolved_role.endpoint_uids,
    )

    event = telemetry_event(
        family=TelemetryEventFamily.POLICY_RESOLVED,
        operation_invocation_id=operation_invocation_id,
        role=role,
        operation_ref=operation_ref,
        policy_fingerprint=fingerprint,
        attributes={
            "config_identity": registry.config_identity,
            "endpoint_count": str(len(resolved_role.endpoint_uids)),
            "policy_resolver_version": POLICY_RESOLVER_VERSION,
        },
    )
    return PolicyResolution(
        role=role,
        operation_ref=operation_ref,
        endpoint_uids=resolved_role.endpoint_uids,
        effective_config=effective,
        provenance=provenance,
        policy_fingerprint=fingerprint,
        config_identity=registry.config_identity,
        telemetry=event,
    )


def policy_fingerprint(
    *,
    effective_config: EffectiveRuntimeConfig,
    provenance: dict[str, PolicySource],
    config_identity: str,
    role: str,
    operation_ref: str,
    endpoint_uids: tuple[str, ...],
) -> str:
    """Return deterministic policy fingerprint for telemetry/debug identity."""

    payload = {
        "config_identity": config_identity,
        "effective_config": asdict(effective_config),
        "endpoint_uids": endpoint_uids,
        "operation_ref": operation_ref,
        "provenance": {key: value.value for key, value in sorted(provenance.items())},
        "role": role,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _effective_config(
    policy: OperationRuntimePolicy,
    overrides: CallerPolicyOverrides,
) -> EffectiveRuntimeConfig:
    deadline_ms = overrides.deadline_ms or policy.deadline_ms
    candidate_budget_ms = overrides.candidate_budget_ms or policy.candidate_budget_ms
    if candidate_budget_ms is None:
        candidate_budget_ms = max(1, deadline_ms - policy.failover_reserve_ms)
    return EffectiveRuntimeConfig(
        deadline_ms=deadline_ms,
        max_output_tokens=overrides.max_output_tokens or policy.max_output_tokens,
        reasoning_mode=overrides.reasoning_mode or policy.reasoning_mode,
        candidate_budget_ms=candidate_budget_ms,
        failover_reserve_ms=policy.failover_reserve_ms,
        structured_output_mode=policy.structured_output_mode,
        retry_class=policy.retry_policy.retry_class.value,
        max_attempts=policy.retry_policy.max_attempts,
    )


def _provenance(
    policy: OperationRuntimePolicy,
    overrides: CallerPolicyOverrides,
) -> dict[str, PolicySource]:
    return {
        PolicyField.DEADLINE_MS.value: (
            PolicySource.CALLER_OVERRIDE
            if overrides.deadline_ms is not None
            else PolicySource.POLICY
        ),
        PolicyField.MAX_OUTPUT_TOKENS.value: (
            PolicySource.CALLER_OVERRIDE
            if overrides.max_output_tokens is not None
            else PolicySource.POLICY
        ),
        PolicyField.REASONING_MODE.value: (
            PolicySource.CALLER_OVERRIDE
            if overrides.reasoning_mode is not None
            else PolicySource.POLICY
        ),
        PolicyField.CANDIDATE_BUDGET_MS.value: (
            PolicySource.CALLER_OVERRIDE
            if overrides.candidate_budget_ms is not None
            else PolicySource.POLICY
            if policy.candidate_budget_ms is not None
            else PolicySource.DERIVED
        ),
        PolicyField.FAILOVER_RESERVE_MS.value: PolicySource.POLICY,
        PolicyField.STRUCTURED_OUTPUT_MODE.value: PolicySource.POLICY,
        PolicyField.RETRY_CLASS.value: PolicySource.POLICY,
        PolicyField.MAX_ATTEMPTS.value: PolicySource.POLICY,
    }


def _validate_effective_config(
    *,
    registry: Registry,
    role: str,
    operation_ref: str,
    operation_invocation_id: str,
    endpoint_uids: tuple[str, ...],
    effective: EffectiveRuntimeConfig,
    capability_catalog: CapabilityCatalog,
) -> TypedFailure | None:
    if effective.deadline_ms <= 0:
        return _budget_failure(
            "deadline_ms must be positive",
            role,
            operation_ref,
            operation_invocation_id,
        )
    if effective.max_output_tokens <= 0:
        return _budget_failure(
            "max_output_tokens must be positive",
            role,
            operation_ref,
            operation_invocation_id,
        )
    if effective.candidate_budget_ms <= 0:
        return _budget_failure(
            "candidate_budget_ms must be positive",
            role,
            operation_ref,
            operation_invocation_id,
        )
    if effective.failover_reserve_ms < 0 or effective.failover_reserve_ms >= effective.deadline_ms:
        return _budget_failure(
            "failover_reserve_ms must be below deadline_ms",
            role,
            operation_ref,
            operation_invocation_id,
        )

    for endpoint_uid in endpoint_uids:
        endpoint = registry.endpoints_by_uid[endpoint_uid]
        profile = capability_catalog.get(endpoint.provider_format, endpoint.model_family)
        if profile is None:
            return failure(
                code=FailureCode.CAPABILITY_MISMATCH,
                message="endpoint model family is not in the capability catalog",
                operation_invocation_id=operation_invocation_id,
                role=role,
                operation_ref=operation_ref,
                endpoint_uid=endpoint_uid,
            )
        if effective.max_output_tokens > profile.hard_limits.max_output_tokens:
            return failure(
                code=FailureCode.OUTPUT_BUDGET_EXCEEDS_HARD_CAP,
                message="max_output_tokens exceeds provider hard limit",
                operation_invocation_id=operation_invocation_id,
                role=role,
                operation_ref=operation_ref,
                endpoint_uid=endpoint_uid,
            )
        if (
            profile.hard_limits.max_deadline_ms is not None
            and effective.deadline_ms > profile.hard_limits.max_deadline_ms
        ):
            return failure(
                code=FailureCode.CANDIDATE_BUDGET_UNALLOCATABLE,
                message="deadline_ms exceeds provider hard limit",
                operation_invocation_id=operation_invocation_id,
                role=role,
                operation_ref=operation_ref,
                endpoint_uid=endpoint_uid,
            )
        if not profile.supports_reasoning_mode(effective.reasoning_mode):
            return failure(
                code=FailureCode.UNSUPPORTED_REASONING_MODE,
                message="reasoning mode is not supported by endpoint capability profile",
                operation_invocation_id=operation_invocation_id,
                role=role,
                operation_ref=operation_ref,
                endpoint_uid=endpoint_uid,
            )
        if not profile.supports_structured_output(effective.structured_output_mode):
            return failure(
                code=FailureCode.CAPABILITY_MISMATCH,
                message="structured output mode is not supported by endpoint capability profile",
                operation_invocation_id=operation_invocation_id,
                role=role,
                operation_ref=operation_ref,
                endpoint_uid=endpoint_uid,
            )
    return None


def _budget_failure(
    message: str,
    role: str,
    operation_ref: str,
    operation_invocation_id: str,
) -> TypedFailure:
    return failure(
        code=FailureCode.CANDIDATE_BUDGET_UNALLOCATABLE,
        message=message,
        operation_invocation_id=operation_invocation_id,
        role=role,
        operation_ref=operation_ref,
    )
