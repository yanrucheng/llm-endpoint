---
id: "prd-260516-1321-llm-endpoint-module"
title: "LLM Endpoint Module - Standalone V1 Product Contract"
type: prd
status: draft
created: 2026-05-16
updated: 2026-05-16
parent: "index-prd"
depends-on: []
superseded-by: ""
author: "agent"
tags: ["llm", "endpoint", "reusable-module", "registry", "runtime-policy", "failover", "structured-output", "telemetry", "cross-repo", "v1"]
source: "/Users/chengyanru/repos/venture/lg/nightfall-ai/docs/external/external-260516-0500-llm-endpoint-module.md"
---

# LLM Endpoint Module - Standalone V1 Product Contract

## Context / Problem

The LLM endpoint code started as a Nightfall AI internal boundary for selecting providers, validating endpoint configuration, enforcing structured output, and making model calls observable. It is now used by Nightfall AI plus at least two additional repositories. That changes the product: the module is no longer a local helper. It is a standalone infrastructure dependency with real consumers, upgrade risk, operator expectations, and explicit Zero BC release discipline before production.

The reviewed direction is correct: the module should not be a thin wrapper around provider SDKs. It should be the shared model-execution boundary where host applications express intent and the module owns provider execution safety.

```text
role + operation + messages + schema? + deadline + metadata
  -> validated endpoint plan
  -> provider invocation with deadline-aware routing
  -> typed result or typed failure
```

The feedback from `eval/sessions/260516-1236-standalone-llm-endpoint-feedback/report.md`, `eval/sessions/260516-1245-llm-endpoint-module-feedback/report.md`, and `eval/sessions/260516-1301-llm-endpoint-v1-feedback/report.md` is also clear: the previous PRD was a good target contract, but too broad for first migration. V1 must be a smaller durable spine, not a platform big bang. This document therefore defines the standalone module's pragmatic V1 product contract: what must work now, what is explicitly not V1, what can land as V1 hardening/add-ons, and what behavior consuming repositories can rely on.

This document describes externally observable behavior, public surfaces, host responsibilities, acceptance criteria, errors, and handoff requirements for technical design. It does not prescribe internal class layout, implementation phases, provider SDK choices, storage backends, or release mechanics beyond what affects the public contract.

## Product Definition

The LLM Endpoint Module is a policy-driven model execution layer.

It maps application-level LLM operations to provider-specific, capability-validated, observable endpoint invocations with deadline-aware routing, structured-output enforcement when requested, redacted telemetry, and normalized failure handling.

The defining boundary is:

| Layer | Owned by module | Owned by host application |
|---|---|---|
| Intent machinery | Roles, operations, invocation contract, policy binding | Role names, operation names, product meaning |
| Endpoint identity | UID schema, registry validation, opaque identity semantics | Which concrete endpoints are configured |
| Runtime policy | Policy schema, precedence, validation, provenance | Operation-specific policy values and SLO choices |
| Provider execution | Adapter contract, capability profile, error normalization | Provider accounts, credentials, quota ownership |
| Structured output | Extraction mode, validation boundary, typed failure behavior | Domain schemas and business validation |
| Plain text output | Deadline, failure normalization, telemetry, redaction | Conversation semantics and response presentation |
| Failover | Deterministic ordered pool routing and retry classification | Pool membership and priority order |
| Observability | Event schema, redaction, attempt trace, request correlation | Log/metric/tracing sink and incident workflow |
| Migration | Direct-API extraction with no compatibility bridge | Call-site inventory and rollout sequencing |

The core principle is:

```text
The module owns provider execution safety.
The host owns product behavior.
```

## Product Goal

| ID | Goal | Priority |
|---|---|---|
| G1 | Provide one durable endpoint vocabulary across repos: endpoint UID, provider format, model family, capability profile, role, operation, runtime policy, schema contract identity, typed result, and typed failure | P0 |
| G2 | Let consumer code invoke models through role + operation, not raw provider/model/base-url/credential tuples | P0 |
| G3 | Return only validated typed results, plain text results, or normalized typed failures; raw provider payloads must never be returned as success | P0 |
| G4 | Co-design `max_tokens`, reasoning control, candidate budget, operation deadline, structured-output mode, and failover reserve inside one operation runtime policy | P0 |
| G5 | Validate provider capability, runtime policy, structured-output mode, credential references, schema contract identity, and routing compatibility before live invocation where possible | P0 |
| G6 | Honor caller-bound operation deadlines, cancellation, and local candidate timeouts without late-response corruption | P0 |
| G7 | Emit redacted, normalized telemetry with request correlation, attempt traces, token usage when available, and comparable failure classes across repos | P0 |
| G8 | Support deterministic offline validation and fake-provider conformance tests so consumers can upgrade without real provider calls | P0 |
| G9 | Migrate current Nightfall-needed ergonomics directly onto the canonical invocation API without preserving a compatibility facade | P0 |
| G10 | Allow each repo to define its own roles, operations, schemas, policy values, endpoint pools, and rollout controls without forking module code | P0 |
| G11 | Expose fixture-backed V1 public surfaces with explicit Zero BC rules before production release | P0 |
| G12 | Expose role health/status and safe debug replay artifacts for operators without leaking prompts, responses, or secrets | P1 |

## V1 Scope

V1 is the minimum durable endpoint boundary. It must be small enough to migrate safely and complete enough to stop endpoint behavior from forking across repos.

### V1 Core

V1 Core is the smallest independently useful standalone module surface. It must exist before any repo treats the module as a reusable dependency.

| Area | Requirement |
|---|---|
| Endpoint registry | UID registry, provider format, model family, capability profile, role mapping, config identity |
| Direct invocation API | Canonical role + operation + messages + schema? + deadline + metadata API |
| Runtime policy | Operation runtime policy, config precedence, effective runtime config, provenance, provider hard limits |
| Provider adapters | Provider-format adapter contract and current provider support needed by existing consumers |
| Capability profiles | Conservative provider-format x model-family facts, advanced capability evidence, unknown-family fail-closed behavior |
| Typed failures | Stable V1 failure codes, retryability flags, safe diagnostics, redacted attempt traces |
| Telemetry | Redacted event envelope, request correlation, operation invocation ID, policy fingerprint, schema fingerprint when relevant, token usage when available |
| Secret resolution | Minimal host-provided `resolve_secret(ref)` contract with redacted failure semantics |
| Offline validation | Config validation, capability compatibility, runtime-policy validity, redaction, telemetry shape |

### V1 Migration Hardening

V1 Migration Hardening is required to migrate Nightfall and the first consumer repos safely. These items may land after V1 Core, but they are still part of the V1 acceptance target before broad adoption.

