"""Typed result and failure contracts for provider invocation outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

FAILURE_TAXONOMY_VERSION = "v1"


class Retryability(StrEnum):
    """Whether a failure may be retried by deterministic failover."""

    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    UNKNOWN = "unknown"


class FailureClass(StrEnum):
    """High-level failure class for telemetry and operator handling."""

    VALIDATION = "validation"
    CONFIGURATION = "configuration"
    CREDENTIAL = "credential"
    CAPABILITY = "capability"
    POLICY = "policy"
    ROUTING = "routing"
    PROVIDER_AVAILABILITY = "provider_availability"
    PROVIDER_CONTRACT = "provider_contract"
    STRUCTURED_OUTPUT = "structured_output"
    DEADLINE = "deadline"
    CANCELLATION = "cancellation"
    INTERNAL = "internal"


class FailureCode(StrEnum):
    """Stable public PRD failure codes owned by the result contract."""

    INVALID_ENDPOINT_CONFIG = "llm.config.invalid_endpoint_config"
    CREDENTIAL_UNAVAILABLE = "llm.config.credential_unavailable"
    UNKNOWN_ROLE = "llm.endpoint.unknown_role"
    UNKNOWN_ENTRYPOINT = "llm.endpoint.unknown_entrypoint"
    UNSUPPORTED_PROVIDER_FORMAT = "llm.endpoint.unsupported_provider_format"
    ENDPOINT_SUPPRESSED = "llm.endpoint.suppressed"
    UNSUPPORTED_RUNTIME_KNOB = "llm.endpoint.unsupported_runtime_knob"
    CAPABILITY_MISMATCH = "llm.policy.capability_mismatch"
    UNSUPPORTED_REASONING_MODE = "llm.policy.unsupported_reasoning_mode"
    OUTPUT_BUDGET_EXCEEDS_HARD_CAP = "llm.policy.output_budget_exceeds_hard_cap"
    CANDIDATE_BUDGET_UNALLOCATABLE = "llm.policy.candidate_budget_unallocatable"
    OPERATION_REF_REQUIRED = "llm.policy.operation_ref_required"
    INVALID_MESSAGES = "llm.input.invalid_messages"
    CANCELLED = "llm.input.cancelled"
    MISSING_SCHEMA_CONTRACT = "llm.schema.missing_contract"
    UNKNOWN_SCHEMA_CONTRACT = "llm.schema.unknown_contract"
    INVALID_STRUCTURED_OUTPUT_PAYLOAD = "llm.structured_output.invalid_payload"
    STRUCTURED_OUTPUT_REFUSAL = "llm.structured_output.refusal"
    INVOCATION_RATE_LIMITED = "llm.invocation.rate_limited"
    INVOCATION_QUOTA_EXHAUSTED = "llm.invocation.quota_exhausted"
    TRANSIENT_NETWORK = "llm.invocation.transient_network"
    PROVIDER_5XX = "llm.invocation.provider_5xx"
    PROVIDER_FAILURE = "llm.invocation.provider_failure"
    LOCAL_CANDIDATE_TIMEOUT = "llm.invocation.local_candidate_timeout"
    LATE_RESPONSE_DISCARDED = "llm.invocation.late_response_discarded"
    DEADLINE_EXCEEDED = "llm.deadline.exceeded"
    NO_ELIGIBLE_CANDIDATE = "llm.pool.no_eligible_candidate"
    POOL_EXHAUSTED = "llm.pool.exhausted"
    SMOKE_SKIPPED = "llm.smoke.skipped"
    SMOKE_FAILED = "llm.smoke.failed"
    BUDGET_VIOLATION = "llm.budget.violation"
    MODULE_UNSUPPORTED_VERSION = "llm.module.unsupported_version"


RETRYABILITY_BY_CODE: Mapping[FailureCode, Retryability] = MappingProxyType(
    {
        FailureCode.INVALID_ENDPOINT_CONFIG: Retryability.NON_RETRYABLE,
        FailureCode.CREDENTIAL_UNAVAILABLE: Retryability.NON_RETRYABLE,
        FailureCode.UNKNOWN_ROLE: Retryability.NON_RETRYABLE,
        FailureCode.UNKNOWN_ENTRYPOINT: Retryability.NON_RETRYABLE,
        FailureCode.UNSUPPORTED_PROVIDER_FORMAT: Retryability.NON_RETRYABLE,
        FailureCode.ENDPOINT_SUPPRESSED: Retryability.RETRYABLE,
        FailureCode.UNSUPPORTED_RUNTIME_KNOB: Retryability.NON_RETRYABLE,
        FailureCode.CAPABILITY_MISMATCH: Retryability.NON_RETRYABLE,
        FailureCode.UNSUPPORTED_REASONING_MODE: Retryability.NON_RETRYABLE,
        FailureCode.OUTPUT_BUDGET_EXCEEDS_HARD_CAP: Retryability.NON_RETRYABLE,
        FailureCode.CANDIDATE_BUDGET_UNALLOCATABLE: Retryability.NON_RETRYABLE,
        FailureCode.OPERATION_REF_REQUIRED: Retryability.NON_RETRYABLE,
        FailureCode.INVALID_MESSAGES: Retryability.NON_RETRYABLE,
        FailureCode.CANCELLED: Retryability.NON_RETRYABLE,
        FailureCode.MISSING_SCHEMA_CONTRACT: Retryability.NON_RETRYABLE,
        FailureCode.UNKNOWN_SCHEMA_CONTRACT: Retryability.NON_RETRYABLE,
        FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD: Retryability.NON_RETRYABLE,
        FailureCode.STRUCTURED_OUTPUT_REFUSAL: Retryability.NON_RETRYABLE,
        FailureCode.INVOCATION_RATE_LIMITED: Retryability.RETRYABLE,
        FailureCode.INVOCATION_QUOTA_EXHAUSTED: Retryability.RETRYABLE,
        FailureCode.TRANSIENT_NETWORK: Retryability.RETRYABLE,
        FailureCode.PROVIDER_5XX: Retryability.RETRYABLE,
        FailureCode.PROVIDER_FAILURE: Retryability.NON_RETRYABLE,
        FailureCode.LOCAL_CANDIDATE_TIMEOUT: Retryability.RETRYABLE,
        FailureCode.LATE_RESPONSE_DISCARDED: Retryability.NON_RETRYABLE,
        FailureCode.DEADLINE_EXCEEDED: Retryability.NON_RETRYABLE,
        FailureCode.NO_ELIGIBLE_CANDIDATE: Retryability.NON_RETRYABLE,
        FailureCode.POOL_EXHAUSTED: Retryability.NON_RETRYABLE,
        FailureCode.SMOKE_SKIPPED: Retryability.NON_RETRYABLE,
        FailureCode.SMOKE_FAILED: Retryability.NON_RETRYABLE,
        FailureCode.BUDGET_VIOLATION: Retryability.NON_RETRYABLE,
        FailureCode.MODULE_UNSUPPORTED_VERSION: Retryability.NON_RETRYABLE,
    }
)

FAILURE_CLASS_BY_CODE: Mapping[FailureCode, FailureClass] = MappingProxyType(
    {
        FailureCode.INVALID_ENDPOINT_CONFIG: FailureClass.CONFIGURATION,
        FailureCode.CREDENTIAL_UNAVAILABLE: FailureClass.CREDENTIAL,
        FailureCode.UNKNOWN_ROLE: FailureClass.ROUTING,
        FailureCode.UNKNOWN_ENTRYPOINT: FailureClass.ROUTING,
        FailureCode.UNSUPPORTED_PROVIDER_FORMAT: FailureClass.CAPABILITY,
        FailureCode.ENDPOINT_SUPPRESSED: FailureClass.ROUTING,
        FailureCode.UNSUPPORTED_RUNTIME_KNOB: FailureClass.CAPABILITY,
        FailureCode.CAPABILITY_MISMATCH: FailureClass.CAPABILITY,
        FailureCode.UNSUPPORTED_REASONING_MODE: FailureClass.CAPABILITY,
        FailureCode.OUTPUT_BUDGET_EXCEEDS_HARD_CAP: FailureClass.POLICY,
        FailureCode.CANDIDATE_BUDGET_UNALLOCATABLE: FailureClass.POLICY,
        FailureCode.OPERATION_REF_REQUIRED: FailureClass.POLICY,
        FailureCode.INVALID_MESSAGES: FailureClass.VALIDATION,
        FailureCode.CANCELLED: FailureClass.CANCELLATION,
        FailureCode.MISSING_SCHEMA_CONTRACT: FailureClass.STRUCTURED_OUTPUT,
        FailureCode.UNKNOWN_SCHEMA_CONTRACT: FailureClass.STRUCTURED_OUTPUT,
        FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD: FailureClass.STRUCTURED_OUTPUT,
        FailureCode.STRUCTURED_OUTPUT_REFUSAL: FailureClass.STRUCTURED_OUTPUT,
        FailureCode.INVOCATION_RATE_LIMITED: FailureClass.PROVIDER_AVAILABILITY,
        FailureCode.INVOCATION_QUOTA_EXHAUSTED: FailureClass.PROVIDER_AVAILABILITY,
        FailureCode.TRANSIENT_NETWORK: FailureClass.PROVIDER_AVAILABILITY,
        FailureCode.PROVIDER_5XX: FailureClass.PROVIDER_AVAILABILITY,
        FailureCode.PROVIDER_FAILURE: FailureClass.PROVIDER_CONTRACT,
        FailureCode.LOCAL_CANDIDATE_TIMEOUT: FailureClass.DEADLINE,
        FailureCode.LATE_RESPONSE_DISCARDED: FailureClass.DEADLINE,
        FailureCode.DEADLINE_EXCEEDED: FailureClass.DEADLINE,
        FailureCode.NO_ELIGIBLE_CANDIDATE: FailureClass.ROUTING,
        FailureCode.POOL_EXHAUSTED: FailureClass.ROUTING,
        FailureCode.SMOKE_SKIPPED: FailureClass.ROUTING,
        FailureCode.SMOKE_FAILED: FailureClass.PROVIDER_CONTRACT,
        FailureCode.BUDGET_VIOLATION: FailureClass.POLICY,
        FailureCode.MODULE_UNSUPPORTED_VERSION: FailureClass.INTERNAL,
    }
)


@dataclass(frozen=True, slots=True)
class SafeDiagnostics:
    """Human-safe diagnostic material for failures and telemetry."""

    message: str
    remediation_hint: str | None = None
    safe_context: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AttemptTraceRef:
    """Redacted attempt trace identity, not raw trace payload."""

    trace_id: str


@dataclass(frozen=True, slots=True)
class FailureContext:
    """Safe correlation context attached to typed failures."""

    operation_invocation_id: str
    role: str | None = None
    operation_ref: str | None = None
    endpoint_uid: str | None = None
    schema_contract_ref: str | None = None
    schema_fingerprint: str | None = None
    schema_resolution_status: str | None = None
    policy_fingerprint: str | None = None
    elapsed_ms: int | None = None
    attempt_trace: AttemptTraceRef | None = None


@dataclass(frozen=True, slots=True)
class TypedFailure:
    """Terminal module failure safe for public handling and telemetry."""

    code: FailureCode
    diagnostics: SafeDiagnostics
    context: FailureContext
    retryability: Retryability | None = None
    failure_class: FailureClass | None = None
    taxonomy_version: str = FAILURE_TAXONOMY_VERSION

    def __post_init__(self) -> None:
        retryability = self.retryability or RETRYABILITY_BY_CODE[self.code]
        failure_class = self.failure_class or FAILURE_CLASS_BY_CODE[self.code]
        object.__setattr__(self, "retryability", retryability)
        object.__setattr__(self, "failure_class", failure_class)
        if self.context.elapsed_ms is not None and self.context.elapsed_ms < 0:
            raise ValueError("elapsed_ms must be omitted or non-negative")

    @property
    def is_retryable(self) -> bool:
        """Return true only for explicitly retryable availability failures."""

        return self.retryability is Retryability.RETRYABLE


@dataclass(frozen=True, slots=True)
class StructuredResult:
    """Validated structured result after extraction and application validation."""

    value: Mapping[str, Any]
    schema_name: str
    schema_version: str
    schema_fingerprint: str
    operation_invocation_id: str
    endpoint_uid: str
    policy_fingerprint: str
    elapsed_ms: int

    def __post_init__(self) -> None:
        if self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must be non-negative")
        if not self.schema_name or not self.schema_version or not self.schema_fingerprint:
            raise ValueError("structured results require schema identity")


@dataclass(frozen=True, slots=True)
class PlainTextResult:
    """Accepted plain text result for operations that permit text output."""

    text: str
    operation_invocation_id: str
    endpoint_uid: str
    policy_fingerprint: str
    elapsed_ms: int

    def __post_init__(self) -> None:
        if self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must be non-negative")


type TerminalResult = StructuredResult | PlainTextResult | TypedFailure


def failure(
    *,
    code: FailureCode,
    message: str,
    operation_invocation_id: str,
    role: str | None = None,
    operation_ref: str | None = None,
    endpoint_uid: str | None = None,
    schema_contract_ref: str | None = None,
    schema_fingerprint: str | None = None,
    schema_resolution_status: str | None = None,
    policy_fingerprint: str | None = None,
    elapsed_ms: int | None = None,
    attempt_trace_id: str | None = None,
    remediation_hint: str | None = None,
    safe_context: Mapping[str, str] | None = None,
) -> TypedFailure:
    """Build a typed failure with safe diagnostics only."""

    trace = AttemptTraceRef(attempt_trace_id) if attempt_trace_id else None
    return TypedFailure(
        code=code,
        diagnostics=SafeDiagnostics(
            message=message,
            remediation_hint=remediation_hint,
            safe_context=safe_context or {},
        ),
        context=FailureContext(
            operation_invocation_id=operation_invocation_id,
            role=role,
            operation_ref=operation_ref,
            endpoint_uid=endpoint_uid,
            schema_contract_ref=schema_contract_ref,
            schema_fingerprint=schema_fingerprint,
            schema_resolution_status=schema_resolution_status,
            policy_fingerprint=policy_fingerprint,
            elapsed_ms=elapsed_ms,
            attempt_trace=trace,
        ),
    )
