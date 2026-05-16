---
id: "design-260516-2208-prd-compliance-remediation"
title: "LLM Endpoint PRD Compliance Remediation Design"
type: design
status: finalized
created: 2026-05-16
updated: 2026-05-16
parent: "index-design"
depends-on:
  - "prd-260516-1321-llm-endpoint-module"
  - "design-260516-1331-llm-endpoint-module"
superseded-by: ""
author: "agent"
tags: ["llm", "endpoint", "prd-compliance", "failure-taxonomy", "telemetry", "zero-bc"]
source: "docs/prd/prd-260516-1321-llm-endpoint-module.md"
---

# LLM Endpoint PRD Compliance Remediation Design

## Context & Goals

The original LLM Endpoint Module implementation plan has finished all phase gates. A post-implementation audit in `eval/sessions/260516-1743-prd-design-compliance-audit/report.md` found that the repository is directionally strong but not yet fully aligned with the PRD as a consumer-facing V1 public contract.

This design is a follow-up remediation design, not a replacement for the original module architecture. It narrows the next technical work to public-contract drift found after implementation.

Technical goals:

| ID | Goal | PRD / Eval Trace |
|---|---|---|
| RG1 | Make failure taxonomy values and granularity match the PRD's public `llm.*` codes. | PRD Output & Errors; eval S1 taxonomy finding |
| RG2 | Ensure contract tests assert PRD-observable public values, not implementation-local enum identity. | PRD Public Surface Contract; eval S1 test-debt finding |
| RG3 | Carry schema contract identity through structured failures and failure telemetry, not only structured successes. | PRD Telemetry, Typed Failure fields; eval S1 schema-identity finding |
| RG4 | Implement `prompt_json` as a supported V1 Migration Hardening mode. | PRD V1 Migration Hardening; eval S2 prompt-json finding |
| RG5 | Resolve the sync/async public API ambiguity without weakening cancellation and deadline integrity. | PRD Async/Cancellation; eval S2 async finding |
| RG6 | Align router policy vocabulary with the PRD's `protect_last_eligible` control. | PRD Pool Router; eval S3 vocabulary finding |

## Non-Goals

| Non-goal | Technical Boundary |
|---|---|
| Rebuilding the LLM endpoint module from scratch | The completed implementation remains the baseline; this design only corrects public-contract drift. |
| Adding compatibility aliases for current incorrect failure codes | Zero BC allows direct replacement before production; aliases would create debt. |
| Reopening provider adapter, registry, role-health, rollout, fake-provider, or debug replay architecture | Eval marked these areas materially aligned unless touched by public-contract remediation. |
| Changing product requirements in the PRD | If the PRD is wrong, update it explicitly before implementation; do not silently diverge in code. |
| Creating a migration facade for consumers | The original Zero BC design still applies; consumers update to canonical public contracts. |

## Backward Compatibility Policy

| Attribute | Value |
|---|---|
| Production status | Not in production as a standalone public dependency |
| BC Level | None - Zero BC policy |

No production consumers. BC mechanisms are prohibited to avoid code debt. Clean-slate deployment is assumed.

Design constraints:

- Replace incorrect public names directly; do not add aliases, deprecated codes, adapters, or compatibility translation layers.
- Contract fixtures must change with the public contract so tests prove PRD behavior, not historical implementation behavior.
- Any consumer-facing change must be captured in the release guard/changelog evidence before adoption.

## System Context

| Actor / System | Relationship | Boundary |
|---|---|---|
| Host application | Handles typed failures, consumes telemetry, and runs contract fixtures. | Public API, failure taxonomy, telemetry schema, fixture pack. |
| Module maintainer | Owns remediation and Zero BC public-surface replacement. | Release guard, changelog, public surface manifest. |
| Contract test suite | Proves PRD-observable behavior. | Golden fixtures and public string/code assertions. |
| Telemetry sink | Receives redacted event envelopes. | Must receive schema identity for structured failures. |
| Schema resolver | Supplies schema contract identity and validation material. | Source for schema ref/version/fingerprint propagation. |
| Provider adapter / router | Produces terminal outcomes and attempt traces. | Must map failures into PRD taxonomy without raw provider leakage. |

