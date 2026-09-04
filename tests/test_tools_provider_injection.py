from unittest.mock import Mock

import pytest

from hcaptcha_challenger.tools.challenge_router import ChallengeRouter
from hcaptcha_challenger.tools.image_classifier import ImageClassifier
from hcaptcha_challenger.tools.internal import base
from hcaptcha_challenger.tools.spatial import (
    SpatialBboxReasoner,
    SpatialPathReasoner,
    SpatialPointReasoner,
)

TOOL_CLASSES = (
    ImageClassifier,
    ChallengeRouter,
    SpatialPathReasoner,
    SpatialPointReasoner,
    SpatialBboxReasoner,
)


class SyntheticProvider:
    def __bool__(self):
        return False


@pytest.mark.parametrize("tool_class", TOOL_CLASSES)
def test_synthetic_provider_is_injected_directly(tool_class):
    provider = SyntheticProvider()

    tool = tool_class("unused-key", "synthetic-model", provider=provider)

    assert tool._provider is provider


@pytest.mark.parametrize("tool_class", TOOL_CLASSES)
def test_synthetic_default_provider_uses_gemini(tool_class, monkeypatch):
    provider = Mock()
    gemini_provider = Mock(return_value=provider)
    monkeypatch.setattr(base, "GeminiProvider", gemini_provider)

    tool = tool_class("gemini-key", "gemini-model")

    gemini_provider.assert_called_once_with(api_key="gemini-key", model="gemini-model")
    assert tool._provider is provider
