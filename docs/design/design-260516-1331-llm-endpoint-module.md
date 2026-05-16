---
id: "design-260516-1331-llm-endpoint-module"
title: "LLM Endpoint Module Technical Design"
type: design
status: draft
created: 2026-05-16
updated: 2026-05-16
parent: "index-design"
depends-on:
  - "prd-260516-1321-llm-endpoint-module"
superseded-by: ""
author: "agent"
tags: ["llm", "endpoint", "runtime-policy", "failover", "structured-output", "telemetry", "cross-repo"]
source: "docs/prd/prd-260516-1321-llm-endpoint-module.md"
---

# LLM Endpoint Module Technical Design

## Context & Goals

The PRD defines a standalone V1 LLM Endpoint Module consumed by multiple repositories. The module is not a provider SDK wrapper. It is the shared execution boundary where host applications express intent and the module owns provider execution safety.

Technical goals:

| ID | Goal | PRD Trace |
|---|---|---|
| TG1 | Define a stable module boundary for role + operation invocation, endpoint registry resolution, provider execution, typed results, typed failures, and redacted telemetry. | G1, G2, G3, Public Surface Contract |
| TG2 | Centralize runtime policy resolution so output budget, reasoning control, candidate budget, deadline, structured-output mode, retry, and last-candidate protection are validated together. | G4, Configuration Precedence |
| TG3 | Validate configuration, capabilities, schema contracts, secrets, and routing compatibility before live invocation where possible. | G5, Acceptance Criteria |
| TG4 | Preserve deadline and cancellation integrity across ordered pool failover and late provider responses. | G6, Async/Cancellation, Pool Router |
| TG5 | Emit comparable, redacted, request-correlated telemetry, attempt traces, smoke results, and debug replay artifacts across repos. | G7, Telemetry, Debug Replay |
| TG6 | Provide fake-provider and offline validation contracts so consumers can test upgrades without live credentials or provider calls. | G8, Smoke Gates |
| TG7 | Keep Nightfall extraction clean by requiring call sites to move to the canonical direct invocation contract, with no compatibility facade. | G9, Zero BC Migration |

## Non-Goals

| Non-goal | Technical Boundary |
|---|---|
| Prompt, persona, conversation, agent-planning, or domain workflow design | Host-owned product behavior; module sees messages and metadata as input payloads. |
| Provider SDK class hierarchy standardization | Provider-specific implementation is hidden behind adapter contracts. |
| Remote config storage or hot reload as a core assumption | The module owns schema and validation; hosts own loading and lifecycle. |
| Adaptive routing, cost-aware routing, or quality ranking | V1 routing is deterministic and policy-driven. |
| Multi-language client architecture | V1 proves one package contract first. |
| Legacy facade or compatibility adapter architecture | Zero BC prohibits compatibility shims, deprecated facade preservation, and dual API paths. |
| Executing tools or side effects from model output | Module returns typed data or typed failure only. |

## Backward Compatibility Policy

| Attribute | Value |
|---|---|
| Production status | Not in production as a standalone module contract. Existing repo-local call sites are outside this package boundary. |
| BC Level | None - Zero BC policy |
| Deprecation window | N/A |
| Migration ownership | Consumers move directly to the canonical API; the module does not preserve legacy facades. |
| Version sunset criteria | N/A until the standalone module enters production as a released public dependency. |

Design constraints:

| Constraint | Impact |
|---|---|
| Public API, config schema, telemetry schema, failure taxonomy, validation API, fake-provider API, and adapter extension API are clean-slate surfaces. | Breaking changes are allowed before production release; every current public surface still needs owner, version rule, and fixtures. |
| Compatibility mechanisms are prohibited. | No version routers, dual APIs, deprecated-field preservation, legacy facade adapters, or migration shims. |
| Nightfall-local env-var/provider tuple paths use Zero BC during extraction. | Consumers migrate by changing call sites, config, and tests rather than relying on module compatibility code. |

## System Context

