The `auth0-ai-fastmcp` library secures [Model Context Protocol (MCP)](https://modelcontextprotocol.io) servers built on [Prefect FastMCP](https://gofastmcp.com) with Auth0.

It is the FastMCP adapter for [`auth0-ai-mcp`](https://github.com/auth0/auth0-ai-python/tree/main/packages/auth0-ai-mcp). It wires Auth0 token verification, the caller's identity, and the On-Behalf-Of token exchange into a FastMCP server with a single configuration object.

![Release](https://img.shields.io/pypi/v/auth0-ai-fastmcp) ![Downloads](https://img.shields.io/pypi/dw/auth0-ai-fastmcp) [![License](https://img.shields.io/:license-Apache%202.0-blue.svg?style=flat)](https://opensource.org/licenses/Apache-2.0)

📚 [Documentation](#documentation) - 🚀 [Getting Started](#getting-started) - 💬 [Feedback](#feedback)

## Getting Started

### 1. Install the SDK

`auth0-ai-fastmcp` requires Python 3.10 or later and FastMCP 4.0.10 or later. It is tested with FastMCP 4.0.10 to 4.1.6.

```bash
pip install auth0-ai-fastmcp
```

With Poetry:

```bash
poetry add auth0-ai-fastmcp
```

### 2. Configure Auth0FastMCP

```python
from fastmcp import FastMCP
from auth0_ai_fastmcp import Auth0FastMCP, Auth0FastMCPOptions

auth0 = Auth0FastMCP(Auth0FastMCPOptions(
    domain="your-tenant.auth0.com",
    resource_url="https://your-api.example.com",
    tool_scopes=["tool:do_thing"],
    client_id="...",
    client_secret="...",
))

mcp = FastMCP(name="My Server", auth=auth0.provider)
mcp.add_middleware(auth0.middleware)
```

> [!IMPORTANT]
> Both `auth=auth0.provider` and `mcp.add_middleware(auth0.middleware)` are required. Without the middleware, tools cannot read the caller.

The provider checks every incoming token and the middleware makes the verified caller available to your tools, resources and prompts. See [What the middleware does](./docs/Configuration.md#what-the-middleware-does).

> [!WARNING]
> Do not add `/mcp` to the end of `resource_url`. FastMCP appends the MCP path itself.

### 3. Gate a tool

```python
from auth0_ai_fastmcp import with_required_scopes
from auth0_ai_mcp import require_caller_mcp_client

@mcp.tool
@with_required_scopes("tool:do_thing")
async def do_thing() -> str:
    auth0 = require_caller_mcp_client()
    token = await auth0.get_token_on_behalf_of(audience="https://downstream-api/", scope="read:things")
    # call the downstream API with token["access_token"]
    return "done"
```

### 4. Gate a resource or prompt

Resources and prompts are gated the same way. See [Gating resources and prompts](./docs/ToolScopes.md#gating-resources-and-prompts).

## Documentation

- [Configuration](./docs/Configuration.md) - all `Auth0FastMCPOptions` fields.
- [Tool Scopes](./docs/ToolScopes.md) - how scopes are advertised at login and how tools, resources and prompts are gated.
- [Examples](./EXAMPLES.md) - a full runnable server.

### Core guides

These guides cover the behavior this package builds on.

- [On-Behalf-Of](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/OnBehalfOf.md) - get a token for a downstream API for the caller.
- [Token Vault](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/TokenVault.md) - get a token for a third-party provider such as Google.
- [Token Caching](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/TokenCaching.md) - reuse exchanged tokens with a token store.
- [Request Context](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/RequestContext.md) - read the caller inside a tool.
- [Scope Enforcement](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/ScopeEnforcement.md) - check the caller's scopes before a tool runs.

## Feedback

### Contributing

We appreciate feedback and contribution to this repo! Before you get started, please read the following:

- [Auth0's general contribution guidelines](https://github.com/auth0/open-source-template/blob/master/GENERAL-CONTRIBUTING.md)
- [Auth0's code of conduct guidelines](https://github.com/auth0/open-source-template/blob/master/CODE-OF-CONDUCT.md)
- [This package's contribution guide](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-fastmcp/CONTRIBUTING.md)

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
  This project is licensed under the Apache 2.0 license. See the <a href="https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-fastmcp/LICENSE">LICENSE</a> file for more info.
</p>
