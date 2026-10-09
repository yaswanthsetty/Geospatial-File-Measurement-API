from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "endpoints" in data


def test_upload_and_get_kml():
    kml_path = SAMPLES_DIR / "sample_polygon.kml"
    with open(kml_path, "rb") as f:
        response = client.post(
            "/api/files/",
            files={
                "file": (
                    "sample_polygon.kml",
                    f,
                    "application/vnd.google-earth.kml+xml",
                )
            },
        )

    assert response.status_code == 201
    data = response.json()
    file_id = data["id"]
    assert file_id is not None
    assert data["filename"] == "sample_polygon.kml"
    assert data["feature_count"] == 1
    assert data["crs"] == "EPSG:4326"
    assert data["status"] == "COMPLETED"

    # GET /api/files/{id}/
    info_resp = client.get(f"/api/files/{file_id}/")
    assert info_resp.status_code == 200
    info_data = info_resp.json()
    assert info_data["id"] == file_id
    assert info_data["filename"] == "sample_polygon.kml"
    assert info_data["feature_count"] == 1

    # GET /api/files/{id}/measurements/
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    meas_data = meas_resp.json()
    assert meas_data["file_id"] == file_id
    assert meas_data["summary"]["total_features"] == 1
    assert meas_data["summary"]["measured_features"] == 1
    assert len(meas_data["measurements"]) == 1

    feat_meas = meas_data["measurements"][0]
    assert feat_meas["geometry_type"] == "Polygon"
    assert feat_meas["measurement_type"] == "area"
    assert feat_meas["area"]["area_sq_meters"] > 0
    assert feat_meas["area"]["area_hectares"] > 0
    assert feat_meas["projected_crs"] is not None

    # GET /api/files/{id}/features/
    feat_resp = client.get(f"/api/files/{file_id}/features/")
    assert feat_resp.status_code == 200
    feat_data = feat_resp.json()
    assert feat_data["type"] == "FeatureCollection"
    assert len(feat_data["features"]) == 1


def test_upload_shapefile_zip():
    zip_path = SAMPLES_DIR / "sample_parcels.zip"
    with open(zip_path, "rb") as f:
        response = client.post(
            "/api/files/",
            files={"file": ("sample_parcels.zip", f, "application/zip")},
        )

    assert response.status_code == 201
    data = response.json()
    file_id = data["id"]
    assert data["feature_count"] == 2
    assert data["file_type"] == "SHAPEFILE"
    assert data["status"] == "COMPLETED"

    # Check measurements
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    meas_data = meas_resp.json()
    assert meas_data["summary"]["total_features"] == 2
    assert meas_data["summary"]["measured_features"] == 2


def test_upload_invalid_extension():
    response = client.post(
        "/api/files/",
        files={"file": ("test.txt", b"plain text", "text/plain")},
    )
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]


def test_upload_empty_file():
    response = client.post(
        "/api/files/",
        files={"file": ("empty.kml", b"", "application/vnd.google-earth.kml+xml")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_get_non_existent_file():
    response = client.get("/api/files/non_existent_id/")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_delete_file():
    kml_path = SAMPLES_DIR / "sample_linestring.kml"
    with open(kml_path, "rb") as f:
        upload_resp = client.post(
            "/api/files/",
            files={
                "file": (
                    "sample_linestring.kml",
                    f,
                    "application/vnd.google-earth.kml+xml",
                )
            },
        )
    file_id = upload_resp.json()["id"]

    del_resp = client.delete(f"/api/files/{file_id}/")
    assert del_resp.status_code == 200

    # Confirm it's gone
    get_resp = client.get(f"/api/files/{file_id}/")
    assert get_resp.status_code == 404


def test_pagination_measurements_and_files():
    zip_path = SAMPLES_DIR / "sample_parcels.zip"
    with open(zip_path, "rb") as f:
        upload_resp = client.post(
            "/api/files/",
            files={"file": ("sample_parcels.zip", f, "application/zip")},
        )
    file_id = upload_resp.json()["id"]

    # Test limit=1
    meas_resp = client.get(f"/api/files/{file_id}/measurements/?limit=1")
    assert meas_resp.status_code == 200
    meas_data = meas_resp.json()
    assert len(meas_data["measurements"]) == 1
    assert meas_data["summary"]["total_features"] == 2

    # Test offset=1, limit=1
    meas_resp_p2 = client.get(f"/api/files/{file_id}/measurements/?offset=1&limit=1")
    assert meas_resp_p2.status_code == 200
    assert len(meas_resp_p2.json()["measurements"]) == 1

    # Test list_files with pagination
    list_resp = client.get("/api/files/?limit=1")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
