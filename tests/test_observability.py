import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.utils.observability import generate_request_id, generate_trace_id


def test_generate_request_id():
    id1 = generate_request_id()
    id2 = generate_request_id()
    assert id1 != id2
    assert len(id1) == 36  # UUID format


def test_generate_trace_id():
    id1 = generate_trace_id()
    id2 = generate_trace_id()
    assert id1 != id2
    assert len(id1) == 16
    assert id1.isalnum()
