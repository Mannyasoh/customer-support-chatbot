"""Integration tests for main application"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app


class TestMainApp:
    """Test main FastAPI application"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)

    def test_health_endpoint(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_config_endpoint(self, client):
        """Test config endpoint"""
        response = client.get("/config")
        assert response.status_code == 200
        data = response.json()
        assert "app_title" in data
        assert "intent_threshold" in data
        assert "streaming_enabled" in data

    def test_auth_endpoint_valid_credentials(self, client):
        """Test authentication with valid credentials"""
        response = client.post(
            "/auth", json={"email": "donaldgarcia@example.net", "pin": "7912"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["customer"] == "donaldgarcia@example.net"

    def test_auth_endpoint_invalid_credentials(self, client):
        """Test authentication with invalid credentials"""
        response = client.post(
            "/auth", json={"email": "invalid@example.com", "pin": "0000"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["customer"] is None

    def test_auth_endpoint_missing_data(self, client):
        """Test authentication with missing data"""
        response = client.post("/auth", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    def test_root_endpoint_returns_html(self, client):
        """Test root endpoint returns HTML chat interface"""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Customer Support Chat" in response.text
        assert "login()" in response.text
        assert "sendMessage()" in response.text

    def test_test_endpoint_file_not_found(self, client):
        """Test /test endpoint when test.html doesn't exist"""
        # This test assumes test.html doesn't exist
        with pytest.raises(FileNotFoundError):
            client.get("/test")

    @patch("main.intent_classifier.classify_intent")
    @patch("main.mcp_client.route_intent_to_mcp")
    @patch("main.mcp_client.execute_mcp_call")
    def test_chat_endpoint_integration(
        self, mock_execute, mock_route, mock_classify, client
    ):
        """Test chat endpoint integration (mocked)"""
        # Mock intent classification
        mock_classify.return_value = {
            "intent": "GREETING",
            "confidence": 0.9,
            "entities": [],
            "reasoning": "Customer greeting",
        }

        # Mock MCP routing (no MCP call for greeting)
        mock_route.return_value = (None, "")

        # Test chat stream endpoint
        response = client.get("/chat/test@example.com?message=hello")

        # Should return streaming response
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]


class TestCustomerData:
    """Test customer data validation"""

    def test_all_test_customers_valid(self):
        """Test all predefined test customers have valid data"""
        from config import CUSTOMERS

        assert len(CUSTOMERS) == 10

        # Check email formats
        for email in CUSTOMERS.keys():
            assert "@" in email
            assert "." in email

        # Check PIN formats (4 digits)
        for pin in CUSTOMERS.values():
            assert len(pin) == 4
            assert pin.isdigit()

    def test_customer_uniqueness(self):
        """Test customer emails and PINs are unique"""
        from config import CUSTOMERS

        emails = list(CUSTOMERS.keys())
        pins = list(CUSTOMERS.values())

        assert len(set(emails)) == len(emails)  # Unique emails
        assert len(set(pins)) == len(pins)  # Unique PINs


class TestIntentCategories:
    """Test intent category definitions"""

    def test_intent_categories_complete(self):
        """Test all required intent categories are defined"""
        from config import INTENT_CATEGORIES

        expected_categories = [
            "SEARCH_PRODUCTS",
            "ORDER_STATUS",
            "PLACE_ORDER",
            "WARRANTY_SUPPORT",
            "TECH_SUPPORT",
            "GREETING",
            "ACCOUNT_INFO",
            "OTHER",
        ]

        for category in expected_categories:
            assert category in INTENT_CATEGORIES

    def test_mcp_tools_defined(self):
        """Test MCP tools are properly defined"""
        from config import MCP_TOOLS

        expected_tools = [
            "verify_customer_pin",
            "get_customer",
            "list_products",
            "search_products",
            "get_product",
            "list_orders",
            "get_order",
            "create_order",
        ]

        for tool in expected_tools:
            assert tool in MCP_TOOLS
            assert "description" in MCP_TOOLS[tool]
            assert "params" in MCP_TOOLS[tool]
