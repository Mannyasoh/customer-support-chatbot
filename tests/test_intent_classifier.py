"""Tests for intent classification service"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.intent_classifier import IntentClassifier


class TestIntentClassifier:
    """Test intent classification functionality"""

    @pytest.fixture
    def classifier(self):
        """Create intent classifier instance"""
        return IntentClassifier()

    @pytest.fixture
    def mock_openai_response(self):
        """Mock OpenAI API response"""
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(
            {
                "intent": "SEARCH_PRODUCTS",
                "confidence": 0.95,
                "entities": ["gaming", "laptop"],
                "reasoning": "Customer looking for gaming laptop",
            }
        )

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        return mock_response

    @pytest.mark.asyncio
    async def test_classify_intent_success(self, classifier, mock_openai_response):
        """Test successful intent classification"""
        with patch.object(
            classifier.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_openai_response
            result = await classifier.classify_intent(
                "I want a gaming laptop", "test@example.com"
            )

            assert result["intent"] == "SEARCH_PRODUCTS"
            assert result["confidence"] == 0.95
            assert "gaming" in result["entities"]
            assert "laptop" in result["entities"]

    @pytest.mark.asyncio
    async def test_classify_intent_api_error(self, classifier):
        """Test intent classification with API error"""
        with patch.object(
            classifier.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=Exception("API Error"),
        ):
            result = await classifier.classify_intent(
                "test message", "test@example.com"
            )

            assert result["intent"] == "OTHER"
            assert result["confidence"] == 0.5
            assert result["entities"] == []
            assert "Classification failed" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_classify_intent_invalid_json(self, classifier):
        """Test intent classification with invalid JSON response"""
        mock_choice = MagicMock()
        mock_choice.message.content = "Invalid JSON"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch.object(
            classifier.client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await classifier.classify_intent(
                "test message", "test@example.com"
            )

            assert result["intent"] == "OTHER"
            assert result["confidence"] == 0.5

    def test_get_category_description(self, classifier):
        """Test category description mapping"""
        assert "Looking for products" in classifier._get_category_description(
            "SEARCH_PRODUCTS"
        )
        assert "Checking order status" in classifier._get_category_description(
            "ORDER_STATUS"
        )
        assert "Unknown category" in classifier._get_category_description(
            "INVALID_CATEGORY"
        )

    def test_build_system_prompt(self, classifier):
        """Test system prompt construction"""
        prompt = classifier._build_system_prompt()

        assert "intent classifier" in prompt
        assert "SEARCH_PRODUCTS" in prompt
        assert "ORDER_STATUS" in prompt
        assert "JSON" in prompt