## Component Architecture

| Component | Remediation Responsibility | Ownership |
|---|---|---|
| Failure Taxonomy Contract | Replace local compact codes with PRD `llm.*` public codes and preserve retryability/failure-class mapping. | Runtime owner |
| Failure Context Model | Carry schema contract ref/fingerprint when structured operations fail. | Runtime owner + Schema owner |
| Telemetry Context Model | Promote schema contract ref/fingerprint into the event context or a required structured-event field set. | Observability owner |
| Invocation & Policy Error Mapper | Distinguish missing operation ref, invalid messages, unknown role, unknown operation, policy mismatch, and budget errors. | API owner + Runtime owner |
| Structured Failure Pipeline | Attach schema identity to missing schema, unknown schema, invalid payload, refusal, wrong tool, and validation failures when available. | Schema owner |
| Contract Fixture Pack | Assert exact public code strings, schema identity on failures, and redaction constraints. | Test owner |
| Structured Mode Scope Gate | Enforce `prompt_json` as an implemented V1 mode. | Schema owner + Module maintainer |
| Async Contract Boundary | Document sync-only V1; preserve cancellation/deadline semantics on the supported sync API. | API owner |
| Router Policy Vocabulary | Align public config/telemetry/docs for last-candidate protection semantics. | Runtime owner |
| Release Guard | Treat the corrected taxonomy, telemetry, and mode/sync decisions as the new clean-slate baseline. | Module maintainer |

## Data Flow

### Failure Taxonomy Flow

```text
input/config/policy/provider/schema/router failure
  -> specific PRD failure code selection
  -> retryability + failure class mapping
  -> typed failure envelope
  -> failure telemetry event
  -> contract fixture assertion
```

The mapper must choose the most specific public code available. Generic validation failure is allowed only when the PRD has no more precise code.

### Structured Failure Identity Flow

```text
invocation request + operation policy
  -> schema contract ref resolution
  -> schema name/version/fingerprint when available
  -> structured provider attempt
  -> structured failure or success
  -> typed failure/result with schema identity
  -> telemetry/debug artifact with same identity
```

If schema resolution fails before a fingerprint exists, the failure must still carry the requested schema contract ref and a safe missing/unknown status.

### Contract Test Flow

```text
PRD public contract
  -> golden fixture values
  -> typed failure / telemetry assertions
  -> release guard baseline
  -> consumer contract pack
```

Tests must assert public strings and payload fields that consumers observe, not only internal enum members.

## Data Model

| Entity | Remediation Change | Invariant |
|---|---|---|
| Public Failure Code | Value is the PRD `llm.*` code. | Stable public string is the primary contract. |
| Failure Category | Groups codes by config, endpoint, policy, input, schema, structured output, invocation, deadline, pool, smoke, budget, or module. | Category cannot replace a specific public code. |
| Retryability | Retains public retryable/non-retryable semantics. | Retryable defaults match PRD taxonomy. |
| Failure Context | Adds schema contract ref/fingerprint fields when applicable. | Context contains safe identities only, never raw payloads. |
| Telemetry Context | Adds structured schema identity fields when applicable. | Required common fields are present by event family. |
| Schema Identity | Requested ref plus resolved name/version/fingerprint when available. | Structured success requires fingerprint; structured failure carries the best safe identity available. |
| Structured Mode Declaration | Records `prompt_json` as supported V1 behavior. | Config validation and tests agree. |
| Async Contract Declaration | Records sync-only V1 behavior. | Cancellation and late-response semantics are defined for the supported sync API. |
| Router Protection Policy | Represents last eligible candidate protection semantics. | Public config, telemetry, and docs use one canonical vocabulary. |

## API & Contract Surface

### Failure Taxonomy Contract

Failure codes are public strings. The contract must include at least the PRD codes in these families:

