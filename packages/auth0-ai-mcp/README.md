The `auth0-ai-mcp` library secures [Model Context Protocol (MCP)](https://modelcontextprotocol.io) servers with Auth0, built on [`auth0-api-python`](https://github.com/auth0/auth0-api-python).

An MCP server is just another resource server. This library ships no MCP framework of its own. It verifies the incoming bearer token, runs the On-Behalf-Of token exchange for downstream API calls with an optional cache in front, and exposes the verified caller to tool code. Each framework gets a thin adapter that wires this into its request pipeline.

![Release](https://img.shields.io/pypi/v/auth0-ai-mcp) ![Downloads](https://img.shields.io/pypi/dw/auth0-ai-mcp) [![License](https://img.shields.io/:license-Apache--2.0-blue.svg?style=flat)](https://opensource.org/licenses/Apache-2.0)

🚀 [Getting Started](#getting-started) - 💬 [Feedback](#feedback)

## How it works

1. **Verify** - every incoming bearer token is checked before the MCP handler runs.
2. **Context** - the verified caller is available to tool code.
3. **Scopes** - tools can require scopes on the caller's token.
4. **On-Behalf-Of** - exchange the caller's token for a downstream token.
5. **Token Vault** - exchange the caller's token for a federated provider token.
6. **Client Credentials** - get a token for the server itself.

## Getting Started

### 1. Install

```bash
pip install auth0-ai-mcp
```

Or with Poetry:

```bash
poetry add auth0-ai-mcp
```

Python 3.10 or later is required.

### 2. Build the client

```python
from auth0_ai_mcp import create_mcp_client

client = create_mcp_client(
    domain="your-tenant.auth0.com",
    audience="https://your-mcp-server/mcp",
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
)
```

> [!IMPORTANT]
> `audience` must be the public URL of your MCP server. It is also the API identifier you register in Auth0, so a token issued for any other value is rejected with a `401`.

`client_id` and `client_secret` are only needed for token exchanges.

### 3. Wire an adapter

The ASGI adapter wraps any ASGI app and handles all auth work before the MCP handler runs:

```python
from auth0_ai_mcp.middleware import Auth0AsgiMiddleware

secured_app = Auth0AsgiMiddleware(
    app,
    mcp_client=client,
)
```


### 4. Write a gated tool

```python
from auth0_ai_mcp import require_caller_mcp_client, with_required_scopes

@with_required_scopes("read:weather")
async def get_weather(location: str) -> dict:
    auth0 = require_caller_mcp_client()
    token = await auth0.get_token_on_behalf_of(
        audience="https://weather-api/",
        scope="read:weather",
    )
    # call the downstream API with token["access_token"]
```

`with_required_scopes` raises before the tool body runs if the caller's token is missing a listed scope. `require_caller_mcp_client` reads the request-scoped client from the `contextvar` set by the adapter.

## Feedback

### Contributing

We appreciate feedback and contribution to this repo! Before you get started, please read the following:

- [Auth0's general contribution guidelines](https://github.com/auth0/open-source-template/blob/master/GENERAL-CONTRIBUTING.md)
- [Auth0's code of conduct guidelines](https://github.com/auth0/open-source-template/blob/master/CODE-OF-CONDUCT.md)
- [This package's contribution guide](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/CONTRIBUTING.md)

### Raise an issue

To provide feedback or report a bug, please [raise an issue on our issue tracker](https://github.com/auth0/auth0-ai-python/issues).

## Vulnerability Reporting

Please do not report security vulnerabilities on the public GitHub issue tracker. The [Responsible Disclosure Program](https://auth0.com/responsible-disclosure-policy) details the procedure for disclosing security issues.

## What is Auth0?

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://cdn.auth0.com/website/sdks/logos/auth0_dark_mode.png" width="150">
    <source media="(prefers-color-scheme: light)" srcset="https://cdn.auth0.com/website/sdks/logos/auth0_light_mode.png" width="150">
    <img alt="Auth0 Logo" src="https://cdn.auth0.com/website/sdks/logos/auth0_light_mode.png" width="150">
  </picture>
</p>
<p align="center">
  Auth0 is an easy to implement, adaptable authentication and authorization platform. To learn more checkout <a href="https://auth0.com/why-auth0">Why Auth0?</a>
</p>
<p align="center">
  This project is licensed under the Apache 2.0 license. See the <a href="https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/LICENSE">LICENSE</a> file for more info.
</p>
