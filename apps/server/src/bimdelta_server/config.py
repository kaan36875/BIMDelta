from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from bimdelta_core import Settings


class ServerSettings(BaseSettings):
    max_upload_bytes: int = 50 * 1024 * 1024
    # Hosts the viewer's URL mode may download models from.
    url_allowed_hosts: list[str] = [
        "raw.githubusercontent.com",
        "media.githubusercontent.com",
        "objects.githubusercontent.com",
    ]

    model_config = SettingsConfigDict(env_prefix="BIMDELTA_", env_file=".env", extra="ignore")


server_settings = ServerSettings()
diff_settings = Settings()
