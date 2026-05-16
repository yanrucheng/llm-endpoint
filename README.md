# llm-endpoint

Professional, reusable LLM endpoint execution boundary for Python applications.

`llm-endpoint` gives host repositories a clean contract for configuring LLM
roles, planning invocations, routing across endpoint pools, validating
structured output, emitting redacted telemetry, and running offline or opt-in
live smoke checks. It keeps provider credentials, network clients, schema
storage, and environment-specific behavior owned by the consuming repository.

## Status

| Attribute | Value |
|---|---|
| Package | `llm-endpoint` |
| Import | `llm_endpoint` |
| Version | `0.1.0` |
| Python | `>=3.12` |
| Runtime dependencies | None |
| License | MIT |
| Stability | Pre-V1 adoption candidate |
| Distribution | GitHub/source pinning first; PyPI deferred |

This project follows a Zero Backward Compatibility policy before V1. Consumers
must pin exact versions and treat each upgrade as an explicit contract
replacement.

## Why Use It

- Centralize endpoint config, role-to-pool mapping, runtime policy, failover,
  failure taxonomy, telemetry, and smoke validation.
- Keep provider-specific SDK code outside the shared endpoint contract.
- Validate config and invocation planning without network calls or credentials.
- Route requests through deterministic ordered pools with redacted attempt
  traces.
- Support structured-output and plain-text results with typed terminal
  failures.
- Provide consumer contract fixtures and release guards for cross-repo adoption.

## What This Module Owns

- Versioned endpoint configuration dataclasses.
- Offline config validation and registry construction.
- Invocation planning without provider calls.
- Ordered-pool routing and normalized terminal results.
- Provider adapter contracts and normalized provider outcomes.
- Secret and schema resolver callback contracts.
- Redacted telemetry events, attempt traces, and debug artifacts.
- Offline smoke and explicitly opted-in live smoke result envelopes.
- Public surface and consumer contract-pack helpers.

## What The Host Repo Owns

- Loading config from YAML, JSON, environment variables, or internal config
  services.
- Resolving `credential_ref` values into raw secrets.
- Implementing provider adapters for OpenAI, Anthropic, internal gateways, or
  other providers.
- Resolving structured-output schema refs.
- Persisting telemetry and redacted debug artifacts.
- Owning async wrappers, web handlers, retries outside the module contract, and
  deployment rollout.

Secrets must never be placed in endpoint config, telemetry, exceptions, debug
artifacts, or logs. Use credential references such as `secret://prod/openai` or
`local://team/role/api_key`.

## Installation

This project is not positioned as a PyPI-first package yet. Use source-pinned
adoption until at least one real consuming repository has passed offline smoke,
optional live smoke, and the consumer contract pack.

For active local development from a sibling checkout:

```bash
uv add --editable /absolute/path/to/llm-endpoint
```

For a private/local path dependency:

```toml
[project]
dependencies = [
  "llm-endpoint @ file:///absolute/path/to/llm-endpoint",
]
```

For cross-repo adoption from GitHub, pin an exact commit SHA:

```toml
[project]
dependencies = [
  "llm-endpoint @ git+https://github.com/yanrucheng/llm-endpoint.git@<commit-sha>",
]
```

After a verified adoption tag exists, consumers may pin that tag instead:

```toml
[project]
dependencies = [
  "llm-endpoint @ git+https://github.com/yanrucheng/llm-endpoint.git@v0.1.0-adoption.1",
]
```

Do not depend on `main` directly. Do not use floating version ranges for pre-V1
adoption. PyPI publication is deferred until the source-pinned adoption path is
proven in a real external repository.

## Quick Start

Create a config in the consuming repository. The example uses the built-in fake
provider format so it can run offline.

