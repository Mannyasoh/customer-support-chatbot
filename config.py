"""Configuration module for Customer Support Chatbot"""
import os
from typing import Any, Dict

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration class"""

    # OpenAI Settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # MCP Server Settings
    MCP_SERVER_URL: str = os.getenv("MCP_SERVER_URL", "")
    MCP_TIMEOUT: float = float(os.getenv("MCP_TIMEOUT", "30"))

    # Application Settings
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    APP_TITLE: str = os.getenv("APP_TITLE", "Customer Support Chatbot")

    # Intent Classification Settings
    INTENT_CONFIDENCE_THRESHOLD: float = float(
        os.getenv("INTENT_CONFIDENCE_THRESHOLD", "0.7")
    )
    INTENT_MAX_TOKENS: int = int(os.getenv("INTENT_MAX_TOKENS", "150"))
    INTENT_TEMPERATURE: float = float(os.getenv("INTENT_TEMPERATURE", "0.1"))

    # Streaming Configuration
    CHAR_STREAMING_THRESHOLD: int = int(os.getenv("CHAR_STREAMING_THRESHOLD", "200"))
    WORD_STREAMING_THRESHOLD: int = int(os.getenv("WORD_STREAMING_THRESHOLD", "1000"))
    CHAR_STREAM_DELAY: float = float(os.getenv("CHAR_STREAM_DELAY", "0.04"))
    WORD_STREAM_DELAY: float = float(os.getenv("WORD_STREAM_DELAY", "0.08"))
    LINE_STREAM_DELAY: float = float(os.getenv("LINE_STREAM_DELAY", "0.1"))

    # Product Configuration
    MAX_PRODUCTS_DISPLAY: int = int(os.getenv("MAX_PRODUCTS_DISPLAY", "8"))
    PRODUCT_TRUNCATION_ENABLED: bool = (
        os.getenv("PRODUCT_TRUNCATION_ENABLED", "true").lower() == "true"
    )

    # Langfuse Configuration
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration values"""
        required_vars = ["OPENAI_API_KEY", "MCP_SERVER_URL"]
        missing = [var for var in required_vars if not getattr(cls, var)]

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

        return True


# Test customer data - in production, this would come from a database
CUSTOMERS: Dict[str, str] = {
    "donaldgarcia@example.net": "7912",
    "michellejames@example.com": "1520",
    "laurahenderson@example.org": "1488",
    "spenceamanda@example.org": "2535",
    "glee@example.net": "4582",
    "williamsthomas@example.net": "4811",
    "justin78@example.net": "9279",
    "jason31@example.com": "1434",
    "samuel81@example.com": "4257",
    "williamleon@example.net": "9928",
}

# Intent categories for LLM classification
INTENT_CATEGORIES = [
    "SEARCH_PRODUCTS",
    "ORDER_STATUS",
    "PLACE_ORDER",
    "WARRANTY_SUPPORT",
    "TECH_SUPPORT",
    "GREETING",
    "ACCOUNT_INFO",
    "OTHER",
]

# MCP tool configurations
MCP_TOOLS = {
    "verify_customer_pin": {
        "description": "Verify customer email/PIN and get customer ID",
        "params": ["email", "pin"],
    },
    "get_customer": {
        "description": "Get detailed customer information",
        "params": ["customer_id"],
    },
    "list_products": {"description": "Browse product catalog", "params": ["category"]},
    "search_products": {"description": "Search products by query", "params": ["query"]},
    "get_product": {
        "description": "Get specific product details",
        "params": ["product_id"],
    },
    "list_orders": {
        "description": "Get customer's order history",
        "params": ["customer_id"],
    },
    "get_order": {"description": "Get specific order details", "params": ["order_id"]},
    "create_order": {
        "description": "Place new order",
        "params": ["customer_id", "product_id", "quantity"],
    },
}
