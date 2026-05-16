from llm_endpoint.config import (
    EndpointConfig,
    EndpointPool,
    LLMEndpointConfig,
    OperationConfig,
    OperationRuntimePolicy,
    ProviderFormat,
    ReasoningMode,
    RoleConfig,
    StructuredOutputMode,
)
from llm_endpoint.policy import (
    CallerPolicyOverrides,
    PolicyResolution,
    PolicySource,
    resolve_policy,
)
from llm_endpoint.results import FailureCode, TypedFailure
from llm_endpoint.telemetry import TelemetryEventFamily


def test_policy_resolution_contract() -> None:
    result = resolve_policy(
        config=_config(allow_overrides=True),
        role="writer",
        operation_ref="draft",
        operation_invocation_id="inv-1",
        caller_overrides=CallerPolicyOverrides(max_output_tokens=512),
    )

    assert isinstance(result, PolicyResolution)
    assert result.endpoint_uids == ("primary", "fallback")
    assert result.effective_config.max_output_tokens == 512
    assert result.effective_config.candidate_budget_ms == 4_000
    assert result.effective_config.protect_last_eligible is True
    assert result.provenance["max_output_tokens"] is PolicySource.CALLER_OVERRIDE
    assert result.provenance["candidate_budget_ms"] is PolicySource.POLICY
    assert result.provenance["protect_last_eligible"] is PolicySource.POLICY
    assert len(result.policy_fingerprint) == 64
    assert result.telemetry.family is TelemetryEventFamily.POLICY_RESOLVED
    assert result.telemetry.context.policy_fingerprint == result.policy_fingerprint


def test_policy_override_requires_policy_permission() -> None:
    result = resolve_policy(
        config=_config(allow_overrides=False),
        role="writer",
        operation_ref="draft",
        operation_invocation_id="inv-2",
        caller_overrides=CallerPolicyOverrides(max_output_tokens=512),
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.UNSUPPORTED_RUNTIME_KNOB
    assert result.code.value == "llm.endpoint.unsupported_runtime_knob"


def test_policy_hard_cap_violation() -> None:
    result = resolve_policy(
        config=_config(max_output_tokens=9_000),
        role="writer",
        operation_ref="draft",
        operation_invocation_id="inv-3",
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.OUTPUT_BUDGET_EXCEEDS_HARD_CAP
    assert result.code.value == "llm.policy.output_budget_exceeds_hard_cap"
    assert result.context.endpoint_uid == "primary"


def test_policy_unknown_role_returns_specific_endpoint_code() -> None:
    result = resolve_policy(
        config=_config(),
        role="ghost",
        operation_ref="draft",
        operation_invocation_id="inv-unknown-role",
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.UNKNOWN_ROLE
    assert result.code.value == "llm.endpoint.unknown_role"


def test_policy_unknown_operation_returns_specific_endpoint_code() -> None:
    result = resolve_policy(
        config=_config(),
        role="writer",
        operation_ref="missing",
        operation_invocation_id="inv-unknown-operation",
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.UNKNOWN_ENTRYPOINT
    assert result.code.value == "llm.endpoint.unknown_entrypoint"


def test_policy_deadline_shape_returns_candidate_budget_code() -> None:
    result = resolve_policy(
        config=_config(deadline_ms=70_000),
        role="writer",
        operation_ref="draft",
        operation_invocation_id="inv-budget-shape",
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.CANDIDATE_BUDGET_UNALLOCATABLE
    assert result.code.value == "llm.policy.candidate_budget_unallocatable"
    assert result.context.endpoint_uid == "primary"


def _config(
    *,
    allow_overrides: bool = False,
    deadline_ms: int = 10_000,
    max_output_tokens: int = 1_024,
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
                deadline_ms=deadline_ms,
                max_output_tokens=max_output_tokens,
                reasoning_mode=ReasoningMode.MEDIUM,
                candidate_budget_ms=4_000,
                protect_last_eligible=True,
                structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
                allow_caller_overrides=allow_overrides,
            ),
        ),
    )
