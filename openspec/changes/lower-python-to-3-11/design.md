## Context

The package currently declares `requires-python = ">=3.12"` and includes Python 3.12-only `type` alias syntax. A consuming repository must run on Python 3.11, so the current metadata and syntax prevent that repository from using this package as a dependency.

The package has no runtime dependencies, so the compatibility migration is expected to be limited to packaging metadata, local tool configuration, and syntax that prevents Python 3.11 parsing.

## Goals / Non-Goals

**Goals:**
- Make the package installable and importable on Python 3.11.
- Keep existing public APIs and runtime behavior unchanged.
- Align local tooling with Python 3.11 by adding `.python-version` and updating tool targets.
- Validate the migration by running the existing test suite.

**Non-Goals:**
- Add support for Python versions below 3.11.
- Change package runtime dependencies.
- Refactor application architecture or public API names.
- Introduce compatibility shims for behavior that is already compatible with Python 3.11.

## Decisions

- Set the supported Python floor to `>=3.11` rather than `>=3.10`.
  - Rationale: the immediate consumer requirement is Python 3.11, and 3.11 provides a modern, currently-supported baseline without expanding test responsibility to older versions.
  - Alternative considered: `>=3.10`, but that increases support scope beyond the known need.

- Replace Python 3.12 `type` alias statements with assignment-based aliases.
  - Rationale: this is the minimal syntax migration needed for Python 3.11 parsing and preserves the exported alias names.
  - Alternative considered: introduce `typing.TypeAlias`, but plain assignment is sufficient when the alias is clear and avoids extra compatibility noise.

- Update tool metadata to target Python 3.11.
  - Rationale: linters and formatters should detect accidental use of syntax or upgrades that would break the supported floor.
  - Alternative considered: leave tooling at Python 3.12, but that would allow regressions against the new floor.

- Add `.python-version` with Python 3.11.
  - Rationale: local version managers should select the same Python major/minor version that defines the package floor.
  - Alternative considered: rely only on `requires-python`, but that does not guide local shell tooling.

## Risks / Trade-offs

- Accidental use of Python 3.12-only APIs later → Mitigate by setting the tool target to Python 3.11 and validating under Python 3.11 where available.
- Lockfile regeneration may change tool dependency versions → Mitigate by reviewing the lockfile diff and keeping runtime dependencies unchanged.
- Local environment may not have Python 3.11 installed → Mitigate by documenting that tests must run in a Python 3.11 environment or through the configured package manager.
