"""Public surface ownership manifest for the LLM endpoint module."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

PUBLIC_SURFACE_MANIFEST_VERSION = "2026-05-16.prd-remediation-p3c"


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
    CAPABILITY_CATALOG = "capability_catalog"
    POLICY_RESOLVER = "policy_resolver"
    HOST_CALLBACK = "host_callback"
    PROVIDER_ADAPTER = "provider_adapter"
    ROUTER = "router"
    STRUCTURED_OUTPUT = "structured_output"
    FIXTURE_SCHEMA = "fixture_schema"
    FAKE_PROVIDER_HARNESS = "fake_provider_harness"
    ROLE_HEALTH = "role_health"
    DEBUG_REPLAY = "debug_replay"
    MIGRATION_READINESS = "migration_readiness"
    ROLLOUT_CONTROLS = "rollout_controls"
    RELEASE_GUARD = "release_guard"


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
        name="llm_endpoint.capabilities",
        kind=SurfaceKind.CAPABILITY_CATALOG,
        owner="adapter-owner",
        version_rule=(
            "Capability catalog v1 is clean-slate; unknown provider/model-family pairs fail closed."
        ),
        positive_fixture="tests/contracts/test_capabilities_contract.py::test_default_catalog_lookup",
        negative_fixture=(
            "tests/contracts/test_capabilities_contract.py::test_unknown_model_family_fails_closed"
        ),
    ),
    PublicSurface(
        name="llm_endpoint.policy",
        kind=SurfaceKind.POLICY_RESOLVER,
        owner="runtime-owner",
        version_rule=(
            "Runtime policy resolver v1 replaces pre-V1 contracts directly; no legacy precedence."
        ),
        positive_fixture="tests/contracts/test_policy_contract.py::test_policy_resolution_contract",
        negative_fixture="tests/contracts/test_policy_contract.py::test_policy_hard_cap_violation",
    ),
    PublicSurface(
        name="llm_endpoint.invocation",
        kind=SurfaceKind.API,
        owner="api-owner",
        version_rule="Invocation facade v1 is direct API only; no compatibility facade.",
        positive_fixture="tests/contracts/test_invocation_contract.py::test_invocation_plan_contract",
        negative_fixture="tests/contracts/test_invocation_contract.py::test_invalid_invocation_returns_typed_failure",
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
        name="llm_endpoint.normalization",
        kind=SurfaceKind.RESULT_CONTRACT,
        owner="runtime-owner",
        version_rule="Provider outcome normalization is Zero BC before V1 release freeze.",
        positive_fixture=(
            "tests/contracts/test_results_contract.py::test_provider_failure_normalization"
        ),
        negative_fixture=(
            "tests/contracts/test_results_contract.py::test_structured_payload_requires_pipeline"
        ),
    ),
    PublicSurface(
        name="llm_endpoint.structured",
        kind=SurfaceKind.STRUCTURED_OUTPUT,
        owner="schema-owner",
        version_rule=(
            "Structured-output pipeline v1 is clean-slate; no legacy parser fallbacks."
        ),
        positive_fixture=(
            "tests/contracts/test_structured_output_contract.py::"
            "test_json_schema_structured_output_validates_and_emits_schema_identity"
        ),
        negative_fixture=(
            "tests/contracts/test_structured_output_contract.py::"
            "test_schema_validation_failure_is_typed_and_non_retryable"
        ),
    ),
    PublicSurface(
        name="llm_endpoint.results.FailureCode",
        kind=SurfaceKind.FAILURE_TAXONOMY,
        owner="runtime-owner",
        version_rule=(
            "Failure taxonomy clean-slate baseline is the PRD llm.* public code set; "
            "old compact codes and aliases are prohibited."
        ),
        positive_fixture="tests/contracts/test_results_contract.py::test_failure_codes_are_public",
        negative_fixture="tests/contracts/test_results_contract.py::test_failure_contract_is_safe",
    ),
    PublicSurface(
        name="llm_endpoint.telemetry",
        kind=SurfaceKind.TELEMETRY_SCHEMA,
        owner="observability-owner",
        version_rule=(
            "Telemetry schema clean-slate baseline includes structured failure schema identity; "
            "legacy failure-event shapes are prohibited."
        ),
        positive_fixture="tests/contracts/test_telemetry_contract.py::test_redacted_event_contract",
        negative_fixture="tests/contracts/test_telemetry_contract.py::test_forbidden_telemetry_fields_fail_closed",
    ),
    PublicSurface(
        name="llm_endpoint.smoke",
        kind=SurfaceKind.VALIDATION_API,
        owner="test-owner",
        version_rule=(
            "Smoke API v1 is clean-slate: offline smoke performs no live calls and "
            "optional live smoke requires explicit host consent."
        ),
        positive_fixture=(
            "tests/contracts/test_phase5_operator_readiness.py::"
            "test_phase_5f_live_smoke_uses_safe_minimal_payload"
        ),
        negative_fixture=(
            "tests/contracts/test_phase5_operator_readiness.py::"
            "test_phase_5f_live_smoke_reports_typed_failed_outcome"
        ),
    ),
    PublicSurface(
        name="llm_endpoint.callbacks",
        kind=SurfaceKind.HOST_CALLBACK,
        owner="integration-owner",
        version_rule=(
            "Host callback contracts are Zero BC before V1; no legacy secret/schema adapters."
        ),
        positive_fixture="tests/contracts/test_callbacks_contract.py::test_secret_resolution_contract_is_redacted",
        negative_fixture="tests/contracts/test_callbacks_contract.py::test_schema_identity_is_required",
    ),
    PublicSurface(
        name="llm_endpoint.adapters",
        kind=SurfaceKind.PROVIDER_ADAPTER,
        owner="adapter-owner",
        version_rule=(
            "Provider adapter contract v1 is clean-slate; raw provider payloads are prohibited."
        ),
        positive_fixture="tests/contracts/test_adapters_contract.py::test_provider_success_contract",
        negative_fixture="tests/contracts/test_adapters_contract.py::test_raw_provider_status_fields_are_rejected",
    ),
    PublicSurface(
        name="llm_endpoint.router",
        kind=SurfaceKind.ROUTER,
        owner="runtime-owner",
        version_rule=(
            "Deadline pool router v1 is clean-slate; no legacy routing or fallback modes."
        ),
        positive_fixture="tests/contracts/test_router_contract.py::test_ordered_retryable_failover",
        negative_fixture="tests/contracts/test_router_contract.py::test_pool_exhaustion_is_typed_failure",
    ),
    PublicSurface(
        name="llm_endpoint.fixtures",
        kind=SurfaceKind.FIXTURE_SCHEMA,
        owner="test-owner",
        version_rule=(
            "Fixture skeletons and consumer contract packs are replaced cleanly before V1; "
            "no deprecated fixture layouts."
        ),
        positive_fixture=(
            "tests/contracts/test_fixture_manifest.py::"
            "test_consumer_contract_pack_covers_phase_5d_areas"
        ),
        negative_fixture="tests/contracts/test_fixture_manifest.py::test_fixture_manifest_has_positive_and_negative_coverage",
    ),
    PublicSurface(
        name="llm_endpoint.fake_provider",
        kind=SurfaceKind.FAKE_PROVIDER_HARNESS,
        owner="test-owner",
        version_rule=(
            "Fake-provider harness v1 is deterministic and clean-slate; no legacy fixture layouts."
        ),
        positive_fixture=(
            "tests/contracts/test_phase4_invocation_hardening.py::"
            "test_phase_4c_fake_provider_harness_covers_required_scenarios"
        ),
        negative_fixture=(
            "tests/contracts/test_phase4_invocation_hardening.py::"
            "test_phase_4c_fake_provider_harness_drives_pool_exhaustion"
        ),
    ),
    PublicSurface(
        name="llm_endpoint.role_health",
        kind=SurfaceKind.ROLE_HEALTH,
        owner="operations-owner",
        version_rule=(
            "Role-health service v1 is direct operator API only; no legacy status mapping."
        ),
        positive_fixture=(
            "tests/contracts/test_phase4_invocation_hardening.py::"
            "test_phase_4d_role_health_reports_available_and_degraded_states"
        ),
        negative_fixture=(
            "tests/contracts/test_phase4_invocation_hardening.py::"
            "test_phase_4d_role_health_reports_unavailable_states"
        ),
    ),
    PublicSurface(
        name="llm_endpoint.debug",
        kind=SurfaceKind.DEBUG_REPLAY,
        owner="observability-owner",
        version_rule=(
            "Debug replay artifact v1 is redacted and replaceable before V1; "
            "no raw payload capture."
        ),
        positive_fixture=(
            "tests/contracts/test_phase4_invocation_hardening.py::"
            "test_phase_4e_debug_replay_artifact_is_redacted_and_reproducible"
        ),
        negative_fixture=(
            "tests/contracts/test_phase4_invocation_hardening.py::"
            "test_phase_4e_debug_replay_rejects_forbidden_fields"
        ),
    ),
    PublicSurface(
        name="llm_endpoint.migration",
        kind=SurfaceKind.MIGRATION_READINESS,
        owner="migration-owner",
        version_rule=(
            "Migration readiness v1 is direct API only; compatibility facades and "
            "legacy provider tuple adapters are prohibited."
        ),
        positive_fixture=(
            "tests/contracts/test_phase5_operator_readiness.py::"
            "test_phase_5a_direct_migration_delegates_to_canonical_invocation"
        ),
        negative_fixture=(
            "tests/contracts/test_phase5_operator_readiness.py::"
            "test_phase_5a_rejects_legacy_nightfall_fields_under_zero_bc"
        ),
    ),
    PublicSurface(
        name="llm_endpoint.rollout",
        kind=SurfaceKind.ROLLOUT_CONTROLS,
        owner="operations-owner",
        version_rule=(
            "Rollout controls v1 operate on current endpoint UIDs and policy fingerprints "
            "only; no legacy rollout gates."
        ),
        positive_fixture=(
            "tests/contracts/test_phase5_operator_readiness.py::"
            "test_phase_5b_rollout_controls_suppress_and_label_canaries"
        ),
        negative_fixture=(
            "tests/contracts/test_phase5_operator_readiness.py::"
            "test_phase_5b_force_candidate_requires_test_mode"
        ),
    ),
    PublicSurface(
        name="llm_endpoint.release_guard",
        kind=SurfaceKind.RELEASE_GUARD,
        owner="module-maintainer",
        version_rule=(
            "Compatibility checker enforces Zero BC release evidence and rejects "
            "non-Zero-BC public surfaces."
        ),
        positive_fixture=(
            "tests/contracts/test_phase5_operator_readiness.py::"
            "test_phase_5c_release_guard_accepts_documented_zero_bc_surface_diff"
        ),
        negative_fixture=(
            "tests/contracts/test_phase5_operator_readiness.py::"
            "test_phase_5c_release_guard_requires_changelog_and_migration_notes"
        ),
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
