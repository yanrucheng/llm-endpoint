"""Operator rollout controls for endpoint candidates and policy fingerprints."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from llm_endpoint.invocation import InvocationPlan
from llm_endpoint.results import FailureCode, TypedFailure, failure

ROLLOUT_CONTROLS_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class RolloutControls:
    """Host-owned rollout policy applied after invocation planning."""

    disabled_endpoint_uids: frozenset[str] = frozenset()
    forced_endpoint_uid: str | None = None
    test_mode: bool = False
    canary_roles: frozenset[str] = frozenset()
    canary_operations: frozenset[str] = frozenset()
    expected_policy_fingerprints: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RolloutDecision:
    """Effective rollout decision safe to pass to routing and operator logs."""

    plan: InvocationPlan
    suppressed_endpoint_reasons: Mapping[str, str]
    canary_id: str | None
    policy_fingerprint_matches: bool | None
    rollout_version: str = ROLLOUT_CONTROLS_VERSION

    def __post_init__(self) -> None:
        if self.rollout_version != ROLLOUT_CONTROLS_VERSION:
            raise ValueError("only rollout controls version 'v1' is supported")


def apply_rollout_controls(
    *,
    plan: InvocationPlan,
    controls: RolloutControls,
) -> RolloutDecision | TypedFailure:
    """Apply UID controls, optional test forcing, canary labels, and fingerprint checks."""

    forced_failure = _validate_forced_endpoint(plan, controls)
    if forced_failure is not None:
        return forced_failure

    effective_plan = plan
    if controls.forced_endpoint_uid is not None:
        effective_plan = replace(plan, endpoint_uids=(controls.forced_endpoint_uid,))

    suppressed = {
        endpoint_uid: "rollout_disabled"
        for endpoint_uid in effective_plan.endpoint_uids
        if endpoint_uid in controls.disabled_endpoint_uids
    }
    if len(suppressed) == len(effective_plan.endpoint_uids):
        return failure(
            code=FailureCode.NO_ELIGIBLE_ENDPOINT,
            message="rollout controls disabled every candidate endpoint",
            operation_invocation_id=plan.operation_invocation_id,
            role=plan.role,
            operation_ref=plan.operation_ref,
            policy_fingerprint=plan.policy_fingerprint,
            safe_context={"disabled_endpoint_count": str(len(suppressed))},
        )

    return RolloutDecision(
        plan=effective_plan,
        suppressed_endpoint_reasons=suppressed,
        canary_id=_canary_id(effective_plan, controls),
        policy_fingerprint_matches=_policy_fingerprint_matches(effective_plan, controls),
    )


def policy_fingerprint_key(role: str, operation_ref: str) -> str:
    """Return the stable rollout lookup key for role/operation policy fingerprints."""

    return f"{role}:{operation_ref}"


def _validate_forced_endpoint(
    plan: InvocationPlan,
    controls: RolloutControls,
) -> TypedFailure | None:
    forced = controls.forced_endpoint_uid
    if forced is None:
        return None

    if not controls.test_mode:
        return failure(
            code=FailureCode.INVALID_INVOCATION,
            message="forced endpoint selection is allowed only in test mode",
            operation_invocation_id=plan.operation_invocation_id,
            role=plan.role,
            operation_ref=plan.operation_ref,
            policy_fingerprint=plan.policy_fingerprint,
        )
    if forced not in plan.endpoint_uids:
        return failure(
            code=FailureCode.NO_ELIGIBLE_ENDPOINT,
            message="forced endpoint is not in the planned candidate pool",
            operation_invocation_id=plan.operation_invocation_id,
            role=plan.role,
            operation_ref=plan.operation_ref,
            policy_fingerprint=plan.policy_fingerprint,
            safe_context={"forced_endpoint_present": "false"},
        )
    return None


def _canary_id(plan: InvocationPlan, controls: RolloutControls) -> str | None:
    role_matches = not controls.canary_roles or plan.role in controls.canary_roles
    operation_matches = (
        not controls.canary_operations or plan.operation_ref in controls.canary_operations
    )
    if not role_matches or not operation_matches:
        return None
    return policy_fingerprint_key(plan.role, plan.operation_ref)


def _policy_fingerprint_matches(
    plan: InvocationPlan,
    controls: RolloutControls,
) -> bool | None:
    expected = controls.expected_policy_fingerprints.get(
        policy_fingerprint_key(plan.role, plan.operation_ref)
    )
    if expected is None:
        return None
    return expected == plan.policy_fingerprint