| Actor / System | Relationship | Protocol / Boundary |
|---|---|---|
| Host application | Calls the module, supplies role, operation, messages, deadline, metadata, schema refs, secret refs, config, and telemetry sink. | In-process public API and host callbacks. |
| Module maintainer | Publishes public surfaces, Zero BC rules, contract tests, adapter extension contracts, and migration notes. | Package release and documentation contract. |
| Provider service / gateway | Executes model calls through provider-format adapters. | Provider adapter contract; raw provider payloads stay internal. |
| Secret source | Resolves credential refs at host discretion. | `resolve_secret(ref)` callback contract. |
| Schema source | Resolves schema material, validator, version, and fingerprint. | `resolve_schema(ref)` callback or equivalent registration contract. |
| Telemetry sink | Receives normalized events, metrics, traces, smoke results, and debug artifacts. | Redacted event envelope and artifact schema. |
| CI / offline validation | Validates config, policy, fake-provider behavior, and redaction without live provider calls. | Validation and smoke API. |
| Consumer test suite | Verifies upgrades through contract fixtures and fake providers. | Public conformance fixtures. |

## Component Architecture

| Component | Ownership | Responsibility |
|---|---|---|
| Public Invocation Facade | Module | Canonical sync/async entrypoint for role + operation + messages + deadline + optional schema and cancellation. |
| Registry & Config Validator | Module | Validates endpoint UIDs, roles, pools, provider formats, model families, capability refs, credential refs, schema refs, and config identity. |
| Runtime Policy Resolver | Module | Resolves effective runtime config, applies precedence, enforces provider hard limits, records provenance, and computes policy fingerprints. |
| Capability Profile Catalog | Module with maintainer-owned evidence | Stores provider-format x model-family facts and conservative unknown-family behavior. |
| Provider Adapter Layer | Module extension boundary | Converts normalized invocation plans into provider calls and returns normalized provider outcomes. |
| Secret Resolver Boundary | Host-owned implementation, module-owned contract | Resolves credential refs and returns redacted credential failures. |
| Schema Resolver & Validation Boundary | Host-owned schemas, module-owned contract | Resolves schema identities and validates structured output before success. |
| Deadline Pool Router | Module | Allocates candidate budgets, applies suppression, orders attempts, classifies retryable failures, and discards late successes. |
| Result & Failure Normalizer | Module | Produces typed success, plain text success, or typed failure with safe diagnostics and retryability. |
| Telemetry & Debug Artifact Emitter | Module contract, host sink | Emits event families, redacted attempt traces, token usage when available, and replay artifacts. |
| Role Health Service | Module | Computes deterministic role availability states without implicit live provider calls. |
| Offline Smoke & Fake Provider Harness | Module | Provides deterministic validation, failure simulation, and conformance fixtures. |
| Zero BC Guard | Module maintainer tooling | Blocks compatibility mechanisms and verifies public surfaces have owners, version rules, and fixtures. |
| Migration Extraction Guide | Module docs/tests | Documents direct-API migration steps and fixture requirements without shipping a compatibility facade. |

Primary ownership rule:

```text
Host owns product vocabulary and infrastructure choices.
Module owns validation, execution safety, normalization, and public contracts.
```

## Data Flow

### Startup / Validation Flow

```text
host config
  -> registry & config validator
  -> capability profile compatibility check
  -> operation policy validation
  -> schema ref shape validation
  -> secret ref shape validation
  -> config identity + validation report
  -> telemetry: llm.registry.validated / smoke result
```

Failure before activation uses typed validation errors and must not require network calls or real credential values.

### Invocation Flow

```text
host invoke(role, operation_ref, messages, deadline, schema_ref?, overrides?, metadata?, cancellation?)
  -> input validation
  -> registry role/pool resolution
  -> runtime policy resolution + provenance
  -> schema resolution when structured output is required
  -> candidate budget plan
  -> provider adapter attempt(s)
  -> structured extraction/validation or plain text normalization
  -> typed result or typed failure
  -> telemetry + attempt trace + optional debug artifact
```

### Failover Flow

