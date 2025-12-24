import json
from typing import Any, Dict

from langfuse import observe
from loguru import logger
from openai import AsyncOpenAI

from config import INTENT_CATEGORIES, Config


class IntentClassifier:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=Config.OPENAI_API_KEY,
            timeout=30.0,
            max_retries=3,
        )
        self.model = Config.OPENAI_MODEL

    @observe(name="intent-classification", as_type="generation")
    async def classify_intent(self, message: str, customer: str) -> Dict[str, Any]:
        try:
            system_prompt = self._build_system_prompt()
            user_prompt = f"Customer: {customer}\nMessage: {message}"

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=Config.INTENT_MAX_TOKENS,
                temperature=Config.INTENT_TEMPERATURE,
            )

            result: Dict[str, Any] = json.loads(response.choices[0].message.content)
            logger.debug(f"Intent classification: {result}")
            return result

        except Exception as e:
            logger.error(f"Intent classification error: {e}")
            return {
                "intent": "OTHER",
                "confidence": 0.5,
                "entities": [],
                "reasoning": "Classification failed",
            }

    def _build_system_prompt(self) -> str:
        categories_text = "\n".join(
            [
                f"- {cat}: {self._get_category_description(cat)}"
                for cat in INTENT_CATEGORIES
            ]
        )

        return f"""You are an intent classifier for a computer products customer support chatbot.

Classify the customer message into ONE of these categories:
{categories_text}

Extract key entities like product names, order numbers, issues.

Return ONLY valid JSON in this exact format:
{{"intent": "CATEGORY", "confidence": 0.95, "entities": ["key", "terms"], "reasoning": "brief explanation"}}"""

    def _get_category_description(self, category: str) -> str:
        descriptions = {
            "SEARCH_PRODUCTS": "Looking for products, browsing, specifications",
            "ORDER_STATUS": "Checking order status, delivery, tracking",
            "PLACE_ORDER": "Wanting to buy, purchase, order a product",
            "WARRANTY_SUPPORT": "Warranty claims, returns, repairs",
            "TECH_SUPPORT": "Technical issues, setup help, troubleshooting",
            "GREETING": "Hello, hi, general greeting",
            "ACCOUNT_INFO": "Account details, login issues, customer info",
            "OTHER": "Anything that doesn't fit above categories",
        }
        return descriptions.get(category, "Unknown category")
