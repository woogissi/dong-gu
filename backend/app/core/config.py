from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = Field(default="DEU Chatbot API", alias="APP_NAME")
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+psycopg://chatbot:chatbot@postgres:5432/chatbot"
    OPENAI_API_KEY: str | None = None
    KAKAO_MAP_API_KEY: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


settings = Settings()
