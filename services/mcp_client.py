import json
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger

from config import CUSTOMERS, Config


class MCPClient:
    def __init__(self):
        self.server_url = Config.MCP_SERVER_URL
        self.timeout = httpx.Timeout(Config.MCP_TIMEOUT)
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)

    async def route_intent_to_mcp(
        self, intent: str, entities: List[str], message: str, customer: str
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        async with httpx.AsyncClient(
            timeout=self.timeout, limits=self.limits, headers=self.headers
        ) as client:
            if intent == "SEARCH_PRODUCTS":
                return await self._handle_search_products(entities, message), ""

            elif intent == "ORDER_STATUS" and customer in CUSTOMERS:
                return await self._handle_order_status(client, customer)

            elif intent == "ACCOUNT_INFO" and customer in CUSTOMERS:
                return await self._handle_account_info(client, customer)

            elif intent == "PLACE_ORDER" and customer in CUSTOMERS:
                return await self._handle_place_order(entities, message), ""

            elif intent == "WARRANTY_SUPPORT":
                return await self._handle_warranty_support(), ""

            else:
                return await self._handle_default_products(entities), ""

    async def _handle_search_products(self, entities: List[str], message: str) -> Dict:
        """Handle product search requests"""
        search_term = (
            " ".join(entities)
            if entities
            else message.replace("search", "").replace("find", "").strip()
        )
        if not search_term:
            search_term = "monitor"

        return {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_products", "arguments": {"query": search_term}},
            "id": 2,
        }

    async def _handle_order_status(
        self, client: httpx.AsyncClient, customer: str
    ) -> Tuple[Optional[Dict], str]:
        verify_msg = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "verify_customer_pin",
                "arguments": {"email": customer, "pin": CUSTOMERS[customer]},
            },
            "id": 2,
        }

        try:
            verify_resp = await client.post(
                self.server_url, json=verify_msg, headers=self.headers, timeout=10.0
            )
            logger.debug(f"Customer verify response: {verify_resp.status_code}")

            if verify_resp.status_code == 200:
                verify_result = verify_resp.json()
                logger.debug(f"Verify result structure: {verify_result}")

                customer_info = self._extract_customer_info(verify_result)
                if customer_info:
                    customer_id = self._extract_customer_id(customer_info)
                    if customer_id:
                        logger.debug(f"Found customer ID: {customer_id}")
                        order_msg = {
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "params": {
                                "name": "list_orders",
                                "arguments": {"customer_id": customer_id},
                            },
                            "id": 3,
                        }
                        return order_msg, ""
                    else:
                        return None, f"Customer verified: {customer_info[:200]}..."
                else:
                    return (
                        None,
                        "Unable to verify customer information. Please check your credentials.",
                    )
            else:
                return (
                    None,
                    f"Customer verification failed (status {verify_resp.status_code}). Please check your email and PIN.",
                )

        except Exception as verify_error:
            logger.error(f"Customer verification error: {verify_error}")
            return (
                None,
                "Unable to verify customer at this time. Please try again later.",
            )

    async def _handle_account_info(
        self, client: httpx.AsyncClient, customer: str
    ) -> Tuple[Optional[Dict], str]:
        verify_msg = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "verify_customer_pin",
                "arguments": {"email": customer, "pin": CUSTOMERS[customer]},
            },
            "id": 2,
        }

        try:
            verify_resp = await client.post(
                self.server_url, json=verify_msg, headers=self.headers, timeout=10.0
            )
            logger.debug(f"Account info response: {verify_resp.status_code}")

            if verify_resp.status_code == 200:
                verify_result = verify_resp.json()
                logger.debug(f"Account info result: {verify_result}")

                customer_info = self._extract_customer_info(verify_result)
                if customer_info:
                    return None, f"Your account information:\n{customer_info}"
                else:
                    return (
                        None,
                        "Unable to retrieve account information. Please contact support.",
                    )
            else:
                return (
                    None,
                    "Unable to access account information. Please check your credentials.",
                )

        except Exception as account_error:
            print(f"Account info error: {account_error}")
            return None, "Unable to retrieve account information at this time."

    async def _handle_place_order(self, entities: List[str], message: str) -> Dict:
        """Handle order placement requests"""
        if entities:
            search_term = " ".join(entities)
            return {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "search_products",
                    "arguments": {"query": search_term},
                },
                "id": 2,
            }
        else:
            return {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "list_products",
                    "arguments": {"category": "Monitors"},
                },
                "id": 2,
            }

    async def _handle_warranty_support(self) -> Dict:
        """Handle warranty support requests"""
        return {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "list_products", "arguments": {"category": None}},
            "id": 2,
        }

    async def _handle_default_products(self, entities: List[str]) -> Dict:
        """Handle default product listing with smart category detection"""
        category = None
        for entity in entities:
            if "monitor" in entity.lower():
                category = "Monitors"
                break
            elif "computer" in entity.lower() or "laptop" in entity.lower():
                category = "Computers"
                break

        return {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "list_products", "arguments": {"category": category}},
            "id": 2,
        }

    async def execute_mcp_call(self, tool_msg: Dict) -> Dict:
        """Execute MCP tool call and return processed response"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                print(f"Sending MCP request: {tool_msg}")
                tool_resp = await client.post(
                    self.server_url, json=tool_msg, headers=self.headers
                )
                print(f"MCP response status: {tool_resp.status_code}")

                if tool_resp.status_code == 200:
                    return await self._process_success_response(tool_resp)
                else:
                    return self._process_error_response(tool_resp)

        except httpx.TimeoutException:
            print("MCP request timeout")
            return {
                "error": "Request timed out. Please try again with a shorter query."
            }
        except httpx.ConnectError:
            print("MCP connection failed")
            return {
                "error": "Unable to connect to product database. Please check your connection and try again."
            }
        except Exception as e:
            print(f"Unexpected MCP error: {e}")
            return {
                "error": "An unexpected error occurred. Please try again or contact support if this continues."
            }

    async def _process_success_response(self, response: httpx.Response) -> Dict:
        """Process successful MCP response"""
        try:
            result = response.json()
            print(f"MCP result: {result}")

            if "result" in result and result["result"]:
                if (
                    "structuredContent" in result["result"]
                    and result["result"]["structuredContent"]
                    and "result" in result["result"]["structuredContent"]
                ):
                    content = result["result"]["structuredContent"]["result"]
                    print(f"Updated response to: {content[:100]}...")
                elif (
                    "content" in result["result"]
                    and result["result"]["content"]
                    and len(result["result"]["content"]) > 0
                    and "text" in result["result"]["content"][0]
                ):
                    content = result["result"]["content"][0]["text"]
                    print(f"Updated response to: {content[:100]}...")
                else:
                    content = str(result["result"])
                    print(f"Fallback response: {content[:100]}...")

                return {"content": content}

            elif "error" in result:
                error_msg = result["error"].get("message", "Unknown MCP error")
                print(f"MCP returned error: {error_msg}")
                return {
                    "error": f"Service temporarily unavailable: {error_msg}. Please try again later."
                }
            else:
                print(f"Unexpected MCP response structure: {result}")
                return {
                    "error": "Unable to process your request at this time. Please try again."
                }

        except json.JSONDecodeError as json_err:
            print(f"Invalid JSON response from MCP: {json_err}")
            return {"error": "Service temporarily unavailable. Please try again later."}
        except Exception as parse_err:
            print(f"Error parsing MCP response: {parse_err}")
            return {
                "error": "Unable to process your request at this time. Please try again."
            }

    def _process_error_response(self, response: httpx.Response) -> Dict:
        """Process MCP error response"""
        print(f"MCP error response: {response.status_code} - {response.text}")

        if response.status_code == 404:
            return {
                "error": "Service not found. Please contact support if this continues."
            }
        elif response.status_code >= 500:
            return {
                "error": "Service temporarily unavailable. Please try again in a few moments."
            }
        elif response.status_code == 429:
            return {"error": "Service is busy. Please wait a moment and try again."}
        else:
            return {
                "error": "Unable to connect to product database. Please try again later."
            }

    def _extract_customer_info(self, verify_result: Dict) -> Optional[str]:
        """Extract customer information from verification result"""
        if "result" not in verify_result:
            return None

        result = verify_result["result"]

        if "structuredContent" in result and "result" in result["structuredContent"]:
            return str(result["structuredContent"]["result"])
        elif "content" in result and result["content"]:
            return str(result["content"][0]["text"])
        else:
            return str(result)

    def _extract_customer_id(self, customer_info: str) -> Optional[str]:
        """Extract customer ID from customer info text"""
        customer_id_match = re.search(r"ID: ([a-f0-9-]+)", customer_info)
        return customer_id_match.group(1) if customer_id_match else None
