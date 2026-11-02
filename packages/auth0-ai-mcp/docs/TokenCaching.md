# Token Caching

The OBO cache is optional and off by default. Without a `token_store`, every call to `get_token_on_behalf_of` performs a fresh exchange and nothing is persisted anywhere. There is no default in-memory cache and no built-in `MemoryTokenStore` class.

To enable caching, pass a concrete `AbstractTokenStore` implementation to `create_mcp_client`:

```python
from auth0_ai_mcp import create_mcp_client

# store is your AbstractTokenStore implementation.
client = create_mcp_client(
    domain, audience,
    client_id="...", client_secret="...",
    token_store=store,
    scope_matching="strict",
)
```

## The store interface

`AbstractTokenStore` is exported from `auth0_ai_mcp` and defined in `auth0-api-python`. It is abstract. You provide a concrete implementation with three async methods, `get`, `set`, and `delete`. The base class takes a `secret` of at least 32 characters (for example from `openssl rand -hex 32`) and gives you `encrypt(key, value)` and `decrypt(key, data)` helpers. The SDK passes plain values to `set`, so call `self.encrypt(key, value)` in `set` and `self.decrypt(key, data)` in `get`. Otherwise the store holds tokens in plain text.

The package ships no concrete store. The [`examples/b2b_ecommerce`](../examples/b2b_ecommerce/) example includes in-memory `InMemoryTokenStore` and `InMemoryIndexedTokenStore` classes in `token_store.py`. They show the shape of a store but lose every token on restart, so a production server needs a shared store such as Redis. See [A Redis store](#a-redis-store).

> [!WARNING]
> A production store has to handle expiry itself, because the SDK never calls `delete` and never cleans up old entries. Every value passed to `set` carries an `expires_at` Unix timestamp, so set a matching TTL when you write it.

A cached token is reused only while it has more than 30 seconds left before it expires.

If the store raises on a read, the SDK logs a warning and treats it as a cache miss. If it raises on a write, the SDK logs a warning and still returns the freshly exchanged token. A store outage costs extra exchanges but never fails a tool call.

## Cache key

The cache key is derived from the caller's `sub`, the `audience`, the organization, the scopes, and the session. On Auth0 an access token has no `sid`, and on the default profile no `jti` either, so the session part is a digest of the incoming access token. Reuse therefore happens only across calls with the same access token. After a refresh the user gets a new set of entries, and the old ones stay until `expires_at`. Tokens are stored under the scopes Auth0 actually granted (see "Scope re-check on every hit" below), so two requests from the same user that end up with different granted scopes are separate cache entries under `"strict"` mode.

M2M tokens from `get_client_credentials_token` are keyed on tenant, client ID, audience, and scope set. Connection tokens from `get_token_for_connection` are keyed on tenant, client ID, `sub`, `connection`, and `login_hint` with no scope dimension. Scope-matching modes (`strict` and `non_strict`) apply to OBO tokens only.

## Scope-matching modes

`scope_matching` controls when a cached token is considered a hit.

- `"strict"` is the default. It reuses a cached token only when the granted scopes exactly equal the requested scope set, so a different scope set is simply a different entry.
- `"non_strict"` reuses a cached token whenever its granted scopes cover the requested scopes. To do this without one scope set evicting another, it keeps every distinct token plus an index of the scopes each was granted, so any cached token whose scopes cover the request can be reused. This requires a store that subclasses `IndexedTokenStore` (see below). Using `"non_strict"` with a plain store, or with no `token_store`, raises `ConfigurationError` at construction.

`"strict"` is the safer default because it never silently widens access. Use `"non_strict"` when your tools request overlapping scope sets and you want to avoid redundant exchanges.

## The indexed store

`IndexedTokenStore` extends `AbstractTokenStore` with two async methods that manage the index. Each index member is a `TokenIndexMember` holding a `token_key`, its `granted_scopes`, and its `expires_at`.

- `add_index_member(index_key, member)` adds the member, replacing any member with the same `token_key`.
- `list_index_members(index_key)` returns every member, or `[]` when the index does not exist. It may include expired members, because the SDK skips those on read.

> [!IMPORTANT]
> `add_index_member` must be atomic. Two concurrent exchanges for the same user and audience can add to the same index at once, and a read-modify-write without a lock or an atomic store operation (such as a Redis hash field write) loses one of them.

The SDK never removes members from an index, so the store should expire the whole index key. Pushing its TTL out to the latest member's `expires_at` on every add keeps it alive exactly as long as its newest token.

## A Redis store

A store for any shared key-value database follows the same three steps. Encrypt on `set`, decrypt on `get`, and give each entry a TTL that matches `expires_at`. This one uses an async `redis.asyncio.Redis` client.

```python
import time

from auth0_ai_mcp import AbstractTokenStore, TokenSet


class RedisTokenStore(AbstractTokenStore):
    def __init__(self, redis_client, *, secret: str) -> None:
        super().__init__(secret=secret)
        self._redis = redis_client

    async def get(self, key: str) -> TokenSet | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        # Redis returns bytes by default and decrypt expects str.
        if isinstance(raw, bytes):
            raw = raw.decode()
        return self.decrypt(key, raw)

    async def set(self, key: str, value: TokenSet) -> None:
        ttl = value["expires_at"] - int(time.time())
        if ttl > 0:
            await self._redis.set(key, self.encrypt(key, value), ex=ttl)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)
```

For `scope_matching="non_strict"`, subclass it with `IndexedTokenStore`. A Redis hash with one field per token makes `add_index_member` a single atomic `HSET`, so concurrent adds never lose each other.

```python
import json
import time

from auth0_ai_mcp import IndexedTokenStore, TokenIndexMember


class RedisIndexedTokenStore(RedisTokenStore, IndexedTokenStore):
    async def add_index_member(self, index_key: str, member: TokenIndexMember) -> None:
        await self._redis.hset(index_key, member["token_key"], json.dumps(member))

    async def list_index_members(self, index_key: str) -> list[TokenIndexMember]:
        raw = await self._redis.hgetall(index_key)
        now = int(time.time())
        live: list[TokenIndexMember] = []
        expired_fields = []
        for field, value in raw.items():
            member = json.loads(value)
            if member["expires_at"] > now:
                live.append(member)
            else:
                expired_fields.append(field)
        # Drop expired fields so the hash does not grow as tokens age out.
        if expired_fields:
            await self._redis.hdel(index_key, *expired_fields)
        return live
```

## Scope re-check on every hit

The scopes Auth0 actually granted can be narrower than what was requested. Both modes store the token under its granted scopes and record those granted scopes alongside it, so a downscoped token is cached. On a hit, `"strict"` reuses the token only when the granted scopes exactly equal the request, and `"non_strict"` reuses it only when the granted scopes still cover the request. A request with no scopes never reuses a cached token under `"non_strict"`.
