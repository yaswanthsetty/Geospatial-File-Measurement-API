import logging
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.exceptions import InvalidFileError, ResourceNotFoundError
from app.models.schemas import (
    FileInfoResponse,
    FileMeasurementsResponse,
    GeoJSONFeatureCollection,
)
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["Geospatial Files"])


@router.post(
    "/",
    response_model=FileInfoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload & Process Geospatial File",
    description=(
        "Accepts a geospatial file (.zip containing Shapefile components or .kml), "
        "validates file integrity, parses geometry features and CRS, transforms geographic "
        "coordinates to optimal projected metric coordinate systems, and calculates measurements."
    ),
)
async def upload_file(
    file: UploadFile = File(
        ...,
        description="Geospatial file: .zip (containing .shp, .shx, .dbf, etc.) or .kml file",
    )
):
    try:
        result = await storage_service.save_and_process_upload(file)
        return result
    except (InvalidFileError, ResourceNotFoundError):
        raise
    except Exception as e:
        logger.exception("Unexpected error during file upload/processing: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing the file: {e}",
        )


@router.get(
    "/",
    response_model=list[FileInfoResponse],
    summary="List Uploaded Files",
    description="Retrieves a list of all uploaded and processed geospatial files.",
)
async def list_files():
    return storage_service.list_files()


@router.get(
    "/{file_id}/",
    response_model=FileInfoResponse,
    summary="Get File Information",
    description="Returns metadata and processing status for a specific uploaded geospatial file.",
)
async def get_file_info(file_id: str):
    return storage_service.get_file_info(file_id)


@router.get(
    "/{file_id}/measurements/",
    response_model=FileMeasurementsResponse,
    summary="Get File Feature Measurements",
    description=(
        "Returns calculated measurements (area in m²/km²/ha/ac for polygons, "
        "length in m/km/mi for linestrings, and WGS84 geodesic benchmarks) "
        "for features in the file."
    ),
)
async def get_file_measurements(file_id: str):
    return storage_service.get_measurements(file_id)


@router.get(
    "/{file_id}/features/",
    response_model=GeoJSONFeatureCollection,
    summary="Get File GeoJSON FeatureCollection",
    description="Returns the processed features in standard GeoJSON FeatureCollection format.",
)
async def get_file_features(file_id: str):
    return storage_service.get_features_geojson(file_id)


@router.delete(
    "/{file_id}/",
    status_code=status.HTTP_200_OK,
    summary="Delete File",
    description="Deletes an uploaded file, its artifacts, and measurement data.",
)
async def delete_file(file_id: str):
    storage_service.delete_file(file_id)
    return {"message": f"File '{file_id}' deleted successfully."}

