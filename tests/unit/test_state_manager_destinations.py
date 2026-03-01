"""
Tests for StateManager per-destination tracking.
"""
import pytest
import json
import os
import tempfile
from process_skyblue.core.state_manager import StateManager


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
        sm.mark_destination_completed("post_a", "x")
        assert sm.is_destination_completed("post_a", "x") is True
        assert sm.is_destination_completed("post_a", "discord_ebilog") is False

    def test_is_all_destinations_completed(self, state_file):
        sm = StateManager(state_file)
        sm.mark_destination_completed("post_a", "x")
        assert sm.is_all_destinations_completed("post_a") is False
        sm.mark_destination_completed("post_a", "discord_ebilog")
        assert sm.is_all_destinations_completed("post_a") is True

    def test_backward_compatibility_legacy_posts(self, state_file_with_legacy_posts):
        sm = StateManager(state_file_with_legacy_posts)
        # Legacy posts should be treated as all-destinations-completed
        assert sm.is_destination_completed("post_1", "x") is True
        assert sm.is_destination_completed("post_1", "discord_ebilog") is True
        assert sm.is_all_destinations_completed("post_1") is True
        assert sm.is_all_destinations_completed("post_2") is True

    def test_new_post_not_in_completed(self, state_file):
        sm = StateManager(state_file)
        assert sm.is_destination_completed("new_post", "x") is False
        assert sm.is_destination_completed("new_post", "discord_ebilog") is False
        assert sm.is_all_destinations_completed("new_post") is False

    def test_duplicate_mark_destination(self, state_file):
        sm = StateManager(state_file)
        sm.mark_destination_completed("post_a", "x")
        sm.mark_destination_completed("post_a", "x")
        assert sm.completed_destinations["post_a"].count("x") == 1


class TestDiscordEbilogFailedPosts:

    def test_add_discord_ebilog_failed_post(self, state_file):
        sm = StateManager(state_file)
        result = sm.add_discord_ebilog_failed_post("post_a", "2025-07-13T10:00:00Z", "webhook error")
        assert result is False  # Not permanently failed yet
        assert sm.is_discord_ebilog_failed("post_a") is True
        assert sm.get_discord_ebilog_failed_count("post_a") == 1

    def test_discord_ebilog_permanent_failure(self, state_file):
        sm = StateManager(state_file)
        sm.add_discord_ebilog_failed_post("post_a", "2025-07-13T10:00:00Z", "error 1")
        sm.add_discord_ebilog_failed_post("post_a", "2025-07-13T10:00:00Z", "error 2")
        result = sm.add_discord_ebilog_failed_post("post_a", "2025-07-13T10:00:00Z", "error 3")
        assert result is True  # Permanently failed after 3 retries
        assert sm.is_discord_ebilog_permanently_failed("post_a") is True
        assert sm.is_discord_ebilog_failed("post_a") is False  # Removed from active failures

    def test_remove_from_discord_ebilog_failed(self, state_file):
        sm = StateManager(state_file)
        sm.add_discord_ebilog_failed_post("post_a", "2025-07-13T10:00:00Z", "error")
        sm.remove_from_discord_ebilog_failed("post_a")
        assert sm.is_discord_ebilog_failed("post_a") is False

    def test_remove_nonexistent_from_discord_ebilog_failed(self, state_file):
        sm = StateManager(state_file)
        sm.remove_from_discord_ebilog_failed("nonexistent")  # Should not raise

    def test_get_discord_ebilog_failed_count_nonexistent(self, state_file):
        sm = StateManager(state_file)
        assert sm.get_discord_ebilog_failed_count("nonexistent") == 0


class TestStatePersistence:

    def test_new_fields_persisted(self, state_file):
        sm = StateManager(state_file)
        sm.mark_destination_completed("post_a", "x")
        sm.add_discord_ebilog_failed_post("post_b", "2025-07-13T10:00:00Z", "error")

        # Reload from file
        sm2 = StateManager(state_file)
        assert sm2.is_destination_completed("post_a", "x") is True
        assert sm2.is_discord_ebilog_failed("post_b") is True
