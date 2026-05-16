---
title: "260516-prd-design-compliance-audit"
service_version: "0.1.0"
date: 2026-05-16
environment: "local-static-review"
model_id: "manual-repo-inspection"
dataset_version: "prd-260516-1321-llm-endpoint-module"
purpose: "Assess whether the current repo follows the standalone V1 LLM endpoint module PRD."
baseline_ref: ""
---

# PRD Design Compliance Audit

## Verdict

The repo is directionally high quality, but not yet high quality in following the full PRD as a consumer-facing V1 contract.

It has a coherent Python package, a strong public-surface manifest, contract tests, fake-provider coverage, offline smoke, role health, rollout controls, debug replay, and Zero BC release guard. `uv run pytest` passes with 81 tests.

The gap is not broad implementation chaos. The gap is public contract precision: several surfaces implement a plausible internal V1, but not the exact product contract written in `docs/prd/prd-260516-1321-llm-endpoint-module.md`. In pre-production / Zero BC mode, that is still debt because consumers will build against the public names, failure codes, telemetry fields, and supported modes.

## Audit Scope

Design source:

- `docs/prd/prd-260516-1321-llm-endpoint-module.md`

Implementation reviewed:

- `src/llm_endpoint/results.py`
- `src/llm_endpoint/invocation.py`
- `src/llm_endpoint/policy.py`
- `src/llm_endpoint/config.py`
- `src/llm_endpoint/router.py`
- `src/llm_endpoint/telemetry.py`
- `src/llm_endpoint/public_surface.py`
- `src/llm_endpoint/__init__.py`
- `tests/contracts/*`

Validation run:

```bash
uv run pytest
```

Result:

```text
81 passed in 0.32s
```

## Findings

## [G: Inconsistent Pattern] [S1] Failure taxonomy does not match the PRD public codes

**File**: `src/llm_endpoint/results.py` lines 39-69, `src/llm_endpoint/invocation.py` lines 182-239, `src/llm_endpoint/policy.py` lines 101-111

**Intent contradiction**: The PRD defines normalized public failure codes as stable `llm.*` values, for example `llm.endpoint.unknown_role`, `llm.endpoint.unknown_entrypoint`, `llm.policy.operation_ref_required`, `llm.input.invalid_messages`, `llm.pool.exhausted`, and `llm.structured_output.invalid_payload`. The implementation exposes compact enum values such as `invalid_invocation`, `invalid_config`, `provider_timeout`, `pool_exhausted`, and maps multiple distinct public cases into `INVALID_INVOCATION`.

**Why this matters**: Failure codes are explicitly public API. Consumers cannot reliably branch on PRD-defined errors if the module collapses unknown role, missing operation ref, invalid messages, and unknown operation into the same internal-looking code.

**Evidence**:

- PRD `Output & Errors` requires `llm.*` codes: `docs/prd/prd-260516-1321-llm-endpoint-module.md` lines 663-697.
- `FailureCode` values are not `llm.*`: `src/llm_endpoint/results.py` lines 39-69.
- Missing `operation_ref` returns `FailureCode.INVALID_INVOCATION`: `src/llm_endpoint/invocation.py` lines 190-196.
- Invalid messages return `FailureCode.INVALID_INVOCATION`: `src/llm_endpoint/invocation.py` lines 205-239.
- Unknown role / operation from registry resolution returns `FailureCode.INVALID_INVOCATION`: `src/llm_endpoint/policy.py` lines 101-111.

**Verdict**: Replace the public taxonomy with PRD-aligned `llm.*` codes, or update the PRD before treating this repo as compliant. In Zero BC pre-production mode, prefer replacing the code now.

**Verification**:

```bash
grep -R "llm\\.endpoint\\.unknown_role\\|llm\\.policy\\.operation_ref_required\\|llm\\.input\\.invalid_messages" -n src tests
```

**Maturity note**: S1 in pre-production because this is a public contract mismatch, not an implementation detail.

## [F: Test Debt] [S1] Contract tests validate the repo's current taxonomy, not the PRD taxonomy

**File**: `tests/contracts/test_invocation_contract.py`, `tests/contracts/test_policy_contract.py`, `tests/contracts/test_phase5_operator_readiness.py`, `tests/fixtures/contracts/direct_migration/legacy_fields_rejected.json`

**Intent contradiction**: The PRD makes the failure taxonomy part of the consumer-facing contract. Tests currently assert `FailureCode.INVALID_INVOCATION`, `FailureCode.POLICY_VIOLATION`, and fixture value `invalid_invocation` instead of asserting the PRD's exact public codes.

