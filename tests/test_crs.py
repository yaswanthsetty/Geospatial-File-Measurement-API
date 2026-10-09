from pyproj import CRS
from shapely.geometry import Polygon

from app.services.crs_service import CRSService


def test_parse_crs_valid_epsg():
    crs_obj, crs_str = CRSService.parse_crs("EPSG:4326")
    assert crs_str == "EPSG:4326"
    assert crs_obj.to_epsg() == 4326


def test_parse_crs_none_fallback():
    crs_obj, crs_str = CRSService.parse_crs(None)
    assert crs_str == "EPSG:4326"
    assert crs_obj.to_epsg() == 4326


def test_parse_crs_invalid_fallback():
    crs_obj, crs_str = CRSService.parse_crs("INVALID_CRS_TEXT")
    assert crs_str == "EPSG:4326"
    assert crs_obj.to_epsg() == 4326


def test_determine_optimal_projected_crs_already_projected():
    proj_crs = CRS.from_epsg(32643)  # UTM Zone 43N
    poly = Polygon(
        [(780000, 1434000), (780500, 1434000), (780500, 1434500), (780000, 1434500)]
    )
    target_crs, label = CRSService.determine_optimal_projected_crs(poly, proj_crs)
    assert target_crs.to_epsg() == 32643
    assert "32643" in label


def test_determine_optimal_projected_crs_india():
    # Bangalore (approx lon 77.59, lat 12.97) -> UTM Zone 43N (EPSG 32643)
    source_crs = CRS.from_epsg(4326)
    poly = Polygon([(77.58, 12.96), (77.60, 12.96), (77.60, 12.98), (77.58, 12.98)])
    target_crs, label = CRSService.determine_optimal_projected_crs(poly, source_crs)
    assert target_crs.to_epsg() == 32643
    assert "43N" in label or "32643" in label


def test_determine_optimal_projected_crs_san_francisco():
    # San Francisco (approx lon -122.42, lat 37.77) -> UTM Zone 10N (EPSG 32610)
    source_crs = CRS.from_epsg(4326)
    poly = Polygon(
        [(-122.45, 37.75), (-122.40, 37.75), (-122.40, 37.80), (-122.45, 37.80)]
    )
    target_crs, label = CRSService.determine_optimal_projected_crs(poly, source_crs)
    assert target_crs.to_epsg() == 32610
    assert "10N" in label or "32610" in label


def test_determine_optimal_projected_crs_southern_hemisphere():
    # Sydney, Australia (approx lon 151.2, lat -33.8) -> UTM Zone 56S (EPSG 32756)
    source_crs = CRS.from_epsg(4326)
    poly = Polygon([(151.1, -33.9), (151.3, -33.9), (151.3, -33.7), (151.1, -33.7)])
    target_crs, label = CRSService.determine_optimal_projected_crs(poly, source_crs)
    assert target_crs.to_epsg() == 32756
    assert "56S" in label or "32756" in label


def test_determine_optimal_projected_crs_polar():
    # Arctic (lat > 84) -> UPS North (EPSG 32661)
    source_crs = CRS.from_epsg(4326)
    poly = Polygon([(10.0, 85.0), (10.1, 85.0), (10.1, 85.1), (10.0, 85.1)])
    target_crs, label = CRSService.determine_optimal_projected_crs(poly, source_crs)
    assert target_crs.to_epsg() == 32661


def test_transform_and_measure():
    # 1 degree square around equator
    # Transform to UTM 31N (0° to 1° E, 0° to 1° N)
    source_crs = CRS.from_epsg(4326)
    poly = Polygon([(0.0, 0.0), (0.1, 0.0), (0.1, 0.1), (0.0, 0.1), (0.0, 0.0)])
    target_crs, _ = CRSService.determine_optimal_projected_crs(poly, source_crs)
    proj_geom = CRSService.transform_to_crs(poly, source_crs, target_crs)

    # 0.1 deg ~ 11.13 km -> Area ~ 11.13 * 11.13 ~ 123.8 sq km = 123,800,000 m2
    assert 120_000_000 < proj_geom.area < 126_000_000

    # Geodesic calculation
    geodesic = CRSService.calculate_geodesic_measurements(poly, source_crs)
    assert geodesic.geodesic_area_sq_meters is not None
    assert 120_000_000 < geodesic.geodesic_area_sq_meters < 126_000_000