| Area | Requirement |
|---|---|
| Structured output | Tool-call/schema/prompt-JSON extraction modes when configured, schema contract identity, validation handoff, typed invalid-payload/refusal failures |
| Plain text mode | Deadline, cancellation, telemetry, redaction, typed failures, and provider normalization without requiring fake schemas |
| Deadline failover | Deterministic ordered pools, retryable-only fallback, candidate budget allocator, hard local timeout, late-response discard |
| Async/cancellation | Documented sync/async behavior, caller cancellation semantics, deadline expiry semantics, no fallback after caller cancellation |
| Fake providers | Deterministic harness for rate limit, quota exhaustion, timeout, transient network, provider 5xx, refusal, malformed JSON, wrong tool, duplicate terminal tool, schema violation, late response, cancellation, and pool exhaustion |
| Migration extraction | Direct call-site migration from Nightfall-style role model handles to canonical invocation; no compatibility facade |
| Contract tests | Consumer-facing fixtures for config validation, failure taxonomy, telemetry redaction, structured output, and pool simulation |

### V1 Operator Add-Ons

V1 Operator Add-Ons are production-operability requirements. They should not block the first internal extraction if V1 Core and Migration Hardening are not yet stable, but they must be present before the module is treated as the cross-repo production default.

| Area | Requirement |
|---|---|
| Role health/status | Query roles as available, degraded, suppressed, uncertified, missing secrets, failing smoke, or fallback-only |
| Rollout controls | Host-controlled enable/disable by UID, force candidate for tests, canary by role/operation, policy fingerprint comparison |
| Debug replay artifacts | Redacted endpoint plan, effective runtime config, capability profile, schema transform trace, attempt trace, typed failure, fake-provider reproduction fixture |
| Token usage visibility | Capture provider token usage when available and emit safe attribution fields without cost-aware routing |

### Explicitly Not V1

| Item | Reason |
|---|---|
| Multi-language clients | V1 should prove the Python/module contract first |
| Remote config backends | Host-owned loaders are enough; the module only needs schema and validation contracts |
| Adaptive routing or adaptive candidate budgets | Deterministic behavior is required for reproducible incidents |
| Cost-aware routing | Basic token/cost telemetry is V1; routing by cost is not |
| Provider incident registry | Manual/TTL endpoint suppression is enough for V1 |
| Policy recommendation tooling | Probe evidence can be recorded, but policy choice remains host-owned config |
| Broad facade support | Zero BC excludes migration facades; direct API is the only invocation API |
| Full CLI as a product surface | Library validation APIs are sufficient unless CI requires CLI output immediately |
| Runtime config hot reload | Startup validation and config identity are V1; reload is only V1 if already required by a consumer |
| Live smoke as mandatory CI | Live smoke is opt-in; offline smoke is mandatory |
| Cross-repo governance automation | Changelog and compatibility discipline are V1; automated governance can wait |

## Persona / Target Users

| Persona | Context | Need | Product Promise |
|---|---|---|---|
| Consuming-app developer | Builds LLM-backed features in any dependent repo | Simple invocation, typed/plain result, no provider leakage | "I pass role, operation, messages, optional schema, deadline, and metadata; I get a result or typed failure." |
| Application owner | Owns repo-specific behavior and SLAs | Predictable migration and upgrade impact | "The module tells me what is public, what changed, and what my repo must configure." |
| Cross-repo operator | Runs services sharing providers, gateways, or quotas | Comparable telemetry, safe rollout, clear incident signals | "Endpoint failures look the same across services and can be traced safely." |
| Module maintainer | Evolves the standalone module across consumers | Small public surface, conformance tests, extension boundaries | "Core behavior is stable; non-core behavior is not accidentally public." |
| Capability extender | Adds provider format, model family, gateway, or structured-output mode | Stable adapter/profile contract and proof requirements | "I add capabilities with evidence and do not touch app code." |
| Eval/probe author | Measures latency, reasoning support, output reliability, and error modes | Evidence that maps to policies and capability profiles | "Probe results inform policy values without becoming hidden behavior." |
| Security/compliance reviewer | Reviews shared infra used by multiple products | Redaction, secret handling, output validation, auditability | "Secrets and raw payloads do not leak; untrusted model output is validated or rejected." |

## Non-Goals

| Non-goal | Rationale |
|---|---|
| Owning prompts, system messages, conversation strategy, agent planning, or persona text | These are application behavior, not endpoint execution behavior |
| Owning domain state such as game state, customer tickets, documents, profiles, or business entities | The module is domain-agnostic infrastructure |
| Owning domain schemas or business validators | The module can reference schema identity and run provided validators; schema meaning is host-owned |
| Providing an end-user model picker or model marketplace | Model selection is operator/application policy, not end-user UX |
| Ranking model quality or maintaining a universal benchmark leaderboard | The module records evidence; it does not declare global model truth |
| Choosing a secrets manager, config backend, telemetry vendor, HTTP client, or deployment platform | Host applications own infrastructure choices; the module owns contracts and validation behavior |
| Replacing LangChain, LangGraph, provider SDKs, or raw HTTP clients as a product requirement | Framework choice is an implementation concern behind stable module behavior |
| Hiding incidents with indefinite retries, automatic load balancing, quota smoothing, or silent model substitution | The module provides deterministic failover and explicit suppression, not opaque routing |
| Treating provider strict mode as sufficient application validation | Provider validation is helpful but never replaces module boundary validation and host business validation |
| Allowing UID parsing for business logic | UIDs are opaque identities; roles and operations carry semantics |
| Embedding Nightfall-specific role names, eval sessions, schemas, or latency assumptions as core defaults | Repo-specific vocabulary and evidence must be configuration or examples only |
| Executing model-emitted commands, tool side effects, URLs, SQL, file paths, approvals, or external actions | The module returns data; authorization and side effects belong to the host app |
| Guaranteeing provider availability, latency, cost, or output quality beyond configured policy and provider behavior | The module can route, validate, observe, and fail clearly; it cannot control provider service quality |

## Scope

| In Scope | Out of Scope |
|---|---|
| Versioned configuration schema: endpoints, roles, operation policies, failover policies, capability profiles, schema-output modes | Concrete storage backend for configuration |
| Opaque endpoint UID registry and deterministic role-to-pool resolution | Business-specific role vocabulary shipped in module core |
| Operation runtime policy resolution with precedence and provenance | Prompt design or application operation semantics |
| Provider format adapters and model-family capability profiles as extension boundaries | Public commitment to any specific SDK class hierarchy |
| Secret resolver interface and redacted credential failures | Owning the host's secret manager |
| Structured-output extraction, validation handoff, refusal handling, retry limit, and typed failure normalization | Authoring per-feature schemas or business validators |
| Plain-text invocation mode with deadlines, failures, and telemetry | Conversation UX and response rendering |
| Deadline-aware ordered pool routing and retryable failure classification | Load balancing, cost optimization, or autonomous model selection |
| Manual/TTL endpoint suppression and force-candidate testing controls | Hidden adaptive routing or silent role remapping |
| Redacted telemetry events, request correlation, attempt traces, token usage when available, and smoke reports | Raw prompt/response logging, credential logging, or vendor-specific dashboard coupling |
| Offline validation, fake provider harness, and opt-in live smoke using production-equivalent registry paths | Mandatory live calls in CI or local development |
| V1 public API definition, Zero BC release rules, direct-migration checks, and contract tests | Permanent compatibility for legacy construction helpers |

