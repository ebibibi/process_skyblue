"""
Configuration Manager for Process SkyBlue.

Handles loading and validating configuration from environment variables
and .env files with proper error handling and validation.
"""
import os
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError, field_validator


class Config(BaseModel):
    """Configuration model with validation."""
    
    bluesky_identifier: str
    bluesky_password: str
    x_api_key: str
    x_api_secret: str
    x_access_token: str
    x_access_token_secret: str
    x_oauth2_client_id: Optional[str] = None
    x_oauth2_client_secret: Optional[str] = None
    discord_webhook_url: str
    discord_log_webhook_url: Optional[str] = None
    polling_interval: int = 60
    x_premium: bool = True

    @field_validator('polling_interval')
    @classmethod
    def validate_polling_interval(cls, v):
        """Validate polling interval is reasonable."""
        if v < 10 or v > 3600:
            raise ValueError('Polling interval must be between 10 and 3600 seconds')
        return v

    @field_validator('discord_webhook_url')
    @classmethod
    def validate_webhook_url(cls, v):
        """Validate Discord webhook URL format."""
        if not (
            v.startswith('https://discord.com/api/webhooks/')
            or v.startswith('https://discordapp.com/api/webhooks/')
        ):
            raise ValueError('Invalid Discord webhook URL format')
        return v

    @field_validator('discord_log_webhook_url')
    @classmethod
    def validate_log_webhook_url(cls, v):
        """Validate Discord log webhook URL format."""
        if v is not None and not (
            v.startswith('https://discord.com/api/webhooks/')
            or v.startswith('https://discordapp.com/api/webhooks/')
        ):
            raise ValueError('Invalid Discord log webhook URL format')
        return v


class ConfigManager:
    """Manages application configuration."""
    
    def __init__(self, env_file: str = '.env'):
        """
        Initialize configuration manager.
        
        Args:
            env_file: Path to environment file
        """
        self.env_file = env_file
        self._config: Optional[Config] = None
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from environment variables and .env file."""
        # Load .env file if it exists
        if os.path.exists(self.env_file):
            load_dotenv(self.env_file)
        
        try:
            self._config = Config(
                bluesky_identifier=self._get_required_env('BLUESKY_IDENTIFIER'),
                bluesky_password=self._get_required_env('BLUESKY_PASSWORD'),
                x_api_key=self._get_required_env('X_API_KEY'),
                x_api_secret=self._get_required_env('X_API_SECRET'),
                x_access_token=self._get_required_env('X_ACCESS_TOKEN'),
                x_access_token_secret=self._get_required_env('X_ACCESS_TOKEN_SECRET'),
                x_oauth2_client_id=os.getenv('X_OAUTH2_CLIENT_ID'),
                x_oauth2_client_secret=os.getenv('X_OAUTH2_CLIENT_SECRET'),
                discord_webhook_url=self._get_required_env('DISCORD_WEBHOOK_URL'),
                discord_log_webhook_url=os.getenv('DISCORD_LOG_WEBHOOK_URL'),
                polling_interval=int(os.getenv('POLLING_INTERVAL', '60')),
                x_premium=os.getenv('X_PREMIUM', 'true').lower() == 'true'
            )
        except ValidationError as e:
            raise ValueError(f"Configuration validation error: {e}")
    
    def _get_required_env(self, key: str) -> str:
        """
        Get required environment variable.
        
        Args:
            key: Environment variable key
            
        Returns:
            Environment variable value
            
        Raises:
            ValueError: If required environment variable is missing
        """
        value = os.getenv(key)
        if value is None:
            raise ValueError(f"Missing required configuration: {key}")
        return value
    
    @property
    def bluesky_identifier(self) -> str:
        """Get Bluesky identifier."""
        return self._config.bluesky_identifier
    
    @property
    def bluesky_password(self) -> str:
        """Get Bluesky password."""
        return self._config.bluesky_password
    
    @property
    def x_api_key(self) -> str:
        """Get X API key."""
        return self._config.x_api_key
    
    @property
    def x_api_secret(self) -> str:
        """Get X API secret."""
        return self._config.x_api_secret
    
    @property
    def x_access_token(self) -> str:
        """Get X access token."""
        return self._config.x_access_token
    
    @property
    def x_access_token_secret(self) -> str:
        """Get X access token secret."""
        return self._config.x_access_token_secret
    
    @property
    def x_oauth2_client_id(self) -> Optional[str]:
        """Get X OAuth 2.0 client ID."""
        return self._config.x_oauth2_client_id
    
    @property
    def x_oauth2_client_secret(self) -> Optional[str]:
        """Get X OAuth 2.0 client secret."""
        return self._config.x_oauth2_client_secret
    
    @property
    def discord_webhook_url(self) -> str:
        """Get Discord webhook URL."""
        return self._config.discord_webhook_url

    @property
    def discord_log_webhook_url(self) -> Optional[str]:
        """Get Discord log webhook URL."""
        return self._config.discord_log_webhook_url

    @property
    def polling_interval(self) -> int:
        """Get polling interval in seconds."""
        return self._config.polling_interval

    @property
    def x_premium(self) -> bool:
        """Get X Premium mode flag."""
        return self._config.x_premium