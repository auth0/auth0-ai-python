"""
Regression tests for GHSA-rcmp-9f79-cfm9 / SEC-80753.

The FGARetriever deduplicated/correlated OpenFGA results with an incomplete key
(relation/object/user, and a permissions_map keyed on ``object`` alone). Two
documents whose checks differ only by ``context`` collapsed into a single check,
and the denied document inherited the allowed result and leaked into the output.

These tests drive the real FGARetriever and mock only the OpenFGA client. The
mock authorizes each *distinct* check on its own merits and echoes the request
back, exactly like the service, so correlating each result to the right document
is the retriever's responsibility.

Docs are ordered [denied, allowed] on purpose: under the old key the *allowed*
check wins deduplication, so a regression would let the denied document leak —
making these tests fail rather than silently pass via over-restriction.
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
    """Echo each check back with an allowed flag derived from its context."""
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
    # Optimization guardrail: checks identical in every dimension (including
    # context) must still be sent to FGA only once.
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
