"""
Tests for BlueskyInputService.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import Mock, patch, MagicMock
from process_skyblue.services.bluesky_input_service import BlueskyInputService


class TestBlueskyInputService:
    """Test cases for BlueskyInputService."""
    
    @pytest.fixture
    def mock_client(self):
        """Mock atproto client."""
        with patch('process_skyblue.services.bluesky_input_service.Client') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            yield mock_client
    
    @pytest.fixture
    def service(self, mock_client):
        """BlueskyInputService instance with mocked client."""
        return BlueskyInputService(
            identifier="test.bsky.social",
            password="test_password"
        )
    
    def test_initialization(self, service):
        """Test service initialization."""
        assert service.identifier == "test.bsky.social"
        assert service.password == "test_password"
        assert service.connected is False
    
    def test_connect_success(self, service, mock_client):
        """Test successful connection."""
        mock_client.login.return_value = True
        
        result = service.connect()
        
        assert result is True
        assert service.connected is True
        mock_client.login.assert_called_once_with("test.bsky.social", "test_password")
    
    def test_connect_failure(self, service, mock_client):
        """Test connection failure."""
        mock_client.login.side_effect = Exception("Login failed")
        
        result = service.connect()
        
        assert result is False
        assert service.connected is False
    
    def test_get_latest_posts_success(self, service, mock_client, sample_bluesky_post):
        """Test successful post retrieval."""
        service.connected = True
        service.client = mock_client  # Set the mock client
        
        # Create proper mock objects that behave like ATProto objects
        mock_post = Mock()
        mock_post.uri = sample_bluesky_post["uri"]
        mock_post.cid = sample_bluesky_post["cid"]
        mock_post.author.handle = sample_bluesky_post["author"]["handle"]
        mock_post.record.text = sample_bluesky_post["record"]["text"]
        mock_post.record.created_at = sample_bluesky_post["record"]["createdAt"]
        mock_post.reply_count = 0
        mock_post.repost_count = 0
        mock_post.like_count = 0
        
        mock_feed_item = Mock()
        mock_feed_item.post = mock_post
        
        # Mock the response structure
        mock_response = Mock()
        mock_response.feed = [mock_feed_item]
        mock_client.get_author_feed.return_value = mock_response
        
        posts = service.get_latest_posts()
        
        assert len(posts) == 1
        assert posts[0]["id"] == sample_bluesky_post["uri"]
        assert posts[0]["content"] == sample_bluesky_post["record"]["text"]
        assert posts[0]["author"] == sample_bluesky_post["author"]["handle"]
        assert posts[0]["timestamp"] == sample_bluesky_post["record"]["createdAt"]
    
    def test_get_latest_posts_with_timestamp_filter(self, service, mock_client, sample_bluesky_post):
        """Test post retrieval with timestamp filter."""
        service.connected = True
        service.client = mock_client
        
        # Create proper mock object
        mock_post = Mock()
        mock_post.uri = sample_bluesky_post["uri"]
        mock_post.author.handle = sample_bluesky_post["author"]["handle"]
        mock_post.record.text = sample_bluesky_post["record"]["text"]
        mock_post.record.created_at = sample_bluesky_post["record"]["createdAt"]
        
        mock_feed_item = Mock()
        mock_feed_item.post = mock_post
        
        mock_response = Mock()
        mock_response.feed = [mock_feed_item]
        mock_client.get_author_feed.return_value = mock_response
        
        posts = service.get_latest_posts(since_timestamp="2025-07-13T09:00:00.000Z")
        
        # Should return posts newer than the timestamp
        assert len(posts) == 1
    
    def test_get_latest_posts_not_connected(self, service):
        """Test post retrieval when not connected."""
        posts = service.get_latest_posts()
        
        assert posts == []
    
    def test_get_latest_posts_api_error(self, service, mock_client):
        """Test post retrieval with API error raises RuntimeError."""
        service.connected = True
        service.client = mock_client  # Set the mock client
        mock_client.get_author_feed.side_effect = Exception("API Error")

        with pytest.raises(RuntimeError, match="Bluesky API error"):
            service.get_latest_posts()
    
    def test_disconnect(self, service):
        """Test disconnection."""
        service.connected = True
        
        service.disconnect()
        
        assert service.connected is False
    
    def test_filter_posts_by_author(self, service, sample_bluesky_post):
        """Test filtering posts by target author."""
        service.target_author = "ebibibibibibi.bsky.social"
        
        # Post from target author (use proper structure)
        target_post = {
            "author": {"handle": "ebibibibibibi.bsky.social"},
            "content": "Target post",
            "timestamp": "2025-07-13T10:00:00.000Z"
        }
        
        # Post from different author
        other_post = {
            "author": {"handle": "other.bsky.social"},
            "content": "Other post", 
            "timestamp": "2025-07-13T10:00:00.000Z"
        }
        
        posts = [target_post, other_post]
        filtered = service._filter_own_posts(posts)
        
        assert len(filtered) == 1
        assert filtered[0]["author"]["handle"] == "ebibibibibibi.bsky.social"
    
    def test_convert_to_standard_format(self, service, sample_bluesky_post):
        """Test conversion to standard post format."""
        # Create proper mock object for the new method
        mock_post = Mock()
        mock_post.uri = sample_bluesky_post["uri"]
        mock_post.cid = sample_bluesky_post["cid"]
        mock_post.author.handle = sample_bluesky_post["author"]["handle"]
        mock_post.record.text = sample_bluesky_post["record"]["text"]
        mock_post.record.created_at = sample_bluesky_post["record"]["createdAt"]
        mock_post.reply_count = 0
        mock_post.repost_count = 0
        mock_post.like_count = 0
        
        mock_feed_item = Mock()
        mock_feed_item.post = mock_post
        
        converted = service._convert_to_standard_format_from_feed_item(mock_feed_item)
        
        assert converted["id"] == sample_bluesky_post["uri"]
        assert converted["content"] == sample_bluesky_post["record"]["text"]
        assert converted["author"] == sample_bluesky_post["author"]["handle"]
        assert converted["timestamp"] == sample_bluesky_post["record"]["createdAt"]
        assert "metadata" in converted


class TestResolveFacetLinks:
    """Test cases for _resolve_facet_links method."""

    @pytest.fixture
    def service(self):
        with patch('process_skyblue.services.bluesky_input_service.Client'):
            return BlueskyInputService(
                identifier="test.bsky.social",
                password="test_password"
            )

    def _make_record(self, text, facets=None):
        """Helper to create a record-like object."""
        return SimpleNamespace(text=text, facets=facets)

    def _make_facet(self, byte_start, byte_end, uri):
        """Helper to create a facet with a link feature."""
        feature = SimpleNamespace(py_type="app.bsky.richtext.facet#link", uri=uri)
        index = SimpleNamespace(byte_start=byte_start, byte_end=byte_end)
        return SimpleNamespace(features=[feature], index=index)

    def test_no_facets_returns_original_text(self, service):
        record = self._make_record("Hello world")
        assert service._resolve_facet_links(record) == "Hello world"

    def test_none_facets_returns_original_text(self, service):
        record = self._make_record("Hello world", facets=None)
        assert service._resolve_facet_links(record) == "Hello world"

    def test_replaces_truncated_url_with_full_url(self, service):
        text = "Check this www.youtube.com/w..."
        text_bytes = text.encode('utf-8')
        # "www.youtube.com/w..." starts at byte 11, ends at byte 30
        start = text_bytes.index(b"www.youtube.com/w...")
        end = start + len(b"www.youtube.com/w...")
        facet = self._make_facet(start, end, "https://www.youtube.com/watch?v=JD3SFullVideoID")
        record = self._make_record(text, facets=[facet])

        result = service._resolve_facet_links(record)
        assert result == "Check this https://www.youtube.com/watch?v=JD3SFullVideoID"

    def test_japanese_text_with_url_facet(self, service):
        text = "動画を見て！ youtu.be/abc..."
        text_bytes = text.encode('utf-8')
        # "動画を見て！ " is 7 chars but 7*3=21 bytes (6 CJK chars * 3 + space)
        # Actually: 動(3) 画(3) を(3) 見(3) て(3) ！(3) (1 space) = 19 bytes
        start = text_bytes.index(b"youtu.be/abc...")
        end = start + len(b"youtu.be/abc...")
        facet = self._make_facet(start, end, "https://youtu.be/abcdefghijk")
        record = self._make_record(text, facets=[facet])

        result = service._resolve_facet_links(record)
        assert "https://youtu.be/abcdefghijk" in result
        assert "動画を見て！" in result

    def test_multiple_urls_replaced(self, service):
        text = "Link1: a.com/... Link2: b.com/..."
        text_bytes = text.encode('utf-8')
        start1 = text_bytes.index(b"a.com/...")
        end1 = start1 + len(b"a.com/...")
        start2 = text_bytes.index(b"b.com/...")
        end2 = start2 + len(b"b.com/...")
        facets = [
            self._make_facet(start1, end1, "https://a.com/full-path-1"),
            self._make_facet(start2, end2, "https://b.com/full-path-2"),
        ]
        record = self._make_record(text, facets=facets)

        result = service._resolve_facet_links(record)
        assert "https://a.com/full-path-1" in result
        assert "https://b.com/full-path-2" in result

    def test_non_link_facet_ignored(self, service):
        text = "Hello @mention"
        text_bytes = text.encode('utf-8')
        start = text_bytes.index(b"@mention")
        end = start + len(b"@mention")
        # Mention facet, not link
        feature = SimpleNamespace(py_type="app.bsky.richtext.facet#mention", uri=None)
        index = SimpleNamespace(byte_start=start, byte_end=end)
        facet = SimpleNamespace(features=[feature], index=index)
        record = self._make_record(text, facets=[facet])

        result = service._resolve_facet_links(record)
        assert result == "Hello @mention"

    def test_full_url_not_truncated_still_works(self, service):
        """When text already has the full URL, facet replacement should still work."""
        text = "See https://example.com/full"
        text_bytes = text.encode('utf-8')
        start = text_bytes.index(b"https://example.com/full")
        end = start + len(b"https://example.com/full")
        facet = self._make_facet(start, end, "https://example.com/full")
        record = self._make_record(text, facets=[facet])

        result = service._resolve_facet_links(record)
        assert result == "See https://example.com/full"