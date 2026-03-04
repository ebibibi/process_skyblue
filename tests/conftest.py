"""
Pytest configuration and fixtures.
"""
import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch
from datetime import datetime, timezone


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        "bluesky": {
            "identifier": "test.bsky.social",
            "password": "test_password"
        },
        "x": {
            "api_key": "test_api_key",
            "api_secret": "test_api_secret",
            "access_token": "test_access_token",
            "access_token_secret": "test_access_token_secret"
        },
        "discord": {
            "webhook_url": "https://discord.com/api/webhooks/test"
        },
        "polling_interval": 60
    }


@pytest.fixture
def sample_bluesky_post():
    """Sample Bluesky post data for testing."""
    return {
        "uri": "at://did:plc:test/app.bsky.feed.post/test123",
        "cid": "test_cid",
        "author": {
            "did": "did:plc:test",
            "handle": "ebibibibibibi.bsky.social"
        },
        "record": {
            "text": "This is a test post from Bluesky",
            "createdAt": "2025-07-13T10:00:00.000Z"
        },
        "indexedAt": "2025-07-13T10:00:00.000Z"
    }


@pytest.fixture
def sample_long_post():
    """Sample long post that exceeds X character limit."""
    return {
        "uri": "at://did:plc:test/app.bsky.feed.post/long123",
        "cid": "test_cid_long",
        "author": {
            "did": "did:plc:test",
            "handle": "ebibibibibibi.bsky.social"
        },
        "record": {
            "text": "A" * 300,  # 300 characters
            "createdAt": "2025-07-13T10:00:00.000Z"
        },
        "indexedAt": "2025-07-13T10:00:00.000Z"
    }


@pytest.fixture
def temp_state_file():
    """Create a temporary state file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        state = {
            "last_processed_at": "2025-07-13T09:00:00.000Z",
            "last_check": "2025-07-13T09:00:00.000Z"
        }
        json.dump(state, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    os.unlink(temp_path)


@pytest.fixture
def mock_datetime():
    """Mock datetime for consistent testing."""
    with patch('process_bluesky.utils.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2025, 7, 13, 10, 0, 0, tzinfo=timezone.utc)
        mock_dt.fromisoformat = datetime.fromisoformat
        yield mock_dt