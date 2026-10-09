from pathlib import Path
import pytest

from app.core.exceptions import InvalidFileError
from app.services.parsers.kml_parser import KMLParser
from app.services.parsers.shapefile_parser import ShapefileParser

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


def test_parse_kml_polygon():
    kml_path = SAMPLES_DIR / "sample_polygon.kml"
    features, geoms, crs_obj, crs_str = KMLParser.parse_kml(kml_path)

    assert len(features) == 1
    assert features[0]["feature_id"] == "park_1"
    assert features[0]["geometry_type"] == "Polygon"
    assert features[0]["properties"]["name"] == "Golden Gate Park Demo Parcel"
    assert features[0]["properties"]["zone"] == "Recreational"
    assert crs_str == "EPSG:4326"
    assert geoms[0].geom_type == "Polygon"


def test_parse_kml_linestring():
    kml_path = SAMPLES_DIR / "sample_linestring.kml"
    features, geoms, crs_obj, crs_str = KMLParser.parse_kml(kml_path)

    assert len(features) == 1
    assert features[0]["feature_id"] == "route_101"
    assert features[0]["geometry_type"] == "LineString"
    assert features[0]["properties"]["route_type"] == "Pedestrian / Bike"
    assert crs_str == "EPSG:4326"


def test_parse_kml_mixed():
    kml_path = SAMPLES_DIR / "sample_mixed.kml"
    features, geoms, crs_obj, crs_str = KMLParser.parse_kml(kml_path)

    assert len(features) == 3
    types = [f["geometry_type"] for f in features]
    assert "Polygon" in types
    assert "LineString" in types
    assert "Point" in types


def test_parse_kml_invalid_xml(tmp_path):
    bad_kml = tmp_path / "bad.kml"
    bad_kml.write_text("<unclosed_xml>", encoding="utf-8")
    with pytest.raises(InvalidFileError) as exc_info:
        KMLParser.parse_kml(bad_kml)
    assert "Malformed or invalid KML" in str(exc_info.value)


def test_parse_shapefile_zip():
    zip_path = SAMPLES_DIR / "sample_parcels.zip"
    features, geoms, crs_obj, crs_str = ShapefileParser.parse_zip(zip_path)

    assert len(features) == 2
    assert features[0]["geometry_type"] == "Polygon"
    assert features[0]["properties"]["parcel_id"] == "P-101"
    assert features[1]["properties"]["parcel_id"] == "P-102"
    assert crs_str == "EPSG:4326"


def test_parse_projected_shapefile_zip():
    zip_path = SAMPLES_DIR / "sample_projected_parcels.zip"
    features, geoms, crs_obj, crs_str = ShapefileParser.parse_zip(zip_path)

    assert len(features) == 1
    assert features[0]["geometry_type"] == "Polygon"
    assert features[0]["properties"]["code"] == "LOT-A"
    assert "32643" in crs_str


def test_parse_shapefile_zip_without_shp(tmp_path):
    import zipfile
    bad_zip = tmp_path / "empty.zip"
    with zipfile.ZipFile(bad_zip, "w") as z:
        z.writestr("readme.txt", "no shapefile here")

    with pytest.raises(InvalidFileError) as exc_info:
        ShapefileParser.parse_zip(bad_zip)
    assert "does not contain a valid .shp shapefile" in str(exc_info.value)


def test_parse_shapefile_non_zip(tmp_path):
    fake_zip = tmp_path / "fake.zip"
    fake_zip.write_text("not a zip file", encoding="utf-8")
    with pytest.raises(InvalidFileError) as exc_info:
        ShapefileParser.parse_zip(fake_zip)
    assert "not a valid zip archive" in str(exc_info.value)
