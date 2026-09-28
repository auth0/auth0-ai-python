from contextlib import asynccontextmanager, contextmanager
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from auth0_ai_llamaindex.FGARetriever import FGARetriever
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import Node, NodeWithScore, QueryBundle
from openfga_sdk import ClientConfiguration
from openfga_sdk.client.models import ClientBatchCheckItem


@pytest.fixture
def mock_retriever():
    return MagicMock(spec=BaseRetriever)


@pytest.fixture
def mock_fga_configuration():
    mock = MagicMock(spec=ClientConfiguration)
    return mock


@pytest.fixture
def mock_query_builder():
    return MagicMock()


@pytest.fixture
def fga_retriever(mock_retriever, mock_fga_configuration, mock_query_builder):
    return FGARetriever(
        retriever=mock_retriever,
        fga_configuration=mock_fga_configuration,
        build_query=mock_query_builder,
    )


def create_test_data(num_nodes=2):
    """Create test documents and check requests."""
    nodes = [MagicMock(spec=NodeWithScore) for _ in range(num_nodes)]
    for node in nodes:
        node.node = MagicMock(spec=Node)
    check_requests = [
        MagicMock(spec=ClientBatchCheckItem,
                  tuple_key=f"check_{i}", object=f"doc:{i}",
                  relation="viewer", user="user:jane", context=None)
        for i in range(num_nodes)
    ]
    return nodes, check_requests


def verify_query_builder_calls(mock_query_builder, nodes):
    """Verify query builder was called correctly for each document."""
    assert mock_query_builder.call_count == len(nodes)
    for node, call_args in zip(nodes, mock_query_builder.call_args_list):
        assert call_args == call(node.node)


def verify_batch_check_calls(mock_batch_check, check_requests):
    """Verify batch_check was called with correct requests."""
    mock_batch_check.assert_called_once()
    called_args = mock_batch_check.call_args
    assert called_args[0][0].checks == check_requests


@pytest.mark.asyncio
async def test_async_query_builder_integration(
    fga_retriever,
    mock_query_builder,
    mock_retriever,
    mock_fga_configuration,
):
    # Setup
    query = MagicMock(spec=QueryBundle)
    nodes, check_requests = create_test_data()

    # Configure mocks
    mock_query_builder.side_effect = check_requests
    mock_retriever._aretrieve = AsyncMock(return_value=nodes)
    mock_results = MagicMock(
        result=[
            MagicMock(
                allowed=True,
                request=MagicMock(spec=ClientBatchCheckItem,
                                  object=f"doc:{i}",
                                  relation="viewer", user="user:jane",
                                  context=None),
            )
            for i in range(2)
        ]
    )
    mock_batch_check = AsyncMock(return_value=mock_results)

    @asynccontextmanager
    async def mock_client(*args, **kwargs):
        mock = AsyncMock()
        mock.batch_check = mock_batch_check
        yield mock

    # Execute
    with patch("auth0_ai_llamaindex.FGARetriever.OpenFgaClient", mock_client):
        await fga_retriever._aretrieve(query)

        # Verify behaviors
        verify_query_builder_calls(mock_query_builder, nodes)
        verify_batch_check_calls(mock_batch_check, check_requests)


def test_sync_query_builder_integration(
    fga_retriever,
    mock_query_builder,
    mock_retriever,
    mock_fga_configuration,
):
    # Setup
    query = MagicMock(spec=QueryBundle)
    run_manager = MagicMock()
    nodes, check_requests = create_test_data()

    # Configure mocks
    mock_query_builder.side_effect = check_requests
    mock_retriever._retrieve.return_value = nodes
    mock_results = MagicMock(
        result=[
            MagicMock(
                allowed=True,
                request=MagicMock(spec=ClientBatchCheckItem,
                                  object=f"doc:{i}",
                                  relation="viewer", user="user:jane",
                                  context=None),
            )
            for i in range(2)
        ]
    )
    mock_batch_check = MagicMock(return_value=mock_results)

    @contextmanager
    def mock_client(*args, **kwargs):
        mock = MagicMock()
        mock.batch_check = mock_batch_check
        yield mock

    # Execute
    with patch("auth0_ai_llamaindex.FGARetriever.OpenFgaClientSync", mock_client):
        fga_retriever._retrieve(query)

        # Verify behaviors
        verify_query_builder_calls(mock_query_builder, nodes)
        verify_batch_check_calls(mock_batch_check, check_requests)
