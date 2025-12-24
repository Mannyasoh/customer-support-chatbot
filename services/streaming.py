import asyncio
from typing import Any, AsyncGenerator, Dict

from fastapi import Request
from loguru import logger

from config import Config


class StreamingService:
    def __init__(self):
        self.char_threshold = Config.CHAR_STREAMING_THRESHOLD
        self.word_threshold = Config.WORD_STREAMING_THRESHOLD
        self.char_delay = Config.CHAR_STREAM_DELAY
        self.word_delay = Config.WORD_STREAM_DELAY
        self.line_delay = Config.LINE_STREAM_DELAY
        self.max_display = Config.MAX_PRODUCTS_DISPLAY
        self.truncation_enabled = Config.PRODUCT_TRUNCATION_ENABLED

    async def stream_response(
        self, response: str, request: Request, intent: str | None = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        response = self._handle_product_truncation(response)

        if intent == "PLACE_ORDER":
            response += "\n\n🛒 To place an order for any of these products, please contact our sales team or visit our website. Note: This demo doesn't process actual orders."

        logger.debug(f"Streaming response length: {len(response)} chars")

        if len(response) <= self.char_threshold:
            async for chunk in self._stream_by_character(response, request):
                yield chunk
        elif len(response) <= self.word_threshold:
            async for chunk in self._stream_by_word(response, request):
                yield chunk
        else:
            async for chunk in self._stream_by_line(response, request):
                yield chunk

        logger.debug("Sending DONE signal")
        yield {"data": "[DONE]"}

    async def _stream_by_character(
        self, response: str, request: Request
    ) -> AsyncGenerator[Dict[str, str], None]:
        for char in response:
            if await request.is_disconnected():
                break
            yield {"data": char}
            await asyncio.sleep(self.char_delay)

    async def _stream_by_word(
        self, response: str, request: Request
    ) -> AsyncGenerator[Dict[str, str], None]:
        words = response.split(" ")
        for word in words:
            if await request.is_disconnected():
                break
            yield {"data": word + " "}
            await asyncio.sleep(self.word_delay)

    async def _stream_by_line(
        self, response: str, request: Request
    ) -> AsyncGenerator[Dict[str, str], None]:
        lines = response.split("\n")
        for line in lines:
            if await request.is_disconnected():
                break
            yield {"data": line + "\n"}
            await asyncio.sleep(self.line_delay)

    def _handle_product_truncation(self, response: str) -> str:
        if not self.truncation_enabled:
            return response

        if "Found 200 products:" in response:
            lines = response.split("\n")
            summary = lines[0]
            products = [line for line in lines[1:] if line.strip() and "[" in line][
                : self.max_display
            ]

            truncated_response = (
                summary + "\n\n" + "\n\n".join(products[: self.max_display])
            )
            if len(products) > self.max_display:
                remaining = 200 - self.max_display
                truncated_response += f"\n\n... and {remaining} more products.\nType 'search [keyword]' to find specific items or 'list monitors' for category browsing."

            logger.debug(f"Truncated to {len(truncated_response)} chars for better UX")
            return truncated_response

        return response


def get_simple_response(msg: str, customer: str) -> str:
    msg_lower = msg.lower()
    if any(word in msg_lower for word in ["hello", "hi", "hey"]):
        return f"Hello {customer}! How can I help with your computer products today?"
    if any(word in msg_lower for word in ["thank", "thanks"]):
        return "You're welcome! Is there anything else I can help you with?"
    if any(word in msg_lower for word in ["bye", "goodbye"]):
        return "Goodbye! Have a great day, and feel free to reach out if you need any help."
    return "I can help with orders, products, warranties, and technical issues. What do you need?"