```text
ordered candidate pool
  -> skip suppressed or ineligible candidates
  -> attempt candidate within allocated budget
  -> classify provider/local failure
  -> retryable availability failure: next eligible candidate if deadline remains
  -> non-retryable failure: fail fast
  -> pool exhaustion: typed failure with redacted attempt trace
```

### Cancellation / Late Response Flow

```text
caller cancellation or operation deadline
  -> stop starting new attempts
  -> mark active attempt canceled/timed out where possible
  -> reject late provider response as success
  -> emit cancellation/deadline/late-response telemetry
```

## Data Model

Logical entities:

| Entity | Description | Key Invariants |
|---|---|---|
| Module Version | Public package version and schema/taxonomy versions. | Version discovery requires no provider credentials or network calls. |
| Endpoint Entrypoint | Opaque UID plus provider format, model family, endpoint/deployment config, credential ref, and capability refs. | UID is opaque and never parsed for business semantics. |
| Role | Host-defined semantic alias resolving to one endpoint or ordered pool. | Role names are host vocabulary; pool membership validates before activation. |
| Endpoint Pool | Ordered candidate list with suppression and eligibility state. | Empty pools and duplicate UIDs fail validation. |
| Operation | Host-defined invocation pattern bound to runtime policy and optional schema contract. | Invocation requires an operation ref; no migration mode is active. |
| Operation Runtime Policy | Output budget, reasoning mode, candidate budget shape, last-candidate protection, retry rules, structured-output mode, and override rules. | Effective values must have provenance and respect hard constraints. |
| Effective Runtime Config | Immutable resolved runtime values plus provenance. | Cannot silently include values from env/secret refs as behavior overrides. |
| Capability Profile | Provider-format x model-family facts and evidence. | Unknown family fails closed or uses conservative capabilities. |
| Schema Contract | Stable schema name/version/fingerprint plus validator and extraction mode. | Structured success requires schema identity and validation. |
| Invocation Request | Role, operation, messages, deadline, schema ref, overrides, metadata, invocation ID, cancellation. | Messages validate before provider calls. |
| Endpoint Plan | Resolved role, policy, pool, candidate budgets, schema identity, and suppression state. | Plan must be reproducible for debug artifacts without secrets or raw payloads. |
| Attempt Trace | Redacted record of each candidate attempt, skip, timeout, or failure. | Contains no secrets, raw prompts, raw responses, or sensitive outputs. |
| Typed Result | Validated structured value or accepted plain text output. | Raw provider payload never becomes success directly. |
| Typed Failure | Code, retryability, safe diagnostics, correlation IDs, attempt trace ref, and remediation hint when safe. | Failure meaning is fixture-backed, but pre-production changes may replace it directly under Zero BC. |
| Telemetry Event | Redacted event envelope for validation, policy resolution, attempt, success, failure, smoke, and fake provider results. | Required fields are present by event family. |
| Role Health | Deterministic summary and reason list for role availability. | No implicit live call; multiple reasons may coexist. |
| Debug Replay Artifact | Redacted endpoint plan, policy provenance, capability profile, schema trace, attempt trace, failure, and fake-provider fixture when possible. | Reproducible without raw prompts, responses, or secrets. |
| Public Surface Baseline | Versioned manifest of public APIs, config schema, telemetry schema, failure taxonomy, fixture schemas, and adapter contracts. | Every surface has owner, version rule, Zero BC level, and positive/negative fixtures. |

## API & Contract Surface

### Direct Invocation Contract

Protocol: in-process public API.

Payload shape:

| Field | Required | Notes |
|---|---:|---|
| `role` | Yes | Host-defined role name. |
| `operation_ref` | Yes | Required for canonical invocation; no migration compatibility mode exists. |
| `messages` | Yes | Module validates structural shape only. |
| `deadline_ms` | Yes | Operation-wide wall-clock budget. |
| `schema_contract_ref` | Conditional | Required for structured-output operations. |
| `caller_overrides` | No | Accepted only when allowed by policy and capability. |
| `request_metadata` | No | Safe correlation and attribution fields only. |
| `operation_invocation_id` | No | Host-provided or module-generated. |
| `cancellation_token` | No | Sync and async APIs must preserve equivalent semantics. |

