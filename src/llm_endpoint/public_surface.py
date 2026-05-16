"""Public surface ownership manifest for the LLM endpoint module."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

PUBLIC_SURFACE_MANIFEST_VERSION = "2026-05-16.phase1"


class CompatibilityLevel(StrEnum):
    """Compatibility classification for exported surfaces."""

    ZERO_BC = "zero_bc"


class SurfaceKind(StrEnum):
    """Kinds of public contract surfaces owned by this package."""

    API = "api"
    CONFIG_SCHEMA = "config_schema"
    FAILURE_TAXONOMY = "failure_taxonomy"
    RESULT_CONTRACT = "result_contract"
    TELEMETRY_SCHEMA = "telemetry_schema"
    VALIDATION_API = "validation_api"
    HOST_CALLBACK = "host_callback"
    PROVIDER_ADAPTER = "provider_adapter"
    FIXTURE_SCHEMA = "fixture_schema"
    MIGRATION_ADAPTER = "migration_adapter"


@dataclass(frozen=True, slots=True)
class PublicSurface:
    """One owned public surface in the package contract."""

    name: str
    kind: SurfaceKind
    owner: str
    version_rule: str
    compatibility_level: CompatibilityLevel = CompatibilityLevel.ZERO_BC
    positive_fixture: str | None = None
    negative_fixture: str | None = None


PUBLIC_SURFACES: tuple[PublicSurface, ...] = (
    PublicSurface(
        name="llm_endpoint.public_surface",
        kind=SurfaceKind.API,
        owner="module-maintainer",
        version_rule="Public manifest changes replace the current pre-V1 contract directly.",
        positive_fixture="tests/contracts/test_public_surface.py::test_manifest_surfaces_are_owned",
        negative_fixture="tests/contracts/test_public_surface.py::test_manifest_uses_zero_bc",
    ),
    PublicSurface(
        name="llm_endpoint.config",
        kind=SurfaceKind.CONFIG_SCHEMA,
        owner="registry-owner",
        version_rule="Only config_schema_version == 'v1' is accepted; no legacy loaders.",
        positive_fixture="tests/contracts/test_config_contract.py::test_valid_config_contract",
        negative_fixture="tests/contracts/test_config_contract.py::test_invalid_config_contract",
    ),
    PublicSurface(
        name="llm_endpoint.results",
        kind=SurfaceKind.RESULT_CONTRACT,
        owner="runtime-owner",
        version_rule="Result and failure meanings are replaced cleanly until V1 release freeze.",
        positive_fixture="tests/contracts/test_results_contract.py::test_success_result_contracts",
        negative_fixture="tests/contracts/test_results_contract.py::test_failure_contract_is_safe",
    ),
    PublicSurface(
        name="llm_endpoint.results.FailureCode",
        kind=SurfaceKind.FAILURE_TAXONOMY,
        owner="runtime-owner",
        version_rule="Failure taxonomy is Zero BC before V1 release freeze.",
        positive_fixture="tests/contracts/test_results_contract.py::test_failure_codes_are_public",
        negative_fixture="tests/contracts/test_results_contract.py::test_failure_contract_is_safe",
    ),
    PublicSurface(
        name="llm_endpoint.telemetry",
        kind=SurfaceKind.TELEMETRY_SCHEMA,
        owner="observability-owner",
        version_rule="Reserved Phase 1D surface; not exported until implemented.",
        positive_fixture=None,
        negative_fixture=None,
    ),
    PublicSurface(
        name="llm_endpoint.callbacks",
        kind=SurfaceKind.HOST_CALLBACK,
        owner="integration-owner",
        version_rule="Reserved Phase 1E surface; not exported until implemented.",
        positive_fixture=None,
        negative_fixture=None,
    ),
    PublicSurface(
        name="llm_endpoint.adapters",
        kind=SurfaceKind.PROVIDER_ADAPTER,
        owner="adapter-owner",
        version_rule="Reserved Phase 1F surface; not exported until implemented.",
        positive_fixture=None,
        negative_fixture=None,
    ),
    PublicSurface(
        name="tests/contracts",
        kind=SurfaceKind.FIXTURE_SCHEMA,
        owner="test-owner",
        version_rule="Fixture layout is replaced cleanly until V1 release freeze.",
        positive_fixture="tests/contracts",
        negative_fixture="tests/contracts",
    ),
    PublicSurface(
        name="llm_endpoint.migration",
        kind=SurfaceKind.MIGRATION_ADAPTER,
        owner="migration-owner",
        version_rule="Reserved Phase 5A surface; no legacy facade is exported in Phase 1.",
        positive_fixture=None,
        negative_fixture=None,
    ),
)

INTERNAL_SURFACE_PREFIXES: tuple[str, ...] = ("llm_endpoint._",)


def public_surface_names() -> frozenset[str]:
    """Return the exported public surface names in the manifest."""

    return frozenset(surface.name for surface in PUBLIC_SURFACES)


def public_surfaces_by_kind(kind: SurfaceKind) -> tuple[PublicSurface, ...]:
    """Return public surfaces matching one manifest kind."""

    return tuple(surface for surface in PUBLIC_SURFACES if surface.kind is kind)


def assert_manifest_complete() -> None:
    """Fail fast if any public surface is missing Phase 1 ownership metadata."""

    missing_metadata = [
        surface.name
        for surface in PUBLIC_SURFACES
        if not surface.owner or not surface.version_rule or not surface.compatibility_level
    ]
    if missing_metadata:
        names = ", ".join(sorted(missing_metadata))
        raise ValueError(f"public surfaces missing ownership metadata: {names}")

