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


def test_valid_config_contract() -> None:
    config = LLMEndpointConfig(
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
                max_output_tokens=1_024,
                candidate_budget_ms=4_000,
                failover_reserve_ms=1_000,
                structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
            ),
        ),
    )

    report = validate_config(config)

    assert report.ok is True
    assert report.config_identity is not None
    assert report.errors == ()


def test_invalid_config_contract() -> None:
    config = LLMEndpointConfig(
        config_schema_version="v0",
        endpoints=(
            EndpointConfig(
                uid="primary",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-model",
                credential_ref="",
            ),
            EndpointConfig(
                uid="primary",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-model",
                credential_ref="secret://duplicate",
            ),
        ),
        roles=(RoleConfig(name="writer", pool=EndpointPool(("primary", "primary", "missing"))),),
        operations=(
            OperationConfig(ref="draft", policy_ref="missing-policy", schema_contract_ref=""),
        ),
        policies=(
            OperationRuntimePolicy(
                ref="draft-policy",
                deadline_ms=0,
                max_output_tokens=0,
                failover_reserve_ms=1,
                structured_output_mode=StructuredOutputMode.PROMPT_JSON,
            ),
        ),
    )

    report = validate_config(config)
    codes = {error.code for error in report.errors}

    assert report.ok is False
    assert report.config_identity is None
    assert ConfigErrorCode.UNSUPPORTED_CONFIG_VERSION in codes
    assert ConfigErrorCode.DUPLICATE_UID in codes
    assert ConfigErrorCode.UNKNOWN_ENDPOINT_REF in codes
    assert ConfigErrorCode.UNKNOWN_POLICY_REF in codes
    assert ConfigErrorCode.INVALID_STRUCTURED_OUTPUT in codes