Result shape:

| Result | Meaning |
|---|---|
| Typed structured result | Schema contract resolved, output extracted, and validator accepted it. |
| Plain text result | Operation permits plain text and provider output is normalized. |
| Typed failure | Stable code, retryability, invocation ID, safe diagnostics, and redacted trace. |

### Registry / Validation Contract

| Operation | Contract |
|---|---|
| Validate config | Returns machine-readable pass/fail with path-specific errors. |
| Resolve role | Returns candidate UID or ordered pool with eligibility metadata. |
| Resolve operation policy | Returns effective runtime config and provenance. |
| Query role health | Returns deterministic summary state plus all applicable reasons. |
| Smoke offline | Runs config, capability, policy, telemetry, fake-provider, and contract checks without network or secrets. |
| Smoke live | Optional, explicit, uses production-equivalent registry path and redacted payloads. |

### Provider Adapter Contract

| Input | Output |
|---|---|
| Resolved candidate plan, safe messages payload, effective runtime config, deadline/candidate budget, schema mode, invocation ID, cancellation signal. | Normalized provider outcome: success payload, refusal, retryable availability failure, non-retryable failure, timeout, cancellation, token usage, and safe provider status. |

Adapters must not leak raw provider exceptions, headers, prompts, responses, or credential values into public result surfaces.

### Error Contract

Errors are normalized into public typed failure codes from the PRD taxonomy. Each failure includes a stable code, retryability flag, human-safe message, invocation ID, role/operation context when applicable, endpoint UID when applicable, policy fingerprint, elapsed time, and redacted attempt trace reference.

### Idempotency & Versioning

| Concern | Decision |
|---|---|
| Invocation idempotency | The module does not guarantee provider-side idempotency. It guarantees one terminal module outcome per operation invocation ID. |
| Late responses | A late provider response cannot overwrite a terminal timeout, cancellation, or failure. |
| Config versioning | `config_schema_version` accepts only the current clean-slate schema; no legacy loaders. |
| Telemetry versioning | Event families and required fields are versioned public surfaces. |
| Failure taxonomy versioning | Current codes are fixture-backed; pre-production changes may replace codes directly under Zero BC. |

### Config Lifecycle Contract

| Concern | Decision |
|---|---|
| Startup activation | A registry is active only after config, capability, policy, schema-ref shape, credential-ref shape, and telemetry redaction validation pass. |
| Runtime reload | Not a V1 core behavior; if a host needs reload, it must be an explicit host lifecycle operation that validates the full replacement registry before activation. |
| Config identity | Every active registry exposes `config_identity`; policy fingerprints and debug artifacts reference the active identity. |
| Failed replacement | A failed validation never partially replaces the active registry. |
| Rollback | Host rollback is version pinning or reactivation of a previously validated config identity, not a module-internal compatibility shim. |

## NFR & SLO Targets

Targets derive from PRD acceptance criteria and are stated as module-level obligations rather than provider guarantees.

| Target | SLO / Measurement | PRD Trace |
|---|---|---|
| Offline validation determinism | Same config and fixtures produce identical validation output and policy fingerprints. | AC3, AC4 |
| Startup safety | No live provider calls or credential values are required for offline validation. | Expected Behavior, Smoke Gates |
| Deadline integrity | 100% of module terminal outcomes respect caller-bound operation deadline as the upper bound for module-controlled work. | AC8, AC9 |
| Cancellation integrity | 100% of canceled invocations stop new attempts and never become late success. | AC9 |
| Failure normalization | 100% of module-owned failures map to documented typed failure codes. | AC10, Output & Errors |
| Telemetry completeness | Invocation, attempt, success, failure, pool exhaustion, deadline, smoke, and fake-provider events include required common fields. | AC11 |
| Redaction | Tests prove forbidden fields are absent from telemetry, failures, smoke output, and debug artifacts. | Security, AC11 |
| Fake-provider coverage | Required success, retryable, non-retryable, invalid output, cancellation, late response, and pool exhaustion scenarios are deterministic. | AC14 |
| Role health determinism | Role health uses registry, policy, suppression, smoke, and secret availability state without implicit live calls. | AC13 |
| Local planning latency | Registry, policy, schema-ref planning, and routing decisions are local bounded work; live provider and host callback time are accounted separately. | AC4, AC8 |
| Module availability boundary | Module-owned offline validation, planning, failure normalization, and telemetry envelope generation remain available without provider network access. | AC3, AC10, AC11 |
| Throughput isolation | The module keeps no cross-host mutable runtime state; host traffic volume and provider rate limits remain outside module-global state. | Assumptions, Capacity Estimates |

