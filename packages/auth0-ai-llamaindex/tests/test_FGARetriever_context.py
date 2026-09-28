"""
Regression tests for GHSA-rcmp-9f79-cfm9 / SEC-80753.

The FGARetriever deduplicated/correlated OpenFGA results with an incomplete key
(relation/object/user, and a permissions_map keyed on ``object`` alone). Two
nodes whose checks differ only by ``context`` collapsed into a single check, and
the denied node inherited the allowed result and leaked into the output.

These tests drive the real FGARetriever and mock only the OpenFGA client. The
mock authorizes each *distinct* check on its own merits and echoes the request
back, exactly like the service, so correlating each result to the right node is
the retriever's responsibility.

Nodes are ordered [denied, allowed] on purpose: under the old key the *allowed*
check wins deduplication, so a regression would let the denied node leak —
making these tests fail rather than silently pass via over-restriction.
"""
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth0_ai_llamaindex.FGARetriever import FGARetriever
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore
from openfga_sdk import ClientConfiguration
from openfga_sdk.client.models import ClientBatchCheckItem


def _make_check(context):
    check = MagicMock(spec=ClientBatchCheckItem)
    check.user = "user:jane"
    check.object = "doc:budget"
    check.relation = "viewer"
    check.context = context
    return check


def _node(marker):
    inner = MagicMock()
    inner.marker = marker
    nws = MagicMock(spec=NodeWithScore)
    nws.id_ = marker
    nws.node = inner
    return nws


def _make_retriever(build_query):
    cfg = MagicMock(spec=ClientConfiguration)
    cfg.connection_pool_maxsize = 10
    return FGARetriever(
        retriever=MagicMock(spec=BaseRetriever),
        fga_configuration=cfg,
        build_query=build_query,
    )


def _echo_results(request, allowed_fn, captured):
    captured.append(list(request.checks))
    return MagicMock(
        result=[
            MagicMock(allowed=allowed_fn(check), request=check)
            for check in request.checks
        ]
    )


def _allow_flat(check):
    return bool(check.context and check.context.get("authorized") is True)


def _allow_nested(check):
    return bool(check.context and check.context.get("dept", {}).get("level") == 5)


SCENARIOS = [
    (
        "same_object_differing_context",
        lambda node: _make_check({"authorized": node.marker == "d_allow"}),
        _allow_flat,
    ),
    (
        "same_object_differing_nested_context",
        lambda node: _make_check({"dept": {"level": 5 if node.marker == "d_allow" else 2}}),
        _allow_nested,
    ),
]


@pytest.mark.parametrize("name,build_query,allowed_fn", SCENARIOS)
def test_sync_denied_node_is_filtered_out(name, build_query, allowed_fn):
    nodes = [_node("d_deny"), _node("d_allow")]
    retriever = _make_retriever(build_query)
    retriever._retriever._retrieve.return_value = nodes
    captured = []

    @contextmanager
    def mock_client(*args, **kwargs):
        client = MagicMock()
        client.batch_check.side_effect = lambda req: _echo_results(req, allowed_fn, captured)
        yield client

    with patch("auth0_ai_llamaindex.FGARetriever.OpenFgaClientSync", mock_client):
        result = retriever._retrieve(MagicMock())

    ids = [n.id_ for n in result]
    assert ids == ["d_allow"], f"{name}: expected only d_allow, got {ids}"
    assert len(captured[0]) == 2, f"{name}: both distinct checks must be sent"


@pytest.mark.asyncio
@pytest.mark.parametrize("name,build_query,allowed_fn", SCENARIOS)
async def test_async_denied_node_is_filtered_out(name, build_query, allowed_fn):
    nodes = [_node("d_deny"), _node("d_allow")]
    retriever = _make_retriever(build_query)
    retriever._retriever._aretrieve = AsyncMock(return_value=nodes)
    captured = []

    @asynccontextmanager
    async def mock_client(*args, **kwargs):
        client = AsyncMock()
        client.batch_check.side_effect = lambda req: _echo_results(req, allowed_fn, captured)
        yield client

    with patch("auth0_ai_llamaindex.FGARetriever.OpenFgaClient", mock_client):
        result = await retriever._aretrieve(MagicMock())

    ids = [n.id_ for n in result]
    assert ids == ["d_allow"], f"{name}: expected only d_allow, got {ids}"
    assert len(captured[0]) == 2, f"{name}: both distinct checks must be sent"


def test_sync_identical_checks_are_deduplicated():
    # Optimization guardrail: checks identical in every dimension (including
    # context) must still be sent to FGA only once.
    nodes = [_node("a"), _node("b")]
    retriever = _make_retriever(lambda node: _make_check({"authorized": True}))
    retriever._retriever._retrieve.return_value = nodes
    captured = []

    @contextmanager
    def mock_client(*args, **kwargs):
        client = MagicMock()
        client.batch_check.side_effect = lambda req: _echo_results(req, _allow_flat, captured)
        yield client

    with patch("auth0_ai_llamaindex.FGARetriever.OpenFgaClientSync", mock_client):
        result = retriever._retrieve(MagicMock())

    assert len(result) == 2
    assert len(captured[0]) == 1, "identical checks must dedupe to a single batch item"
