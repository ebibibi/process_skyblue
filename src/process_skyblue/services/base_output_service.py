"""
Base Output Service interface for Process SkyBlue.

Defines the common interface that all output services must implement
to ensure consistent behavior and easy extensibility.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseOutputService(ABC):
    """Abstract base class for output services."""
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the output service.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def post_content(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Post content to the output service.
        
        Args:
            content: Content to post
            metadata: Optional metadata for the post
            
        Returns:
            Result dictionary with format:
            {
                "success": bool,     # Whether post was successful
                "id": str,          # Posted content ID (if successful)
                "error": str        # Error message (if failed)
            }
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """
        Close connection to the output service.
        """
        pass
    
    def get_service_name(self) -> str:
        """
        Get the name of this service.
        
        Returns:
            Service name
        """
        return self.__class__.__name__
    
    def validate_content(self, content: str) -> bool:
        """
        Validate content before posting (override in subclasses).
        
        Args:
            content: Content to validate
            
        Returns:
            True if content is valid
        """
        return len(content.strip()) > 0