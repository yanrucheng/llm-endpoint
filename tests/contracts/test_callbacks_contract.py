import pytest

from llm_endpoint.callbacks import (
    SchemaContract,
    SchemaResolution,
    SchemaResolutionStatus,
    SecretResolutionStatus,
    missing_secret,
    resolved_schema,
    resolved_secret,
)
from llm_endpoint.results import FailureCode


def test_secret_resolution_contract_is_redacted() -> None:
    resolution = resolved_secret("secret://primary", "super-secret-token")

    assert resolution.status is SecretResolutionStatus.RESOLVED
    assert resolution.secret is not None
    assert "super-secret-token" not in repr(resolution.secret)

    missing = missing_secret("secret://missing")
    typed_failure = missing.to_failure(operation_invocation_id="inv-1", endpoint_uid="primary")

    assert typed_failure.code is FailureCode.CREDENTIAL_UNAVAILABLE
    assert typed_failure.diagnostics.safe_context["secret_ref"] == "secret://missing"
    assert "super-secret-token" not in repr(typed_failure)


def test_schema_identity_is_required() -> None:
    with pytest.raises(ValueError, match="sha256"):
        SchemaContract(
            ref="schema://answer",
            name="answer",
            version="1",
            fingerprint="not-sha",
            json_schema={"type": "object"},
        )


def test_schema_resolution_contract() -> None:
    resolution = resolved_schema(
        ref="schema://answer",
        name="answer",
        version="1",
        fingerprint="sha256:abc",
        json_schema={"type": "object"},
    )

    assert resolution.status is SchemaResolutionStatus.RESOLVED
    assert resolution.schema is not None
    assert resolution.schema.fingerprint == "sha256:abc"

    missing = SchemaResolution(ref="schema://missing", status=SchemaResolutionStatus.NOT_FOUND)
    typed_failure = missing.to_failure(operation_invocation_id="inv-2", operation_ref="draft")

    assert typed_failure.code is FailureCode.UNKNOWN_SCHEMA_CONTRACT
