# B2B Ecommerce MCP Server (ASGI)

This is an MCP server for a pretend online store whose backend is split into separate services
for orders, payments, inventory, shipping, customers, notifications and analytics. Each service
is its own API in Auth0. When a user calls a tool, the server takes the user's one token and
swaps it for a separate, narrower token for each service it needs to talk to. Real company
backends are built this way, so the example walks through it end to end on a live Auth0 tenant.

The store itself is fake, so every tool just returns a one-line message. The security is real.
Incoming tokens are actually checked, and the per-service tokens actually come from Auth0
through the on-behalf-of (OBO) token exchange.

## The services and the tools

There are seven downstream services. Each one is a separate API with its own audience and
scopes.

| Service | Audience | Scopes |
|---|---|---|
| Orders | `https://orders.api/` | `cancel:orders`, `read:orders`, `write:orders` |
| Payments | `https://payments.api/` | `refund:payments` |
| Inventory | `https://inventory.api/` | `read:inventory`, `write:inventory` |
| Shipping | `https://shipping.api/` | `read:shipments`, `create:shipments` |
| Customers | `https://customers.api/` | `read:customers`, `write:customers` |
| Notifications | `https://notifications.api/` | `send:notifications` |
| Analytics | `https://analytics.api/` | `read:analytics` (M2M) |

The server has five tools, and a user needs a matching `tool:*` scope to call each one. Four of
them talk to several services in a single call. The fifth, `sales_analytics_report`, does not
act for the user at all. It gets a machine-to-machine (M2M) token for the server itself. Each
tool asks every service for only the scopes it really needs.

| Tool | Scope needed to call it | Services it calls (scope it asks for) |
|---|---|---|
| `cancel_and_refund_order` | `tool:cancel_and_refund_order` | orders (`cancel:orders`), payments (`refund:payments`) |
| `fulfill_order` | `tool:fulfill_order` | orders (`read:orders`), inventory (`read:inventory write:inventory`), shipping (`read:shipments create:shipments`), notifications (`send:notifications`) |
| `order_status_report` | `tool:order_status_report` | orders (`read:orders`), inventory (`read:inventory`), shipping (`read:shipments`), customers (`read:customers`) |
| `update_customer_and_notify` | `tool:update_customer_and_notify` | customers (`read:customers write:customers`), notifications (`send:notifications`) |
| `sales_analytics_report` | `tool:sales_analytics_report` | analytics (M2M, `read:analytics`) |

Start with `cancel_and_refund_order`, because it shows the whole idea in one call. If the
user's token lacks `tool:cancel_and_refund_order`, the call is turned away before any
downstream token is requested. Otherwise the server swaps the user's token twice, once for
orders and once for payments.

## How little auth code lives in the tool

The SDK takes care of checking the token, publishing the login metadata, swapping tokens,
caching them and checking their scopes. The tool itself reads like ordinary business code. One
decorator checks the caller's scope, and one call per service hands back a token that is ready
to use.

```python
@with_required_scopes("tool:cancel_and_refund_order")
async def cancel_and_refund_order(order_id: str, amount: str) -> str:
    auth0 = require_caller_mcp_client()
    orders_token = await auth0.get_token_on_behalf_of(audience=ORDERS_AUDIENCE, scope="cancel:orders")
    payments_token = await auth0.get_token_on_behalf_of(audience=PAYMENTS_AUDIENCE, scope="refund:payments")
    ...
```

Here is what happens behind those few lines.

- Before any tool runs, the middleware checks the incoming token, works out who the caller is
  (the `Principal`) and makes that available to the tool. It also serves the RFC 9728
  `/.well-known/oauth-protected-resource` metadata that tells Claude Code how to log in. A
  request with a missing or bad token gets a `401` with a `WWW-Authenticate` header and never
  reaches a tool.
