import os
from pathlib import Path

from auth0_ai_langchain.utils.interrupt import get_auth0_interrupts
from auth0_fastapi.server.routes import register_auth_routes, router
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from langchain_core.messages import HumanMessage
from langgraph_sdk import get_client
from langgraph_sdk.schema import Command
from starlette.middleware.sessions import SessionMiddleware

from ..auth0.auth import auth_client, config
from .middleware import HostRedirectMiddleware

load_dotenv()

app = FastAPI(
    title="Auth0 AI + LangChain - Chatbot Example: Calling API's on user's behalf")

# Add host redirect middleware to ensure requests use the correct host configured in APP_BASE_URL
app.add_middleware(HostRedirectMiddleware)

app.add_middleware(SessionMiddleware, secret_key=os.getenv(
    "APP_SECRET_KEY", "SOME_RANDOM_SECRET_KEY"))

# Attach to the FastAPI app state so internal routes can access it
app.state.config = config
app.state.auth_client = auth_client

# Conditionally register routes
register_auth_routes(router, config)

# Include the SDK’s default routes
app.include_router(router)

# Set up templates directory with custom Jinja2 environment
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Initialize LangGraph client
langgraph_client = get_client(url=os.getenv(
    "LANGGRAPH_API_URL", "http://localhost:54367"))


async def get_thread(thread_id: str, user_id: str):
    """
        Get and validate that the thread belongs to the authenticated user.
    """
    thread = await langgraph_client.threads.get(thread_id)
    if thread.get("metadata", {}).get("user_id") != user_id:
        raise HTTPException(
            status_code=400, detail="Conversation has expired or doesn't exist. Please start a new chat.")
    return thread


@app.get("/")
async def home(request: Request, response: Response):
    try:
        auth_session = await auth_client.require_session(request, response)
    except Exception:
        return RedirectResponse(url="/auth/login")

    user_id = auth_session.get("user")["sub"]

    # create thread
    thread_id = (await langgraph_client.threads.create(metadata={
        "user_id": user_id
    }))["thread_id"]

    return RedirectResponse(url=f"/chat/{thread_id}")


@app.get("/chat/resume/{thread_id}")
async def chat_resume(request: Request, thread_id: str, response: Response, auth_session=Depends(auth_client.require_session)):
    user = auth_session.get("user")
    user_id = user["sub"]
    thread = await get_thread(thread_id, user_id)

    auth0_interrupts = get_auth0_interrupts(thread)

    if auth0_interrupts:
        # Here I must resume tool calls
        await langgraph_client.runs.wait(
            thread_id,
            "agent",
            command=Command(resume=''),
            config={"configurable": {
                "_credentials": {"refresh_token": auth_session.get("refresh_token")}
            }}
        )

    return RedirectResponse(url="/chat/" + thread_id)


@app.get('/chat/{thread_id}')
async def chat_thread(request: Request, thread_id: str, response: Response, auth_session=Depends(auth_client.require_session)):
    user = auth_session.get("user")
    user_id = user["sub"]

    thread = await get_thread(thread_id, user_id)

    auth0_interrupts = get_auth0_interrupts(thread)

    thread_messages = (thread["values"] if thread["values"]
                       else {}).get("messages", [])

    # Limit the content that is sent to the client
    messages = [
        {
            "type": message["type"],
            "content": message["content"],
            "id": message["id"]
        }
        for message in thread_messages
    ]
    interrupt = auth0_interrupts[0] if auth0_interrupts else None

    # Render the chat page with the user information
    return templates.TemplateResponse("index.html", {
        "request": request,
        "messages": messages,
        "user": user,
        "interrupt": interrupt,
        "thread_id": thread_id})


@app.post("/api/chat")
async def chat_api(request: Request, auth_session=Depends(auth_client.require_session)):
    body = await request.json()
    message, thread_id = body.get("message"), body.get("thread_id")

    user = auth_session.get("user")
    user_id = user["sub"]

    thread = await get_thread(thread_id, user_id)

    # Get the user's message from the request body
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    try:
        wait_result = await langgraph_client.runs.wait(
            thread_id,
            "agent",
            input={"messages": [HumanMessage(content=message)]},
            config={"configurable": {
                "_credentials": {"refresh_token": auth_session.get("refresh_token")}
            }}
        )
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

    # Retrieve thread and handle Auth0 interrupts
    thread = await langgraph_client.threads.get(thread_id)
    auth0_interrupts = get_auth0_interrupts(thread)

    if auth0_interrupts:
        return JSONResponse(content={"response": auth0_interrupts[0]})

    # Return the last message from the LangGraph agent
    if wait_result and "messages" in wait_result:
        # reply with the last message
        last_message = wait_result["messages"][-1]
        return JSONResponse(content={"response": last_message["content"]})

    return JSONResponse(content={"error": "Unexpected error"}, status_code=500)
    return JSONResponse(content={"error": "Unexpected error"}, status_code=500)
