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


def test_manifest_uses_zero_bc() -> None:
    assert {surface.compatibility_level for surface in PUBLIC_SURFACES} == {
        CompatibilityLevel.ZERO_BC
    }

    config_surfaces = public_surfaces_by_kind(SurfaceKind.CONFIG_SCHEMA)

    assert len(config_surfaces) == 1
    assert "no legacy loaders" in config_surfaces[0].version_rule

