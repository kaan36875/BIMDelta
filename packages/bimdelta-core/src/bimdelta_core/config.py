from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB

    # All tolerances in metres
    float_tolerance: float = 1e-5
    placement_translation_tolerance: float = 0.001  # 1 mm
    placement_rotation_tolerance_deg: float = 0.01
    fallback_placement_tolerance: float = 0.050  # 50 mm
    geometry_bbox_tolerance: float = 0.001  # 1 mm
    geometry_volume_tolerance: float = 1e-6  # 1e-6 m³

    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")

    model_config = {"env_prefix": "BIMDELTA_", "env_file": ".env"}


settings = Settings()
