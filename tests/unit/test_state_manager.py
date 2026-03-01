"""
Tests for StateManager.
"""
import pytest
import json
import os
from datetime import datetime, timezone
from unittest.mock import patch, mock_open
from process_skyblue.core.state_manager import StateManager


class TestStateManager:
    """Test cases for StateManager."""
    
    def test_init_creates_default_state_file(self, temp_state_file):
        """Test that StateManager creates default state file if none exists."""
        non_existent_path = "/tmp/non_existent_state.json"
        
        with patch('os.path.exists', return_value=False):
            with patch('builtins.open', mock_open()) as mock_file:
                with patch('json.dump') as mock_json_dump:
                    state_manager = StateManager(non_existent_path)
                    
                    # Should create file with default state
                    mock_file.assert_called()
                    mock_json_dump.assert_called()
    
    def test_load_existing_state_file(self, temp_state_file):
        """Test loading existing state file."""
        state_manager = StateManager(temp_state_file)
        
        assert state_manager.last_processed_at == "2025-07-13T09:00:00.000Z"
        assert state_manager.last_check == "2025-07-13T09:00:00.000Z"
    
    def test_update_last_processed_at(self, temp_state_file):
        """Test updating last processed timestamp."""
        state_manager = StateManager(temp_state_file)
        new_timestamp = "2025-07-13T11:00:00.000Z"
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('json.dump') as mock_json_dump:
                state_manager.update_last_processed_at(new_timestamp)
                
                assert state_manager.last_processed_at == new_timestamp
                mock_file.assert_called()
                mock_json_dump.assert_called()
    
    def test_update_last_check(self, temp_state_file):
        """Test updating last check timestamp."""
        state_manager = StateManager(temp_state_file)
        new_timestamp = "2025-07-13T11:00:00.000Z"
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('json.dump') as mock_json_dump:
                state_manager.update_last_check(new_timestamp)
                
                assert state_manager.last_check == new_timestamp
                mock_file.assert_called()
                mock_json_dump.assert_called()
    
    def test_get_last_processed_datetime(self, temp_state_file):
        """Test getting last processed time as datetime object."""
        state_manager = StateManager(temp_state_file)
        
        dt = state_manager.get_last_processed_datetime()
        
        assert isinstance(dt, datetime)
        assert dt.year == 2025
        assert dt.month == 7
        assert dt.day == 13
        assert dt.hour == 9
    
    def test_is_newer_than_last_processed(self, temp_state_file):
        """Test checking if timestamp is newer than last processed."""
        state_manager = StateManager(temp_state_file)
        
        # Newer timestamp
        newer_time = "2025-07-13T10:00:00.000Z"
        assert state_manager.is_newer_than_last_processed(newer_time) is True
        
        # Older timestamp
        older_time = "2025-07-13T08:00:00.000Z"
        assert state_manager.is_newer_than_last_processed(older_time) is False
        
        # Same timestamp
        same_time = "2025-07-13T09:00:00.000Z"
        assert state_manager.is_newer_than_last_processed(same_time) is False