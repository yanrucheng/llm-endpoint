"""Capability profile catalog for offline provider/model-family validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from llm_endpoint.config import ProviderFormat, ReasoningMode, StructuredOutputMode

CAPABILITY_CATALOG_VERSION = "v1"


class CapabilityFlag(StrEnum):
    """Provider/model-family facts consumed by planning and policy resolution."""

    STRUCTURED_JSON_SCHEMA = "structured_json_schema"
    STRUCTURED_TOOL_CALL = "structured_tool_call"
    REASONING_CONTROL = "reasoning_control"
    TOKEN_USAGE = "token_usage"


@dataclass(frozen=True, slots=True)
class CapabilityHardLimits:
    """Hard provider limits known without live calls."""

    max_output_tokens: int
    max_deadline_ms: int | None = None

    def __post_init__(self) -> None:
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if self.max_deadline_ms is not None and self.max_deadline_ms <= 0:
            raise ValueError("max_deadline_ms must be omitted or positive")


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    """Maintainer-owned source for a capability claim."""

    source: str
    note: str

    def __post_init__(self) -> None:
        if not self.source or not self.note:
            raise ValueError("capability evidence requires source and note")


@dataclass(frozen=True, slots=True)
class CapabilityProfile:
    """Provider-format x model-family capability profile."""

    provider_format: ProviderFormat
    model_family: str
    hard_limits: CapabilityHardLimits
    supported_capabilities: frozenset[CapabilityFlag] = field(default_factory=frozenset)
    supported_reasoning_modes: frozenset[ReasoningMode] = field(
        default_factory=lambda: frozenset({ReasoningMode.DISABLED})
    )
    evidence: CapabilityEvidence = field(
        default_factory=lambda: CapabilityEvidence(
            source="maintainer-fixture",
            note="phase-2 default profile",
        )
    )

    def __post_init__(self) -> None:
        if not self.model_family:
            raise ValueError("model_family is required")
        if ReasoningMode.DISABLED not in self.supported_reasoning_modes:
            raise ValueError("disabled reasoning mode must always be supported")

    def supports_structured_output(self, mode: StructuredOutputMode) -> bool:
        """Return whether this profile supports a structured-output mode."""

        if mode is StructuredOutputMode.NONE:
            return True
        if mode is StructuredOutputMode.JSON_SCHEMA:
            return CapabilityFlag.STRUCTURED_JSON_SCHEMA in self.supported_capabilities
        if mode is StructuredOutputMode.TOOL_CALL:
            return CapabilityFlag.STRUCTURED_TOOL_CALL in self.supported_capabilities
        return False

    def supports_reasoning_mode(self, mode: ReasoningMode) -> bool:
        """Return whether this profile supports the requested reasoning mode."""

        return mode in self.supported_reasoning_modes


@dataclass(frozen=True, slots=True)
class CapabilityCatalog:
    """Immutable offline lookup for provider/model-family facts."""

    profiles: tuple[CapabilityProfile, ...]
    version: str = CAPABILITY_CATALOG_VERSION

    def __post_init__(self) -> None:
        if self.version != CAPABILITY_CATALOG_VERSION:
            raise ValueError(
                "only capability catalog version 'v1' is supported under Zero BC policy"
            )
        seen: set[tuple[ProviderFormat, str]] = set()
        for profile in self.profiles:
            key = (profile.provider_format, profile.model_family)
            if key in seen:
                raise ValueError(
                    "duplicate capability profile: "
                    f"{profile.provider_format}/{profile.model_family}"
                )
            seen.add(key)

    def get(self, provider_format: ProviderFormat, model_family: str) -> CapabilityProfile | None:
        """Return a known profile or None for fail-closed unknown families."""

        for profile in self.profiles:
            if profile.provider_format is provider_format and profile.model_family == model_family:
                return profile
        return None

    def require(self, provider_format: ProviderFormat, model_family: str) -> CapabilityProfile:
        """Return a profile or raise a safe validation error."""

        profile = self.get(provider_format, model_family)
        if profile is None:
            raise KeyError(f"unsupported provider/model_family: {provider_format}/{model_family}")
        return profile


DEFAULT_CAPABILITY_CATALOG = CapabilityCatalog(
    profiles=(
        CapabilityProfile(
            provider_format=ProviderFormat.FAKE,
            model_family="fake-family",
            hard_limits=CapabilityHardLimits(max_output_tokens=8_192, max_deadline_ms=60_000),
            supported_capabilities=frozenset(
                {
                    CapabilityFlag.STRUCTURED_JSON_SCHEMA,
                    CapabilityFlag.STRUCTURED_TOOL_CALL,
                    CapabilityFlag.TOKEN_USAGE,
                }
            ),
            supported_reasoning_modes=frozenset(
                {
                    ReasoningMode.DISABLED,
                    ReasoningMode.LOW,
                    ReasoningMode.MEDIUM,
                    ReasoningMode.HIGH,
                }
            ),
            evidence=CapabilityEvidence(
                source="tests/contracts",
                note="fake provider supports every Phase 2 planning path offline",
            ),
        ),
    )
)
