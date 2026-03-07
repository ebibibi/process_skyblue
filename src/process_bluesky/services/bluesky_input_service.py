"""
Bluesky Input Service for Process BlueSky.

Handles connection to Bluesky AT Protocol and retrieval of posts.
"""
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from process_bluesky.services.base_input_service import BaseInputService

try:
    from atproto import Client
    import httpx
except ImportError:
    # For testing when atproto is not available
    Client = None
    httpx = None


class BlueskyServerError(Exception):
    """Bluesky API server-side error (5xx)."""
    pass


class BlueskyRateLimitError(Exception):
    """Bluesky API rate limit exceeded."""
    pass


class BlueskyAuthError(Exception):
    """Bluesky API authentication error."""
    pass


class BlueskyInputService(BaseInputService):
    """Input service for Bluesky AT Protocol."""
    
    def __init__(self, identifier: str, password: str):
        """
        Initialize Bluesky service.

        Args:
            identifier: Bluesky identifier (handle)
            password: Bluesky password
        """
        self.identifier = identifier
        self.password = password
        self.client = None
        self.connected = False
        self.target_author = "ebibibibibibi.bsky.social"
        self._max_retries = 3
        self._retry_delay = 2  # seconds
    
    def connect(self) -> bool:
        """
        Connect to Bluesky AT Protocol.

        Returns:
            True if connection successful
        """
        if Client is None:
            print("⚠️  atproto library not available, using mock mode")
            self.connected = True
            return True

        try:
            self.client = Client()
            # Increase timeout from default 5s to 30s for better stability
            if httpx is not None:
                self.client._request._client = httpx.Client(
                    timeout=httpx.Timeout(30.0, connect=10.0)
                )
            self.client.login(self.identifier, self.password)
            self.connected = True
            print("✅ Connected to Bluesky with 30s timeout")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to Bluesky: {str(e)}")
            self.connected = False
            return False

    def _reconnect(self) -> bool:
        """
        Attempt to reconnect to Bluesky.

        Returns:
            True if reconnection successful
        """
        print("🔄 Attempting to reconnect to Bluesky...")
        self.disconnect()
        return self.connect()
    
    def get_latest_posts(self, since_timestamp: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get latest posts from Bluesky with automatic retry on network errors.

        Args:
            since_timestamp: Get posts newer than this timestamp

        Returns:
            List of posts in standard format
        """
        if not self.connected:
            return []

        if self.client is None:
            # Mock data for testing
            return [{
                "id": "mock_post_1",
                "content": "Mock Bluesky post for testing",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "author": self.target_author,
                "metadata": {"source": "bluesky_mock"}
            }]

        last_error = None
        for attempt in range(self._max_retries):
            try:
                return self._fetch_posts(since_timestamp)
            except Exception as e:
                last_error = e
                error_str = str(e)
                error_type = type(e).__name__

                # Check if this is a network error that we should retry
                is_network_error = (
                    'NetworkError' in error_str or
                    'ConnectError' in error_str or
                    'TimeoutException' in error_str or
                    'ConnectionError' in error_type or
                    'Timeout' in error_type
                )

                # Check for server-side errors (5xx status codes)
                if 'status_code=502' in error_str or 'status_code=503' in error_str or 'status_code=504' in error_str:
                    error_type = "UpstreamFailure" if "UpstreamFailure" in error_str else "Server Error"
                    print(f"⚠️ Bluesky API サーバー側エラー ({error_type}) - リトライ {attempt + 1}/{self._max_retries}")
                    if attempt < self._max_retries - 1:
                        time.sleep(self._retry_delay * (attempt + 1))
                        continue
                    raise BlueskyServerError(f"Bluesky API server error: {error_type}") from e
                elif 'status_code=429' in error_str:
                    print(f"⚠️ Bluesky API レートリミット到達")
                    raise BlueskyRateLimitError("Bluesky API rate limit exceeded") from e
                elif 'status_code=401' in error_str or 'status_code=403' in error_str:
                    print(f"❌ Bluesky API 認証エラー")
                    raise BlueskyAuthError("Bluesky API authentication error") from e
                elif is_network_error:
                    print(f"⚠️ ネットワークエラー - リトライ {attempt + 1}/{self._max_retries}: {error_str[:100]}")
                    if attempt < self._max_retries - 1:
                        time.sleep(self._retry_delay * (attempt + 1))
                        # Try to reconnect on network errors
                        if attempt == 1:  # Reconnect on second retry
                            self._reconnect()
                        continue
                    error_detail = error_str if error_str else error_type
                    raise RuntimeError(f"Bluesky API error after {self._max_retries} retries: {error_detail}") from e
                else:
                    error_detail = error_str if error_str else error_type
                    print(f"❌ Error getting posts from Bluesky: {error_detail}")
                    raise RuntimeError(f"Bluesky API error: {error_detail}") from e

        # Should not reach here, but just in case
        if last_error:
            raise last_error
        return []

    def _fetch_posts(self, since_timestamp: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Internal method to fetch posts from Bluesky.

        Args:
            since_timestamp: Get posts newer than this timestamp

        Returns:
            List of posts in standard format
        """
        # Get author feed
        response = self.client.get_author_feed(
            actor=self.target_author,
            limit=50
        )

        posts = []
        seen_ids = set()
        for item in response.feed:
            # item is a FeedViewPost object, need to access .post attribute
            if hasattr(item, 'post') and self._is_own_post_from_feed_item(item) and self._is_newer_than_from_feed_item(item, since_timestamp):
                post_data = self._convert_to_standard_format_from_feed_item(item)
                if post_data['id'] not in seen_ids:
                    posts.append(post_data)
                    seen_ids.add(post_data['id'])

        # BlueSky's getAuthorFeed omits intermediate posts in multi-part threads
        # (e.g. in a 3-post thread A→B→C, only A and C appear in the feed).
        # For any post that belongs to a thread, fetch the full thread via
        # get_post_thread and add any missing posts that are newer than since_timestamp.
        thread_roots_to_fetch = set()
        for post in posts:
            root_uri = post.get('thread_root')
            if root_uri and root_uri not in seen_ids:
                thread_roots_to_fetch.add(root_uri)

        for root_uri in thread_roots_to_fetch:
            try:
                thread_response = self.client.get_post_thread(uri=root_uri)
                thread_posts = self._extract_thread_posts_flat(thread_response.thread, since_timestamp)
                for tp in thread_posts:
                    if tp['id'] not in seen_ids:
                        posts.append(tp)
                        seen_ids.add(tp['id'])
                        print(f"🔗 Supplemented missing thread post: {tp['id'].split('/')[-1]}")
            except Exception as e:
                print(f"⚠️ Failed to fetch thread for {root_uri}: {e}")

        return posts

    def _extract_thread_posts_flat(self, node: Any, since_timestamp: Optional[str]) -> List[Dict[str, Any]]:
        """
        Walk a post thread tree (depth-first) and return all self-authored posts
        that are newer than since_timestamp as a flat list.

        Thread nodes returned by get_post_thread already have a .post attribute
        with the same structure as FeedViewPost.post, so we can use the existing
        helper methods by wrapping the node in a simple object with a .post field.
        """
        results = []
        if node is None or not hasattr(node, 'post'):
            return results

        # Wrap node so _is_own_post_from_feed_item / _is_newer_than_from_feed_item work
        class _NodeWrapper:
            def __init__(self, post):
                self.post = post

        wrapper = _NodeWrapper(node.post)
        if self._is_own_post_from_feed_item(wrapper) and self._is_newer_than_from_feed_item(wrapper, since_timestamp):
            results.append(self._convert_to_standard_format_from_feed_item(wrapper))

        for reply in getattr(node, 'replies', None) or []:
            results.extend(self._extract_thread_posts_flat(reply, since_timestamp))

        return results
    
    def disconnect(self) -> None:
        """Disconnect from Bluesky."""
        self.connected = False
        self.client = None
    
    def _is_own_post(self, item: Dict[str, Any]) -> bool:
        """Check if post is from target author."""
        return (
            item.get("post", {}).get("author", {}).get("handle") == self.target_author
        )
    
    def _filter_own_posts(self, posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter posts to only include own posts."""
        return [post for post in posts if post.get("author", {}).get("handle") == self.target_author]
    
    def _is_own_post_from_feed_item(self, item: Any) -> bool:
        """Check if post is from target author (for actual API objects)."""
        try:
            return item.post.author.handle == self.target_author
        except AttributeError:
            return False
    
    def _is_newer_than_from_feed_item(self, item: Any, since_timestamp: Optional[str]) -> bool:
        """Check if post is newer than given timestamp (for actual API objects)."""
        if since_timestamp is None:
            return True
        
        try:
            post_time = item.post.record.created_at
            post_dt = datetime.fromisoformat(post_time.replace('Z', '+00:00'))
            since_dt = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
            return post_dt > since_dt
        except (AttributeError, ValueError):
            return False
    
    def _resolve_facet_links(self, record: Any) -> str:
        """
        Replace truncated URLs in text with full URLs from facets.

        BlueSky stores display text in record.text (which may have truncated URLs)
        and actual URLs in record.facets. This method reconstructs the text with
        full URLs.

        Args:
            record: BlueSky post record with text and optional facets

        Returns:
            Text with truncated URLs replaced by full URLs from facets
        """
        text = record.text
        facets = getattr(record, 'facets', None)
        if not facets or not isinstance(facets, (list, tuple)):
            return text

        # Collect link facets with byte offsets and full URIs
        link_replacements = []
        for facet in facets:
            if not hasattr(facet, 'features') or not hasattr(facet, 'index'):
                continue
            for feature in facet.features:
                # Check for link facet type
                feature_type = getattr(feature, 'py_type', '') or str(type(feature))
                if 'link' not in feature_type.lower():
                    continue
                uri = getattr(feature, 'uri', None)
                if not uri:
                    continue
                byte_start = getattr(facet.index, 'byte_start', None)
                byte_end = getattr(facet.index, 'byte_end', None)
                if byte_start is not None and byte_end is not None:
                    link_replacements.append((byte_start, byte_end, uri))

        if not link_replacements:
            return text

        # Sort by byte_start descending to replace from end (preserves earlier offsets)
        link_replacements.sort(key=lambda x: x[0], reverse=True)

        # BlueSky uses byte offsets on UTF-8 encoded text
        text_bytes = text.encode('utf-8')
        for byte_start, byte_end, uri in link_replacements:
            text_bytes = text_bytes[:byte_start] + uri.encode('utf-8') + text_bytes[byte_end:]

        return text_bytes.decode('utf-8')

    def _convert_to_standard_format_from_feed_item(self, item: Any) -> Dict[str, Any]:
        """Convert Bluesky feed item to standard format (for actual API objects)."""
        try:
            post_data = {
                "id": item.post.uri,
                "content": self._resolve_facet_links(item.post.record),
                "timestamp": item.post.record.created_at,
                "author": item.post.author.handle,
                "metadata": {
                    "source": "bluesky",
                    "cid": item.post.cid,
                    "reply_count": getattr(item.post, 'reply_count', 0),
                    "repost_count": getattr(item.post, 'repost_count', 0),
                    "like_count": getattr(item.post, 'like_count', 0)
                }
            }
            
            # Extract image URLs if present
            images = []
            if hasattr(item.post.record, 'embed') and item.post.record.embed:
                embed = item.post.record.embed
                
                # Check if it's an images embed - atproto_client.models.app.bsky.embed.images.Main
                if 'app.bsky.embed.images' in str(type(embed)):
                    if hasattr(embed, 'images'):
                        for img in embed.images:
                            # Get image reference
                            image_ref = None
                            if hasattr(img, 'image'):
                                if hasattr(img.image, 'ref'):
                                    image_ref = img.image.ref
                                elif hasattr(img.image, 'blob'):
                                    image_ref = img.image.blob
                                    
                            if image_ref:
                                # Get blob link
                                blob_link = None
                                if hasattr(image_ref, 'link'):
                                    blob_link = image_ref.link
                                elif hasattr(image_ref, '$link'):
                                    blob_link = getattr(image_ref, '$link')
                                    
                                if blob_link:
                                    # Extract DID from author
                                    did = getattr(item.post.author, 'did', 'did:plc:ghdr2kw5774wigtl2fo4mske')
                                    image_url = f"https://cdn.bsky.app/img/feed_fullsize/plain/{did}/{blob_link}@jpeg"
                                    images.append({
                                        'url': image_url,
                                        'alt': getattr(img, 'alt', '')
                                    })
            
            if images:
                post_data['images'] = images

            # Extract reply/thread information
            if hasattr(item.post.record, 'reply') and item.post.record.reply:
                reply = item.post.record.reply
                # Get parent post URI (the post this is replying to)
                if hasattr(reply, 'parent') and reply.parent:
                    parent_uri = getattr(reply.parent, 'uri', None)
                    if parent_uri:
                        post_data['reply_to'] = parent_uri
                # Get root post URI (the first post in the thread)
                if hasattr(reply, 'root') and reply.root:
                    root_uri = getattr(reply.root, 'uri', None)
                    if root_uri:
                        post_data['thread_root'] = root_uri

            return post_data
            
        except AttributeError as e:
            # Fallback for unexpected structure
            return {
                "id": f"unknown_{datetime.now().timestamp()}",
                "content": str(item),
                "timestamp": datetime.now().isoformat() + "Z",
                "author": self.target_author,
                "metadata": {"source": "bluesky", "error": str(e)}
            }
    
    def _is_newer_than(self, item: Dict[str, Any], since_timestamp: Optional[str]) -> bool:
        """Check if post is newer than given timestamp."""
        if since_timestamp is None:
            return True
        
        post_time = item.get("post", {}).get("record", {}).get("createdAt")
        if not post_time:
            return False
        
        post_dt = datetime.fromisoformat(post_time.replace('Z', '+00:00'))
        since_dt = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
        
        return post_dt > since_dt
    
    def _convert_to_standard_format(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Bluesky post to standard format."""
        post = item.get("post", {})
        record = post.get("record", {})
        author = post.get("author", {})
        
        return {
            "id": post.get("uri", ""),
            "content": record.get("text", ""),
            "timestamp": record.get("createdAt", ""),
            "author": author.get("handle", ""),
            "metadata": {
                "source": "bluesky",
                "cid": post.get("cid", ""),
                "reply_count": post.get("replyCount", 0),
                "repost_count": post.get("repostCount", 0),
                "like_count": post.get("likeCount", 0)
            }
        }