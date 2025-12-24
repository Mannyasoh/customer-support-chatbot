"""Intent classification service using OpenAI"""
import json
from typing import Dict, List

from openai import AsyncOpenAI

from config import INTENT_CATEGORIES, Config

from .langfuse_client import langfuse_client


class IntentClassifier:
    """LLM-based intent classification service"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.OPENAI_MODEL

    async def classify_intent(self, message: str, customer: str, trace=None) -> Dict:
        """
        Classify customer intent using LLM

        Args:
            message: Customer message
            customer: Customer email
            trace: Langfuse trace for observability

        Returns:
            Dict with intent, confidence, entities, and reasoning
        """
        try:
            system_prompt = self._build_system_prompt()
            user_prompt = f"Customer: {customer}\nMessage: {message}"

            # Log to Langfuse
            generation = None
            if trace:
                generation = langfuse_client.log_generation(
                    trace=trace,
                    name="intent_classification",
                    input_data={
                        "system_prompt": system_prompt,
                        "user_message": message,
                        "customer": customer,
                    },
                    output_data={},
                    model=self.model,
                    metadata={"service": "intent_classifier"},
                )

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=Config.INTENT_MAX_TOKENS,
                temperature=Config.INTENT_TEMPERATURE,
            )

            result = json.loads(response.choices[0].message.content)
            print(f"Intent classification: {result}")

            # Update Langfuse generation
            if generation:
                langfuse_client.log_generation(
                    trace=trace,
                    name="intent_classification",
                    input_data={
                        "system_prompt": system_prompt,
                        "user_message": message,
                        "customer": customer,
                    },
                    output_data=result,
                    model=self.model,
                    tokens_used={
                        "input": response.usage.prompt_tokens,
                        "output": response.usage.completion_tokens,
                        "total": response.usage.total_tokens,
                    }
                    if response.usage
                    else None,
                    metadata={"service": "intent_classifier"},
                )

                # Score the classification confidence
                langfuse_client.score_generation(
                    generation=generation,
                    score_name="confidence",
                    score_value=result.get("confidence", 0.0),
                    comment=f"Intent: {result.get('intent', 'unknown')}",
                )

            return result

        except Exception as e:
            print(f"Intent classification error: {e}")
            error_result = {
                "intent": "OTHER",
                "confidence": 0.5,
                "entities": [],
                "reasoning": "Classification failed",
            }

            # Log error to Langfuse
            if trace:
                langfuse_client.log_event(
                    trace=trace,
                    name="intent_classification_error",
                    metadata={"error": str(e), "service": "intent_classifier"},
                )

            return error_result

    def _build_system_prompt(self) -> str:
        """Build the system prompt for intent classification"""
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
        """Get description for each intent category"""
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