| Family | Examples |
|---|---|
| Config | `llm.config.invalid_endpoint_config`, `llm.config.credential_unavailable` |
| Endpoint | `llm.endpoint.unknown_role`, `llm.endpoint.unknown_entrypoint`, `llm.endpoint.unsupported_provider_format`, `llm.endpoint.suppressed` |
| Policy | `llm.policy.capability_mismatch`, `llm.policy.unsupported_reasoning_mode`, `llm.policy.output_budget_exceeds_hard_cap`, `llm.policy.candidate_budget_unallocatable`, `llm.policy.operation_ref_required` |
| Input | `llm.input.invalid_messages`, `llm.input.cancelled` |
| Schema / Structured Output | `llm.schema.missing_contract`, `llm.schema.unknown_contract`, `llm.structured_output.invalid_payload`, `llm.structured_output.refusal` |
| Invocation / Pool | `llm.invocation.rate_limited`, `llm.invocation.quota_exhausted`, `llm.invocation.transient_network`, `llm.invocation.provider_5xx`, `llm.invocation.provider_failure`, `llm.invocation.local_candidate_timeout`, `llm.invocation.late_response_discarded`, `llm.pool.no_eligible_candidate`, `llm.pool.exhausted` |
| Smoke / Budget / Module | `llm.smoke.skipped`, `llm.smoke.failed`, `llm.budget.violation`, `llm.module.unsupported_version` |

### Telemetry Contract

Structured invocation telemetry must include:

| Field | Required When |
|---|---|
| `schema_contract_ref` | Structured operation references or requires a schema. |
| `schema_fingerprint` | Schema was resolved or a structured result/failure has schema material. |
| `failure_class` | Terminal failure event. |
| `failure_code` | Terminal failure event. |
| `operation_invocation_id`, `role`, `operation_ref`, `policy_fingerprint`, `redaction_status` | Invocation-related events. |

Schema fields must remain safe identifiers. Raw schema material, prompts, responses, tool args, or outputs remain forbidden.

### Structured Mode Contract

The module must choose one of two compliant states:

| State | Contract |
|---|---|
| Full V1 | `prompt_json` is a supported extraction mode with validation, bounded retry/failure behavior, telemetry, and fake-provider coverage. |
| Core-only interim | `prompt_json` remains rejected, but docs, tests, release guard, and adoption status clearly state the repo is not full V1 PRD-compliant yet. |

Silent mismatch is not allowed.

### Sync/Async Contract

The module must choose one of two compliant states:

| State | Contract |
|---|---|
| Sync-only V1 | Public docs and comments state sync-only API; hosts own async wrapping; cancellation token semantics remain supported for sync execution. |
| Sync+async V1 | Public async invocation and routing contracts exist; sync and async terminal failure, cancellation, timeout, and telemetry semantics are equivalent. |

### Router Protection Contract

The module must expose exactly one public vocabulary for last-candidate protection:

| Option | Contract |
|---|---|
| `protect_last_eligible` | Boolean policy/control explicitly preserves enough budget for the final eligible candidate. |
| Rejected numeric reserve | `failover_reserve_ms` is removed as public vocabulary under Zero BC. |

## NFR & SLO Targets

| Target | SLO / Measurement | Trace |
|---|---|---|
| Taxonomy precision | 100% of audited PRD failure cases map to exact `llm.*` public codes. | RG1 |
| Contract-test fidelity | Tests assert public code strings and telemetry fields for each changed surface. | RG2 |
| Structured failure observability | 100% of structured-output failures carry schema ref and resolved fingerprint when available. | RG3 |
| Redaction preservation | No remediation adds raw prompt, response, schema material, secret, or provider header leakage. | PRD Security |
| Zero BC cleanliness | No aliases, legacy loaders, deprecated code mappings, or compatibility adapters are introduced. | BC policy |
| Decision clarity | `prompt_json`, sync-only V1, and `protect_last_eligible` each have one documented public state. | RG4-RG6 |

## Cross-Cutting Concerns

| Concern | Rule |
|---|---|
| Security | New schema fields are identity/fingerprint fields only; no raw schema or model output may enter telemetry/failures. |
| Observability | Failure telemetry must be sufficient for cross-repo grouping by PRD code, schema identity, role, operation, endpoint, and policy fingerprint. |
| Testing | Golden fixtures become the source of truth for public values; enum identity tests are secondary. |
| Release discipline | Release guard/changelog must mark taxonomy and telemetry changes as Zero BC public-surface replacement. |
| Documentation | Original completed plan remains archived; remediation docs own the new work. |

