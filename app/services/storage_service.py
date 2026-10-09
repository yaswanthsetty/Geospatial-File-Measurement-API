import anyio
import json
import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import InvalidFileError, ResourceNotFoundError
from app.models.schemas import (
    FileInfoResponse,
    FileMeasurementsResponse,
    FileProcessingStatus,
    GeoJSONFeatureCollection,
)
from app.services.parser_service import ParserService

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir or settings.STORAGE_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        # In-memory index for fast lookups
        self._records: dict[str, dict[str, Any]] = {}
        # Load any existing saved files on disk
        self._load_persisted_records()

    def _load_persisted_records(self) -> None:
        """Loads records from metadata.json in storage folders on restart."""
        for file_dir in self.storage_dir.iterdir():
            if file_dir.is_dir():
                meta_path = file_dir / "metadata.json"
                if meta_path.exists():
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            self._records[data["id"]] = data
                    except Exception as e:
                        logger.warning(
                            "Could not load persisted metadata from %s: %s",
                            meta_path,
                            e,
                        )

    async def save_and_process_upload(
        self, upload_file: UploadFile
    ) -> FileInfoResponse:
        """
        Saves uploaded file to disk and runs parser & measurement pipeline.
        """
        if not upload_file.filename:
            raise InvalidFileError("Uploaded file must have a filename.")

        filename = upload_file.filename
        suffix = Path(filename).suffix.lower()

        if suffix not in settings.SUPPORTED_EXTENSIONS:
            raise InvalidFileError(
                f"Unsupported file format '{suffix}'. Supported formats are: "
                f"{', '.join(settings.SUPPORTED_EXTENSIONS)}."
            )

        file_id = uuid.uuid4().hex[:12]
        file_folder = self.storage_dir / file_id
        file_folder.mkdir(parents=True, exist_ok=True)
        saved_file_path = file_folder / filename

        # Stream file to disk while checking size limit
        total_bytes = 0
        try:
            with open(saved_file_path, "wb") as buffer:
                while chunk := await upload_file.read(1024 * 64):  # 64 KB chunks
                    total_bytes += len(chunk)
                    if total_bytes > settings.MAX_FILE_SIZE_BYTES:
                        raise InvalidFileError(
                            f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB."
                        )
                    buffer.write(chunk)
        except Exception:
            shutil.rmtree(file_folder, ignore_errors=True)
            raise

        if total_bytes == 0:
            shutil.rmtree(file_folder, ignore_errors=True)
            raise InvalidFileError("Uploaded file is empty.")

        now = datetime.now(UTC)
        record: dict[str, Any] = {
            "id": file_id,
            "filename": filename,
            "file_type": "SHAPEFILE" if suffix == ".zip" else "KML",
            "feature_count": 0,
            "crs": "UNKNOWN",
            "status": FileProcessingStatus.PROCESSING.value,
            "uploaded_at": now.isoformat(),
            "error_message": None,
            "file_path": str(saved_file_path),
            "features": [],
            "measurements": [],
            "summary": None,
        }

        # Process the geospatial file asynchronously in thread pool to keep event loop unblocked
        try:
            file_type, features, measurements, summary, crs_str = (
                await anyio.to_thread.run_sync(
                    ParserService.process_geospatial_file, saved_file_path, filename
                )
            )

            record["file_type"] = file_type
            record["feature_count"] = len(features)
            record["crs"] = crs_str
            record["status"] = FileProcessingStatus.COMPLETED.value
            record["features"] = features
            record["measurements"] = [m.model_dump() for m in measurements]
            record["summary"] = summary.model_dump()

        except Exception as e:
            logger.error("Processing failed for file %s: %s", file_id, e)
            record["status"] = FileProcessingStatus.FAILED.value
            record["error_message"] = str(e)
            self._save_record_to_disk(file_folder, record)
            self._records[file_id] = record
            raise

        # Save metadata and index
        self._save_record_to_disk(file_folder, record)
        self._records[file_id] = record

        return FileInfoResponse(
            id=record["id"],
            filename=record["filename"],
            file_type=record["file_type"],
            feature_count=record["feature_count"],
            crs=record["crs"],
            status=FileProcessingStatus(record["status"]),
            uploaded_at=datetime.fromisoformat(record["uploaded_at"]),
            error_message=record["error_message"],
        )

    def _save_record_to_disk(self, folder: Path, record: dict[str, Any]) -> None:
        """Persists file record metadata to JSON."""
        try:
            meta_file = folder / "metadata.json"
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2)
        except Exception as e:
            logger.warning("Could not persist record metadata: %s", e)

    def get_file_info(self, file_id: str) -> FileInfoResponse:
        """Retrieve file summary by ID."""
        record = self._records.get(file_id)
        if not record:
            raise ResourceNotFoundError(f"File with ID '{file_id}' not found.")

        return FileInfoResponse(
            id=record["id"],
            filename=record["filename"],
            file_type=record["file_type"],
            feature_count=record["feature_count"],
            crs=record["crs"],
            status=FileProcessingStatus(record["status"]),
            uploaded_at=datetime.fromisoformat(record["uploaded_at"]),
            error_message=record["error_message"],
        )

    def get_measurements(
        self, file_id: str, offset: int = 0, limit: Optional[int] = None
    ) -> FileMeasurementsResponse:
        """Retrieve computed measurements for file features with optional pagination."""
        record = self._records.get(file_id)
        if not record:
            raise ResourceNotFoundError(f"File with ID '{file_id}' not found.")

        all_measurements = record["measurements"]
        if limit is not None:
            paged = all_measurements[offset : offset + limit]
        elif offset > 0:
            paged = all_measurements[offset:]
        else:
            paged = all_measurements

        return FileMeasurementsResponse(
            file_id=record["id"],
            filename=record["filename"],
            summary=record["summary"],
            measurements=paged,
        )

    def get_features_geojson(self, file_id: str) -> GeoJSONFeatureCollection:
        """Retrieve features in standard GeoJSON FeatureCollection format."""
        record = self._records.get(file_id)
        if not record:
            raise ResourceNotFoundError(f"File with ID '{file_id}' not found.")

        geojson_features = []
        for feat in record.get("features", []):
            geojson_features.append(
                {
                    "type": "Feature",
                    "id": feat["feature_id"],
                    "geometry": feat["geometry"],
                    "properties": feat["properties"],
                }
            )

        return GeoJSONFeatureCollection(
            type="FeatureCollection",
            file_id=file_id,
            features=geojson_features,
        )

    def list_files(self, offset: int = 0, limit: Optional[int] = None) -> list[FileInfoResponse]:
        """List all processed files with optional pagination."""
        records = list(self._records.values())
        if limit is not None:
            paged = records[offset : offset + limit]
        elif offset > 0:
            paged = records[offset:]
        else:
            paged = records

        return [
            FileInfoResponse(
                id=rec["id"],
                filename=rec["filename"],
                file_type=rec["file_type"],
                feature_count=rec["feature_count"],
                crs=rec["crs"],
                status=FileProcessingStatus(rec["status"]),
                uploaded_at=datetime.fromisoformat(rec["uploaded_at"]),
                error_message=rec["error_message"],
            )
            for rec in paged
        ]

    def delete_file(self, file_id: str) -> bool:
        """Deletes file record and directory from storage."""
        if file_id not in self._records:
            raise ResourceNotFoundError(f"File with ID '{file_id}' not found.")

        file_folder = self.storage_dir / file_id
        shutil.rmtree(file_folder, ignore_errors=True)
        del self._records[file_id]
        return True


storage_service = StorageService()
