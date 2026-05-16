from pathlib import Path

from llm_endpoint.fixtures import (
    CONTRACT_FIXTURES,
    ConsumerContractArea,
    FixtureArea,
    FixturePolarity,
    assert_consumer_contract_pack_complete,
    assert_fixture_manifest_complete,
    build_consumer_contract_pack,
    consumer_contract_cases_by_area,
    fixtures_by_area,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_fixture_manifest_covers_required_areas() -> None:
    assert_fixture_manifest_complete()

    assert {fixture.area for fixture in CONTRACT_FIXTURES} == set(FixtureArea)


def test_fixture_manifest_has_positive_and_negative_coverage() -> None:
    for area in FixtureArea:
        fixtures = fixtures_by_area(area)
        polarities = {fixture.polarity for fixture in fixtures}

        assert FixturePolarity.POSITIVE in polarities
        assert FixturePolarity.NEGATIVE in polarities
        assert all(fixture.path.startswith("tests/fixtures/contracts/") for fixture in fixtures)
        assert all((REPO_ROOT / fixture.path).is_file() for fixture in fixtures)


def test_consumer_contract_pack_covers_phase_5d_areas() -> None:
    pack = build_consumer_contract_pack()

    assert_consumer_contract_pack_complete(pack)
    assert {contract_case.area for contract_case in pack.cases} == set(ConsumerContractArea)
    assert all(
        (REPO_ROOT / contract_case.fixture_path).is_file()
        for contract_case in pack.cases
    )
    assert all(
        contract_case.test_selector.startswith("tests/contracts/")
        for contract_case in pack.cases
    )


def test_consumer_contract_pack_has_area_lookup() -> None:
    cases = consumer_contract_cases_by_area(ConsumerContractArea.DIRECT_MIGRATION)

    assert len(cases) == 1
    assert cases[0].name == "direct_migration_parity"
