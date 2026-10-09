import shutil
import zipfile
from pathlib import Path

import pyproj
import shapefile

samples_dir = Path("samples")
samples_dir.mkdir(exist_ok=True)

# 1. sample_polygon.kml
kml_polygon = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Sample Parks</name>
    <Placemark id="park_1">
      <name>Golden Gate Park Demo Parcel</name>
      <description>Urban park parcel in San Francisco, CA</description>
      <ExtendedData>
        <Data name="zone"><value>Recreational</value></Data>
        <Data name="jurisdiction"><value>San Francisco</value></Data>
      </ExtendedData>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              -122.4862,37.7694,0
              -122.4530,37.7712,0
              -122.4542,37.7665,0
              -122.4875,37.7648,0
              -122.4862,37.7694,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>"""
(samples_dir / "sample_polygon.kml").write_text(kml_polygon, encoding="utf-8")

# 2. sample_linestring.kml
kml_linestring = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Sample Route</name>
    <Placemark id="route_101">
      <name>Bridge Crossing Route</name>
      <description>Scenic route across Golden Gate Strait</description>
      <ExtendedData>
        <Data name="route_type"><value>Pedestrian / Bike</value></Data>
        <Data name="speed_limit_mph"><value>15</value></Data>
      </ExtendedData>
      <LineString>
        <coordinates>
          -122.4786,37.8100,0
          -122.4784,37.8197,0
          -122.4795,37.8280,0
          -122.4832,37.8324,0
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>"""
(samples_dir / "sample_linestring.kml").write_text(kml_linestring, encoding="utf-8")

# 3. sample_mixed.kml
kml_mixed = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Mixed Survey Features</name>
    <Placemark id="boundary_poly">
      <name>District Campus</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.590,12.970,0
              77.600,12.970,0
              77.600,12.980,0
              77.590,12.980,0
              77.590,12.970,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark id="access_road">
      <name>Campus Main Avenue</name>
      <LineString>
        <coordinates>
          77.590,12.975,0
          77.595,12.975,0
          77.600,12.978,0
        </coordinates>
      </LineString>
    </Placemark>
    <Placemark id="entrance_gate">
      <name>North Security Gate</name>
      <Point>
        <coordinates>77.595,12.980,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""
(samples_dir / "sample_mixed.kml").write_text(kml_mixed, encoding="utf-8")

# 4. sample_parcels.zip
temp_shp = samples_dir / "_temp_shp"
temp_shp.mkdir(exist_ok=True)
shp_base = temp_shp / "parcels"

w = shapefile.Writer(str(shp_base))
w.field("parcel_id", "C", size=20)
w.field("owner", "C", size=50)
w.field("zoning", "C", size=20)

# Parcel 1
w.poly(
    [
        [
            [77.580, 12.960],
            [77.585, 12.960],
            [77.585, 12.965],
            [77.580, 12.965],
            [77.580, 12.960],
        ]
    ]
)
w.record("P-101", "Acme Corp", "Commercial")

# Parcel 2
w.poly(
    [
        [
            [77.585, 12.960],
            [77.590, 12.960],
            [77.590, 12.965],
            [77.585, 12.965],
            [77.585, 12.960],
        ]
    ]
)
w.record("P-102", "City Housing", "Residential")
w.close()

crs_4326 = pyproj.CRS.from_epsg(4326)
(temp_shp / "parcels.prj").write_text(crs_4326.to_wkt(), encoding="utf-8")

zip_path = samples_dir / "sample_parcels.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for f in temp_shp.glob("parcels.*"):
        z.write(f, arcname=f.name)

shutil.rmtree(temp_shp)

# 5. sample_projected_parcels.zip (UTM Zone 43N - EPSG:32643)
temp_utm = samples_dir / "_temp_utm"
temp_utm.mkdir(exist_ok=True)
utm_base = temp_utm / "utm_parcels"

w_utm = shapefile.Writer(str(utm_base))
w_utm.field("lot_num", "N")
w_utm.field("code", "C", size=10)
# Planar coordinates in meters (approx 500m x 500m = 250,000 m2)
w_utm.poly(
    [
        [
            [780000, 1434000],
            [780500, 1434000],
            [780500, 1434500],
            [780000, 1434500],
            [780000, 1434000],
        ]
    ]
)
w_utm.record(1, "LOT-A")
w_utm.close()

crs_utm = pyproj.CRS.from_epsg(32643)
(temp_utm / "utm_parcels.prj").write_text(crs_utm.to_wkt(), encoding="utf-8")

utm_zip_path = samples_dir / "sample_projected_parcels.zip"
with zipfile.ZipFile(utm_zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for f in temp_utm.glob("utm_parcels.*"):
        z.write(f, arcname=f.name)

shutil.rmtree(temp_utm)
print("Successfully generated all sample datasets in samples/ folder!")