## Assumptions

| Assumption | Impact |
|---|---|
| The module already has three or more real repository consumers | Public-surface ownership, fixtures, changelog evidence, and direct migration notes are required even under Zero BC |
| Consumers can migrate toward role + operation invocation | Raw provider tuple construction is not a permanent public API |
| Different repos may share providers, gateways, and quotas | Telemetry, token usage, and failure classes must be normalized across repos |
| Provider behavior differs by gateway and model family even when SDK shape looks similar | Provider format and model family remain separate concepts |
| Local development and CI may not have provider credentials | Offline validation and fake providers must be first-class |
| Each consumer owns its domain schema and business validation | The module validates transport/structure and hands off to caller-provided validators |
| Repo-local eval evidence can conflict across consumers | Evidence informs policy values but must not become hidden module behavior |
| Nightfall currently needs migration ergonomics | Direct-migration readiness checks are V1; compatibility adapters are prohibited |
| Streaming behavior is product-sensitive | V1 must explicitly exclude streaming from the direct API unless a future Zero BC replacement adds it |

## Terminology

| Term | Definition |
|---|---|
| Module | The standalone LLM Endpoint package/repo consumed by multiple applications |
| Host application | A repo/service that installs or vendors the module and invokes LLM operations through it |
| Endpoint entrypoint | One concrete model deployment configuration: UID, provider format, model/deployment, credential reference, endpoint URL/config |
| UID | Stable opaque endpoint identity safe for telemetry; never parsed for semantics |
| Provider format | Adapter boundary defined by SDK/transport/auth/gateway behavior |
| Model family | Capability class within a provider format |
| Capability profile | Provider-format x model-family facts: required fields, allowed knobs, structured-output support, reasoning modes, streaming support, output hard cap, caveats, evidence |
| Role | Host-defined semantic alias resolving to one UID or an ordered endpoint pool |
| Operation | Host-defined named invocation pattern bound to a runtime policy and optional schema contract |
| Operation runtime policy | Validated bundle of output budget, reasoning mode, candidate budget shape, failover reserve, structured-output mode, retry policy, and override rules |
| Effective runtime config | Immutable resolved runtime values plus provenance for each value |
| Schema contract identity | Stable schema name/version/fingerprint used in validation, smoke, telemetry, and debug artifacts |
| Operation deadline | Caller-bound wall-clock budget for one logical invocation, including failover attempts |
| Candidate budget | Per-attempt slice of the operation deadline allocated by the operation runtime policy |
| Endpoint pool | Ordered candidate list for a role with deterministic failover rules |
| Typed result | Validated value accepted by the schema contract, or a plain text result accepted by a plain-text operation |
| Typed failure | Normalized module failure outcome safe for application handling and telemetry |
| Operation invocation ID | Host-provided or module-generated request correlation ID spanning attempts, telemetry, failures, and debug artifacts |
| Attempt trace | Redacted per-candidate execution record for diagnostics |
| Fake provider | Deterministic provider harness used for conformance, failure, timeout, and fallback tests |
| Role health | Queryable status summarizing whether a role is available, degraded, suppressed, uncertified, missing secrets, failing smoke, or fallback-only |
| Public API | Names, types, config schema, error codes, telemetry fields, validation APIs, direct-migration checks, and documented CLI behavior governed by Zero BC policy |
| Internal | Implementation detail that may change without compatibility guarantees |

## Product Principles

| Principle | Requirement |
|---|---|
| Intent in, provider details out | Caller expresses role + operation + messages + schema? + deadline; provider construction stays behind the module |
| V1 spine over platform breadth | Build the durable execution path first; do not force every platform feature into initial migration |
| Validate early, fail closed | Invalid configs, unsupported knobs, incompatible capabilities, unsafe schemas, and missing secrets fail before live calls where possible |
| Runtime budgets are one contract | `max_tokens`, reasoning, timeout, structured-output mode, retry policy, and failover reserve must be resolved together |
| Structured output is a trust boundary | No raw provider payload becomes structured success without extraction and validation |
| Plain text is first-class | Conversational calls still receive deadlines, failures, telemetry, and redaction without fake schemas |
| Domain-agnostic core | The module ships machinery, not consumer vocabulary, prompts, schemas, eval truth, or business behavior |
| Deterministic failover | Candidate order is explicit; fallback happens only for retryable availability failures |
| Explicit suppression only | A known-bad endpoint can be manually or TTL-suppressed, but no silent role remapping or hidden adaptive routing is allowed |
| Deadline integrity | The module never silently extends the host-provided operation deadline |
| Cancellation integrity | Caller cancellation stops new attempts and cannot later become success through a late provider response |
| Redaction by default | Secrets, raw prompts, raw responses, and sensitive payloads are excluded from logs, telemetry, errors, smoke output, and cache keys |
| Evidence is data, not code | Probe results can justify capability claims and policy values but must not mutate behavior implicitly |
| Public API discipline | Anything shown to consumers is either explicitly public and versioned or explicitly internal |
| Operational truth over fake success | Exhausted pools, refusals, invalid payloads, and deadline failures return typed failures; no synthetic success payloads |

## Backward Compatibility Policy

| Attribute | Policy |
|---|---|
| Production API status | Not established for the standalone package; current repo-local call sites are outside this package boundary |
| Versioning | Current public surfaces carry explicit schema/taxonomy versions for fixture identity, not BC coexistence |
| Breaking changes | Allowed before production release; no deprecation window, aliases, dual APIs, or compatibility shims |
| Config schema | Uses `config_schema_version`; loaders accept only the current clean-slate schema |
| Telemetry schema | Current event schema is fixture-backed; pre-production renames/removals may replace it directly |
| Error codes | Current codes are fixture-backed; pre-production removals or meaning changes may replace them directly |
| Provider format identifiers | Current identifiers are fixture-backed; pre-production renames do not require aliases |
| Capability profiles | Capability semantics may be corrected or replaced directly before production release |
| Facade APIs | No facade APIs are shipped; direct invocation is the only public invocation contract |
| Migration adapter | Prohibited as BC debt; migration is call-site change plus version-pin rollback |
| Internal layout | Free to change without notice if public behavior remains stable |

Requirements:

1. Every consuming repo must depend on a published module version or pinned commit with a direct-API migration plan; local forks are not an intended extension path.
2. Every behavior-affecting release must include a changelog entry naming affected public surfaces.
3. Every breaking release before production must label the changed public surfaces and required consumer edits.
4. Unknown construction keys, unsupported runtime knobs, and unknown config fields must fail closed unless an extension point explicitly allows them.
5. Security-driven tightening may replace unsafe behavior immediately; the changelog must label it as a safety correction.
6. Nightfall-local migration uses zero backward compatibility for old internal env-var/provider tuple paths and does not create standalone module BC obligations.

## Public Surface Contract

The module's V1 public surface includes only the following categories:

