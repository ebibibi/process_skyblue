"""Tests for the circuit breaker safety mechanism."""
import json
import os
import pytest
from datetime import datetime, timezone, timedelta
from process_bluesky.core.state_manager import StateManager, CircuitBreakerTripped, DuplicateContentSkipped


@pytest.fixture
def state(tmp_path):
    """Create a StateManager with a temp state file."""
    state_file = str(tmp_path / "state.json")
    return StateManager(state_file_path=state_file)


class TestCircuitBreakerCheck:
    def test_not_tripped_by_default(self, state):
        state.check_circuit_breaker()  # Should not raise

    def test_tripped_blocks_execution(self, state):
        with pytest.raises(CircuitBreakerTripped):
            state._trip_breaker("test reason")
        # Now it's tripped — check_circuit_breaker should also raise
        with pytest.raises(CircuitBreakerTripped, match="test reason"):
            state.check_circuit_breaker()

    def test_reset_allows_execution(self, state):
        with pytest.raises(CircuitBreakerTripped):
            state._trip_breaker("test reason")
        state.reset_circuit_breaker()
        state.check_circuit_breaker()  # Should not raise

    def test_tripped_state_persists_across_loads(self, state):
        with pytest.raises(CircuitBreakerTripped):
            state._trip_breaker("persisted reason")
        # Reload from same file
        state2 = StateManager(state_file_path=state.state_file_path)
        assert state2.circuit_breaker_tripped is True
        assert state2.circuit_breaker_reason == "persisted reason"
        with pytest.raises(CircuitBreakerTripped):
            state2.check_circuit_breaker()


class TestPrePostCheck:
    def test_passes_for_first_post(self, state):
        state.pre_post_check("Hello world")  # Should not raise

    def test_duplicate_content_skips_post(self, state):
        state.record_x_post("Same content here")
        with pytest.raises(DuplicateContentSkipped, match="Duplicate content"):
            state.pre_post_check("Same content here")
        # Circuit breaker should NOT be tripped for duplicates
        assert not state.circuit_breaker_tripped

    def test_different_content_passes(self, state):
        state.record_x_post("First post")
        state.pre_post_check("Second post")  # Should not raise

    def test_rolling_window_limit(self, state):
        state.cb_max_posts_per_window = 3
        state.cb_window_minutes = 30
        for i in range(3):
            state.record_x_post(f"Post number {i}")
        with pytest.raises(CircuitBreakerTripped, match="Rolling window limit"):
            state.pre_post_check("One too many")

    def test_per_run_limit(self, state):
        state.cb_max_posts_per_run = 2
        state.cb_max_posts_per_window = 100  # Don't hit this one
        state.record_x_post("Run post 1")
        state.record_x_post("Run post 2")
        with pytest.raises(CircuitBreakerTripped, match="Per-run limit"):
            state.pre_post_check("Run post 3")

    def test_old_posts_outside_window_dont_count(self, state):
        state.cb_max_posts_per_window = 3
        state.cb_window_minutes = 30
        # Inject old timestamps (2 hours ago)
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        state.x_post_log = [old_time] * 5
        state._save_state()
        # Should pass because those are outside the window
        state.pre_post_check("New post")  # Should not raise


class TestRecordXPost:
    def test_records_timestamp_and_hash(self, state):
        assert len(state.x_post_log) == 0
        assert len(state.x_content_hashes) == 0
        state.record_x_post("Test content")
        assert len(state.x_post_log) == 1
        assert len(state.x_content_hashes) == 1

    def test_increments_run_counter(self, state):
        assert state._posts_this_run == 0
        state.record_x_post("Post 1")
        assert state._posts_this_run == 1
        state.record_x_post("Post 2")
        assert state._posts_this_run == 2

    def test_persists_across_loads(self, state):
        state.record_x_post("Persisted post")
        state2 = StateManager(state_file_path=state.state_file_path)
        assert len(state2.x_post_log) == 1
        assert len(state2.x_content_hashes) == 1
        # But run counter resets (new process)
        assert state2._posts_this_run == 0

    def test_content_hash_trimmed_to_100(self, state):
        for i in range(120):
            state.x_content_hashes.append(f"hash_{i}")
        state._save_state()
        state2 = StateManager(state_file_path=state.state_file_path)
        assert len(state2.x_content_hashes) == 100

    def test_post_log_trimmed_to_24h(self, state):
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        recent = datetime.now(timezone.utc).isoformat()
        state.x_post_log = [old, old, recent]
        state._save_state()
        state2 = StateManager(state_file_path=state.state_file_path)
        assert len(state2.x_post_log) == 1  # Only the recent one
