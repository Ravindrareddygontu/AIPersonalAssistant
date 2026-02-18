"""
Tests for config.py - Settings class and model configuration.

Tests cover:
- Settings class: workspace, model, history_enabled, slack_notify, slack_webhook_url
- get_auggie_model_id: Converting display names to CLI model IDs
- AVAILABLE_MODELS, MODEL_ID_MAP constants
- SKIP_PATTERNS, BOX_CHARS_PATTERN
"""

import pytest
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import (
    Settings, AVAILABLE_MODELS, MODEL_ID_MAP, DEFAULT_MODEL,
    get_auggie_model_id, SKIP_PATTERNS, BOX_CHARS_PATTERN
)


class TestSettingsClass:
    """Test the Settings class."""

    def test_default_workspace(self):
        """Test default workspace is set."""
        settings = Settings()
        assert settings.workspace is not None
        assert "ai-chat-app" in settings.workspace

    def test_workspace_setter_expands_home(self):
        """Test that workspace setter expands ~ to home directory."""
        settings = Settings()
        settings.workspace = "~/test-project"
        assert settings.workspace.startswith("/home") or settings.workspace.startswith("/Users")
        assert "~" not in settings.workspace

    def test_default_model(self):
        """Test default model is set."""
        settings = Settings()
        assert settings.model == DEFAULT_MODEL

    def test_model_setter_valid(self):
        """Test setting a valid model."""
        settings = Settings()
        settings.model = 'gpt-4o'
        assert settings.model == 'gpt-4o'

    def test_model_setter_invalid(self):
        """Test that invalid model is rejected."""
        settings = Settings()
        original_model = settings.model
        settings.model = 'invalid-model'
        assert settings.model == original_model  # Unchanged

    def test_history_enabled_default(self):
        """Test default history_enabled state."""
        settings = Settings()
        assert settings.history_enabled == True

    def test_history_enabled_setter(self):
        """Test setting history_enabled."""
        settings = Settings()
        settings.history_enabled = False
        assert settings.history_enabled == False
        settings.history_enabled = True
        assert settings.history_enabled == True

    def test_history_enabled_converts_to_bool(self):
        """Test that history_enabled converts values to bool."""
        settings = Settings()
        settings.history_enabled = 1
        assert settings.history_enabled == True
        settings.history_enabled = 0
        assert settings.history_enabled == False

    def test_slack_notify_default(self):
        """Test default slack_notify state."""
        settings = Settings()
        assert settings.slack_notify == False

    def test_slack_notify_setter(self):
        """Test setting slack_notify."""
        settings = Settings()
        settings.slack_notify = True
        assert settings.slack_notify == True

    def test_slack_webhook_url_setter(self):
        """Test setting slack_webhook_url."""
        settings = Settings()
        settings.slack_webhook_url = "https://hooks.slack.com/services/xxx"
        assert settings.slack_webhook_url == "https://hooks.slack.com/services/xxx"

    def test_slack_webhook_url_handles_none(self):
        """Test that None is converted to empty string."""
        settings = Settings()
        settings.slack_webhook_url = None
        assert settings.slack_webhook_url == ""

    def test_to_dict(self):
        """Test to_dict method."""
        settings = Settings()
        result = settings.to_dict()
        
        assert 'workspace' in result
        assert 'model' in result
        assert 'available_models' in result
        assert 'history_enabled' in result
        assert 'slack_notify' in result
        assert 'slack_webhook_url' in result
        assert result['available_models'] == AVAILABLE_MODELS


class TestGetAuggieModelId:
    """Test model ID conversion."""

    def test_known_models(self):
        """Test conversion of known models."""
        assert get_auggie_model_id('claude-opus-4.5') == 'opus4.5'
        assert get_auggie_model_id('claude-sonnet-4') == 'sonnet4'
        assert get_auggie_model_id('gpt-4o') == 'gpt-4o'
        assert get_auggie_model_id('gpt-4-turbo') == 'gpt-4-turbo'

    def test_unknown_model_returns_itself(self):
        """Test that unknown model returns itself."""
        assert get_auggie_model_id('custom-model') == 'custom-model'


class TestConstants:
    """Test module constants."""

    def test_available_models(self):
        """Test AVAILABLE_MODELS is defined correctly."""
        assert len(AVAILABLE_MODELS) > 0
        assert 'claude-opus-4.5' in AVAILABLE_MODELS
        assert 'gpt-4o' in AVAILABLE_MODELS

    def test_model_id_map(self):
        """Test MODEL_ID_MAP has entries for all available models."""
        for model in AVAILABLE_MODELS:
            assert model in MODEL_ID_MAP

    def test_skip_patterns(self):
        """Test SKIP_PATTERNS is a list of strings."""
        assert isinstance(SKIP_PATTERNS, list)
        assert len(SKIP_PATTERNS) > 0
        assert all(isinstance(p, str) for p in SKIP_PATTERNS)
        # Test some expected patterns
        assert any('Processing response' in p for p in SKIP_PATTERNS)

    def test_box_chars_pattern(self):
        """Test BOX_CHARS_PATTERN regex."""
        # Should match box-only lines
        assert BOX_CHARS_PATTERN.match("╭─────╮")
        assert BOX_CHARS_PATTERN.match("│││")
        assert BOX_CHARS_PATTERN.match("───────")
        # Should not match lines with text
        assert not BOX_CHARS_PATTERN.match("│ Text │")
        assert not BOX_CHARS_PATTERN.match("Hello world")


class TestEnvironmentVariables:
    """Test environment variable handling."""

    @patch.dict(os.environ, {'SLACK_WEBHOOK_URL': 'https://test.slack.com'})
    def test_slack_webhook_from_env(self):
        """Test that SLACK_WEBHOOK_URL is read from environment."""
        # Create new settings to pick up env var
        settings = Settings()
        assert settings.slack_webhook_url == 'https://test.slack.com'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

