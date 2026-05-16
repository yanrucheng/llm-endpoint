---
id: "phase-5e-extraction-adoption-guide"
title: "LLM Endpoint Extraction and Adoption Guide"
type: guide
status: draft
created: 2026-05-16
updated: 2026-05-16
parent: "plan-260516-1331-llm-endpoint-module"
tags: ["llm", "endpoint", "adoption", "zero-bc", "rollout", "rollback"]
---

# LLM Endpoint Extraction and Adoption Guide

This guide is the Phase 5E adoption artifact for consuming repositories.

## Backward Compatibility Policy

| Attribute | Value |
|---|---|
| Production status | Not in production |
| BC Level | None - Zero BC policy |

No production consumers. BC mechanisms are prohibited to avoid code debt.
Clean-slate deployment is assumed.

Prohibited mechanisms:

- API version routers or `/v1`/`/v2` coexistence.
- Compatibility facades for legacy provider/model tuples.
- Deprecated field preservation in config, telemetry, failure, or fixture schemas.
- Feature flags that select old-vs-new behavior for non-existent consumers.

## Pinning Strategy

Consumers pin the package by exact pre-V1 version and treat each upgrade as a
replacement of the current clean-slate contract.

Required consumer actions:

- Pin `llm-endpoint==0.1.0` until the next coordinated replacement.
- Capture a public surface baseline with `capture_public_surface_baseline()`.
- Run `check_public_surface_release()` with changelog and Zero BC migration notes
  before accepting a replacement.
- Run `build_consumer_contract_pack()` and execute every listed test selector.

## Host Responsibilities

The host repository owns environment-specific boundaries. The module owns public
contracts and redacted reporting.

Host-owned responsibilities:

- Provide `resolve_secret(ref)` without exposing raw secret values to telemetry.
- Provide `resolve_schema(ref)` with stable schema name, version, and fingerprint.
- Configure roles, pools, policies, capability refs, and credential refs.
- Own live provider network behavior through the optional live-smoke probe callback.
- Store redacted debug replay artifacts and telemetry events only.

Module-owned guarantees:

- Offline validation runs without network or credentials.
- Consumer contract cases cover config validation, failure taxonomy, telemetry
  redaction, structured output, pool simulation, plain text, and direct migration.
- Optional live smoke requires explicit consent and emits typed skipped, passed,
  or failed outcomes.

## Rollout Levers

Use rollout controls only against current endpoint UIDs and policy fingerprints.

Safe rollout sequence:

- Validate config offline with `run_offline_smoke()`.
- Run the consumer contract pack without credentials.
- Enable canary identification by role and operation.
- Compare expected policy fingerprints before accepting traffic.
- Suppress individual endpoint UIDs when a candidate must be removed.
- Force a candidate only in test mode.

## Rollback Levers

Rollback is by current config identity, not by legacy adapters.

Supported rollback actions:

- Restore the last known-good config object.
- Suppress a bad endpoint UID.
- Re-pin the package to the previous exact pre-V1 version.
- Re-run offline smoke and the consumer contract pack before resuming traffic.

Unsupported rollback actions:

- Runtime translation from old config schemas.
- Dual-running legacy and current invocation contracts.
- Legacy Nightfall facade compatibility beyond direct API parity checks.

## Non-V1 Exclusions

The following remain outside the V1 adoption path:

- Runtime config reload without explicit validated replacement semantics.
- Multi-version API coexistence.
- Automatic provider credential discovery.
- Broad Nightfall facade support beyond the direct migration readiness boundary.
- Live smoke as a production health dependency.
