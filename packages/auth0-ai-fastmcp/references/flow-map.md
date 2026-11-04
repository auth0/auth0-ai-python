# Flow Map

Before changing a flow, read its entry points and supporting helpers. Everything marked "auth0-ai-mcp" or "core SDK" lives in another package and is only wired here.

| Flow | Entry points | Also read | Docs |
|------|--------------|-----------|------|
| Configuration | `Auth0FastMCPOptions`, `Auth0FastMCP.__init__` (`config.py`) | auth0-ai-mcp `create_mcp_client`, FastMCP `Auth0MCPProvider` | `README.md`, `docs/Configuration.md` |
| Token verification | `Auth0TokenVerifier.verify_token` (`verifier.py`) | auth0-ai-mcp `McpServerClient.verify_access_token` and `build_principal`, FastMCP `TokenVerifier` | `docs/Configuration.md`, `README.md` "Configure Auth0FastMCP" |
| Required scopes | `Auth0TokenVerifier.__init__` (`verifier.py`), `Auth0FastMCPOptions.required_scopes` | FastMCP `RemoteAuthProvider` (reads `required_scopes` from the verifier) | `docs/Configuration.md` |
| Caller context | `Auth0ContextMiddleware.on_request` (`middleware.py`) | auth0-ai-mcp `bind_request_context`, `RequestContext`, `get_caller_*` | `README.md`, `EXAMPLES.md` |
| Tool scopes | `Auth0FastMCPOptions.tool_scopes`, `with_required_scopes`, `require_scopes` (`scopes.py`) | auth0-ai-mcp `with_required_scopes` and `require_scopes`, FastMCP `ToolError` | `docs/ToolScopes.md` |
| On-behalf-of exchange and caching | `Auth0FastMCPOptions.token_store`, `scope_matching`, `client_id`, `client_secret` | auth0-ai-mcp `create_mcp_client` | `docs/Configuration.md` |

Tests: `tests/test_config.py` covers option wiring, defaults, the advertised resource and scopes, the bare-domain rule, and the hidden client secret. `tests/test_verifier.py` covers accept and reject outcomes, blank tokens, an unreachable Auth0, and the debug log that never holds the token. `tests/test_middleware.py` covers the bound caller, its reset, the exempt lifecycle requests, and the missing-token path. `tests/test_scopes.py` covers the scope wrappers, including what the client sees with `mask_error_details` on and off. `tests/test_outage.py` covers the `503` middleware's edge cases. `tests/test_config.py` also sends real requests and expects the `403` and `200` for `required_scopes`, the `401` for a token with no subject, the `503` with `Retry-After` when Auth0 is down, and a tool that reads the caller in stateless and stateful sessions.

Two rules cut across every flow. Reject on every failure path, and tool code reads the caller through `get_caller_principal`, never the raw incoming token.
