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
    build_registry,
    resolve_role,
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


def test_registry_resolves_role_and_policy() -> None:
    config = LLMEndpointConfig(
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
        operations=(OperationConfig(ref="draft", policy_ref="draft-policy"),),
        policies=(
            OperationRuntimePolicy(
                ref="draft-policy",
                deadline_ms=1_000,
                max_output_tokens=128,
            ),
        ),
    )

    registry = build_registry(config)
    resolved = resolve_role(config, "writer")

    assert registry.config_identity == resolved.config_identity
    assert resolved.endpoint_uids == ("primary",)
    assert registry.resolve_operation_policy("draft").ref == "draft-policy"


def test_unknown_model_family_fails_config_validation() -> None:
    config = LLMEndpointConfig(
        endpoints=(
            EndpointConfig(
                uid="primary",
                provider_format=ProviderFormat.FAKE,
                model_family="unknown-family",
                model="fake-model",
                credential_ref="secret://fake-primary",
            ),
        ),
        roles=(RoleConfig(name="writer", endpoint_uid="primary"),),
        operations=(OperationConfig(ref="draft", policy_ref="draft-policy"),),
        policies=(
            OperationRuntimePolicy(
                ref="draft-policy",
                deadline_ms=1_000,
                max_output_tokens=128,
            ),
        ),
    )

    report = validate_config(config)

    assert report.ok is False
    assert {error.code for error in report.errors} == {ConfigErrorCode.UNSUPPORTED_MODEL_FAMILY}


def test_duplicate_registry_refs_fail_validation() -> None:
    config = LLMEndpointConfig(
        endpoints=(
            EndpointConfig(
                uid="primary",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-model",
                credential_ref="secret://fake-primary",
            ),
        ),
        roles=(
            RoleConfig(name="writer", endpoint_uid="primary"),
            RoleConfig(name="writer", endpoint_uid="primary"),
        ),
        operations=(
            OperationConfig(ref="draft", policy_ref="draft-policy"),
            OperationConfig(ref="draft", policy_ref="draft-policy"),
        ),
        policies=(
            OperationRuntimePolicy(
                ref="draft-policy",
                deadline_ms=1_000,
                max_output_tokens=128,
            ),
            OperationRuntimePolicy(
                ref="draft-policy",
                deadline_ms=1_000,
                max_output_tokens=128,
            ),
        ),
    )

    report = validate_config(config)
    codes = {error.code for error in report.errors}

    assert report.ok is False
    assert ConfigErrorCode.DUPLICATE_ROLE in codes
    assert ConfigErrorCode.DUPLICATE_OPERATION_REF in codes
    assert ConfigErrorCode.DUPLICATE_POLICY_REF in codes


def test_registry_lifecycle_replaces_active_config_atomically() -> None:
    lifecycle = RegistryLifecycle()
    first = lifecycle.activate(_lifecycle_config(model="fake-model-a"))
    replacement = lifecycle.replace_active(_lifecycle_config(model="fake-model-b"))
    failed = lifecycle.replace_active(_lifecycle_config(model="fake-model-c", schema_version="v0"))

    assert first.ok is True
    assert replacement.ok is True
    assert first.active_config_identity != replacement.active_config_identity
    assert failed.ok is False
    assert failed.active_config_identity == replacement.active_config_identity
    assert lifecycle.active_registry is not None
    assert lifecycle.active_registry.endpoints_by_uid["primary"].model == "fake-model-b"


def test_registry_lifecycle_rolls_back_by_validated_identity_only() -> None:
    lifecycle = RegistryLifecycle()
    first = lifecycle.activate(_lifecycle_config(model="fake-model-a"))
    replacement = lifecycle.replace_active(_lifecycle_config(model="fake-model-b"))

    assert first.active_config_identity is not None
    assert replacement.active_config_identity is not None
    rollback = lifecycle.rollback_to_identity(first.active_config_identity)
    missing = lifecycle.rollback_to_identity("missing-identity")

    assert rollback.ok is True
    assert lifecycle.active_config_identity == first.active_config_identity
    assert missing.ok is False
    assert missing.active_config_identity == first.active_config_identity
    assert missing.validation_report.errors[0].code is ConfigErrorCode.CONFIG_IDENTITY_NOT_FOUND


def _lifecycle_config(*, model: str, schema_version: str = "v1") -> LLMEndpointConfig:
    return LLMEndpointConfig(
        config_schema_version=schema_version,
        endpoints=(
            EndpointConfig(
                uid="primary",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model=model,
                credential_ref="secret://fake-primary",
            ),
        ),
        roles=(RoleConfig(name="writer", endpoint_uid="primary"),),
        operations=(OperationConfig(ref="draft", policy_ref="draft-policy"),),
        policies=(
            OperationRuntimePolicy(
                ref="draft-policy",
                deadline_ms=1_000,
                max_output_tokens=128,
            ),
        ),
    )
