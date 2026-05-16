from llm_endpoint.adapters import ProviderOutcomeKind, provider_failure, provider_success
from llm_endpoint.config import (
    EndpointConfig,
    EndpointPool,
    LLMEndpointConfig,
    OperationConfig,
    OperationRuntimePolicy,
    ProviderFormat,
    RoleConfig,
    StructuredOutputMode,
)
from llm_endpoint.invocation import InvocationPlan, InvocationRequest, invoke_plan
from llm_endpoint.migration import DirectMigrationRequest, assess_direct_migration
from llm_endpoint.public_surface import PUBLIC_SURFACES
from llm_endpoint.release_guard import (
    CompatibilityIssueCode,
    PublicSurfaceSnapshot,
    capture_public_surface_baseline,
    check_public_surface_release,
)
from llm_endpoint.results import FailureCode, TypedFailure
from llm_endpoint.rollout import (
    RolloutControls,
    RolloutDecision,
    apply_rollout_controls,
    policy_fingerprint_key,
)
from llm_endpoint.smoke import (
    LIVE_SMOKE_SAFE_PROMPT,
    LiveSmokeReport,
    LiveSmokeStatus,
    run_optional_live_smoke,
)


def test_phase_5a_direct_migration_delegates_to_canonical_invocation() -> None:
    report = assess_direct_migration(
        migration_request=DirectMigrationRequest(
            request=_request("inv-p5a"),
            source_callsite="nightfall.writer.draft",
        ),
        config=_config(),
    )

    assert report.ok is True
    assert report.plan is not None
    assert report.plan.operation_invocation_id == "inv-p5a"
    assert report.diagnostics == ("canonical_direct_api_ready", "no_compatibility_facade")


def test_phase_5a_rejects_legacy_nightfall_fields_under_zero_bc() -> None:
    report = assess_direct_migration(
        migration_request=DirectMigrationRequest(
            request=_request("inv-p5a-legacy"),
            source_callsite="nightfall.writer.legacy",
            legacy_fields={"provider": "openai", "model": "legacy-model"},
        ),
        config=_config(),
    )

    assert report.ok is False
    assert isinstance(report.failure, TypedFailure)
    assert report.failure.code is FailureCode.UNSUPPORTED_RUNTIME_KNOB
    assert report.failure.code.value == "llm.endpoint.unsupported_runtime_knob"
    assert report.failure.diagnostics.safe_context["legacy_field_count"] == "2"


def test_phase_5b_rollout_controls_suppress_and_label_canaries() -> None:
    plan = _plan("inv-p5b")
    controls = RolloutControls(
        disabled_endpoint_uids=frozenset({"primary"}),
        canary_roles=frozenset({"writer"}),
        canary_operations=frozenset({"draft"}),
        expected_policy_fingerprints={
            policy_fingerprint_key("writer", "draft"): plan.policy_fingerprint
        },
    )

    decision = apply_rollout_controls(plan=plan, controls=controls)

    assert isinstance(decision, RolloutDecision)
    assert decision.plan.endpoint_uids == ("primary", "fallback")
    assert decision.suppressed_endpoint_reasons == {"primary": "rollout_disabled"}
    assert decision.canary_id == "writer:draft"
    assert decision.policy_fingerprint_matches is True


def test_phase_5b_force_candidate_requires_test_mode() -> None:
    plan = _plan("inv-p5b-force")

    result = apply_rollout_controls(
        plan=plan,
        controls=RolloutControls(forced_endpoint_uid="fallback"),
    )

    assert isinstance(result, TypedFailure)
    assert result.code is FailureCode.UNSUPPORTED_RUNTIME_KNOB
    assert result.code.value == "llm.endpoint.unsupported_runtime_knob"


def test_phase_5b_force_candidate_rewrites_plan_in_test_mode() -> None:
    plan = _plan("inv-p5b-test-force")

    decision = apply_rollout_controls(
        plan=plan,
        controls=RolloutControls(forced_endpoint_uid="fallback", test_mode=True),
    )

    assert isinstance(decision, RolloutDecision)
    assert decision.plan.endpoint_uids == ("fallback",)


def test_phase_5c_release_guard_accepts_documented_zero_bc_surface_diff() -> None:
    current = PUBLIC_SURFACES
    baseline = tuple(
        surface
        for surface in capture_public_surface_baseline(current)
        if surface.name != "llm_endpoint.release_guard"
    )

    report = check_public_surface_release(
        current_surfaces=current,
        baseline=baseline,
        changelog_entries=("public surface: add compatibility checker",),
        migration_notes=("zero bc: consumers use the current checker directly",),
        package_version="0.1.0",
    )

    assert report.ok is True
    assert report.issues == ()


def test_phase_5c_release_guard_requires_changelog_and_migration_notes() -> None:
    baseline = tuple(
        surface
        for surface in capture_public_surface_baseline(PUBLIC_SURFACES)
        if surface.name != "llm_endpoint.rollout"
    )

    report = check_public_surface_release(
        current_surfaces=PUBLIC_SURFACES,
        baseline=baseline,
        package_version="0.1.0",
    )
    codes = {issue.code for issue in report.issues}

    assert report.ok is False
    assert CompatibilityIssueCode.PUBLIC_SURFACE_ADDED in codes
    assert CompatibilityIssueCode.MISSING_CHANGELOG in codes
    assert CompatibilityIssueCode.MISSING_MIGRATION_NOTE in codes


