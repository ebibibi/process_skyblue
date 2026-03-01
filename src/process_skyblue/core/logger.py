"""
Logger for Process SkyBlue.

Provides centralized logging with Discord notification integration
for error handling and monitoring.
"""
import logging
import sys
from typing import Optional
from datetime import datetime


class Logger:
    """Centralized logger with Discord integration."""
    
    def __init__(
        self, 
        name: str = "process_skyblue", 
        level: int = logging.INFO,
        discord_notifier: Optional[object] = None
    ):
        """
        Initialize logger.
        
        Args:
            name: Logger name
            level: Logging level
            discord_notifier: Discord notifier instance for error alerts
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.discord_notifier = discord_notifier
        
        # Avoid duplicate handlers
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self) -> None:
        """Setup console and file handlers."""
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(console_handler)
    
    def info(self, message: str) -> None:
        """Log info message."""
        self.logger.info(message)
    
    def warning(self, message: str) -> None:
        """Log warning message."""
        self.logger.warning(message)
    
    def error(self, message: str) -> None:
        """Log error message and send Discord notification."""
        self.logger.error(message)
        if self.discord_notifier:
            self.discord_notifier.send_error_notification(
                error_type="Error",
                message=message,
                timestamp=datetime.utcnow().isoformat()
            )
    
    def debug(self, message: str) -> None:
        """Log debug message."""
        self.logger.debug(message)
    
    def exception(self, message: str, exc_info=None) -> None:
        """Log exception with traceback and send Discord notification."""
        self.logger.exception(message)
        if self.discord_notifier:
            self.discord_notifier.send_error_notification(
                error_type="Exception",
                message=f"{message}: {str(exc_info) if exc_info else 'Unknown exception'}",
                timestamp=datetime.utcnow().isoformat()
            )