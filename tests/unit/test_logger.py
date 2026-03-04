"""
Tests for Logger.
"""
import pytest
import logging
from unittest.mock import patch, Mock
from process_bluesky.core.logger import Logger


class TestLogger:
    """Test cases for Logger."""
    
    def test_logger_initialization(self):
        """Test logger initialization with default settings."""
        logger = Logger()
        
        assert logger.logger.name == "process_bluesky"
        assert logger.logger.level == logging.INFO
    
    def test_logger_with_custom_name_and_level(self):
        """Test logger initialization with custom name and level."""
        logger = Logger(name="test_logger", level=logging.DEBUG)
        
        assert logger.logger.name == "test_logger"
        assert logger.logger.level == logging.DEBUG
    
    def test_info_logging(self):
        """Test info level logging."""
        with patch('logging.Logger.info') as mock_info:
            logger = Logger()
            logger.info("Test info message")
            
            mock_info.assert_called_once_with("Test info message")
    
    def test_error_logging(self):
        """Test error level logging."""
        with patch('logging.Logger.error') as mock_error:
            logger = Logger()
            logger.error("Test error message")
            
            mock_error.assert_called_once_with("Test error message")
    
    def test_warning_logging(self):
        """Test warning level logging."""
        with patch('logging.Logger.warning') as mock_warning:
            logger = Logger()
            logger.warning("Test warning message")
            
            mock_warning.assert_called_once_with("Test warning message")
    
    def test_debug_logging(self):
        """Test debug level logging."""
        with patch('logging.Logger.debug') as mock_debug:
            logger = Logger()
            logger.debug("Test debug message")
            
            mock_debug.assert_called_once_with("Test debug message")
    
    def test_exception_logging_with_discord_notification(self):
        """Test exception logging triggers Discord notification."""
        mock_discord = Mock()
        
        with patch('logging.Logger.exception') as mock_exception:
            logger = Logger(discord_notifier=mock_discord)
            test_exception = Exception("Test exception")
            
            logger.exception("Exception occurred", exc_info=test_exception)
            
            mock_exception.assert_called_once_with("Exception occurred")
            mock_discord.send_error_notification.assert_called_once()