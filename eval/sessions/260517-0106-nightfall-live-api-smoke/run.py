#!/usr/bin/env python3
"""Run opt-in live smoke against Nightfall LLM endpoint test config."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__version__ = "0.1.0"

SESSION_DIR = Path(__file__).resolve().parent
REPO_ROOT = SESSION_DIR.parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "llm-endpoints.yaml"
SAFE_PROMPT = "Return exactly: OK"


@dataclass(frozen=True, slots=True)
class SmokeResult:
    """One redacted endpoint live-smoke result."""

    uid: str
    provider_format: str
    model: str
    name: str
    status: str
    available: bool
    http_status: int | None
    elapsed_ms: float
    content_chars: int
    content_sha256: str | None
    exact_ok: bool
    error_type: str | None
    error_message: str | None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python run.py --confirm-live\n"
            "  python run.py --confirm-live --endpoint ofc-seed2pro-gj7n7a"
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        metavar="PATH",
        help="Ignored local llm-endpoints.yaml containing test credentials.",
    )
    parser.add_argument(
        "--endpoint",
        action="append",
        default=None,
        metavar="UID",
        help="Endpoint UID to smoke. Repeatable. Defaults to all endpoints.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=60.0,
        metavar="SECONDS",
        help="Per-endpoint HTTP timeout.",
    )
    parser.add_argument(
        "--pause-sec",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Pause between endpoint calls.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=16,
        metavar="N",
        help="Small max token budget for the safe smoke prompt.",
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Required safety flag. Without it, no provider calls are made.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the live-smoke CLI."""
    args = parse_args(argv)
    try:
        return run(args)
    except Exception as exc:  # noqa: BLE001 - CLI boundary should be concise.
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def run(args: argparse.Namespace) -> int:
    """Execute live smoke and write eval artifacts."""
    if not args.confirm_live:
        raise ValueError("--confirm-live is required before real provider calls")
    if args.timeout_sec <= 0:
        raise ValueError("--timeout-sec must be positive")
    if args.pause_sec < 0:
        raise ValueError("--pause-sec must be non-negative")
    if args.max_tokens <= 0:
        raise ValueError("--max-tokens must be positive")

    started_at = datetime.now(UTC)
    config_path = args.config.resolve()
    config = load_yaml(config_path)
    entrypoints = config.get("entrypoints")
    if not isinstance(entrypoints, dict) or not entrypoints:
        raise ValueError("config must contain non-empty entrypoints mapping")

    requested = set(args.endpoint or entrypoints)
    unknown = sorted(requested - set(entrypoints))
    if unknown:
        raise ValueError(f"unknown endpoint uid(s): {', '.join(unknown)}")

    selected = [(uid, entrypoints[uid]) for uid in entrypoints if uid in requested]
    outputs_dir = SESSION_DIR / "outputs"
    metrics_dir = SESSION_DIR / "metrics"
    manifests_dir = SESSION_DIR / "manifests"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    results: list[SmokeResult] = []
    raw_path = outputs_dir / "results.jsonl"
    with raw_path.open("w", encoding="utf-8") as raw_file:
        for index, (uid, endpoint) in enumerate(selected, start=1):
            print(f"[live-smoke] {uid} {index}/{len(selected)}", file=sys.stderr, flush=True)
            result = smoke_endpoint(
                uid=uid,
                endpoint=endpoint,
                timeout_sec=args.timeout_sec,
                max_tokens=args.max_tokens,
            )
            results.append(result)
            raw_file.write(json.dumps(result_to_dict(result), sort_keys=True) + "\n")
            raw_file.flush()
            if index < len(selected):
                time.sleep(args.pause_sec)

    finished_at = datetime.now(UTC)
    summary = summarize(
        results=results,
        config_path=config_path,
        started_at=started_at,
        finished_at=finished_at,
        timeout_sec=args.timeout_sec,
        max_tokens=args.max_tokens,
    )
    write_json(metrics_dir / "summary.json", summary)
    write_json(metrics_dir / "combined.json", summary)
    (SESSION_DIR / "report.md").write_text(render_report(summary), encoding="utf-8")
    (manifests_dir / "run_manifest.yaml").write_text(render_manifest(summary), encoding="utf-8")
    print(json.dumps(compact_stdout(summary), sort_keys=True), flush=True)
    return 0 if summary["all_passed"] else 1