**Why this matters**: Passing tests create false confidence. The test suite is strong mechanically, but it does not prove the most important public error-code contract.

**Evidence**:

- `tests/contracts/test_invocation_contract.py` asserts `FailureCode.INVALID_INVOCATION` for invalid invocation cases.
- `tests/contracts/test_policy_contract.py` asserts `FailureCode.POLICY_VIOLATION` / `BUDGET_VIOLATION` instead of PRD codes.
- `tests/contracts/test_phase5_operator_readiness.py` asserts legacy-field rejection as `FailureCode.INVALID_INVOCATION`.
- `tests/fixtures/contracts/direct_migration/legacy_fields_rejected.json` expects `"invalid_invocation"`.

**Verdict**: Rewrite contract fixtures around PRD-observable strings, not enum member identity. Internal enums can remain if their `.value` is the public `llm.*` code.

**Verification**:

```bash
grep -R "INVALID_INVOCATION\\|invalid_invocation\\|POLICY_VIOLATION\\|BUDGET_VIOLATION" -n tests
```

**Maturity note**: S1 because the suite masks an S1 public-surface defect.

## [E: Defensive Anachronism] [S1] Structured failures and failure telemetry cannot carry required schema identity

**File**: `src/llm_endpoint/results.py` lines 153-163, `src/llm_endpoint/telemetry.py` lines 73-85, `src/llm_endpoint/router.py` lines 713-731

**Intent contradiction**: The PRD requires typed failures to include schema contract ref/fingerprint when applicable, and telemetry common fields to include `schema_contract_ref` and `schema_fingerprint` when structured output is involved. The implementation only carries schema identity on `StructuredResult` success and success-event attributes. `FailureContext` and `TelemetryContext` have no schema fields, and `_failure_event()` only emits failure code, retryability, and router version.

**Why this matters**: The most important structured-output failures are schema failures, refusals, wrong tools, malformed JSON, and missing contracts. Those failures need schema identity for debugging, cross-repo telemetry, smoke, and replay.

**Evidence**:

- PRD common telemetry fields: `docs/prd/prd-260516-1321-llm-endpoint-module.md` lines 573-591.
- PRD typed failure fields: `docs/prd/prd-260516-1321-llm-endpoint-module.md` lines 698-711.
- `FailureContext` lacks schema fields: `src/llm_endpoint/results.py` lines 153-163.
- `TelemetryContext` lacks schema fields: `src/llm_endpoint/telemetry.py` lines 73-85.
- `_failure_event()` omits schema fields: `src/llm_endpoint/router.py` lines 713-731.
- `_success_event()` includes schema identity only for success attributes, not the common context: `src/llm_endpoint/router.py` lines 681-710.

**Verdict**: Add schema contract ref/fingerprint to failure context and telemetry context, then require structured-output failure tests to assert them.

**Verification**:

```bash
grep -R "schema_contract_ref\\|schema_fingerprint" -n src/llm_endpoint/results.py src/llm_endpoint/telemetry.py src/llm_endpoint/router.py tests/contracts
```

**Maturity note**: S1 because structured output is a PRD trust boundary, and failures without schema identity are operationally incomplete.

## [B: Temporal Residue] [S2] `prompt_json` is in V1 Migration Hardening but rejected as a Phase 1 non-contract

**File**: `src/llm_endpoint/config.py` lines 588-595, `tests/contracts/test_config_contract.py` line 87

**Intent contradiction**: The PRD includes tool-call, schema, and prompt-JSON extraction modes as V1 Migration Hardening. The implementation defines `StructuredOutputMode.PROMPT_JSON`, but validation rejects it with the message `prompt_json is a last-resort mode and is not accepted in the Phase 1 contract`.

**Why this matters**: This can be acceptable for a Phase 1/Core-only milestone, but it means the repo is not compliant with the full V1 PRD acceptance target. The code also uses phase language that is not reflected in the PRD's public V1 product contract.

**Evidence**:

- PRD V1 Migration Hardening requires `Tool-call/schema/prompt-JSON extraction modes`: `docs/prd/prd-260516-1321-llm-endpoint-module.md` lines 103-111.
- Config rejects prompt JSON mode: `src/llm_endpoint/config.py` lines 588-595.
- Test fixture intentionally exercises the rejected mode: `tests/contracts/test_config_contract.py` line 87.

