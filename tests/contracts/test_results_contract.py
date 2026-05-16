import pytest

from llm_endpoint.adapters import ProviderOutcomeKind, provider_failure, provider_success
from llm_endpoint.normalization import normalize_provider_outcome
from llm_endpoint.results import (
    FAILURE_CLASS_BY_CODE,
    RETRYABILITY_BY_CODE,
    FailureCode,
    PlainTextResult,
    Retryability,
    StructuredResult,
    TypedFailure,
    failure,
)


def test_failure_codes_are_public() -> None:
    assert set(RETRYABILITY_BY_CODE) == set(FailureCode)
    assert set(FAILURE_CLASS_BY_CODE) == set(FailureCode)
    assert RETRYABILITY_BY_CODE[FailureCode.PROVIDER_TIMEOUT] is Retryability.RETRYABLE
    assert RETRYABILITY_BY_CODE[FailureCode.PROVIDER_REFUSAL] is Retryability.NON_RETRYABLE


def test_success_result_contracts() -> None:
    structured = StructuredResult(
        value={"answer": "ok"},
        schema_name="answer",
        schema_version="1",
        schema_fingerprint="sha256:abc",
        operation_invocation_id="inv-1",
        endpoint_uid="endpoint-a",
        policy_fingerprint="policy-1",
        elapsed_ms=12,
    )
    text = PlainTextResult(
        text="ok",
        operation_invocation_id="inv-2",
        endpoint_uid="endpoint-a",
        policy_fingerprint="policy-1",
        elapsed_ms=13,
    )

    assert structured.value["answer"] == "ok"
    assert text.text == "ok"


def test_failure_contract_is_safe() -> None:
    typed_failure = failure(
        code=FailureCode.PROVIDER_TIMEOUT,
        message="provider timed out",
        operation_invocation_id="inv-3",
        role="writer",
        operation_ref="draft",
        endpoint_uid="endpoint-a",
        policy_fingerprint="policy-1",
        elapsed_ms=1_000,
        attempt_trace_id="trace-1",
        safe_context={"provider_status": "timeout"},
    )

    assert typed_failure.is_retryable is True
    assert typed_failure.context.attempt_trace is not None
    assert typed_failure.diagnostics.safe_context == {"provider_status": "timeout"}


def test_structured_result_requires_schema_identity() -> None:
    with pytest.raises(ValueError, match="schema identity"):
        StructuredResult(
            value={},
            schema_name="",
            schema_version="1",
            schema_fingerprint="sha256:abc",
            operation_invocation_id="inv-4",
            endpoint_uid="endpoint-a",
            policy_fingerprint="policy-1",
            elapsed_ms=0,
        )


def test_provider_failure_normalization() -> None:
    result = normalize_provider_outcome(
        provider_failure(
            kind=ProviderOutcomeKind.TIMEOUT,
            endpoint_uid="primary",
            elapsed_ms=120,
            failure_code=FailureCode.PROVIDER_TIMEOUT,
            safe_provider_status={"status": "timeout"},
        ),
        operation_invocation_id="inv-5",
        role="writer",
        operation_ref="draft",
        policy_fingerprint="policy-1",
        attempt_trace_id="trace-1",
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.PROVIDER_TIMEOUT
    assert result.is_retryable is True
    assert result.diagnostics.safe_context == {"provider_status.status": "timeout"}


def test_structured_payload_requires_pipeline() -> None:
    result = normalize_provider_outcome(
        provider_success(
            endpoint_uid="primary",
            elapsed_ms=12,
            content={"answer": "ok"},
        ),
        operation_invocation_id="inv-6",
        policy_fingerprint="policy-1",
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.MALFORMED_PROVIDER_OUTPUT
