from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os

class Settings(BaseSettings):
    SPLUNK_HOST: str = Field(default="localhost")
    SPLUNK_PORT: int = Field(default=8089)
    SPLUNK_USERNAME: str = Field(default="admin")
    SPLUNK_PASSWORD: str = Field(default="changeme")
    SPLUNK_VERIFY_SSL: int = Field(default=0)

    SNOW_INSTANCE: str = Field(default="")
    SNOW_USERNAME: str = Field(default="")
    SNOW_PASSWORD: str = Field(default="")

    OPENAI_API_KEY: str = Field(default="")

    MOCK_MODE: int = Field(default=1)
    TZ: str = Field(default=os.getenv("TZ", "Asia/Singapore"))

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
