## Why

This package is intended to be reusable by other Python applications, but the current Python `>=3.12` requirement prevents Python 3.11 projects from depending on it. Lowering the floor to Python 3.11 resolves dependency conflicts for consumers that must remain on 3.11 while preserving the current public behavior.

## What Changes

- Lower the package Python requirement from `>=3.12` to `>=3.11`.
- Migrate Python 3.12-only syntax to Python 3.11-compatible syntax without changing runtime semantics.
- Add a `.python-version` file that selects Python 3.11 for local tooling.
- Update tooling metadata so linting and packaging target Python 3.11 compatibility.
- Validate the package test suite under the updated Python compatibility target.

## Capabilities

### New Capabilities
- `python-version-compatibility`: Defines the supported Python version floor and compatibility expectations for this package.

### Modified Capabilities

## Impact

- Affects package metadata in `pyproject.toml` and the generated lockfile.
- Affects source files that currently use Python 3.12-only syntax.
- Affects local developer environment selection through `.python-version`.
- No intended changes to public APIs, runtime behavior, or dependency surface.
