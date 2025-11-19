from auth0_ai_langchain.auth0_ai import Auth0AI
from dotenv import load_dotenv

load_dotenv()

auth0_ai = Auth0AI()

with_calendar_free_busy_access = auth0_ai.with_token_vault(
    connection="google-oauth2",
    scopes=[
        "openid",
        "https://www.googleapis.com/auth/calendar.freebusy"
    ],
    # Optional: authorization_params={"login_hint": "user@example.com", "ui_locales": "en"}
)

with_slack_access = auth0_ai.with_token_vault(
    connection="sign-in-with-slack",
    scopes=["channels:read"],
    # Optional: authorization_params={"login_hint": "user@example.com"}
)

with_github_access = auth0_ai.with_token_vault(
    connection="github",
    scopes=["repo"],
    # Optional: authorization_params={"login_hint": "user@example.com"}
)
