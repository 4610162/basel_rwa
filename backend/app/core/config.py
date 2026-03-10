"""
Application configuration via environment variables.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    google_api_key: str = ""
    chroma_db_path: str = "./chroma_db"
    data_dir: str = "./data"
    collection_name: str = "basel3"
    chunk_size: int = 700
    chunk_overlap: int = 100
    top_k: int = 5
    primary_model: str = "gemini-2.5-flash"
    fallback_model: str = "gemini-2.0-flash"
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
