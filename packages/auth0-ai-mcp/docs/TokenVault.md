# Token Vault

`get_token_for_connection` exchanges the caller's Auth0 token for a federated provider token (such as a Google or Slack access token) via Auth0 Token Vault, so a tool can call a third-party API as the user without the user's original token ever leaving the server.

## Signatures

When calling from `McpServerClient` directly (for example in custom adapter code), you supply the verified token explicitly:

```python
McpServerClient.get_token_for_connection(verified, *, connection: str, login_hint: str | None = None) -> TokenSet
```

Inside a tool, use the request-scoped client. It closes over the request's verified token internally, so the tool never touches it:

```python
RequestScopedMcpClient.get_token_for_connection(*, connection: str, login_hint: str | None = None) -> TokenSet
```

## Using it inside a tool

```python
from auth0_ai_mcp import require_caller_mcp_client, with_required_scopes

@with_required_scopes("tool:list_calendar_events")
async def list_calendar_events() -> str:
    auth0 = require_caller_mcp_client()
    token_set = await auth0.get_token_for_connection(connection="google-oauth2")
    # use token_set["access_token"] to call the Google API
```

The returned `TokenSet` carries `access_token` and `expires_at`, plus `granted_scopes` when the token response carried a `scope`. Token Vault results are not downscope-checked (see [Downscope protection](./OnBehalfOf.md#downscope-protection)). If the returned token is already expired, `get_token_for_connection` raises `GetAccessTokenForConnectionError`.

The scope in `with_required_scopes` must be in the caller's token (see [ScopeEnforcement.md](ScopeEnforcement.md#tenant-side-setup-scopes-must-be-in-the-client-grant)). The user must also have linked a Google account first, or the exchange returns `invalid_grant`. See [Linking an account](#linking-an-account).

## login_hint

Pass `login_hint` with the user's email to pre-fill the federated login prompt if the provider requires a fresh interactive step.

## Caching

If a `token_store` was passed to `create_mcp_client`, connection tokens are cached as described in [Token Caching](./TokenCaching.md#cache-key).

## Auth0 setup requirements

The Token Vault grant must be enabled on the client application in the Auth0 dashboard. The federated connection must be configured and enabled on the same application. The user must have linked their external account via Auth0's Connected Accounts flow before a token can be exchanged.

- [Configure Token Vault](https://auth0.com/docs/secure/tokens/token-vault/configure-token-vault)
- [Connected Accounts for Token Vault](https://auth0.com/docs/secure/tokens/token-vault/connected-accounts-for-token-vault)

### Linking an account

The Auth0 guides above cover the background. The steps below fill the gaps those docs leave out.

**Tenant setup (one time)**

Register a "My Account API" in the Auth0 Dashboard with audience `https://{your-domain}/me/` and add three permissions: `create:me:connected_accounts`, `read:me:connected_accounts`, and `delete:me:connected_accounts`. Then open the google-oauth2 connection settings and enable Connected Accounts (`connected_accounts.active: true`, `cross_app_access: true`) with `offline_access` turned on.

**The connect/complete flow**

To create a vault entry for a user, your app runs a server-side flow using a Regular Web App client and the My Account API audience. The steps are below.

1. Get a My Account token for the user via an Authorization Code flow with `scope=create:me:connected_accounts` and `audience=https://{domain}/me/`.
2. POST to `/me/v1/connected-accounts/connect` with that token and body `{"connection": "google-oauth2", "redirect_uri": "YOUR_CALLBACK_URL"}`. The response includes `auth_session`, `connect_uri`, and `connect_params.ticket`.
3. Redirect the user's browser to `{connect_uri}?ticket={ticket}`. The ticket expires in 300 seconds, so redirect immediately rather than waiting for manual action.
4. After the user consents on Google, Auth0 redirects to your callback URL with a `connect_code` query parameter.
5. POST to `/me/v1/connected-accounts/complete` with the same My Account token and body `{"auth_session": "...", "connect_code": "...", "redirect_uri": "..."}`. This call creates the vault entry.

**Gotchas**

> [!IMPORTANT]
> `/complete` is mandatory. Auth0 does not create the vault entry when it redirects to your callback. The entry is only created when your server calls `/complete` with the `connect_code`.

- `connect_code` arrives as a query parameter on the callback URL. Some Auth0 documentation describes it as a URL fragment. It is not.
- Auth0 returns 404 (not 403) when the path is wrong or the token is missing a required scope. If you see unexpected 404s, check both.
- The correct paths are `/me/v1/connected-accounts/accounts` (list and delete), `/me/v1/connected-accounts/connect`, and `/me/v1/connected-accounts/complete`. The path `/me/connected-accounts` without `v1` does not exist.
- The callback server must remain alive between the two callbacks (the first from Auth0 after login, the second after Google consent). A one-shot request handler shuts down too early.
- The Google account email does not need to match the Auth0 user's email.
