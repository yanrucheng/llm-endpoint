from llm_endpoint.config import (
    EndpointConfig,
    EndpointPool,
    LLMEndpointConfig,
    OperationConfig,
    OperationRuntimePolicy,
    ProviderFormat,
    RetryPolicy,
    RoleConfig,
    StructuredOutputMode,
)
from llm_endpoint.results import FailureCode
from llm_endpoint.smoke import OfflineSmokeReport, SmokeCheckName, run_offline_smoke
from llm_endpoint.telemetry import TelemetryEventFamily


def test_offline_smoke_report_contract() -> None:
    report = run_offline_smoke(config=_config(), role="writer", operation_ref="draft")

    assert isinstance(report, OfflineSmokeReport)
    assert report.ok is True
    assert report.config_identity is not None
    assert report.plan is not None
    assert report.failure is None
    assert {check.name for check in report.checks} == {
        SmokeCheckName.CONFIG_VALIDATION,
        SmokeCheckName.REGISTRY_BUILD,
        SmokeCheckName.INVOCATION_PLANNING,
        SmokeCheckName.CANDIDATE_BUDGET_SIMULATION,
        SmokeCheckName.TELEMETRY_REDACTION,
    }
    assert report.events[-1].family is TelemetryEventFamily.SMOKE_RESULT
    assert report.events[-1].attributes["ok"] == "true"


def test_offline_smoke_invalid_config_fails_closed() -> None:
    report = run_offline_smoke(
        config=_config(credential_ref=""),
        role="writer",
        operation_ref="draft",
    )

    assert report.ok is False
    assert report.config_identity is None
    assert report.plan is None
    assert len(report.checks) == 1
    assert report.checks[0].name is SmokeCheckName.CONFIG_VALIDATION
    assert report.events[-1].family is TelemetryEventFamily.SMOKE_RESULT
    assert report.events[-1].attributes["ok"] == "false"


def test_offline_smoke_stale_candidate_budget_override_fails_closed() -> None:
    report = run_offline_smoke(
        config=_config(candidate_budget_overrides_ms={"stale": 6_000}),
        role="writer",
        operation_ref="draft",
    )

    assert report.ok is False
    assert report.plan is None
    assert report.failure is not None
    assert report.failure.code is FailureCode.CANDIDATE_BUDGET_UNALLOCATABLE
    assert [check.name for check in report.checks] == [
        SmokeCheckName.CONFIG_VALIDATION,
        SmokeCheckName.REGISTRY_BUILD,
        SmokeCheckName.INVOCATION_PLANNING,
    ]
    assert (
        report.checks[-1].message
        == FailureCode.CANDIDATE_BUDGET_UNALLOCATABLE.value
    )
    assert "stale" in report.failure.diagnostics.message
    assert report.events[-1].family is TelemetryEventFamily.SMOKE_RESULT
    assert report.events[-1].attributes["ok"] == "false"


def test_offline_smoke_simulates_per_uid_candidate_budgets() -> None:
    report = run_offline_smoke(
        config=_config(
            fallback_credential_ref="secret://fake-fallback",
            candidate_budget_overrides_ms={"primary": 6_000},
        ),
        role="writer",
        operation_ref="draft",
    )

    assert report.ok is True
    assert report.plan is not None
    assert report.plan.endpoint_uids == ("primary", "fallback")
    assert report.plan.effective_config.candidate_budget_overrides_ms == (
        ("primary", 6_000),
    )
    budget_check = next(
        check
        for check in report.checks
        if check.name is SmokeCheckName.CANDIDATE_BUDGET_SIMULATION
    )
    assert budget_check.ok is True
    assert budget_check.message.endswith(
        "primary=6000:override,fallback=4000:base"
    )


def _config(
    credential_ref: str = "secret://fake-primary",
    *,
    fallback_credential_ref: str | None = None,
    candidate_budget_overrides_ms: dict[str, int] | None = None,
) -> LLMEndpointConfig:
    endpoints = (
        EndpointConfig(
            uid="primary",
            provider_format=ProviderFormat.FAKE,
            model_family="fake-family",
            model="fake-model",
            credential_ref=credential_ref,
        ),
    )
    roles = (RoleConfig(name="writer", endpoint_uid="primary"),)
    retry_policy = RetryPolicy()
    if fallback_credential_ref is not None:
        endpoints = (
            endpoints[0],
            EndpointConfig(
                uid="fallback",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-model",
                credential_ref=fallback_credential_ref,
            ),
        )
        roles = (
            RoleConfig(name="writer", pool=EndpointPool(("primary", "fallback"))),
        )
        retry_policy = RetryPolicy(max_attempts=2)
    return LLMEndpointConfig(
        endpoints=endpoints,
        roles=roles,
        operations=(
            OperationConfig(
                ref="draft",
                policy_ref="draft-policy",
                schema_contract_ref="schema://draft/v1",
            ),
        ),
        policies=(
            OperationRuntimePolicy(
                ref="draft-policy",
                deadline_ms=10_000,
                max_output_tokens=1_024,
                candidate_budget_ms=4_000,
                candidate_budget_overrides_ms=candidate_budget_overrides_ms,
                protect_last_eligible=True,
                structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
                retry_policy=retry_policy,
            ),
        ),
    )
