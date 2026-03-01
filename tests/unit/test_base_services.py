"""
Tests for Base Service interfaces.
"""
import pytest
from abc import ABC
from process_skyblue.services.base_input_service import BaseInputService
from process_skyblue.services.base_output_service import BaseOutputService


class TestBaseInputService:
    """Test cases for BaseInputService interface."""
    
    def test_base_input_service_is_abstract(self):
        """Test that BaseInputService cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseInputService()
    
    def test_base_input_service_has_required_methods(self):
        """Test that BaseInputService has required abstract methods."""
        # Check that required methods are defined as abstract
        assert hasattr(BaseInputService, 'connect')
        assert hasattr(BaseInputService, 'get_latest_posts')
        assert hasattr(BaseInputService, 'disconnect')


class TestBaseOutputService:
    """Test cases for BaseOutputService interface."""
    
    def test_base_output_service_is_abstract(self):
        """Test that BaseOutputService cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseOutputService()
    
    def test_base_output_service_has_required_methods(self):
        """Test that BaseOutputService has required abstract methods."""
        # Check that required methods are defined as abstract
        assert hasattr(BaseOutputService, 'connect')
        assert hasattr(BaseOutputService, 'post_content')
        assert hasattr(BaseOutputService, 'disconnect')


class MockInputService(BaseInputService):
    """Mock implementation for testing."""
    
    def __init__(self):
        self.connected = False
    
    def connect(self):
        self.connected = True
        return True
    
    def get_latest_posts(self, since_timestamp=None):
        return [
            {
                "id": "test_post_1",
                "content": "Test post content",
                "timestamp": "2025-07-13T10:00:00.000Z",
                "author": "test_user"
            }
        ]
    
    def disconnect(self):
        self.connected = False


class MockOutputService(BaseOutputService):
    """Mock implementation for testing."""
    
    def __init__(self):
        self.connected = False
        self.posted_content = []
    
    def connect(self):
        self.connected = True
        return True
    
    def post_content(self, content, metadata=None):
        self.posted_content.append({
            "content": content,
            "metadata": metadata,
            "posted_at": "2025-07-13T10:00:00.000Z"
        })
        return {"success": True, "id": "mock_post_id"}
    
    def disconnect(self):
        self.connected = False


class TestMockServices:
    """Test the mock implementations work correctly."""
    
    def test_mock_input_service(self):
        """Test mock input service implementation."""
        service = MockInputService()
        
        # Test connection
        assert service.connect() is True
        assert service.connected is True
        
        # Test getting posts
        posts = service.get_latest_posts()
        assert len(posts) == 1
        assert posts[0]["id"] == "test_post_1"
        
        # Test disconnection
        service.disconnect()
        assert service.connected is False
    
    def test_mock_output_service(self):
        """Test mock output service implementation."""
        service = MockOutputService()
        
        # Test connection
        assert service.connect() is True
        assert service.connected is True
        
        # Test posting content
        result = service.post_content("Test content", {"source": "test"})
        assert result["success"] is True
        assert len(service.posted_content) == 1
        
        # Test disconnection
        service.disconnect()
        assert service.connected is False