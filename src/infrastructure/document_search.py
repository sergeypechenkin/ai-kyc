"""Document search service for Azure AI Search integration."""

import os
from typing import Any

from dotenv import load_dotenv

from src.infrastructure.config import get_settings

# Load environment variables
load_dotenv()


class DocumentSearchService:
    """Service for searching bank documents using Azure AI Search.

    Requires Azure AI Search to be configured. When not configured,
    search returns empty results (agent will use its base knowledge).
    """

    def __init__(self):
        """Initialize the document search service."""
        self._settings = get_settings()
        self._client = None
        self._initialize_client()

    @property
    def is_available(self) -> bool:
        """Check if document search is available (Azure Search configured)."""
        return self._client is not None

    def _initialize_client(self) -> None:
        """Initialize Azure AI Search client if configured."""
        if not self._settings.azure_search_configured:
            print("Azure Search not configured - document grounding unavailable")
            return

        try:
            from azure.identity import ClientSecretCredential
            from azure.search.documents import SearchClient

            # Use Service Principal credentials
            client_id = os.environ.get("AZURE_CLIENT_ID")
            client_secret = os.environ.get("AZURE_CLIENT_SECRET")
            tenant_id = os.environ.get("AZURE_TENANT_ID")
            
            if all([client_id, client_secret, tenant_id]):
                credential = ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                )
                self._client = SearchClient(
                    endpoint=self._settings.azure_search_endpoint,
                    index_name=self._settings.azure_search_index_name,
                    credential=credential,
                )
                print(f"Azure Search client initialized: {self._settings.azure_search_index_name}")
            else:
                print("Service Principal credentials missing - document grounding unavailable")
        except ImportError as e:
            print(f"Azure SDK not installed: {e} - document grounding unavailable")

    async def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Search for documents matching the query.

        Args:
            query: Search query
            top_k: Maximum number of results

        Returns:
            List of search results with content and source.
            Returns empty list if Azure Search is not configured.
        """
        if not self._client:
            return []
        
        return await self._azure_search(query, top_k)

    async def _azure_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """Search using Azure AI Search.

        Args:
            query: Search query
            top_k: Maximum results

        Returns:
            List of results
        """
        results = []
        try:
            search_results = self._client.search(  # type: ignore
                search_text=query,
                top=top_k,
                select=["content", "title", "source"],
            )

            for result in search_results:
                results.append({
                    "content": result.get("content", ""),
                    "source": result.get("source", result.get("title", "Unknown")),
                    "score": result.get("@search.score", 0),
                })
        except Exception as e:
            print(f"Azure Search error: {e}")
            return []

        return results