Per-component latency allocations are policy-derived:

| Component | Budget Rule |
|---|---|
| Registry and policy resolution | Must be bounded by local computation; no network dependency. |
| Secret resolution | Counts against invocation deadline when required for live call. |
| Schema resolution | Counts against planning budget and must complete before provider invocation for structured operations. |
| Provider attempt | Uses allocated candidate budget from operation runtime policy. |
| Fallback reserve | Preserved by budget allocator when configured. |

## Cross-Cutting Concerns

### Security & Redaction

| Area | Rule |
|---|---|
| Secrets | Secret values never enter telemetry, errors, cache keys, debug artifacts, smoke reports, or repr/debug strings. |
| Prompts and responses | Raw prompts/messages and raw provider responses are excluded by default. |
| Schema outputs | Treated as host-sensitive data; not emitted unless explicitly redacted and allowed. |
| Provider metadata | Only allowlisted safe fields may be emitted. |
| Debug artifacts | Must be useful through identities, fingerprints, traces, and fake fixtures, not raw data. |

### Observability

Required event families are `llm.registry.validated`, `llm.policy.resolved`, `llm.role.health`, `llm.pool.attempt`, `llm.success`, `llm.failure`, `llm.pool.exhausted`, `llm.deadline.exceeded`, `llm.endpoint.suppressed`, `llm.budget.violation`, `llm.smoke.result`, and `llm.fake_provider.result`.

Every invocation-related event must carry operation invocation ID, role, operation ref, endpoint UID when applicable, attempt trace ID, policy fingerprint, elapsed time, failure class when applicable, and redaction status.

### Testing & Conformance

| Layer | Required Proof |
|---|---|
| Config contract | Offline validation fixtures for valid and invalid configs. |
| Policy contract | Budget, reasoning, override, hard-cap, and provenance fixtures. |
| Adapter contract | Fake provider and adapter conformance fixtures. |
| Structured output | Extraction mode, refusal, malformed payload, duplicate terminal tool, wrong tool, and schema violation fixtures. |
| Router | Retryable failover, non-retryable fail-fast, suppression skip, no eligible candidate, pool exhaustion, and deadline reserve fixtures. |
| Redaction | Golden event/artifact fixtures proving forbidden fields are absent. |
| Migration extraction | Direct-API migration guide and consumer contract fixtures; no compatibility facade or facade-parity requirement. |

## Infrastructure Topology

V1 is an in-process library module, not a remote service.

```text
host process
  -> llm endpoint module
      -> host callbacks: secret resolver, schema resolver, telemetry sink
      -> provider services/gateways via adapters
      -> offline/fake provider harness for CI
```

Deployment responsibility remains with each host application. The module publishes package artifacts, Zero BC docs, fixtures, and examples; it does not own host CI/CD, logging vendor, secrets backend, or config backend.

## Security Model

| Boundary | Trust Rule |
|---|---|
| Host input | Role, operation, messages, overrides, metadata, schema refs, and deadlines are untrusted until validated. |
| Provider output | Raw output is untrusted; structured output requires extraction and validator acceptance. |
| Secrets | Host resolver is trusted to return credentials; module is responsible for never leaking returned values. |
| Telemetry sink | Receives only redacted envelopes and safe identities. |
| Fake fixtures | Must not depend on production prompts, user data, responses, or credentials. |
| Migration extraction | Has no runtime trust boundary; consumers migrate call sites to the direct API. |