```python
from llm_endpoint import (
    EndpointConfig,
    EndpointPool,
    LLMEndpointConfig,
    OperationConfig,
    OperationRuntimePolicy,
    ProviderFormat,
    RoleConfig,
    StructuredOutputMode,
)


config = LLMEndpointConfig(
    endpoints=(
        EndpointConfig(
            uid="primary",
            provider_format=ProviderFormat.FAKE,
            model_family="fake-family",
            model="fake-model",
            credential_ref="secret://llm/primary",
        ),
        EndpointConfig(
            uid="fallback",
            provider_format=ProviderFormat.FAKE,
            model_family="fake-family",
            model="fake-model",
            credential_ref="secret://llm/fallback",
        ),
    ),
    roles=(
        RoleConfig(
            name="writer",
            pool=EndpointPool(("primary", "fallback")),
        ),
    ),
    operations=(
        OperationConfig(ref="draft", policy_ref="draft-policy"),
    ),
    policies=(
        OperationRuntimePolicy(
            ref="draft-policy",
            deadline_ms=10_000,
            max_output_tokens=1_024,
            candidate_budget_ms=4_000,
            protect_last_eligible=True,
            structured_output_mode=StructuredOutputMode.NONE,
        ),
    ),
)
```

Validate the config and planning path without network calls or credential
resolution:

```python
from llm_endpoint import run_offline_smoke


report = run_offline_smoke(
    config=config,
    role="writer",
    operation_ref="draft",
)

assert report.ok, report.checks
print(report.config_identity)
```

Plan an invocation:

```python
from llm_endpoint import InvocationPlan, InvocationRequest, TypedFailure, invoke_plan


planned = invoke_plan(
    request=InvocationRequest(
        role="writer",
        operation_ref="draft",
        messages=({"role": "user", "content": "Draft a release note."},),
        deadline_ms=10_000,
        operation_invocation_id="req-001",
    ),
    config=config,
)

if isinstance(planned, TypedFailure):
    raise RuntimeError(planned.code.value)

assert isinstance(planned, InvocationPlan)
```

Route the invocation through a provider adapter. Production hosts replace
`FakeProviderAdapter` with their real provider adapter.

```python
from llm_endpoint import (
    FakeProviderAdapter,
    PlainTextResult,
    ProviderFormat,
    build_registry,
    provider_success,
    resolved_secret,
    route_invocation,
)


registry = build_registry(config)
adapter = FakeProviderAdapter(
    {
        "primary": (
            provider_success(
                endpoint_uid="primary",
                elapsed_ms=20,
                content="Release note draft",
                safe_provider_status={"status_class": "2xx"},
            ),
        ),
    }
)

result = route_invocation(
    plan=planned,
    registry=registry,
    adapters={ProviderFormat.FAKE: adapter},
    secret_resolver=lambda ref: resolved_secret(ref, "host-owned-secret-value"),
)

if isinstance(result.terminal_result, PlainTextResult):
    print(result.terminal_result.text)
else:
    print(result.terminal_result.code.value)
```

## Real Provider Integration

A consuming repository implements one adapter per provider format. The adapter
receives a redacted `AdapterInvocationPlan` and returns a normalized
`ProviderOutcome`.

```python
from llm_endpoint import (
    AdapterInvocationPlan,
    ProviderFormat,
    ProviderOutcome,
    provider_failure,
    provider_success,
)
from llm_endpoint.results import FailureCode
from llm_endpoint.adapters import ProviderOutcomeKind


class OpenAIResponsesAdapter:
    provider_format = ProviderFormat.OPENAI_RESPONSES

    def invoke(self, plan: AdapterInvocationPlan) -> ProviderOutcome:
        # The host repo owns the real SDK client and network behavior.
        # Never put raw request/response bodies or credentials in status fields.
        try:
            text = call_openai_responses_api(
                api_key=plan.credential.value if plan.credential else None,
                model=plan.model,
                messages=plan.messages,
                timeout_ms=plan.candidate_budget_ms,
            )
        except TimeoutError:
            return provider_failure(
                kind=ProviderOutcomeKind.TIMEOUT,
                endpoint_uid=plan.endpoint_uid,
                elapsed_ms=plan.candidate_budget_ms,
                failure_code=FailureCode.DEADLINE_EXCEEDED,
                safe_provider_status={"provider": "openai", "status": "timeout"},
            )

        return provider_success(
            endpoint_uid=plan.endpoint_uid,
            elapsed_ms=100,
            content=text,
            safe_provider_status={"provider": "openai", "status_class": "2xx"},
        )
```

Register the adapter at routing time:

```python
result = route_invocation(
    plan=planned,
    registry=registry,
    adapters={ProviderFormat.OPENAI_RESPONSES: OpenAIResponsesAdapter()},
    secret_resolver=resolve_secret,
    schema_resolver=resolve_schema,
)
```

## Host Callback Contracts

