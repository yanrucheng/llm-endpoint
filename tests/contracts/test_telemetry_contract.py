import pytest

from llm_endpoint.results import FailureClass
from llm_endpoint.telemetry import (
    RedactionStatus,
    TelemetryEmitter,
    TelemetryEventFamily,
    TokenUsage,
    telemetry_event,
)


def test_redacted_event_contract() -> None:
    event = telemetry_event(
        family=TelemetryEventFamily.POOL_ATTEMPT,
        operation_invocation_id="inv-1",
        role="writer",
        operation_ref="draft",
        endpoint_uid="primary",
        attempt_trace_id="trace-1",
        policy_fingerprint="policy-1",
        elapsed_ms=12,
        failure_class=FailureClass.PROVIDER_AVAILABILITY,
        attributes={"provider_status": "rate_limited"},
        token_usage=TokenUsage(input_tokens=10, output_tokens=2, total_tokens=12),
    )

    assert event.redaction_status is RedactionStatus.REDACTED
    assert event.context.operation_invocation_id == "inv-1"
    assert event.token_usage is not None
    assert event.token_usage.total_tokens == 12


def test_forbidden_telemetry_fields_fail_closed() -> None:
    with pytest.raises(ValueError, match="forbidden fields"):
        telemetry_event(
            family=TelemetryEventFamily.FAILURE,
            operation_invocation_id="inv-2",
            attributes={"raw_response": "provider payload"},
        )


def test_telemetry_emitter_is_best_effort() -> None:
    def failing_sink(_event: object) -> None:
        raise RuntimeError("sink unavailable")

    emitter = TelemetryEmitter(sink=failing_sink)
    event = telemetry_event(
        family=TelemetryEventFamily.REGISTRY_VALIDATED,
        operation_invocation_id="inv-3",
        attributes={"ok": "true"},
    )

    emitted = emitter.emit(event)

    assert emitted is event
    assert emitter.captured_events == [event]
    assert emitter.sink_failures == ["RuntimeError"]
