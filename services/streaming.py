"""Response streaming service"""
import asyncio
from typing import AsyncGenerator, Dict

from fastapi import Request

from config import Config


class StreamingService:
    """Service for streaming responses with smart pacing"""

    def __init__(self):
        self.char_threshold = Config.CHAR_STREAMING_THRESHOLD
        self.word_threshold = Config.WORD_STREAMING_THRESHOLD
        self.char_delay = Config.CHAR_STREAM_DELAY
        self.word_delay = Config.WORD_STREAM_DELAY
        self.line_delay = Config.LINE_STREAM_DELAY
        self.max_display = Config.MAX_PRODUCTS_DISPLAY
        self.truncation_enabled = Config.PRODUCT_TRUNCATION_ENABLED

    async def stream_response(
        self, response: str, request: Request, intent: str = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Stream response with smart pacing based on content length

        Args:
            response: Text to stream
            request: FastAPI request object
            intent: Intent classification for special handling

        Yields:
            Dict with 'data' key containing chunk
        """
        # Handle large product lists specially
        response = self._handle_product_truncation(response)

        # Add ordering instructions for PLACE_ORDER intent
        if intent == "PLACE_ORDER":
            response += "\n\n🛒 To place an order for any of these products, please contact our sales team or visit our website. Note: This demo doesn't process actual orders."

        print(f"Streaming response length: {len(response)} chars")

        # Choose streaming strategy based on response length
        if len(response) <= self.char_threshold:
            async for chunk in self._stream_by_character(response, request):
                yield chunk
        elif len(response) <= self.word_threshold:
            async for chunk in self._stream_by_word(response, request):
                yield chunk
        else:
            async for chunk in self._stream_by_line(response, request):
                yield chunk

        print("Sending DONE signal")
        yield {"data": "[DONE]"}

    async def _stream_by_character(
        self, response: str, request: Request
    ) -> AsyncGenerator[Dict, None]:
        """Stream response character by character for conversational feel"""
        for char in response:
            if await request.is_disconnected():
                break
            yield {"data": char}
            await asyncio.sleep(self.char_delay)

    async def _stream_by_word(
        self, response: str, request: Request
    ) -> AsyncGenerator[Dict, None]:
        """Stream response word by word for medium responses"""
        words = response.split(" ")
        for word in words:
            if await request.is_disconnected():
                break
            yield {"data": word + " "}
            await asyncio.sleep(self.word_delay)

    async def _stream_by_line(
        self, response: str, request: Request
    ) -> AsyncGenerator[Dict, None]:
        """Stream response line by line for large responses"""
        lines = response.split("\n")
        for line in lines:
            if await request.is_disconnected():
                break
            yield {"data": line + "\n"}
            await asyncio.sleep(self.line_delay)

    def _handle_product_truncation(self, response: str) -> str:
        """Truncate large product lists for better UX"""
        if not self.truncation_enabled:
            return response

        if "Found 200 products:" in response:
            lines = response.split("\n")
            summary = lines[0]  # "Found 200 products:"
            products = [line for line in lines[1:] if line.strip() and "[" in line][
                : self.max_display
            ]

            truncated_response = (
                summary + "\n\n" + "\n\n".join(products[: self.max_display])
            )
            if len(products) > self.max_display:
                remaining = 200 - self.max_display
                truncated_response += f"\n\n... and {remaining} more products.\nType 'search [keyword]' to find specific items or 'list monitors' for category browsing."

            print(f"Truncated to {len(truncated_response)} chars for better UX")
            return truncated_response

        return response


def get_simple_response(msg: str, customer: str) -> str:
    """Enhanced simple response logic using basic patterns"""
    msg = msg.lower()
    if "hello" in msg or "hi" in msg or "hey" in msg:
        return f"Hello {customer}! How can I help with your computer products today?"
    if "thank" in msg or "thanks" in msg:
        return "You're welcome! Is there anything else I can help you with?"
    if "bye" in msg or "goodbye" in msg:
        return "Goodbye! Have a great day, and feel free to reach out if you need any help."
    return "I can help with orders, products, warranties, and technical issues. What do you need?"