**Verdict**: Either implement prompt-JSON mode before claiming full V1 PRD compliance, or explicitly mark the repo as Core-only and keep the eval status partial.

**Verification**:

```bash
grep -R "PROMPT_JSON\\|prompt_json" -n src tests docs
```

**Maturity note**: S2 because it is a scope-completion gap, not a hidden runtime bug.

## [C: Speculative Scaffolding] [S2] Cancellation protocol mentions sync and async paths, but no async public API exists

**File**: `src/llm_endpoint/invocation.py` lines 35-41, `src/llm_endpoint/router.py` lines 87-96

**Intent contradiction**: The PRD requires documented sync/async behavior and cancellation semantics. The implementation has a `CancellationToken` protocol "shared by sync and async invocation paths", but the public invocation and routing functions are synchronous, and a source scan found no `async def` implementation.

**Why this matters**: The phrase implies a public async path or at least a documented async compatibility story. Without one, async consumers must wrap sync execution themselves, which can break deadline, cancellation, and late-response semantics that the PRD makes public.

**Evidence**:

- PRD requires documented sync/async behavior: `docs/prd/prd-260516-1321-llm-endpoint-module.md` lines 107-112 and lines 460-473.
- `CancellationToken` docstring references sync and async paths: `src/llm_endpoint/invocation.py` lines 35-41.
- Public route API is sync only: `src/llm_endpoint/router.py` lines 87-96.
- `grep -R "async def" src` returns no async implementation.

**Verdict**: Add an explicit async API or rewrite the public docs/comments to state V1 is sync-only with host-owned async wrapping. If PRD stays as written, implement and test async semantics.

**Verification**:

```bash
grep -R "async def" -n src tests
```

**Maturity note**: S2 because cancellation exists, but the async public contract is incomplete.

## [G: Inconsistent Pattern] [S3] Router reserve behavior exists, but the PRD's named `protect_last_eligible` control is absent

**File**: `src/llm_endpoint/policy.py` lines 193-210, `src/llm_endpoint/router.py` lines 144-146

**Intent contradiction**: The PRD names `protect_last_eligible` behavior for preserving budget to attempt the last eligible candidate. The implementation uses `failover_reserve_ms` and candidate-budget logic instead, without exposing the named control.

**Why this matters**: This is probably functionally close, but public policy vocabulary matters because the PRD says host operators configure policy, rollout, and failover behavior.

**Evidence**:

- PRD names `protect_last_eligible`: `docs/prd/prd-260516-1321-llm-endpoint-module.md` lines 485-491.
- Effective config exposes `failover_reserve_ms`, not `protect_last_eligible`: `src/llm_endpoint/policy.py` lines 193-210.
- Router derives candidate budget from reserve logic: `src/llm_endpoint/router.py` lines 144-146.

**Verdict**: Either add the named policy knob or update the PRD to define `failover_reserve_ms` as the canonical V1 mechanism.

**Verification**:

```bash
grep -R "protect_last_eligible\\|failover_reserve_ms" -n src tests docs
```

**Maturity note**: S3 because the intended behavior may already be covered by a different field.

## Non-Findings

These areas are materially aligned with the PRD:

- Public package and version constants exist in `src/llm_endpoint/__init__.py`.
- Zero BC ownership is explicit in `src/llm_endpoint/public_surface.py`.
- Direct invocation planning exists in `src/llm_endpoint/invocation.py`.
- Runtime policy resolution and provenance exist in `src/llm_endpoint/policy.py`.
- Deterministic pool routing, retryable-only fallback, cancellation handling, and late-response discard exist in `src/llm_endpoint/router.py`.
- Secret and schema resolver contracts exist in `src/llm_endpoint/callbacks.py`.
- Fake provider, offline smoke, role health, rollout controls, debug replay, and release guard surfaces exist.
- Tests are broad and fast: 81 passing contract tests.

## Recommendation

Do not call the repo fully PRD-compliant yet. Call it a strong pre-V1/Core implementation with public-contract drift.

Fix order:

1. Replace failure code values and tests with exact PRD `llm.*` public codes.
2. Add schema contract identity to structured failures and failure telemetry.
3. Decide whether current milestone is Core-only or full V1; if full V1, implement `prompt_json`.
4. Decide sync-only vs sync+async; align code, docs, and tests with that decision.
5. Resolve the `protect_last_eligible` vocabulary mismatch between PRD and policy schema.

## Raw Artifacts

No raw outputs were generated. This session is a static design-compliance audit. Runtime test output was reviewed from `uv run pytest` and is summarized above.
