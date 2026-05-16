"""Provider adapter extension contracts, execution, and normalized outcomes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Protocol

from llm_endpoint.callbacks import SecretResolutionStatus, SecretResolver, SecretValue
from llm_endpoint.config import ProviderFormat, StructuredOutputMode
from llm_endpoint.results import FailureCode, TypedFailure, failure
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
    credential: SecretValue | None = None
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


@dataclass(slots=True)
class FakeProviderAdapter:
    """Deterministic provider-format adapter for offline execution contracts."""

    outcomes_by_endpoint: Mapping[str, Sequence[ProviderOutcome]]
    provider_format: ProviderFormat = field(default=ProviderFormat.FAKE, init=False)
    calls_by_endpoint: dict[str, int] = field(default_factory=dict, init=False)

    def invoke(self, plan: AdapterInvocationPlan) -> ProviderOutcome:
        if plan.provider_format is not ProviderFormat.FAKE:
            return provider_failure(
                kind=ProviderOutcomeKind.NON_RETRYABLE_FAILURE,
                endpoint_uid=plan.endpoint_uid,
                elapsed_ms=0,
                failure_code=FailureCode.UNSUPPORTED_PROVIDER,
                safe_provider_status={"adapter": "fake_provider_format_mismatch"},
            )

        outcomes = self.outcomes_by_endpoint.get(plan.endpoint_uid, ())
        call_index = self.calls_by_endpoint.get(plan.endpoint_uid, 0)
        self.calls_by_endpoint[plan.endpoint_uid] = call_index + 1
        if call_index >= len(outcomes):
            return provider_failure(
                kind=ProviderOutcomeKind.NON_RETRYABLE_FAILURE,
                endpoint_uid=plan.endpoint_uid,
                elapsed_ms=0,
                failure_code=FailureCode.PROVIDER_NON_RETRYABLE_ERROR,
                safe_provider_status={"adapter": "fake_outcome_missing"},
            )
        return outcomes[call_index]


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


def execute_provider_attempt(
    *,
    plan: AdapterInvocationPlan,
    adapter: ProviderAdapter,
    secret_resolver: SecretResolver | None = None,
) -> ProviderOutcome | TypedFailure:
    """Resolve credentials, invoke one adapter, and keep raw provider errors private."""

    credential_or_failure = _resolve_credential(plan, secret_resolver)
    if isinstance(credential_or_failure, TypedFailure):
        return credential_or_failure

    resolved_plan = (
        replace(plan, credential=credential_or_failure)
        if credential_or_failure is not None
        else plan
    )
    if adapter.provider_format is not resolved_plan.provider_format:
        return failure(
            code=FailureCode.UNSUPPORTED_PROVIDER,
            message="adapter provider_format does not match endpoint provider_format",
            operation_invocation_id=resolved_plan.operation_invocation_id,
            endpoint_uid=resolved_plan.endpoint_uid,
            policy_fingerprint=resolved_plan.policy_fingerprint,
        )

    try:
        outcome = adapter.invoke(resolved_plan)
    except Exception as exc:  # pragma: no cover - adapter implementation is external.
        return provider_failure(
            kind=ProviderOutcomeKind.NON_RETRYABLE_FAILURE,
            endpoint_uid=resolved_plan.endpoint_uid,
            elapsed_ms=0,
            failure_code=FailureCode.PROVIDER_NON_RETRYABLE_ERROR,
            safe_provider_status={"adapter_exception": exc.__class__.__name__},
        )

    if outcome.endpoint_uid != resolved_plan.endpoint_uid:
        return failure(
            code=FailureCode.PROVIDER_NON_RETRYABLE_ERROR,
            message="adapter returned outcome for a different endpoint_uid",
            operation_invocation_id=resolved_plan.operation_invocation_id,
            endpoint_uid=resolved_plan.endpoint_uid,
            policy_fingerprint=resolved_plan.policy_fingerprint,
        )
    return outcome


def _resolve_credential(
    plan: AdapterInvocationPlan,
    secret_resolver: SecretResolver | None,
) -> SecretValue | None | TypedFailure:
    if plan.credential_ref is None:
        return None
    if secret_resolver is None:
        return failure(
            code=FailureCode.MISSING_SECRET,
            message="secret resolver is required for endpoint credential_ref",
            operation_invocation_id=plan.operation_invocation_id,
            endpoint_uid=plan.endpoint_uid,
            policy_fingerprint=plan.policy_fingerprint,
            safe_context={"secret_ref": plan.credential_ref},
        )

    try:
        resolution = secret_resolver(plan.credential_ref)
    except Exception as exc:  # pragma: no cover - callback implementation is host-owned.
        return failure(
            code=FailureCode.SECRET_RESOLUTION_FAILED,
            message="secret resolver raised during credential resolution",
            operation_invocation_id=plan.operation_invocation_id,
            endpoint_uid=plan.endpoint_uid,
            policy_fingerprint=plan.policy_fingerprint,
            safe_context={
                "secret_ref": plan.credential_ref,
                "resolver_exception": exc.__class__.__name__,
            },
        )
    if resolution.ref != plan.credential_ref:
        return failure(
            code=FailureCode.SECRET_RESOLUTION_FAILED,
            message="secret resolver returned a mismatched ref",
            operation_invocation_id=plan.operation_invocation_id,
            endpoint_uid=plan.endpoint_uid,
            policy_fingerprint=plan.policy_fingerprint,
            safe_context={
                "expected_secret_ref": plan.credential_ref,
                "actual_secret_ref": resolution.ref,
            },
        )
    if resolution.status is not SecretResolutionStatus.RESOLVED:
        return resolution.to_failure(
            operation_invocation_id=plan.operation_invocation_id,
            endpoint_uid=plan.endpoint_uid,
        )
    if resolution.secret is None:
        return failure(
            code=FailureCode.SECRET_RESOLUTION_FAILED,
            message="secret resolver returned resolved status without a secret",
            operation_invocation_id=plan.operation_invocation_id,
            endpoint_uid=plan.endpoint_uid,
            policy_fingerprint=plan.policy_fingerprint,
            safe_context={"secret_ref": plan.credential_ref},
        )
    return resolution.secret
