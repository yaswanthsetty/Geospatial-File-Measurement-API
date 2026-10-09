import logging
from pathlib import Path
import re
from typing import Any, Optional
from xml.etree.ElementTree import Element
import defusedxml.ElementTree as ET
import pyproj
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    mapping,
)
from shapely.geometry.base import BaseGeometry

from app.core.exceptions import InvalidFileError
from app.services.crs_service import CRSService

logger = logging.getLogger(__name__)


def _strip_ns(tag: str) -> str:
    """Helper to remove XML namespace prefix from tag."""
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_coordinates(coord_str: str) -> list[tuple[float, float]]:
    """
    Parses KML coordinate text into list of (lon, lat) tuples.
    KML format: lon,lat[,altitude] separated by whitespace.
    """
    coords: list[tuple[float, float]] = []
    # Split by whitespace, newline, tab
    tokens = re.split(r"\s+", coord_str.strip())
    for token in tokens:
        if not token:
            continue
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lon = float(parts[0].strip())
                lat = float(parts[1].strip())
                coords.append((lon, lat))
            except ValueError:
                continue
    return coords


class KMLParser:
    @classmethod
    def parse_kml(
        cls, kml_path: Path
    ) -> tuple[list[dict[str, Any]], list[BaseGeometry], pyproj.CRS, str]:
        """
        Parses a KML file into feature records and Shapely geometry objects.
        KML specification natively uses WGS84 geographic coordinates (EPSG:4326).
        """
        try:
            tree = ET.parse(str(kml_path))
            root = tree.getroot()
        except Exception as e:
            logger.error("Failed to parse KML XML tree: %s", e)
            raise InvalidFileError(f"Malformed or invalid KML file: {e}")

        crs_obj, crs_str = CRSService.parse_crs("EPSG:4326")
        features: list[dict[str, Any]] = []
        shapely_geoms: list[BaseGeometry] = []

        # Find all Placemark elements anywhere in the tree
        placemarks = [elem for elem in root.iter() if _strip_ns(elem.tag) == "Placemark"]

        for idx, pm in enumerate(placemarks):
            feature_id = pm.attrib.get("id") or f"feature_{idx + 1}"
            properties: dict[str, Any] = {}

            # Extract basic tags: name, description, snippet
            for child in pm:
                tag = _strip_ns(child.tag)
                if tag == "name" and child.text:
                    properties["name"] = child.text.strip()
                elif tag == "description" and child.text:
                    properties["description"] = child.text.strip()
                elif tag in ("Snippet", "snippet") and child.text:
                    properties["snippet"] = child.text.strip()
                elif tag == "ExtendedData":
                    ext_props = cls._parse_extended_data(child)
                    properties.update(ext_props)

            # If name was provided and id was default, use name if distinct
            if "name" in properties and not pm.attrib.get("id"):
                feature_id = properties["name"]

            # Parse Geometry inside Placemark
            geom = cls._parse_geometry(pm)
            if geom is None or geom.is_empty:
                logger.debug("Placemark %s has no valid geometry", feature_id)
                continue

            feature_entry = {
                "feature_id": feature_id,
                "geometry_type": geom.geom_type,
                "geometry": mapping(geom),
                "crs": crs_str,
                "properties": properties,
            }

            features.append(feature_entry)
            shapely_geoms.append(geom)

        return features, shapely_geoms, crs_obj, crs_str

    @classmethod
    def _parse_extended_data(cls, ext_elem: Element) -> dict[str, Any]:
        """Extract key-value pairs from KML <ExtendedData>."""
        props: dict[str, Any] = {}
        for child in ext_elem:
            tag = _strip_ns(child.tag)
            # <Data name="foo"><value>bar</value></Data>
            if tag == "Data":
                name = child.attrib.get("name")
                if name:
                    val_elem = next((c for c in child if _strip_ns(c.tag) == "value"), None)
                    props[name] = val_elem.text.strip() if val_elem is not None and val_elem.text else ""
            # <SchemaData><SimpleData name="foo">bar</SimpleData></SchemaData>
            elif tag == "SchemaData":
                for simple in child:
                    if _strip_ns(simple.tag) == "SimpleData":
                        s_name = simple.attrib.get("name")
                        if s_name:
                            props[s_name] = simple.text.strip() if simple.text else ""
        return props

    @classmethod
    def _parse_geometry(cls, parent_elem: Element) -> Optional[BaseGeometry]:
        """Finds and parses any geometry tag under parent_elem."""
        for child in parent_elem:
            tag = _strip_ns(child.tag)
            if tag == "Polygon":
                return cls._parse_polygon(child)
            if tag == "LineString":
                return cls._parse_linestring(child)
            if tag == "Point":
                return cls._parse_point(child)
            if tag == "MultiGeometry":
                return cls._parse_multigeometry(child)
        return None

    @classmethod
    def _parse_polygon(cls, poly_elem: Element) -> Optional[Polygon]:
        """Parses <Polygon> with optional inner rings (holes)."""
        exterior_coords: list[tuple[float, float]] = []
        interior_rings: list[list[tuple[float, float]]] = []

        for child in poly_elem:
            tag = _strip_ns(child.tag)
            if tag == "outerBoundaryIs":
                for sub in child:
                    if _strip_ns(sub.tag) == "LinearRing":
                        for c in sub:
                            if _strip_ns(c.tag) == "coordinates" and c.text:
                                exterior_coords = _parse_coordinates(c.text)
            elif tag == "innerBoundaryIs":
                for sub in child:
                    if _strip_ns(sub.tag) == "LinearRing":
                        for c in sub:
                            if _strip_ns(c.tag) == "coordinates" and c.text:
                                hole_coords = _parse_coordinates(c.text)
                                if len(hole_coords) >= 3:
                                    interior_rings.append(hole_coords)

        if len(exterior_coords) >= 3:
            # Ensure ring is closed
            if exterior_coords[0] != exterior_coords[-1]:
                exterior_coords.append(exterior_coords[0])
            return Polygon(exterior_coords, interior_rings)
        return None

    @classmethod
    def _parse_linestring(cls, line_elem: Element) -> Optional[LineString]:
        """Parses <LineString>."""
        for child in line_elem:
            if _strip_ns(child.tag) == "coordinates" and child.text:
                coords = _parse_coordinates(child.text)
                if len(coords) >= 2:
                    return LineString(coords)
        return None

    @classmethod
    def _parse_point(cls, pt_elem: Element) -> Optional[Point]:
        """Parses <Point>."""
        for child in pt_elem:
            if _strip_ns(child.tag) == "coordinates" and child.text:
                coords = _parse_coordinates(child.text)
                if coords:
                    return Point(coords[0])
        return None

    @classmethod
    def _parse_multigeometry(cls, multi_elem: Element) -> Optional[BaseGeometry]:
        """Parses <MultiGeometry> containing multiple geometries."""
        geoms: list[BaseGeometry] = []
        for child in multi_elem:
            g = cls._parse_geometry_element(child)
            if g is not None and not g.is_empty:
                geoms.append(g)

        if not geoms:
            return None

        # Check homogeneous types
        all_polys = all(isinstance(g, (Polygon, MultiPolygon)) for g in geoms)
        if all_polys:
            flat_polys = []
            for g in geoms:
                if isinstance(g, Polygon):
                    flat_polys.append(g)
                elif isinstance(g, MultiPolygon):
                    flat_polys.extend(g.geoms)
            return MultiPolygon(flat_polys)

        all_lines = all(isinstance(g, (LineString, MultiLineString)) for g in geoms)
        if all_lines:
            flat_lines = []
            for g in geoms:
                if isinstance(g, LineString):
                    flat_lines.append(g)
                elif isinstance(g, MultiLineString):
                    flat_lines.extend(g.geoms)
            return MultiLineString(flat_lines)

        all_points = all(isinstance(g, (Point, MultiPoint)) for g in geoms)
        if all_points:
            flat_points = []
            for g in geoms:
                if isinstance(g, Point):
                    flat_points.append(g)
                elif isinstance(g, MultiPoint):
                    flat_points.extend(g.geoms)
            return MultiPoint(flat_points)

        return GeometryCollection(geoms)

    @classmethod
    def _parse_geometry_element(cls, elem: Element) -> Optional[BaseGeometry]:
        """Helper to parse a single geometry element by tag."""
        tag = _strip_ns(elem.tag)
        if tag == "Polygon":
            return cls._parse_polygon(elem)
        if tag == "LineString":
            return cls._parse_linestring(elem)
        if tag == "Point":
            return cls._parse_point(elem)
        if tag == "MultiGeometry":
            return cls._parse_multigeometry(elem)
        return None
