from llm_endpoint.adapters import FakeProviderAdapter, provider_success
from llm_endpoint.callbacks import (
    SchemaResolution,
    SchemaResolutionStatus,
    resolved_schema,
    resolved_secret,
)
from llm_endpoint.config import (
    EndpointConfig,
    LLMEndpointConfig,
    OperationConfig,
    OperationRuntimePolicy,
    ProviderFormat,
    Registry,
    RoleConfig,
    StructuredOutputMode,
    build_registry,
)
from llm_endpoint.invocation import InvocationPlan, InvocationRequest, invoke_plan
from llm_endpoint.results import FailureCode, StructuredResult, TypedFailure
from llm_endpoint.router import route_invocation
from llm_endpoint.telemetry import TelemetryEventFamily


def test_json_schema_structured_output_validates_and_emits_schema_identity() -> None:
    registry = build_registry(_config())
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(
                    endpoint_uid="primary",
                    elapsed_ms=24,
                    content={"answer": "ok"},
                ),
            )
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
        schema_resolver=_answer_schema,
    )

    assert isinstance(result.terminal_result, StructuredResult)
    assert result.terminal_result.value == {"answer": "ok"}
    assert result.terminal_result.schema_name == "answer"
    success_event = result.telemetry[-1]
    assert success_event.family is TelemetryEventFamily.SUCCESS
    assert success_event.context.schema_contract_ref == "schema://answer/v1"
    assert success_event.context.schema_fingerprint == "sha256:answer"
    assert success_event.context.schema_resolution_status == "resolved"
    assert success_event.attributes["schema_fingerprint"] == "sha256:answer"
    assert success_event.attributes["structured_output_pipeline_version"] == "v1"
    assert success_event.attributes["structured_output_mode"] == "json_schema"


def test_schema_validation_failure_is_typed_and_non_retryable() -> None:
    registry = build_registry(_config())
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(
                    endpoint_uid="primary",
                    elapsed_ms=24,
                    content={"answer": ""},
                ),
            )
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
        schema_resolver=_answer_schema,
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD
    assert result.terminal_result.is_retryable is False
    assert result.terminal_result.context.schema_contract_ref == "schema://answer/v1"
    assert result.terminal_result.context.schema_fingerprint == "sha256:answer"
    assert result.terminal_result.diagnostics.safe_context["validation_stage"] == "host_validator"
    failure_event = result.telemetry[-1]
    assert failure_event.family is TelemetryEventFamily.FAILURE
    assert failure_event.context.schema_contract_ref == "schema://answer/v1"
    assert failure_event.context.schema_fingerprint == "sha256:answer"


def test_json_schema_validation_runs_before_host_validator() -> None:
    registry = build_registry(_config())
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(
                    endpoint_uid="primary",
                    elapsed_ms=24,
                    content={"answer": 42},
                ),
            )
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
        schema_resolver=_answer_schema,
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD
    assert result.terminal_result.diagnostics.safe_context["validation_stage"] == "json_schema"


def test_host_validator_exception_fails_closed() -> None:
    registry = build_registry(_config())
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(
                    endpoint_uid="primary",
                    elapsed_ms=24,
                    content={"answer": "ok"},
                ),
            )
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
        schema_resolver=_raising_schema,
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD
    assert result.terminal_result.diagnostics.safe_context == {
        "schema_ref": "schema://answer/v1",
        "schema_name": "answer",
        "schema_version": "1",
        "schema_fingerprint": "sha256:answer",
        "validation_stage": "host_validator",
        "validator_exception": "RuntimeError",
    }


def test_missing_schema_resolution_blocks_provider_attempts() -> None:
    registry = build_registry(_config())
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(
                    endpoint_uid="primary",
                    elapsed_ms=24,
                    content={"answer": "ok"},
                ),
            )
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
        schema_resolver=lambda ref: SchemaResolution(
            ref=ref,
            status=SchemaResolutionStatus.NOT_FOUND,
        ),
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.UNKNOWN_SCHEMA_CONTRACT
    assert result.terminal_result.context.schema_contract_ref == "schema://answer/v1"
    assert result.terminal_result.context.schema_resolution_status == "not_found"
    failure_event = result.telemetry[-1]
    assert failure_event.context.schema_contract_ref == "schema://answer/v1"
    assert failure_event.context.schema_resolution_status == "not_found"
    assert result.attempt_traces == ()
    assert adapter.calls_by_endpoint == {}


def test_tool_call_mode_rejects_wrong_terminal_tool() -> None:
    registry = build_registry(_config(mode=StructuredOutputMode.TOOL_CALL))
    plan = _plan(registry)
    adapter = FakeProviderAdapter(
        {
            "primary": (
                provider_success(
                    endpoint_uid="primary",
                    elapsed_ms=24,
                    content={"answer": "ok"},
                    tool_name="wrong_tool",
                ),
            )
        }
    )

    result = route_invocation(
        plan=plan,
        registry=registry,
        adapters={ProviderFormat.FAKE: adapter},
        secret_resolver=lambda ref: resolved_secret(ref, "credential-value"),
        schema_resolver=_answer_schema,
    )

    assert isinstance(result.terminal_result, TypedFailure)
    assert result.terminal_result.code is FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD


def _answer_schema(ref: str) -> SchemaResolution:
    return resolved_schema(
        ref=ref,
        name="answer",
        version="1",
        fingerprint="sha256:answer",
        json_schema={
            "type": "object",
            "required": ["answer"],
            "properties": {"answer": {"type": "string"}},
            "additionalProperties": False,
        },
        validate=lambda value: bool(value.get("answer")),
    )


def _raising_schema(ref: str) -> SchemaResolution:
    def _raise(_: object) -> bool:
        raise RuntimeError("boom")

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
        validate=_raise,
    )


def _plan(registry: Registry) -> InvocationPlan:
    result = invoke_plan(
        request=InvocationRequest(
            role="writer",
            operation_ref="draft",
            messages=({"role": "user", "content": "draft this"},),
            deadline_ms=10_000,
            operation_invocation_id="inv-structured",
        ),
        registry=registry,
    )
    assert isinstance(result, InvocationPlan)
    return result


def _config(
    *,
    mode: StructuredOutputMode = StructuredOutputMode.JSON_SCHEMA,
) -> LLMEndpointConfig:
    return LLMEndpointConfig(
        endpoints=(
            EndpointConfig(
                uid="primary",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-model",
                credential_ref="secret://fake-primary",
                capability_refs=("cap.fake.structured",),
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
                structured_output_mode=mode,
            ),
        ),
    )
