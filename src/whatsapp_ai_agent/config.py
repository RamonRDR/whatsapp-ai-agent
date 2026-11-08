"""Explicit application configuration with outbound traffic disabled by default."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str = "sqlite:///./whatsapp_agent.db"
    demo_enabled: bool = True
    admin_api_key: str = "local-development-key-change-before-deploying"
    webhook_verify_token: str = ""
    meta_app_secret: str = ""
    meta_access_token: str = ""
    meta_phone_number_id: str = ""
    meta_graph_version: str = "v23.0"
    enable_real_send: bool = False
    llm_provider: str = "deterministic"
    llm_api_base: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_max_tokens: int = Field(400, ge=16, le=2048)
    llm_max_tool_calls: int = Field(3, ge=1, le=5)
    message_retention_days: int = Field(30, ge=1, le=365)

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        if self.app_env != "local":
            if self.demo_enabled:
                raise ValueError("Demo endpoints must be disabled outside local mode")
            if len(self.admin_api_key) < 32 or self.admin_api_key.startswith("local-"):
                raise ValueError("Provide a strong ADMIN_API_KEY outside local mode")
        if self.enable_real_send and not all(
            (self.meta_access_token, self.meta_phone_number_id, self.meta_app_secret)
        ):
            raise ValueError("Real sending requires Meta credentials and app secret")
        if self.llm_provider not in {"deterministic", "openai-compatible"}:
            raise ValueError("Unsupported LLM provider")
        if self.llm_provider == "openai-compatible" and not all((self.llm_api_key, self.llm_model)):
            raise ValueError("LLM credentials and model required for live provider")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
