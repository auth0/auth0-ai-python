# Auth0 AI for Microsoft Agent Framework

`auth0-ai-ms-agent` is an SDK for building secure AI-powered applications using [Auth0](https://www.auth0.ai/) and [Microsoft Agent Framework](https://github.com/microsoft/agent-framework).

## Installation

> ⚠️ **WARNING**: `auth0-ai-ms-agent` is currently **under heavy development**. We strictly follow [Semantic Versioning (SemVer)](https://semver.org/), meaning all **breaking changes will only occur in major versions**. However, please note that during this early phase, **major versions may be released frequently** as the API evolves. We recommend locking versions when using this in production.

```bash
pip install auth0-ai-ms-agent
```

## Features

- **Token Vault**: OAuth-based authorization for calling third-party APIs (GitHub, Slack, Google Calendar, etc.)
- **Async Authorization** _(coming soon)_: CIBA-based user approval workflows
- **Fine-Grained Authorization** _(coming soon)_: Integration with Okta FGA for document and tool-level permissions

## Calling APIs On User's Behalf

The `Auth0AI.with_token_vault` function exchanges a user's refresh token (or access token) for a Token Vault access token that is valid to call a third-party API.

Full Example of [Calling APIs On User's Behalf](../../../examples/calling-apis/ms-agent-examples/).

### Basic Usage

1. Define a tool with the proper authorizer:

```python
from auth0_ai_ms_agent.auth0_ai import Auth0AI
from auth0_ai_ms_agent.token_vault import get_credentials_from_token_vault
from agent_framework import FunctionTool
from datetime import datetime

# If not provided, Auth0 settings will be read from env variables: `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, and `AUTH0_CLIENT_SECRET`
auth0_ai = Auth0AI()

with_google_calendar_access = auth0_ai.with_token_vault(
    connection="google-oauth2",
    scopes=["openid", "https://www.googleapis.com/auth/calendar.freebusy"],
    refresh_token=lambda *_args, **_kwargs: session["user"]["refresh_token"],
    # Optional:
    # login_hint="user@example.com",
    # authorization_params={"ui_locales": "en"}
    # store=InMemoryStore(),
)

def tool_function(date: datetime):
    credentials = get_credentials_from_token_vault()
    # Call Google API using credentials["access_token"]

check_calendar_tool = with_google_calendar_access(
    FunctionTool(
        name="check_user_calendar",
        description="Use this function to check if the user is available on a certain date and time",
        func=tool_function,
    )
)
```

2. Pass the agent session to the tool at runtime. The MS Agent Framework injects the session automatically when you configure it via `additional_function_arguments`:

```python
result = await agent.run(
    "Am I free on Friday at 10am?",
    options={
        "additional_function_arguments": {
            "session": session,
        }
    }
)
```

3. Handle interruptions properly. If the tool does not have access to the user's calendar, it will raise a `TokenVaultInterrupt`. See [Handling Interrupts](#handling-interrupts).

### Additional Authorization Parameters

The `authorization_params` parameter is optional and can be used to pass additional authorization parameters needed to connect an account (e.g., `ui_locales`).
If you need `login_hint` during the token exchange, pass it via the top-level `login_hint` argument.

```python
with_google_calendar_access = auth0_ai.with_token_vault(
    connection="google-oauth2",
    scopes=["openid", "https://www.googleapis.com/auth/calendar.freebusy"],
    refresh_token=lambda *_args, **_kwargs: session["user"]["refresh_token"],
    login_hint="user@example.com",
    authorization_params={"ui_locales": "en"}
)
```

## Handling Interrupts

When authorization is required, the tool raises a `TokenVaultInterrupt` and stores it in `session.state["pending_interrupt"]`. Your application should check for this after each agent run and redirect the user to complete authorization.

```python
from auth0_ai_ms_agent.token_vault import TokenVaultInterrupt

result = await agent.run(
    "Am I free on Friday at 10am?",
    options={
        "additional_function_arguments": {
            "session": session,
        }
    }
)

interrupt = session.state.get("pending_interrupt")
if isinstance(interrupt, TokenVaultInterrupt):
    # Redirect user to complete authorization
    # interrupt.connection, interrupt.scopes, interrupt.required_scopes, interrupt.authorization_params are available
    pass
```

## Configuration

### Environment Variables

```bash
# Auth0 Configuration
AUTH0_DOMAIN=your-tenant.auth0.com
AUTH0_CLIENT_ID=your_client_id
AUTH0_CLIENT_SECRET=your_client_secret
```

### Token Vault Setup

1. Configure Auth0 connections (GitHub, Slack, Google, etc.)
2. Enable Token Vault in Auth0 dashboard
3. Obtain user's refresh token or access token through Auth0 login
4. Pass the token resolver to `with_token_vault`

## Examples

See the [examples directory](../../../examples/) for complete working examples:

- [Calling APIs](../../../examples/calling-apis/ms-agent-examples/) - Token Vault with GitHub, Slack, and Google Calendar

---

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="https://cdn.auth0.com/website/sdks/logos/auth0_light_mode.png"   width="150">
    <source media="(prefers-color-scheme: dark)" srcset="https://cdn.auth0.com/website/sdks/logos/auth0_dark_mode.png" width="150">
    <img alt="Auth0 Logo" src="https://cdn.auth0.com/website/sdks/logos/auth0_light_mode.png" width="150">
  </picture>
</p>
<p align="center">Auth0 is an easy to implement, adaptable authentication and authorization platform. To learn more checkout <a href="https://auth0.com/why-auth0">Why Auth0?</a></p>
<p align="center">
This project is licensed under the Apache 2.0 license. See the <a href="https://github.com/auth0/auth0-ai-python/blob/main/LICENSE"> LICENSE</a> file for more info.</p>