| Surface | Public commitment |
|---|---|
| Configuration schema | Versioned field names, validation rules, identity rules, precedence rules, extension points |
| Direct invocation API | Input contract: role, operation, messages, optional schema, deadline, overrides, metadata, cancellation |
| Result API | Typed success, typed failure, attempt trace, elapsed time, effective runtime config provenance |
| Registry API | Resolve role, UID, operation policy, capability profile, effective runtime config, role health |
| Validation/smoke API | Offline validation and opt-in live smoke with machine-readable results |
| Fake provider API | Deterministic provider harness and fixtures for conformance tests |
| Failure taxonomy | Stable error codes, categories, retryability flags, and safe diagnostics |
| Telemetry schema | Event names, required fields, redaction rules, request correlation, token usage when available |
| Secret resolver interface | Minimal host callback contract and redacted credential-failure behavior |
| Schema resolver interface | Host callback or registration contract for schema material, validator, version, and fingerprint |
| Provider adapter extension API | Minimum contract for adding provider formats and model families |
| Migration extraction docs/tests | Direct-API migration steps and fixtures for current Nightfall-needed call-site changes |

Everything else is internal unless explicitly documented as public.

## Migration Extraction Contract

Nightfall migration reduces risk through explicit call-site changes, fixture coverage, and version-pin rollback. V1 does not preserve legacy ergonomics through a module compatibility facade.

| Legacy surface | V1 stance |
|---|---|
| Role-based model lookup | Replace with canonical role + operation invocation |
| Pool-aware chat model handle | Replace with registry-backed endpoint pools and explicit operation policy |
| Structured invoke helper | Replace with schema contract refs and canonical structured invocation |
| LangGraph compatibility | Host-owned integration around the direct API; not a module facade |
| Raw provider tuple construction | Not preserved; callers must not construct provider/model/base-url/credential tuples |
| Old env-var factory semantics | Config-source compatibility only; not a public invocation API |

Migration proof is consumer fixture parity against direct API outcomes, not facade behavior preservation.

## Host Application Responsibilities

| Responsibility | Requirement |
|---|---|
| Role vocabulary | Define role names meaningful to the host domain |
| Operation vocabulary | Define operation refs and bind them to runtime policies |
| Schema contracts | Provide schema names, versions/fingerprints, validators, and `resolve_schema(ref)` or equivalent registration |
| Prompt/messages | Provide messages, system instructions, tool descriptions, and conversation context |
| Credentials | Provide credential references and implement the `resolve_secret(ref)` mechanism |
| Provider catalog choices | Decide which endpoints are configured and in which priority order |
| SLOs/deadlines | Provide operation deadlines aligned with host UX/API contracts |
| Business validation | Validate typed output against domain policy after module structural validation |
| Side effects | Authorize and execute any tool effects outside the module |
| Rollout control | Choose canaries, endpoint suppression, force-candidate tests, and policy rollouts |
| Telemetry sink | Route normalized events into logs, metrics, traces, or incident systems |
| Version upgrades | Pin, test, and roll out module versions according to host release policy |

The module must make these responsibilities explicit in errors, docs, examples, and conformance tests so consumers do not confuse module guarantees with application guarantees.

## Configuration Precedence

Every effective runtime value must expose provenance. V1 separates behavior sources from resolution mechanisms so environment references and secret references cannot silently become behavior overrides.

| Category | Contents | Rule |
|---|---|---|
| Hard constraints | Provider hard limits and capability profile restrictions | Absolute safety limits; cannot be overridden upward or bypassed |
| Defaults | Package safe defaults | Minimal safe defaults only; never business-specific |
| Host configuration | Entrypoints, roles, operation policies, failover policies, schema-output modes | Primary source for production behavior |
| Component defaults | Narrow host component defaults | Allowed only when the operation policy permits them |
| Caller overrides | Explicitly allowed runtime knobs | Always provenance-tracked and bounded by policy/capability limits |
| Test overrides | Fake-provider or explicit test mode values | Forbidden in production plans unless the host marks the invocation as test-only |
| Resolution mechanisms | Environment refs, secret refs, schema refs | Resolve values or materials; do not override behavior silently |

If two behavior sources conflict, the stricter safety constraint wins. If provenance cannot explain the winning value, validation fails.

## Expected Behavior

### 1. Installation And Version Discovery

**Trigger:** A host application installs, imports, or initializes the module.

| Consumer / system action | Expected result |
|---|---|
| Host imports the public package | Public API is available without provider credentials or network calls |
| Host asks for module version | Module returns semantic version, config schema version, telemetry schema version, and failure taxonomy version |
| Host uses unsupported Python/runtime version | Initialization or packaging metadata fails clearly with `llm.module.unsupported_version` |
| Host imports internal modules | Behavior is unsupported; docs mark internal imports as unstable |
| Host installs optional adapter extras | Only the requested adapter dependencies are required |
| Host only wants validation in CI | Validation runs without constructing live provider clients |

### 2. Configuration And Registry

**Trigger:** A host starts, validates config, or resolves role/UID/policy.

| Consumer / system action | Expected result |
|---|---|
| Operator provides endpoint config | Module validates `config_version`, UIDs, roles, provider formats, model families, credential refs, policy refs, capability refs, schema contract refs, and config identity |
| App requests role `R` | Registry resolves `R` to one candidate or an ordered endpoint pool |
| App requests unknown role | Fails with `llm.endpoint.unknown_role` and safe alternatives when available |
| App requests unknown UID | Fails with `llm.endpoint.unknown_entrypoint` |
| Config maps a role to a missing UID | Validation fails before registry becomes active |
| Config includes unsupported provider format | Validation fails with `llm.endpoint.unsupported_provider_format` |
| Config includes unknown construction keys | Validation fails unless explicitly allowed by provider format/capability profile |
| Config maps a role pool to an incompatible operation policy | Validation fails with `llm.policy.capability_mismatch` |
| Credential ref is absent for a live-required endpoint | Live validation/invocation fails with `llm.config.credential_unavailable` and no secret leakage |

**Edge behavior:**

| Case | Expected behavior |
|---|---|
| Two roles point to the same UID | Valid; telemetry records requested role and resolved UID |
| Role pool is empty or has duplicate UIDs | Validation fails |
| Config is identity-identical | Registry identity remains stable; cache reuse is allowed |
| Credential value is missing but only offline validation is requested | Offline validation checks reference shape, not secret availability |
| Role has a suppressed primary endpoint | Role health reports degraded/fallback-only; routing skips suppressed candidates according to suppression policy |

### 3. Operation Runtime Policy

**Trigger:** A consumer invokes a role with `operation_ref`, or validates operation policies.

| Consumer / system action | Expected result |
|---|---|
| App passes `operation_ref` | Module resolves output budget, reasoning mode, candidate budget, structured-output mode, retry policy, override rules, and failover reserve |
| Caller provides allowed override | Effective runtime config records caller value and provenance |
| Caller override conflicts with hard cap | Hard cap wins; provenance records requested value and clamp/rejection |
| Policy `max_tokens` exceeds candidate hard cap | Validation fails with `llm.policy.output_budget_exceeds_hard_cap` |
| Policy reasoning mode is unsupported by candidate | Candidate is skipped or policy validation fails according to declared fallback behavior |
| Policy declares per-family or per-UID budget | Router uses matching candidate budget and validates floors/ceilings |
| Policy cannot allocate fallback reserve under deadline | Planning fails with `llm.policy.candidate_budget_unallocatable` |
| Policy omits production deadline behavior | Validation fails; unbounded production invocations are not allowed |
| Policy references schema contract identity | Telemetry, smoke, and debug artifacts include schema name/version/fingerprint |

