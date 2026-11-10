"""
Regression tests for GHSA-43rq-mx95-c3xx / SEC-80753.

Docs differing only by ``context`` must not share a batch-check result. Ordered
[denied, allowed] so a regression leaks the denied doc (fails) rather than
silently over-restricting. Mocks only the OpenFGA client, which echoes each
distinct check back like the service does.
"""
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth0_ai_langchain.FGARetriever import FGARetriever
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from openfga_sdk import ClientConfiguration
from openfga_sdk.client.models import ClientBatchCheckItem


def _make_check(context):
    check = MagicMock(spec=ClientBatchCheckItem)
    check.user = "user:jane"
    check.object = "doc:budget"
    check.relation = "viewer"
    check.context = context
    return check


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


# --- authorization policies used by the mock FGA client -----------------------

def _allow_flat(check):
    return bool(check.context and check.context.get("authorized") is True)


def _allow_nested(check):
    return bool(check.context and check.context.get("dept", {}).get("level") == 5)


# --- scenarios: (name, build_query, allowed_fn) -------------------------------

SCENARIOS = [
    (
        "same_object_differing_context",
        lambda doc: _make_check({"authorized": doc.id == "d_allow"}),
        _allow_flat,
    ),
    (
        "same_object_differing_nested_context",
        lambda doc: _make_check({"dept": {"level": 5 if doc.id == "d_allow" else 2}}),
        _allow_nested,
    ),
]


@pytest.mark.parametrize("name,build_query,allowed_fn", SCENARIOS)
def test_sync_denied_doc_is_filtered_out(name, build_query, allowed_fn):
    docs = [MagicMock(spec=Document, id="d_deny"), MagicMock(spec=Document, id="d_allow")]
    retriever = _make_retriever(build_query)
    retriever._retriever._get_relevant_documents.return_value = docs
    captured = []

    @contextmanager
    def mock_client(*args, **kwargs):
        client = MagicMock()
        client.batch_check.side_effect = lambda req: _echo_results(req, allowed_fn, captured)
        yield client

    with patch("auth0_ai_langchain.FGARetriever.OpenFgaClientSync", mock_client):
        result = retriever._get_relevant_documents("q", run_manager=MagicMock())

    ids = [d.id for d in result]
    assert ids == ["d_allow"], f"{name}: expected only d_allow, got {ids}"
    assert len(captured[0]) == 2, f"{name}: both distinct checks must be sent"


@pytest.mark.asyncio
@pytest.mark.parametrize("name,build_query,allowed_fn", SCENARIOS)
async def test_async_denied_doc_is_filtered_out(name, build_query, allowed_fn):
    docs = [MagicMock(spec=Document, id="d_deny"), MagicMock(spec=Document, id="d_allow")]
    retriever = _make_retriever(build_query)
    retriever._retriever._aget_relevant_documents = AsyncMock(return_value=docs)
    captured = []

    @asynccontextmanager
    async def mock_client(*args, **kwargs):
        client = AsyncMock()
        client.batch_check.side_effect = lambda req: _echo_results(req, allowed_fn, captured)
        yield client

    with patch("auth0_ai_langchain.FGARetriever.OpenFgaClient", mock_client):
        result = await retriever._aget_relevant_documents("q", run_manager=MagicMock())

    ids = [d.id for d in result]
    assert ids == ["d_allow"], f"{name}: expected only d_allow, got {ids}"
    assert len(captured[0]) == 2, f"{name}: both distinct checks must be sent"


def test_sync_identical_checks_are_deduplicated():
    # Fully identical checks must still dedupe to one batch item.
    docs = [MagicMock(spec=Document, id="a"), MagicMock(spec=Document, id="b")]
    retriever = _make_retriever(lambda doc: _make_check({"authorized": True}))
    retriever._retriever._get_relevant_documents.return_value = docs
    captured = []

    @contextmanager
    def mock_client(*args, **kwargs):
        client = MagicMock()
        client.batch_check.side_effect = lambda req: _echo_results(req, _allow_flat, captured)
        yield client

    with patch("auth0_ai_langchain.FGARetriever.OpenFgaClientSync", mock_client):
        result = retriever._get_relevant_documents("q", run_manager=MagicMock())

    assert len(result) == 2
    assert len(captured[0]) == 1, "identical checks must dedupe to a single batch item"
