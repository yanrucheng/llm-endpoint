"""Redacted debug replay artifacts for deterministic offline reproduction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from llm_endpoint.capabilities import DEFAULT_CAPABILITY_CATALOG, CapabilityCatalog
from llm_endpoint.config import Registry
from llm_endpoint.fake_provider import FakeProviderScenario
from llm_endpoint.invocation import InvocationPlan
from llm_endpoint.results import TerminalResult, TypedFailure
from llm_endpoint.router import PoolRouteResult
from llm_endpoint.telemetry import forbidden_attribute_keys

DEBUG_REPLAY_ARTIFACT_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class DebugReplayArtifact:
    """Redacted replay bundle safe to persist in logs or support tickets."""

    operation_invocation_id: str
    endpoint_plan: tuple[Mapping[str, str], ...]
    policy_provenance: Mapping[str, str]
    capability_profiles: tuple[Mapping[str, str], ...]
    schema_trace: Mapping[str, str]
    attempt_trace: tuple[Mapping[str, str], ...]
    typed_failure: Mapping[str, str] | None
    fake_provider_reproduction: Mapping[str, str]
    artifact_version: str = DEBUG_REPLAY_ARTIFACT_VERSION

    def __post_init__(self) -> None:
        if self.artifact_version != DEBUG_REPLAY_ARTIFACT_VERSION:
            raise ValueError("only debug replay artifact version 'v1' is supported")
        for section in self._sections():
            unsafe = forbidden_attribute_keys(section)
            if unsafe:
                names = ", ".join(sorted(unsafe))
                raise ValueError(f"debug replay artifact contains forbidden fields: {names}")

    def _sections(self) -> tuple[Mapping[str, str], ...]:
        sections: list[Mapping[str, str]] = [
            self.policy_provenance,
            self.schema_trace,
            self.fake_provider_reproduction,
        ]
        sections.extend(self.endpoint_plan)
        sections.extend(self.capability_profiles)
        sections.extend(self.attempt_trace)
        if self.typed_failure is not None:
            sections.append(self.typed_failure)
        return tuple(sections)


def build_debug_replay_artifact(
    *,
    plan: InvocationPlan,
    registry: Registry,
    route_result: PoolRouteResult,
    capability_catalog: CapabilityCatalog = DEFAULT_CAPABILITY_CATALOG,
    schema_trace: Mapping[str, str] | None = None,
    fake_provider_scenario: FakeProviderScenario | str | None = None,
) -> DebugReplayArtifact:
    """Build a redacted replay artifact from public route outputs only."""

    return DebugReplayArtifact(
        operation_invocation_id=plan.operation_invocation_id,
        endpoint_plan=_endpoint_plan(plan, registry),
        policy_provenance=_policy_provenance(plan),
        capability_profiles=_capability_profiles(plan, registry, capability_catalog),
        schema_trace=_schema_trace(plan, schema_trace),
        attempt_trace=tuple(
            {
                "trace_id": trace.trace_id,
                "endpoint_uid": trace.endpoint_uid,
                "status": trace.status.value,
                "candidate_budget_ms": str(trace.candidate_budget_ms or ""),
                "elapsed_ms": str(trace.elapsed_ms or ""),
                "failure_code": trace.failure_code.value if trace.failure_code else "",
                "skip_reason": trace.skip_reason or "",
                "suppression_protected": str(trace.suppression_protected).lower(),
            }
            for trace in route_result.attempt_traces
        ),
        typed_failure=_typed_failure(route_result.terminal_result),
        fake_provider_reproduction=_fake_provider_reproduction(plan, fake_provider_scenario),
    )


def _endpoint_plan(
    plan: InvocationPlan,
    registry: Registry,
) -> tuple[Mapping[str, str], ...]:
    return tuple(
        {
            "endpoint_uid": endpoint.uid,
            "provider_format": endpoint.provider_format.value,
            "model_family": endpoint.model_family,
            "credential_ref_present": str(bool(endpoint.credential_ref)).lower(),
            "candidate_index": str(index),
        }
        for index, endpoint in enumerate(
            registry.endpoints_by_uid[endpoint_uid] for endpoint_uid in plan.endpoint_uids
        )
    )


def _policy_provenance(plan: InvocationPlan) -> Mapping[str, str]:
    config = plan.effective_config
    return {
        "role": plan.role,
        "operation_ref": plan.operation_ref,
        "config_identity": plan.config_identity,
        "policy_fingerprint": plan.policy_fingerprint,
        "deadline_ms": str(plan.deadline_ms),
        "candidate_budget_ms": str(config.candidate_budget_ms),
        "max_attempts": str(config.max_attempts),
        "structured_output_mode": config.structured_output_mode.value,
    }


def _capability_profiles(
    plan: InvocationPlan,
    registry: Registry,
    capability_catalog: CapabilityCatalog,
) -> tuple[Mapping[str, str], ...]:
    profiles: list[Mapping[str, str]] = []
    for endpoint_uid in plan.endpoint_uids:
        endpoint = registry.endpoints_by_uid[endpoint_uid]
        profile = capability_catalog.get(endpoint.provider_format, endpoint.model_family)
        profiles.append(
            {
                "endpoint_uid": endpoint_uid,
                "provider_format": endpoint.provider_format.value,
                "model_family": endpoint.model_family,
                "profile_found": str(profile is not None).lower(),
                "catalog_version": capability_catalog.version,
                "max_output_tokens": (
                    str(profile.hard_limits.max_output_tokens) if profile is not None else ""
                ),
            }
        )
    return tuple(profiles)


def _schema_trace(
    plan: InvocationPlan,
    schema_trace: Mapping[str, str] | None,
) -> Mapping[str, str]:
    clean_trace = dict(schema_trace or {})
    return {
        "schema_contract_ref_present": str(bool(plan.schema_contract_ref)).lower(),
        "schema_contract_ref": plan.schema_contract_ref or "",
        **clean_trace,
    }


def _typed_failure(terminal: TerminalResult) -> Mapping[str, str] | None:
    if not isinstance(terminal, TypedFailure):
        return None
    return {
        "failure_code": terminal.code.value,
        "failure_class": terminal.failure_class.value if terminal.failure_class else "",
        "retryability": terminal.retryability.value if terminal.retryability else "",
        "endpoint_uid": terminal.context.endpoint_uid or "",
        "attempt_trace_id": (
            terminal.context.attempt_trace.trace_id if terminal.context.attempt_trace else ""
        ),
        "safe_context_keys": ",".join(sorted(terminal.diagnostics.safe_context)),
    }


def _fake_provider_reproduction(
    plan: InvocationPlan,
    scenario: FakeProviderScenario | str | None,
) -> Mapping[str, str]:
    scenario_value = (
        scenario.value if isinstance(scenario, FakeProviderScenario) else scenario or ""
    )
    return {
        "adapter": "fake",
        "scenario": scenario_value,
        "operation_invocation_id": plan.operation_invocation_id,
        "message_count": str(len(plan.messages)),
    }
