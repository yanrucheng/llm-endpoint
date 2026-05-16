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
            code=FailureCode.MALFORMED_PROVIDER_OUTPUT,
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

    if context.schema.validate is not None and not context.schema.validate(extracted_or_failure):
        return failure(
            code=FailureCode.SCHEMA_VALIDATION_FAILED,
            message="structured provider output failed schema validation",
            operation_invocation_id=context.operation_invocation_id,
            role=context.role,
            operation_ref=context.operation_ref,
            endpoint_uid=context.endpoint_uid,
            policy_fingerprint=context.policy_fingerprint,
            elapsed_ms=context.elapsed_ms,
            attempt_trace_id=context.attempt_trace_id,
            safe_context=_schema_context(context.schema),
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


def _extract_payload(
    outcome: ProviderOutcome,
    context: StructuredOutputContext,
) -> Mapping[str, Any] | TerminalResult:
    payload = outcome.payload
    if payload is None:
        return failure(
            code=FailureCode.MALFORMED_PROVIDER_OUTPUT,
            message="provider success outcome omitted structured payload",
            operation_invocation_id=context.operation_invocation_id,
            role=context.role,
            operation_ref=context.operation_ref,
            endpoint_uid=context.endpoint_uid,
            policy_fingerprint=context.policy_fingerprint,
            elapsed_ms=context.elapsed_ms,
            attempt_trace_id=context.attempt_trace_id,
        )

    content = payload.content
    if not isinstance(content, Mapping):
        return failure(
            code=FailureCode.MALFORMED_PROVIDER_OUTPUT,
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
                code=FailureCode.WRONG_TOOL_OUTPUT,
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
            code=FailureCode.MALFORMED_PROVIDER_OUTPUT,
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
