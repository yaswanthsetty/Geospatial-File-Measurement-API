import logging
from typing import Any
import pyproj
from shapely.geometry.base import BaseGeometry
import shapely

from app.models.schemas import (
    AreaMeasurement,
    FeatureMeasurement,
    LengthMeasurement,
    MeasurementStatus,
    MeasurementSummary,
    MeasurementType,
)
from app.services.crs_service import CRSService

logger = logging.getLogger(__name__)

# Conversion constants
SQ_METERS_TO_SQ_KM = 1e-6
SQ_METERS_TO_HECTARES = 1e-4
SQ_METERS_TO_ACRES = 1.0 / 4046.8564224
METERS_TO_KM = 1e-3
METERS_TO_MILES = 1.0 / 1609.344


class MeasurementService:
    @staticmethod
    def calculate_feature_measurement(
        feature_id: Any,
        geometry: BaseGeometry,
        source_crs: pyproj.CRS,
        source_crs_str: str,
        properties: dict[str, Any] | None = None,
    ) -> FeatureMeasurement:
        """
        Calculates measurements for a single geometry feature using appropriate CRS projection.
        Gracefully handles unsupported and invalid geometries without crashing.
        """
        properties = properties or {}

        if geometry is None or geometry.is_empty:
            return FeatureMeasurement(
                feature_id=feature_id,
                geometry_type="Empty/None",
                measurement_type=MeasurementType.NONE,
                supported=False,
                status=MeasurementStatus.WARNING,
                message="Geometry is empty or null.",
                source_crs=source_crs_str,
                properties=properties,
            )

        geom_type = geometry.geom_type

        # Validate geometry, attempt fix if invalid
        if not geometry.is_valid:
            try:
                geometry = shapely.make_valid(geometry)
                geom_type = geometry.geom_type
            except Exception as e:
                logger.warning("Feature %s is invalid and could not be repaired: %s", feature_id, e)
                return FeatureMeasurement(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_type=MeasurementType.UNSUPPORTED,
                    supported=False,
                    status=MeasurementStatus.ERROR,
                    message=f"Invalid geometry: {e}",
                    source_crs=source_crs_str,
                    properties=properties,
                )

        # Points / MultiPoints: No measurement required per specification
        if geom_type in ("Point", "MultiPoint"):
            return FeatureMeasurement(
                feature_id=feature_id,
                geometry_type=geom_type,
                measurement_type=MeasurementType.NONE,
                supported=False,
                status=MeasurementStatus.SKIPPED_UNSUPPORTED,
                message="Points do not have area or length measurements.",
                source_crs=source_crs_str,
                properties=properties,
            )

        # Polygons: Area calculation
        if geom_type in ("Polygon", "MultiPolygon"):
            try:
                projected_crs, proj_label = CRSService.determine_optimal_projected_crs(
                    geometry, source_crs
                )
                proj_geom = CRSService.transform_to_crs(geometry, source_crs, projected_crs)
                area_m2 = round(float(proj_geom.area), 4)
                perimeter_m = round(float(proj_geom.length), 4)

                area_meas = AreaMeasurement(
                    area_sq_meters=area_m2,
                    area_sq_kilometers=round(area_m2 * SQ_METERS_TO_SQ_KM, 6),
                    area_hectares=round(area_m2 * SQ_METERS_TO_HECTARES, 6),
                    area_acres=round(area_m2 * SQ_METERS_TO_ACRES, 6),
                    perimeter_meters=perimeter_m,
                )

                geodesic = CRSService.calculate_geodesic_measurements(geometry, source_crs)

                return FeatureMeasurement(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_type=MeasurementType.AREA,
                    supported=True,
                    status=MeasurementStatus.SUCCESS,
                    message="Area calculated successfully in projected metric CRS.",
                    source_crs=source_crs_str,
                    projected_crs=proj_label,
                    area=area_meas,
                    geodesic=geodesic,
                    properties=properties,
                )
            except Exception as e:
                logger.error("Failed to calculate polygon area for feature %s: %s", feature_id, e)
                return FeatureMeasurement(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_type=MeasurementType.AREA,
                    supported=True,
                    status=MeasurementStatus.ERROR,
                    message=f"Error calculating area: {e}",
                    source_crs=source_crs_str,
                    properties=properties,
                )

        # LineStrings: Length calculation
        if geom_type in ("LineString", "MultiLineString", "LinearRing"):
            try:
                projected_crs, proj_label = CRSService.determine_optimal_projected_crs(
                    geometry, source_crs
                )
                proj_geom = CRSService.transform_to_crs(geometry, source_crs, projected_crs)
                len_m = round(float(proj_geom.length), 4)

                len_meas = LengthMeasurement(
                    length_meters=len_m,
                    length_kilometers=round(len_m * METERS_TO_KM, 6),
                    length_miles=round(len_m * METERS_TO_MILES, 6),
                )

                geodesic = CRSService.calculate_geodesic_measurements(geometry, source_crs)

                return FeatureMeasurement(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_type=MeasurementType.LENGTH,
                    supported=True,
                    status=MeasurementStatus.SUCCESS,
                    message="Length calculated successfully in projected metric CRS.",
                    source_crs=source_crs_str,
                    projected_crs=proj_label,
                    length=len_meas,
                    geodesic=geodesic,
                    properties=properties,
                )
            except Exception as e:
                logger.error("Failed to calculate linestring length for feature %s: %s", feature_id, e)
                return FeatureMeasurement(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_type=MeasurementType.LENGTH,
                    supported=True,
                    status=MeasurementStatus.ERROR,
                    message=f"Error calculating length: {e}",
                    source_crs=source_crs_str,
                    properties=properties,
                )

        # GeometryCollection: Composite calculation
        if geom_type == "GeometryCollection":
            try:
                projected_crs, proj_label = CRSService.determine_optimal_projected_crs(
                    geometry, source_crs
                )
                proj_geom = CRSService.transform_to_crs(geometry, source_crs, projected_crs)

                # Extract sub-geometries
                total_area = 0.0
                total_length = 0.0
                has_polygon = False
                has_linestring = False

                for sub in proj_geom.geoms:
                    if sub.geom_type in ("Polygon", "MultiPolygon"):
                        total_area += sub.area
                        has_polygon = True
                    elif sub.geom_type in ("LineString", "MultiLineString"):
                        total_length += sub.length
                        has_linestring = True

                area_meas = None
                if has_polygon:
                    area_meas = AreaMeasurement(
                        area_sq_meters=round(total_area, 4),
                        area_sq_kilometers=round(total_area * SQ_METERS_TO_SQ_KM, 6),
                        area_hectares=round(total_area * SQ_METERS_TO_HECTARES, 6),
                        area_acres=round(total_area * SQ_METERS_TO_ACRES, 6),
                    )

                len_meas = None
                if has_linestring:
                    len_meas = LengthMeasurement(
                        length_meters=round(total_length, 4),
                        length_kilometers=round(total_length * METERS_TO_KM, 6),
                        length_miles=round(total_length * METERS_TO_MILES, 6),
                    )

                return FeatureMeasurement(
                    feature_id=feature_id,
                    geometry_type=geom_type,
                    measurement_type=MeasurementType.AREA if has_polygon else MeasurementType.LENGTH,
                    supported=True,
                    status=MeasurementStatus.SUCCESS,
                    message="GeometryCollection measurements computed from constituent parts.",
                    source_crs=source_crs_str,
                    projected_crs=proj_label,
                    area=area_meas,
                    length=len_meas,
                    properties=properties,
                )
            except Exception as e:
                logger.error("Failed to calculate collection for feature %s: %s", feature_id, e)

        # Any other unhandled geometry type (handled gracefully rather than crashing)
        return FeatureMeasurement(
            feature_id=feature_id,
            geometry_type=geom_type,
            measurement_type=MeasurementType.UNSUPPORTED,
            supported=False,
            status=MeasurementStatus.SKIPPED_UNSUPPORTED,
            message=f"Geometry type '{geom_type}' is not currently supported for measurements.",
            source_crs=source_crs_str,
            properties=properties,
        )

    @classmethod
    def summarize_measurements(cls, measurements: list[FeatureMeasurement]) -> MeasurementSummary:
        """Aggregate summary metrics across all processed feature measurements."""
        total = len(measurements)
        measured = sum(1 for m in measurements if m.supported and m.status == MeasurementStatus.SUCCESS)
        skipped = total - measured

        total_area = sum(m.area.area_sq_meters for m in measurements if m.area)
        total_len = sum(m.length.length_meters for m in measurements if m.length)

        return MeasurementSummary(
            total_features=total,
            measured_features=measured,
            skipped_features=skipped,
            total_area_sq_meters=round(total_area, 4),
            total_area_sq_kilometers=round(total_area * SQ_METERS_TO_SQ_KM, 6),
            total_area_hectares=round(total_area * SQ_METERS_TO_HECTARES, 6),
            total_length_meters=round(total_len, 4),
            total_length_kilometers=round(total_len * METERS_TO_KM, 6),
        )