- `get_token_on_behalf_of` swaps the user's token for a service token and caches it under the
  scopes Auth0 actually granted. If Auth0 grants fewer scopes than the tool asked for, the call
  raises, so a tool never quietly runs with too little access. Reusing a cached token is safe
  for the same reason, because its scopes are checked again every time.
- `with_required_scopes` checks the caller's scopes before the tool body runs and raises
  `insufficient_scope` if one is missing.

You can leave out `scope` on a `get_token_on_behalf_of` call. Auth0 then returns a token with no
`scope`, and in `non_strict` mode such a call never reuses a cached token.

## The wiring

The package ships the middleware, so the server only has to mount it. This is from
`server.py`:

```python
mcp_client = create_mcp_client(
    DOMAIN,
    AUDIENCE,
    client_id=os.environ["OBO_CLIENT_ID"],
    client_secret=os.environ["OBO_CLIENT_SECRET"],
    token_store=store,
    scope_matching=SCOPE_MATCHING,
    organization_policy="required" if ORGANIZATION_ID else "allow",
    organization_id=ORGANIZATION_ID,
)

...

app = Auth0AsgiMiddleware(
    mcp.streamable_http_app(host="127.0.0.1"),
    mcp_client=mcp_client,
    scopes_supported=TOOL_SCOPES,
)
```

The middleware takes the advertised resource and the Auth0 login server from `mcp_client`, so `AUTH0_AUDIENCE` and `AUTH0_DOMAIN` are the only values to set. Here it wraps the MCP SDK's streamable-HTTP app. `Auth0AsgiMiddleware` is plain ASGI
middleware, so a FastAPI or Starlette app can be wrapped the same way.

## The OBO token cache

Every `get_token_on_behalf_of` call swaps the user's token for a service token at Auth0, which
costs a network round trip. With a cache, the SDK keeps each token it gets and hands it back the
next time a tool asks for the same user, service and scopes. Caching is on when you pass a
`token_store` to `create_mcp_client`, and off without one. This example keeps tokens in memory
(`token_store.py`), so a restart loses them. [Token Caching](../../docs/TokenCaching.md) explains what a shared,
production store needs.

The `scope_matching` option on `create_mcp_client` decides when a saved token is good enough to hand back.
This example reads it from `SCOPE_MATCHING` in `.env`.

| | `strict` (default) | `non_strict` |
|---|---|---|
| Reuses a saved token when | its scopes exactly match what the tool asks for | its scopes include everything the tool asks for |
| A `read:inventory` request after a `read:inventory write:inventory` swap | does a new swap | reuses the saved token |
| Store it needs | any `AbstractTokenStore` | an `IndexedTokenStore`, which also tracks the scopes of each saved token. A plain store, or no store at all, raises `ConfigurationError` at startup. This example switches to `InMemoryIndexedTokenStore` on its own. |
| Pick it when | you have no reason not to. Each tool gets a token with only the access it asked for. | several tools call the same service with overlapping scopes and the extra swaps matter to you |
| Trade-off | more swaps | a tool can get a token with more access than it asked for |

## What you need on the tenant

You will register eight APIs, one for the MCP server itself and one per downstream service, and
two clients. Every step uses the Auth0 CLI against your own tenant. Swap in your own ids where
the commands say `YOUR_...`.

> **Log in to the Auth0 CLI with extra scopes first.** A plain `auth0 login` cannot run every
> command below. Log in once like this before you start.
>
> ```bash
> auth0 login --scopes create:client_grants,create:organization_clients
> ```
>
> If a command still fails with `access token lacks scope: <scope>`, run
> `auth0 login --scopes <scope>` and try the command again.

### 1. Register the APIs

The MCP server's own API is the one Claude Code's login token is issued for, so its identifier
has to match `AUTH0_AUDIENCE`.

