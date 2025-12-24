import asyncio
import json
from typing import Any, Dict

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from openai import AsyncOpenAI
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="Customer Support Chatbot")

# Add CORS middleware to handle cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Test customers
CUSTOMERS = {
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

MCP_SERVER_URL = "https://vipfapwm3x.us-east-1.awsapprunner.com/mcp"

# OpenAI Configuration
OPENAI_API_KEY = "<OPENAI_API_KEY>"
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


async def classify_intent(message: str, customer: str) -> dict:
    """Use OpenAI to classify customer intent and extract entities"""
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",  # Cheapest OpenAI model at $0.15/M input, $0.6/M output
            messages=[
                {
                    "role": "system",
                    "content": """You are an intent classifier for a computer products customer support chatbot.

Classify the customer message into ONE of these categories:
- SEARCH_PRODUCTS: Looking for products, browsing, specifications
- ORDER_STATUS: Checking order status, delivery, tracking
- PLACE_ORDER: Wanting to buy, purchase, order a product
- WARRANTY_SUPPORT: Warranty claims, returns, repairs
- TECH_SUPPORT: Technical issues, setup help, troubleshooting
- GREETING: Hello, hi, general greeting
- ACCOUNT_INFO: Account details, login issues, customer info
- OTHER: Anything that doesn't fit above categories

Extract key entities like product names, order numbers, issues.

Return ONLY valid JSON in this exact format:
{"intent": "CATEGORY", "confidence": 0.95, "entities": ["key", "terms"], "reasoning": "brief explanation"}""",
                },
                {
                    "role": "user",
                    "content": f"Customer: {customer}\nMessage: {message}",
                },
            ],
            max_tokens=150,
            temperature=0.1,
        )

        result: Dict[str, Any] = json.loads(response.choices[0].message.content)
        print(f"Intent classification: {result}")
        return result
    except Exception as e:
        print(f"Intent classification error: {e}")
        return {
            "intent": "OTHER",
            "confidence": 0.5,
            "entities": [],
            "reasoning": "Classification failed",
        }


@app.post("/auth")
async def authenticate(request: Request):
    data = await request.json()
    email, pin = data.get("email"), data.get("pin")
    return {
        "success": CUSTOMERS.get(email) == pin,
        "customer": email if CUSTOMERS.get(email) == pin else None,
    }