def load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML through PyYAML when available, otherwise through system Ruby."""
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return load_yaml_with_ruby(path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("top-level YAML must be a mapping")
    return loaded


def load_yaml_with_ruby(path: Path) -> dict[str, Any]:
    """Load YAML with Ruby stdlib on machines without PyYAML."""
    ruby = shutil.which("ruby")
    if ruby is None:
        raise RuntimeError("PyYAML is not installed and ruby is unavailable for YAML parsing")
    command = [
        ruby,
        "-ryaml",
        "-rjson",
        "-e",
        "puts JSON.generate(YAML.load_file(ARGV[0]))",
        str(path),
    ]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    loaded = json.loads(completed.stdout)
    if not isinstance(loaded, dict):
        raise ValueError("top-level YAML must be a mapping")
    return loaded


def smoke_endpoint(
    *,
    uid: str,
    endpoint: dict[str, Any],
    timeout_sec: float,
    max_tokens: int,
) -> SmokeResult:
    """Call one real endpoint using the safe smoke prompt."""
    start = time.perf_counter()
    http_status: int | None = None
    content = ""
    error_type: str | None = None
    error_message: str | None = None
    status = "success"
    try:
        request = build_request(endpoint, max_tokens=max_tokens)
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            http_status = response.status
            body = response.read().decode("utf-8", errors="replace")
            content = extract_content(body)
            if not content.strip():
                status = "empty_response"
                error_type = "EmptyResponse"
                error_message = "provider returned no visible content"
    except urllib.error.HTTPError as exc:
        http_status = exc.code
        status = classify_http_error(exc)
        error_type = type(exc).__name__
        error_message = safe_error_message(read_http_error(exc))
    except Exception as exc:  # noqa: BLE001 - provider failures are eval data.
        status = "error"
        error_type = type(exc).__name__
        error_message = safe_error_message(str(exc))

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    available = status == "success"
    return SmokeResult(
        uid=uid,
        provider_format=str(endpoint.get("provider_format", "")),
        model=str(endpoint.get("model", "")),
        name=str(endpoint.get("name", "")),
        status=status,
        available=available,
        http_status=http_status,
        elapsed_ms=elapsed_ms,
        content_chars=len(content),
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest() if content else None,
        exact_ok=content.strip() == "OK",
        error_type=error_type,
        error_message=error_message,
    )


def build_request(endpoint: dict[str, Any], *, max_tokens: int) -> urllib.request.Request:
    """Build a non-streaming OpenAI-compatible chat completion request."""
    provider = str(endpoint["provider_format"])
    config = endpoint["config"]
    credentials = endpoint["credentials"]
    if provider == "azure_gemini":
        url = (
            str(config["endpoint"]).rstrip("/")
            + f"/openai/deployments/{urllib.parse.quote(str(endpoint['model']))}/chat/completions"
            + f"?api-version={urllib.parse.quote(str(config['api_version']))}"
        )
        headers = {"api-key": str(credentials["api_key"])}
    else:
        url = str(config["base_url"]).rstrip("/") + "/chat/completions"
        headers = {"Authorization": "Bearer " + str(credentials["api_key"])}

    payload = {
        "model": endpoint["model"],
        "messages": [{"role": "user", "content": SAFE_PROMPT}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return urllib.request.Request(url, data=body, headers=headers, method="POST")


def extract_content(body: str) -> str:
    """Extract visible content from an OpenAI-compatible JSON response."""
    parsed = json.loads(body)
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    text = first.get("text")
    return text if isinstance(text, str) else ""


def classify_http_error(exc: urllib.error.HTTPError) -> str:
    """Return a normalized status label for an HTTP provider failure."""
    if exc.code in {401, 403}:
        return "auth_or_permission_error"
    if exc.code == 429:
        return "rate_limited"
    if 500 <= exc.code <= 599:
        return "provider_5xx"
    return "http_error"


def read_http_error(exc: urllib.error.HTTPError) -> str:
    """Read a bounded HTTP error body."""
    try:
        return exc.read().decode("utf-8", errors="replace")[:1000]
    except Exception:  # noqa: BLE001 - best-effort diagnostics only.
        return str(exc)


def safe_error_message(message: str) -> str:
    """Redact common credential fragments from an error message."""
    redacted = message
    for marker in ("Authorization", "Bearer", "api-key", "api_key"):
        redacted = redacted.replace(marker, "[redacted]")
    return redacted[:1000]


def summarize(
    *,
    results: list[SmokeResult],
    config_path: Path,
    started_at: datetime,
    finished_at: datetime,
    timeout_sec: float,
    max_tokens: int,
) -> dict[str, Any]:
    """Build the tracked redacted summary."""
    rows = [result_to_dict(result) for result in results]
    passed = [row for row in rows if row["available"]]
    failed = [row for row in rows if not row["available"]]
    return {
        "session_id": SESSION_DIR.name,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "duration_sec": round((finished_at - started_at).total_seconds(), 3),
        "config_path": str(config_path),
        "prompt_sha256": hashlib.sha256(SAFE_PROMPT.encode("utf-8")).hexdigest(),
        "timeout_sec": timeout_sec,
        "max_tokens": max_tokens,
        "endpoint_count": len(rows),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "all_passed": not failed and bool(rows),
        "results": rows,
        "raw_artifacts_local_only": True,
    }


def result_to_dict(result: SmokeResult) -> dict[str, Any]:
    """Convert a smoke result into redacted JSON data."""
    return {
        "uid": result.uid,
        "provider_format": result.provider_format,
        "model": result.model,
        "name": result.name,
        "status": result.status,
        "available": result.available,
        "http_status": result.http_status,
        "elapsed_ms": result.elapsed_ms,
        "content_chars": result.content_chars,
        "content_sha256": result.content_sha256,
        "exact_ok": result.exact_ok,
        "error_type": result.error_type,
        "error_message": result.error_message,
    }


def compact_stdout(summary: dict[str, Any]) -> dict[str, Any]:
    """Return short machine-readable CLI output."""
    return {
        "all_passed": summary["all_passed"],
        "endpoint_count": summary["endpoint_count"],
        "passed_count": summary["passed_count"],
        "failed_count": summary["failed_count"],
    }


def write_json(path: Path, value: Any) -> None:
    """Write stable pretty JSON."""
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_report(summary: dict[str, Any]) -> str:
    """Render the eval report markdown."""
    verdict = "Pass" if summary["all_passed"] else "Fail"
    rows = "\n".join(
        (
            "| {uid} | {provider_format} | {model} | {status} | {http_status} | "
            "{elapsed_ms} | {exact_ok} | {error_type} |"
        ).format(
            **row,
        )
        for row in summary["results"]
    )
    return f"""---
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

