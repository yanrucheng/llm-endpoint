"""Host callback contracts for secrets and structured-output schemas."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from llm_endpoint.results import FailureCode, SafeDiagnostics, TypedFailure, failure

SECRET_RESOLVER_CONTRACT_VERSION = "v1"
SCHEMA_RESOLVER_CONTRACT_VERSION = "v1"


class SecretResolutionStatus(StrEnum):
    """Machine-readable host secret resolution status."""

    RESOLVED = "resolved"
    MISSING = "missing"
    FAILED = "failed"


class SchemaResolutionStatus(StrEnum):
    """Machine-readable host schema resolution status."""

    RESOLVED = "resolved"
    NOT_FOUND = "not_found"
    FAILED = "failed"


@dataclass(frozen=True, slots=True, repr=False)
class SecretValue:
    """Resolved credential value that must never appear in public diagnostics."""

    ref: str
    value: str

    def __post_init__(self) -> None:
        if not self.ref:
            raise ValueError("secret ref is required")
        if not self.value:
            raise ValueError("secret value is required")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(ref={self.ref!r}, value='<redacted>')"


@dataclass(frozen=True, slots=True)
class SecretResolution:
    """Host callback output for credential refs."""

    ref: str
    status: SecretResolutionStatus
    secret: SecretValue | None = None
    diagnostics: SafeDiagnostics | None = None
    contract_version: str = SECRET_RESOLVER_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != SECRET_RESOLVER_CONTRACT_VERSION:
            raise ValueError("only secret resolver contract version 'v1' is supported")
        if not self.ref:
            raise ValueError("secret ref is required")
        if self.status is SecretResolutionStatus.RESOLVED and self.secret is None:
            raise ValueError("resolved secret status requires a SecretValue")
        if self.status is not SecretResolutionStatus.RESOLVED and self.secret is not None:
            raise ValueError("unresolved secret status cannot carry a SecretValue")

    def to_failure(
        self, *, operation_invocation_id: str, endpoint_uid: str | None = None
    ) -> TypedFailure:
        """Convert unresolved secret resolution into a redacted typed failure."""

        if self.status is SecretResolutionStatus.RESOLVED:
            raise ValueError("resolved secrets do not produce failures")
        code = (
            FailureCode.MISSING_SECRET
            if self.status is SecretResolutionStatus.MISSING
            else FailureCode.SECRET_RESOLUTION_FAILED
        )
        diagnostics = self.diagnostics or SafeDiagnostics(message="secret resolution failed")
        return failure(
            code=code,
            message=diagnostics.message,
            operation_invocation_id=operation_invocation_id,
            endpoint_uid=endpoint_uid,
            remediation_hint=diagnostics.remediation_hint,
            safe_context={"secret_ref": self.ref, **dict(diagnostics.safe_context)},
        )


@dataclass(frozen=True, slots=True)
class SchemaContract:
    """Resolved host schema identity and validation hook."""

    ref: str
    name: str
    version: str
    fingerprint: str
    json_schema: Mapping[str, Any]
    validate: Callable[[Mapping[str, Any]], bool] | None = None

    def __post_init__(self) -> None:
        if not self.ref or not self.name or not self.version:
            raise ValueError("schema ref, name, and version are required")
        if not self.fingerprint.startswith("sha256:"):
            raise ValueError("schema fingerprint must use the sha256: prefix")
        if not self.json_schema:
            raise ValueError("json_schema is required")


@dataclass(frozen=True, slots=True)
class SchemaResolution:
    """Host callback output for structured-output schema refs."""

    ref: str
    status: SchemaResolutionStatus
    schema: SchemaContract | None = None
    diagnostics: SafeDiagnostics | None = None
    contract_version: str = SCHEMA_RESOLVER_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != SCHEMA_RESOLVER_CONTRACT_VERSION:
            raise ValueError("only schema resolver contract version 'v1' is supported")
        if not self.ref:
            raise ValueError("schema ref is required")
        if self.status is SchemaResolutionStatus.RESOLVED and self.schema is None:
            raise ValueError("resolved schema status requires a SchemaContract")
        if self.status is not SchemaResolutionStatus.RESOLVED and self.schema is not None:
            raise ValueError("unresolved schema status cannot carry a SchemaContract")

    def to_failure(
        self, *, operation_invocation_id: str, operation_ref: str | None = None
    ) -> TypedFailure:
        """Convert unresolved schema resolution into a redacted typed failure."""

        if self.status is SchemaResolutionStatus.RESOLVED:
            raise ValueError("resolved schemas do not produce failures")
        diagnostics = self.diagnostics or SafeDiagnostics(message="schema resolution failed")
        return failure(
            code=FailureCode.SCHEMA_NOT_FOUND,
            message=diagnostics.message,
            operation_invocation_id=operation_invocation_id,
            operation_ref=operation_ref,
            remediation_hint=diagnostics.remediation_hint,
            safe_context={"schema_ref": self.ref, **dict(diagnostics.safe_context)},
        )


class SecretResolver(Protocol):
    """Host-owned callback that resolves one secret ref."""

    def __call__(self, ref: str) -> SecretResolution: ...


class SchemaResolver(Protocol):
    """Host-owned callback that resolves one schema ref."""

    def __call__(self, ref: str) -> SchemaResolution: ...


def resolved_secret(ref: str, value: str) -> SecretResolution:
    """Build a successful secret resolution without exposing value in repr output."""

    return SecretResolution(
        ref=ref,
        status=SecretResolutionStatus.RESOLVED,
        secret=SecretValue(ref=ref, value=value),
    )


def missing_secret(ref: str, message: str = "secret is missing") -> SecretResolution:
    """Build a redacted missing-secret callback result."""

    return SecretResolution(
        ref=ref,
        status=SecretResolutionStatus.MISSING,
        diagnostics=SafeDiagnostics(message=message, safe_context={"secret_ref": ref}),
    )


def resolved_schema(
    *,
    ref: str,
    name: str,
    version: str,
    fingerprint: str,
    json_schema: Mapping[str, Any],
    validate: Callable[[Mapping[str, Any]], bool] | None = None,
) -> SchemaResolution:
    """Build a successful schema resolution with stable identity fields."""

    return SchemaResolution(
        ref=ref,
        status=SchemaResolutionStatus.RESOLVED,
        schema=SchemaContract(
            ref=ref,
            name=name,
            version=version,
            fingerprint=fingerprint,
            json_schema=json_schema,
            validate=validate,
        ),
    )
