from dataclasses import dataclass
from typing import NoReturn, cast

from llm_endpoint.adapters import (
    AdapterInvocationPlan,
    FakeProviderAdapter,
    ProviderOutcome,
    provider_success,
)
from llm_endpoint.callbacks import SchemaResolver, resolved_secret
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
from llm_endpoint.telemetry import TelemetryEventFamily


def test_phase_4a_plain_text_path_requires_no_schema_resolver() -> None:
    registry = build_registry(_plain_text_config())
    plan = _plan(registry, deadline_ms=10_000)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(
                    endpoint_uid="primary",
                    elapsed_ms=20,
                    content="plain response",
                ),
            )
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
        schema_resolver=cast(SchemaResolver, _fail_schema_resolution),
    )

    assert isinstance(result.terminal_result, PlainTextResult)
    assert result.terminal_result.text == "plain response"
    assert result.attempt_traces[0].status is AttemptStatus.SUCCESS
    assert [event.family for event in result.telemetry] == [
        TelemetryEventFamily.POOL_ATTEMPT,
        TelemetryEventFamily.SUCCESS,
    ]


def test_phase_4b_cancellation_stops_before_starting_attempts() -> None:
    token = MutableCancellationToken(cancelled=True)
    registry = build_registry(_plain_text_config())
    plan = _plan(registry, deadline_ms=10_000, cancellation_token=token)
    adapter = FakeProviderAdapter(
        {"primary": (provider_success(endpoint_uid="primary", elapsed_ms=20, content="late"),)}
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.CANCELLED
    assert result.attempt_traces == ()
    assert adapter.calls_by_endpoint == {}
    assert [event.family for event in result.telemetry] == [
        TelemetryEventFamily.CANCELLATION,
        TelemetryEventFamily.FAILURE,
    ]


def test_phase_4b_cancellation_after_attempt_discards_late_success_without_failover() -> None:
    token = MutableCancellationToken()
    registry = build_registry(_plain_text_config(max_attempts=2))
    plan = _plan(registry, deadline_ms=10_000, cancellation_token=token)
    adapter = CancellingSuccessAdapter(token)

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.CANCELLED
    assert [trace.endpoint_uid for trace in result.attempt_traces] == ["primary"]
    assert result.attempt_traces[0].status is AttemptStatus.CANCELLED
    assert adapter.calls == ("primary",)
    assert [event.family for event in result.telemetry] == [
        TelemetryEventFamily.POOL_ATTEMPT,
        TelemetryEventFamily.CANCELLATION,
        TelemetryEventFamily.LATE_RESPONSE_DISCARDED,
        TelemetryEventFamily.FAILURE,
    ]


def test_phase_4b_late_provider_success_is_discarded_without_failover() -> None:
    registry = build_registry(_plain_text_config(max_attempts=2, candidate_budget_ms=100))
    plan = _plan(registry, deadline_ms=10_000)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(endpoint_uid="primary", elapsed_ms=150, content="too late"),
            ),
            "fallback": (
                provider_success(endpoint_uid="fallback", elapsed_ms=20, content="fallback"),
            ),
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.LATE_RESPONSE_DISCARDED
    assert result.attempt_traces[0].status is AttemptStatus.LATE_RESPONSE_DISCARDED
    assert adapter.calls_by_endpoint == {"primary": 1}
    assert [event.family for event in result.telemetry] == [
        TelemetryEventFamily.POOL_ATTEMPT,
        TelemetryEventFamily.LATE_RESPONSE_DISCARDED,
        TelemetryEventFamily.FAILURE,
    ]


@dataclass(slots=True)
class MutableCancellationToken:
    cancelled: bool = False

    def is_cancelled(self) -> bool:
        return self.cancelled

    def cancel(self) -> None:
        self.cancelled = True


@dataclass(slots=True)
class CancellingSuccessAdapter:
    token: MutableCancellationToken
    provider_format: ProviderFormat = ProviderFormat.FAKE
    calls: tuple[str, ...] = ()

    def invoke(self, plan: AdapterInvocationPlan) -> ProviderOutcome:
        self.calls = (*self.calls, plan.endpoint_uid)
        self.token.cancel()
        return provider_success(
            endpoint_uid=plan.endpoint_uid,
            elapsed_ms=20,
            content="must not become success",
        )


def _plan(
    registry: Registry,
    *,
    deadline_ms: int,
    cancellation_token: MutableCancellationToken | None = None,
) -> InvocationPlan:
    result = invoke_plan(
        request=InvocationRequest(
            role="writer",
            operation_ref="draft",
            messages=({"role": "user", "content": "draft this"},),
            deadline_ms=deadline_ms,
            operation_invocation_id="phase4-gate",
            cancellation_token=cancellation_token,
        ),
        registry=registry,
    )
    assert isinstance(result, InvocationPlan)
    return result


def _plain_text_config(
    *,
    max_attempts: int = 1,
    candidate_budget_ms: int = 4_000,
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
                model="fake-fallback",
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
                failover_reserve_ms=100,
                structured_output_mode=StructuredOutputMode.NONE,
                retry_policy=RetryPolicy(max_attempts=max_attempts),
            ),
        ),
    )


def _fail_schema_resolution(ref: str) -> NoReturn:
    raise AssertionError(f"plain text path must not resolve schema: {ref}")