@app.get("/chat/{customer}")
async def chat_stream(customer: str, message: str, request: Request):
    async def event_generator():
        if await request.is_disconnected():
            return

        # Classify intent using LLM
        intent_result = await classify_intent(message, customer)
        intent = intent_result.get("intent", "OTHER")
        entities = intent_result.get("entities", [])
        confidence = intent_result.get("confidence", 0.5)

        print(f"Classified intent: {intent} (confidence: {confidence})")

        # Start with simple response
        response = get_simple_response(message, customer)

        # Route to MCP server based on LLM intent classification
        if (
            intent
            in [
                "SEARCH_PRODUCTS",
                "ORDER_STATUS",
                "PLACE_ORDER",
                "WARRANTY_SUPPORT",
                "ACCOUNT_INFO",
            ]
            and confidence > 0.7
        ):
            print(f"MCP trigger detected in: {message}")
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    headers = {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    }

                    # Choose appropriate MCP tool based on LLM classification
                    if intent == "SEARCH_PRODUCTS":
                        # Use entities for search term, fallback to message
                        search_term = (
                            " ".join(entities)
                            if entities
                            else message.replace("search", "")
                            .replace("find", "")
                            .strip()
                        )
                        if not search_term:
                            search_term = "monitor"

                        tool_msg = {
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "params": {
                                "name": "search_products",
                                "arguments": {"query": search_term},
                            },
                            "id": 2,
                        }

                    elif intent == "ORDER_STATUS" and customer in CUSTOMERS:
                        # Get customer info first, then orders
                        verify_msg = {
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "params": {
                                "name": "verify_customer_pin",
                                "arguments": {
                                    "email": customer,
                                    "pin": CUSTOMERS[customer],
                                },
                            },
                            "id": 2,
                        }

                        try:
                            verify_resp = await client.post(
                                MCP_SERVER_URL,
                                json=verify_msg,
                                headers=headers,
                                timeout=10.0,
                            )
                            print(
                                f"Customer verify response: {verify_resp.status_code}"
                            )

                            if verify_resp.status_code == 200:
                                verify_result = verify_resp.json()
                                print(f"Verify result structure: {verify_result}")

                                # Fix: Check for proper response structure
                                if "result" in verify_result:
                                    # Try structuredContent first, then content
                                    if (
                                        "structuredContent" in verify_result["result"]
                                        and "result"
                                        in verify_result["result"]["structuredContent"]
                                    ):
                                        customer_info = verify_result["result"][
                                            "structuredContent"
                                        ]["result"]
                                    elif (
                                        "content" in verify_result["result"]
                                        and verify_result["result"]["content"]
                                    ):
                                        customer_info = verify_result["result"][
                                            "content"
                                        ][0]["text"]
                                    else:
                                        customer_info = str(verify_result["result"])

                                    print(f"Customer info extracted: {customer_info}")

                                    # Extract customer ID and get orders
                                    import re

                                    customer_id_match = re.search(
                                        r"ID: ([a-f0-9-]+)", customer_info
                                    )
                                    if customer_id_match:
                                        customer_id = customer_id_match.group(1)
                                        print(f"Found customer ID: {customer_id}")
                                        tool_msg = {
                                            "jsonrpc": "2.0",
                                            "method": "tools/call",
                                            "params": {
                                                "name": "list_orders",
                                                "arguments": {
                                                    "customer_id": customer_id
                                                },
                                            },
                                            "id": 3,
                                        }
                                    else:
                                        # Customer verified but no ID found - show info instead
                                        response = f"Customer verified: {customer_info[:200]}..."
                                        tool_msg = None
                                else:
                                    response = "Unable to verify customer information. Please check your credentials."
                                    tool_msg = None
                            else:
                                response = f"Customer verification failed (status {verify_resp.status_code}). Please check your email and PIN."
                                tool_msg = None
                        except Exception as verify_error:
                            print(f"Customer verification error: {verify_error}")
                            response = "Unable to verify customer at this time. Please try again later."
                            tool_msg = None

                    elif intent == "WARRANTY_SUPPORT":
                        # Use general product list for warranty inquiries
                        tool_msg = {
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "params": {
                                "name": "list_products",
                                "arguments": {"category": None},
                            },
                            "id": 2,
                        }
                    elif intent == "ACCOUNT_INFO" and customer in CUSTOMERS:
                        # Get customer account information
                        verify_msg = {
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "params": {
                                "name": "verify_customer_pin",
                                "arguments": {
                                    "email": customer,
                                    "pin": CUSTOMERS[customer],
                                },
                            },
                            "id": 2,
                        }

                        try:
                            verify_resp = await client.post(
                                MCP_SERVER_URL,
                                json=verify_msg,
                                headers=headers,
                                timeout=10.0,
                            )
                            print(f"Account info response: {verify_resp.status_code}")

                            if verify_resp.status_code == 200:
                                verify_result = verify_resp.json()
                                print(f"Account info result: {verify_result}")

                                if "result" in verify_result:
                                    if (
                                        "structuredContent" in verify_result["result"]
                                        and "result"
                                        in verify_result["result"]["structuredContent"]
                                    ):
                                        response = f"Your account information:\n{verify_result['result']['structuredContent']['result']}"
                                    elif (
                                        "content" in verify_result["result"]
                                        and verify_result["result"]["content"]
                                    ):
                                        response = f"Your account information:\n{verify_result['result']['content'][0]['text']}"
                                    else:
                                        response = f"Your account information:\n{str(verify_result['result'])}"
                                else:
                                    response = "Unable to retrieve account information. Please contact support."
                            else:
                                response = "Unable to access account information. Please check your credentials."
                        except Exception as account_error:
                            print(f"Account info error: {account_error}")
                            response = (
                                "Unable to retrieve account information at this time."
                            )

                        tool_msg = None  # We already handled the response above
                    elif intent == "PLACE_ORDER" and customer in CUSTOMERS:
                        # Handle order placement - need product search first
                        if entities:
                            # Search for the product they want to order
                            search_term = " ".join(entities)
                            response = f"Let me find '{search_term}' for you so you can place an order..."
                            tool_msg = {
                                "jsonrpc": "2.0",
                                "method": "tools/call",
                                "params": {
                                    "name": "search_products",
                                    "arguments": {"query": search_term},
                                },
                                "id": 2,
                            }
                        else:
                            # No specific product mentioned, show popular options
                            response = "I can help you place an order! Here are some popular products:"
                            tool_msg = {
                                "jsonrpc": "2.0",
                                "method": "tools/call",
                                "params": {
                                    "name": "list_products",
                                    "arguments": {"category": "Monitors"},
                                },
                                "id": 2,
                            }
                    else:
                        # Default to list products with smart category detection
                        category = None
                        for entity in entities:
                            if "monitor" in entity.lower():
                                category = "Monitors"
                                break
                            elif (
                                "computer" in entity.lower()
                                or "laptop" in entity.lower()
                            ):
                                category = "Computers"
                                break
                        tool_msg = {
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "params": {
                                "name": "list_products",
                                "arguments": {"category": category},
                            },
                            "id": 2,
                        }

                    if tool_msg:
                        print(f"Sending MCP request: {tool_msg}")
                        tool_resp = await client.post(
                            MCP_SERVER_URL, json=tool_msg, headers=headers
                        )
                        print(f"MCP response status: {tool_resp.status_code}")

                        if tool_resp.status_code == 200:
                            try:
                                result = tool_resp.json()
                                print(f"MCP result: {result}")
                                if "result" in result and result["result"]:
                                    # Try structuredContent first (preferred), then content text
                                    if (
                                        "structuredContent" in result["result"]
                                        and result["result"]["structuredContent"]
                                        and "result"
                                        in result["result"]["structuredContent"]
                                    ):
                                        response = result["result"][
                                            "structuredContent"
                                        ]["result"]
                                        print(
                                            f"Updated response to: {response[:100]}..."
                                        )
                                    elif (
                                        "content" in result["result"]
                                        and result["result"]["content"]
                                        and len(result["result"]["content"]) > 0
                                        and "text" in result["result"]["content"][0]
                                    ):
                                        response = result["result"]["content"][0][
                                            "text"
                                        ]
                                        print(
                                            f"Updated response to: {response[:100]}..."
                                        )
                                    else:
                                        # Fallback to string representation
                                        response = str(result["result"])
                                        print(f"Fallback response: {response[:100]}...")

                                    # Add ordering instructions for PLACE_ORDER intent
                                    if intent == "PLACE_ORDER":
                                        response += "\n\n🛒 To place an order for any of these products, please contact our sales team or visit our website. Note: This demo doesn't process actual orders."
                                elif "error" in result:
                                    error_msg = result["error"].get(
                                        "message", "Unknown MCP error"
                                    )
                                    response = f"Service temporarily unavailable: {error_msg}. Please try again later."
                                    print(f"MCP returned error: {error_msg}")
                                else:
                                    response = "Unable to process your request at this time. Please try again."
                                    print(
                                        f"Unexpected MCP response structure: {result}"
                                    )
                            except json.JSONDecodeError as json_err:
                                print(f"Invalid JSON response from MCP: {json_err}")
                                response = "Service temporarily unavailable. Please try again later."
                            except Exception as parse_err:
                                print(f"Error parsing MCP response: {parse_err}")
                                response = "Unable to process your request at this time. Please try again."
                        else:
                            print(
                                f"MCP error response: {tool_resp.status_code} - {tool_resp.text}"
                            )
                            if tool_resp.status_code == 404:
                                response = "Service not found. Please contact support if this continues."
                            elif tool_resp.status_code >= 500:
                                response = "Service temporarily unavailable. Please try again in a few moments."
                            elif tool_resp.status_code == 429:
                                response = "Service is busy. Please wait a moment and try again."
                            else:
                                response = "Unable to connect to product database. Please try again later."

            except httpx.TimeoutException:
                print("MCP request timeout")
                response = "Request timed out. Please try again with a shorter query."
            except httpx.ConnectError:
                print("MCP connection failed")
                response = "Unable to connect to product database. Please check your connection and try again."
            except Exception as e:
                print(f"Unexpected MCP error: {e}")
                import traceback

                traceback.print_exc()
                response = "An unexpected error occurred. Please try again or contact support if this continues."

        # Smart streaming based on response length and type
        print(f"Streaming response length: {len(response)} chars")

        # Handle large product lists specially
        if "Found 200 products:" in response:
            # Extract first few products for better UX
            lines = response.split("\n")
            summary = lines[0]  # "Found 200 products:"
            products = [line for line in lines[1:] if line.strip() and "[" in line][
                :8
            ]  # First 8 products

            # Create truncated response
            truncated_response = summary + "\n\n" + "\n\n".join(products[:8])
            if len(products) > 8:
                truncated_response += f"\n\n... and {200 - 8} more products.\nType 'search [keyword]' to find specific items or 'list monitors' for category browsing."

            response = truncated_response
            print(f"Truncated to {len(response)} chars for better UX")

        # Smart streaming based on length
        if len(response) <= 200:
            # Short responses: Character streaming for conversational feel
            for char in response:
                if await request.is_disconnected():
                    break
                yield {"data": char}
                await asyncio.sleep(0.04)  # Slightly faster
        elif len(response) <= 1000:
            # Medium responses: Word-by-word streaming
            words = response.split(" ")
            for word in words:
                if await request.is_disconnected():
                    break
                yield {"data": word + " "}
                await asyncio.sleep(0.08)
        else:
            # Large responses: Line-by-line streaming (fast)
            lines = response.split("\n")
            for line in lines:
                if await request.is_disconnected():
                    break
                yield {"data": line + "\n"}
                await asyncio.sleep(0.1)

        print("Sending DONE signal")
        yield {"data": "[DONE]"}

    # Add headers to prevent proxy buffering
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # Prevents Nginx buffering
    }
    return EventSourceResponse(event_generator(), headers=headers)


