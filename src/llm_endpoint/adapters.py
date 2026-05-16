"""Provider adapter extension contracts and normalized outcomes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from llm_endpoint.config import ProviderFormat, StructuredOutputMode
from llm_endpoint.results import FailureCode
from llm_endpoint.telemetry import TokenUsage, forbidden_attribute_keys

PROVIDER_ADAPTER_CONTRACT_VERSION = "v1"

FORBIDDEN_PROVIDER_STATUS_FIELDS = frozenset(
    {"api_key", "authorization", "body", "credential", "headers", "raw_request", "raw_response"}
)


class ProviderOutcomeKind(StrEnum):
    """Normalized provider outcomes returned by adapters."""

    SUCCESS = "success"
    REFUSAL = "refusal"
    RETRYABLE_FAILURE = "retryable_failure"
    NON_RETRYABLE_FAILURE = "non_retryable_failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AdapterInvocationPlan:
    """Normalized input passed from routing/runtime policy into one adapter attempt."""

    endpoint_uid: str
    provider_format: ProviderFormat
    model_family: str
    model: str
    operation_invocation_id: str
    messages: Sequence[Mapping[str, Any]]
    deadline_ms: int
    candidate_budget_ms: int
    schema_mode: StructuredOutputMode = StructuredOutputMode.NONE
    credential_ref: str | None = None
    schema_contract_ref: str | None = None
    policy_fingerprint: str | None = None
    request_metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.endpoint_uid:
            raise ValueError("endpoint_uid is required")
        if not self.operation_invocation_id:
            raise ValueError("operation_invocation_id is required")
        if self.deadline_ms <= 0 or self.candidate_budget_ms <= 0:
            raise ValueError("deadline and candidate budgets must be positive")
        if self.candidate_budget_ms > self.deadline_ms:
            raise ValueError("candidate_budget_ms cannot exceed deadline_ms")


@dataclass(frozen=True, slots=True)
class ProviderSuccessPayload:
    """Adapter success payload before result/schema normalization."""

    content: str | Mapping[str, Any]
    finish_reason: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    """Public adapter output with raw provider details normalized away."""

    kind: ProviderOutcomeKind
    endpoint_uid: str
    elapsed_ms: int
    payload: ProviderSuccessPayload | None = None
    failure_code: FailureCode | None = None
    safe_provider_status: Mapping[str, str] = field(default_factory=dict)
    token_usage: TokenUsage | None = None
    contract_version: str = PROVIDER_ADAPTER_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != PROVIDER_ADAPTER_CONTRACT_VERSION:
            raise ValueError("only provider adapter contract version 'v1' is supported")
        if not self.endpoint_uid:
            raise ValueError("endpoint_uid is required")
        if self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must be non-negative")
        if self.kind is ProviderOutcomeKind.SUCCESS:
            if self.payload is None or self.failure_code is not None:
                raise ValueError("success outcomes require payload and no failure_code")
        elif self.failure_code is None:
            raise ValueError("failure-like outcomes require failure_code")

        unsafe = forbidden_attribute_keys(self.safe_provider_status)
        unsafe |= frozenset(
            key
            for key in self.safe_provider_status
            if key.lower() in FORBIDDEN_PROVIDER_STATUS_FIELDS
        )
        if unsafe:
            names = ", ".join(sorted(unsafe))
            raise ValueError(f"provider status contains forbidden fields: {names}")


class ProviderAdapter(Protocol):
    """Provider-format extension boundary implemented by adapter owners."""

    provider_format: ProviderFormat

    def invoke(self, plan: AdapterInvocationPlan) -> ProviderOutcome: ...


def provider_success(
    *,
    endpoint_uid: str,
    elapsed_ms: int,
    content: str | Mapping[str, Any],
    finish_reason: str | None = None,
    tool_name: str | None = None,
    safe_provider_status: Mapping[str, str] | None = None,
    token_usage: TokenUsage | None = None,
) -> ProviderOutcome:
    """Build a normalized success outcome."""

    return ProviderOutcome(
        kind=ProviderOutcomeKind.SUCCESS,
        endpoint_uid=endpoint_uid,
        elapsed_ms=elapsed_ms,
        payload=ProviderSuccessPayload(
            content=content,
            finish_reason=finish_reason,
            tool_name=tool_name,
        ),
        safe_provider_status=safe_provider_status or {},
        token_usage=token_usage,
    )


def provider_failure(
    *,
    kind: ProviderOutcomeKind,
    endpoint_uid: str,
    elapsed_ms: int,
    failure_code: FailureCode,
    safe_provider_status: Mapping[str, str] | None = None,
    token_usage: TokenUsage | None = None,
) -> ProviderOutcome:
    """Build a normalized non-success adapter outcome."""

    if kind is ProviderOutcomeKind.SUCCESS:
        raise ValueError("provider_failure cannot build success outcomes")
    return ProviderOutcome(
        kind=kind,
        endpoint_uid=endpoint_uid,
        elapsed_ms=elapsed_ms,
        failure_code=failure_code,
        safe_provider_status=safe_provider_status or {},
        token_usage=token_usage,
    )
