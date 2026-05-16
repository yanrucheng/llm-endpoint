from dataclasses import dataclass

from llm_endpoint.adapters import (
    AdapterInvocationPlan,
    FakeProviderAdapter,
    ProviderOutcome,
    ProviderOutcomeKind,
    provider_success,
)
from llm_endpoint.callbacks import SchemaResolution, resolved_schema, resolved_secret
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
from llm_endpoint.debug import DebugReplayArtifact, build_debug_replay_artifact
from llm_endpoint.fake_provider import (
    FakeProviderScenario,
    build_fake_provider_harness,
    fake_outcome,
)
from llm_endpoint.invocation import InvocationPlan, InvocationRequest, invoke_plan
from llm_endpoint.results import FailureCode, PlainTextResult, TypedFailure
from llm_endpoint.role_health import RoleHealthState, evaluate_role_health
from llm_endpoint.router import AttemptStatus, route_invocation
from llm_endpoint.telemetry import TelemetryEventFamily, forbidden_attribute_keys


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
        schema_resolver=_fail_schema_resolution,
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


def test_phase_4c_fake_provider_harness_covers_required_scenarios() -> None:
    scenarios = {
        FakeProviderScenario.RATE_LIMIT: FailureCode.INVOCATION_RATE_LIMITED,
        FakeProviderScenario.QUOTA: FailureCode.INVOCATION_QUOTA_EXHAUSTED,
        FakeProviderScenario.TIMEOUT: FailureCode.LOCAL_CANDIDATE_TIMEOUT,
        FakeProviderScenario.TRANSIENT_NETWORK: FailureCode.TRANSIENT_NETWORK,
        FakeProviderScenario.SERVER_5XX: FailureCode.PROVIDER_5XX,
        FakeProviderScenario.REFUSAL: FailureCode.STRUCTURED_OUTPUT_REFUSAL,
        FakeProviderScenario.DUPLICATE_TERMINAL_TOOL: FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD,
    }

    outcomes = {
        scenario: fake_outcome(scenario, endpoint_uid="primary")
        for scenario in (
            *scenarios,
            FakeProviderScenario.SUCCESS,
            FakeProviderScenario.MALFORMED_JSON,
            FakeProviderScenario.WRONG_TOOL,
            FakeProviderScenario.SCHEMA_VIOLATION,
            FakeProviderScenario.LATE_RESPONSE,
            FakeProviderScenario.POOL_EXHAUSTION,
        )
    }

    assert outcomes[FakeProviderScenario.SUCCESS].kind is ProviderOutcomeKind.SUCCESS
    assert outcomes[FakeProviderScenario.MALFORMED_JSON].payload is not None
    assert outcomes[FakeProviderScenario.MALFORMED_JSON].payload.content == "{not-json"
    assert outcomes[FakeProviderScenario.WRONG_TOOL].payload is not None
    assert outcomes[FakeProviderScenario.WRONG_TOOL].payload.tool_name == "wrong_tool"
    assert outcomes[FakeProviderScenario.SCHEMA_VIOLATION].payload is not None
    assert outcomes[FakeProviderScenario.SCHEMA_VIOLATION].payload.content == {"answer": ""}
    assert outcomes[FakeProviderScenario.LATE_RESPONSE].elapsed_ms == 10_000
    for scenario, failure_code in scenarios.items():
        assert outcomes[scenario].failure_code is failure_code


