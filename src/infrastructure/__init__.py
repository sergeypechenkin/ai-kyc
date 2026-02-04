"""Infrastructure package for Azure services and data access."""

from src.infrastructure.config import Settings, get_settings
from src.infrastructure.mock_data import CustomerRepository
from src.infrastructure.document_search import DocumentSearchService

__all__ = [
    "Settings",
    "get_settings",
    "CustomerRepository",
    "DocumentSearchService",
]
