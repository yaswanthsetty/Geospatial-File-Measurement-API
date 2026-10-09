from pyproj import CRS
import pytest
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon

from app.models.schemas import MeasurementStatus, MeasurementType
from app.services.measurement_service import MeasurementService


def test_polygon_measurement():
    source_crs = CRS.from_epsg(4326)
    # A rectangle in Bangalore: ~1.1 km by 1.1 km (~1.2 sq km)
    poly = Polygon([(77.58, 12.96), (77.59, 12.96), (77.59, 12.97), (77.58, 12.97), (77.58, 12.96)])
    
    result = MeasurementService.calculate_feature_measurement(
        feature_id="poly_1",
        geometry=poly,
        source_crs=source_crs,
        source_crs_str="EPSG:4326",
        properties={"name": "Test Parcel"},
    )

    assert result.supported is True
    assert result.status == MeasurementStatus.SUCCESS
    assert result.measurement_type == MeasurementType.AREA
    assert result.area is not None
    assert result.area.area_sq_meters > 1_000_000
    assert result.area.area_sq_kilometers > 1.0
    assert result.area.area_hectares > 100
    assert result.area.area_acres > 200
    assert result.area.perimeter_meters is not None
    assert result.area.perimeter_meters > 4000
    assert result.projected_crs is not None
    assert "32643" in result.projected_crs


def test_linestring_measurement():
    source_crs = CRS.from_epsg(4326)
    # ~1.1 km line
    line = LineString([(77.58, 12.96), (77.59, 12.96)])
    
    result = MeasurementService.calculate_feature_measurement(
        feature_id="line_1",
        geometry=line,
        source_crs=source_crs,
        source_crs_str="EPSG:4326",
    )

    assert result.supported is True
    assert result.status == MeasurementStatus.SUCCESS
    assert result.measurement_type == MeasurementType.LENGTH
    assert result.length is not None
    assert 1000 < result.length.length_meters < 1200
    assert 1.0 < result.length.length_kilometers < 1.2
    assert result.length.length_miles > 0.6


def test_point_measurement_skipped_gracefully():
    source_crs = CRS.from_epsg(4326)
    pt = Point(77.58, 12.96)
    
    result = MeasurementService.calculate_feature_measurement(
        feature_id="pt_1",
        geometry=pt,
        source_crs=source_crs,
        source_crs_str="EPSG:4326",
    )

    assert result.supported is False
    assert result.status == MeasurementStatus.SKIPPED_UNSUPPORTED
    assert result.measurement_type == MeasurementType.NONE
    assert result.area is None
    assert result.length is None
    assert "Points do not have area or length measurements" in result.message


def test_empty_geometry_handling():
    source_crs = CRS.from_epsg(4326)
    poly = Polygon()
    
    result = MeasurementService.calculate_feature_measurement(
        feature_id="empty_1",
        geometry=poly,
        source_crs=source_crs,
        source_crs_str="EPSG:4326",
    )

    assert result.supported is False
    assert result.status == MeasurementStatus.WARNING


def test_geometry_collection_handling():
    source_crs = CRS.from_epsg(4326)
    poly = Polygon([(77.58, 12.96), (77.59, 12.96), (77.59, 12.97), (77.58, 12.97)])
    line = LineString([(77.58, 12.96), (77.59, 12.96)])
    gc = GeometryCollection([poly, line])

    result = MeasurementService.calculate_feature_measurement(
        feature_id="gc_1",
        geometry=gc,
        source_crs=source_crs,
        source_crs_str="EPSG:4326",
    )

    assert result.supported is True
    assert result.status == MeasurementStatus.SUCCESS
    assert result.area is not None
    assert result.length is not None


def test_summarize_measurements():
    source_crs = CRS.from_epsg(4326)
    poly = Polygon([(77.58, 12.96), (77.59, 12.96), (77.59, 12.97), (77.58, 12.97)])
    line = LineString([(77.58, 12.96), (77.59, 12.96)])
    pt = Point(77.58, 12.96)

    m1 = MeasurementService.calculate_feature_measurement("p", poly, source_crs, "EPSG:4326")
    m2 = MeasurementService.calculate_feature_measurement("l", line, source_crs, "EPSG:4326")
    m3 = MeasurementService.calculate_feature_measurement("pt", pt, source_crs, "EPSG:4326")

    summary = MeasurementService.summarize_measurements([m1, m2, m3])
    assert summary.total_features == 3
    assert summary.measured_features == 2
    assert summary.skipped_features == 1
    assert summary.total_area_sq_meters > 0
    assert summary.total_length_meters > 0
