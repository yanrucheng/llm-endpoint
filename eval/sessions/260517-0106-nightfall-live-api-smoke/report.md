---
title: "260517-nightfall-live-api-smoke"
service_version: "0.1.0"
date: 2026-05-17
environment: "local-macos-live-provider"
model_id: "nightfall-ai-test-endpoints"
dataset_version: "local gitignored llm-endpoints.yaml"
purpose: "Verify every endpoint in the copied Nightfall test config with real provider API calls."
baseline_ref: "260517-0006-nightfall-config-smoke"
---

# Nightfall Live API Smoke

## Verdict

Pass.

This session executed real provider calls against every selected endpoint using the safe prompt
`Return exactly: OK`. Credentials were read only from the local ignored config file. The tracked
report and metrics contain no raw credential values and no raw response body.

## Summary

| Metric | Value |
|---|---:|
| Endpoint count | 6 |
| Passed | 6 |
| Failed | 0 |
| Timeout seconds | 60.0 |
| Max tokens | 16 |

## Results

| UID | Provider | Model | Status | HTTP | Elapsed ms | Exact OK | Error type |
|---|---|---|---|---:|---:|---|---|
| azgem-gemini3pro-4kd82j | azure_gemini | gemini-3-pro-preview-new | success | 200 | 1144.71 | True | None |
| ofc-seed2pro-gj7n7a | openai_func_call | ep-20260407180116-gj7n7 | success | 200 | 2359.45 | True | None |
| ofc-seed2lite-b6grf2 | openai_func_call | ep-20251108185845-b6grf | success | 200 | 1479.33 | True | None |
| ofc-seed2mini-2mbch3 | openai_func_call | ep-20251210163014-2mbch | success | 200 | 443.82 | True | None |
| ofc-seed1-6-rtthr6 | openai_func_call | ep-20250611155053-rtthr | success | 200 | 2028.11 | True | None |
| ofc-seed1-6-xtj2n6 | openai_func_call | ep-20251110230627-xtj2n | success | 200 | 2494.29 | True | None |

## Artifacts

- Tracked summary: `metrics/summary.json`
- Tracked combined metrics: `metrics/combined.json`
- Local-only raw results: `outputs/results.jsonl`

## Command

```bash
uv run python eval/sessions/260517-0106-nightfall-live-api-smoke/run.py --confirm-live
```

## Notes

- Raw credentials remain in `config/llm-endpoints.yaml`, which is gitignored.
- Raw provider bodies are not written to tracked artifacts.
- `exact_ok` records whether the provider returned exactly `OK`; endpoint availability only requires
  a successful HTTP response with visible content.
