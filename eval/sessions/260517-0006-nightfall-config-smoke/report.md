---
title: "260517-nightfall-config-smoke"
service_version: "0.1.0"
date: 2026-05-17
environment: "local-macos"
model_id: "nightfall-ai-test-endpoints"
dataset_version: "local llm-endpoints.yaml copied from Nightfall AI"
purpose: "Verify whether Nightfall AI's test LLM endpoint config can pass this module's smoke readiness path."
baseline_ref: "260516-2325-prd-final-gate"
---

# Nightfall Config Smoke

## Verdict

Module offline smoke passed after translating the copied Nightfall test config into the module's V1 in-memory contract.

The copied Nightfall config is present locally and ignored by git, and Nightfall's own legacy loader can parse it. Direct module smoke against the raw YAML shape fails because the file is still in Nightfall's legacy/adoption schema. The successful path keeps the raw credentials in the ignored local YAML, maps each endpoint to a V1 `credential_ref`, adds smoke-only capability profiles, and runs `run_offline_smoke()` against the translated V1 config.

## Inputs

- Source config: `/Users/chengyanru/repos/venture/lg/nightfall-ai/config/llm-endpoints.yaml`
- Local copy: `config/llm-endpoints.yaml`
- Git policy: local copy is ignored by `.gitignore`
- Raw credentials: present in the local test file by user approval; not copied into this report

## Commands

```bash
git check-ignore -v config/llm-endpoints.yaml
```

Result:

```text
.gitignore:210:config/llm-endpoints.yaml config/llm-endpoints.yaml
```

```bash
uv run python - <<'PY'
from pathlib import Path
from agent.llm_endpoint.config_loader import FileConfigLoader

config = FileConfigLoader(Path("config/llm-endpoints.yaml")).load()
print(len(config.entrypoints), len(config.roles), len(config.runtime_policies))
PY
```

Result:

```text
nightfall_loader=passed
entrypoints=6
roles=4
runtime_policies=2
failover_policies=1
config_identity=aaedc07bcc3e3e1fe3ccffd2c27e120449534875aadf6cd8d1098d7ef00441e8
```

```bash
ruby -ryaml -rjson -e 'puts JSON.generate(YAML.load_file(ARGV[0]))' config/llm-endpoints.yaml > /tmp/nightfall_llm_endpoints.json
uv run python - <<'PY'
# Probe whether the copied YAML can enter this module's V1 smoke path.
PY
```

Result:

```text
module_offline_smoke=failed
legacy_top_level_keys=['entrypoints', 'failover_policies', 'invocation_budget', 'operation_latency_objectives', 'promotion_decisions', 'roles', 'runtime_policies']
missing_v1_keys=['endpoints', 'operations', 'policies']
unsupported_provider_formats=['azure_gemini', 'openai_func_call']
entrypoints_missing_model_family_count=6
entrypoints_with_raw_credentials_count=6
roles_without_operation_refs=['agentic_dm', 'character_generation', 'default', 'mini']
failure_stage=config_ingestion_before_run_offline_smoke
```

```bash
ruby -ryaml -rjson -e 'puts JSON.generate(YAML.load_file(ARGV[0]))' config/llm-endpoints.yaml > /tmp/nightfall_llm_endpoints.json
uv run python - <<'PY'
# Translate Nightfall's local test YAML into the module V1 dataclass contract,
# then run run_offline_smoke() for every Nightfall role/operation.
PY
```

Result:

```text
role=default operation=default ok=True checks=4 identity=854eafa37923c8757c294814dcae73c66bca305e1d8287ab72dee83a5b5a52cf
role=mini operation=mini ok=True checks=4 identity=854eafa37923c8757c294814dcae73c66bca305e1d8287ab72dee83a5b5a52cf
role=agentic_dm operation=agentic_dm ok=True checks=4 identity=854eafa37923c8757c294814dcae73c66bca305e1d8287ab72dee83a5b5a52cf
role=character_generation operation=character_generation ok=True checks=4 identity=854eafa37923c8757c294814dcae73c66bca305e1d8287ab72dee83a5b5a52cf
module_offline_smoke_all_roles=passed
endpoints=6 roles=4 operations=4 policies=2 profiles=5
```

## Failure Analysis

| Gate | Status | Reason |
|---|---|---|
| Local file inclusion | Pass | `config/llm-endpoints.yaml` was copied into the repo workspace. |
| Git hygiene | Pass | `.gitignore` now excludes `config/llm-endpoints.yaml`; `git check-ignore` confirms it. |
| Nightfall legacy loader | Pass | Nightfall's `FileConfigLoader` parsed the source config and derived a config identity. |
| Direct module V1 smoke against raw YAML | Fail | The file does not directly match this module's V1 config contract. |
| Translated module V1 offline smoke | Pass | All four Nightfall roles planned successfully with config validation, registry build, invocation planning, and telemetry redaction checks. |

The direct module-side failure is expected under Zero BC. This package accepts the clean V1 contract with `endpoints`, `roles`, `operations`, and `policies`. The Nightfall file still uses `entrypoints`, `runtime_policies`, role-bound runtime policy refs, raw `credentials.api_key`, and provider format names that this module does not expose as V1 provider formats.

The passing smoke path does not add raw API key support to the module. It treats the ignored YAML as a host-owned local secret source, converts each raw credential into a `local://nightfall/<uid>/api_key` credential reference, and runs the module-owned offline checks against the translated in-memory config.

## Required Fix

Convert the Nightfall config in one cut before treating it as a permanent consumer-smoke fixture:

- Replace `entrypoints` with V1 `endpoints`.
- Replace raw `credentials.api_key` fields with safe `credential_ref` values plus host `resolve_secret(ref)`.
- Add explicit `model_family` for every endpoint.
- Map or add provider adapter support for `azure_gemini` and `openai_func_call`, or convert them to supported V1 provider formats.
- Split role runtime binding into explicit `operations` plus `policies`.
- Add operation refs for roles that should be smoke-tested.

## Decision

Nightfall's local test config is safe to keep as a gitignored local artifact. Module offline smoke is now proven for all copied Nightfall roles through a V1 in-memory translation. The remaining productization step is to make that translation a first-class Nightfall adoption config or loader boundary instead of an ad hoc eval probe.
