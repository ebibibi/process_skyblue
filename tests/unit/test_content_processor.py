"""
Tests for ContentProcessor.
"""
import pytest
from process_skyblue.utils.content_processor import ContentProcessor


class TestContentProcessor:
    """Test cases for ContentProcessor."""
    
    def test_truncate_short_content(self):
        """Test that short content is not truncated."""
        processor = ContentProcessor()
        content = "Short post"
        
        result = processor.truncate_for_x(content)
        
        assert result == "Short post"
    
    def test_truncate_exactly_280_chars(self):
        """Test content that is exactly 280 characters."""
        processor = ContentProcessor()
        content = "A" * 280
        
        result = processor.truncate_for_x(content)
        
        assert result == content
        assert len(result) == 280
    
    def test_truncate_over_280_chars(self):
        """Test content over 280 characters gets truncated with ellipsis."""
        processor = ContentProcessor()
        content = "A" * 300  # 300 characters
        
        result = processor.truncate_for_x(content)
        
        assert result.endswith("...")
        assert len(result) == 280
        assert result == "A" * 277 + "..."
    
    def test_truncate_with_word_boundary(self):
        """Test truncation respects word boundaries when possible."""
        processor = ContentProcessor()
        # 290 characters with words
        content = "This is a long post " * 14 + "that exceeds"
        
        result = processor.truncate_for_x(content, respect_word_boundary=True)
        
        assert result.endswith("...")
        assert len(result) <= 280
        # Should not cut in middle of word
        assert not result[:-3].endswith(" that")
    
    def test_clean_content_removes_extra_whitespace(self):
        """Test content cleaning removes extra whitespace."""
        processor = ContentProcessor()
        content = "  Multiple   spaces    and\n\nnewlines  "
        
        result = processor.clean_content(content)
        
        assert result == "Multiple spaces and newlines"
    
    def test_clean_content_handles_unicode(self):
        """Test content cleaning handles Unicode characters."""
        processor = ContentProcessor()
        content = "Testing émojis 🚀 and ñíñó characters"
        
        result = processor.clean_content(content)
        
        assert result == content  # Should remain unchanged
    
    def test_process_for_x_complete_workflow(self):
        """Test complete processing workflow for X posting."""
        processor = ContentProcessor()
        # Long content with extra whitespace
        content = "  This is a very long post   " + "with lots of content " * 20
        
        result = processor.process_for_x(content)
        
        # Should be cleaned and truncated
        assert not result.startswith(" ")
        assert not result.endswith(" ")
        assert len(result) <= 280
        if len(content.strip()) > 280:
            assert result.endswith("...")
    
    def test_extract_mentions(self):
        """Test extraction of @mentions from content."""
        processor = ContentProcessor()
        content = "Hello @user1 and @user2! Check out @user3's post."
        
        mentions = processor.extract_mentions(content)
        
        assert mentions == ["@user1", "@user2", "@user3"]
    
    def test_extract_hashtags(self):
        """Test extraction of #hashtags from content."""
        processor = ContentProcessor()
        content = "Testing #python #ai and #automation hashtags"
        
        hashtags = processor.extract_hashtags(content)
        
        assert hashtags == ["#python", "#ai", "#automation"]
    
    def test_count_characters_unicode(self):
        """Test character counting with Unicode characters."""
        processor = ContentProcessor()
        content = "Testing 日本語 and émojis 🚀🌟"

        count = processor.count_characters(content)

        assert count == len(content)

    def test_split_for_thread_does_not_break_url(self):
        """Test that URLs are never split across thread chunks."""
        processor = ContentProcessor()
        # Build content where a URL would land right at the split boundary
        url = "https://example.com/very/long/path/to/some/page?query=value&foo=bar"
        # Pad before URL to push it near the 270-char split boundary
        padding = "A" * 240 + " "
        content = padding + url + " " + "B" * 200

        chunks = processor.split_for_thread(content)

        # Verify URL is intact in one of the chunks
        url_found = any(url in chunk for chunk in chunks)
        assert url_found, f"URL was split across chunks: {chunks}"

        # Also verify no chunk contains a partial URL
        for chunk in chunks:
            if "https://" in chunk:
                assert url in chunk, f"Chunk contains partial URL: {chunk}"

    def test_split_for_thread_url_at_end(self):
        """Test splitting when URL is at the end of content."""
        processor = ContentProcessor()
        padding = "これはテスト投稿です。" * 15  # Long Japanese text
        url = "https://note.com/ebisuda/n/abc123"
        content = padding + " " + url

        chunks = processor.split_for_thread(content)

        # URL must be intact in one chunk
        url_found = any(url in chunk for chunk in chunks)
        assert url_found, f"URL was split: {chunks}"

    def test_split_for_thread_url_with_dots_not_treated_as_sentence_end(self):
        """Test that dots within URLs are not treated as sentence-ending split points."""
        processor = ContentProcessor()
        url = "https://www.example.co.jp/path/page.html"
        # Put enough text before URL to exceed one tweet
        content = "A" * 250 + " " + url + " " + "B" * 100

        chunks = processor.split_for_thread(content)

        url_found = any(url in chunk for chunk in chunks)
        assert url_found, f"URL was split (likely at dot): {chunks}"

    def test_split_for_thread_multiple_urls(self):
        """Test splitting with multiple URLs preserves all of them."""
        processor = ContentProcessor()
        url1 = "https://example.com/page1"
        url2 = "https://example.com/page2"
        content = "A" * 200 + " " + url1 + " " + "B" * 200 + " " + url2

        chunks = processor.split_for_thread(content)

        all_text = " ".join(chunks)
        assert url1 in all_text, f"URL1 was broken: {chunks}"
        assert url2 in all_text, f"URL2 was broken: {chunks}"

    def test_find_url_ranges(self):
        """Test URL range detection."""
        processor = ContentProcessor()
        text = "Check https://example.com/path and https://foo.bar/baz here"

        ranges = processor._find_url_ranges(text)

        assert len(ranges) == 2
        assert text[ranges[0][0]:ranges[0][1]] == "https://example.com/path"
        assert text[ranges[1][0]:ranges[1][1]] == "https://foo.bar/baz"

    def test_is_inside_url(self):
        """Test position-inside-URL check."""
        processor = ContentProcessor()
        url_ranges = [(10, 40), (50, 70)]

        assert processor._is_inside_url(15, url_ranges) is True
        assert processor._is_inside_url(10, url_ranges) is True
        assert processor._is_inside_url(39, url_ranges) is True
        assert processor._is_inside_url(40, url_ranges) is False
        assert processor._is_inside_url(5, url_ranges) is False
        assert processor._is_inside_url(45, url_ranges) is False

    def test_encode_urls_for_x_japanese_url(self):
        """Test that Japanese characters in URLs are percent-encoded."""
        processor = ContentProcessor()
        content = "日記書いた https://diary.ebisuda.net/posts/2026-02-08-雪の日曜日/ おやすみ"

        result = processor.encode_urls_for_x(content)

        assert "雪の日曜日" not in result
        assert "https://diary.ebisuda.net/posts/2026-02-08-" in result
        assert "%E9%9B%AA%E3%81%AE%E6%97%A5%E6%9B%9C%E6%97%A5" in result
        # Non-URL text should remain unchanged
        assert result.startswith("日記書いた ")
        assert result.endswith(" おやすみ")

    def test_encode_urls_for_x_ascii_url_unchanged(self):
        """Test that ASCII-only URLs are not modified."""
        processor = ContentProcessor()
        content = "Check https://example.com/posts/hello-world/ here"

        result = processor.encode_urls_for_x(content)

        assert result == content

    def test_encode_urls_for_x_no_url(self):
        """Test that text without URLs is not modified."""
        processor = ContentProcessor()
        content = "日本語のテキストだけ。URLなし。"

        result = processor.encode_urls_for_x(content)

        assert result == content

    def test_encode_urls_for_x_multiple_urls(self):
        """Test encoding multiple URLs with mixed ASCII and non-ASCII."""
        processor = ContentProcessor()
        content = "記事1 https://example.com/日本語/ 記事2 https://example.com/english/"

        result = processor.encode_urls_for_x(content)

        assert "https://example.com/english/" in result
        assert "日本語" not in result.split("記事2")[0]  # First URL should be encoded