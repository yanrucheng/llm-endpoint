"""Golden contract fixture skeletons and consumer contract-pack manifest."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

FIXTURE_MANIFEST_VERSION = "v1"
CONSUMER_CONTRACT_PACK_VERSION = "v1"


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
    PLAIN_TEXT = "plain_text"
    DIRECT_MIGRATION = "direct_migration"


class ConsumerContractArea(StrEnum):
    """Installable consumer contract areas required for Phase 5D adoption."""

    CONFIG_VALIDATION = "config_validation"
    FAILURE_TAXONOMY = "failure_taxonomy"
    TELEMETRY_REDACTION = "telemetry_redaction"
    STRUCTURED_OUTPUT = "structured_output"
    POOL_SIMULATION = "pool_simulation"
    PLAIN_TEXT = "plain_text"
    DIRECT_MIGRATION = "direct_migration"


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


@dataclass(frozen=True, slots=True)
class ConsumerContractCase:
    """One installable contract-pack case for consuming repositories."""

    area: ConsumerContractArea
    name: str
    fixture_path: str
    test_selector: str
    owner: str

    def __post_init__(self) -> None:
        if not self.name or not self.fixture_path or not self.test_selector or not self.owner:
            raise ValueError("consumer contract cases require name, fixture, selector, and owner")


@dataclass(frozen=True, slots=True)
class ConsumerContractPack:
    """Machine-readable contract pack consumers can install and run offline."""

    name: str
    version: str
    cases: tuple[ConsumerContractCase, ...]

    def __post_init__(self) -> None:
        if self.version != CONSUMER_CONTRACT_PACK_VERSION:
            raise ValueError("only consumer contract pack version 'v1' is supported")
        if not self.name:
            raise ValueError("consumer contract pack name is required")


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
        name="llm.config.invalid_endpoint_config",
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
    ContractFixture(
        area=FixtureArea.PLAIN_TEXT,
        polarity=FixturePolarity.POSITIVE,
        name="plain_text_success",
        path="tests/fixtures/contracts/plain_text/success.json",
        owner="api-owner",
    ),
    ContractFixture(
        area=FixtureArea.PLAIN_TEXT,
        polarity=FixturePolarity.NEGATIVE,
        name="plain_text_provider_failure",
        path="tests/fixtures/contracts/plain_text/provider_failure.json",
        owner="api-owner",
    ),
    ContractFixture(
        area=FixtureArea.DIRECT_MIGRATION,
        polarity=FixturePolarity.POSITIVE,
        name="direct_migration_parity",
        path="tests/fixtures/contracts/direct_migration/direct_migration.json",
        owner="migration-owner",
    ),
    ContractFixture(
        area=FixtureArea.DIRECT_MIGRATION,
        polarity=FixturePolarity.NEGATIVE,
        name="legacy_fields_rejected",
        path="tests/fixtures/contracts/direct_migration/legacy_fields_rejected.json",
        owner="migration-owner",
    ),
)


CONSUMER_CONTRACT_CASES: tuple[ConsumerContractCase, ...] = (
    ConsumerContractCase(
        area=ConsumerContractArea.CONFIG_VALIDATION,
        name="valid_config",
        fixture_path="tests/fixtures/contracts/config/valid.json",
        test_selector="tests/contracts/test_config_contract.py::test_valid_config_contract",
        owner="registry-owner",
    ),
    ConsumerContractCase(
        area=ConsumerContractArea.FAILURE_TAXONOMY,
        name="typed_failure",
        fixture_path="tests/fixtures/contracts/failures/typed_failure.json",
        test_selector="tests/contracts/test_results_contract.py::test_failure_contract_is_safe",
        owner="runtime-owner",
    ),
    ConsumerContractCase(
        area=ConsumerContractArea.TELEMETRY_REDACTION,
        name="redacted_event",
        fixture_path="tests/fixtures/contracts/telemetry/redacted_event.json",
        test_selector="tests/contracts/test_telemetry_contract.py::test_redacted_event_contract",
        owner="observability-owner",
    ),
    ConsumerContractCase(
        area=ConsumerContractArea.STRUCTURED_OUTPUT,
        name="schema_validated",
        fixture_path="tests/fixtures/contracts/structured_output/schema_validated.json",
        test_selector=(
            "tests/contracts/test_structured_output_contract.py::"
            "test_json_schema_structured_output_validates_and_emits_schema_identity"
        ),
        owner="schema-owner",
    ),
    ConsumerContractCase(
        area=ConsumerContractArea.POOL_SIMULATION,
        name="ordered_failover",
        fixture_path="tests/fixtures/contracts/router/ordered_failover.json",
        test_selector="tests/contracts/test_router_contract.py::test_ordered_retryable_failover",
        owner="runtime-owner",
    ),
    ConsumerContractCase(
        area=ConsumerContractArea.PLAIN_TEXT,
        name="plain_text_success",
        fixture_path="tests/fixtures/contracts/plain_text/success.json",
        test_selector=(
            "tests/contracts/test_phase4_invocation_hardening.py::"
            "test_phase_4a_plain_text_path_requires_no_schema_resolver"
        ),
        owner="api-owner",
    ),
    ConsumerContractCase(
        area=ConsumerContractArea.DIRECT_MIGRATION,
        name="direct_migration_parity",
        fixture_path="tests/fixtures/contracts/direct_migration/direct_migration.json",
        test_selector=(
            "tests/contracts/test_phase5_operator_readiness.py::"
            "test_phase_5a_direct_migration_delegates_to_canonical_invocation"
        ),
        owner="migration-owner",
    ),
)


def fixtures_by_area(area: FixtureArea) -> tuple[ContractFixture, ...]:
    """Return fixture skeleton entries for one conformance area."""

    return tuple(fixture for fixture in CONTRACT_FIXTURES if fixture.area is area)


def consumer_contract_cases_by_area(
    area: ConsumerContractArea,
) -> tuple[ConsumerContractCase, ...]:
    """Return installable consumer contract cases for one adoption area."""

    return tuple(
        contract_case for contract_case in CONSUMER_CONTRACT_CASES if contract_case.area is area
    )


def build_consumer_contract_pack(
    name: str = "llm-endpoint-consumer-contracts",
) -> ConsumerContractPack:
    """Build the current Zero BC consumer contract pack."""

    return ConsumerContractPack(
        name=name,
        version=CONSUMER_CONTRACT_PACK_VERSION,
        cases=CONSUMER_CONTRACT_CASES,
    )


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


def assert_consumer_contract_pack_complete(
    pack: ConsumerContractPack | None = None,
) -> None:
    """Fail if the installable consumer contract pack lacks any Phase 5D area."""

    contract_pack = pack or build_consumer_contract_pack()
    missing = [
        area.value
        for area in ConsumerContractArea
        if not any(contract_case.area is area for contract_case in contract_pack.cases)
    ]
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"consumer contract pack missing required coverage: {names}")