## Migration & Rollback

Migration path:

| Step | Technical Action | Rollback Lever |
|---|---|---|
| 1 | Extract current endpoint behavior into standalone public contract and fixtures. | Keep consuming repos pinned to previous local package/commit. |
| 2 | Add host config, role/operation policies, schema refs, and secret resolver implementations per consumer. | Revert host dependency pin and config change. |
| 3 | Move call sites to canonical direct API. | Revert host dependency pin while call-site migration continues. |
| 4 | Enable offline validation and fake-provider conformance in consumer CI. | Block upgrade before runtime rollout. |
| 5 | Roll out production invocations by role/operation with policy fingerprint comparison and suppression controls. | Disable role/operation candidate or pin previous module version. |
| 6 | Remove Nightfall-local raw provider tuple paths after direct-API migration. | Roll back by pinning the previous host commit or package version. |

Rollback must never require compatibility shims inside module internals.

## Capacity Estimates

| Concern | V1 Estimate / Constraint |
|---|---|
| Consumer count | Designed for several repositories with independent role vocabularies and config files. |
| Runtime invocation volume | Bound by host traffic; module must avoid global mutable state that crosses hosts. |
| Provider fanout | One logical invocation may attempt multiple candidates, but only sequential deterministic failover in V1. |
| Telemetry volume | At least one policy event, one attempt event per candidate attempt/skip, and one terminal success/failure event per invocation. |
| Fixture scale | Fake-provider and offline validation should scale by config size and scenario count without network dependency. |

## Dependency Map

| Dependency | Direction | Required Reliability Assumption |
|---|---|---|
| Host config loader | Host -> Module | Provides config material before validation. |
| Secret resolver | Module -> Host | Available for live invocation; failures become typed credential failures. |
| Schema resolver | Module -> Host | Available before structured provider invocation; missing schema fails planning. |
| Provider services/gateways | Module -> External | Unreliable; failures normalized and routed only when retryable. |
| Telemetry sink | Module -> Host | Best effort emission should not leak data or corrupt invocation result. |
| Consumer CI | Host -> Module | Runs offline validation and fake-provider fixtures without credentials. |

## Trade-Off Analysis

| Option | Decision | Rationale |
|---|---|---|
| Thin provider wrapper vs policy-driven execution boundary | Choose policy-driven execution boundary. | PRD requires validation, deadline routing, structured-output enforcement, telemetry, and typed failures across repos. |
| Direct API only vs direct API plus bounded migration adapter | Choose direct API only. | Zero BC forbids compatibility facades; migration happens through call-site changes, fixtures, and version pin rollback. |
| Adaptive failover vs deterministic ordered pools | Choose deterministic ordered pools. | Incident reproducibility and cross-repo auditability matter more than optimization in V1. |
| Inline schemas everywhere vs host schema resolver | Choose host schema resolver as primary path. | Hosts own domain schemas; module owns identity, fingerprint, and validation boundary. |
| Live smoke by default vs offline-first validation | Choose offline-first with opt-in live smoke. | CI and local dev may lack credentials; live calls are operationally sensitive. |
| Treat suppression as terminal failure vs routing skip reason | Choose routing skip reason plus role-health state. | Suppressed primary should not fail an operation if fallback is eligible. |

## Sequencing Constraints

| Constraint | Blocks |
|---|---|
| Public contract names, failure taxonomy, telemetry event families, and config schema shape must be fixture-backed before component work proceeds. | Adapter, router, smoke, and consumer integration work. |
| Registry/config validation and capability profiles must exist before runtime policy compatibility and pool eligibility can be validated. | Policy resolver, role health, router planning. |
| Runtime policy resolver must exist before deadline allocator and provider adapters can execute consistent budgets. | Pool router and provider invocation. |
| Schema resolver contract must exist before structured-output validation and structured fake-provider cases. | Structured output pipeline and conformance fixtures. |
| Telemetry envelope and redaction rules must exist before provider attempts and debug artifacts can be accepted. | Router, adapters, smoke, debug replay. |
| Fake provider harness must exist before consumer contract tests can be trusted. | Migration hardening and broad adoption. |
| Direct invocation contract must be fixture-backed before host call-site migration starts. | Nightfall call-site migration. |
| Public surface baseline and Zero BC guard must exist before broad release automation can block unsafe changes. | Consumer contract test pack, changelog enforcement, and breaking-change review. |