def test_phase_5c_release_guard_requires_clean_slate_remediation_evidence() -> None:
    baseline = _pre_remediation_baseline()

    report = check_public_surface_release(
        current_surfaces=PUBLIC_SURFACES,
        baseline=baseline,
        changelog_entries=("public surface: replace result and telemetry contracts",),
        migration_notes=("zero bc: consumers adopt current contracts directly",),
        package_version="0.1.0",
    )
    codes = {issue.code for issue in report.issues}

    assert report.ok is False
    assert CompatibilityIssueCode.PUBLIC_SURFACE_CHANGED in codes
    assert CompatibilityIssueCode.MISSING_CLEAN_SLATE_BASELINE_EVIDENCE in codes


def test_phase_5c_release_guard_accepts_prd_remediation_clean_slate_baseline() -> None:
    baseline = _pre_remediation_baseline()

    report = check_public_surface_release(
        current_surfaces=PUBLIC_SURFACES,
        baseline=baseline,
        changelog_entries=(
            "public surface: failure taxonomy and telemetry schema are the "
            "PRD remediation clean-slate baseline",
        ),
        migration_notes=(
            "zero bc: no aliases; consumers adopt the clean-slate baseline for "
            "failure taxonomy and telemetry schema",
        ),
        package_version="0.1.0",
    )

    assert report.ok is True
    assert report.issues == ()


def test_phase_5f_live_smoke_skips_without_explicit_consent() -> None:
    report = run_optional_live_smoke(
        config=_config(),
        role="writer",
        operation_ref="draft",
        explicit_consent=False,
    )

    assert isinstance(report, LiveSmokeReport)
    assert report.ok is True
    assert report.status is LiveSmokeStatus.SKIPPED
    assert report.reason == "explicit_consent_required"
    assert report.events[-1].attributes["status"] == "skipped"


def test_phase_5f_live_smoke_uses_safe_minimal_payload() -> None:
    seen_messages: list[object] = []

    def probe(plan: InvocationPlan):
        seen_messages.extend(plan.messages)
        return provider_success(endpoint_uid="primary", elapsed_ms=20, content="OK")

    report = run_optional_live_smoke(
        config=_config(),
        role="writer",
        operation_ref="draft",
        explicit_consent=True,
        provider_probe=probe,
    )

    assert report.ok is True
    assert report.status is LiveSmokeStatus.PASSED
    assert seen_messages == [{"role": "user", "content": LIVE_SMOKE_SAFE_PROMPT}]
    assert report.events[-1].attributes["status"] == "passed"


def test_phase_5f_live_smoke_reports_typed_failed_outcome() -> None:
    def probe(_plan: InvocationPlan):
        return provider_failure(
            kind=ProviderOutcomeKind.NON_RETRYABLE_FAILURE,
            endpoint_uid="primary",
            elapsed_ms=20,
            failure_code=FailureCode.PROVIDER_FAILURE,
            safe_provider_status={"provider": "synthetic_failure"},
        )

    report = run_optional_live_smoke(
        config=_config(),
        role="writer",
        operation_ref="draft",
        explicit_consent=True,
        provider_probe=probe,
    )

    assert report.ok is False
    assert report.status is LiveSmokeStatus.FAILED
    assert isinstance(report.failure, TypedFailure)
    assert report.failure.code is FailureCode.PROVIDER_FAILURE
    assert report.events[-1].attributes["reason"] == "llm.invocation.provider_failure"


def _request(operation_invocation_id: str) -> InvocationRequest:
    return InvocationRequest(
        role="writer",
        operation_ref="draft",
        messages=({"role": "user", "content": "draft this"},),
        deadline_ms=10_000,
        operation_invocation_id=operation_invocation_id,
    )


def _plan(operation_invocation_id: str) -> InvocationPlan:
    result = invoke_plan(request=_request(operation_invocation_id), config=_config())

    assert isinstance(result, InvocationPlan)
    return result


def _pre_remediation_baseline() -> tuple[PublicSurfaceSnapshot, ...]:
    replacements = {
        "llm_endpoint.results.FailureCode": (
            "Failure taxonomy is Zero BC before V1 release freeze."
        ),
        "llm_endpoint.telemetry": (
            "Telemetry schema v1 replaces pre-V1 contracts directly; no legacy event routers."
        ),
    }
    return tuple(
        PublicSurfaceSnapshot(
            name=surface.name,
            kind=surface.kind,
            owner=surface.owner,
            version_rule=replacements.get(surface.name, surface.version_rule),
            compatibility_level=surface.compatibility_level,
        )
        for surface in capture_public_surface_baseline(PUBLIC_SURFACES)
    )


def _config(schema_ref: str | None = "schema://draft/v1") -> LLMEndpointConfig:
    return LLMEndpointConfig(
        endpoints=(
            EndpointConfig(
                uid="primary",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-model",
                credential_ref="secret://fake-primary",
                capability_refs=("cap.fake.structured",),
            ),
            EndpointConfig(
                uid="fallback",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-model",
                credential_ref="secret://fake-fallback",
            ),
        ),
        roles=(RoleConfig(name="writer", pool=EndpointPool(("primary", "fallback"))),),
        operations=(
            OperationConfig(ref="draft", policy_ref="draft-policy", schema_contract_ref=schema_ref),
        ),
        policies=(
            OperationRuntimePolicy(
                ref="draft-policy",
                deadline_ms=10_000,
                max_output_tokens=1_024,
                candidate_budget_ms=4_000,
                failover_reserve_ms=1_000,
                structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
            ),
        ),
    )
