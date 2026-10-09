from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Geospatial File Measurement API"
    PROJECT_VERSION: str = "1.0.0"
    PROJECT_DESCRIPTION: str = (
        "High-performance REST API for geospatial file ingestion (Shapefile, KML), "
        "accurate CRS projection handling, and geometric feature measurements."
    )
    API_PREFIX: str = "/api"

    # File Storage
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage"
    MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
    SUPPORTED_EXTENSIONS: tuple[str, ...] = (".zip", ".kml")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

# Ensure storage directory exists
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)

