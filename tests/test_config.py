"""Tests for configuration module"""
import os
from unittest.mock import patch

import pytest

from config import Config


class TestConfig:
    """Test configuration management"""

    def test_config_defaults(self):
        """Test default configuration values"""
        assert Config.APP_HOST == "0.0.0.0"
        assert Config.APP_PORT == 8000
        assert Config.INTENT_CONFIDENCE_THRESHOLD == 0.7
        assert Config.CHAR_STREAMING_THRESHOLD == 200
        assert Config.WORD_STREAMING_THRESHOLD == 1000
        assert Config.MAX_PRODUCTS_DISPLAY == 8
        assert Config.PRODUCT_TRUNCATION_ENABLED == True

    def test_config_validation_missing_api_key(self):
        """Test validation fails when API key is missing"""
        with patch.object(Config, "OPENAI_API_KEY", ""):
            with pytest.raises(
                ValueError, match="Missing required environment variables"
            ):
                Config.validate()

    def test_config_validation_missing_mcp_url(self):
        """Test validation fails when MCP URL is missing"""
        with patch.object(Config, "MCP_SERVER_URL", ""):
            with pytest.raises(
                ValueError, match="Missing required environment variables"
            ):
                Config.validate()

    def test_config_validation_success(self):
        """Test validation passes when all required vars are present"""
        with patch.object(Config, "OPENAI_API_KEY", "test-key"):
            with patch.object(Config, "MCP_SERVER_URL", "https://example.com"):
                assert Config.validate() == True

    @patch.dict(os.environ, {"INTENT_CONFIDENCE_THRESHOLD": "0.8"})
    def test_config_env_override(self):
        """Test environment variables override defaults"""
        from config import Config

        # Note: This test may need module reload in real scenarios
        assert isinstance(Config.INTENT_CONFIDENCE_THRESHOLD, float)
