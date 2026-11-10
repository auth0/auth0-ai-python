"""
Regression tests for GHSA-43rq-mx95-c3xx / SEC-80753.

Nodes differing only by ``context`` must not share a batch-check result. Ordered
[denied, allowed] so a regression leaks the denied node (fails) rather than
silently over-restricting. Mocks only the OpenFGA client, which echoes each
distinct check back like the service does.
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
    # Fully identical checks must still dedupe to one batch item.
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
