import pytest

from llm_endpoint.capabilities import (
    CAPABILITY_CATALOG_VERSION,
    DEFAULT_CAPABILITY_CATALOG,
    CapabilityCatalog,
    CapabilityHardLimits,
    CapabilityProfile,
)
from llm_endpoint.config import ProviderFormat, ReasoningMode, StructuredOutputMode


def test_default_catalog_lookup() -> None:
    profile = DEFAULT_CAPABILITY_CATALOG.require(ProviderFormat.FAKE, "fake-family")

    assert DEFAULT_CAPABILITY_CATALOG.version == CAPABILITY_CATALOG_VERSION
    assert profile.hard_limits.max_output_tokens == 8_192
    assert profile.supports_reasoning_mode(ReasoningMode.HIGH)
    assert profile.supports_structured_output(StructuredOutputMode.JSON_SCHEMA)


def test_unknown_model_family_fails_closed() -> None:
    assert DEFAULT_CAPABILITY_CATALOG.get(ProviderFormat.FAKE, "missing-family") is None

    with pytest.raises(KeyError):
        DEFAULT_CAPABILITY_CATALOG.require(ProviderFormat.FAKE, "missing-family")


def test_duplicate_profile_is_rejected() -> None:
    profile = CapabilityProfile(
        provider_format=ProviderFormat.FAKE,
        model_family="duplicate-family",
        hard_limits=CapabilityHardLimits(max_output_tokens=1),
    )

    with pytest.raises(ValueError, match="duplicate capability profile"):
        CapabilityCatalog((profile, profile))
