"""
X (Twitter) Output Service for Process SkyBlue.

Handles posting content to X using the Twitter API.
"""
import tempfile
import requests
import logging
from typing import Dict, Any, Optional, List
from process_skyblue.services.base_output_service import BaseOutputService

# Enable tweepy debug logging
logging.basicConfig(level=logging.INFO)
tweepy_logger = logging.getLogger('tweepy')
tweepy_logger.setLevel(logging.DEBUG)

try:
    import tweepy
except ImportError:
    # For testing when tweepy is not available
    tweepy = None


class XOutputService(BaseOutputService):
    """Output service for X (Twitter)."""
    
    X_PREMIUM_MAX_LENGTH = 25000
    X_FREE_MAX_LENGTH = 280

    def __init__(self, api_key: str, api_secret: str, access_token: str, access_token_secret: str,
                 oauth2_client_id: str = None, oauth2_client_secret: str = None,
                 x_premium: bool = True):
        """
        Initialize X service.
        
        Args:
            api_key: X API key
            api_secret: X API secret
            access_token: X access token
            access_token_secret: X access token secret
            oauth2_client_id: X OAuth 2.0 client ID (optional)
            oauth2_client_secret: X OAuth 2.0 client secret (optional)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.oauth2_client_id = oauth2_client_id
        self.oauth2_client_secret = oauth2_client_secret
        self.client = None
        self.connected = False
        self.max_length = self.X_PREMIUM_MAX_LENGTH if x_premium else self.X_FREE_MAX_LENGTH
        self._username = "ebi"  # Hardcoded to avoid API calls
    
    def connect(self) -> bool:
        """
        Connect to X API using v2 endpoints.
        
        Returns:
            True if connection successful
        """
        if tweepy is None:
            print("⚠️  tweepy library not available, using mock mode")
            self.connected = True
            return True
        
        try:
            # Use tweepy v4+ Client for v2 API with OAuth 1.0a authentication
            print("🔄 Creating X API client...")
            
            # Custom response handler to see rate limit info
            class RateLimitHandler:
                @staticmethod
                def on_response(response):
                    if response.headers:
                        print("📊 Response Headers:")
                        for key, value in response.headers.items():
                            if 'rate' in key.lower() or 'limit' in key.lower():
                                print(f"   {key}: {value}")
                    return response
            
            self.client = tweepy.Client(
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
                wait_on_rate_limit=True
            )
            
            # Skip connection test to avoid unnecessary API calls
            print("✅ X API client created (connection test skipped)")
            self.connected = True
            return True
            
        except Exception as e:
            print(f"❌ Failed to connect to X API v2: {str(e)}")
            self.connected = False
            return False
    
    def _download_images(self, image_urls: List[str]) -> List[str]:
        """
        Download images from URLs to temporary files.
        
        Args:
            image_urls: List of image URLs to download
            
        Returns:
            List of local file paths
        """
        local_paths = []
        for url in image_urls:
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                
                # Create temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                    tmp_file.write(response.content)
                    local_paths.append(tmp_file.name)
                    
            except Exception as e:
                print(f"⚠️  Failed to download image {url}: {str(e)}")
                
        return local_paths
    
    def _upload_media_v1(self, file_path: str) -> Optional[str]:
        """
        Upload media using v1.1 API (required for media upload).
        
        Args:
            file_path: Path to the media file
            
        Returns:
            Media ID string or None if failed
        """
        try:
            # Create v1.1 API client for media upload
            auth = tweepy.OAuthHandler(self.api_key, self.api_secret)
            auth.set_access_token(self.access_token, self.access_token_secret)
            api_v1 = tweepy.API(auth, wait_on_rate_limit=True)  # Let tweepy handle rate limits
            
            # Upload media
            media = api_v1.media_upload(file_path)
            return str(media.media_id)
            
        except Exception as e:
            print(f"⚠️  Failed to upload media: {str(e)}")
            return None
    
    def post_content(self, content: str, metadata: Optional[Dict[str, Any]] = None,
                     reply_to_tweet_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Post content to X with optional images and reply-to support.

        Args:
            content: Content to post
            metadata: Optional metadata including images
            reply_to_tweet_id: Optional tweet ID to reply to (for threading)

        Returns:
            Result dictionary with success status and post ID
        """
        if not self.connected:
            return {"success": False, "error": "Not connected to X API"}

        if not self.validate_content(content):
            return {"success": False, "error": "Invalid content"}
        
        try:
            if self.client is None:
                # Mock mode for testing
                print(f"📱 Mock X post: {content[:50]}...")
                return {
                    "success": True,
                    "id": "mock_tweet_123",
                    "url": "https://x.com/user/status/mock_tweet_123"
                }
            
            # Check for images in metadata
            media_ids = []
            if metadata and 'images' in metadata:
                image_urls = [img['url'] for img in metadata['images'] if 'url' in img]
                if image_urls:
                    print(f"📸 Processing {len(image_urls)} image(s)...")
                    
                    # Download images
                    local_paths = self._download_images(image_urls[:4])  # X API v2 supports max 4 images
                    
                    # Upload each image and collect media IDs
                    for path in local_paths:
                        media_id = self._upload_media_v1(path)
                        if media_id:
                            media_ids.append(media_id)
                        
                        # Clean up temporary file
                        try:
                            import os
                            os.unlink(path)
                        except:
                            pass
            
            # Post to X using v2 API
            print(f"📤 Posting tweet: {content[:100]}{'...' if len(content) > 100 else ''}")
            
            # Try to catch rate limit before tweepy handles it
            import time
            start_time = time.time()
            
            try:
                # Build tweet parameters
                tweet_params = {"text": content}

                if media_ids:
                    print(f"📎 Attaching {len(media_ids)} media file(s)")
                    tweet_params["media_ids"] = media_ids

                if reply_to_tweet_id:
                    print(f"↩️ Replying to tweet ID: {reply_to_tweet_id}")
                    tweet_params["in_reply_to_tweet_id"] = reply_to_tweet_id

                response = self.client.create_tweet(**tweet_params)
                
                print(f"✅ X API Response: {response}")
                tweet_id = response.data['id']
                
                print(f"🎯 Successfully posted tweet ID: {tweet_id}")
                
                return {
                    "success": True,
                    "id": tweet_id,
                    "url": f"https://x.com/{self._username}/status/{tweet_id}"
                }
            except Exception as api_error:
                error_str = str(api_error)
                print(f"🔍 X API Error Details:")
                print(f"   Error Type: {type(api_error).__name__}")
                print(f"   Error Message: {error_str}")
                if hasattr(api_error, 'response'):
                    print(f"   Response Status: {getattr(api_error.response, 'status_code', 'N/A')}")
                    print(f"   Response Headers: {getattr(api_error.response, 'headers', {})}")
                    print(f"   Response Content: {getattr(api_error.response, 'text', 'N/A')}")

                # Check for duplicate content error
                if "You are not allowed to create a Tweet with duplicate content" in error_str:
                    print("⚠️  Duplicate content detected - skipping this post")
                    return {
                        "success": True,  # Return success to continue processing
                        "skipped": True,
                        "reason": "duplicate_content",
                        "id": None,
                        "url": None
                    }

                raise api_error
            
        except Exception as e:
            error_msg = f"Failed to post to X: {str(e)}"
            print(f"❌ {error_msg}")
            return {"success": False, "error": error_msg}
    
    def post_thread(self, contents: List[str], metadata: Optional[Dict[str, Any]] = None,
                    reply_to_tweet_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Post a thread (multiple tweets in sequence).

        Args:
            contents: List of content strings to post as a thread
            metadata: Optional metadata (images only applied to first tweet)
            reply_to_tweet_id: Optional tweet ID to reply to (makes this a reply thread)

        Returns:
            Result dictionary with success status, list of tweet IDs, and last tweet ID
        """
        if not contents:
            return {"success": False, "error": "No content to post"}

        tweet_ids = []
        last_tweet_id = reply_to_tweet_id

        for i, content in enumerate(contents):
            # Only attach images to the first tweet
            post_metadata = metadata if i == 0 else None

            result = self.post_content(
                content=content,
                metadata=post_metadata,
                reply_to_tweet_id=last_tweet_id
            )

            if not result.get('success'):
                return {
                    "success": False,
                    "error": f"Failed to post tweet {i+1}/{len(contents)}: {result.get('error')}",
                    "partial_tweet_ids": tweet_ids,
                    "last_successful_tweet_id": last_tweet_id
                }

            tweet_id = result.get('id')
            if tweet_id:
                tweet_ids.append(tweet_id)
                last_tweet_id = tweet_id

            print(f"🧵 Posted thread part {i+1}/{len(contents)}: {tweet_id}")

        return {
            "success": True,
            "tweet_ids": tweet_ids,
            "first_tweet_id": tweet_ids[0] if tweet_ids else None,
            "last_tweet_id": last_tweet_id,
            "url": f"https://x.com/{self._username}/status/{tweet_ids[0]}" if tweet_ids else None
        }

    def disconnect(self) -> None:
        """Disconnect from X API."""
        self.connected = False
        self.client = None
    
    def validate_content(self, content: str) -> bool:
        """
        Validate content for X posting.
        
        Args:
            content: Content to validate
            
        Returns:
            True if content is valid
        """
        if not content or not content.strip():
            return False
        
        if len(content) > self.max_length:
            return False
        
        return True
    
    def get_character_limit(self) -> int:
        """
        Get character limit for X.
        
        Returns:
            Character limit
        """
        return self.max_length
    