```bash
auth0 apis create --name "B2B Ecommerce MCP" --identifier "http://localhost:3002/mcp" --signing-alg RS256
auth0 apis create --name "Orders Service"        --identifier "https://orders.api/"        --signing-alg RS256 --scopes "cancel:orders,read:orders,write:orders"
auth0 apis create --name "Payments Service"      --identifier "https://payments.api/"      --signing-alg RS256 --scopes "refund:payments"
auth0 apis create --name "Inventory Service"     --identifier "https://inventory.api/"     --signing-alg RS256 --scopes "read:inventory,write:inventory"
auth0 apis create --name "Shipping Service"      --identifier "https://shipping.api/"      --signing-alg RS256 --scopes "read:shipments,create:shipments"
auth0 apis create --name "Customers Service"     --identifier "https://customers.api/"     --signing-alg RS256 --scopes "read:customers,write:customers"
auth0 apis create --name "Notifications Service" --identifier "https://notifications.api/" --signing-alg RS256 --scopes "send:notifications"
```

Then add the five tool scopes to the MCP API, using the id from its create output.

```bash
auth0 api patch "resource-servers/YOUR_MCP_API_ID" --data '{"scopes":[
  {"value":"tool:cancel_and_refund_order","description":"Cancel and refund an order"},
  {"value":"tool:fulfill_order","description":"Fulfill an order"},
  {"value":"tool:order_status_report","description":"Read an order status report"},
  {"value":"tool:update_customer_and_notify","description":"Update a customer and notify"},
  {"value":"tool:sales_analytics_report","description":"Run the sales analytics report"}
]}'
```

### 2. Create the OBO client

Token swapping only works through a Custom API client, which is a client with `app_type` set to
`resource_server` and tied to the MCP server's API.

```bash
auth0 api post clients --data '{
  "name": "B2B Ecommerce OBO Client",
  "app_type": "resource_server",
  "resource_server_identifier": "http://localhost:3002/mcp"
}'
```

A Regular Web App will not work here. Trying it fails with
`This client is not a resource server and cannot exchange access tokens`.

Next, turn on the OBO exchange for that client, using its id from the create output.

```bash
auth0 api patch "clients/YOUR_OBO_CLIENT_ID" \
  --data '{"token_exchange":{"allow_any_profile_of_type":["on_behalf_of_token_exchange"]}}'
```

Now give the OBO client access to every downstream API on behalf of users, which is why
`subject_type` is `user`. Give each service exactly the scopes its tools ask for.

```bash
auth0 api post client-grants --data '{"client_id":"YOUR_OBO_CLIENT_ID","audience":"https://orders.api/","scope":["cancel:orders","read:orders","write:orders"],"subject_type":"user"}'
auth0 api post client-grants --data '{"client_id":"YOUR_OBO_CLIENT_ID","audience":"https://payments.api/","scope":["refund:payments"],"subject_type":"user"}'
auth0 api post client-grants --data '{"client_id":"YOUR_OBO_CLIENT_ID","audience":"https://inventory.api/","scope":["read:inventory","write:inventory"],"subject_type":"user"}'
auth0 api post client-grants --data '{"client_id":"YOUR_OBO_CLIENT_ID","audience":"https://shipping.api/","scope":["read:shipments","create:shipments"],"subject_type":"user"}'
auth0 api post client-grants --data '{"client_id":"YOUR_OBO_CLIENT_ID","audience":"https://customers.api/","scope":["read:customers","write:customers"],"subject_type":"user"}'
auth0 api post client-grants --data '{"client_id":"YOUR_OBO_CLIENT_ID","audience":"https://notifications.api/","scope":["send:notifications"],"subject_type":"user"}'
```

