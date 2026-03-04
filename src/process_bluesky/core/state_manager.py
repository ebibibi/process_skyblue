"""
State Manager for Process SkyBlue.

Manages application state including last processed timestamp
and check times with persistent JSON storage.
"""
import json
import os
from datetime import datetime, timezone
from typing import Optional


class StateManager:
    """Manages application state persistence."""

    ALL_DESTINATIONS = ["x", "discord_log"]

    def __init__(self, state_file_path: str = "data/state.json"):
        """
        Initialize state manager.

        Args:
            state_file_path: Path to state file
        """
        self.state_file_path = state_file_path
        self.last_processed_at: Optional[str] = None
        self.last_check: Optional[str] = None
        self.processed_posts_cache: list = []  # Recent processed post IDs
        self.failed_posts: dict = {}  # Failed posts with retry counts: {post_id: {"count": N, "timestamp": str, "last_error": str}}
        self.permanently_failed_posts: list = []  # Posts that exceeded max retries
        self.post_id_mapping: dict = {}  # Bluesky post ID -> Twitter tweet ID mapping for threading
        self.completed_destinations: dict = {}  # {post_id: ["x", "discord_log"]}
        self.discord_log_failed_posts: dict = {}  # Same structure as failed_posts
        self.discord_log_permanently_failed_posts: list = []  # Same structure as permanently_failed_posts
        self.max_cache_size = 1000  # Keep last 1000 post IDs
        self.max_retry_count = 3  # Max retries before marking as permanently failed
        self._load_state()
    
    def _load_state(self) -> None:
        """Load state from file or create default state."""
        if os.path.exists(self.state_file_path):
            try:
                with open(self.state_file_path, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    self.last_processed_at = state_data.get('last_processed_at')
                    self.last_check = state_data.get('last_check')
                    self.processed_posts_cache = state_data.get('processed_posts_cache', [])
                    self.failed_posts = state_data.get('failed_posts', {})
                    self.permanently_failed_posts = state_data.get('permanently_failed_posts', [])
                    self.post_id_mapping = state_data.get('post_id_mapping', {})
                    self.completed_destinations = state_data.get('completed_destinations', {})
                    self.discord_log_failed_posts = state_data.get('discord_log_failed_posts', {})
                    self.discord_log_permanently_failed_posts = state_data.get(
                        'discord_log_permanently_failed_posts', []
                    )

                    # Backward compatibility: posts in processed_posts_cache
                    # but not in completed_destinations are treated as all-destinations-completed
                    for post_id in self.processed_posts_cache:
                        if post_id not in self.completed_destinations:
                            self.completed_destinations[post_id] = list(self.ALL_DESTINATIONS)
            except (json.JSONDecodeError, IOError):
                # If file is corrupted, create default state
                self._create_default_state()
        else:
            self._create_default_state()
    
    def _create_default_state(self) -> None:
        """Create default state with timestamp from 24 hours ago to catch recent posts."""
        from datetime import timedelta
        
        # Set initial timestamp to 24 hours ago to catch recent posts
        initial_time = datetime.now(timezone.utc) - timedelta(hours=24)
        initial_time_str = initial_time.isoformat().replace('+00:00', 'Z')
        
        current_time = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        self.last_processed_at = initial_time_str
        self.last_check = current_time
        self._save_state()
    
    def _save_state(self) -> None:
        """Save current state to file."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.state_file_path), exist_ok=True)

        # Keep cache size limited
        if len(self.processed_posts_cache) > self.max_cache_size:
            self.processed_posts_cache = self.processed_posts_cache[-self.max_cache_size:]

        # Keep post_id_mapping size limited (keep last 500 mappings)
        if len(self.post_id_mapping) > 500:
            # Remove oldest entries (assuming dict maintains insertion order in Python 3.7+)
            keys_to_remove = list(self.post_id_mapping.keys())[:-500]
            for key in keys_to_remove:
                del self.post_id_mapping[key]

        # Trim completed_destinations to match cache size
        if len(self.completed_destinations) > self.max_cache_size:
            keys_to_keep = set(self.processed_posts_cache[-self.max_cache_size:])
            self.completed_destinations = {
                k: v for k, v in self.completed_destinations.items() if k in keys_to_keep
            }

        state_data = {
            'last_processed_at': self.last_processed_at,
            'last_check': self.last_check,
            'processed_posts_cache': self.processed_posts_cache,
            'failed_posts': self.failed_posts,
            'permanently_failed_posts': self.permanently_failed_posts,
            'post_id_mapping': self.post_id_mapping,
            'completed_destinations': self.completed_destinations,
            'discord_log_failed_posts': self.discord_log_failed_posts,
            'discord_log_permanently_failed_posts': self.discord_log_permanently_failed_posts,
        }

        with open(self.state_file_path, 'w', encoding='utf-8') as f:
            json.dump(state_data, f, indent=2)
    
    def update_last_processed_at(self, timestamp: str) -> None:
        """
        Update last processed timestamp.
        
        Args:
            timestamp: ISO format timestamp string
        """
        self.last_processed_at = timestamp
        self._save_state()
    
    def update_last_check(self, timestamp: Optional[str] = None) -> None:
        """
        Update last check timestamp.
        
        Args:
            timestamp: ISO format timestamp string, current time if None
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        self.last_check = timestamp
        self._save_state()
    
    def get_last_processed_datetime(self) -> Optional[datetime]:
        """
        Get last processed timestamp as datetime object.
        
        Returns:
            datetime object or None if not set
        """
        if self.last_processed_at:
            # Handle both old malformed format and new correct format
            timestamp = self.last_processed_at
            # Fix malformed timestamps with double .000Z
            if '.000Z' in timestamp:
                timestamp = timestamp.replace('.000Z', '+00:00')
            elif 'Z' in timestamp:
                timestamp = timestamp.replace('Z', '+00:00')
            return datetime.fromisoformat(timestamp)
        return None
    
    def get_last_check_datetime(self) -> Optional[datetime]:
        """
        Get last check timestamp as datetime object.
        
        Returns:
            datetime object or None if not set
        """
        if self.last_check:
            # Handle both old malformed format and new correct format
            timestamp = self.last_check
            # Fix malformed timestamps with double .000Z
            if '.000Z' in timestamp:
                timestamp = timestamp.replace('.000Z', '+00:00')
            elif 'Z' in timestamp:
                timestamp = timestamp.replace('Z', '+00:00')
            return datetime.fromisoformat(timestamp)
        return None
    
    def is_newer_than_last_processed(self, timestamp: str) -> bool:
        """
        Check if timestamp is newer than last processed.
        
        Args:
            timestamp: ISO format timestamp string to check
            
        Returns:
            True if timestamp is newer than last processed
        """
        if not self.last_processed_at:
            return True
        
        last_processed_dt = self.get_last_processed_datetime()
        
        # Fix timestamp format for comparison
        check_timestamp = timestamp
        if '.000Z' in check_timestamp:
            check_timestamp = check_timestamp.replace('.000Z', '+00:00')
        elif 'Z' in check_timestamp:
            check_timestamp = check_timestamp.replace('Z', '+00:00')
        
        check_dt = datetime.fromisoformat(check_timestamp)
        
        return check_dt > last_processed_dt
    
    def add_processed_post(self, post_id: str, timestamp: str) -> None:
        """
        Add a post ID to the processed cache and update timestamp.
        
        Args:
            post_id: The ID of the processed post
            timestamp: The timestamp of the processed post
        """
        if post_id not in self.processed_posts_cache:
            self.processed_posts_cache.append(post_id)
        self.update_last_processed_at(timestamp)
    
    def is_post_processed(self, post_id: str) -> bool:
        """
        Check if a post has already been processed.

        Args:
            post_id: The ID of the post to check

        Returns:
            True if the post has been processed
        """
        return post_id in self.processed_posts_cache

    def add_failed_post(self, post_id: str, timestamp: str, error: str) -> bool:
        """
        Add or update a failed post with retry count.

        Args:
            post_id: The ID of the failed post
            timestamp: The timestamp of the post
            error: The error message

        Returns:
            True if post exceeded max retries and was moved to permanently_failed
        """
        if post_id in self.failed_posts:
            self.failed_posts[post_id]["count"] += 1
            self.failed_posts[post_id]["last_error"] = error
        else:
            self.failed_posts[post_id] = {
                "count": 1,
                "timestamp": timestamp,
                "last_error": error
            }

        # Check if exceeded max retries
        if self.failed_posts[post_id]["count"] >= self.max_retry_count:
            # Move to permanently failed
            self.permanently_failed_posts.append({
                "post_id": post_id,
                "timestamp": timestamp,
                "last_error": error,
                "failed_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            })
            del self.failed_posts[post_id]
            self._save_state()
            return True

        self._save_state()
        return False

    def is_post_failed(self, post_id: str) -> bool:
        """
        Check if a post is in the failed queue.

        Args:
            post_id: The ID of the post to check

        Returns:
            True if the post is in failed queue
        """
        return post_id in self.failed_posts

    def is_post_permanently_failed(self, post_id: str) -> bool:
        """
        Check if a post has permanently failed.

        Args:
            post_id: The ID of the post to check

        Returns:
            True if the post is permanently failed
        """
        return any(p["post_id"] == post_id for p in self.permanently_failed_posts)

    def get_failed_post_count(self, post_id: str) -> int:
        """
        Get the retry count for a failed post.

        Args:
            post_id: The ID of the post

        Returns:
            The retry count, or 0 if not in failed queue
        """
        if post_id in self.failed_posts:
            return self.failed_posts[post_id]["count"]
        return 0

    def remove_from_failed(self, post_id: str) -> None:
        """
        Remove a post from the failed queue (e.g., when retry succeeds).

        Args:
            post_id: The ID of the post to remove
        """
        if post_id in self.failed_posts:
            del self.failed_posts[post_id]
            self._save_state()

    def get_posts_to_retry(self) -> list:
        """
        Get list of posts that should be retried.

        Returns:
            List of post IDs that are in failed queue and should be retried
        """
        return list(self.failed_posts.keys())

    def add_post_mapping(self, bluesky_post_id: str, twitter_tweet_id: str) -> None:
        """
        Add a mapping from Bluesky post ID to Twitter tweet ID.

        Args:
            bluesky_post_id: The Bluesky post URI
            twitter_tweet_id: The corresponding Twitter tweet ID
        """
        self.post_id_mapping[bluesky_post_id] = twitter_tweet_id
        self._save_state()

    def get_twitter_id_for_bluesky_post(self, bluesky_post_id: str) -> Optional[str]:
        """
        Get the Twitter tweet ID for a given Bluesky post ID.

        Args:
            bluesky_post_id: The Bluesky post URI to look up

        Returns:
            The Twitter tweet ID if found, None otherwise
        """
        return self.post_id_mapping.get(bluesky_post_id)

    def add_post_mapping_with_last_tweet(
        self, bluesky_post_id: str, first_tweet_id: str, last_tweet_id: str
    ) -> None:
        """
        Add a mapping from Bluesky post ID to Twitter tweet IDs.
        Stores both first and last tweet ID for thread continuation.

        Args:
            bluesky_post_id: The Bluesky post URI
            first_tweet_id: The first tweet ID in the thread
            last_tweet_id: The last tweet ID (for reply continuation)
        """
        self.post_id_mapping[bluesky_post_id] = {
            "first": first_tweet_id,
            "last": last_tweet_id
        }
        self._save_state()

    def get_last_twitter_id_for_bluesky_post(self, bluesky_post_id: str) -> Optional[str]:
        """
        Get the last Twitter tweet ID for a given Bluesky post ID.
        Used for continuing threads.

        Args:
            bluesky_post_id: The Bluesky post URI to look up

        Returns:
            The last Twitter tweet ID if found, None otherwise
        """
        mapping = self.post_id_mapping.get(bluesky_post_id)
        if mapping is None:
            return None
        if isinstance(mapping, dict):
            return mapping.get("last")
        # Legacy format: just a single ID
        return mapping

    # --- Per-destination tracking methods ---

    def mark_destination_completed(self, post_id: str, destination: str) -> None:
        """Mark a destination as completed for a post."""
        if post_id not in self.completed_destinations:
            self.completed_destinations[post_id] = []
        if destination not in self.completed_destinations[post_id]:
            self.completed_destinations[post_id].append(destination)
        self._save_state()

    def is_destination_completed(self, post_id: str, destination: str) -> bool:
        """Check if a destination is completed for a post."""
        return destination in self.completed_destinations.get(post_id, [])

    def is_all_destinations_completed(self, post_id: str) -> bool:
        """Check if all destinations are completed for a post."""
        completed = self.completed_destinations.get(post_id, [])
        return all(d in completed for d in self.ALL_DESTINATIONS)

    def add_discord_log_failed_post(self, post_id: str, timestamp: str, error: str) -> bool:
        """
        Add or update a Discord ebilog failed post with retry count.

        Returns:
            True if post exceeded max retries and was moved to permanently_failed
        """
        if post_id in self.discord_log_failed_posts:
            self.discord_log_failed_posts[post_id]["count"] += 1
            self.discord_log_failed_posts[post_id]["last_error"] = error
        else:
            self.discord_log_failed_posts[post_id] = {
                "count": 1,
                "timestamp": timestamp,
                "last_error": error,
            }

        if self.discord_log_failed_posts[post_id]["count"] >= self.max_retry_count:
            self.discord_log_permanently_failed_posts.append({
                "post_id": post_id,
                "timestamp": timestamp,
                "last_error": error,
                "failed_at": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            })
            del self.discord_log_failed_posts[post_id]
            self._save_state()
            return True

        self._save_state()
        return False

    def is_discord_log_failed(self, post_id: str) -> bool:
        """Check if a post is in the Discord ebilog failed queue."""
        return post_id in self.discord_log_failed_posts

    def is_discord_log_permanently_failed(self, post_id: str) -> bool:
        """Check if a post has permanently failed for Discord ebilog."""
        return any(p["post_id"] == post_id for p in self.discord_log_permanently_failed_posts)

    def remove_from_discord_log_failed(self, post_id: str) -> None:
        """Remove a post from the Discord ebilog failed queue."""
        if post_id in self.discord_log_failed_posts:
            del self.discord_log_failed_posts[post_id]
            self._save_state()

    def get_discord_log_failed_count(self, post_id: str) -> int:
        """Get the retry count for a Discord ebilog failed post."""
        if post_id in self.discord_log_failed_posts:
            return self.discord_log_failed_posts[post_id]["count"]
        return 0