**Edge behavior:**

| Case | Expected behavior |
|---|---|
| App invokes without `operation_ref` | Validation fails with `llm.policy.operation_ref_required`; no migration compatibility mode exists |
| Operation policy is unused by any role | Validation warns unless strict-unused mode is enabled |
| Policy references unknown model family | Validation fails unless conservative unknown-family behavior is explicitly selected |
| Host retunes policy values | No code change is required; validation and telemetry expose the new policy fingerprint |
| Structured-output retry rules are configured | Retry budget location and count are explicit in operation policy, not hidden in call sites |

### 4. Schema Contract Resolution

**Trigger:** A structured-output operation references `schema_contract_ref`.

V1 primary path is a host resolver. The module calls a host-provided `resolve_schema(ref)` contract and receives schema material, validator, schema version, and fingerprint. Inline schemas are allowed only for tests, examples, or explicit host opt-in. Pre-registration at initialization is allowed as an implementation style if it preserves the same behavior.

| Consumer / system action | Expected result |
|---|---|
| Operation references known schema | Resolver returns schema material, validator, version, and fingerprint |
| Operation references unknown schema | Planning fails with `llm.schema.unknown_contract` before provider invocation |
| Resolver returns schema without fingerprint | Validation fails; structured operations require stable schema identity |
| Caller passes inline schema in test mode | Module accepts it when paired with explicit `schema_contract_ref` and fingerprint |
| Schema fingerprint changes | Telemetry, smoke, and debug artifacts expose the new fingerprint |
| Schema validation succeeds structurally | Module returns typed result, then host remains responsible for business validation |

### 5. Invocation API And Result Contract

**Trigger:** Host code executes an LLM operation.

Canonical V1 invocation shape:

```text
invoke(
  role,
  operation_ref,
  messages,
  deadline_ms,
  schema_contract_ref?,
  caller_overrides?,
  request_metadata?,
  operation_invocation_id?,
  cancellation_token?
) -> TypedResult | PlainTextResult | TypedFailure
```

| Consumer / system action | Expected result |
|---|---|
| App invokes valid structured operation | Module resolves plan, invokes candidate(s), validates output, and returns typed result or typed failure |
| App invokes valid plain-text operation | Module applies deadline, policy, provider normalization, telemetry, and returns plain text result or typed failure |
| App supplies malformed messages | Fails before provider call with `llm.input.invalid_messages` |
| App supplies no schema where operation requires structured output | Fails before provider call with `llm.schema.missing_contract` |
| Provider returns usable structured output | Module validates and returns typed result |
| Provider returns text where structured output is required | Module applies bounded retry/fallback extraction or returns `llm.structured_output.invalid_payload` |
| Provider returns refusal | Module returns `llm.structured_output.refusal`; refusal is not success |
| Provider succeeds after fallback | Result includes winning endpoint UID and redacted attempt trace |
| All candidates fail | Module returns `llm.pool.exhausted` with safe attempt trace |
| Caller supplies operation invocation ID | All attempts, failures, telemetry, and debug artifacts carry the same ID |

### 6. Async, Cancellation, And Late Responses

**Trigger:** Caller cancels, deadline expires, candidate times out, or provider returns after local timeout.

| Case | Expected behavior |
|---|---|
| Caller cancellation before provider call | No candidate starts; module returns/raises documented cancellation outcome |
| Caller cancellation during candidate attempt | Module stops starting new candidates and marks in-flight attempt canceled where possible |
| Caller cancellation occurs before fallback | Fallback is not allowed after caller cancellation |
| Operation deadline expires | Module returns `llm.deadline.exceeded`; no later response can become success |
| Candidate exceeds allocated budget | Candidate is classified as `llm.invocation.local_candidate_timeout`; fallback may proceed if retryable and deadline remains |
| Provider response arrives after local timeout | Late response is discarded as success; telemetry may record redacted late-response diagnostic |
| Async API and sync API differ mechanically | Difference is documented; failure codes, telemetry, and cancellation semantics remain equivalent |

### 7. Pool Router, Suppression, And Rollout Controls

**Trigger:** An operation resolves to an ordered endpoint pool.

| Behavior | Expected result |
|---|---|
| Caller binds operation deadline `D` | Router treats `D` as authoritative and never silently extends it |
| Router starts candidate attempt | Candidate receives allocated budget derived from policy and remaining deadline |
| Provider returns retryable availability failure | Router falls through in configured order |
| Provider returns non-retryable error | Router fails fast and does not try later candidates |
| Pool exhausts | Module returns `llm.pool.exhausted` with attempt trace and no synthetic payload |
| `protect_last_eligible` is enabled | Router preserves enough budget to attempt the last eligible candidate |
| Host manually suppresses UID | Candidate is skipped with reason `endpoint_suppressed` until suppression is removed or TTL expires |
| Host forces a candidate in test mode | Router uses forced candidate and records the override in telemetry |
| Host canaries a role/operation | Policy fingerprint and endpoint plan identify canary traffic |
| Suppressed candidate is followed by healthy fallback | Operation succeeds; attempt trace records the suppressed candidate as skipped |
| Every candidate is suppressed or ineligible | Module returns `llm.pool.no_eligible_candidate` or `llm.pool.exhausted` according to the public failure taxonomy |

Retryable failures are limited to a closed taxonomy such as rate limit, quota/resource exhaustion, transient network, provider 5xx, and local candidate timeout. Credential, schema, validation, malformed input, unsupported capability, and policy errors are not retryable by default.

Suppression is primarily a routing reason and role-health state, not necessarily the final invocation failure. A suppressed primary should not make an operation fail if a later eligible candidate succeeds.

### 8. Role Health Semantics

**Trigger:** Operator or host code asks whether a role can serve traffic.

Role health must be deterministic. It is not a model-quality score and must not hide routing decisions.

| State | Deterministic input |
|---|---|
| `available` | At least one eligible candidate validates, is not suppressed, and has required offline proof |
| `degraded` | Primary candidate is unavailable, invalid, suppressed, missing secret, or failing smoke, but at least one fallback is eligible |
| `fallback_only` | Only non-primary candidates are eligible |
| `missing_secret` | Live invocation cannot resolve a required secret ref for at least one required candidate |
| `failing_smoke` | Required offline smoke fails for role, policy, schema, adapter, or telemetry shape |
| `uncertified` | Capability evidence or required smoke certification is missing |
| `suppressed` | One or more candidates are manually/TTL suppressed |
| `unavailable` | No candidate is eligible to serve the role |

If multiple states apply, the role-health response must include all applicable reasons plus a deterministic summary state. It must not perform a live provider call unless the host explicitly requests live smoke.

