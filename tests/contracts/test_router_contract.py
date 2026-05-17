from collections.abc import Mapping

from llm_endpoint.adapters import (
    FakeProviderAdapter,
    ProviderAdapter,
    ProviderOutcomeKind,
    provider_failure,
    provider_success,
)
from llm_endpoint.callbacks import resolved_secret
from llm_endpoint.config import (
    EndpointConfig,
    EndpointPool,
    LLMEndpointConfig,
    OperationConfig,
    OperationRuntimePolicy,
    ProviderFormat,
    Registry,
    RetryPolicy,
    RoleConfig,
    StructuredOutputMode,
    build_registry,
)
from llm_endpoint.invocation import InvocationPlan, InvocationRequest, invoke_plan
from llm_endpoint.results import FailureCode, PlainTextResult, TypedFailure
from llm_endpoint.router import AttemptStatus, route_invocation
from llm_endpoint.telemetry import TelemetryEventFamily, TokenUsage


def test_ordered_retryable_failover() -> None:
    registry = build_registry(_config(max_attempts=2))
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_failure(
                    kind=ProviderOutcomeKind.TIMEOUT,
                    endpoint_uid="primary",
                    elapsed_ms=500,
                    failure_code=FailureCode.LOCAL_CANDIDATE_TIMEOUT,
                    safe_provider_status={"status": "timeout"},
                ),
            ),
            "fallback": (
                provider_success(
                    endpoint_uid="fallback",
                    elapsed_ms=120,
                    content="ok",
                    token_usage=TokenUsage(input_tokens=5, output_tokens=2, total_tokens=7),
                ),
            ),
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters=_adapter_map(adapter),
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    assert isinstance(result.terminal_result, PlainTextResult)
    assert result.terminal_result.endpoint_uid == "fallback"
    assert [trace.endpoint_uid for trace in result.attempt_traces] == ["primary", "fallback"]
    assert [trace.status for trace in result.attempt_traces] == [
        AttemptStatus.RETRYABLE_FAILURE,
        AttemptStatus.SUCCESS,
    ]
    assert [event.family for event in result.telemetry] == [
        TelemetryEventFamily.POOL_ATTEMPT,
        TelemetryEventFamily.POOL_ATTEMPT,
        TelemetryEventFamily.SUCCESS,
    ]
    assert result.telemetry[-1].token_usage == TokenUsage(
        input_tokens=5,
        output_tokens=2,
        total_tokens=7,
    )


def test_suppression_skip_preserves_last_eligible_candidate() -> None:
    registry = build_registry(_config(max_attempts=2))
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "fallback": (
                provider_success(endpoint_uid="fallback", elapsed_ms=100, content="ok"),
            )
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters=_adapter_map(adapter),
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
        suppressed_endpoint_reasons={
            "primary": "maintenance",
            "fallback": "fallback_only",
        },
    )

    assert isinstance(result.terminal_result, PlainTextResult)
    assert [trace.status for trace in result.attempt_traces] == [
        AttemptStatus.SKIPPED_SUPPRESSED,
        AttemptStatus.SUCCESS,
    ]
    assert result.attempt_traces[0].skip_reason == "maintenance"
    assert result.attempt_traces[1].suppression_protected is True
    assert [event.family for event in result.telemetry] == [
        TelemetryEventFamily.ENDPOINT_SUPPRESSED,
        TelemetryEventFamily.POOL_ATTEMPT,
        TelemetryEventFamily.SUCCESS,
    ]


def test_non_retryable_failure_stops_pool() -> None:
    registry = build_registry(_config(max_attempts=2))
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_failure(
                    kind=ProviderOutcomeKind.NON_RETRYABLE_FAILURE,
                    endpoint_uid="primary",
                    elapsed_ms=20,
                    failure_code=FailureCode.PROVIDER_FAILURE,
                    safe_provider_status={"status": "bad_request"},
                ),
            ),
            "fallback": (provider_success(endpoint_uid="fallback", elapsed_ms=100, content="ok"),),
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters=_adapter_map(adapter),
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.PROVIDER_FAILURE
    assert result.terminal_result.code.value == "llm.invocation.provider_failure"
    assert [trace.endpoint_uid for trace in result.attempt_traces] == ["primary"]
    assert adapter.calls_by_endpoint == {"primary": 1}


def test_missing_provider_adapter_returns_endpoint_code() -> None:
    registry = build_registry(_config(max_attempts=1))
    plan = _plan(registry)

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.UNSUPPORTED_PROVIDER_FORMAT
    assert result.terminal_result.code.value == "llm.endpoint.unsupported_provider_format"
    assert result.terminal_result.context.endpoint_uid == "primary"