{verdict}.

This session executed real provider calls against every selected endpoint using the safe prompt
`Return exactly: OK`. Credentials were read only from the local ignored config file. The tracked
report and metrics contain no raw credential values and no raw response body.

## Summary

| Metric | Value |
|---|---:|
| Endpoint count | {summary["endpoint_count"]} |
| Passed | {summary["passed_count"]} |
| Failed | {summary["failed_count"]} |
| Timeout seconds | {summary["timeout_sec"]} |
| Max tokens | {summary["max_tokens"]} |

## Results

| UID | Provider | Model | Status | HTTP | Elapsed ms | Exact OK | Error type |
|---|---|---|---|---:|---:|---|---|
{rows}

## Artifacts

- Tracked summary: `metrics/summary.json`
- Tracked combined metrics: `metrics/combined.json`
- Local-only raw results: `outputs/results.jsonl`

## Command

```bash
uv run python eval/sessions/{SESSION_DIR.name}/run.py --confirm-live
```

## Notes

- Raw credentials remain in `config/llm-endpoints.yaml`, which is gitignored.
- Raw provider bodies are not written to tracked artifacts.
- `exact_ok` records whether the provider returned exactly `OK`; endpoint availability only requires
  a successful HTTP response with visible content.
"""


def render_manifest(summary: dict[str, Any]) -> str:
    """Render the eval run manifest."""
    return f"""session_id: {SESSION_DIR.name}
task_type: live-provider-smoke
dataset:
  name: nightfall-ai-local-test-llm-endpoints
  location: config/llm-endpoints.yaml
  fingerprint: local-credential-file-gitignored
runner:
  entrypoint: eval/sessions/{SESSION_DIR.name}/run.py
  commit: "0ca6466"
parameters:
  prompt_sha256: "{summary["prompt_sha256"]}"
  timeout_sec: {summary["timeout_sec"]}
  max_tokens: {summary["max_tokens"]}
outputs:
  directory: eval/sessions/{SESSION_DIR.name}/outputs
  primary_metrics: metrics/summary.json
  primary_results: outputs/results.jsonl
decision:
  report: report.md
"""


if __name__ == "__main__":
    raise SystemExit(main())
