import datetime
import logging
import shutil
import tempfile
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyproj
import shapefile
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from app.core.exceptions import InvalidFileError
from app.services.crs_service import CRSService

logger = logging.getLogger(__name__)


def serialize_attribute(val: Any) -> Any:
    """Helper to ensure DBF record fields are JSON-serializable."""
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return val


class ShapefileParser:
    @classmethod
    def parse_zip(
        cls, zip_path: Path
    ) -> tuple[list[dict[str, Any]], list[BaseGeometry], pyproj.CRS, str]:
        """
        Extracts and parses a shapefile archive (.zip).
        Returns:
            - features: list of feature dictionaries (id, geometry_type, geometry, crs, properties)
            - geometries: list of Shapely BaseGeometry objects
            - crs_obj: pyproj.CRS object
            - crs_str: normalized CRS string (e.g. EPSG:4326)
        """
        temp_dir = Path(tempfile.mkdtemp(prefix="shp_parse_"))
        try:
            # 1. Safely extract zip archive (Zip Slip prevention)
            cls._safe_extract_zip(zip_path, temp_dir)

            # 2. Locate .shp file
            shp_files = list(temp_dir.rglob("*.shp")) + list(temp_dir.rglob("*.SHP"))
            if not shp_files:
                raise InvalidFileError(
                    "The uploaded zip file does not contain a valid .shp shapefile."
                )

            shp_file = shp_files[0]
            base_stem = shp_file.stem
            parent_dir = shp_file.parent

            # 3. Read CRS from .prj file if present
            prj_candidates = [
                parent_dir / f"{base_stem}.prj",
                parent_dir / f"{base_stem}.PRJ",
            ]
            prj_file = next((f for f in prj_candidates if f.exists()), None)

            crs_wkt_or_text = None
            if prj_file:
                try:
                    crs_wkt_or_text = prj_file.read_text(
                        encoding="utf-8", errors="replace"
                    ).strip()
                except Exception as e:
                    logger.warning("Could not read .prj file: %s", e)

            crs_obj, crs_str = CRSService.parse_crs(
                crs_wkt_or_text, default="EPSG:4326"
            )

            # 4. Read Shapefile records and geometries
            features: list[dict[str, Any]] = []
            shapely_geoms: list[BaseGeometry] = []

            try:
                with shapefile.Reader(str(shp_file)) as sf:
                    for idx, shape_rec in enumerate(sf.iterShapeRecords()):
                        sh = shape_rec.shape
                        if not sh.points and not sh.parts:
                            # Empty geometry
                            continue

                        # Convert to GeoJSON geometry and Shapely geometry
                        geo_dict = sh.__geo_interface__
                        geom = shape(geo_dict)

                        # Clean properties
                        raw_props = shape_rec.record.as_dict()
                        properties = {
                            k: serialize_attribute(v) for k, v in raw_props.items()
                        }

                        feature_id = (
                            properties.get("id") or properties.get("FID") or idx
                        )

                        feature_entry = {
                            "feature_id": feature_id,
                            "geometry_type": geom.geom_type,
                            "geometry": mapping(geom),
                            "crs": crs_str,
                            "properties": properties,
                        }

                        features.append(feature_entry)
                        shapely_geoms.append(geom)

            except Exception as e:
                logger.error("Error reading shapefile content: %s", e)
                raise InvalidFileError(f"Failed to read shapefile content: {e}")

            return features, shapely_geoms, crs_obj, crs_str

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
        """Secure zip extractor preventing path traversal attacks."""
        if not zipfile.is_zipfile(zip_path):
            raise InvalidFileError("The uploaded file is not a valid zip archive.")

        with zipfile.ZipFile(zip_path, "r") as archive:
            target_resolved = target_dir.resolve()
            for member in archive.namelist():
                member_path = (target_dir / member).resolve()
                if not str(member_path).startswith(str(target_resolved)):
                    raise InvalidFileError(
                        f"Security error: archive member '{member}' points outside directory."
                    )
            archive.extractall(target_dir)
