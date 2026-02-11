"""Application configuration for CabinetForge."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration values used by Flask and services."""

    secret_key: str
    max_content_length: int
    upload_dir: Path
    extract_dir: Path
    session_ttl_seconds: int


def build_config() -> AppConfig:
    """Build configuration from environment variables with safe defaults."""

    temp_root = Path(os.environ.get("TEMP", "."))
    upload_dir = Path(os.environ.get("CABINETFORGE_UPLOAD_DIR", temp_root / "cabinetforge_uploads"))
    extract_dir = Path(os.environ.get("CABINETFORGE_EXTRACT_DIR", temp_root / "cabinetforge_extract"))
    upload_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        secret_key=os.environ.get("CABINETFORGE_SECRET_KEY", "cab-webui-local-dev"),
        max_content_length=int(os.environ.get("CABINETFORGE_MAX_UPLOAD_BYTES", 300 * 1024 * 1024)),
        upload_dir=upload_dir,
        extract_dir=extract_dir,
        session_ttl_seconds=int(os.environ.get("CABINETFORGE_SESSION_TTL", 6 * 60 * 60)),
    )
