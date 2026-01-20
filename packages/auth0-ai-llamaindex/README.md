# Auth0 AI for LlamaIndex

`auth0-ai-llamaindex` is an SDK for building secure AI-powered applications using [Auth0](https://www.auth0.ai/), [Okta FGA](https://docs.fga.dev/) and [LlamaIndex](https://docs.llamaindex.ai/en/stable/).

![Release](https://img.shields.io/pypi/v/auth0-ai-llamaindex) ![Downloads](https://img.shields.io/pypi/dw/auth0-ai-llamaindex) [![License](https://img.shields.io/:license-APACHE%202.0-blue.svg?style=flat)](https://opensource.org/license/apache-2-0)

## Installation

> ⚠️ **WARNING**: `auth0-ai-llamaindex` is currently **under heavy development**. We strictly follow [Semantic Versioning (SemVer)](https://semver.org/), meaning all **breaking changes will only occur in major versions**. However, please note that during this early phase, **major versions may be released frequently** as the API evolves. We recommend locking versions when using this in production.

```bash
pip install auth0-ai-llamaindex
```

## Async Authorization

`Auth0AI` uses CIBA (Client Initiated Backchannel Authentication) to handle user confirmation asynchronously. This is useful when you need to confirm a user action before proceeding with a tool execution.

Full Example of [Async Authorization](https://github.com/auth0/auth0-ai-python/tree/main/examples/async-authorization/llama-index-examples).

Define a tool with the proper authorizer specifying a function to resolve the user id:

```python
from auth0_ai_llamaindex.auth0_ai import Auth0AI, set_ai_context
from auth0_ai_llamaindex.async_authorization import get_async_authorization_credentials
from llama_index.core.tools import FunctionTool

# If not provided, Auth0 settings will be read from env variables: `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, and `AUTH0_CLIENT_SECRET`
auth0_ai = Auth0AI()

with_async_authorization = auth0_ai.with_async_authorization(
    scopes=["stock:trade"],
    audience=os.getenv("AUDIENCE"),
    requested_expiry=os.getenv("REQUESTED_EXPIRY"),
    binding_message=lambda ticker, qty: f"Authorize the purchase of {qty} {ticker}",
    user_id=lambda *_, **__: session["user"]["userinfo"]["sub"],
    # Optional:
    # store=InMemoryStore()
)

def tool_function(ticker: str, qty: int) -> str:
    credentials = get_async_authorization_credentials()
    headers = {
        "Authorization": f"{credentials["token_type"]} {credentials["access_token"]}",
        # ...
    }
    # Call API

trade_tool = with_async_authorization(
    FunctionTool.from_defaults(
        name="trade_tool",
        description="Use this function to trade a stock",
        fn=tool_function,
        # ...
    )
)

# Set the thread ID to associate with the retrieved credentials
set_ai_context("<thread-id>")
```

### Async Authorization with RAR (Rich Authorization Requests)

`Auth0AI` supports RAR (Rich Authorization Requests) for Async Authorization. This allows you to provide additional authorization parameters to be displayed during the user confirmation request.

When defining the tool authorizer, you can specify the `authorization_details` parameter to include detailed information about the authorization being requested:

```python
with_async_authorization = auth0_ai.with_async_authorization(
    scopes=["stock:trade"],
    audience=os.getenv("AUDIENCE"),
    requested_expiry=os.getenv("REQUESTED_EXPIRY"),
    binding_message=lambda ticker, qty: f"Authorize the purchase of {qty} {ticker}",
    authorization_details=lambda ticker, qty: [
        {
            "type": "trade_authorization",
            "qty": qty,
            "ticker": ticker,
            "action": "buy"
        }
    ],
    user_id=lambda *_, **__: ensure_config().get("configurable", {}).get("user_id"),
    # Optional:
    # store=InMemoryStore()
)
```

To use RAR with CIBA, you need to [set up authorization details](https://auth0.com/docs/get-started/apis/configure-rich-authorization-requests) in your Auth0 tenant. This includes defining the authorization request parameters and their types. Additionally, the [Guardian SDK](https://auth0.com/docs/secure/multi-factor-authentication/auth0-guardian) is required to handle these authorization details in your authorizer app.

For more information on setting up RAR with CIBA, refer to:

- [Configure Rich Authorization Requests (RAR)](https://auth0.com/docs/get-started/apis/configure-rich-authorization-requests)
- [User Authorization with CIBA](https://auth0.com/docs/get-started/authentication-and-authorization-flow/client-initiated-backchannel-authentication-flow/user-authorization-with-ciba)

## Authorization for Tools

The `FGAAuthorizer` can leverage Okta FGA to authorize tools executions. The `FGAAuthorizer.create` function can be used to create an authorizer that checks permissions before executing the tool.

Full Example of [Authorization for Tools](https://github.com/auth0/auth0-ai-python/tree/main/examples/authorization-for-tools/llama-index-examples).

1. Create an instance of FGA Authorizer:

```python
from auth0_ai_llamaindex.fga import FGAAuthorizer

# If not provided, FGA settings will be read from env variables: `FGA_STORE_ID`, `FGA_CLIENT_ID`, `FGA_CLIENT_SECRET`, etc.
fga = FGAAuthorizer.create()
```

2. Define the FGA query (`build_query`) and, optionally, the `on_unauthorized` handler:

```python
def build_fga_query(tool_input):
    return {
        "user": f"user:{context.get("user_id")}",
        "object": f"asset:{tool_input["ticker"]}",
        "relation": "can_buy",
        "context": {"current_time": datetime.now(timezone.utc).isoformat()}
    }

def on_unauthorized(tool_input):
    return f"The user is not allowed to buy {tool_input["qty"]} shares of {tool_input["ticker"]}."

use_fga = fga(
    build_query=build_fga_query,
    on_unauthorized=on_unauthorized,
)
```

**Note**: The parameters given to the `build_query` and `on_unauthorized` functions are the same as those provided to the tool function.

3. Wrap the tool:

```python
from llama_index.core.tools import FunctionTool

async def buy_tool_function(ticker: str, qty: int) -> str:
        # TODO: implement buy operation
        return f"Purchased {qty} shares of {ticker}"

func=use_fga(buy_tool_function)

return FunctionTool.from_defaults(
    fn=func,
    async_fn=func,
    name="buy",
    description="Use this function to buy stocks",
)
```

## Calling APIs On User's Behalf

The `Auth0AI.with_token_vault` function exchanges user's refresh token for a Token Vault access token with the third-party.

Full Example of [Calling APIs On User's Behalf](https://github.com/auth0/auth0-ai-python/tree/main/examples/calling-apis/llama-index-examples).

### Basic Usage

Define a tool with the proper authorizer specifying a function to resolve the user's refresh token:

```python
from auth0_ai_llamaindex.auth0_ai import Auth0AI, set_ai_context
from auth0_ai_llamaindex.token_vault import get_credentials_from_token_vault
from llama_index.core.tools import FunctionTool

# If not provided, Auth0 settings will be read from env variables: `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, and `AUTH0_CLIENT_SECRET`
auth0_ai = Auth0AI()

with_google_calendar_access = auth0_ai.with_token_vault(
    connection="google-oauth2",
    scopes=["openid", "https://www.googleapis.com/auth/calendar.freebusy"],
    refresh_token=lambda *_args, **_kwargs: session["user"]["refresh_token"],
    # Optional:
    # authorization_params={"login_hint": "user@example.com", "ui_locales": "en"}
    # store=InMemoryStore()
)

def tool_function(date: datetime):
    credentials = get_credentials_from_token_vault()
    # Call Google API using credentials["access_token"]

check_calendar_tool = with_google_calendar_access(
    FunctionTool.from_defaults(
        name="check_user_calendar",
        description="Use this function to check if the user is available on a certain date and time",
        fn=tool_function,
        # ...
    )
)

# Set the thread ID to associate with the retrieved credentials
set_ai_context("<thread-id>")
```

### Additional Authorization Parameters

The `authorization_params` parameter is optional and can be used to pass additional authorization parameters needed to connect an account (e.g., `login_hint`, `ui_locales`):

```python
with_google_calendar_access = auth0_ai.with_token_vault(
    connection="google-oauth2",
    scopes=["openid", "https://www.googleapis.com/auth/calendar.freebusy"],
    refresh_token=lambda *_args, **_kwargs: session["user"]["refresh_token"],
    authorization_params={"login_hint": "user@example.com", "ui_locales": "en"}
)
```

## RAG with FGA

The `FGARetriever` can be used to filter documents based on access control checks defined in Okta FGA. This retriever performs batch checks on retrieved documents, returning only the ones that pass the specified access criteria.

Full Example of [RAG Application](https://github.com/auth0/auth0-ai-python/tree/main/examples/authorization-for-rag/llama-index-examples).

```python
from llama_index.core import VectorStoreIndex, Document
from auth0_ai_llamaindex import FGARetriever
from openfga_sdk.client.models import ClientCheckRequest
from openfga_sdk import ClientConfiguration
from openfga_sdk.credentials import CredentialConfiguration, Credentials

# Define some docs:
documents = [
    Document(text="This is a public doc", doc_id="public-doc"),
    Document(text="This is a private doc", doc_id="private-doc"),
]

# Create a vector store:
vector_store = VectorStoreIndex.from_documents(documents)

# Create a retriever:
base_retriever = vector_store.as_retriever()

# Create the FGA retriever wrapper.
# If not provided, FGA settings will be read from env variables: `FGA_STORE_ID`, `FGA_CLIENT_ID`, `FGA_CLIENT_SECRET`, etc.
retriever = FGARetriever(
    base_retriever,
    build_query=lambda node: ClientCheckRequest(
        user=f'user:{user}',
        object=f'doc:{node.ref_doc_id}',
        relation="viewer",
    )
)

# Create a query engine:
query_engine = RetrieverQueryEngine.from_args(
    retriever=retriever,
    llm=OpenAI()
)

# Query:
response = query_engine.query("What is the forecast for ZEKO?")

print(response)
```

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
