"""
Base Input Service interface for Process SkyBlue.

Defines the common interface that all input services must implement
to ensure consistent behavior and easy extensibility.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class BaseInputService(ABC):
    """Abstract base class for input services."""
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the input service.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def get_latest_posts(self, since_timestamp: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve latest posts from the service.
        
        Args:
            since_timestamp: Optional timestamp to filter posts newer than this time
            
        Returns:
            List of post dictionaries with standardized format:
            {
                "id": str,           # Unique post identifier
                "content": str,      # Post content/text
                "timestamp": str,    # ISO format timestamp
                "author": str,       # Author identifier
                "metadata": dict     # Additional service-specific data
            }
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """
        Close connection to the input service.
        """
        pass
    
    def get_service_name(self) -> str:
        """
        Get the name of this service.
        
        Returns:
            Service name
        """
        return self.__class__.__name__