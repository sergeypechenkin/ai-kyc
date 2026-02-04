"""Infrastructure configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Azure OpenAI
    azure_openai_endpoint: str = Field(default="")
    azure_openai_deployment_name: str = Field(default="gpt-5-mini")
    azure_openai_api_version: str = Field(default="2024-02-15-preview")

    # Azure AI Search
    azure_search_endpoint: str = Field(default="")
    azure_search_index_name: str = Field(default="kyc-documents")

    # Azure AD Client ID (for Service Principal authentication, optional)
    azure_client_id: str = Field(default="")

    # Application
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    enable_document_grounding: bool = Field(default=False)

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def azure_openai_configured(self) -> bool:
        return bool(self.azure_openai_endpoint)

    @property
    def azure_search_configured(self) -> bool:
        return bool(self.azure_search_endpoint)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