## Risks & Mitigations

| Risk | Severity | Likelihood | Mitigation |
|---|---|---:|---|
| V1 scope expands into platform breadth. | High | Medium | Keep Core, Migration Hardening, and Operator Add-Ons explicit; defer non-V1 items. |
| Public surfaces accidentally include internals. | High | Medium | Document public/internal boundary and add compatibility checker for exported surfaces, config, telemetry, and failures. |
| Provider quirks bypass capability profiles. | High | Medium | Require evidence for capability claims and fail closed for unknown families. |
| Deadline and cancellation behavior differs between sync and async APIs. | High | Medium | Define equivalent terminal outcomes and include fake-provider cancellation/late-response fixtures. |
| Telemetry leaks sensitive prompts, responses, or secrets. | High | Low | Redaction-first envelope, forbidden-field fixture tests, and debug artifacts based on identities/fingerprints. |
| Legacy facade pressure creates hidden BC debt. | Medium | Medium | Prohibit migration adapters; require direct-API call-site migration and version-pin rollback only. |
| Host responsibilities remain ambiguous. | Medium | Medium | Surface host-owned roles, schemas, secrets, prompts, business validation, and rollout controls in docs and errors. |
| Offline validation passes but live provider behavior differs. | Medium | Medium | Separate offline proof from opt-in live smoke; record capability evidence and safe provider status. |
| Runtime config reload sneaks in as hidden mutable state. | Medium | Low | Exclude reload from V1 core; require full replacement validation and explicit host lifecycle if a current consumer needs it. |

## Open Questions

| Question | Owner | Design Impact |
|---|---|---|
| What exact package/distribution path will V1 use during extraction? | Module maintainer | Release, import boundary, and consumer pinning mechanics. |
| Which provider formats and model families are required for first consumer migration? | Consuming repo owners | Initial adapter and capability profile scope. |
| What exact sync/async cancellation representation is public: typed failure, raised exception, or API-style dependent? | Module maintainer | Invocation API contract. |
| What schema fingerprint format is canonical? | Module maintainer + host owners | Telemetry, smoke, debug, and compatibility fixtures. |
| Which token usage fields are safe and available across V1 providers? | Operators + security reviewer | Telemetry schema and cost attribution fields. |
| Does any first-wave consumer require runtime config reload in V1? | Module maintainer + consuming repo owners | If yes, reload must be explicit validated replacement; otherwise it stays non-V1. |

## Glossary

| Term | Meaning |
|---|---|
| Endpoint Entrypoint | One concrete model deployment configuration identified by an opaque UID. |
| Provider Format | Adapter boundary shaped by SDK, transport, auth, gateway, and request semantics. |
| Model Family | Capability class within a provider format. |
| Operation Runtime Policy | Validated bundle of output budget, reasoning, deadline, retries, failover, and structured-output behavior. |
| Effective Runtime Config | Immutable resolved runtime values plus provenance. |
| Candidate Budget | Per-attempt slice of the operation deadline. |
| Typed Failure | Normalized safe failure object with stable code and retryability. |
| Debug Replay Artifact | Redacted diagnostic package for reproducing or understanding a module outcome. |

## Related Documents

- [PRD: LLM Endpoint Module](../prd/prd-260516-1321-llm-endpoint-module.md)

## Revision Log

| Date | Change |
|---|---|
| 2026-05-16 | Tightened design traceability for execution planning: added compatibility guard, public surface baseline, config lifecycle contract, explicit availability/throughput NFR boundaries, runtime reload risk, and reload open question. |
| 2026-05-16 | Initial technical design from PRD V1 product contract. |
