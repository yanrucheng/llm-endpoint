---
id: "design-260517-0941-per-uid-candidate-budget"
title: "Per-UID Candidate Budget Overrides And README Contract Hardening"
type: design
status: draft
created: 2026-05-17
updated: 2026-05-17
parent: "prd-260516-1321-llm-endpoint-module"
depends-on:
  - "design-260516-1331-llm-endpoint-module"
superseded-by: ""
author: "agent"
tags: ["candidate-budget", "per-uid", "policy", "router", "telemetry-docs", "readme", "reasoning-mode"]
source: "/Users/chengyanru/repos/venture/lg/nightfall-ai/eval/sessions/260517-0941-llm-endpoint-expectation-mismatch/report.md"
---

# Per-UID Candidate Budget Overrides And README Contract Hardening

## Context

The first external adoption review (Nightfall `260517-0941-llm-endpoint-expectation-mismatch`) identified three gaps between the module's PRD commitments and what the implementation and README currently expose:

1. **Per-UID candidate budgets (M8):** The PRD (Section 3 row "per-family or per-UID budget", Design Decisions row "candidate budget shape supports uniform, per-family, and per-UID allocation") commits to asymmetric candidate budgets. The implementation only has a flat `candidate_budget_ms`. Real pools have asymmetric latency profiles (e.g., a reasoning model at 12s TTFT vs. a fast model at 2s), so uniform allocation is suboptimal and forces consumers into host-side workarounds.

2. **Telemetry event name documentation (M12):** The code defines 14 stable `TelemetryEventFamily` names and the PRD lists them. The README says "redacted telemetry events" without naming them. Consumers cannot wire dashboards without reading source code.

3. **Reasoning mode README visibility (M7):** `ReasoningMode` (DISABLED/LOW/MEDIUM/HIGH) is already implemented, validated, and provenance-tracked. The README quick-start policy example omits it, leading consumers to believe it does not exist.

Items 2 and 3 are documentation-only. Item 1 is a feature requiring schema, policy, router, validation, and test changes.

This design covers Item 1 in detail and specifies the scope of Items 2 and 3.

## Goals

| ID | Goal |
|---|---|
| D1 | Add `candidate_budget_overrides_ms` to `OperationRuntimePolicy` as a provider-blind, UID-keyed override map |
| D2 | Propagate per-UID budget through policy resolution, effective runtime config, provenance, and validation |
| D3 | Update the router to apply per-UID candidate budgets instead of uniform allocation when overrides are present |
| D4 | Document telemetry event families in the README with stable names |
| D5 | Demonstrate `reasoning_mode` in the README quick-start policy example |

## Non-Goals

| Non-goal | Rationale |
|---|---|
| Per-family budget keying | Provider taxonomy ("gemini", "openai_gpt") in the policy contract leaks provider identity into business-agnostic config. Hosts can derive per-UID overrides from their own family knowledge. |
| Adaptive or learned candidate budgets | Deterministic behavior is a V1 principle. Adaptive budgets belong to a future design. |
| Reasoning fallback mode | If an endpoint doesn't support the requested reasoning mode, the current fail-closed behavior is correct. Adding a fallback mode would violate deterministic routing. |
| CallerPolicyOverrides for per-UID budgets | Caller overrides are request-scoped ergonomics; per-UID budgets are operator topology knowledge that belongs in config. |

## Design

### 1. Schema Change: `OperationRuntimePolicy`

Add one optional field:

```python
@dataclass(frozen=True, slots=True)
class OperationRuntimePolicy:
    ref: str
    deadline_ms: int
    max_output_tokens: int
    reasoning_mode: ReasoningMode = ReasoningMode.DISABLED
    candidate_budget_ms: int | None = None
    candidate_budget_overrides_ms: Mapping[str, int] | None = None  # NEW: keyed by endpoint UID
    protect_last_eligible: bool = False
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.NONE
    allow_caller_overrides: bool = False
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
```

Semantics:

- `candidate_budget_overrides_ms` is `None` by default (no overrides; uniform behavior).
- When present, it is a `Mapping[str, int]` keyed by endpoint UID. UIDs not present in the map fall back to the base `candidate_budget_ms`.
- All values in the map must be positive integers.
- Override values are subject to the same hard-limit validation as `candidate_budget_ms`.
- The field is config-level only; it is NOT available through `CallerPolicyOverrides`.

### 2. Policy Resolution Changes

#### `EffectiveRuntimeConfig`

Add a new field:

