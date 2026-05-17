"""Versioned configuration schema and offline validation contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

CONFIG_SCHEMA_VERSION = "v1"


class ProviderFormat(StrEnum):
    """Provider adapter boundary identifiers."""

    OPENAI_RESPONSES = "openai_responses"
    OPENAI_CHAT_COMPLETIONS = "openai_chat_completions"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    FAKE = "fake"


class ReasoningMode(StrEnum):
    """Reasoning controls allowed by the public policy contract."""

    DISABLED = "disabled"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StructuredOutputMode(StrEnum):
    """Structured-output extraction mode requested by an operation."""

    NONE = "none"
    TOOL_CALL = "tool_call"
    JSON_SCHEMA = "json_schema"
    PROMPT_JSON = "prompt_json"


class RetryClass(StrEnum):
    """Retry behavior configured for endpoint failover."""

    NEVER = "never"
    RETRYABLE_AVAILABILITY_ONLY = "retryable_availability_only"


class ConfigErrorCode(StrEnum):
    """Machine-readable config validation error codes."""

    UNSUPPORTED_CONFIG_VERSION = "unsupported_config_version"
    EMPTY_ENDPOINTS = "empty_endpoints"
    EMPTY_UID = "empty_uid"
    DUPLICATE_UID = "duplicate_uid"
    EMPTY_ROLE = "empty_role"
    DUPLICATE_ROLE = "duplicate_role"
    UNKNOWN_ENDPOINT_REF = "unknown_endpoint_ref"
    EMPTY_POOL = "empty_pool"
    DUPLICATE_POOL_MEMBER = "duplicate_pool_member"
    UNKNOWN_POLICY_REF = "unknown_policy_ref"
    DUPLICATE_POLICY_REF = "duplicate_policy_ref"
    EMPTY_OPERATION_REF = "empty_operation_ref"
    DUPLICATE_OPERATION_REF = "duplicate_operation_ref"
    INVALID_DEADLINE = "invalid_deadline"
    INVALID_OUTPUT_BUDGET = "invalid_output_budget"
    INVALID_CANDIDATE_BUDGET = "invalid_candidate_budget"
    INVALID_SCHEMA_REF = "invalid_schema_ref"
    INVALID_CREDENTIAL_REF = "invalid_credential_ref"
    INVALID_CAPABILITY_REF = "invalid_capability_ref"
    UNSUPPORTED_PROVIDER_FORMAT = "unsupported_provider_format"
    UNSUPPORTED_MODEL_FAMILY = "unsupported_model_family"
    INVALID_STRUCTURED_OUTPUT = "invalid_structured_output"
    CONFIG_IDENTITY_NOT_FOUND = "config_identity_not_found"


@dataclass(frozen=True, slots=True)
class EndpointConfig:
    """One opaque endpoint entrypoint."""

    uid: str
    provider_format: ProviderFormat
    model_family: str
    model: str
    credential_ref: str
    capability_refs: tuple[str, ...] = ()
    endpoint_url: str | None = None
    deployment: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EndpointPool:
    """Ordered candidate pool for one role."""

    members: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoleConfig:
    """Host-owned role mapped to one endpoint or ordered pool."""

    name: str
    endpoint_uid: str | None = None
    pool: EndpointPool | None = None


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Retry and failover contract for one operation."""

    retry_class: RetryClass = RetryClass.RETRYABLE_AVAILABILITY_ONLY
    max_attempts: int = 1


@dataclass(frozen=True, slots=True)
class OperationRuntimePolicy:
    """Runtime budget and structured-output policy for one operation."""

    ref: str
    deadline_ms: int
    max_output_tokens: int
    reasoning_mode: ReasoningMode = ReasoningMode.DISABLED
    candidate_budget_ms: int | None = None
    candidate_budget_overrides_ms: Mapping[str, int] | None = None
    protect_last_eligible: bool = False
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.NONE
    allow_caller_overrides: bool = False
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)


@dataclass(frozen=True, slots=True)
class OperationConfig:
    """Host operation bound to a runtime policy and optional schema contract."""

    ref: str
    policy_ref: str
    schema_contract_ref: str | None = None


