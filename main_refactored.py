"""Refactored Customer Support Chatbot with modular architecture"""
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

# Import our modular services
from config import CUSTOMERS, Config
from services.intent_classifier import IntentClassifier
from services.langfuse_client import langfuse_client
from services.mcp_client import MCPClient
from services.streaming import StreamingService, get_simple_response

# Validate configuration
Config.validate()

# Initialize FastAPI app
app = FastAPI(title=Config.APP_TITLE)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
intent_classifier = IntentClassifier()
mcp_client = MCPClient()
streaming_service = StreamingService()


@app.post("/auth")
async def authenticate(request: Request):
    """Authenticate customer with email and PIN"""
    data = await request.json()
    email, pin = data.get("email"), data.get("pin")
    is_valid = CUSTOMERS.get(email) == pin
    return {"success": is_valid, "customer": email if is_valid else None}


@app.get("/chat/{customer}")
async def chat_stream(customer: str, message: str, request: Request):
    """Main chat endpoint with intelligent routing and streaming"""

    async def event_generator():
        if await request.is_disconnected():
            return

        # Create Langfuse trace for observability
        trace = langfuse_client.create_trace(
            name="chat_interaction",
            user_id=customer,
            session_id=f"{customer}_{hash(message) % 10000}",
            metadata={"message": message, "customer": customer, "endpoint": "chat"},
        )

        try:
            # Step 1: Classify intent using LLM
            intent_result = await intent_classifier.classify_intent(
                message, customer, trace
            )
            intent = intent_result.get("intent", "OTHER")
            entities = intent_result.get("entities", [])
            confidence = intent_result.get("confidence", 0.5)

            print(f"Classified intent: {intent} (confidence: {confidence})")

            # Log intent classification result
            if trace:
                langfuse_client.log_event(
                    trace=trace,
                    name="intent_classified",
                    metadata={
                        "intent": intent,
                        "confidence": confidence,
                        "entities": entities,
                    },
                )

            # Step 2: Start with simple response as fallback
            response = get_simple_response(message, customer)

            # Step 3: Route to MCP server if confidence is high enough
            if (
                intent
                in [
                    "SEARCH_PRODUCTS",
                    "ORDER_STATUS",
                    "PLACE_ORDER",
                    "WARRANTY_SUPPORT",
                    "ACCOUNT_INFO",
                ]
                and confidence > Config.INTENT_CONFIDENCE_THRESHOLD
            ):
                print(f"MCP trigger detected in: {message}")

                # Log MCP routing span
                mcp_span = langfuse_client.log_span(
                    trace=trace,
                    name="mcp_routing",
                    input_data={
                        "intent": intent,
                        "entities": entities,
                        "message": message,
                        "customer": customer,
                    },
                    metadata={"service": "mcp_client"},
                )

                try:
                    # Route intent to appropriate MCP tool
                    tool_msg, direct_response = await mcp_client.route_intent_to_mcp(
                        intent, entities, message, customer
                    )

                    if direct_response:
                        # Use direct response (e.g., from account info)
                        response = direct_response
                        if mcp_span:
                            langfuse_client.log_span(
                                trace=trace,
                                name="mcp_routing",
                                input_data={
                                    "intent": intent,
                                    "entities": entities,
                                    "message": message,
                                    "customer": customer,
                                },
                                output_data={
                                    "response": direct_response,
                                    "type": "direct",
                                },
                                metadata={"service": "mcp_client"},
                            )
                    elif tool_msg:
                        # Execute MCP tool call
                        mcp_result = await mcp_client.execute_mcp_call(tool_msg)

                        if "content" in mcp_result:
                            response = mcp_result["content"]
                            if mcp_span:
                                langfuse_client.log_span(
                                    trace=trace,
                                    name="mcp_routing",
                                    input_data={
                                        "intent": intent,
                                        "entities": entities,
                                        "message": message,
                                        "customer": customer,
                                        "tool_msg": tool_msg,
                                    },
                                    output_data={
                                        "response": response,
                                        "type": "mcp_tool",
                                    },
                                    metadata={
                                        "service": "mcp_client",
                                        "tool": tool_msg.get("params", {}).get("name"),
                                    },
                                )
                        elif "error" in mcp_result:
                            response = mcp_result["error"]
                            if trace:
                                langfuse_client.log_event(
                                    trace=trace,
                                    name="mcp_error",
                                    metadata={
                                        "error": mcp_result["error"],
                                        "tool_msg": tool_msg,
                                    },
                                )

                except Exception as e:
                    print(f"Unexpected error in MCP routing: {e}")
                    response = "An unexpected error occurred. Please try again or contact support if this continues."
                    if trace:
                        langfuse_client.log_event(
                            trace=trace,
                            name="mcp_routing_error",
                            metadata={"error": str(e)},
                        )

            # Step 4: Stream response with smart pacing
            async for chunk in streaming_service.stream_response(
                response, request, intent
            ):
                yield chunk

        except Exception as e:
            print(f"Chat processing error: {e}")
            if trace:
                langfuse_client.log_event(
                    trace=trace, name="chat_error", metadata={"error": str(e)}
                )
            # Send error response
            error_response = (
                "I'm experiencing technical difficulties. Please try again."
            )
            async for chunk in streaming_service.stream_response(
                error_response, request
            ):
                yield chunk

        finally:
            # Update trace with final response
            if trace:
                langfuse_client.update_trace(
                    trace=trace,
                    output={"response": response, "intent": intent},
                    metadata={
                        "final_intent": intent,
                        "confidence": confidence,
                        "response_length": len(response),
                    },
                )
                langfuse_client.flush()

    # Anti-buffering headers for real-time streaming
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    return EventSourceResponse(event_generator(), headers=headers)


@app.get("/test")
async def test_page():
    """Test page for debugging"""
    with open("test.html") as f:
        return HTMLResponse(f.read())


@app.get("/", response_class=HTMLResponse)
async def get_chat_ui():
    """Serve the main chat interface"""
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


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "2.0.0"}


@app.get("/config")
async def get_config():
    """Get public configuration (for debugging)"""
    return {
        "app_title": Config.APP_TITLE,
        "intent_threshold": Config.INTENT_CONFIDENCE_THRESHOLD,
        "streaming_enabled": True,
        "mcp_server_connected": bool(Config.MCP_SERVER_URL),
    }


if __name__ == "__main__":
    uvicorn.run(app, host=Config.APP_HOST, port=Config.APP_PORT, log_level="info")
