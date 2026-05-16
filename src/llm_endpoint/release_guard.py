"""Zero BC public surface checker for release readiness."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from llm_endpoint.public_surface import (
    PUBLIC_SURFACES,
    CompatibilityLevel,
    PublicSurface,
    SurfaceKind,
)

COMPATIBILITY_CHECKER_VERSION = "v1"


class CompatibilityIssueCode(StrEnum):
    """Machine-readable release-readiness issue codes."""

    NON_ZERO_BC_SURFACE = "non_zero_bc_surface"
    MISSING_CHANGELOG = "missing_changelog"
    MISSING_MIGRATION_NOTE = "missing_migration_note"
    PUBLIC_SURFACE_ADDED = "public_surface_added"
    PUBLIC_SURFACE_REMOVED = "public_surface_removed"
    PUBLIC_SURFACE_CHANGED = "public_surface_changed"
    INVALID_PRE_V1_SEMVER = "invalid_pre_v1_semver"


@dataclass(frozen=True, slots=True)
class PublicSurfaceSnapshot:
    """Serializable public surface baseline entry."""

    name: str
    kind: str
    owner: str
    version_rule: str
    compatibility_level: str


@dataclass(frozen=True, slots=True)
class CompatibilityIssue:
    """One public surface release-readiness issue."""

    code: CompatibilityIssueCode
    message: str
    surface_name: str | None = None


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    """Compatibility guard result for release automation."""

    ok: bool
    issues: tuple[CompatibilityIssue, ...]
    checker_version: str = COMPATIBILITY_CHECKER_VERSION

    def __post_init__(self) -> None:
        if self.checker_version != COMPATIBILITY_CHECKER_VERSION:
            raise ValueError("only compatibility checker version 'v1' is supported")
        if self.ok != (not self.issues):
            raise ValueError("ok must match whether compatibility issues are empty")


def capture_public_surface_baseline(
    surfaces: Iterable[PublicSurface] = PUBLIC_SURFACES,
) -> tuple[PublicSurfaceSnapshot, ...]:
    """Capture the current manifest as a deterministic Zero BC baseline."""

    return tuple(
        sorted(
            (
                PublicSurfaceSnapshot(
                    name=surface.name,
                    kind=surface.kind.value,
                    owner=surface.owner,
                    version_rule=surface.version_rule,
                    compatibility_level=surface.compatibility_level.value,
                )
                for surface in surfaces
            ),
            key=lambda surface: surface.name,
        )
    )


def check_public_surface_release(
    *,
    current_surfaces: Iterable[PublicSurface] = PUBLIC_SURFACES,
    baseline: Iterable[PublicSurfaceSnapshot] = (),
    changelog_entries: Iterable[str] = (),
    migration_notes: Iterable[str] = (),
    package_version: str = "0.1.0",
) -> CompatibilityReport:
    """Enforce Zero BC surface policy and release-note evidence."""

    current = tuple(current_surfaces)
    baseline_by_name = {surface.name: surface for surface in baseline}
    current_by_name = {surface.name: surface for surface in current}
    issues: list[CompatibilityIssue] = []

    issues.extend(_zero_bc_issues(current))
    surface_diff_issues = _surface_diff_issues(current_by_name, baseline_by_name)
    if surface_diff_issues and not _contains_evidence(changelog_entries, "public surface"):
        issues.extend(surface_diff_issues)
        issues.append(
            CompatibilityIssue(
                code=CompatibilityIssueCode.MISSING_CHANGELOG,
                message="public surface changes require a changelog entry",
            )
        )
    if surface_diff_issues and not _contains_evidence(migration_notes, "zero bc"):
        issues.extend(surface_diff_issues)
        issues.append(
            CompatibilityIssue(
                code=CompatibilityIssueCode.MISSING_MIGRATION_NOTE,
                message="public surface changes require Zero BC migration notes",
            )
        )
    if not package_version.startswith("0."):
        issues.append(
            CompatibilityIssue(
                code=CompatibilityIssueCode.INVALID_PRE_V1_SEMVER,
                message="Zero BC checker accepts only pre-V1 package versions",
            )
        )

    return CompatibilityReport(ok=not issues, issues=tuple(issues))


def public_surface_snapshot_mapping(
    baseline: Iterable[PublicSurfaceSnapshot],
) -> Mapping[str, PublicSurfaceSnapshot]:
    """Return a name-indexed baseline mapping for release tooling."""

    return {surface.name: surface for surface in baseline}


def _zero_bc_issues(surfaces: tuple[PublicSurface, ...]) -> tuple[CompatibilityIssue, ...]:
    return tuple(
        CompatibilityIssue(
            code=CompatibilityIssueCode.NON_ZERO_BC_SURFACE,
            surface_name=surface.name,
            message="public surfaces must remain Zero BC before production release",
        )
        for surface in surfaces
        if surface.compatibility_level is not CompatibilityLevel.ZERO_BC
    )


def _surface_diff_issues(
    current_by_name: Mapping[str, PublicSurface],
    baseline_by_name: Mapping[str, PublicSurfaceSnapshot],
) -> tuple[CompatibilityIssue, ...]:
    issues: list[CompatibilityIssue] = []
    for name in sorted(current_by_name.keys() - baseline_by_name.keys()):
        issues.append(
            CompatibilityIssue(
                code=CompatibilityIssueCode.PUBLIC_SURFACE_ADDED,
                surface_name=name,
                message="public surface was added",
            )
        )
    for name in sorted(baseline_by_name.keys() - current_by_name.keys()):
        issues.append(
            CompatibilityIssue(
                code=CompatibilityIssueCode.PUBLIC_SURFACE_REMOVED,
                surface_name=name,
                message="public surface was removed",
            )
        )
    for name in sorted(current_by_name.keys() & baseline_by_name.keys()):
        if _snapshot(current_by_name[name]) != baseline_by_name[name]:
            issues.append(
                CompatibilityIssue(
                    code=CompatibilityIssueCode.PUBLIC_SURFACE_CHANGED,
                    surface_name=name,
                    message="public surface metadata changed",
                )
            )
    return tuple(issues)


def _snapshot(surface: PublicSurface) -> PublicSurfaceSnapshot:
    return PublicSurfaceSnapshot(
        name=surface.name,
        kind=_kind_value(surface.kind),
        owner=surface.owner,
        version_rule=surface.version_rule,
        compatibility_level=surface.compatibility_level.value,
    )


def _kind_value(kind: SurfaceKind | str) -> str:
    return kind.value if isinstance(kind, SurfaceKind) else kind


def _contains_evidence(entries: Iterable[str], phrase: str) -> bool:
    return any(phrase in entry.lower() for entry in entries)
