## 1. Version Metadata

- [x] 1.1 Change `requires-python` in `pyproject.toml` from `>=3.12` to `>=3.11`
- [x] 1.2 Add the Python 3.11 classifier to package metadata while retaining supported newer versions
- [x] 1.3 Change Ruff `target-version` from `py312` to `py311`
- [x] 1.4 Add `.python-version` selecting Python 3.11

## 2. Source Compatibility

- [x] 2.1 Replace Python 3.12-only `type` alias syntax in `src/llm_endpoint/results.py`
- [x] 2.2 Replace Python 3.12-only `type` alias syntax in `src/llm_endpoint/smoke.py`
- [x] 2.3 Search source and tests for remaining Python 3.12-only syntax or APIs

## 3. Lockfile and Validation

- [x] 3.1 Regenerate or update `uv.lock` so it records `requires-python = ">=3.11"`
- [x] 3.2 Run linting with the Python 3.11 target
- [x] 3.3 Run the test suite under the updated compatibility configuration
- [x] 3.4 Review the diff to confirm runtime behavior and public APIs are unchanged
