from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from bimdelta_core import Settings


class ServerSettings(BaseSettings):
    max_upload_bytes: int = 50 * 1024 * 1024

    model_config = SettingsConfigDict(env_prefix="BIMDELTA_", env_file=".env", extra="ignore")


server_settings = ServerSettings()
diff_settings = Settings()
