from llm_endpoint.config import (
    EndpointConfig,
    LLMEndpointConfig,
    OperationConfig,
    OperationRuntimePolicy,
    ProviderFormat,
    RoleConfig,
    StructuredOutputMode,
)
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


def _config(credential_ref: str = "secret://fake-primary") -> LLMEndpointConfig:
    return LLMEndpointConfig(
        endpoints=(
            EndpointConfig(
                uid="primary",
                provider_format=ProviderFormat.FAKE,
                model_family="fake-family",
                model="fake-model",
                credential_ref=credential_ref,
            ),
        ),
        roles=(RoleConfig(name="writer", endpoint_uid="primary"),),
        operations=(
            OperationConfig(ref="draft", policy_ref="draft-policy", schema_contract_ref="schema://draft/v1"),
        ),
        policies=(
            OperationRuntimePolicy(
                ref="draft-policy",
                deadline_ms=10_000,
                max_output_tokens=1_024,
                candidate_budget_ms=4_000,
                protect_last_eligible=True,
                structured_output_mode=StructuredOutputMode.JSON_SCHEMA,
            ),
        ),
    )