## Trade-Off Analysis

| Option | Decision | Rationale |
|---|---|---|
| Patch current compact failure code names with aliases vs replace them | Replace them. | Zero BC pre-production makes direct replacement simpler and avoids consumers learning wrong names. |
| Keep schema identity as success-only attribute vs add it to failure/telemetry context | Add it to failures and telemetry. | PRD requires structured failures to be diagnosable without raw payloads. |
| Implement `prompt_json` immediately vs declare Core-only interim | Implement `prompt_json`. | Full V1 compliance requires the mode and the implementation is bounded to extraction plus schema validation. |
| Add async API immediately vs declare sync-only V1 | Declare sync-only V1. | The current public API is sync; hosts own async wrapping until a real async router can preserve cancellation without shims. |
| Rename policy to `protect_last_eligible` vs document `failover_reserve_ms` as canonical | Use `protect_last_eligible`. | The PRD already names this public behavior; Zero BC allows direct replacement of the numeric reserve field. |

## Sequencing Constraints

| Constraint | Blocks |
|---|---|
| Failure taxonomy target table must be finalized before code or fixture changes. | Error mapper, fixtures, release guard baseline. |
| Schema identity fields must be defined before structured failure pipeline updates. | Router failures, telemetry events, debug artifacts, tests. |
| `prompt_json` state must be decided before config validation and structured-output tests are updated. | Full V1 compliance claim. |
| Sync/async state must be decided before invocation API docs/comments/tests are updated. | Cancellation contract and adoption guidance. |
| Router vocabulary must be decided before policy schema/docs/fixtures change. | Pool router contract and PRD-doc consistency. |
| Release guard baseline must update after public contract fixtures pass. | Adoption and changelog evidence. |

## Risks & Mitigations

| Risk | Severity | Likelihood | Mitigation |
|---|---|---:|---|
| Tests continue to assert internal enum identity and miss public drift. | High | Medium | Require public string fixtures for all changed failure codes. |
| Code adds aliases to keep old compact values working. | High | Medium | Zero BC guard rejects compatibility aliases and deprecated mappings. |
| Schema identity propagation leaks raw schema/output content. | High | Low | Restrict new fields to refs, versions, fingerprints, and safe statuses. |
| `prompt_json` implementation grows beyond V1 hardening scope. | Medium | Medium | Gate it as a bounded extraction mode with typed failure and fake-provider coverage only. |
| Async implementation duplicates router behavior. | Medium | Medium | Either choose sync-only or make async share the same terminal-outcome contract. |
| Router vocabulary change breaks config clarity. | Low | Medium | Pick one public knob and update docs/fixtures together. |

## Open Questions

| Question | Owner | Resolution |
|---|---|---|
| Is this remediation targeting full V1 PRD compliance now, including `prompt_json`? | Module maintainer | Yes. `prompt_json` is supported and covered by config/structured-output contract tests. |
| Should V1 expose async APIs, or should docs declare sync-only host-owned wrapping? | Module maintainer | Sync-only V1. Async wrappers are host-owned until a native async router is designed. |
| Should the public router knob be `protect_last_eligible` or `failover_reserve_ms`? | Runtime owner | `protect_last_eligible` is canonical; `failover_reserve_ms` is removed. |
| Are all PRD failure codes required immediately, or only codes reachable by current V1 surfaces? | Module maintainer | The public taxonomy includes the PRD code set; reachable behaviors are covered by contract tests. |

## Related Documents

- [PRD: LLM Endpoint Module](../prd/prd-260516-1321-llm-endpoint-module.md)
- [Base Design: LLM Endpoint Module](design-260516-1331-llm-endpoint-module.md)
- [Completed Base Plan](../plan/plan-260516-1331-llm-endpoint-module.md)
- Eval session: `eval/sessions/260516-1743-prd-design-compliance-audit/report.md`

## Revision Log

| Date | Change |
|---|---|
| 2026-05-16 | Initial remediation design created from post-implementation PRD compliance audit. |