If these fail with `access token lacks scope: create:client_grants`, the CLI is missing the
login scopes from the top of [What you need on the tenant](#what-you-need-on-the-tenant). Log
in again with them and rerun the grants.

Last, let the OBO client get tokens for the downstream APIs without showing the user a consent
screen. Run this on each downstream API with its id.

```bash
auth0 api patch "resource-servers/YOUR_ORDERS_API_ID"        --data '{"skip_consent_for_verifiable_first_party_clients":true}'
auth0 api patch "resource-servers/YOUR_PAYMENTS_API_ID"      --data '{"skip_consent_for_verifiable_first_party_clients":true}'
auth0 api patch "resource-servers/YOUR_INVENTORY_API_ID"     --data '{"skip_consent_for_verifiable_first_party_clients":true}'
auth0 api patch "resource-servers/YOUR_SHIPPING_API_ID"      --data '{"skip_consent_for_verifiable_first_party_clients":true}'
auth0 api patch "resource-servers/YOUR_CUSTOMERS_API_ID"     --data '{"skip_consent_for_verifiable_first_party_clients":true}'
auth0 api patch "resource-servers/YOUR_NOTIFICATIONS_API_ID" --data '{"skip_consent_for_verifiable_first_party_clients":true}'
```

Without it the swap fails with
`The API must have "Allow Skipping User Consent for Verifiable First-Party Clients" enabled`,
which is the Dashboard name for this same setting.

### 3. Register Claude Code as a client

Claude Code does not register itself on the fly. It identifies itself with a Client ID Metadata
Document (CIMD), which is a public URL it uses as its client id, so you register that URL on
your tenant. First turn on Settings > Advanced > `Client ID Metadata Document Registration`,
then run these two calls.

```bash
auth0 api post "clients/cimd/preview"  --data '{"external_client_id":"https://claude.ai/oauth/claude-code-client-metadata"}'
auth0 api post "clients/cimd/register" --data '{"external_client_id":"https://claude.ai/oauth/claude-code-client-metadata"}'
```

The `preview` call only fetches and checks the document, so it is safe to run first.
`register` creates the client and returns a client id that starts with `tpc_`. If you skip
this, the login fails with
`invalid_request: Unknown client: https://claude.ai/oauth/claude-code-client-metadata`.

Then give that `tpc_` client access to the MCP API with all five tool scopes, using the id from
the register output.

```bash
auth0 api post client-grants --data '{"client_id":"YOUR_TPC_CLIENT_ID","audience":"http://localhost:3002/mcp","scope":["tool:cancel_and_refund_order","tool:fulfill_order","tool:order_status_report","tool:update_customer_and_notify","tool:sales_analytics_report"],"subject_type":"user"}'
```

This grant is easy to forget. Without it the login goes through but every tool call fails with
`Client ... is not authorized to access resource server YOUR_MCP_AUDIENCE`. Third-party
(`tpc_`) clients never get an API's allow-all access, so they always need their own grant.

### 4. Set up the analytics API for the M2M tool

`sales_analytics_report` gets its token with client credentials instead of swapping the user's
token. Create the analytics API and let the OBO client use client credentials against it.

```bash
# Create the API
auth0 apis create --name "Analytics Service" \
  --identifier "https://analytics.api/" \
  --scopes "read:analytics"

# Let the OBO client use client credentials against it
auth0 api post "client-grants" \
  --data '{"client_id":"YOUR_OBO_CLIENT_ID","audience":"https://analytics.api/","scope":["read:analytics"]}'
```

The OBO client also needs `client_credentials` in its grant types. The CLI's `apps update` has
no option for that, so use the Management API. A PATCH replaces the whole list, so look at the
current list first.

```bash
auth0 api get "clients/YOUR_OBO_CLIENT_ID?fields=grant_types"
```

Then send back that same list with `client_credentials` added.

```bash
auth0 api patch "clients/YOUR_OBO_CLIENT_ID" \
  --data '{"grant_types":["EXISTING_GRANT_TYPES","client_credentials"]}'
```

## Configure and run

Copy `.env.example` to `.env` and fill it in.

```bash
cp .env.example .env
```

```
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_ORGANIZATION_ID=
AUTH0_AUDIENCE=http://localhost:3002/mcp
ORDERS_AUDIENCE=https://orders.api/
PAYMENTS_AUDIENCE=https://payments.api/
INVENTORY_AUDIENCE=https://inventory.api/
SHIPPING_AUDIENCE=https://shipping.api/
CUSTOMERS_AUDIENCE=https://customers.api/
NOTIFICATIONS_AUDIENCE=https://notifications.api/
ANALYTICS_AUDIENCE=https://analytics.api/
TOKEN_STORE_SECRET=
SCOPE_MATCHING=strict
OBO_CLIENT_ID=
OBO_CLIENT_SECRET=
```

Run `poetry install` in the package folder, then start the server from the example folder.

```bash
poetry install
cd examples/b2b_ecommerce && poetry run python server.py
```

Add the server to Claude Code. The URL has to end in `/mcp`, because that is where the server
listens. Pointing Claude Code at `http://localhost:3002` alone fails with
`MCP endpoint not found`.

```bash
claude mcp add --transport http b2b-ecommerce http://localhost:3002/mcp
```

## Adding a new downstream service and tool

Say you want a `returns` service and a `process_return` tool that reads orders and writes a
return. These are the steps.

1. Register the service API and its scopes.

   ```bash
   auth0 apis create --name "Returns Service" --identifier "https://returns.api/" --signing-alg RS256 --scopes "read:returns,write:returns"
   ```

2. Give the OBO client access to it on behalf of users, with the scopes the tool will ask for.

   ```bash
   auth0 api post client-grants --data '{"client_id":"YOUR_OBO_CLIENT_ID","audience":"https://returns.api/","scope":["read:returns","write:returns"],"subject_type":"user"}'
   ```

3. Let the OBO client skip consent on the new API.

   ```bash
   auth0 api patch "resource-servers/YOUR_RETURNS_API_ID" --data '{"skip_consent_for_verifiable_first_party_clients":true}'
   ```

4. Add the tool's scope to the MCP API.

   ```bash
   auth0 api patch "resource-servers/YOUR_MCP_API_ID" --data '{"scopes":[{"value":"tool:process_return","description":"Process a return"}]}'
   ```

5. Update the `tpc_` client's grant to include the new scope. The new scope list replaces the
   old one, so send every existing `tool:*` scope plus `tool:process_return`.

6. Add `RETURNS_AUDIENCE=https://returns.api/` to `.env` and read it in the tools file.

7. Write the tool. Check the scope, then ask for one token per service it calls.

   ```python
   @mcp.tool(name="process_return", title="Process Return")
   @with_required_scopes("tool:process_return")
   async def process_return(order_id: str) -> str:
       auth0 = require_caller_mcp_client()
       orders_token = await auth0.get_token_on_behalf_of(audience=ORDERS_AUDIENCE, scope="read:orders")
       returns_token = await auth0.get_token_on_behalf_of(audience=RETURNS_AUDIENCE, scope="read:returns write:returns")
       ...
   ```

8. Add `tool:process_return` to `TOOL_SCOPES` in `server.py` so Claude Code asks for it at login.

## Try Token Vault

The example has no Token Vault tool, but adding one takes a few lines. A tool asks for a
Google token the same way it asks for a downstream API token, and the SDK caches it.

```python
@mcp.tool(name="list_calendar_events", title="List Calendar Events")
@with_required_scopes("tool:list_calendar_events")
async def list_calendar_events() -> str:
    auth0 = require_caller_mcp_client()
    token_set = await auth0.get_token_for_connection(connection="google-oauth2")
    # call the Google Calendar API with token_set["access_token"]
```

Add `tool:list_calendar_events` to `TOOL_SCOPES` in `server.py` and to the MCP API's
permissions, then log in again with `/mcp`. The user also needs a linked Google account first.
The tenant setup and the linking steps are in [Token Vault](../../docs/TokenVault.md).

## Running in B2B org mode

Setting `AUTH0_ORGANIZATION_ID` in `.env` makes the server accept only users from that one
organization. A token with no `org_id` claim is turned away, and so is a token whose `org_id`
is a different organization. The setup below gets Auth0 to put the right `org_id` in the token
when the user logs in. You only do it once per tenant.

**1. Let the OBO client work with organizations.**

```bash
auth0 api patch "clients/YOUR_OBO_CLIENT_ID" \
  --data '{"organization_usage":"allow"}'
```

OBO clients do not have this by default, and it only matters in org mode. A user's token in
org mode carries an `org_id`, so the swap happens inside that organization, and a client
without `organization_usage` set to `allow` is refused with a `400` and
`parameter organization is not allowed for this client`.

**2. Add your test user to the organization.**

```bash
auth0 orgs members add YOUR_ORG_ID --user-id YOUR_USER_ID
```

**3. Make the Claude Code client require an organization at login.**

```bash
auth0 api patch "clients/YOUR_TPC_CLIENT_ID" \
  --data '{"organization_usage":"require","organization_require_behavior":"post_login_prompt"}'
```

With this, Auth0 asks the user to pick the organization after they log in, and the token comes
back with `org_id`. Claude Code does not need to know anything about Auth0 organizations.

**4. Add the Claude Code client to the organization.**

```bash
auth0 api post "organizations/YOUR_ORG_ID/clients" \
  --data '{"clients":[{"client_id":"YOUR_TPC_CLIENT_ID","use_for_member_access":true}]}'
```

The user being a member is not enough on its own, because the client has to be added to the
organization as well. Without this step the login fails with `client requires organization
membership, but user does not belong to any organization`, even for a real member.

You do not have to pass the organization when swapping tokens. Auth0 copies `org_id` from the
user's token into every downstream token on its own.

## Troubleshooting

### Every tool call fails the scope check

Check that `Auth0AsgiMiddleware` gets `scopes_supported` with every tool scope, the way
`server.py` does. Claude Code learns which scopes to ask for from that list. Without it the
token arrives with an empty `scope` claim and every `with_required_scopes` check fails.

### A new scope never shows up in the token

Adding a scope to the MCP API does not add it to existing grants, and Auth0 silently leaves a
scope out of the token when the client's grant does not include it. Update the `tpc_` client's
grant with the full list.

```bash
auth0 api patch "client-grants/YOUR_GRANT_ID" \
  --data '{"scope":["existing:scope","new:scope"]}'
# find the grant id: auth0 api get "client-grants?client_id=YOUR_TPC_CLIENT_ID&audience=YOUR_AUDIENCE"
```

### Every request gets a 401

Make sure the identifier of the MCP server's API in Auth0 is exactly `AUTH0_AUDIENCE`, and that
`AUTH0_AUDIENCE` is the URL clients use to reach the server. MCP clients read `resource` from
the `/.well-known/oauth-protected-resource` metadata, which is the audience, and ask for a token
for exactly that value. If the API is registered under a different identifier, the token's `aud`
will not match and the middleware turns every request away.

### Tokens still carry `org_id` after leaving org mode

Step 3 of org mode set the `tpc_` client's `organization_usage` to `require`, and with that
every token carries `org_id` even when `AUTH0_ORGANIZATION_ID` is empty. Set it back to `allow`
before running without an organization.

## Test the full example

With the server running and added to Claude Code, try these prompts in order.

```
Use the b2b-ecommerce MCP server to cancel and refund order ORD-1042, amount 250 USD.
Use b2b-ecommerce to fulfill order ORD-1042.
Use b2b-ecommerce to run an order status report for ORD-1042.
Use b2b-ecommerce to update customer CUST-77 and notify them.
Use b2b-ecommerce to run the sales analytics report.
Use b2b-ecommerce to run an order status report for ORD-1042 again.
```

The first prompt opens a browser to log in and approve access. After that the tool runs, and
behind the scenes the server swaps your one token for an orders token and a payments token.
The fulfill and status prompts use the token cache. The analytics prompt is
the M2M tool, so it runs without your token. The repeated status report comes straight from the
cache.

To try org mode, set `AUTH0_ORGANIZATION_ID`, restart the server and run the first prompt again.
[Running in B2B org mode](#running-in-b2b-org-mode) has the setup.
