"""Terminal result and provider outcome normalization."""

from __future__ import annotations

from collections.abc import Mapping

from llm_endpoint.adapters import ProviderOutcome, ProviderOutcomeKind
from llm_endpoint.results import FailureCode, PlainTextResult, TerminalResult, TypedFailure, failure

NORMALIZER_VERSION = "v1"

_FAILURE_MESSAGES: Mapping[FailureCode, str] = {
    FailureCode.INVOCATION_RATE_LIMITED: "provider rate limited the request",
    FailureCode.INVOCATION_QUOTA_EXHAUSTED: "provider quota is exhausted",
    FailureCode.LOCAL_CANDIDATE_TIMEOUT: "provider attempt timed out",
    FailureCode.TRANSIENT_NETWORK: "provider returned a retryable transient error",
    FailureCode.PROVIDER_FAILURE: "provider returned a non-retryable error",
    FailureCode.STRUCTURED_OUTPUT_REFUSAL: "provider refused the request",
    FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD: "provider output could not be normalized",
    FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD: "provider returned the wrong terminal tool",
    FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD: "provider returned duplicate terminal outputs",
    FailureCode.CANCELLED: "provider attempt was cancelled",
    FailureCode.PROVIDER_FAILURE: "provider returned a non-retryable error",
}


def normalize_provider_outcome(
    outcome: ProviderOutcome,
    *,
    operation_invocation_id: str,
    role: str | None = None,
    operation_ref: str | None = None,
    policy_fingerprint: str | None = None,
    attempt_trace_id: str | None = None,
    plain_text_allowed: bool = True,
) -> TerminalResult:
    """Convert one adapter outcome into exactly one public terminal result."""

    if outcome.kind is ProviderOutcomeKind.SUCCESS:
        return _normalize_success(
            outcome,
            operation_invocation_id=operation_invocation_id,
            policy_fingerprint=policy_fingerprint,
            plain_text_allowed=plain_text_allowed,
        )

    if outcome.failure_code is None:
        return failure(
            code=FailureCode.PROVIDER_FAILURE,
            message="provider failure outcome omitted a failure code",
            operation_invocation_id=operation_invocation_id,
            role=role,
            operation_ref=operation_ref,
            endpoint_uid=outcome.endpoint_uid,
            policy_fingerprint=policy_fingerprint,
            elapsed_ms=outcome.elapsed_ms,
            attempt_trace_id=attempt_trace_id,
        )

    return failure(
        code=outcome.failure_code,
        message=_FAILURE_MESSAGES.get(outcome.failure_code, outcome.failure_code.value),
        operation_invocation_id=operation_invocation_id,
        role=role,
        operation_ref=operation_ref,
        endpoint_uid=outcome.endpoint_uid,
        policy_fingerprint=policy_fingerprint,
        elapsed_ms=outcome.elapsed_ms,
        attempt_trace_id=attempt_trace_id,
        safe_context=_provider_status_context(outcome.safe_provider_status),
    )


def is_retryable_provider_outcome(outcome: ProviderOutcome) -> bool:
    """Return whether an adapter outcome is retryable after public normalization."""

    if outcome.kind is ProviderOutcomeKind.SUCCESS:
        return False
    normalized = normalize_provider_outcome(
        outcome,
        operation_invocation_id="retryability-classification",
    )
    return isinstance(normalized, TypedFailure) and normalized.is_retryable


def _normalize_success(
    outcome: ProviderOutcome,
    *,
    operation_invocation_id: str,
    policy_fingerprint: str | None,
    plain_text_allowed: bool,
) -> TerminalResult:
    if outcome.payload is None:
        return failure(
            code=FailureCode.PROVIDER_FAILURE,
            message="provider success outcome omitted payload",
            operation_invocation_id=operation_invocation_id,
            endpoint_uid=outcome.endpoint_uid,
            policy_fingerprint=policy_fingerprint,
            elapsed_ms=outcome.elapsed_ms,
        )

    if isinstance(outcome.payload.content, str):
        if not plain_text_allowed:
            return failure(
                code=FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD,
                message="plain text provider output is not allowed for this operation",
                operation_invocation_id=operation_invocation_id,
                endpoint_uid=outcome.endpoint_uid,
                policy_fingerprint=policy_fingerprint,
                elapsed_ms=outcome.elapsed_ms,
                safe_context=_provider_status_context(outcome.safe_provider_status),
            )
        return PlainTextResult(
            text=outcome.payload.content,
            operation_invocation_id=operation_invocation_id,
            endpoint_uid=outcome.endpoint_uid,
            policy_fingerprint=policy_fingerprint or "",
            elapsed_ms=outcome.elapsed_ms,
        )

    return failure(
        code=FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD,
        message="structured provider output requires the structured-output pipeline",
        operation_invocation_id=operation_invocation_id,
        endpoint_uid=outcome.endpoint_uid,
        policy_fingerprint=policy_fingerprint,
        elapsed_ms=outcome.elapsed_ms,
        safe_context=_provider_status_context(outcome.safe_provider_status),
    )


def _provider_status_context(status: Mapping[str, str]) -> Mapping[str, str]:
    return {f"provider_status.{key}": value for key, value in status.items()}
