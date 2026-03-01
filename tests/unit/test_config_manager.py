"""
Tests for ConfigManager.
"""
import pytest
import os
import tempfile
from unittest.mock import patch, mock_open
from process_skyblue.core.config_manager import ConfigManager


class TestConfigManager:
    """Test cases for ConfigManager."""
    
    def test_load_from_env_variables(self, mock_config):
        """Test loading configuration from environment variables."""
        env_vars = {
            'BLUESKY_IDENTIFIER': 'test.bsky.social',
            'BLUESKY_PASSWORD': 'test_password',
            'X_API_KEY': 'test_api_key',
            'X_API_SECRET': 'test_api_secret',
            'X_ACCESS_TOKEN': 'test_access_token',
            'X_ACCESS_TOKEN_SECRET': 'test_access_token_secret',
            'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/test',
            'POLLING_INTERVAL': '60'
        }
        
        with patch.dict(os.environ, env_vars):
            config = ConfigManager()
            
            assert config.bluesky_identifier == 'test.bsky.social'
            assert config.bluesky_password == 'test_password'
            assert config.x_api_key == 'test_api_key'
            assert config.x_api_secret == 'test_api_secret'
            assert config.x_access_token == 'test_access_token'
            assert config.x_access_token_secret == 'test_access_token_secret'
            assert config.discord_webhook_url == 'https://discord.com/api/webhooks/test'
            assert config.polling_interval == 60
    
    def test_load_from_env_file(self, mock_config):
        """Test loading configuration from .env file."""
        env_content = """
BLUESKY_IDENTIFIER=test.bsky.social
BLUESKY_PASSWORD=test_password
X_API_KEY=test_api_key
X_API_SECRET=test_api_secret
X_ACCESS_TOKEN=test_access_token
X_ACCESS_TOKEN_SECRET=test_access_token_secret
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/test
POLLING_INTERVAL=60
        """
        
        # Clear environment variables first
        env_vars = {
            'BLUESKY_IDENTIFIER': 'test.bsky.social',
            'BLUESKY_PASSWORD': 'test_password',
            'X_API_KEY': 'test_api_key',
            'X_API_SECRET': 'test_api_secret',
            'X_ACCESS_TOKEN': 'test_access_token',
            'X_ACCESS_TOKEN_SECRET': 'test_access_token_secret',
            'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/test',
            'POLLING_INTERVAL': '60'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch('builtins.open', mock_open(read_data=env_content)):
                with patch('os.path.exists', return_value=True):
                    config = ConfigManager()
                    
                    assert config.bluesky_identifier == 'test.bsky.social'
                    assert config.polling_interval == 60
    
    def test_missing_required_config_raises_error(self):
        """Test that missing required configuration raises ValueError."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('os.path.exists', return_value=False):
                with pytest.raises(ValueError, match="Missing required configuration"):
                    ConfigManager()
    
    def test_validate_config_success(self, mock_config):
        """Test successful configuration validation."""
        env_vars = {
            'BLUESKY_IDENTIFIER': 'test.bsky.social',
            'BLUESKY_PASSWORD': 'test_password',
            'X_API_KEY': 'test_api_key',
            'X_API_SECRET': 'test_api_secret',
            'X_ACCESS_TOKEN': 'test_access_token',
            'X_ACCESS_TOKEN_SECRET': 'test_access_token_secret',
            'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/test',
            'POLLING_INTERVAL': '60'
        }
        
        with patch.dict(os.environ, env_vars):
            config = ConfigManager()
            # Should not raise any exception
            assert config.bluesky_identifier is not None