import contextvars

from auth0_ai_llamaindex.auth0_ai import Auth0AI
from dotenv import load_dotenv
from fastapi import Request, Response

from .auth import auth_client

load_dotenv()

auth0_ai = Auth0AI()

session_var_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "auth0_ai_session")


async def store_session(request: Request, call_next):
    """
    FastAPI middleware that stores the Auth0 session in a context variable.

    This middleware intercepts incoming requests, authenticates them using Auth0,
    and stores the session data in a context variable that can be accessed by
    downstream handlers and functions. The context variable is automatically
    cleaned up after the request is processed.

    Args:
        request (Request): The incoming FastAPI request object.
        call_next: The next middleware or route handler in the chain.

    Returns:
        Response: The response from the downstream handler.

    Raises:
        Any authentication errors from auth_client.require_session() if the
        session is invalid or missing.

    Note:
        The session is stored in the `session_var_ctx` context variable and can be
        retrieved using `session_var_ctx.get()` in any function called during the
        request lifecycle.
    """
    try:
        session = await auth_client.require_session(request, Response())
        token = session_var_ctx.set(session)
    except Exception:
        response = await call_next(request)
        return response

    try:
        response = await call_next(request)
    finally:
        session_var_ctx.reset(token)

    return response


def refresh_token(*args, **kwargs):
    auth_session = session_var_ctx.get()
    return auth_session.get("refresh_token")


with_calendar_free_busy_access = auth0_ai.with_token_vault(
    connection="google-oauth2",
    scopes=["openid", "https://www.googleapis.com/auth/calendar.freebusy"],
    refresh_token=refresh_token
    # Optional: authorization_params={"login_hint": "user@example.com", "ui_locales": "en"}
)

with_slack_access = auth0_ai.with_token_vault(
    connection="sign-in-with-slack",
    scopes=["channels:read"],
    refresh_token=refresh_token,
    # Optional: authorization_params={"login_hint": "user@example.com"}
)

with_github_access = auth0_ai.with_token_vault(
    connection="github",
    scopes=["repo"],
    refresh_token=refresh_token,
    # Optional: authorization_params={"login_hint": "user@example.com"}
)
