"""
Tests for StateManager per-destination tracking.
"""
import pytest
import json
import os
import tempfile
from process_bluesky.core.state_manager import StateManager


@pytest.fixture
def state_file():
    """Create a temporary state file with basic state."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        state = {
            "last_processed_at": "2025-07-13T09:00:00.000Z",
            "last_check": "2025-07-13T09:00:00.000Z",
            "processed_posts_cache": [],
            "failed_posts": {},
            "permanently_failed_posts": [],
            "post_id_mapping": {},
        }
        json.dump(state, f)
        temp_path = f.name
    yield temp_path
    os.unlink(temp_path)


@pytest.fixture
def state_file_with_legacy_posts():
    """State file with posts in processed_posts_cache but no completed_destinations."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        state = {
            "last_processed_at": "2025-07-13T09:00:00.000Z",
            "last_check": "2025-07-13T09:00:00.000Z",
            "processed_posts_cache": ["post_1", "post_2"],
            "failed_posts": {},
            "permanently_failed_posts": [],
            "post_id_mapping": {},
        }
        json.dump(state, f)
        temp_path = f.name
    yield temp_path
    os.unlink(temp_path)


class TestDestinationTracking:

    def test_mark_destination_completed(self, state_file):
        sm = StateManager(state_file)
        assert sm.is_destination_completed("post_a", "discord_log") is False
        sm.mark_destination_completed("post_a", "discord_log")
        assert sm.is_destination_completed("post_a", "discord_log") is True

    def test_is_all_destinations_completed(self, state_file):
        sm = StateManager(state_file)
        assert sm.is_all_destinations_completed("post_a") is False
        sm.mark_destination_completed("post_a", "discord_log")
        assert sm.is_all_destinations_completed("post_a") is True

    def test_discord_permanent_failure_is_terminal(self, state_file):
        """A permanent Discord failure must not be retried forever."""
        sm = StateManager(state_file)
        for attempt in range(sm.max_retry_count):
            sm.add_discord_log_failed_post(
                "post_a",
                "2025-07-13T10:00:00Z",
                f"Discord error {attempt + 1}",
            )

        assert sm.is_destination_terminal("post_a", "discord_log") is True
        assert sm.is_all_destinations_completed("post_a") is True
        sm.add_processed_post("post_a", "2025-07-13T10:00:00Z")

        reloaded = StateManager(state_file)
        assert reloaded.is_post_processed("post_a") is True
        assert reloaded.is_destination_terminal("post_a", "discord_log") is True

    def test_legacy_x_destination_does_not_block_completion(self, state_file):
        """State written before X removal lists an "x" destination — it must be ignored."""
        sm = StateManager(state_file)
        sm.completed_destinations["post_a"] = ["x"]
        assert sm.is_all_destinations_completed("post_a") is False
        sm.mark_destination_completed("post_a", "discord_log")
        assert sm.is_all_destinations_completed("post_a") is True

    def test_backward_compatibility_legacy_posts(self, state_file_with_legacy_posts):
        sm = StateManager(state_file_with_legacy_posts)
        # Legacy posts should be treated as all-destinations-completed
        assert sm.is_destination_completed("post_1", "discord_log") is True
        assert sm.is_all_destinations_completed("post_1") is True
        assert sm.is_all_destinations_completed("post_2") is True

    def test_new_post_not_in_completed(self, state_file):
        sm = StateManager(state_file)
        assert sm.is_destination_completed("new_post", "discord_log") is False
        assert sm.is_all_destinations_completed("new_post") is False

    def test_duplicate_mark_destination(self, state_file):
        sm = StateManager(state_file)
        sm.mark_destination_completed("post_a", "discord_log")
        sm.mark_destination_completed("post_a", "discord_log")
        assert sm.completed_destinations["post_a"].count("discord_log") == 1


class TestDiscordLogFailedPosts:

    def test_add_discord_log_failed_post(self, state_file):
        sm = StateManager(state_file)
        result = sm.add_discord_log_failed_post("post_a", "2025-07-13T10:00:00Z", "webhook error")
        assert result is False  # Not permanently failed yet
        assert sm.is_discord_log_failed("post_a") is True
        assert sm.get_discord_log_failed_count("post_a") == 1

    def test_discord_log_permanent_failure(self, state_file):
        sm = StateManager(state_file)
        sm.add_discord_log_failed_post("post_a", "2025-07-13T10:00:00Z", "error 1")
        sm.add_discord_log_failed_post("post_a", "2025-07-13T10:00:00Z", "error 2")
        result = sm.add_discord_log_failed_post("post_a", "2025-07-13T10:00:00Z", "error 3")
        assert result is True  # Permanently failed after 3 retries
        assert sm.is_discord_log_permanently_failed("post_a") is True
        assert sm.is_discord_log_failed("post_a") is False  # Removed from active failures

    def test_remove_from_discord_log_failed(self, state_file):
        sm = StateManager(state_file)
        sm.add_discord_log_failed_post("post_a", "2025-07-13T10:00:00Z", "error")
        sm.remove_from_discord_log_failed("post_a")
        assert sm.is_discord_log_failed("post_a") is False

    def test_remove_nonexistent_from_discord_log_failed(self, state_file):
        sm = StateManager(state_file)
        sm.remove_from_discord_log_failed("nonexistent")  # Should not raise

    def test_get_discord_log_failed_count_nonexistent(self, state_file):
        sm = StateManager(state_file)
        assert sm.get_discord_log_failed_count("nonexistent") == 0


class TestCompletedDestinationsTrimming:
    """Regression tests for the cache trimming bug that caused infinite reprocessing."""

    def test_in_progress_post_not_trimmed_from_completed_destinations(self, state_file):
        """When cache is full, marking a new post's destination must not be lost to trimming."""
        sm = StateManager(state_file)
        sm.max_cache_size = 5

        for i in range(5):
            pid = f"old_post_{i}"
            sm.mark_destination_completed(pid, "discord_log")
            sm.add_processed_post(pid, f"2025-07-13T09:0{i}:00Z")

        assert len(sm.processed_posts_cache) == 5

        sm.mark_destination_completed("new_post", "discord_log")
        assert sm.is_destination_completed("new_post", "discord_log") is True

        sm.mark_destination_completed("new_post", "discord_log")
        assert sm.is_all_destinations_completed("new_post") is True

    def test_fully_completed_evicted_post_is_trimmed_on_disk(self, state_file):
        """Fully completed posts evicted from cache are trimmed on disk, not in memory."""
        sm = StateManager(state_file)
        sm.max_cache_size = 3

        for i in range(4):
            pid = f"post_{i}"
            sm.mark_destination_completed(pid, "discord_log")
            sm.add_processed_post(pid, f"2025-07-13T09:0{i}:00Z")

        # Reload from disk — evicted post should not be present
        sm2 = StateManager(state_file)
        assert "post_0" not in sm2.completed_destinations


class TestStatePersistence:

    def test_new_fields_persisted(self, state_file):
        sm = StateManager(state_file)
        sm.mark_destination_completed("post_a", "discord_log")
        sm.add_discord_log_failed_post("post_b", "2025-07-13T10:00:00Z", "error")

        # Reload from file
        sm2 = StateManager(state_file)
        assert sm2.is_destination_completed("post_a", "discord_log") is True
        assert sm2.is_discord_log_failed("post_b") is True
