from llm_endpoint.adapters import FakeProviderAdapter, provider_success
from llm_endpoint.callbacks import resolved_schema, resolved_secret
from llm_endpoint.config import (
    ConfigErrorCode,
    EndpointConfig,
    EndpointPool,
    LLMEndpointConfig,
    OperationConfig,
    OperationRuntimePolicy,
    ProviderFormat,
    RegistryLifecycle,
    RoleConfig,
    StructuredOutputMode,
)
from llm_endpoint.invocation import InvocationPlan, InvocationRequest, invoke_plan
from llm_endpoint.results import FailureCode, StructuredResult, TypedFailure
from llm_endpoint.router import route_invocation
from llm_endpoint.telemetry import TelemetryEventFamily, forbidden_attribute_keys


def test_phase_3_gate_integrates_execution_components_without_payload_leakage() -> None:
    lifecycle = RegistryLifecycle()
    activation = lifecycle.activate(_config())
    assert activation.ok is True
    assert activation.registry is not None

    plan = invoke_plan(
        request=InvocationRequest(
            role="writer",
            operation_ref="draft",
            messages=({"role": "user", "content": "draft this"},),
            deadline_ms=10_000,
            operation_invocation_id="phase3-gate",
        ),
        registry=activation.registry,
    )
    assert isinstance(plan, InvocationPlan)
    assert plan.config_identity == activation.active_config_identity

    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(
                    endpoint_uid="primary",
                    elapsed_ms=20,
                    content={"answer": "ok"},
                    safe_provider_status={"status_class": "2xx"},
                ),
            )
        }
    )

    result = route_invocation(
        plan=plan,
        registry=activation.registry,
        adapters={ProviderFormat.FAKE: adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
        schema_resolver=_answer_schema,
    )

    assert isinstance(result.terminal_result, StructuredResult)
    assert result.terminal_result.value == {"answer": "ok"}
    assert result.terminal_result.schema_fingerprint == "sha256:answer"
    assert [event.family for event in result.telemetry] == [
        TelemetryEventFamily.POOL_ATTEMPT,
        TelemetryEventFamily.SUCCESS,
    ]
    assert all(not forbidden_attribute_keys(event.attributes) for event in result.telemetry)
    assert all("raw_response" not in event.attributes for event in result.telemetry)


def test_phase_3_gate_preserves_active_config_and_returns_typed_failures() -> None:
    lifecycle = RegistryLifecycle()
    activation = lifecycle.activate(_config(model="fake-model-a"))
    failed_replacement = lifecycle.replace_active(
        _config(model="fake-model-b", schema_version="v0")
    )

    assert activation.ok is True
    assert failed_replacement.ok is False
    assert failed_replacement.active_config_identity == activation.active_config_identity
    assert failed_replacement.validation_report.errors[0].code is (
        ConfigErrorCode.UNSUPPORTED_CONFIG_VERSION
    )
    assert lifecycle.active_registry is not None

    plan = invoke_plan(
        request=InvocationRequest(
            role="writer",
            operation_ref="draft",
            messages=({"role": "user", "content": "draft this"},),
            deadline_ms=10_000,
            operation_invocation_id="phase3-failure",
        ),
        registry=lifecycle.active_registry,
    )
    assert isinstance(plan, InvocationPlan)

    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(
                    endpoint_uid="primary",
                    elapsed_ms=20,
                    content={"answer": ""},
                ),
            )
        }
    )
    result = route_invocation(
        plan=plan,
        registry=lifecycle.active_registry,
        adapters={ProviderFormat.FAKE: adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
        schema_resolver=_answer_schema,
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.SCHEMA_VALIDATION_FAILED
    assert result.terminal_result.is_retryable is False
    assert result.telemetry[-1].attributes["failure_code"] == "schema_validation_failed"


def _answer_schema(ref: str):
    return resolved_schema(
        ref=ref,
        name="answer",
        version="1",
        fingerprint="sha256:answer",
        json_schema={"type": "object", "required": ["answer"]},
        validate=lambda value: bool(value.get("answer")),
    )


def _config(*, model: str = "fake-model", schema_version: str = "v1") -> LLMEndpointConfig:
    return LLMEndpointConfig(
        config_schema_version=schema_version,
        endpoints=(
            EndpointConfig(
                uid="primary",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model=model,
                credential_ref="secret://fake-primary",
                capability_refs=("cap.fake.structured",),
            ),
            EndpointConfig(
                uid="fallback",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-fallback",
                credential_ref="secret://fake-fallback",
                capability_refs=("cap.fake.structured",),
            ),
        ),
        roles=(RoleConfig(name="writer", pool=EndpointPool(("primary", "fallback"))),),
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
                failover_reserve_ms=1_000,
                structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
            ),
        ),
    )