### 9. Provider Format And Capability Profiles

**Trigger:** A registry plan constructs or validates a provider candidate.

| Difference | Expected boundary |
|---|---|
| Different SDK, auth, transport, request protocol, deployment semantics, or gateway behavior | New provider format adapter |
| Same SDK but different structured-output support, reasoning knobs, streaming behavior, schema dialect, or token hard cap | New or updated model-family capability profile |
| Same model family but different endpoint URL, credential ref, deployment name, quota tier, or timeout default | New endpoint entrypoint config |
| Business preference such as cheap, judge, writer, agentic, fast, accurate | Host-defined role and operation policy |

Unknown provider formats fail closed. Unknown model families must use conservative capabilities and cannot claim tool calling, strict schema, streaming, reasoning control, or high token limits without explicit capability evidence.

### 10. Structured Output And Plain Text

| Need | V1 behavior | Module rule |
|---|---|---|
| Cross-provider typed payload | Forced single tool call where supported | Default for structured output when capability profile allows it |
| Model chooses one of several actions | Multiple tools with explicit action identity | Tool name and arguments are validated before success |
| Provider lacks tool calling | Prompt-instructed JSON with bounded validation retry | Must be capability-declared and lower confidence |
| Provider supports strict schema response | Schema response mode | Only allowed when capability profile proves support |
| Provider emits refusal | Typed refusal failure | Refusal never becomes empty success |
| Provider emits partial or extra fields | Schema validation determines accept/reject; extras follow schema policy |
| Operation expects plain text | Plain text result allowed | Still uses deadline, policy, telemetry, redaction, and typed failures |

The module validates structure. The host application remains responsible for domain/business validation after typed structure is accepted.

### 11. Streaming Boundary

V1 must not leave streaming ambiguous.

| Mode | V1 stance |
|---|---|
| Structured-output streaming | Not part of the V1 success contract |
| Plain visible-text streaming | Host-owned outside the module; the V1 direct API is non-streaming |
| Progress events | Host-owned UX; module telemetry must not be treated as user-visible progress |
| Partial output validation | Not success until final output passes the operation's result contract |
| Provider stream failure | Normalized into typed failure with redacted attempt trace |

### 12. Telemetry, Token Accounting, And Diagnostics

**Trigger:** Any config validation, policy resolution, invocation, fallback, smoke gate, suppression, or failure.

Required event families:

- `llm.registry.validated`
- `llm.policy.resolved`
- `llm.role.health`
- `llm.pool.attempt`
- `llm.success`
- `llm.failure`
- `llm.pool.exhausted`
- `llm.deadline.exceeded`
- `llm.endpoint.suppressed`
- `llm.budget.violation`
- `llm.smoke.result`
- `llm.fake_provider.result`

Required common fields:

| Field | Requirement |
|---|---|
| `module_version` | Present on every event |
| `config_version` and `config_identity` | Present when config is involved |
| `operation_invocation_id` | Present for invocation, attempt, success, failure, and debug events |
| `role` and `operation_ref` | Present when invocation/policy is involved |
| `endpoint_uid` | Present when a candidate is involved |
| `attempt_trace_id` | Present for invocation attempt correlation |
| `schema_contract_ref` and `schema_fingerprint` | Present when structured output is involved |
| `policy_fingerprint` | Present for policy resolution and invocation |
| `failure_class` | Present for failures |
| `elapsed_ms` | Present for invocation and smoke events |
| `token_usage` | Present when provider returns it; omitted or marked unavailable otherwise |
| `cost_attribution` | Safe operation/endpoint tags only; no cost-aware routing implied |
| `effective_runtime_config_provenance` | Present for policy resolution and invocation diagnostics |
| `redaction_status` | Indicates that payload redaction rules were applied |

Forbidden telemetry content:

- Raw API keys, tokens, or credential values.
- Raw prompts or full conversation messages by default.
- Raw provider responses by default.
- Unredacted tool arguments or schema outputs that may contain user/business data.
- Provider request headers except safe allowlisted metadata.

### 13. Smoke Gates And Contract Tests

| Gate | Mode | Required | Expected result |
|---|---|---|---|
| Config schema validity | Offline | Yes | Machine-readable pass/fail with path-specific errors |
| Endpoint registry consistency | Offline | Yes | UIDs, roles, provider formats, model families, credential refs, and config identity validate |
| Capability compatibility | Offline | Yes | Role pool x operation policy x candidate capability profiles are compatible |
| Runtime policy validity | Offline | Yes | Output budget, reasoning mode, candidate budget, failover reserve, override rules validate |
| Structured-output transform smoke | Offline | Yes | Tool-call/schema/prompt-JSON transformations validate without provider calls |
| Plain-text operation smoke | Offline | Yes | Plain-text operations validate without fake schemas |
| Candidate budget allocator simulation | Offline | Yes | Example deadlines prove candidates can be allocated or fail with typed reason |
| Telemetry redaction smoke | Offline | Yes | Events and failure payloads prove forbidden fields are absent |
| Fake-provider conformance | Offline | Yes | Deterministic failure/success scenarios produce expected result, failure, telemetry, and attempt trace |
| Direct-API parity | Offline | Yes | Consumer fixtures prove migrated call sites match expected direct API outcomes |
| Live invocation smoke | Online opt-in | Conditional | Uses production-equivalent registry path and returns redacted result |

Offline gates must run without network access and without real credential values.

### 14. Debug Replay Artifacts

**Trigger:** Invocation failure, pool exhaustion, deadline expiry, smoke failure, or operator-requested diagnosis.

A safe debug artifact includes:

- Operation invocation ID.
- Redacted endpoint plan.
- Role and operation ref.
- Policy fingerprint and effective runtime config provenance.
- Capability profile selected for each candidate.
- Schema contract ref and fingerprint when applicable.
- Structured-output transform trace when applicable.
- Attempt trace with safe provider status/code.
- Typed failure payload.
- Fake-provider reproduction fixture when deterministic reproduction is possible.

It must not include raw prompts, raw responses, secrets, unredacted tool args, or provider headers.

## Acceptance Criteria

