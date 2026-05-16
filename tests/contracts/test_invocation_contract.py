from llm_endpoint.config import (
    EndpointConfig,
    EndpointPool,
    LLMEndpointConfig,
    OperationConfig,
    OperationRuntimePolicy,
    ProviderFormat,
    RoleConfig,
    StructuredOutputMode,
)
from llm_endpoint.invocation import InvocationPlan, InvocationRequest, invoke_plan
from llm_endpoint.results import FailureCode, TypedFailure
from llm_endpoint.telemetry import TelemetryEventFamily


def test_invocation_plan_contract() -> None:
    result = invoke_plan(
        request=InvocationRequest(
            role="writer",
            operation_ref="draft",
            messages=({"role": "user", "content": "draft this"},),
            deadline_ms=10_000,
            operation_invocation_id="inv-1",
        ),
        config=_config(),
    )

    assert isinstance(result, InvocationPlan)
    assert result.operation_invocation_id == "inv-1"
    assert result.endpoint_uids == ("primary", "fallback")
    assert result.schema_contract_ref == "schema://draft/v1"
    assert result.policy_fingerprint
    assert [event.family for event in result.telemetry] == [
        TelemetryEventFamily.REGISTRY_VALIDATED,
        TelemetryEventFamily.POLICY_RESOLVED,
    ]


def test_invalid_invocation_returns_typed_failure() -> None:
    result = invoke_plan(
        request=InvocationRequest(
            role="writer",
            operation_ref="draft",
            messages=(),
            deadline_ms=10_000,
            operation_invocation_id="inv-2",
        ),
        config=_config(),
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.INVALID_MESSAGES
    assert result.code.value == "llm.input.invalid_messages"
    assert result.context.operation_invocation_id == "inv-2"


def test_missing_operation_ref_returns_specific_policy_code() -> None:
    result = invoke_plan(
        request=InvocationRequest(
            role="writer",
            operation_ref="",
            messages=({"role": "user", "content": "draft this"},),
            deadline_ms=10_000,
            operation_invocation_id="inv-missing-operation",
        ),
        config=_config(),
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.OPERATION_REF_REQUIRED
    assert result.code.value == "llm.policy.operation_ref_required"


def test_unknown_role_returns_specific_endpoint_code() -> None:
    result = invoke_plan(
        request=InvocationRequest(
            role="ghost",
            operation_ref="draft",
            messages=({"role": "user", "content": "draft this"},),
            deadline_ms=10_000,
            operation_invocation_id="inv-unknown-role",
        ),
        config=_config(),
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.UNKNOWN_ROLE
    assert result.code.value == "llm.endpoint.unknown_role"


def test_invalid_deadline_returns_budget_violation_code() -> None:
    result = invoke_plan(
        request=InvocationRequest(
            role="writer",
            operation_ref="draft",
            messages=({"role": "user", "content": "draft this"},),
            deadline_ms=0,
            operation_invocation_id="inv-invalid-deadline",
        ),
        config=_config(),
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.BUDGET_VIOLATION
    assert result.code.value == "llm.budget.violation"


def test_structured_operation_requires_schema_ref() -> None:
    result = invoke_plan(
        request=InvocationRequest(
            role="writer",
            operation_ref="draft",
            messages=({"role": "user", "content": "draft this"},),
            deadline_ms=10_000,
            operation_invocation_id="inv-3",
        ),
        config=_config(schema_ref=None),
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.MISSING_SCHEMA_CONTRACT
    assert result.code.value == "llm.schema.missing_contract"


def test_unknown_operation_returns_typed_failure() -> None:
    result = invoke_plan(
        request=InvocationRequest(
            role="writer",
            operation_ref="missing",
            messages=({"role": "user", "content": "draft this"},),
            deadline_ms=10_000,
            operation_invocation_id="inv-4",
        ),
        config=_config(),
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.UNKNOWN_ENTRYPOINT
    assert result.code.value == "llm.endpoint.unknown_entrypoint"


def _config(schema_ref: str | None = "schema://draft/v1") -> LLMEndpointConfig:
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
            EndpointConfig(
                uid="fallback",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-model",
                credential_ref="secret://fake-fallback",
            ),
        ),
        roles=(RoleConfig(name="writer", pool=EndpointPool(("primary", "fallback"))),),
        operations=(
            OperationConfig(ref="draft", policy_ref="draft-policy", schema_contract_ref=schema_ref),
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
