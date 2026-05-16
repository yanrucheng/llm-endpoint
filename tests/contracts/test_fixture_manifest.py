from pathlib import Path

from llm_endpoint.fixtures import (
    CONTRACT_FIXTURES,
    FixtureArea,
    FixturePolarity,
    assert_fixture_manifest_complete,
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