1. A consuming repo can integrate V1 by installing/pinning the module, authoring config, implementing secret resolution, and invoking one public direct API with role + operation + messages + deadline.
2. Consumer feature code does not construct provider SDK clients for module-owned calls.
3. Offline validation runs in CI without network access or real credentials.
4. Validation rejects unknown roles, unknown UIDs, unsupported provider formats, unsupported runtime knobs, capability mismatches, invalid schema-output modes, missing required schema contracts, output budgets above hard caps, unsupported reasoning modes, and unallocatable candidate budgets before live calls.
5. Every invocation uses an operation runtime policy; no migration compatibility mode exists.
6. Plain-text operations are supported without forcing fake structured schemas.
7. Structured-output operations return validated typed values or typed failures; raw provider payloads are never success values.
8. The pool router never exceeds the caller-bound operation deadline and never silently retries non-retryable failures.
9. Caller cancellation stops new attempts and cannot later become success through a late provider response.
10. Every failure returns or raises a normalized typed failure with stable code, retryability semantics, operation invocation ID, redacted attempt trace, and safe diagnostics.
11. Telemetry from all consuming repos uses the same event names, required fields, failure classes, request correlation, and redaction rules.
12. Token usage is captured when providers return it, with safe operation/endpoint attribution and no cost-aware routing implication.
13. Role health/status identifies available, degraded, suppressed, uncertified, missing-secret, failing-smoke, and fallback-only states.
14. Fake-provider conformance tests cover retryable failures, non-retryable failures, invalid structured output, cancellation, late response, and pool exhaustion.
15. Endpoint suppression is represented as a routing skip reason and role-health state; operations can still succeed through eligible fallback candidates.
16. Schema contract resolution has one primary V1 path with stable schema version/fingerprint behavior.
17. Nightfall call sites migrate directly to canonical invocation without a module compatibility facade.
18. V1 public surfaces are documented, versioned for fixture identity, and governed by Zero BC before production release.
19. Nightfall-specific examples remain examples only; removing them does not break the module core.

## Output & Errors

Normalized failure classes are part of the public contract.

| Code | Meaning | Retryable by default |
|---|---|---|
| `llm.config.invalid_endpoint_config` | Config schema or consistency validation failed | No |
| `llm.config.credential_unavailable` | Required credential reference cannot be resolved for live invocation | No |
| `llm.endpoint.unknown_role` | Requested role is absent | No |
| `llm.endpoint.unknown_entrypoint` | Requested UID is absent | No |
| `llm.endpoint.unsupported_provider_format` | No adapter is available for provider format | No |
| `llm.endpoint.suppressed` | Endpoint UID is manually or TTL suppressed | Yes for later attempts after suppression expires |
| `llm.endpoint.unsupported_runtime_knob` | Runtime knob is not allowed by capability profile | No |
| `llm.policy.capability_mismatch` | Operation policy is incompatible with candidate capability | No |
| `llm.policy.unsupported_reasoning_mode` | Reasoning mode is not reachable for eligible candidates | No |
| `llm.policy.output_budget_exceeds_hard_cap` | Output budget exceeds provider/model-family hard cap | No |
| `llm.policy.candidate_budget_unallocatable` | Candidate budget shape cannot satisfy deadline/reserve constraints | No |
| `llm.policy.operation_ref_required` | Operation reference is required but missing | No |
| `llm.input.invalid_messages` | Caller messages fail module input validation | No |
| `llm.input.cancelled` | Caller canceled before completion | No |
| `llm.schema.missing_contract` | Structured output requires schema contract but none was supplied | No |
| `llm.schema.unknown_contract` | Schema contract identity is unknown or unavailable | No |
| `llm.structured_output.invalid_payload` | Provider output failed extraction or validation | No by default |
| `llm.structured_output.refusal` | Provider refused the request | No by default |
| `llm.invocation.rate_limited` | Provider returned rate limit | Yes |
| `llm.invocation.quota_exhausted` | Provider quota/resource exhaustion | Yes |
| `llm.invocation.transient_network` | Retryable transport failure | Yes |
| `llm.invocation.provider_5xx` | Retryable provider server failure | Yes |
| `llm.invocation.provider_failure` | Non-retryable provider failure | No |
| `llm.invocation.local_candidate_timeout` | Candidate exceeded allocated hard budget | Yes |
| `llm.invocation.late_response_discarded` | Provider returned after local timeout/cancellation and response was ignored | No |
| `llm.deadline.exceeded` | Operation deadline expired | No |
| `llm.pool.no_eligible_candidate` | No candidate can be attempted because all are suppressed, invalid, uncertified, or missing required live inputs | No |
| `llm.pool.exhausted` | All eligible candidates failed or were skipped | No |
| `llm.smoke.skipped` | Optional smoke was skipped for a typed reason | No |
| `llm.smoke.failed` | Smoke gate failed | No |
| `llm.budget.violation` | Effective runtime config violated a policy invariant | No |
| `llm.module.unsupported_version` | Host/runtime/module version is unsupported | No |

Every typed failure includes, when applicable:

- Stable code.
- Human-safe message.
- Retryability flag.
- Operation invocation ID.
- Endpoint UID, role, operation ref, and attempt index.
- Redacted attempt trace ID.
- Schema contract ref/fingerprint when applicable.
- Policy fingerprint.
- Elapsed time.
- Effective runtime config provenance.
- Safe provider status/code where available.
- Remediation hint when safe and deterministic.

## Security, Privacy, And Redaction

| Requirement | Expected behavior |
|---|---|
| Secret safety | Secret values never appear in errors, telemetry, cache keys, smoke reports, debug artifacts, or repr/debug strings |
| Prompt safety | Raw prompts/messages are excluded from telemetry and debug artifacts by default; opt-in capture requires explicit host policy and redaction |
| Response safety | Raw provider responses are excluded from success/failure telemetry and debug artifacts by default |
| Schema data safety | Typed outputs and tool arguments are treated as potentially sensitive host data |
| Provider metadata safety | Only allowlisted provider metadata is emitted |
| Error safety | Provider exceptions are normalized; unsafe message fragments are redacted |
| Cache safety | Cache keys use safe identities and fingerprints, not secret values or raw payloads |
| Live smoke safety | Live smoke payloads are minimal, non-sensitive, and redacted |
| Fake provider safety | Fake-provider fixtures must not require real prompts, responses, credentials, or user data |

## Design Decisions

| Decision | Rationale |
|---|---|
| V1 is a minimal durable spine | Feedback warned that the full platform target would slow migration and freeze mistakes too early |
| Direct invocation contract is canonical | Framework integrations are host-owned wrappers around the direct API |
| No Nightfall compatibility facade is V1 | Preserving old ergonomics creates BC debt before the clean module boundary is proven |
| Operation refs are first-class | Runtime budgets cannot be safely tuned without a stable operation binding |
| Plain text mode is first-class | Not every LLM call should be forced through a structured schema |
| Capability profiles describe hard facts, not preferences | Prevents runtime policies from confusing provider limits with desired behavior |
| `max_output_tokens` is a hard cap | Operation policies own runtime `max_tokens` defaults |
| Reasoning modes live in capability profiles | Gateways can reject reasoning kwargs even when SDK shapes look compatible |
| Candidate budget shape supports uniform, per-family, and per-UID allocation | Real pools have asymmetric latency and reasoning behavior |
| Deterministic failover beats adaptive routing in V1 | Cross-repo incidents need auditability before optimization |
| Manual/TTL suppression is explicit | Operators need a way to avoid known-bad endpoints without hidden remapping |
| Structured output always validates at the module boundary | Provider strict mode is not a substitute for application-safe validation |
| Eval evidence remains external data | One repo's probe cannot silently change behavior for every consumer |
| Fake providers are required | Consumers need deterministic proof of failure handling without provider credentials |
| Host responsibilities are explicit | Prevents the module from absorbing prompts, schemas, side effects, and business logic |

## Success Metrics

