import os
from pathlib import Path

from auth0_ai_llamaindex.auth0_ai import set_ai_context
from auth0_ai_llamaindex.token_vault import TokenVaultInterrupt
from auth0_fastapi.server.routes import register_auth_routes, router
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from ..agents.agent import agent
from ..agents.memory import get_memory
from ..auth0 import auth0_ai
from ..auth0.auth import auth_client, config
from .middleware import HostRedirectMiddleware
from .threads import create_thread, get_thread

load_dotenv()

app = FastAPI(
    title="Auth0 AI + Llama Index - Chatbot Example: Calling API's on user's behalf")

# Add host redirect middleware to ensure requests use the correct host configured in APP_BASE_URL
app.add_middleware(HostRedirectMiddleware)

app.add_middleware(SessionMiddleware, secret_key=os.getenv(
    "APP_SECRET_KEY", "SOME_RANDOM_SECRET_KEY"))

# Attach to the FastAPI app state so internal routes can access it
app.state.config = config
app.state.auth_client = auth_client

# Conditionally register routes
register_auth_routes(router, config)

# Include the SDK's default routes
app.include_router(router)


# Set up templates directory
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

app.middleware("http")(auth0_ai.store_session)


@app.get("/")
async def home(request: Request, response: Response):
    try:
        auth_session = await auth_client.require_session(request, response)
    except Exception:
        return RedirectResponse(url="/auth/login")

    user_id = auth_session.get("user")["sub"]
    thread_id = create_thread(user_id)
    return RedirectResponse(url="/chat/" + thread_id)


@app.get("/chat/resume/{thread_id}")
async def resume_chat(request: Request, thread_id: str, response: Response, auth_session=Depends(auth_client.require_session)):
    user_id = auth_session.get("user")["sub"]
    thread = get_thread(user_id, thread_id)

    if not thread:
        raise HTTPException(
            status_code=404, detail="Chat thread not found")

    if thread.get("interrupt"):
        set_ai_context(thread_id)
        interrupt = thread["interrupt"]
        memory = await get_memory(user_id, thread_id)
        await agent.run(user_msg=interrupt["last_message"], memory=memory)
        thread["interrupt"] = None

    return RedirectResponse(url="/chat/" + thread_id)


@app.get("/chat/{thread_id}")
async def chat(request: Request, thread_id: str, response: Response, auth_session=Depends(auth_client.require_session)):
    user = auth_session.get("user")
    user_id = user["sub"]
    thread = get_thread(user_id, thread_id)

    if not thread:
        raise HTTPException(
            status_code=404, detail="Chat thread not found")

    memory = await get_memory(user_id, thread_id)

    messages = [
        {
            "role": m.role,
            "content": m.content
        } for m in memory.get_all()
    ]

    # Check if there's an active interrupt for this thread
    interrupt = thread.get("interrupt")

    # Render the chat page with the user information
    context = {"request": request, "messages": messages,
               "user": user, "interrupt": interrupt,
               "thread_id": thread_id}
    return templates.TemplateResponse("index.html", context)


@app.post("/api/chat")
async def api_chat(request: Request, auth_session=Depends(auth_client.require_session)):
    user_id = auth_session.get("user")["sub"]
    body = await request.json()
    message, thread_id = (body.get(k) for k in ("message", "thread_id"))

    thread = get_thread(user_id, thread_id)

    if not thread:
        return JSONResponse(content={"error": "Conversation has expired or doesn't exist. Please start a new chat."}, status_code=400)

    set_ai_context(thread_id)

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    try:
        memory = await get_memory(user_id, thread_id)
        response = await agent.run(user_msg=message, memory=memory)

        # Check if the last tool call resulted in a TokenVaultInterrupt error
        if response.tool_calls:
            last_tool_call = response.tool_calls[-1]
            last_tool_output = last_tool_call.tool_output
            if (last_tool_output.is_error and
                    isinstance(last_tool_output.exception, TokenVaultInterrupt)):
                exception = last_tool_output.exception

                # we cant prevent llamaindex to call the LLM after the tool throws the exception,
                # so we manually delete the 1. user message, 2. assistant resp,
                # 3. the tool result, 4. the agent response:
                store = memory.chat_store.store
                del store[memory.chat_store_key][-4:]

                # store the interrupt in the thread
                thread["interrupt"] = {
                    "value": exception.to_json(),
                    "last_message": message
                }
                return JSONResponse(content={"response": exception.to_json()})

        return JSONResponse(content={"response": str(response)})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