def test_pool_exhaustion_is_typed_failure() -> None:
    registry = build_registry(_config(max_attempts=2))
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_failure(
                    kind=ProviderOutcomeKind.TIMEOUT,
                    endpoint_uid="primary",
                    elapsed_ms=500,
                    failure_code=FailureCode.LOCAL_CANDIDATE_TIMEOUT,
                ),
            ),
            "fallback": (
                provider_failure(
                    kind=ProviderOutcomeKind.RETRYABLE_FAILURE,
                    endpoint_uid="fallback",
                    elapsed_ms=700,
                    failure_code=FailureCode.TRANSIENT_NETWORK,
                ),
            ),
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters=_adapter_map(adapter),
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.POOL_EXHAUSTED
    assert result.terminal_result.code.value == "llm.pool.exhausted"
    assert result.terminal_result.diagnostics.safe_context == {
        "attempt_count": "2",
        "skipped_count": "0",
        "last_retryable_failure": "llm.invocation.transient_network",
    }
    assert [trace.status for trace in result.attempt_traces] == [
        AttemptStatus.RETRYABLE_FAILURE,
        AttemptStatus.RETRYABLE_FAILURE,
    ]
    assert result.telemetry[-1].family is TelemetryEventFamily.POOL_EXHAUSTED


def test_per_uid_budget_overrides_apply_and_fallback_to_base() -> None:
    registry = build_registry(
        _config(
            max_attempts=2,
            candidate_budget_overrides_ms={"primary": 6_000},
            protect_last_eligible=False,
        )
    )
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_failure(
                    kind=ProviderOutcomeKind.TIMEOUT,
                    endpoint_uid="primary",
                    elapsed_ms=500,
                    failure_code=FailureCode.LOCAL_CANDIDATE_TIMEOUT,
                ),
            ),
            "fallback": (
                provider_success(endpoint_uid="fallback", elapsed_ms=100, content="ok"),
            ),
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters=_adapter_map(adapter),
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    assert isinstance(result.terminal_result, PlainTextResult)
    assert [trace.endpoint_uid for trace in result.attempt_traces] == ["primary", "fallback"]
    assert [trace.candidate_budget_ms for trace in result.attempt_traces] == [6_000, 4_000]


def test_protect_last_eligible_reserves_next_candidate_override() -> None:
    registry = build_registry(
        _config(
            max_attempts=1,
            candidate_budget_overrides_ms={"primary": 6_000, "fallback": 7_000},
            protect_last_eligible=True,
        )
    )
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(endpoint_uid="primary", elapsed_ms=100, content="ok"),
            ),
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters=_adapter_map(adapter),
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    assert isinstance(result.terminal_result, PlainTextResult)
    assert result.attempt_traces[0].endpoint_uid == "primary"
    assert result.attempt_traces[0].candidate_budget_ms == 3_000


def test_late_response_discard_uses_per_uid_budget() -> None:
    registry = build_registry(
        _config(
            max_attempts=1,
            candidate_budget_ms=6_000,
            candidate_budget_overrides_ms={"primary": 4_500},
            protect_last_eligible=False,
        )
    )
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(endpoint_uid="primary", elapsed_ms=5_000, content="too late"),
            ),
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters=_adapter_map(adapter),
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.LATE_RESPONSE_DISCARDED
    assert result.attempt_traces[0].candidate_budget_ms == 4_500
    assert result.telemetry[1].family is TelemetryEventFamily.LATE_RESPONSE_DISCARDED


def _plan(registry: Registry) -> InvocationPlan:
    result = invoke_plan(
        request=InvocationRequest(
            role="writer",
            operation_ref="draft",
            messages=({"role": "user", "content": "draft this"},),
            deadline_ms=10_000,
            operation_invocation_id="inv-router",
        ),
        registry=registry,
    )
    assert isinstance(result, InvocationPlan)
    return result


def _adapter_map(adapter: ProviderAdapter) -> dict[ProviderFormat | str, ProviderAdapter]:
    return {ProviderFormat.FAKE: adapter}


def _config(
    max_attempts: int,
    *,
    candidate_budget_ms: int = 4_000,
    candidate_budget_overrides_ms: Mapping[str, int] | None = None,
    protect_last_eligible: bool = True,
) -> LLMEndpointConfig:
    return LLMEndpointConfig(
        endpoints=(
            EndpointConfig(
                uid="primary",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-model",
                credential_ref="secret://fake-primary",
            ),
            EndpointConfig(
                uid="fallback",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-model",
                credential_ref="secret://fake-fallback",
            ),
        ),
        roles=(RoleConfig(name="writer", pool=EndpointPool(("primary", "fallback"))),),
        operations=(OperationConfig(ref="draft", policy_ref="draft-policy"),),
        policies=(
            OperationRuntimePolicy(
                ref="draft-policy",
                deadline_ms=10_000,
                max_output_tokens=1_024,
                candidate_budget_ms=candidate_budget_ms,
                candidate_budget_overrides_ms=candidate_budget_overrides_ms,
                protect_last_eligible=protect_last_eligible,
                structured_output_mode=StructuredOutputMode.NONE,
                retry_policy=RetryPolicy(max_attempts=max_attempts),
            ),
        ),
    )