def test_phase_4c_fake_provider_harness_drives_pool_exhaustion() -> None:
    registry = build_registry(_plain_text_config(max_attempts=2))
    plan = _plan(registry, deadline_ms=10_000)
    harness = build_fake_provider_harness(
        {
            "primary": (FakeProviderScenario.POOL_EXHAUSTION,),
            "fallback": (FakeProviderScenario.POOL_EXHAUSTION,),
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: harness.adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.POOL_EXHAUSTED
    assert [trace.status for trace in result.attempt_traces] == [
        AttemptStatus.RETRYABLE_FAILURE,
        AttemptStatus.RETRYABLE_FAILURE,
    ]


def test_phase_4c_fake_provider_harness_drives_structured_failures() -> None:
    registry = build_registry(_structured_config(StructuredOutputMode.TOOL_CALL))
    plan = _plan(registry, deadline_ms=10_000)
    wrong_tool = build_fake_provider_harness({"primary": (FakeProviderScenario.WRONG_TOOL,)})

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: wrong_tool.adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
        schema_resolver=_answer_schema,
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD


def test_phase_4d_role_health_reports_available_and_degraded_states() -> None:
    registry = build_registry(_plain_text_config())
    adapter = FakeProviderAdapter({})

    available = evaluate_role_health(
        registry=registry,
        role="writer",
        adapters={ProviderFormat.FAKE: adapter},
    )
    degraded = evaluate_role_health(
        registry=registry,
        role="writer",
        adapters={ProviderFormat.FAKE: adapter},
        suppressed_endpoint_reasons={"primary": "maintenance"},
    )

    assert available.state is RoleHealthState.AVAILABLE
    assert available.endpoint_health[0].state is RoleHealthState.AVAILABLE
    assert degraded.state is RoleHealthState.FALLBACK_ONLY
    assert degraded.reasons == ("primary:suppressed:maintenance",)
    assert degraded.telemetry[0].family is TelemetryEventFamily.ROLE_HEALTH


def test_phase_4d_role_health_reports_unavailable_states() -> None:
    registry = build_registry(_plain_text_config())

    missing_secret = evaluate_role_health(
        registry=registry,
        role="writer",
        adapters={ProviderFormat.FAKE: FakeProviderAdapter({})},
        missing_secret_refs=frozenset({"secret://fake-primary", "secret://fake-fallback"}),
    )
    no_adapter = evaluate_role_health(registry=registry, role="writer", adapters={})

    assert missing_secret.state is RoleHealthState.MISSING_SECRET
    assert no_adapter.state is RoleHealthState.UNAVAILABLE
    assert no_adapter.reasons == (
        "fallback:adapter_unregistered",
        "primary:adapter_unregistered",
    )


def test_phase_4e_debug_replay_artifact_is_redacted_and_reproducible() -> None:
    registry = build_registry(_plain_text_config(max_attempts=2))
    plan = _plan(registry, deadline_ms=10_000)
    harness = build_fake_provider_harness({"primary": (FakeProviderScenario.LATE_RESPONSE,)})
    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: harness.adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    artifact = build_debug_replay_artifact(
        plan=plan,
        registry=registry,
        route_result=result,
        fake_provider_scenario=FakeProviderScenario.LATE_RESPONSE,
    )

    assert artifact.operation_invocation_id == "phase4-gate"
    assert artifact.endpoint_plan[0]["credential_ref_present"] == "true"
    assert artifact.fake_provider_reproduction["scenario"] == "late_response"
    assert artifact.typed_failure is not None
    assert artifact.typed_failure["failure_code"] == "llm.invocation.late_response_discarded"
    sections = (
        artifact.endpoint_plan
        + artifact.capability_profiles
        + artifact.attempt_trace
        + (
            artifact.policy_provenance,
            artifact.schema_trace,
            artifact.fake_provider_reproduction,
            artifact.typed_failure,
        )
    )
    assert all(not forbidden_attribute_keys(section) for section in sections if section is not None)


def test_phase_4e_debug_replay_rejects_forbidden_fields() -> None:
    registry = build_registry(_plain_text_config())
    plan = _plan(registry, deadline_ms=10_000)
    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={
            ProviderFormat.FAKE: FakeProviderAdapter(
                {
                    "primary": (
                        provider_success(
                            endpoint_uid="primary",
                            elapsed_ms=20,
                            content="ok",
                        ),
                    )
                }
            )
        },
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
    )

    try:
        DebugReplayArtifact(
            operation_invocation_id=plan.operation_invocation_id,
            endpoint_plan=(),
            policy_provenance={"raw_response": "forbidden"},
            capability_profiles=(),
            schema_trace={},
            attempt_trace=(),
            typed_failure=None,
            fake_provider_reproduction={},
        )
    except ValueError as exc:
        assert "forbidden fields" in str(exc)
    else:
        raise AssertionError("debug replay artifacts must reject raw provider fields")
    assert result.terminal_result is not None


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
                protect_last_eligible=True,
                structured_output_mode=StructuredOutputMode.NONE,
                retry_policy=RetryPolicy(max_attempts=max_attempts),
            ),
        ),
    )


def _structured_config(mode: StructuredOutputMode) -> LLMEndpointConfig:
    return LLMEndpointConfig(
        endpoints=(
            EndpointConfig(
                uid="primary",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-model",
                credential_ref="secret://fake-primary",
            ),
        ),
        roles=(RoleConfig(name="writer", endpoint_uid="primary"),),
        operations=(
            OperationConfig(
                ref="draft",
                policy_ref="draft-policy",
                schema_contract_ref="schema://answer/v1",
            ),
        ),
        policies=(
            OperationRuntimePolicy(
                ref="draft-policy",
                deadline_ms=10_000,
                max_output_tokens=1_024,
                candidate_budget_ms=4_000,
                protect_last_eligible=True,
                structured_output_mode=mode,
            ),
        ),
    )


def _answer_schema(ref: str):
    return resolved_schema(
        ref=ref,
        name="answer",
        version="1",
        fingerprint="sha256:answer",
        json_schema={
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string"}},
        },
        validate=lambda value: bool(value.get("answer")),
    )


def _fail_schema_resolution(ref: str) -> SchemaResolution:
    raise AssertionError(f"plain text path must not resolve schema: {ref}")