```python
@dataclass(frozen=True, slots=True)
class EffectiveRuntimeConfig:
    deadline_ms: int
    max_output_tokens: int
    reasoning_mode: ReasoningMode
    candidate_budget_ms: int
    candidate_budget_overrides_ms: tuple[tuple[str, int], ...] | None  # NEW: frozen representation
    protect_last_eligible: bool
    structured_output_mode: StructuredOutputMode
    retry_class: str
    max_attempts: int
```

The `Mapping` is frozen into a sorted tuple-of-tuples for immutability. This preserves the `frozen=True` invariant.

#### `_effective_config`

```python
def _effective_config(policy, overrides):
    # ... existing logic ...
    raw_overrides = policy.candidate_budget_overrides_ms
    frozen_overrides = (
        tuple(sorted(raw_overrides.items()))
        if raw_overrides
        else None
    )
    return EffectiveRuntimeConfig(
        # ... existing fields ...
        candidate_budget_overrides_ms=frozen_overrides,
    )
```

#### `_provenance`

Add provenance entry:

```python
"candidate_budget_overrides_ms": PolicySource.POLICY if policy.candidate_budget_overrides_ms else PolicySource.NOT_SET,
```

Introduce `PolicySource.NOT_SET` or use the existing derivation pattern. If the field is None, provenance indicates "not set" rather than "derived."

#### `_validate_effective_config`

Extend validation:

- Each override value must be > 0.
- Each override value must not exceed `deadline_ms`.
- Each override UID must exist in the resolved endpoint pool (validated at planning time, not at config validation time, since pools are role-scoped).
- Each override value must be compatible with the endpoint's hard-limit `max_deadline_ms` if available.

New failure code consideration: `CANDIDATE_BUDGET_UNALLOCATABLE` already exists and covers this. Override-specific diagnostics should use the same code with a message indicating the UID and override value.

### 3. Router Changes

#### `_candidate_budget`

Current implementation:

```python
def _candidate_budget(plan, candidate_index, remaining_ms):
    has_later_candidate = candidate_index < len(plan.endpoint_uids) - 1
    reserve = (
        plan.effective_config.candidate_budget_ms
        if has_later_candidate and plan.effective_config.protect_last_eligible
        else 0
    )
    available_ms = max(1, remaining_ms - reserve)
    return min(plan.effective_config.candidate_budget_ms, available_ms)
```

Updated logic:

```python
def _candidate_budget(plan, candidate_index, remaining_ms):
    uid = plan.endpoint_uids[candidate_index]
    overrides = plan.effective_config.candidate_budget_overrides_ms
    overrides_dict = dict(overrides) if overrides else None

    # Per-UID budget or fall back to base budget
    base = plan.effective_config.candidate_budget_ms
    budget = (overrides_dict.get(uid, base)) if overrides_dict else base

    # Reserve calculation uses the NEXT candidate's budget for protect_last_eligible
    has_later_candidate = candidate_index < len(plan.endpoint_uids) - 1
    if has_later_candidate and plan.effective_config.protect_last_eligible:
        next_uid = plan.endpoint_uids[candidate_index + 1]
        reserve = (overrides_dict.get(next_uid, base)) if overrides_dict else base
    else:
        reserve = 0

    available_ms = max(1, remaining_ms - reserve)
    return min(budget, available_ms)
```

Key behavioral change in `protect_last_eligible`: the reserve now uses the **next candidate's** budget, not the current candidate's. This is correct because the reserve is protecting time for the fallback, not for the current attempt.

#### Late-response discard

The late-response threshold already uses the return value of `_candidate_budget`. No additional changes needed.

### 4. Config Validation Changes

In `config.py:_validate_policy`:

- Validate `candidate_budget_overrides_ms` values are positive integers.
- Validate override values do not exceed `deadline_ms`.
- UID existence validation is deferred to planning time (config validation doesn't know which role's pool will be used).

### 5. Planning-Time Validation

In `policy.py:_validate_effective_config`, when iterating over resolved endpoint UIDs:

- If `candidate_budget_overrides_ms` contains UIDs not in the endpoint pool, emit a warning or fail with `CANDIDATE_BUDGET_UNALLOCATABLE` (policy strictness).
- If an override value exceeds the endpoint's `max_deadline_ms` hard limit, fail with `CANDIDATE_BUDGET_UNALLOCATABLE`.

Decision: **Fail closed.** Extra UIDs in the override map that don't match any pool candidate indicate a stale or misconfigured policy. This follows the "validate early, fail closed" principle.

### 6. Telemetry Impact

The `POLICY_RESOLVED` event already includes `policy_fingerprint`. The fingerprint computation (based on `OperationRuntimePolicy` hash) automatically includes the new field because the dataclass uses `frozen=True` with `__hash__`.

Add `candidate_budget_overrides_count` to the policy resolved event attributes for observability:

```python
"candidate_budget_overrides_count": str(len(overrides)) if overrides else "0",
```

### 7. README Documentation Changes

#### Telemetry event families

Add a section listing all 14 event families with one-line descriptions:

| Family | When emitted |
|---|---|
| `llm.registry.validated` | Config validation completes |
| `llm.policy.resolved` | Operation runtime policy is resolved with provenance |
| `llm.role.health` | Role health is queried |
| `llm.pool.attempt` | A candidate attempt starts |
| `llm.success` | Invocation succeeds |
| `llm.failure` | Invocation fails |
| `llm.pool.exhausted` | All eligible candidates failed |
| `llm.deadline.exceeded` | Operation deadline expired |
| `llm.cancellation` | Caller canceled the invocation |
| `llm.late_response.discarded` | Provider returned after local timeout |
| `llm.endpoint.suppressed` | Candidate was skipped due to suppression |
| `llm.budget.violation` | Policy invariant was violated |
| `llm.smoke.result` | Smoke gate completed |
| `llm.fake_provider.result` | Fake provider produced a result |

#### Quick-start policy example

Update the existing example to show `reasoning_mode` and `candidate_budget_overrides_ms`:

```python
OperationRuntimePolicy(
    ref="draft-policy",
    deadline_ms=10_000,
    max_output_tokens=1_024,
    reasoning_mode=ReasoningMode.LOW,
    candidate_budget_ms=4_000,
    candidate_budget_overrides_ms={"primary": 6_000},
    protect_last_eligible=True,
    structured_output_mode=StructuredOutputMode.NONE,
)
```

### 8. Smoke / Offline Validation

Offline smoke must validate:

- Override UIDs are present in the role's endpoint pool.
- Override values satisfy positivity and hard-limit constraints.
- Budget allocation simulation works with asymmetric budgets.

### 9. Test Requirements

| Area | Required proof |
|---|---|
| Config validation | Override values validated: positive, within deadline, frozen correctly |
| Policy resolution | Overrides propagated to effective config; provenance tracks correctly |
| Router | Per-UID budgets applied; fallback reserve uses next candidate's budget; UIDs without overrides use base budget |
| Protect last eligible | Reserve calculated using the last candidate's override (not the current candidate's base) |
| Late response | Discarded based on per-UID budget, not flat budget |
| Telemetry | Policy fingerprint changes when overrides change; override count attribute emitted |
| Offline smoke | Stale UID in overrides fails closed |
| Fixture parity | Existing flat-budget tests still pass when overrides are None |

## Risks

| Risk | Mitigation |
|---|---|
| Override map grows large for big pools | Pools are small by design (ordered failover, not load balancing). Override map size is bounded by pool size. |
| Override UID typos cause silent flat-budget fallback | Fail closed: override UIDs must match pool candidates exactly. |
| Frozen tuple-of-tuples lookup is O(n) per candidate | Pool sizes are typically 2-5. Linear scan on sorted tuples is negligible. If needed, router can build a dict once per invocation. |
| Breaking change for existing configs | No: `candidate_budget_overrides_ms` defaults to `None`, preserving existing behavior. Zero BC is satisfied because pre-V1 consumers pin exact versions. |

## Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Per-family keying (`candidate_budget_overrides_ms: {gemini: 12000}`) | Leaks provider taxonomy into business-agnostic config. Host can derive per-UID overrides from their own family mapping. |
| Nested budget shape object (`CandidateBudgetShape(mode=PER_UID, overrides={...})`) | Over-engineering for one optional map field. If more budget modes are needed later, Zero BC allows a clean replacement. |
| CallerPolicyOverrides support for per-UID budgets | Per-UID budgets encode operator topology knowledge, not request-time intent. Mixing them into caller overrides conflates concerns. |
| Separate `PerUidBudgetPolicy` dataclass | Unnecessary indirection. The field belongs on the existing policy where all budget-related fields live. |

## Sequencing

This design is implemented as one atomic unit. No phased delivery is needed because:

- The field is optional and defaults to None (backward compatible at the config level).
- All changes are internal to the module (no host integration required to ship).
- README changes can land in the same release.
