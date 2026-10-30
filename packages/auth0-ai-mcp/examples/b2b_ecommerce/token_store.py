"""In-memory token stores for the example.

Tokens are lost on restart, so use a shared store in production.
"""

import time

from auth0_ai_mcp import AbstractTokenStore, IndexedTokenStore, TokenIndexMember, TokenSet


class InMemoryTokenStore(AbstractTokenStore):
    """Keeps encrypted tokens in a dict. Enough for scope_matching="strict"."""

    def __init__(self, *, secret: str) -> None:
        super().__init__(secret=secret)
        self._tokens: dict[str, tuple[str, int]] = {}

    async def get(self, key: str) -> TokenSet | None:
        entry = self._tokens.get(key)
        if entry is None:
            return None
        encrypted, expires_at = entry
        if expires_at <= int(time.time()):
            del self._tokens[key]
            return None
        return self.decrypt(key, encrypted)

    async def set(self, key: str, value: TokenSet) -> None:
        self._tokens[key] = (self.encrypt(key, value), value["expires_at"])

    async def delete(self, key: str) -> None:
        self._tokens.pop(key, None)


class InMemoryIndexedTokenStore(InMemoryTokenStore, IndexedTokenStore):
    """Adds the token index that scope_matching="non_strict" requires."""

    def __init__(self, *, secret: str) -> None:
        super().__init__(secret=secret)
        self._indexes: dict[str, dict[str, TokenIndexMember]] = {}

    async def add_index_member(self, index_key: str, member: TokenIndexMember) -> None:
        # No await between read and write, so this is atomic on one event loop.
        self._indexes.setdefault(index_key, {})[member["token_key"]] = member

    async def list_index_members(self, index_key: str) -> list[TokenIndexMember]:
        members = self._indexes.get(index_key, {})
        # Drop expired members so the index does not grow forever.
        now = int(time.time())
        for token_key in [k for k, m in members.items() if m["expires_at"] <= now]:
            del members[token_key]
        if not members:
            self._indexes.pop(index_key, None)
        return list(members.values())