def get_simple_response(msg, customer):
    """Enhanced simple response logic using basic patterns"""
    msg = msg.lower()
    if "hello" in msg or "hi" in msg or "hey" in msg:
        return f"Hello {customer}! How can I help with your computer products today?"
    if "thank" in msg or "thanks" in msg:
        return "You're welcome! Is there anything else I can help you with?"
    if "bye" in msg or "goodbye" in msg:
        return "Goodbye! Have a great day, and feel free to reach out if you need any help."
    return "I can help with orders, products, warranties, and technical issues. What do you need?"


@app.get("/test")
async def test_page():
    with open("test.html") as f:
        return HTMLResponse(f.read())


@app.get("/", response_class=HTMLResponse)
async def get_chat_ui():
    return """<!DOCTYPE html>
<html><head><title>Customer Support Chat</title><style>
body{font-family:Arial;max-width:600px;margin:50px auto;padding:20px}
.auth,.chat{margin:20px 0}.hidden{display:none}
input,button{padding:10px;margin:5px;border:1px solid #ccc;border-radius:5px}
#messages{height:400px;border:1px solid #ccc;padding:10px;overflow-y:scroll;background:#f9f9f9}
.message{margin:10px 0;padding:10px;border-radius:10px}
.user{background:#007bff;color:white;text-align:right}.bot{background:#e9ecef}
</style></head><body>
<h1>🤖 Customer Support</h1>
<div class="auth" id="auth">
<input type="email" id="email" placeholder="Email" required>
<input type="text" id="pin" placeholder="PIN" required>
<button onclick="login()">Login</button>
</div>
<div class="chat hidden" id="chat">
<div id="messages"></div>
<input type="text" id="messageInput" placeholder="Type your message..." onkeypress="if(event.key==='Enter')sendMessage()">
<button onclick="sendMessage()">Send</button>
</div>
<script>
let customer='';
async function login(){
const email=document.getElementById('email').value;
const pin=document.getElementById('pin').value;
const resp=await fetch('/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,pin})});
const data=await resp.json();
if(data.success){customer=data.customer;document.getElementById('auth').classList.add('hidden');document.getElementById('chat').classList.remove('hidden');}
else alert('Invalid credentials');}
async function sendMessage(){
const input=document.getElementById('messageInput');
const message=input.value.trim();if(!message)return;
addMessage(message,'user');input.value='';
const eventSource=new EventSource(`/chat/${encodeURIComponent(customer)}?message=${encodeURIComponent(message)}`);
let botMessage='';
console.log('Starting EventSource for:', message);
eventSource.onopen=()=>console.log('EventSource opened');
eventSource.onmessage=function(event){
console.log('Received:', event.data);
if(event.data==='[DONE]'){console.log('Stream ended');eventSource.close();return;}
botMessage+=event.data;updateBotMessage(botMessage);};
eventSource.onerror=(e)=>{console.error('EventSource error:',e);eventSource.close();};}
function addMessage(text,type){
const messages=document.getElementById('messages');
const div=document.createElement('div');
div.className=`message ${type}`;
div.textContent=text;
messages.appendChild(div);
messages.scrollTop=messages.scrollHeight;}
function updateBotMessage(text){
const messages=document.getElementById('messages');
let lastBot=messages.querySelector('.message.bot:last-child');
if(!lastBot){lastBot=document.createElement('div');lastBot.className='message bot';messages.appendChild(lastBot);}
lastBot.textContent=text;messages.scrollTop=messages.scrollHeight;}
</script></body></html>"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
