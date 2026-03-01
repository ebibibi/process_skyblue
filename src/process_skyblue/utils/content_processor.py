"""
Content Processor for Process SkyBlue.

Handles content transformation, truncation, and formatting
for different social media platforms.
"""
import re
from typing import List
from urllib.parse import urlsplit, urlunsplit, quote


class ContentProcessor:
    """Processes and transforms content for different platforms."""

    X_PREMIUM_MAX_LENGTH = 25000
    X_FREE_MAX_LENGTH = 280

    def __init__(self, x_premium: bool = True):
        """Initialize content processor."""
        self.x_max_length = self.X_PREMIUM_MAX_LENGTH if x_premium else self.X_FREE_MAX_LENGTH
        self.ellipsis = "..."

    def twitter_char_count(self, text: str) -> int:
        """
        Count characters using Twitter's counting method.
        CJK characters (Chinese, Japanese, Korean) are counted as 2 characters.

        Args:
            text: Text to count

        Returns:
            Twitter-weighted character count
        """
        count = 0
        for char in text:
            # CJK Unified Ideographs and other CJK ranges
            code = ord(char)
            if (0x2E80 <= code <= 0x9FFF or      # CJK Radicals, Ideographs, etc.
                0xAC00 <= code <= 0xD7AF or      # Hangul Syllables
                0xF900 <= code <= 0xFAFF or      # CJK Compatibility Ideographs
                0xFF00 <= code <= 0xFFEF or      # Halfwidth and Fullwidth Forms
                0x20000 <= code <= 0x2FA1F):     # CJK Extension B-F
                count += 2
            else:
                count += 1
        return count

    def twitter_truncate(self, text: str, max_length: int) -> str:
        """
        Truncate text to fit Twitter's character limit.

        Args:
            text: Text to truncate
            max_length: Maximum Twitter-weighted length

        Returns:
            Truncated text
        """
        if self.twitter_char_count(text) <= max_length:
            return text

        result = ""
        current_count = 0
        for char in text:
            code = ord(char)
            char_weight = 2 if (0x2E80 <= code <= 0x9FFF or
                               0xAC00 <= code <= 0xD7AF or
                               0xF900 <= code <= 0xFAFF or
                               0xFF00 <= code <= 0xFFEF or
                               0x20000 <= code <= 0x2FA1F) else 1

            if current_count + char_weight > max_length:
                break
            result += char
            current_count += char_weight

        return result
    
    def truncate_for_x(self, content: str, respect_word_boundary: bool = False) -> str:
        """
        Truncate content for X (Twitter) character limit.
        
        Args:
            content: Content to truncate
            respect_word_boundary: If True, try to break at word boundaries
            
        Returns:
            Truncated content with ellipsis if needed
        """
        if len(content) <= self.x_max_length:
            return content
        
        if respect_word_boundary:
            # Try to find a good breaking point
            max_content_length = self.x_max_length - len(self.ellipsis)
            
            # Find the last space before the limit
            truncate_point = max_content_length
            for i in range(max_content_length, max(0, max_content_length - 50), -1):
                if content[i] == ' ':
                    truncate_point = i
                    break
            
            return content[:truncate_point].rstrip() + self.ellipsis
        else:
            # Simple truncation
            max_content_length = self.x_max_length - len(self.ellipsis)
            return content[:max_content_length] + self.ellipsis
    
    def clean_content(self, content: str) -> str:
        """
        Clean content by removing extra whitespace and normalizing.
        
        Args:
            content: Content to clean
            
        Returns:
            Cleaned content
        """
        # Remove extra whitespace and normalize
        cleaned = re.sub(r'\s+', ' ', content.strip())
        return cleaned
    
    def process_for_x(self, content: str) -> str:
        """
        Complete processing pipeline for X posting.
        
        Args:
            content: Original content
            
        Returns:
            Processed content ready for X
        """
        # Clean first, then truncate
        cleaned = self.clean_content(content)
        return self.truncate_for_x(cleaned, respect_word_boundary=True)
    
    def extract_mentions(self, content: str) -> List[str]:
        """
        Extract @mentions from content.
        
        Args:
            content: Content to analyze
            
        Returns:
            List of mentions found
        """
        mention_pattern = r'@\w+'
        return re.findall(mention_pattern, content)
    
    def extract_hashtags(self, content: str) -> List[str]:
        """
        Extract #hashtags from content.
        
        Args:
            content: Content to analyze
            
        Returns:
            List of hashtags found
        """
        hashtag_pattern = r'#\w+'
        return re.findall(hashtag_pattern, content)
    
    def count_characters(self, content: str) -> int:
        """
        Count characters in content (Unicode-aware).
        
        Args:
            content: Content to count
            
        Returns:
            Character count
        """
        return len(content)
    
    def has_media_urls(self, content: str) -> bool:
        """
        Check if content contains media URLs.
        
        Args:
            content: Content to check
            
        Returns:
            True if media URLs found
        """
        url_pattern = r'https?://(?:[-\w.])+(?:\.[a-zA-Z]{2,})+(?:/[^?\s]*)?(?:\?[^#\s]*)?(?:#[^\s]*)?'
        urls = re.findall(url_pattern, content)
        
        # Check for common media domains
        media_domains = [
            'youtube.com', 'youtu.be', 'vimeo.com', 'twitch.tv',
            'instagram.com', 'imgur.com', 'giphy.com'
        ]
        
        for url in urls:
            if any(domain in url for domain in media_domains):
                return True

        return False

    def encode_urls_for_x(self, content: str) -> str:
        """
        Encode non-ASCII characters in URLs so X/Twitter can parse them correctly.

        X's URL parser stops at non-ASCII characters (e.g. Japanese), causing
        partial URL linking. This method percent-encodes the path and query
        portions of URLs while preserving the rest of the text.

        Args:
            content: Text that may contain URLs with non-ASCII characters

        Returns:
            Text with URLs encoded for X compatibility
        """
        def encode_url(match):
            url = match.group(0)
            # Only encode if URL contains non-ASCII characters
            if all(ord(c) < 128 for c in url):
                return url
            parts = urlsplit(url)
            encoded = urlunsplit((
                parts.scheme,
                parts.netloc,
                quote(parts.path, safe='/:@!$&\'()*+,;=-._~'),
                quote(parts.query, safe='/:@!$&\'()*+,;=-._~'),
                quote(parts.fragment, safe='/:@!$&\'()*+,;=-._~'),
            ))
            return encoded

        return re.sub(r'https?://[^\s]+', encode_url, content)

    def split_for_thread(self, content: str, max_twitter_length: int = 270) -> List[str]:
        """
        Split long content into multiple chunks for thread posting.
        Uses Twitter's character counting (CJK = 2 chars).

        Args:
            content: Content to split
            max_twitter_length: Maximum Twitter-weighted length per chunk (default 270)

        Returns:
            List of content chunks
        """
        content = self.clean_content(content)

        # If content fits in one tweet, return as-is
        if self.twitter_char_count(content) <= self.x_max_length:
            return [content]

        chunks = []
        remaining = content

        while remaining:
            if self.twitter_char_count(remaining) <= max_twitter_length:
                # Last chunk
                chunks.append(remaining)
                break

            # Find a good split point using Twitter character counting
            split_point = self._find_split_point_twitter(remaining, max_twitter_length)
            chunk = remaining[:split_point].rstrip()
            chunks.append(chunk)
            remaining = remaining[split_point:].lstrip()

        return chunks

    def _find_split_point(self, text: str, max_length: int) -> int:
        """
        Find the best point to split text.

        Prioritizes (in order):
        1. End of sentence (。.!?）)
        2. Japanese comma (、)
        3. Regular comma or semicolon
        4. Space (word boundary)
        5. Hard cut at max_length

        Args:
            text: Text to find split point in
            max_length: Maximum length to search within

        Returns:
            Index to split at
        """
        if len(text) <= max_length:
            return len(text)

        # Search for split points within the allowed range
        search_range = text[:max_length]

        # Priority 1: End of sentence
        sentence_endings = ['。', '．', '！', '？', ')', '）', '.', '!', '?']
        best_sentence_end = -1
        for ending in sentence_endings:
            pos = search_range.rfind(ending)
            if pos > best_sentence_end and pos > max_length * 0.5:  # At least 50% of max
                best_sentence_end = pos

        if best_sentence_end > 0:
            return best_sentence_end + 1

        # Priority 2: Japanese comma
        jp_comma = search_range.rfind('、')
        if jp_comma > max_length * 0.5:
            return jp_comma + 1

        # Priority 3: Regular comma or semicolon
        for punct in [',', ';', '：', ':']:
            pos = search_range.rfind(punct)
            if pos > max_length * 0.5:
                return pos + 1

        # Priority 4: Space (word boundary)
        space_pos = search_range.rfind(' ')
        if space_pos > max_length * 0.5:
            return space_pos + 1

        # Priority 5: Hard cut
        return max_length

    def needs_splitting(self, content: str) -> bool:
        """
        Check if content needs to be split into multiple tweets.
        Uses Twitter's character counting (CJK = 2 chars).

        Args:
            content: Content to check

        Returns:
            True if content exceeds X character limit
        """
        return self.twitter_char_count(self.clean_content(content)) > self.x_max_length

    def _find_url_ranges(self, text: str) -> list:
        """
        Find all URL positions in text.

        Args:
            text: Text to search for URLs

        Returns:
            List of (start, end) tuples for each URL
        """
        url_pattern = r'https?://[^\s]+'
        return [(m.start(), m.end()) for m in re.finditer(url_pattern, text)]

    def _is_inside_url(self, pos: int, url_ranges: list) -> bool:
        """
        Check if a position falls inside any URL.

        Args:
            pos: Position to check
            url_ranges: List of (start, end) tuples

        Returns:
            True if position is inside a URL
        """
        for start, end in url_ranges:
            if start <= pos < end:
                return True
        return False

    def _find_split_point_twitter(self, text: str, max_twitter_length: int) -> int:
        """
        Find the best point to split text using Twitter character counting.
        Never splits inside a URL.

        Args:
            text: Text to find split point in
            max_twitter_length: Maximum Twitter-weighted length

        Returns:
            Index to split at (Python string index, not Twitter count)
        """
        # First, find the maximum Python index that fits within Twitter limit
        current_count = 0
        max_index = 0
        for i, char in enumerate(text):
            code = ord(char)
            char_weight = 2 if (0x2E80 <= code <= 0x9FFF or
                               0xAC00 <= code <= 0xD7AF or
                               0xF900 <= code <= 0xFAFF or
                               0xFF00 <= code <= 0xFFEF or
                               0x20000 <= code <= 0x2FA1F) else 1

            if current_count + char_weight > max_twitter_length:
                max_index = i
                break
            current_count += char_weight
            max_index = i + 1

        if max_index == 0:
            max_index = 1  # At least one character

        # Find URL ranges to avoid splitting inside them
        url_ranges = self._find_url_ranges(text)

        # If max_index falls inside a URL, move it before the URL
        for start, end in url_ranges:
            if start < max_index < end:
                max_index = start
                break

        if max_index == 0:
            max_index = 1

        # Now find a good split point within the allowed range
        search_range = text[:max_index]
        min_index = max(1, max_index // 2)  # At least 50% of max

        # Priority 1: End of sentence
        sentence_endings = ['。', '．', '！', '？', ')', '）', '.', '!', '?']
        best_sentence_end = -1
        for ending in sentence_endings:
            pos = search_range.rfind(ending)
            if pos > best_sentence_end and pos >= min_index and not self._is_inside_url(pos, url_ranges):
                best_sentence_end = pos

        if best_sentence_end > 0:
            return best_sentence_end + 1

        # Priority 2: Japanese comma
        jp_comma = search_range.rfind('、')
        if jp_comma >= min_index and not self._is_inside_url(jp_comma, url_ranges):
            return jp_comma + 1

        # Priority 3: Regular comma or semicolon
        for punct in [',', ';', '：', ':']:
            pos = search_range.rfind(punct)
            if pos >= min_index and not self._is_inside_url(pos, url_ranges):
                return pos + 1

        # Priority 4: Space (word boundary)
        space_pos = search_range.rfind(' ')
        if space_pos >= min_index and not self._is_inside_url(space_pos, url_ranges):
            return space_pos + 1

        # Priority 5: Use max_index (hard cut at limit, but not inside URL)
        return max_index