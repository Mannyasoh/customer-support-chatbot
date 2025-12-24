from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from langfuse import observe
from loguru import logger

from config import CUSTOMERS, Config
from services.intent_classifier import IntentClassifier
from services.mcp_client import MCPClient
from services.streaming import StreamingService, get_simple_response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting application...")
    Config.validate()
    yield
    # Shutdown
    logger.info("Shutting down application...")


app = FastAPI(
    title=Config.APP_TITLE,
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

intent_classifier = IntentClassifier()
mcp_client = MCPClient()
streaming_service = StreamingService()


@app.post("/auth")
async def authenticate(request: Request):
    data = await request.json()
    email, pin = data.get("email"), data.get("pin")
    is_valid = bool(email and pin and CUSTOMERS.get(email) == pin)
    return {"success": is_valid, "customer": email if is_valid else None}


@app.get("/chat/{customer}")
@observe(name="chat-interaction", capture_input=False, capture_output=False)
async def chat_stream(customer: str, message: str, request: Request):
    async def event_generator():
        if await request.is_disconnected():
            return

        response = "I can help with orders, products, warranties, and technical issues. What do you need?"
        intent = "OTHER"
        confidence = 0.5
        entities = []

        try:
            intent_result = await intent_classifier.classify_intent(message, customer)
            intent = intent_result.get("intent", "OTHER")
            entities = intent_result.get("entities", [])
            confidence = intent_result.get("confidence", 0.5)

            logger.info(f"Intent: {intent} (confidence: {confidence})")
            response = get_simple_response(message, customer)
            mcp_intents = [
                "SEARCH_PRODUCTS",
                "ORDER_STATUS",
                "PLACE_ORDER",
                "WARRANTY_SUPPORT",
                "ACCOUNT_INFO",
            ]
            if (
                intent in mcp_intents
                and confidence > Config.INTENT_CONFIDENCE_THRESHOLD
            ):
                logger.info(f"MCP routing for intent: {intent}")

                try:
                    tool_msg, direct_response = await mcp_client.route_intent_to_mcp(
                        intent, entities, message, customer
                    )

                    if direct_response:
                        response = direct_response
                    elif tool_msg:
                        mcp_result = await mcp_client.execute_mcp_call(tool_msg)
                        response = mcp_result.get("content") or mcp_result.get(
                            "error", response
                        )
                except Exception as e:
                    logger.error(f"MCP routing error: {e}")
                    response = "An unexpected error occurred. Please try again or contact support if this continues."

            async for chunk in streaming_service.stream_response(
                response, request, intent
            ):
                yield chunk

        except Exception as e:
            logger.error(f"Chat error: {e}")
            error_response = (
                "I'm experiencing technical difficulties. Please try again."
            )
            async for chunk in streaming_service.stream_response(
                error_response, request
            ):
                yield chunk

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    async def generate():
        async for chunk in event_generator():
            yield f"data: {chunk['data']}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(), media_type="text/event-stream", headers=headers
    )


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


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "2.0.0"}


@app.get("/config")
async def get_config():
    return {
        "app_title": Config.APP_TITLE,
        "intent_threshold": Config.INTENT_CONFIDENCE_THRESHOLD,
        "streaming_enabled": True,
        "mcp_server_connected": bool(Config.MCP_SERVER_URL),
    }


if __name__ == "__main__":
    uvicorn.run(app, host=Config.APP_HOST, port=Config.APP_PORT, log_level="info")