Secret resolution is host-owned:

```python
import os

from llm_endpoint import SecretResolution, missing_secret, resolved_secret


def resolve_secret(ref: str) -> SecretResolution:
    if ref == "secret://llm/primary":
        value = os.environ.get("PRIMARY_LLM_API_KEY")
        return resolved_secret(ref, value) if value else missing_secret(ref)
    return missing_secret(ref, "unknown secret ref")
```

Structured-output schema resolution is host-owned:

```python
from llm_endpoint import SchemaResolution, resolved_schema


def resolve_schema(ref: str) -> SchemaResolution:
    return resolved_schema(
        ref=ref,
        name="answer",
        version="1",
        fingerprint="sha256:answer-v1",
        json_schema={"type": "object", "required": ["answer"]},
        validate=lambda value: bool(value.get("answer")),
    )
```

## Smoke Testing

Offline smoke is safe for CI and local development:

```python
from llm_endpoint import run_offline_smoke


report = run_offline_smoke(config=config, role="writer", operation_ref="draft")
assert report.ok
```

Optional live smoke requires explicit consent and a host-owned provider probe:

```python
from llm_endpoint import LIVE_SMOKE_SAFE_PROMPT, run_optional_live_smoke


report = run_optional_live_smoke(
    config=config,
    role="writer",
    operation_ref="draft",
    explicit_consent=True,
    provider_probe=lambda plan: real_probe(plan),
)

print(report.status.value, report.reason)
assert report.plan is None or report.plan.messages[0]["content"] == LIVE_SMOKE_SAFE_PROMPT
```

Live smoke is not a production health dependency. It is an explicit operational
probe with redacted reporting.

## Consumer Contract Pack

Consumers can inspect the contract pack and wire the listed selectors into
their own repository checks:

```python
from llm_endpoint import (
    assert_consumer_contract_pack_complete,
    build_consumer_contract_pack,
)


pack = build_consumer_contract_pack()
assert_consumer_contract_pack_complete(pack)

for case in pack.cases:
    print(case.area.value, case.test_selector)
```

The pack covers config validation, failure taxonomy, telemetry redaction,
structured output, pool simulation, plain text, and direct migration.

## Rollout And Rollback

Recommended rollout sequence for a consuming repository:

1. Pin an exact Git commit SHA or verified adoption tag.
2. Build a host-owned config object from local or service-owned config.
3. Run `run_offline_smoke()` for every role and operation.
4. Run the consumer contract pack in the host repository.
5. Enable traffic by role and operation.
6. Suppress bad endpoint UIDs instead of changing legacy provider/model tuples.
7. Re-run offline smoke after every config replacement.

Rollback is by current config identity and exact package pin:

- Restore the last known-good config object.
- Suppress a bad endpoint UID.
- Re-pin to the previous exact commit SHA or adoption tag.
- Re-run offline smoke and consumer contract checks before resuming traffic.

## Release Policy

Current recommended distribution is GitHub/source pinning, not PyPI.

Adoption tags should be created only after:

- The full test suite passes.
- Offline smoke passes for the target consuming repo config.
- Optional live smoke passes or is explicitly recorded as skipped.
- Consumer contract-pack checks are wired into the consuming repo.
- README usage instructions match the real adoption flow.

Suggested pre-V1 tag format:

```text
v0.1.0-adoption.1
v0.1.0-adoption.2
```

PyPI publication should wait until at least one external repository completes
source-pinned adoption without undocumented setup steps.

## Development

Install development dependencies:

```bash
uv sync --extra dev
```

Run the test suite:

```bash
uv run pytest
```

Run lint:

```bash
uv run ruff check .
```

## Documentation

- Product contract: [`docs/prd/prd-260516-1321-llm-endpoint-module.md`](docs/prd/prd-260516-1321-llm-endpoint-module.md)
- Technical design: [`docs/design/design-260516-1331-llm-endpoint-module.md`](docs/design/design-260516-1331-llm-endpoint-module.md)
- Development plan: [`docs/plan/plan-260516-1331-llm-endpoint-module.md`](docs/plan/plan-260516-1331-llm-endpoint-module.md)
- Adoption guide: [`docs/plan/phase-5e-extraction-adoption-guide.md`](docs/plan/phase-5e-extraction-adoption-guide.md)

## License

MIT.
