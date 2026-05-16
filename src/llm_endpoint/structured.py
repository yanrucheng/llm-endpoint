"""Structured-output extraction and schema validation pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from llm_endpoint.adapters import ProviderOutcome
from llm_endpoint.callbacks import SchemaContract
from llm_endpoint.config import StructuredOutputMode
from llm_endpoint.results import FailureCode, StructuredResult, TerminalResult, failure

STRUCTURED_OUTPUT_PIPELINE_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class StructuredOutputContext:
    """Safe context needed to turn provider payloads into structured results."""

    operation_invocation_id: str
    endpoint_uid: str
    policy_fingerprint: str
    elapsed_ms: int
    schema: SchemaContract
    mode: StructuredOutputMode
    role: str | None = None
    operation_ref: str | None = None
    attempt_trace_id: str | None = None


def normalize_structured_provider_outcome(
    outcome: ProviderOutcome,
    *,
    context: StructuredOutputContext,
) -> TerminalResult:
    """Extract, validate, and normalize one structured provider success payload."""

    if outcome.payload is None:
        return failure(
            code=FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD,
            message="provider success outcome omitted structured payload",
            operation_invocation_id=context.operation_invocation_id,
            role=context.role,
            operation_ref=context.operation_ref,
            endpoint_uid=context.endpoint_uid,
            policy_fingerprint=context.policy_fingerprint,
            elapsed_ms=context.elapsed_ms,
            attempt_trace_id=context.attempt_trace_id,
        )

    extracted_or_failure = _extract_payload(outcome, context)
    if not isinstance(extracted_or_failure, Mapping):
        return extracted_or_failure

    if not _matches_json_schema(extracted_or_failure, context.schema.json_schema):
        return _schema_validation_failure(
            context,
            validation_stage="json_schema",
            message="structured provider output failed json schema validation",
        )

    if context.schema.validate is not None:
        try:
            is_valid = context.schema.validate(extracted_or_failure)
        except Exception as exc:  # pragma: no cover - host validator behavior is external.
            return _schema_validation_failure(
                context,
                validation_stage="host_validator",
                message="structured provider output validator raised",
                extra_context={"validator_exception": exc.__class__.__name__},
            )
        if not is_valid:
            return _schema_validation_failure(
                context,
                validation_stage="host_validator",
                message="structured provider output failed host validation",
            )

    return StructuredResult(
        value=dict(extracted_or_failure),
        schema_name=context.schema.name,
        schema_version=context.schema.version,
        schema_fingerprint=context.schema.fingerprint,
        operation_invocation_id=context.operation_invocation_id,
        endpoint_uid=context.endpoint_uid,
        policy_fingerprint=context.policy_fingerprint,
        elapsed_ms=context.elapsed_ms,
    )


def _schema_validation_failure(
    context: StructuredOutputContext,
    *,
    validation_stage: str,
    message: str,
    extra_context: Mapping[str, str] | None = None,
) -> TerminalResult:
    safe_context = {
        **_schema_context(context.schema),
        "validation_stage": validation_stage,
    }
    if extra_context is not None:
        safe_context.update(extra_context)
    return failure(
        code=FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD,
        message=message,
        operation_invocation_id=context.operation_invocation_id,
        role=context.role,
        operation_ref=context.operation_ref,
        endpoint_uid=context.endpoint_uid,
        policy_fingerprint=context.policy_fingerprint,
        elapsed_ms=context.elapsed_ms,
        attempt_trace_id=context.attempt_trace_id,
        safe_context=safe_context,
    )


def _matches_json_schema(value: Mapping[str, Any], schema: Mapping[str, Any]) -> bool:
    """Apply the supported in-process JSON Schema subset before host validation."""

    schema_type = schema.get("type")
    if schema_type is not None and schema_type != "object":
        return False

    required = schema.get("required", ())
    if not isinstance(required, tuple | list):
        return False
    if any(not isinstance(key, str) or key not in value for key in required):
        return False

    properties = schema.get("properties", {})
    if properties is not None and not isinstance(properties, Mapping):
        return False
    if isinstance(properties, Mapping):
        for key, rules in properties.items():
            if key in value and isinstance(rules, Mapping) and not _matches_property_schema(
                value[key],
                rules,
            ):
                return False

    if schema.get("additionalProperties") is False and isinstance(properties, Mapping):
        allowed_keys = set(properties)
        if any(key not in allowed_keys for key in value):
            return False

    return True


def _matches_property_schema(value: Any, rules: Mapping[str, Any]) -> bool:
    if "const" in rules and value != rules["const"]:
        return False
    allowed_values = rules.get("enum")
    if allowed_values is not None and value not in allowed_values:
        return False

    expected_type = rules.get("type")
    if expected_type is None:
        return True
    return _matches_json_type(value, expected_type)


def _matches_json_type(value: Any, expected_type: Any) -> bool:
    if isinstance(expected_type, list | tuple):
        return any(_matches_json_type(value, item) for item in expected_type)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, Mapping)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "null":
        return value is None
    return False


def _extract_payload(
    outcome: ProviderOutcome,
    context: StructuredOutputContext,
) -> Mapping[str, Any] | TerminalResult:
    payload = outcome.payload
    if payload is None:
        return failure(
            code=FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD,
            message="provider success outcome omitted structured payload",
            operation_invocation_id=context.operation_invocation_id,
            role=context.role,
            operation_ref=context.operation_ref,
            endpoint_uid=context.endpoint_uid,
            policy_fingerprint=context.policy_fingerprint,
            elapsed_ms=context.elapsed_ms,
            attempt_trace_id=context.attempt_trace_id,
        )
    assert payload is not None

    content = payload.content
    if not isinstance(content, Mapping):
        return failure(
            code=FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD,
            message="structured provider output must be a mapping",
            operation_invocation_id=context.operation_invocation_id,
            role=context.role,
            operation_ref=context.operation_ref,
            endpoint_uid=context.endpoint_uid,
            policy_fingerprint=context.policy_fingerprint,
            elapsed_ms=context.elapsed_ms,
            attempt_trace_id=context.attempt_trace_id,
            safe_context=_schema_context(context.schema),
        )

    if context.mode is StructuredOutputMode.TOOL_CALL:
        if payload.tool_name != context.schema.name:
            return failure(
                code=FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD,
                message="provider returned the wrong terminal tool",
                operation_invocation_id=context.operation_invocation_id,
                role=context.role,
                operation_ref=context.operation_ref,
                endpoint_uid=context.endpoint_uid,
                policy_fingerprint=context.policy_fingerprint,
                elapsed_ms=context.elapsed_ms,
                attempt_trace_id=context.attempt_trace_id,
                safe_context={
                    **_schema_context(context.schema),
                    "tool_name": payload.tool_name or "",
                },
            )
    elif context.mode is not StructuredOutputMode.JSON_SCHEMA:
        return failure(
            code=FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD,
            message="unsupported structured-output extraction mode",
            operation_invocation_id=context.operation_invocation_id,
            role=context.role,
            operation_ref=context.operation_ref,
            endpoint_uid=context.endpoint_uid,
            policy_fingerprint=context.policy_fingerprint,
            elapsed_ms=context.elapsed_ms,
            attempt_trace_id=context.attempt_trace_id,
            safe_context={"structured_output_mode": context.mode.value},
        )

    return content


def _schema_context(schema: SchemaContract) -> Mapping[str, str]:
    return {
        "schema_ref": schema.ref,
        "schema_name": schema.name,
        "schema_version": schema.version,
        "schema_fingerprint": schema.fingerprint,
    }
