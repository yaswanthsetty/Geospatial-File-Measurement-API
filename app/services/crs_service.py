import logging
import numpy as np
import pyproj
from pyproj import CRS, Transformer, Geod
from pyproj.aoi import AreaOfInterest
from pyproj.database import query_utm_crs_info
import shapely
from shapely.geometry.base import BaseGeometry

from app.models.schemas import GeodesicMeasurement

logger = logging.getLogger(__name__)

# Standard WGS84 Ellipsoid Geod for exact geodesic calculations
WGS84_GEOD = Geod(ellps="WGS84")
WGS84_CRS = CRS.from_epsg(4326)


class CRSService:
    @staticmethod
    def parse_crs(crs_input: str | None, default: str = "EPSG:4326") -> tuple[CRS, str]:
        """
        Parse and normalize a CRS definition from EPSG code, WKT string, or PROJ string.
        Returns a tuple of (pyproj.CRS object, normalized CRS identifier string).
        """
        if not crs_input or not crs_input.strip():
            logger.info("No CRS provided, defaulting to %s", default)
            crs_obj = CRS.from_user_input(default)
            return crs_obj, default

        cleaned = crs_input.strip()
        try:
            crs_obj = CRS.from_user_input(cleaned)
            epsg = crs_obj.to_epsg()
            if epsg:
                norm_str = f"EPSG:{epsg}"
            else:
                norm_str = crs_obj.name or cleaned
            return crs_obj, norm_str
        except Exception as e:
            logger.warning("Failed to parse CRS '%s': %s. Falling back to %s", cleaned, e, default)
            crs_obj = CRS.from_user_input(default)
            return crs_obj, default

    @classmethod
    def get_crs_description(cls, crs: CRS) -> str:
        """Return a human-readable identifier including EPSG code and CRS name."""
        epsg = crs.to_epsg()
        if epsg:
            return f"EPSG:{epsg} ({crs.name})"
        return crs.name or str(crs)

    @classmethod
    def determine_optimal_projected_crs(
        cls, geometry: BaseGeometry, source_crs: CRS
    ) -> tuple[CRS, str]:
        """
        Select an optimal projected metric CRS for accurate planar calculations.
        
        - If source_crs is already projected, return it.
        - If source_crs is geographic (degrees), calculate feature centroid and determine
          the local Universal Transverse Mercator (UTM) zone or UPS (for polar regions).
        """
        if source_crs.is_projected:
            return source_crs, cls.get_crs_description(source_crs)

        # Geometry is geographic; first ensure we have centroid in WGS84 (lon, lat)
        geom_wgs84 = geometry
        if source_crs != WGS84_CRS:
            transformer = Transformer.from_crs(source_crs, WGS84_CRS, always_xy=True)
            geom_wgs84 = cls.transform_geometry_with_transformer(geometry, transformer)

        try:
            centroid = geom_wgs84.centroid
            lon = float(centroid.x)
            lat = float(centroid.y)
        except Exception:
            # Fallback to bounds if centroid fails
            minx, miny, maxx, maxy = geom_wgs84.bounds
            lon = (minx + maxx) / 2.0
            lat = (miny + maxy) / 2.0

        # Polar regions handling (Universal Polar Stereographic)
        if lat > 84.0:
            ups_crs = CRS.from_epsg(32661)  # WGS 84 / UPS North
            return ups_crs, "EPSG:32661 (WGS 84 / UPS North)"
        if lat < -80.0:
            ups_crs = CRS.from_epsg(32761)  # WGS 84 / UPS South
            return ups_crs, "EPSG:32761 (WGS 84 / UPS South)"

        # Normalization for longitude [-180, 180]
        lon_clamped = max(-180.0, min(179.999999, lon))
        lat_clamped = max(-80.0, min(84.0, lat))

        # Query optimal UTM zone from pyproj database
        try:
            utm_list = query_utm_crs_info(
                datum_name="WGS 84",
                area_of_interest=AreaOfInterest(
                    west_lon_degree=lon_clamped - 0.01,
                    south_lat_degree=lat_clamped - 0.01,
                    east_lon_degree=lon_clamped + 0.01,
                    north_lat_degree=lat_clamped + 0.01,
                ),
            )
            if utm_list:
                proj_crs = CRS.from_epsg(utm_list[0].code)
                return proj_crs, f"EPSG:{utm_list[0].code} ({proj_crs.name})"
        except Exception as e:
            logger.debug("Database UTM query failed: %s; falling back to formula", e)

        # Standard mathematical UTM zone calculation
        zone = int((lon_clamped + 180.0) / 6.0) + 1
        zone = max(1, min(60, zone))
        epsg = 32600 + zone if lat >= 0 else 32700 + zone
        proj_crs = CRS.from_epsg(epsg)
        hemisphere = "N" if lat >= 0 else "S"
        label = f"EPSG:{epsg} (WGS 84 / UTM zone {zone}{hemisphere})"
        return proj_crs, label

    @staticmethod
    def transform_geometry_with_transformer(
        geom: BaseGeometry, transformer: Transformer
    ) -> BaseGeometry:
        """Vectorized transform of coordinates using Shapely 2.0 and PyProj Transformer."""
        def _project_coords(coords):
            x, y = transformer.transform(coords[:, 0], coords[:, 1])
            if coords.shape[1] > 2:
                return np.column_stack((x, y, coords[:, 2:]))
            return np.column_stack((x, y))

        return shapely.transform(geom, _project_coords)

    @classmethod
    def transform_to_crs(
        cls, geom: BaseGeometry, source_crs: CRS, target_crs: CRS
    ) -> BaseGeometry:
        """Transform a geometry between two Coordinate Reference Systems."""
        if source_crs == target_crs:
            return geom
        transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
        return cls.transform_geometry_with_transformer(geom, transformer)

    @classmethod
    def calculate_geodesic_measurements(
        cls, geom: BaseGeometry, source_crs: CRS
    ) -> GeodesicMeasurement:
        """
        Calculate true ellipsoidal geodesic measurements using WGS84 ellipsoid.
        Transforms to EPSG:4326 if geometry is in another CRS.
        """
        try:
            if geom.is_empty:
                return GeodesicMeasurement()

            geom_wgs84 = geom
            if source_crs != WGS84_CRS:
                transformer = Transformer.from_crs(source_crs, WGS84_CRS, always_xy=True)
                geom_wgs84 = cls.transform_geometry_with_transformer(geom, transformer)

            geom_type = geom_wgs84.geom_type

            if geom_type in ("Polygon", "MultiPolygon"):
                # Geod computes area in square meters and perimeter in meters
                area, _ = WGS84_GEOD.geometry_area_perimeter(geom_wgs84)
                return GeodesicMeasurement(geodesic_area_sq_meters=round(abs(area), 4))

            if geom_type in ("LineString", "MultiLineString"):
                length = WGS84_GEOD.geometry_length(geom_wgs84)
                return GeodesicMeasurement(geodesic_length_meters=round(abs(length), 4))

            return GeodesicMeasurement()
        except Exception as e:
            logger.warning("Geodesic measurement calculation failed: %s", e)
            return GeodesicMeasurement()
