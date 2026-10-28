from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "文化智能体 · 基座平台"
    app_version: str = "V1.2.Q1"
    secret_key: str = "base-platform-dev-secret-change-me"
    access_token_expire_minutes: int = 60 * 12
    database_url: str = "sqlite:///./data/base_platform.db"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_default_model: str = "mock-gpt"
    cors_origins: list[str] = ["*"]
    # 企业微信 SSO（可选；不配则走 mock）
    wecom_corp_id: str = ""
    wecom_agent_id: str = ""
    wecom_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