| Metric | Target / Signal |
|---|---|
| Consumer adoption | Current consumers invoke through direct API, not provider tuples or migration facades |
| Config validation | CI can validate every consumer config offline |
| Provider leakage | No application feature code imports provider SDKs for module-owned calls |
| Failure normalization | All module invocation failures map to documented typed codes |
| Telemetry comparability | Cross-repo queries can group by shared event names, invocation IDs, endpoint UIDs, operation refs, and failure classes |
| Runtime policy coverage | Operations have explicit operation runtime policies |
| Plain-text support | Conversational operations use module deadlines/failures/telemetry without fake schemas |
| Fake-provider coverage | Required failure and late-response scenarios are covered by deterministic fixtures |
| Redaction | Smoke and tests prove forbidden fields are absent from telemetry, errors, and debug artifacts |
| Upgrade discipline | Releases identify public-surface changes and required direct consumer edits |

## Related Documents

- [external-260508-1452-llm-structured-output-bible](file:///Users/chengyanru/repos/venture/lg/nightfall-ai/docs/external/external-260508-1452-llm-structured-output-bible.md) - repo-agnostic structured output guidance consumed by this module's structured-output rules.
- [prd-260512-1407-llm-endpoint-reliability](file:///Users/chengyanru/repos/venture/lg/nightfall-ai/docs/prd/prd-260512-1407-llm-endpoint-reliability.md) - original Nightfall-internal reliability PRD; this document generalizes its reusable-module concerns.
- [design-260512-1407-llm-endpoint-reliability](file:///Users/chengyanru/repos/venture/lg/nightfall-ai/docs/design/design-260512-1407-llm-endpoint-reliability.md) - current registry and structured-output technical design.
- [design-260515-1305-agentic-deadline-failover](file:///Users/chengyanru/repos/venture/lg/nightfall-ai/docs/design/design-260515-1305-agentic-deadline-failover.md) - deadline-aware failover design.
- [design-260516-0400-agentic-runtime-budget-contract](file:///Users/chengyanru/repos/venture/lg/nightfall-ai/docs/design/design-260516-0400-agentic-runtime-budget-contract.md) - runtime budget contract design generalized here as operation runtime policy.
- [260516-1236 standalone feedback](file:///Users/chengyanru/repos/venture/lg/nightfall-ai/eval/sessions/260516-1236-standalone-llm-endpoint-feedback/report.md) - review feedback requiring strict V1 cut, fake providers, request correlation, secret resolver, and role health.
- [260516-1245 module feedback](file:///Users/chengyanru/repos/venture/lg/nightfall-ai/eval/sessions/260516-1245-llm-endpoint-module-feedback/report.md) - review feedback requiring the later-rejected migration-bridge proposal, conformance tests, config precedence, rollout controls, circuit breaker, cost/token guardrails, async/cancellation, streaming boundary, and debug replay artifacts.
- [260516-1301 V1 feedback](file:///Users/chengyanru/repos/venture/lg/nightfall-ai/eval/sessions/260516-1301-llm-endpoint-v1-feedback/report.md) - review feedback requiring layered V1 scope, cleaner precedence, schema resolver boundary, suppression-as-routing-reason, deterministic role health, and later-superseded migration-facade analysis.

## Open Questions

| Question | Owner | Why it matters |
|---|---|---|
| What is the canonical extraction/distribution path: independent repo, monorepo package, private package registry, or pinned subtree during transition? | Module maintainer + consuming repo owners | Determines release, dependency, and migration mechanics |
| What is the minimum V1 provider-format set required by all current consumers? | Consuming repo owners | Defines initial adapter and capability-profile scope |
| Should runtime config reload be excluded from V1 or included because a current consumer already needs it? | Module maintainer + app owners | Determines lifecycle scope |
| What exact sync/async API shape should represent cancellation: returned typed failure, raised exception, or both by API style? | Module maintainer | Affects direct API |
| Which token usage fields are available from the V1 providers and what safe cost attribution fields are allowed? | Operators + security reviewer | Enables quota visibility without cost-aware routing |
| What schema fingerprint format should hosts use for schema contract identity? | Module maintainer + host app owners | Needed for smoke, telemetry, and debug artifacts |
| Which fields, if any, may hosts opt into capturing for deeper debugging under stricter access controls? | Security/compliance + operators | Balances incident debugging with privacy/redaction guarantees |

## Handoff Notes For Technical Design

The downstream technical design should make these V1 decisions explicit:

1. Public package shape and import boundaries.
2. Layered V1 delivery boundaries: Core, Migration Hardening, and Operator Add-Ons.
3. Config schema versioning, precedence, provenance, and migration mechanics.
4. Direct invocation API types, sync/async behavior, and cancellation semantics.
5. Operation runtime policy schema and validation algorithm.
6. Capability profile schema, evidence requirements, and conservative unknown-family behavior.
7. Provider adapter interface and failure normalization contract.
8. Secret resolver callback interface and redacted credential failure behavior.
9. Schema resolver callback or registration interface.
10. Deadline budget allocator, hard cancellation strategy, suppression skip reason, and late-response discard behavior.
11. Structured-output extraction/validation pipeline and plain-text result path.
12. Schema contract identity and fingerprinting contract.
13. Telemetry event envelope, token usage fields, request correlation, and redaction implementation.
14. Deterministic role health/status API and endpoint suppression policy.
15. Fake provider harness and conformance fixture format.
16. Offline smoke API output format and optional live-smoke behavior.
17. Debug replay artifact schema and redaction proof.
18. Nightfall direct-API migration inventory and rollback plan.
19. Zero BC checker for public API/config/telemetry/failure taxonomy changes.
20. Extraction plan from Nightfall-local package to standalone module.

## Revision Log

| Date | Change |
|---|---|
| 2026-05-16 | Applied Zero BC policy: removed migration adapter as a V1 product surface, made direct API migration mandatory, and prohibited compatibility shims before production release. |
| 2026-05-16 | Incorporated additional V1 feedback from `260516-1301`: split V1 into Core, Migration Hardening, and Operator Add-Ons; cleaned config precedence; defined schema resolver expectations; clarified endpoint suppression as a routing skip reason; added deterministic role-health semantics; analyzed a migration facade later removed by Zero BC; and added `llm.pool.no_eligible_candidate`. |
| 2026-05-16 | Incorporated feedback from the two module review sessions: converted the document from broad target contract to pragmatic V1 product contract, removed speculative extension section, added strict V1 scope, explicit non-V1 scope, fake providers, contract tests, config precedence, rollout controls, endpoint suppression, cost/token telemetry, async/cancellation, streaming boundary, role health, and debug replay artifacts. |
| 2026-05-16 | Strengthened the draft into a standalone cross-repo product contract: added product definition, host responsibilities, public surface contract, installation/version behavior, lifecycle behavior, extension behavior, security/redaction requirements, success metrics, and technical-design handoff notes. |
| 2026-05-16 | Initial draft. Reframed the LLM endpoint code as a cross-repo reusable product module, codified operation runtime policy as the central reusable abstraction, and separated module machinery from consumer vocabulary, prompts, schemas, and evidence. |
