import pytest
from fake_llm_server import FakeLlmServer


@pytest.fixture
def fake_llm_server():
    server = FakeLlmServer()
    yield server
    server.stop()
