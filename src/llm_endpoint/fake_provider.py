"""Deterministic fake-provider harness for offline invocation hardening."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from llm_endpoint.adapters import (
    AdapterInvocationPlan,
    FakeProviderAdapter,
    ProviderAdapter,
    ProviderOutcome,
    ProviderOutcomeKind,
    provider_failure,
    provider_success,
)
from llm_endpoint.config import ProviderFormat
from llm_endpoint.results import FailureCode

FAKE_PROVIDER_HARNESS_VERSION = "v1"


class FakeProviderScenario(StrEnum):
    """Named fake-provider cases required by the Phase 4 harness contract."""

    SUCCESS = "success"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    TIMEOUT = "timeout"
    TRANSIENT_NETWORK = "transient_network"
    SERVER_5XX = "server_5xx"
    REFUSAL = "refusal"
    MALFORMED_JSON = "malformed_json"
    WRONG_TOOL = "wrong_tool"
    DUPLICATE_TERMINAL_TOOL = "duplicate_terminal_tool"
    SCHEMA_VIOLATION = "schema_violation"
    LATE_RESPONSE = "late_response"
    POOL_EXHAUSTION = "pool_exhaustion"


@dataclass(slots=True)
class FakeCancellationToken:
    """Test-owned cancellation token usable by sync and async invocation paths."""

    cancelled: bool = False

    def is_cancelled(self) -> bool:
        """Return true once a fake scenario has cancelled the invocation."""

        return self.cancelled

    def cancel(self) -> None:
        """Mark the token cancelled for deterministic route tests."""

        self.cancelled = True


@dataclass(frozen=True, slots=True)
class FakeProviderHarness:
    """Materialized fake-provider scenario set for one route invocation."""

    adapter: ProviderAdapter
    cancellation_token: FakeCancellationToken | None = None
    harness_version: str = FAKE_PROVIDER_HARNESS_VERSION

    def __post_init__(self) -> None:
        if self.harness_version != FAKE_PROVIDER_HARNESS_VERSION:
            raise ValueError("only fake-provider harness version 'v1' is supported")


@dataclass(slots=True)
class CancellingFakeProviderAdapter:
    """Fake adapter that cancels the caller token after selected endpoint attempts."""

    outcomes_by_endpoint: Mapping[str, Sequence[ProviderOutcome]]
    cancellation_token: FakeCancellationToken
    cancel_after_endpoint_uids: frozenset[str]
    provider_format: ProviderFormat = field(default=ProviderFormat.FAKE, init=False)
    calls_by_endpoint: dict[str, int] = field(default_factory=dict, init=False)

    def invoke(self, plan: AdapterInvocationPlan) -> ProviderOutcome:
        """Return the configured fake outcome, then cancel if the endpoint is selected."""

        if plan.provider_format is not ProviderFormat.FAKE:
            outcome = provider_failure(
                kind=ProviderOutcomeKind.NON_RETRYABLE_FAILURE,
                endpoint_uid=plan.endpoint_uid,
                elapsed_ms=0,
                failure_code=FailureCode.UNSUPPORTED_PROVIDER_FORMAT,
                safe_provider_status={"adapter": "fake_provider_format_mismatch"},
            )
        else:
            outcomes = self.outcomes_by_endpoint.get(plan.endpoint_uid, ())
            call_index = self.calls_by_endpoint.get(plan.endpoint_uid, 0)
            self.calls_by_endpoint[plan.endpoint_uid] = call_index + 1
            outcome = (
                outcomes[call_index]
                if call_index < len(outcomes)
                else provider_failure(
                    kind=ProviderOutcomeKind.NON_RETRYABLE_FAILURE,
                    endpoint_uid=plan.endpoint_uid,
                    elapsed_ms=0,
                    failure_code=FailureCode.PROVIDER_FAILURE,
                    safe_provider_status={"adapter": "fake_outcome_missing"},
                )
            )
        if plan.endpoint_uid in self.cancel_after_endpoint_uids:
            self.cancellation_token.cancel()
        return outcome


def build_fake_provider_harness(
    scenarios_by_endpoint: Mapping[str, Sequence[FakeProviderScenario | ProviderOutcome]],
    *,
    cancel_after_endpoint_uids: frozenset[str] = frozenset(),
) -> FakeProviderHarness:
    """Build a deterministic fake adapter from named scenarios or explicit outcomes."""

    outcomes = {
        endpoint_uid: tuple(
            scenario
            if isinstance(scenario, ProviderOutcome)
            else fake_outcome(scenario, endpoint_uid)
            for scenario in scenarios
        )
        for endpoint_uid, scenarios in scenarios_by_endpoint.items()
    }
    if cancel_after_endpoint_uids:
        token = FakeCancellationToken()
        adapter = CancellingFakeProviderAdapter(
            outcomes_by_endpoint=outcomes,
            cancellation_token=token,
            cancel_after_endpoint_uids=cancel_after_endpoint_uids,
        )
        return FakeProviderHarness(adapter=adapter, cancellation_token=token)
    return FakeProviderHarness(adapter=FakeProviderAdapter(outcomes))


def fake_outcome(scenario: FakeProviderScenario, endpoint_uid: str) -> ProviderOutcome:
    """Return one normalized fake provider outcome for a named scenario."""

    if scenario is FakeProviderScenario.SUCCESS:
        return provider_success(endpoint_uid=endpoint_uid, elapsed_ms=20, content="ok")
    if scenario is FakeProviderScenario.RATE_LIMIT:
        return _availability_failure(
            endpoint_uid,
            FailureCode.INVOCATION_RATE_LIMITED,
            status="rate_limited",
        )
    if scenario is FakeProviderScenario.QUOTA:
        return _availability_failure(
            endpoint_uid,
            FailureCode.INVOCATION_QUOTA_EXHAUSTED,
            status="quota_exhausted",
        )
    if scenario is FakeProviderScenario.TIMEOUT:
        return provider_failure(
            kind=ProviderOutcomeKind.TIMEOUT,
            endpoint_uid=endpoint_uid,
            elapsed_ms=500,
            failure_code=FailureCode.LOCAL_CANDIDATE_TIMEOUT,
            safe_provider_status={"status": "timeout"},
        )
    if scenario is FakeProviderScenario.TRANSIENT_NETWORK:
        return _availability_failure(
            endpoint_uid,
            FailureCode.TRANSIENT_NETWORK,
            status=scenario.value,
        )
    if scenario is FakeProviderScenario.SERVER_5XX:
        return _availability_failure(
            endpoint_uid,
            FailureCode.PROVIDER_5XX,
            status=scenario.value,
        )
    if scenario is FakeProviderScenario.REFUSAL:
        return provider_failure(
            kind=ProviderOutcomeKind.REFUSAL,
            endpoint_uid=endpoint_uid,
            elapsed_ms=20,
            failure_code=FailureCode.STRUCTURED_OUTPUT_REFUSAL,
            safe_provider_status={"status": "refusal"},
        )
    if scenario is FakeProviderScenario.MALFORMED_JSON:
        return provider_success(endpoint_uid=endpoint_uid, elapsed_ms=20, content="{not-json")
    if scenario is FakeProviderScenario.WRONG_TOOL:
        return provider_success(
            endpoint_uid=endpoint_uid,
            elapsed_ms=20,
            content={"answer": "ok"},
            tool_name="wrong_tool",
        )
    if scenario is FakeProviderScenario.DUPLICATE_TERMINAL_TOOL:
        return provider_failure(
            kind=ProviderOutcomeKind.NON_RETRYABLE_FAILURE,
            endpoint_uid=endpoint_uid,
            elapsed_ms=20,
            failure_code=FailureCode.INVALID_STRUCTURED_OUTPUT_PAYLOAD,
            safe_provider_status={"status": "duplicate_terminal_tool"},
        )
    if scenario is FakeProviderScenario.SCHEMA_VIOLATION:
        return provider_success(endpoint_uid=endpoint_uid, elapsed_ms=20, content={"answer": ""})
    if scenario is FakeProviderScenario.LATE_RESPONSE:
        return provider_success(endpoint_uid=endpoint_uid, elapsed_ms=10_000, content="late")
    if scenario is FakeProviderScenario.POOL_EXHAUSTION:
        return _availability_failure(
            endpoint_uid,
            FailureCode.TRANSIENT_NETWORK,
            status="pool_exhaustion",
        )
    raise ValueError(f"unsupported fake provider scenario: {scenario}")


def _availability_failure(
    endpoint_uid: str,
    failure_code: FailureCode,
    *,
    status: str,
) -> ProviderOutcome:
    return provider_failure(
        kind=ProviderOutcomeKind.RETRYABLE_FAILURE,
        endpoint_uid=endpoint_uid,
        elapsed_ms=100,
        failure_code=failure_code,
        safe_provider_status={"status": status},
    )
