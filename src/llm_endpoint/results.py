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
    """Stable public failure codes owned by the result contract."""

    INVALID_INVOCATION = "invalid_invocation"
    INVALID_CONFIG = "invalid_config"
    UNSUPPORTED_PROVIDER = "unsupported_provider"
    UNSUPPORTED_MODEL_FAMILY = "unsupported_model_family"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    MISSING_SECRET = "missing_secret"
    SECRET_RESOLUTION_FAILED = "secret_resolution_failed"
    SCHEMA_NOT_FOUND = "schema_not_found"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    POLICY_VIOLATION = "policy_violation"
    BUDGET_VIOLATION = "budget_violation"
    NO_ELIGIBLE_ENDPOINT = "no_eligible_endpoint"
    ENDPOINT_SUPPRESSED = "endpoint_suppressed"
    POOL_EXHAUSTED = "pool_exhausted"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_QUOTA_EXHAUSTED = "provider_quota_exhausted"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_TRANSIENT_ERROR = "provider_transient_error"
    PROVIDER_NON_RETRYABLE_ERROR = "provider_non_retryable_error"
    PROVIDER_REFUSAL = "provider_refusal"
    MALFORMED_PROVIDER_OUTPUT = "malformed_provider_output"
    WRONG_TOOL_OUTPUT = "wrong_tool_output"
    DUPLICATE_TERMINAL_OUTPUT = "duplicate_terminal_output"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    CANCELLED = "cancelled"
    LATE_RESPONSE_DISCARDED = "late_response_discarded"
    INTERNAL_ERROR = "internal_error"


RETRYABILITY_BY_CODE: Mapping[FailureCode, Retryability] = MappingProxyType(
    {
        FailureCode.INVALID_INVOCATION: Retryability.NON_RETRYABLE,
        FailureCode.INVALID_CONFIG: Retryability.NON_RETRYABLE,
        FailureCode.UNSUPPORTED_PROVIDER: Retryability.NON_RETRYABLE,
        FailureCode.UNSUPPORTED_MODEL_FAMILY: Retryability.NON_RETRYABLE,
        FailureCode.UNSUPPORTED_CAPABILITY: Retryability.NON_RETRYABLE,
        FailureCode.MISSING_SECRET: Retryability.NON_RETRYABLE,
        FailureCode.SECRET_RESOLUTION_FAILED: Retryability.NON_RETRYABLE,
        FailureCode.SCHEMA_NOT_FOUND: Retryability.NON_RETRYABLE,
        FailureCode.SCHEMA_VALIDATION_FAILED: Retryability.NON_RETRYABLE,
        FailureCode.POLICY_VIOLATION: Retryability.NON_RETRYABLE,
        FailureCode.BUDGET_VIOLATION: Retryability.NON_RETRYABLE,
        FailureCode.NO_ELIGIBLE_ENDPOINT: Retryability.NON_RETRYABLE,
        FailureCode.ENDPOINT_SUPPRESSED: Retryability.NON_RETRYABLE,
        FailureCode.POOL_EXHAUSTED: Retryability.NON_RETRYABLE,
        FailureCode.PROVIDER_RATE_LIMITED: Retryability.RETRYABLE,
        FailureCode.PROVIDER_QUOTA_EXHAUSTED: Retryability.RETRYABLE,
        FailureCode.PROVIDER_TIMEOUT: Retryability.RETRYABLE,
        FailureCode.PROVIDER_TRANSIENT_ERROR: Retryability.RETRYABLE,
        FailureCode.PROVIDER_NON_RETRYABLE_ERROR: Retryability.NON_RETRYABLE,
        FailureCode.PROVIDER_REFUSAL: Retryability.NON_RETRYABLE,
        FailureCode.MALFORMED_PROVIDER_OUTPUT: Retryability.NON_RETRYABLE,
        FailureCode.WRONG_TOOL_OUTPUT: Retryability.NON_RETRYABLE,
        FailureCode.DUPLICATE_TERMINAL_OUTPUT: Retryability.NON_RETRYABLE,
        FailureCode.DEADLINE_EXCEEDED: Retryability.NON_RETRYABLE,
        FailureCode.CANCELLED: Retryability.NON_RETRYABLE,
        FailureCode.LATE_RESPONSE_DISCARDED: Retryability.NON_RETRYABLE,
        FailureCode.INTERNAL_ERROR: Retryability.UNKNOWN,
    }
)

FAILURE_CLASS_BY_CODE: Mapping[FailureCode, FailureClass] = MappingProxyType(
    {
        FailureCode.INVALID_INVOCATION: FailureClass.VALIDATION,
        FailureCode.INVALID_CONFIG: FailureClass.CONFIGURATION,
        FailureCode.UNSUPPORTED_PROVIDER: FailureClass.CAPABILITY,
        FailureCode.UNSUPPORTED_MODEL_FAMILY: FailureClass.CAPABILITY,
        FailureCode.UNSUPPORTED_CAPABILITY: FailureClass.CAPABILITY,
        FailureCode.MISSING_SECRET: FailureClass.CREDENTIAL,
        FailureCode.SECRET_RESOLUTION_FAILED: FailureClass.CREDENTIAL,
        FailureCode.SCHEMA_NOT_FOUND: FailureClass.STRUCTURED_OUTPUT,
        FailureCode.SCHEMA_VALIDATION_FAILED: FailureClass.STRUCTURED_OUTPUT,
        FailureCode.POLICY_VIOLATION: FailureClass.POLICY,
        FailureCode.BUDGET_VIOLATION: FailureClass.POLICY,
        FailureCode.NO_ELIGIBLE_ENDPOINT: FailureClass.ROUTING,
        FailureCode.ENDPOINT_SUPPRESSED: FailureClass.ROUTING,
        FailureCode.POOL_EXHAUSTED: FailureClass.ROUTING,
        FailureCode.PROVIDER_RATE_LIMITED: FailureClass.PROVIDER_AVAILABILITY,
        FailureCode.PROVIDER_QUOTA_EXHAUSTED: FailureClass.PROVIDER_AVAILABILITY,
        FailureCode.PROVIDER_TIMEOUT: FailureClass.PROVIDER_AVAILABILITY,
        FailureCode.PROVIDER_TRANSIENT_ERROR: FailureClass.PROVIDER_AVAILABILITY,
        FailureCode.PROVIDER_NON_RETRYABLE_ERROR: FailureClass.PROVIDER_CONTRACT,
        FailureCode.PROVIDER_REFUSAL: FailureClass.STRUCTURED_OUTPUT,
        FailureCode.MALFORMED_PROVIDER_OUTPUT: FailureClass.STRUCTURED_OUTPUT,
        FailureCode.WRONG_TOOL_OUTPUT: FailureClass.STRUCTURED_OUTPUT,
        FailureCode.DUPLICATE_TERMINAL_OUTPUT: FailureClass.STRUCTURED_OUTPUT,
        FailureCode.DEADLINE_EXCEEDED: FailureClass.DEADLINE,
        FailureCode.CANCELLED: FailureClass.CANCELLATION,
        FailureCode.LATE_RESPONSE_DISCARDED: FailureClass.DEADLINE,
        FailureCode.INTERNAL_ERROR: FailureClass.INTERNAL,
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
            policy_fingerprint=policy_fingerprint,
            elapsed_ms=elapsed_ms,
            attempt_trace=trace,
        ),
    )
