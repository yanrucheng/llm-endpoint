from llm_endpoint.public_surface import (
    PUBLIC_SURFACES,
    CompatibilityLevel,
    SurfaceKind,
    assert_manifest_complete,
    public_surface_names,
    public_surfaces_by_kind,
)


def test_manifest_surfaces_are_owned() -> None:
    assert_manifest_complete()

    names = public_surface_names()

    assert "llm_endpoint.public_surface" in names
    assert "llm_endpoint.config" in names
    assert "llm_endpoint.results" in names
    assert "llm_endpoint.results.FailureCode" in names
    assert "llm_endpoint.telemetry" in names
    assert "llm_endpoint.callbacks" in names
    assert "llm_endpoint.adapters" in names
    assert "llm_endpoint.fixtures" in names


def test_manifest_uses_zero_bc() -> None:
    assert {surface.compatibility_level for surface in PUBLIC_SURFACES} == {
        CompatibilityLevel.ZERO_BC
    }

    config_surfaces = public_surfaces_by_kind(SurfaceKind.CONFIG_SCHEMA)

    assert len(config_surfaces) == 1
    assert "no legacy loaders" in config_surfaces[0].version_rule


def test_phase_1_d_to_g_surfaces_have_fixtures() -> None:
    names = {
        "llm_endpoint.telemetry",
        "llm_endpoint.callbacks",
        "llm_endpoint.adapters",
        "llm_endpoint.fixtures",
    }
    surfaces = {surface.name: surface for surface in PUBLIC_SURFACES if surface.name in names}

    assert set(surfaces) == names
    assert all(surface.positive_fixture for surface in surfaces.values())
    assert all(surface.negative_fixture for surface in surfaces.values())
