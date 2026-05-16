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
    assert result.provenance["max_output_tokens"] is PolicySource.CALLER_OVERRIDE
    assert result.provenance["candidate_budget_ms"] is PolicySource.POLICY
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
    assert result.code is FailureCode.POLICY_VIOLATION


def test_policy_hard_cap_violation() -> None:
    result = resolve_policy(
        config=_config(max_output_tokens=9_000),
        role="writer",
        operation_ref="draft",
        operation_invocation_id="inv-3",
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.BUDGET_VIOLATION
    assert result.context.endpoint_uid == "primary"


def _config(
    *,
    allow_overrides: bool = False,
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
                deadline_ms=10_000,
                max_output_tokens=max_output_tokens,
                reasoning_mode=ReasoningMode.MEDIUM,
                candidate_budget_ms=4_000,
                failover_reserve_ms=1_000,
                structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
                allow_caller_overrides=allow_overrides,
            ),
        ),
    )
