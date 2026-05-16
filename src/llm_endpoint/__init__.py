"""Reusable LLM endpoint execution boundary."""

from llm_endpoint.config import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationReport,
    EndpointConfig,
    EndpointPool,
    LLMEndpointConfig,
    OperationConfig,
    OperationRuntimePolicy,
    ProviderFormat,
    ReasoningMode,
    RetryPolicy,
    RoleConfig,
    StructuredOutputMode,
    config_identity,
    validate_config,
)
from llm_endpoint.public_surface import PUBLIC_SURFACE_MANIFEST_VERSION, PUBLIC_SURFACES
from llm_endpoint.results import (
    FAILURE_TAXONOMY_VERSION,
    FailureCode,
    FailureContext,
    PlainTextResult,
    Retryability,
    SafeDiagnostics,
    StructuredResult,
    TerminalResult,
    TypedFailure,
    failure,
)

__version__ = "0.1.0"

__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "FAILURE_TAXONOMY_VERSION",
    "PUBLIC_SURFACES",
    "PUBLIC_SURFACE_MANIFEST_VERSION",
    "ConfigValidationReport",
    "EndpointConfig",
    "EndpointPool",
    "FailureCode",
    "FailureContext",
    "LLMEndpointConfig",
    "OperationConfig",
    "OperationRuntimePolicy",
    "PlainTextResult",
    "ProviderFormat",
    "ReasoningMode",
    "RetryPolicy",
    "Retryability",
    "RoleConfig",
    "SafeDiagnostics",
    "StructuredResult",
    "StructuredOutputMode",
    "TerminalResult",
    "TypedFailure",
    "__version__",
    "config_identity",
    "failure",
    "validate_config",
]
