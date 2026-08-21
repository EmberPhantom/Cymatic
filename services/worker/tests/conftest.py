"""Worker test configuration - mock LLM client for test isolation"""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def mock_llm_client():
    """Mock LLM client to prevent real network calls in tests.

    All agent functions fall through to their keyword-based fallback paths.
    """
    with patch(
        "cymatic_shared.agents.llm_client.call_llm_json",
        new_callable=AsyncMock,
        return_value={},
    ) as mock:
        yield mock
