## ADDED Requirements

### Requirement: Python 3.11 package compatibility
The package SHALL declare Python 3.11 as its minimum supported runtime version and SHALL avoid syntax that prevents parsing on Python 3.11.

#### Scenario: Python floor is declared
- **WHEN** package metadata is inspected
- **THEN** the Python requirement is `>=3.11`

#### Scenario: Source parses on Python 3.11
- **WHEN** the package source is loaded with Python 3.11
- **THEN** no Python 3.12-only syntax prevents parsing or import

### Requirement: Local tooling targets Python 3.11
The repository SHALL include local tooling configuration that selects and validates against Python 3.11 as the compatibility floor.

#### Scenario: Local Python version is selected
- **WHEN** a developer enters the repository with a Python version manager that reads `.python-version`
- **THEN** Python 3.11 is selected for the project

#### Scenario: Lint target matches supported floor
- **WHEN** lint tooling evaluates syntax compatibility
- **THEN** it targets Python 3.11 rather than Python 3.12

### Requirement: Existing behavior remains covered by tests
The migration SHALL preserve existing runtime behavior and public APIs while lowering the Python version requirement.

#### Scenario: Test suite passes after migration
- **WHEN** the existing test suite is run after the compatibility migration
- **THEN** the tests pass without requiring Python 3.12
