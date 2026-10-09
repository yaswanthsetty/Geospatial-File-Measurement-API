from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class FileProcessingStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MeasurementType(str, Enum):
    AREA = "area"
    LENGTH = "length"
    NONE = "none"
    UNSUPPORTED = "unsupported"


class MeasurementStatus(str, Enum):
    SUCCESS = "SUCCESS"
    SKIPPED_UNSUPPORTED = "SKIPPED_UNSUPPORTED"
    WARNING = "WARNING"
    ERROR = "ERROR"


class AreaMeasurement(BaseModel):
    area_sq_meters: float = Field(..., description="Area in square meters (m²)")
    area_sq_kilometers: float = Field(..., description="Area in square kilometers (km²)")
    area_hectares: float = Field(..., description="Area in hectares (ha)")
    area_acres: float = Field(..., description="Area in acres (ac)")
    perimeter_meters: Optional[float] = Field(None, description="Perimeter boundary length in meters (m)")


class LengthMeasurement(BaseModel):
    length_meters: float = Field(..., description="Length in meters (m)")
    length_kilometers: float = Field(..., description="Length in kilometers (km)")
    length_miles: float = Field(..., description="Length in miles (mi)")


class GeodesicMeasurement(BaseModel):
    geodesic_area_sq_meters: Optional[float] = Field(
        None, description="Exact geodesic ellipsoidal area in square meters (WGS84)"
    )
    geodesic_length_meters: Optional[float] = Field(
        None, description="Exact geodesic ellipsoidal length in meters (WGS84)"
    )


# ---------------- File Schemas ---------------- #

class FileInfoResponse(BaseModel):
    id: str = Field(..., description="Unique identifier for uploaded file")
    filename: str = Field(..., description="Original filename")
    file_type: str = Field(..., description="File format: SHAPEFILE or KML")
    feature_count: int = Field(..., description="Number of geospatial features")
    crs: str = Field(..., description="Source coordinate reference system, e.g. EPSG:4326")
    status: FileProcessingStatus = Field(..., description="Processing status")
    uploaded_at: datetime = Field(..., description="Timestamp of file upload")
    error_message: Optional[str] = Field(None, description="Error details if processing failed")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "c7a88b1f-7b7f-44be-9f5b-80dfca623049",
                "filename": "survey.kml",
                "file_type": "KML",
                "feature_count": 12,
                "crs": "EPSG:4326",
                "status": "COMPLETED",
                "uploaded_at": "2026-10-09T16:30:00Z",
                "error_message": None,
            }
        }
    }


class FileUploadResponse(FileInfoResponse):
    message: str = Field(..., description="Upload status message")


# ---------------- Feature Schemas ---------------- #

class GeoJSONGeometry(BaseModel):
    type: str = Field(..., description="Geometry type (Point, Polygon, LineString, etc.)")
    coordinates: Any = Field(..., description="GeoJSON coordinates array")


class FeatureDetail(BaseModel):
    feature_id: Any = Field(..., description="Feature ID or index")
    geometry_type: str = Field(..., description="Geometry type")
    geometry: GeoJSONGeometry = Field(..., description="GeoJSON geometry representation")
    crs: str = Field(..., description="Source CRS")
    properties: dict[str, Any] = Field(default_factory=dict, description="Feature attributes")


# ---------------- Measurement Schemas ---------------- #

class FeatureMeasurement(BaseModel):
    feature_id: Any = Field(..., description="Feature identifier/index")
    geometry_type: str = Field(..., description="Type of geometry")
    measurement_type: MeasurementType = Field(..., description="Type of measurement computed")
    supported: bool = Field(..., description="Whether this geometry type supports measurements")
    status: MeasurementStatus = Field(..., description="Measurement calculation status")
    message: Optional[str] = Field(None, description="Explanatory status message")
    source_crs: str = Field(..., description="Source coordinate reference system")
    projected_crs: Optional[str] = Field(None, description="Projected CRS used for planar calculations")
    area: Optional[AreaMeasurement] = Field(None, description="Area calculations for polygons")
    length: Optional[LengthMeasurement] = Field(None, description="Length calculations for linestrings")
    geodesic: Optional[GeodesicMeasurement] = Field(
        None, description="Ellipsoidal geodesic measurements (WGS84)"
    )
    properties: dict[str, Any] = Field(default_factory=dict, description="Feature attributes")


class MeasurementSummary(BaseModel):
    total_features: int = Field(..., description="Total features in file")
    measured_features: int = Field(..., description="Features with valid measurements")
    skipped_features: int = Field(..., description="Features skipped (e.g. Points, empty)")
    total_area_sq_meters: float = Field(0.0, description="Sum of all polygon areas in m²")
    total_area_sq_kilometers: float = Field(0.0, description="Sum of all polygon areas in km²")
    total_area_hectares: float = Field(0.0, description="Sum of all polygon areas in ha")
    total_length_meters: float = Field(0.0, description="Sum of all linestring lengths in m")
    total_length_kilometers: float = Field(0.0, description="Sum of all linestring lengths in km")


class FileMeasurementsResponse(BaseModel):
    file_id: str = Field(..., description="File ID")
    filename: str = Field(..., description="Original filename")
    summary: MeasurementSummary = Field(..., description="Summary of measurements across all features")
    measurements: list[FeatureMeasurement] = Field(..., description="Individual feature measurements")


# ---------------- GeoJSON FeatureCollection ---------------- #

class GeoJSONFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    file_id: str
    features: list[dict[str, Any]]

