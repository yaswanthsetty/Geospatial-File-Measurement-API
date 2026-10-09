import logging
from pathlib import Path
from typing import Any

from app.core.exceptions import InvalidFileError
from app.models.schemas import (
    FeatureMeasurement,
    MeasurementSummary,
)
from app.services.measurement_service import MeasurementService
from app.services.parsers.kml_parser import KMLParser
from app.services.parsers.shapefile_parser import ShapefileParser

logger = logging.getLogger(__name__)


class ParserService:
    @classmethod
    def process_geospatial_file(
        cls, file_path: Path, filename: str
    ) -> tuple[
        str, list[dict[str, Any]], list[FeatureMeasurement], MeasurementSummary, str
    ]:
        """
        Detects file type, parses features, and computes measurements.

        Returns:
            - file_type: 'SHAPEFILE' or 'KML'
            - features: list of raw feature dictionaries
            - measurements: list of FeatureMeasurement models
            - summary: MeasurementSummary model
            - crs_str: detected/normalized CRS string
        """
        suffix = file_path.suffix.lower()

        if suffix == ".zip":
            file_type = "SHAPEFILE"
            features, geoms, crs_obj, crs_str = ShapefileParser.parse_zip(file_path)
        elif suffix == ".kml":
            file_type = "KML"
            features, geoms, crs_obj, crs_str = KMLParser.parse_kml(file_path)
        else:
            raise InvalidFileError(
                f"Unsupported file format '{suffix}'. Supported formats are: .zip (Shapefile) and .kml."
            )

        # Calculate measurements for every feature
        measurements: list[FeatureMeasurement] = []
        for feat, geom in zip(features, geoms):
            feat_id = feat["feature_id"]
            props = feat.get("properties", {})
            meas = MeasurementService.calculate_feature_measurement(
                feature_id=feat_id,
                geometry=geom,
                source_crs=crs_obj,
                source_crs_str=crs_str,
                properties=props,
            )
            measurements.append(meas)

        summary = MeasurementService.summarize_measurements(measurements)

        return file_type, features, measurements, summary, crs_str
