from typing import get_args

import pytest

import llm_endpoint
from llm_endpoint.adapters import ProviderOutcomeKind, provider_failure, provider_success
from llm_endpoint.normalization import normalize_provider_outcome
from llm_endpoint.results import (
    FAILURE_CLASS_BY_CODE,
    RETRYABILITY_BY_CODE,
    FailureCode,
    PlainTextResult,
    Retryability,
    StructuredResult,
    TerminalResult,
    TypedFailure,
    failure,
)


def test_terminal_result_alias_is_public_union() -> None:
    assert llm_endpoint.TerminalResult is TerminalResult
    assert set(get_args(TerminalResult)) == {StructuredResult, PlainTextResult, TypedFailure}


def test_failure_codes_are_public() -> None:
    expected_codes = {
        "llm.config.invalid_endpoint_config",
        "llm.config.credential_unavailable",
        "llm.endpoint.unknown_role",
        "llm.endpoint.unknown_entrypoint",
        "llm.endpoint.unsupported_provider_format",
        "llm.endpoint.suppressed",
        "llm.endpoint.unsupported_runtime_knob",
        "llm.policy.capability_mismatch",
        "llm.policy.unsupported_reasoning_mode",
        "llm.policy.output_budget_exceeds_hard_cap",
        "llm.policy.candidate_budget_unallocatable",
        "llm.policy.operation_ref_required",
        "llm.input.invalid_messages",
        "llm.input.cancelled",
        "llm.schema.missing_contract",
        "llm.schema.unknown_contract",
        "llm.structured_output.invalid_payload",
        "llm.structured_output.refusal",
        "llm.invocation.rate_limited",
        "llm.invocation.quota_exhausted",
        "llm.invocation.transient_network",
        "llm.invocation.provider_5xx",
        "llm.invocation.provider_failure",
        "llm.invocation.local_candidate_timeout",
        "llm.invocation.late_response_discarded",
        "llm.deadline.exceeded",
        "llm.pool.no_eligible_candidate",
        "llm.pool.exhausted",
        "llm.smoke.skipped",
        "llm.smoke.failed",
        "llm.budget.violation",
        "llm.module.unsupported_version",
    }

    assert {code.value for code in FailureCode} == expected_codes
    assert set(RETRYABILITY_BY_CODE) == set(FailureCode)
    assert set(FAILURE_CLASS_BY_CODE) == set(FailureCode)
    assert RETRYABILITY_BY_CODE[FailureCode.LOCAL_CANDIDATE_TIMEOUT] is Retryability.RETRYABLE
    assert RETRYABILITY_BY_CODE[FailureCode.STRUCTURED_OUTPUT_REFUSAL] is Retryability.NON_RETRYABLE


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
        code=FailureCode.LOCAL_CANDIDATE_TIMEOUT,
        message="provider timed out",
        operation_invocation_id="inv-3",
        role="writer",
        operation_ref="draft",
        endpoint_uid="endpoint-a",
        schema_contract_ref="schema://answer/v1",
        schema_fingerprint="sha256:answer",
        schema_resolution_status="resolved",
        policy_fingerprint="policy-1",
        elapsed_ms=1_000,
        attempt_trace_id="trace-1",
        safe_context={"provider_status": "timeout"},
    )

    assert typed_failure.is_retryable is True
    assert typed_failure.context.attempt_trace is not None
    assert typed_failure.context.schema_contract_ref == "schema://answer/v1"
    assert typed_failure.context.schema_fingerprint == "sha256:answer"
    assert typed_failure.context.schema_resolution_status == "resolved"
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
            failure_code=FailureCode.LOCAL_CANDIDATE_TIMEOUT,
            safe_provider_status={"status": "timeout"},
        ),
        operation_invocation_id="inv-5",
        role="writer",
        operation_ref="draft",
        policy_fingerprint="policy-1",
        attempt_trace_id="trace-1",
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.LOCAL_CANDIDATE_TIMEOUT
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
    assert result.code is FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD
