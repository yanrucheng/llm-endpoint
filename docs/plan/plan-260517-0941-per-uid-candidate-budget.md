---
id: "plan-260517-0941-per-uid-candidate-budget"
title: "Per-UID Candidate Budget Overrides And README Contract Hardening"
type: plan
status: completed
created: 2026-05-17
updated: 2026-05-17
parent: "design-260517-0941-per-uid-candidate-budget"
depends-on:
  - "plan-260516-1331-llm-endpoint-module"
  - "plan-260516-2208-prd-compliance-remediation"
superseded-by: ""
author: "agent"
tags: ["candidate-budget", "per-uid", "policy", "router", "telemetry-docs", "readme"]
---

# Per-UID Candidate Budget Overrides And README Contract Hardening

## Prerequisite State

All prior plans (`plan-260516-1331-llm-endpoint-module`, `plan-260516-2208-prd-compliance-remediation`) are implemented and passing. This plan builds on the completed V1 codebase.

## Delivery Structure

Two parallel tracks, one phase each. No inter-track dependency — they can be implemented and merged independently or together.

```text
Track A: Per-UID Candidate Budget (code)
  T1 -> T2 -> T3 -> T4 -> T5

Track B: README Contract Hardening (docs)
  T6 -> T7
```

## Track A: Per-UID Candidate Budget Overrides

### T1: Schema And Config Validation

**Files:** `src/llm_endpoint/config.py`

| Step | Action |
|---|---|
| 1 | Add `candidate_budget_overrides_ms: Mapping[str, int] | None = None` field to `OperationRuntimePolicy` dataclass, positioned after `candidate_budget_ms`. |
| 2 | Update `_validate_policy` to validate override values are positive integers and do not exceed `deadline_ms`. |
| 3 | Update config identity/fingerprint logic (if `asdict` is used, new field is automatically included by frozen dataclass). |
| 4 | Add unit tests in `tests/` for config validation: valid overrides, zero/negative values rejected, values exceeding deadline rejected, None is valid (no change). |

**Gate:** `pytest tests/ -k config` passes.

### T2: Policy Resolution And Effective Runtime Config

**Files:** `src/llm_endpoint/policy.py`

| Step | Action |
|---|---|
| 1 | Add `candidate_budget_overrides_ms: tuple[tuple[str, int], ...] | None` field to `EffectiveRuntimeConfig` dataclass. |
| 2 | Update `_effective_config` to freeze the mapping into sorted tuple-of-tuples. |
| 3 | Add `"candidate_budget_overrides_ms"` to `PolicyField` enum if provenance tracking requires it. |
| 4 | Update `_provenance` to include the new field with `PolicySource.POLICY` when set or a suitable "not set" indicator when None. |
| 5 | Update `_validate_effective_config` to validate override UIDs exist in the resolved endpoint pool and override values respect endpoint hard limits. Use `FailureCode.CANDIDATE_BUDGET_UNALLOCATABLE` with UID-specific messages. |
| 6 | Add `candidate_budget_overrides_count` attribute to the `POLICY_RESOLVED` telemetry event in `resolve_policy`. |
| 7 | Add unit tests: effective config construction with and without overrides; provenance; validation pass and fail cases; telemetry attribute. |

**Gate:** `pytest tests/ -k policy` passes.

### T3: Router Per-UID Budget Allocation

**Files:** `src/llm_endpoint/router.py`

| Step | Action |
|---|---|
| 1 | Update `_candidate_budget` to resolve the UID from `plan.endpoint_uids[candidate_index]` and look up its override budget if `candidate_budget_overrides_ms` is not None. |
| 2 | Update `protect_last_eligible` reserve calculation to use the **next candidate's** budget (override or base), not the current candidate's. |
| 3 | Add unit tests: per-UID budgets applied correctly; UIDs without overrides fall back to base; protect_last_eligible reserves the correct asymmetric amount; late-response discard uses per-UID budget. |
| 4 | Verify existing flat-budget tests still pass with `candidate_budget_overrides_ms=None`. |

**Gate:** `pytest tests/ -k router` passes.

### T4: Offline Smoke Validation

**Files:** `src/llm_endpoint/smoke.py` (or validation path)

| Step | Action |
|---|---|
| 1 | Ensure offline smoke exercises per-UID budget validation: override UIDs checked against role pool, positivity, hard-limit constraints. |
| 2 | Add smoke test case: config with stale UID in overrides fails with clear error. |
| 3 | Add smoke test case: config with valid overrides passes and budget simulation works. |

**Gate:** `pytest tests/ -k smoke` passes.

### T5: Integration And Full Suite

| Step | Action |
|---|---|
| 1 | Run full test suite: `pytest tests/` — all existing tests must pass unchanged (None default preserves behavior). |
| 2 | Run contract fixtures if applicable. |
| 3 | Verify policy fingerprint changes when overrides are added/removed (hash stability test). |

**Gate:** Full `pytest tests/` green. No regressions.

## Track B: README Contract Hardening

### T6: Telemetry Event Families Documentation

**Files:** `README.md`

| Step | Action |
|---|---|
| 1 | Add a `## Telemetry Event Families` section after the existing "Host Callback Contracts" section. |
| 2 | List all 14 event families with stable names and one-line descriptions (per design doc table). |
| 3 | Note that event names are part of the public contract and governed by Zero BC. |

**Gate:** README renders correctly; event names match `TelemetryEventFamily` enum values in code.

### T7: Quick-Start Policy Example Update

**Files:** `README.md`

| Step | Action |
|---|---|
| 1 | Update the quick-start `OperationRuntimePolicy` example to include `reasoning_mode=ReasoningMode.LOW`. |
| 2 | After T5 lands, also add `candidate_budget_overrides_ms={"primary": 6_000}` to the example. |
| 3 | Add `ReasoningMode` to the imports in the quick-start code block. |
| 4 | Verify the quick-start example is syntactically valid Python (copy-paste test). |

**Gate:** README quick-start example runs without import or type errors against installed module.

## Evidence And Completion Criteria

**Completion evidence:** Full suite verified on 2026-05-17 with `uv run pytest tests/ -q`:
`112 passed in 0.19s`.

| Criterion | Proof |
|---|---|
| Per-UID budgets are configurable | Config with `candidate_budget_overrides_ms` validates and resolves |
| Router uses per-UID budgets | Test shows candidate A gets 6000ms, candidate B gets 4000ms (base) |
| Protect last eligible is asymmetric | Test shows reserve uses the last candidate's budget, not the current candidate's |
| Stale UIDs fail closed | Config with override UID not in pool fails at planning time |
| README documents telemetry events | All 14 families listed with names matching code |
| README shows reasoning_mode | Quick-start policy includes `reasoning_mode=ReasoningMode.LOW` |
| No regressions | Full test suite passes; existing configs without overrides are unchanged |

## Dependency Graph

```text
T1 (config schema)
  └─> T2 (policy resolution)
        └─> T3 (router)
              └─> T4 (smoke)
                    └─> T5 (integration)

T6 (README telemetry) ──┐
T7 (README policy)    ──┘ (independent of Track A until T7 step 2)
```

## Estimated Scope

| Track | Files touched | New test cases | Complexity |
|---|---|---|---|
| A | 4 source files, ~5 test files | ~15-20 new tests | Medium (field addition + router logic change) |
| B | 1 file (README.md) | 0 (manual verification) | Low (documentation only) |

## Zero BC Compliance

- `candidate_budget_overrides_ms` defaults to `None` — no existing config breaks.
- No existing public API signature changes — the field is additive.
- Policy fingerprint changes are expected when the field is populated (new config = new fingerprint).
- README documentation additions are non-breaking by definition.
- Pre-V1 status means consumers pin exact versions; any upgrade is already a conscious act.
