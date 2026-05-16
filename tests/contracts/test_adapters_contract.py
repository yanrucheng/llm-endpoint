import pytest

from llm_endpoint.adapters import (
    AdapterInvocationPlan,
    FakeProviderAdapter,
    ProviderOutcomeKind,
    execute_provider_attempt,
    provider_failure,
    provider_success,
)
from llm_endpoint.callbacks import missing_secret, resolved_secret
from llm_endpoint.config import ProviderFormat, StructuredOutputMode
from llm_endpoint.results import FailureCode, TypedFailure
from llm_endpoint.telemetry import TokenUsage


def test_provider_success_contract() -> None:
    plan = AdapterInvocationPlan(
        endpoint_uid="primary",
        provider_format=ProviderFormat.FAKE,
        model_family="fake-family",
        model="fake-model",
        operation_invocation_id="inv-1",
        messages=({"role": "user", "content": "safe payload owned by host"},),
        deadline_ms=1_000,
        candidate_budget_ms=800,
        schema_mode=StructuredOutputMode.JSON_SCHEMA,
        credential_ref="secret://primary",
        schema_contract_ref="schema://answer",
        policy_fingerprint="policy-1",
    )
    outcome = provider_success(
        endpoint_uid=plan.endpoint_uid,
        elapsed_ms=10,
        content={"answer": "ok"},
        finish_reason="stop",
        safe_provider_status={"status": "ok"},
        token_usage=TokenUsage(input_tokens=3, output_tokens=2, total_tokens=5),
    )

    assert outcome.kind is ProviderOutcomeKind.SUCCESS
    assert outcome.payload is not None
    assert outcome.payload.content == {"answer": "ok"}
    assert outcome.failure_code is None


def test_raw_provider_status_fields_are_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden fields"):
        provider_success(
            endpoint_uid="primary",
            elapsed_ms=10,
            content="ok",
            safe_provider_status={"raw_response": "do not emit"},
        )


def test_provider_failure_requires_failure_code() -> None:
    outcome = provider_failure(
        kind=ProviderOutcomeKind.TIMEOUT,
        endpoint_uid="primary",
        elapsed_ms=1_000,
        failure_code=FailureCode.PROVIDER_TIMEOUT,
        safe_provider_status={"status": "timeout"},
    )

    assert outcome.kind is ProviderOutcomeKind.TIMEOUT
    assert outcome.failure_code is FailureCode.PROVIDER_TIMEOUT


def test_execute_provider_attempt_resolves_credentials_and_token_usage() -> None:
    plan = AdapterInvocationPlan(
        endpoint_uid="primary",
        provider_format=ProviderFormat.FAKE,
        model_family="fake-family",
        model="fake-model",
        operation_invocation_id="inv-2",
        messages=({"role": "user", "content": "safe payload owned by host"},),
        deadline_ms=1_000,
        candidate_budget_ms=800,
        credential_ref="secret://primary",
        policy_fingerprint="policy-1",
    )
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(
                    endpoint_uid="primary",
                    elapsed_ms=11,
                    content="ok",
                    token_usage=TokenUsage(input_tokens=7, output_tokens=3, total_tokens=10),
                ),
            )
        }
    )

    outcome = execute_provider_attempt(
        plan=plan,
        adapter=adapter,
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    assert not isinstance(outcome, TypedFailure)
    assert outcome.kind is ProviderOutcomeKind.SUCCESS
    assert outcome.token_usage == TokenUsage(input_tokens=7, output_tokens=3, total_tokens=10)
    assert adapter.calls_by_endpoint == {"primary": 1}


def test_execute_provider_attempt_missing_secret_is_typed_failure() -> None:
    result = execute_provider_attempt(
        plan=AdapterInvocationPlan(
            endpoint_uid="primary",
            provider_format=ProviderFormat.FAKE,
            model_family="fake-family",
            model="fake-model",
            operation_invocation_id="inv-3",
            messages=({"role": "user", "content": "safe payload owned by host"},),
            deadline_ms=1_000,
            candidate_budget_ms=800,
            credential_ref="secret://primary",
        ),
        adapter=FakeProviderAdapter({}),
        secret_resolver=missing_secret,
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.MISSING_SECRET
    assert result.diagnostics.safe_context["secret_ref"] == "secret://primary"


def test_execute_provider_attempt_resolver_exception_is_redacted() -> None:
    def broken_resolver(ref: str):
        raise RuntimeError(f"do not leak {ref} credential")

    result = execute_provider_attempt(
        plan=AdapterInvocationPlan(
            endpoint_uid="primary",
            provider_format=ProviderFormat.FAKE,
            model_family="fake-family",
            model="fake-model",
            operation_invocation_id="inv-4",
            messages=({"role": "user", "content": "safe payload owned by host"},),
            deadline_ms=1_000,
            candidate_budget_ms=800,
            credential_ref="secret://primary",
        ),
        adapter=FakeProviderAdapter({}),
        secret_resolver=broken_resolver,
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.SECRET_RESOLUTION_FAILED
    assert result.diagnostics.safe_context == {
        "secret_ref": "secret://primary",
        "resolver_exception": "RuntimeError",
    }
