"""Redacted telemetry event contracts for the endpoint boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from llm_endpoint.results import FailureClass

TELEMETRY_SCHEMA_VERSION = "v1"

FORBIDDEN_TELEMETRY_FIELDS = frozenset(
    {
        "api_key",
        "authorization",
        "body",
        "credential",
        "headers",
        "message",
        "messages",
        "prompt",
        "prompts",
        "raw_request",
        "raw_response",
        "response",
        "secret",
    }
)


class TelemetryEventFamily(StrEnum):
    """Required public telemetry event families."""

    REGISTRY_VALIDATED = "llm.registry.validated"
    POLICY_RESOLVED = "llm.policy.resolved"
    ROLE_HEALTH = "llm.role.health"
    POOL_ATTEMPT = "llm.pool.attempt"
    SUCCESS = "llm.success"
    FAILURE = "llm.failure"
    POOL_EXHAUSTED = "llm.pool.exhausted"
    DEADLINE_EXCEEDED = "llm.deadline.exceeded"
    CANCELLATION = "llm.cancellation"
    LATE_RESPONSE_DISCARDED = "llm.late_response.discarded"
    ENDPOINT_SUPPRESSED = "llm.endpoint.suppressed"
    BUDGET_VIOLATION = "llm.budget.violation"
    SMOKE_RESULT = "llm.smoke.result"
    FAKE_PROVIDER_RESULT = "llm.fake_provider.result"


class RedactionStatus(StrEnum):
    """Whether the event payload has been scrubbed before emission."""

    REDACTED = "redacted"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Provider-reported token usage after safe normalization."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        values = (self.input_tokens, self.output_tokens, self.total_tokens)
        if any(value is not None and value < 0 for value in values):
            raise ValueError("token usage values must be omitted or non-negative")


@dataclass(frozen=True, slots=True)
class TelemetryContext:
    """Common redacted correlation fields carried by invocation events."""

    operation_invocation_id: str
    role: str | None = None
    operation_ref: str | None = None
    endpoint_uid: str | None = None
    attempt_trace_id: str | None = None
    policy_fingerprint: str | None = None
    elapsed_ms: int | None = None
    failure_class: FailureClass | None = None

    def __post_init__(self) -> None:
        if not self.operation_invocation_id:
            raise ValueError("operation_invocation_id is required")
        if self.elapsed_ms is not None and self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must be omitted or non-negative")


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    """Public event envelope safe to send to a host telemetry sink."""

    family: TelemetryEventFamily
    context: TelemetryContext
    attributes: Mapping[str, str] = field(default_factory=dict)
    token_usage: TokenUsage | None = None
    redaction_status: RedactionStatus = RedactionStatus.REDACTED
    schema_version: str = TELEMETRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TELEMETRY_SCHEMA_VERSION:
            raise ValueError("only telemetry schema version 'v1' is supported under Zero BC policy")
        if self.redaction_status not in {RedactionStatus.REDACTED, RedactionStatus.NOT_APPLICABLE}:
            raise ValueError("telemetry events must be redacted or explicitly not_applicable")
        unsafe_keys = forbidden_attribute_keys(self.attributes)
        if unsafe_keys:
            names = ", ".join(sorted(unsafe_keys))
            raise ValueError(f"telemetry attributes contain forbidden fields: {names}")


class TelemetrySink(Protocol):
    """Host-owned sink for already-redacted telemetry events."""

    def __call__(self, event: TelemetryEvent) -> None: ...


@dataclass(slots=True)
class TelemetryEmitter:
    """Best-effort emitter that records events without affecting terminal outcomes."""

    sink: TelemetrySink | None = None
    captured_events: list[TelemetryEvent] = field(default_factory=list)
    sink_failures: list[str] = field(default_factory=list)

    def emit(self, event: TelemetryEvent) -> TelemetryEvent:
        """Capture and optionally forward a redacted event."""

        self.captured_events.append(event)
        if self.sink is None:
            return event
        try:
            self.sink(event)
        except Exception as exc:  # pragma: no cover - sink behavior is host-owned.
            self.sink_failures.append(exc.__class__.__name__)
        return event

    def emit_all(self, events: tuple[TelemetryEvent, ...]) -> tuple[TelemetryEvent, ...]:
        """Emit a batch while preserving input order."""

        return tuple(self.emit(event) for event in events)


def forbidden_attribute_keys(attributes: Mapping[str, str]) -> frozenset[str]:
    """Return forbidden telemetry keys by exact key or dotted-path segment."""

    unsafe: set[str] = set()
    for key in attributes:
        segments = {segment.lower() for segment in key.replace("-", "_").split(".")}
        if key.lower() in FORBIDDEN_TELEMETRY_FIELDS or segments & FORBIDDEN_TELEMETRY_FIELDS:
            unsafe.add(key)
    return frozenset(unsafe)


def telemetry_event(
    *,
    family: TelemetryEventFamily,
    operation_invocation_id: str,
    role: str | None = None,
    operation_ref: str | None = None,
    endpoint_uid: str | None = None,
    attempt_trace_id: str | None = None,
    policy_fingerprint: str | None = None,
    elapsed_ms: int | None = None,
    failure_class: FailureClass | None = None,
    attributes: Mapping[str, str] | None = None,
    token_usage: TokenUsage | None = None,
    redaction_status: RedactionStatus = RedactionStatus.REDACTED,
) -> TelemetryEvent:
    """Build a redacted event with required common invocation fields."""

    return TelemetryEvent(
        family=family,
        context=TelemetryContext(
            operation_invocation_id=operation_invocation_id,
            role=role,
            operation_ref=operation_ref,
            endpoint_uid=endpoint_uid,
            attempt_trace_id=attempt_trace_id,
            policy_fingerprint=policy_fingerprint,
            elapsed_ms=elapsed_ms,
            failure_class=failure_class,
        ),
        attributes=attributes or {},
        token_usage=token_usage,
        redaction_status=redaction_status,
    )
