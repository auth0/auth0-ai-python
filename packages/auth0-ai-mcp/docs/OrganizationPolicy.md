# Organization Policy

Organization policy controls whether tokens carrying an Auth0 Organization `org_id` claim are required, and which organizations are accepted.

Set it with the `organization_policy` argument on `create_mcp_client`.

## Modes

- `"allow"` (the default) - accepts tokens whether or not they carry an `org_id` claim. Tokens from organization members and tokens without any organization both pass verification.
- `"required"` - the token must carry an `org_id` claim. Tokens without one are rejected with a `401`. When `organization_id` is also set, only tokens from the specified organization (or one of the specified organizations) are accepted.

## Setting an organization ID

`organization_id` pins accepted tokens to a specific organization or a set of organizations. It takes a single string or a list of strings.

```python
from auth0_ai_mcp import create_mcp_client

client = create_mcp_client(
    domain="your-tenant.auth0.com",
    audience="https://your-mcp-server/mcp",
    organization_policy="required",
    organization_id="org_abc",
)
```

`organization_id` is only valid with `organization_policy="required"`. Setting it with `"allow"` (the default) raises `ConfigurationError` when the client is created.

A token from a rejected organization looks like any other bad token to the caller, a generic `401`.

To accept tokens from multiple organizations:

```python
client = create_mcp_client(
    domain="your-tenant.auth0.com",
    audience="https://your-mcp-server/mcp",
    organization_policy="required",
    organization_id=["org_abc", "org_xyz"],
)
```

> [!IMPORTANT]
> The Auth0 application you use for the On-Behalf-Of exchange needs `organization_usage` set to `allow`. Without it, an exchange for a user who signed in through an organization is refused with a `400` and `parameter organization is not allowed for this client`.

## Reading org_id in tool code

Once a token passes verification, `principal.org_id` holds the organization from the token's `org_id` claim. It is `None` for tokens that carry no Organization. See [Token Verification](./TokenVerification.md) for the full `Principal` field reference.

## Related

- [Token Verification](./TokenVerification.md) - the `Principal.org_id` field and how claims are checked.
- [Request Context](./RequestContext.md) - reading the `Principal` inside a tool.
