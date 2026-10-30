# Flow Map

Before changing a flow, read its entry points and supporting helpers. `McpServerClient` is in `client.py` and its private helpers are in `utils/_internal/`. Everything marked "core SDK" lives in auth0-api-python and is only wrapped here.

| Flow | Entry points | Also read | Docs |
|------|--------------|-----------|------|
| Request verification | `Auth0AsgiMiddleware.__call__` (`middleware.py`) | `bearer_token` (`utils/_internal/headers.py`), `_send_unauthorized`, `_send_unavailable`, `McpServerClient.verify_access_token`, `build_principal`, `errors.py` | `README.md` "How it works", `docs/TokenVerification.md`, `EXAMPLES.md` "Wiring the ASGI adapter" |
| Caller identity | `build_principal`, `Principal` (`principal.py`) | `RequestContext`, `bind_request_context`, `set_request_context`, `reset_request_context`, `get_caller_principal`, `require_caller_principal` (`request_context.py`) | `docs/TokenVerification.md`, `docs/RequestContext.md` |
| Protected-resource metadata | `build_protected_resource_metadata` (`middleware.py`) | `Auth0AsgiMiddleware.__init__`, `_PRM_PATH` | `docs/WritingAnAdapter.md` step 4 |
| Scope enforcement | `require_scopes`, `with_required_scopes` (`scopes.py`) | `UnauthenticatedError`, `InsufficientScopeError`, `get_caller_principal` | `docs/ScopeEnforcement.md`, `EXAMPLES.md` "Writing a gated tool" |
| On-behalf-of exchange | `McpServerClient.get_token_on_behalf_of`, `RequestScopedMcpClient.get_token_on_behalf_of` | `reject_if_downscoped` (`utils/_internal/exchange.py`), `DownscopedTokenError`, core SDK `ApiClient.get_token_on_behalf_of` | `docs/OnBehalfOf.md` |
| Client credentials | `McpServerClient.get_client_credentials_token` | `GetClientCredentialsTokenError`, core SDK `ApiClient.get_client_credentials_token` | `docs/OnBehalfOf.md` "Server-identity calls" |
| Token Vault | `McpServerClient.get_token_for_connection` | `GetAccessTokenForConnectionError`, core SDK `ApiClient.get_access_token_for_connection` | `docs/TokenVault.md` |
| Token caching | `create_mcp_client(token_store=..., scope_matching=...)` | core SDK `AbstractTokenStore`, `IndexedTokenStore` | `docs/TokenCaching.md` |
| Organization policy | `create_mcp_client(organization_policy=..., organization_id=...)` | `Principal.org_id` | `docs/OrganizationPolicy.md` |
| Request context | `bind_request_context`, `require_caller_principal`, `get_caller_mcp_client`, `require_caller_mcp_client` (`request_context.py`) | `RequestScopedMcpClient` (`request_scoped_client.py`) | `docs/RequestContext.md` |

Tests: `tests/test_client.py` covers the exchange, client credentials, Token Vault, and constructor wiring. `tests/test_principal.py` covers claim normalization, `tests/test_scopes.py` covers scope enforcement, `tests/test_request_context.py` covers the request context, and `tests/test_middleware.py` covers the ASGI middleware and the metadata document.

Two rules cut across every flow. Fail closed with a typed error or a `401` on every failure path, and never let tool code see the raw incoming token.
