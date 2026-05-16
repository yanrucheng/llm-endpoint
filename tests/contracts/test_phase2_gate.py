from llm_endpoint.config import (
    ConfigErrorCode,
    EndpointConfig,
    EndpointPool,
    LLMEndpointConfig,
    OperationConfig,
    OperationRuntimePolicy,
    ProviderFormat,
    RoleConfig,
    StructuredOutputMode,
    validate_config,
)
from llm_endpoint.invocation import InvocationPlan, InvocationRequest, invoke_plan
from llm_endpoint.public_surface import PUBLIC_SURFACES, CompatibilityLevel
from llm_endpoint.results import FailureCode, TypedFailure
from llm_endpoint.smoke import SmokeCheckName, run_offline_smoke
from llm_endpoint.telemetry import (
    RedactionStatus,
    TelemetryEmitter,
    TelemetryEventFamily,
    forbidden_attribute_keys,
)


def test_phase_2_gate_passes_offline_spine() -> None:
    report = run_offline_smoke(config=_config(), role="writer", operation_ref="draft")

    assert report.ok is True
    assert report.config_identity is not None
    assert isinstance(report.plan, InvocationPlan)
    assert report.failure is None
    assert {check.name for check in report.checks} == {
        SmokeCheckName.CONFIG_VALIDATION,
        SmokeCheckName.REGISTRY_BUILD,
        SmokeCheckName.INVOCATION_PLANNING,
        SmokeCheckName.TELEMETRY_REDACTION,
    }
    assert report.plan.endpoint_uids == ("primary", "fallback")
    assert report.plan.config_identity == report.config_identity
    assert report.plan.policy_fingerprint
    assert [event.family for event in report.events] == [
        TelemetryEventFamily.POLICY_RESOLVED,
        TelemetryEventFamily.SMOKE_RESULT,
    ]
    assert all(event.redaction_status is RedactionStatus.REDACTED for event in report.events)
    assert all(not forbidden_attribute_keys(event.attributes) for event in report.events)


def test_phase_2_gate_returns_typed_failure_without_provider_call() -> None:
    emitter = TelemetryEmitter()

    result = invoke_plan(
        request=InvocationRequest(
            role="writer",
            operation_ref="draft",
            messages=(),
            deadline_ms=10_000,
            operation_invocation_id="phase2-invalid",
        ),
        config=_config(),
        telemetry_emitter=emitter,
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.INVALID_MESSAGES
    assert result.context.operation_invocation_id == "phase2-invalid"
    assert result.is_retryable is False
    assert [event.family for event in emitter.captured_events] == [TelemetryEventFamily.FAILURE]
    assert all(not forbidden_attribute_keys(event.attributes) for event in emitter.captured_events)


def test_phase_2_gate_enforces_zero_bc_config_and_surfaces() -> None:
    report = validate_config(_config(config_schema_version="v0"))

    assert report.ok is False
    assert {error.code for error in report.errors} == {ConfigErrorCode.UNSUPPORTED_CONFIG_VERSION}
    assert {surface.compatibility_level for surface in PUBLIC_SURFACES} == {
        CompatibilityLevel.ZERO_BC
    }
    assert not any(
        token in surface.name.lower()
        for surface in PUBLIC_SURFACES
        for token in ("legacy", "compat", "shim", "v2")
    )


def _config(config_schema_version: str = "v1") -> LLMEndpointConfig:
    return LLMEndpointConfig(
        config_schema_version=config_schema_version,
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
        operations=(
            OperationConfig(
                ref="draft",
                policy_ref="draft-policy",
                schema_contract_ref="schema://draft/v1",
            ),
        ),
        policies=(
            OperationRuntimePolicy(
                ref="draft-policy",
                deadline_ms=10_000,
                max_output_tokens=1_024,
                candidate_budget_ms=4_000,
                protect_last_eligible=True,
                structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
            ),
        ),
    )
