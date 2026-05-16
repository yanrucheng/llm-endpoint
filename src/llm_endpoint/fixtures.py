"""Golden contract fixture skeleton manifest for Phase 1 conformance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

FIXTURE_MANIFEST_VERSION = "v1"


class FixtureArea(StrEnum):
    """Fixture areas required before parallel implementation starts."""

    CONFIG = "config"
    TELEMETRY = "telemetry"
    FAILURES = "failures"
    POLICY = "policy"
    FAKE_PROVIDER = "fake_provider"
    ROUTER = "router"
    STRUCTURED_OUTPUT = "structured_output"
    ADAPTER_PARITY = "adapter_parity"


class FixturePolarity(StrEnum):
    """Positive or negative contract fixture coverage."""

    POSITIVE = "positive"
    NEGATIVE = "negative"


@dataclass(frozen=True, slots=True)
class ContractFixture:
    """One reusable golden fixture skeleton entry."""

    area: FixtureArea
    polarity: FixturePolarity
    name: str
    path: str
    owner: str
    required: bool = True

    def __post_init__(self) -> None:
        if not self.name or not self.path or not self.owner:
            raise ValueError("fixture name, path, and owner are required")


CONTRACT_FIXTURES: tuple[ContractFixture, ...] = (
    ContractFixture(
        area=FixtureArea.CONFIG,
        polarity=FixturePolarity.POSITIVE,
        name="valid_config",
        path="tests/fixtures/contracts/config/valid.json",
        owner="registry-owner",
    ),
    ContractFixture(
        area=FixtureArea.CONFIG,
        polarity=FixturePolarity.NEGATIVE,
        name="invalid_config",
        path="tests/fixtures/contracts/config/invalid.json",
        owner="registry-owner",
    ),
    ContractFixture(
        area=FixtureArea.TELEMETRY,
        polarity=FixturePolarity.POSITIVE,
        name="redacted_event",
        path="tests/fixtures/contracts/telemetry/redacted_event.json",
        owner="observability-owner",
    ),
    ContractFixture(
        area=FixtureArea.TELEMETRY,
        polarity=FixturePolarity.NEGATIVE,
        name="forbidden_event_fields",
        path="tests/fixtures/contracts/telemetry/forbidden_event_fields.json",
        owner="observability-owner",
    ),
    ContractFixture(
        area=FixtureArea.FAILURES,
        polarity=FixturePolarity.POSITIVE,
        name="typed_failure",
        path="tests/fixtures/contracts/failures/typed_failure.json",
        owner="runtime-owner",
    ),
    ContractFixture(
        area=FixtureArea.FAILURES,
        polarity=FixturePolarity.NEGATIVE,
        name="unsafe_failure_diagnostics",
        path="tests/fixtures/contracts/failures/unsafe_failure_diagnostics.json",
        owner="runtime-owner",
    ),
    ContractFixture(
        area=FixtureArea.POLICY,
        polarity=FixturePolarity.POSITIVE,
        name="effective_policy",
        path="tests/fixtures/contracts/policy/effective_policy.json",
        owner="runtime-owner",
    ),
    ContractFixture(
        area=FixtureArea.POLICY,
        polarity=FixturePolarity.NEGATIVE,
        name="budget_violation",
        path="tests/fixtures/contracts/policy/budget_violation.json",
        owner="runtime-owner",
    ),
    ContractFixture(
        area=FixtureArea.FAKE_PROVIDER,
        polarity=FixturePolarity.POSITIVE,
        name="fake_success",
        path="tests/fixtures/contracts/fake_provider/success.json",
        owner="test-owner",
    ),
    ContractFixture(
        area=FixtureArea.FAKE_PROVIDER,
        polarity=FixturePolarity.NEGATIVE,
        name="fake_retryable_failure",
        path="tests/fixtures/contracts/fake_provider/retryable_failure.json",
        owner="test-owner",
    ),
    ContractFixture(
        area=FixtureArea.ROUTER,
        polarity=FixturePolarity.POSITIVE,
        name="ordered_failover",
        path="tests/fixtures/contracts/router/ordered_failover.json",
        owner="runtime-owner",
    ),
    ContractFixture(
        area=FixtureArea.ROUTER,
        polarity=FixturePolarity.NEGATIVE,
        name="pool_exhausted",
        path="tests/fixtures/contracts/router/pool_exhausted.json",
        owner="runtime-owner",
    ),
    ContractFixture(
        area=FixtureArea.STRUCTURED_OUTPUT,
        polarity=FixturePolarity.POSITIVE,
        name="schema_validated",
        path="tests/fixtures/contracts/structured_output/schema_validated.json",
        owner="schema-owner",
    ),
    ContractFixture(
        area=FixtureArea.STRUCTURED_OUTPUT,
        polarity=FixturePolarity.NEGATIVE,
        name="schema_violation",
        path="tests/fixtures/contracts/structured_output/schema_violation.json",
        owner="schema-owner",
    ),
    ContractFixture(
        area=FixtureArea.ADAPTER_PARITY,
        polarity=FixturePolarity.POSITIVE,
        name="provider_success_mapping",
        path="tests/fixtures/contracts/adapter_parity/provider_success_mapping.json",
        owner="adapter-owner",
    ),
    ContractFixture(
        area=FixtureArea.ADAPTER_PARITY,
        polarity=FixturePolarity.NEGATIVE,
        name="raw_provider_leak",
        path="tests/fixtures/contracts/adapter_parity/raw_provider_leak.json",
        owner="adapter-owner",
    ),
)


def fixtures_by_area(area: FixtureArea) -> tuple[ContractFixture, ...]:
    """Return fixture skeleton entries for one conformance area."""

    return tuple(fixture for fixture in CONTRACT_FIXTURES if fixture.area is area)


def assert_fixture_manifest_complete() -> None:
    """Fail if any required area lacks positive and negative fixture skeletons."""

    missing: list[str] = []
    for area in FixtureArea:
        polarities = {fixture.polarity for fixture in fixtures_by_area(area) if fixture.required}
        if polarities != {FixturePolarity.POSITIVE, FixturePolarity.NEGATIVE}:
            missing.append(area.value)
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"fixture manifest missing required coverage: {names}")