@dataclass(frozen=True, slots=True)
class LLMEndpointConfig:
    """Top-level registry configuration contract."""

    endpoints: tuple[EndpointConfig, ...]
    roles: tuple[RoleConfig, ...]
    operations: tuple[OperationConfig, ...]
    policies: tuple[OperationRuntimePolicy, ...]
    config_schema_version: str = CONFIG_SCHEMA_VERSION
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConfigValidationError:
    """Path-specific machine-readable validation error."""

    code: ConfigErrorCode
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class ConfigValidationReport:
    """Offline validation report with deterministic config identity."""

    ok: bool
    config_identity: str | None
    errors: tuple[ConfigValidationError, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedRole:
    """Deterministic role resolution without provider calls."""

    name: str
    endpoint_uids: tuple[str, ...]
    config_identity: str


@dataclass(frozen=True, slots=True)
class Registry:
    """Validated offline registry indexes used by planning components."""

    config: LLMEndpointConfig
    config_identity: str
    endpoints_by_uid: dict[str, EndpointConfig]
    roles_by_name: dict[str, RoleConfig]
    operations_by_ref: dict[str, OperationConfig]
    policies_by_ref: dict[str, OperationRuntimePolicy]

    def resolve_role(self, role_name: str) -> ResolvedRole:
        """Resolve a role into one endpoint or an ordered candidate pool."""

        role = self.roles_by_name.get(role_name)
        if role is None:
            raise KeyError(f"unknown role: {role_name}")
        if role.endpoint_uid is not None:
            endpoint_uids = (role.endpoint_uid,)
        elif role.pool is not None:
            endpoint_uids = role.pool.members
        else:
            raise ValueError(f"role has no endpoint resolution: {role_name}")
        return ResolvedRole(
            name=role.name,
            endpoint_uids=endpoint_uids,
            config_identity=self.config_identity,
        )

    def resolve_operation_policy(self, operation_ref: str) -> OperationRuntimePolicy:
        """Resolve an operation into its configured runtime policy."""

        operation = self.operations_by_ref.get(operation_ref)
        if operation is None:
            raise KeyError(f"unknown operation: {operation_ref}")
        return self.policies_by_ref[operation.policy_ref]


@dataclass(frozen=True, slots=True)
class ConfigActivationResult:
    """Outcome of explicit active-registry lifecycle operations."""

    ok: bool
    active_config_identity: str | None
    attempted_config_identity: str | None
    validation_report: ConfigValidationReport
    registry: Registry | None = None


@dataclass(slots=True)
class RegistryLifecycle:
    """Explicit active registry lifecycle with full replacement validation."""

    capability_catalog: Any | None = None
    active_registry: Registry | None = None
    registry_history: dict[str, Registry] = field(default_factory=dict)

    @property
    def active_config_identity(self) -> str | None:
        """Expose the currently active config identity, if activation succeeded."""

        if self.active_registry is None:
            return None
        return self.active_registry.config_identity

    def activate(self, config: LLMEndpointConfig) -> ConfigActivationResult:
        """Validate and activate the first or replacement registry atomically."""

        return self.replace_active(config)

    def replace_active(self, config: LLMEndpointConfig) -> ConfigActivationResult:
        """Fully validate replacement config before changing active registry."""

        attempted_identity = config_identity(config)
        report = validate_config(config, capability_catalog=self.capability_catalog)
        if not report.ok:
            return ConfigActivationResult(
                ok=False,
                active_config_identity=self.active_config_identity,
                attempted_config_identity=attempted_identity,
                validation_report=report,
            )

        registry = build_registry(config, capability_catalog=self.capability_catalog)
        self.active_registry = registry
        self.registry_history[registry.config_identity] = registry
        return ConfigActivationResult(
            ok=True,
            active_config_identity=registry.config_identity,
            attempted_config_identity=attempted_identity,
            validation_report=report,
            registry=registry,
        )

    def rollback_to_identity(self, identity: str) -> ConfigActivationResult:
        """Reactivate a previously validated registry by exact config identity."""

        registry = self.registry_history.get(identity)
        if registry is None:
            return ConfigActivationResult(
                ok=False,
                active_config_identity=self.active_config_identity,
                attempted_config_identity=identity,
                validation_report=ConfigValidationReport(
                    ok=False,
                    config_identity=None,
                    errors=(
                        _error(
                            ConfigErrorCode.CONFIG_IDENTITY_NOT_FOUND,
                            "config_identity",
                            f"unknown validated config identity: {identity}",
                        ),
                    ),
                ),
            )

        self.active_registry = registry
        return ConfigActivationResult(
            ok=True,
            active_config_identity=registry.config_identity,
            attempted_config_identity=identity,
            validation_report=ConfigValidationReport(
                ok=True,
                config_identity=registry.config_identity,
                errors=(),
            ),
            registry=registry,
        )


def config_identity(config: LLMEndpointConfig) -> str:
    """Return a deterministic identity for config material without secrets."""

    payload = _canonical_json(asdict(config))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_config(
    config: LLMEndpointConfig,
    capability_catalog: Any | None = None,
) -> ConfigValidationReport:
    """Validate config shape without network calls, credential values, or legacy loaders."""

    errors: list[ConfigValidationError] = []
    catalog = _default_capability_catalog() if capability_catalog is None else capability_catalog

    if config.config_schema_version != CONFIG_SCHEMA_VERSION:
        errors.append(
            _error(
                ConfigErrorCode.UNSUPPORTED_CONFIG_VERSION,
                "config_schema_version",
                "only config_schema_version 'v1' is supported under Zero BC policy",
            )
        )

    endpoint_uids: set[str] = set()
    role_names: set[str] = set()
    operation_refs: set[str] = set()
    policy_refs: set[str] = set()
    if not config.endpoints:
        errors.append(
            _error(
                ConfigErrorCode.EMPTY_ENDPOINTS,
                "endpoints",
                "at least one endpoint is required",
            )
        )

    for index, endpoint in enumerate(config.endpoints):
        path = f"endpoints[{index}]"
        provider_format = _provider_format(endpoint.provider_format)
        if provider_format is None:
            errors.append(
                _error(
                    ConfigErrorCode.UNSUPPORTED_PROVIDER_FORMAT,
                    f"{path}.provider_format",
                    f"unsupported provider format: {endpoint.provider_format}",
                )
            )
        elif not catalog.get(provider_format, endpoint.model_family):
            errors.append(
                _error(
                    ConfigErrorCode.UNSUPPORTED_MODEL_FAMILY,
                    f"{path}.model_family",
                    f"unsupported model family for {provider_format}: {endpoint.model_family}",
                )
            )

        if not endpoint.uid:
            errors.append(
                _error(ConfigErrorCode.EMPTY_UID, f"{path}.uid", "endpoint uid is required")
            )
        elif endpoint.uid in endpoint_uids:
            errors.append(
                _error(ConfigErrorCode.DUPLICATE_UID, f"{path}.uid", "endpoint uid must be unique")
            )
        else:
            endpoint_uids.add(endpoint.uid)

        if not endpoint.credential_ref:
            errors.append(
                _error(
                    ConfigErrorCode.INVALID_CREDENTIAL_REF,
                    f"{path}.credential_ref",
                    "credential_ref is required and must not contain credential values",
                )
            )
        for ref_index, capability_ref in enumerate(endpoint.capability_refs):
            if not capability_ref:
                errors.append(
                    _error(
                        ConfigErrorCode.INVALID_CAPABILITY_REF,
                        f"{path}.capability_refs[{ref_index}]",
                        "capability refs must be non-empty identifiers",
                    )
                )

    for index, role in enumerate(config.roles):
        path = f"roles[{index}]"
        if not role.name:
            errors.append(
                _error(ConfigErrorCode.EMPTY_ROLE, f"{path}.name", "role name is required")
            )
        elif role.name in role_names:
            errors.append(
                _error(
                    ConfigErrorCode.DUPLICATE_ROLE,
                    f"{path}.name",
                    "role name must be unique",
                )
            )
        else:
            role_names.add(role.name)

        if (role.endpoint_uid is None) == (role.pool is None):
            errors.append(
                _error(
                    ConfigErrorCode.UNKNOWN_ENDPOINT_REF,
                    path,
                    "role must reference exactly one endpoint_uid or one pool",
                )
            )
            continue

        if role.endpoint_uid is not None and role.endpoint_uid not in endpoint_uids:
            errors.append(
                _error(
                    ConfigErrorCode.UNKNOWN_ENDPOINT_REF,
                    f"{path}.endpoint_uid",
                    f"unknown endpoint uid: {role.endpoint_uid}",
                )
            )

        if role.pool is not None:
            _validate_pool(role.pool, endpoint_uids, path, errors)

    for index, policy in enumerate(config.policies):
        if policy.ref in policy_refs:
            errors.append(
                _error(
                    ConfigErrorCode.DUPLICATE_POLICY_REF,
                    f"policies[{index}].ref",
                    "policy ref must be unique",
                )
            )
        elif policy.ref:
            policy_refs.add(policy.ref)
        _validate_policy(policy, f"policies[{index}]", errors)

    for index, operation in enumerate(config.operations):
        path = f"operations[{index}]"
        if not operation.ref:
            errors.append(
                _error(
                    ConfigErrorCode.EMPTY_OPERATION_REF,
                    f"{path}.ref",
                    "operation ref is required",
                )
            )
        elif operation.ref in operation_refs:
            errors.append(
                _error(
                    ConfigErrorCode.DUPLICATE_OPERATION_REF,
                    f"{path}.ref",
                    "operation ref must be unique",
                )
            )
        else:
            operation_refs.add(operation.ref)
        if operation.policy_ref not in policy_refs:
            errors.append(
                _error(
                    ConfigErrorCode.UNKNOWN_POLICY_REF,
                    f"{path}.policy_ref",
                    f"unknown policy ref: {operation.policy_ref}",
                )
            )
        if operation.schema_contract_ref == "":
            errors.append(
                _error(
                    ConfigErrorCode.INVALID_SCHEMA_REF,
                    f"{path}.schema_contract_ref",
                    "schema_contract_ref must be omitted or non-empty",
                )
            )

    if errors:
        return ConfigValidationReport(ok=False, config_identity=None, errors=tuple(errors))
    return ConfigValidationReport(ok=True, config_identity=config_identity(config), errors=())


def build_registry(config: LLMEndpointConfig, capability_catalog: Any | None = None) -> Registry:
    """Build validated registry indexes for offline planning."""

    report = validate_config(config, capability_catalog=capability_catalog)
    if not report.ok or report.config_identity is None:
        codes = ", ".join(error.code.value for error in report.errors)
        raise ValueError(f"invalid config cannot build registry: {codes}")
    return Registry(
        config=config,
        config_identity=report.config_identity,
        endpoints_by_uid={endpoint.uid: endpoint for endpoint in config.endpoints},
        roles_by_name={role.name: role for role in config.roles},
        operations_by_ref={operation.ref: operation for operation in config.operations},
        policies_by_ref={policy.ref: policy for policy in config.policies},
    )


def resolve_role(config: LLMEndpointConfig, role_name: str) -> ResolvedRole:
    """Validate config and resolve a role to ordered endpoint UIDs."""

    return build_registry(config).resolve_role(role_name)


def _validate_pool(
    pool: EndpointPool,
    endpoint_uids: set[str],
    path: str,
    errors: list[ConfigValidationError],
) -> None:
    if not pool.members:
        errors.append(
            _error(ConfigErrorCode.EMPTY_POOL, f"{path}.pool.members", "pool cannot be empty")
        )
        return

    seen_members: set[str] = set()
    for member_index, member_uid in enumerate(pool.members):
        member_path = f"{path}.pool.members[{member_index}]"
        if member_uid in seen_members:
            errors.append(
                _error(
                    ConfigErrorCode.DUPLICATE_POOL_MEMBER,
                    member_path,
                    "pool members must be unique",
                )
            )
        seen_members.add(member_uid)
        if member_uid not in endpoint_uids:
            errors.append(
                _error(
                    ConfigErrorCode.UNKNOWN_ENDPOINT_REF,
                    member_path,
                    f"unknown endpoint uid: {member_uid}",
                )
            )


def _validate_policy(
    policy: OperationRuntimePolicy,
    path: str,
    errors: list[ConfigValidationError],
) -> None:
    if not policy.ref:
        errors.append(
            _error(ConfigErrorCode.UNKNOWN_POLICY_REF, f"{path}.ref", "policy ref is required")
        )
    if policy.deadline_ms <= 0:
        errors.append(
            _error(
                ConfigErrorCode.INVALID_DEADLINE,
                f"{path}.deadline_ms",
                "deadline_ms must be positive",
            )
        )
    if policy.max_output_tokens <= 0:
        errors.append(
            _error(
                ConfigErrorCode.INVALID_OUTPUT_BUDGET,
                f"{path}.max_output_tokens",
                "max_output_tokens must be positive",
            )
        )
    if policy.candidate_budget_ms is not None and policy.candidate_budget_ms <= 0:
        errors.append(
            _error(
                ConfigErrorCode.INVALID_CANDIDATE_BUDGET,
                f"{path}.candidate_budget_ms",
                "candidate_budget_ms must be omitted or positive",
            )
        )
    if policy.candidate_budget_overrides_ms is not None:
        for uid, budget in policy.candidate_budget_overrides_ms.items():
            override_path = (
                f"{path}.candidate_budget_overrides_ms[{uid!r}]"
            )
            if budget <= 0:
                errors.append(
                    _error(
                        ConfigErrorCode.INVALID_CANDIDATE_BUDGET,
                        override_path,
                        f"override budget for {uid!r} must be positive",
                    )
                )
            elif policy.deadline_ms > 0 and budget > policy.deadline_ms:
                errors.append(
                    _error(
                        ConfigErrorCode.INVALID_CANDIDATE_BUDGET,
                        override_path,
                        f"override budget for {uid!r} exceeds deadline_ms",
                    )
                )
    if policy.retry_policy.max_attempts <= 0:
        errors.append(
            _error(
                ConfigErrorCode.INVALID_CANDIDATE_BUDGET,
                f"{path}.retry_policy.max_attempts",
                "max_attempts must be positive",
            )
        )


def _error(code: ConfigErrorCode, path: str, message: str) -> ConfigValidationError:
    return ConfigValidationError(code=code, path=path, message=message)


def _provider_format(value: Any) -> ProviderFormat | None:
    if isinstance(value, ProviderFormat):
        return value
    try:
        return ProviderFormat(value)
    except ValueError:
        return None


def _default_capability_catalog() -> Any:
    from llm_endpoint.capabilities import DEFAULT_CAPABILITY_CATALOG

    return DEFAULT_CAPABILITY_CATALOG


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
