from pyspark.sql import functions as F
from common import get_sedona

sedona = get_sedona("boundary-test")

# Read the entire GeoJSON file as one record.
raw = sedona.read.text(
    "file:///data/staging/maharashtra_boundary.geojson"
).agg(
    F.concat_ws("", F.collect_list("value")).alias("geojson")
)

# Extract the first feature's geometry.
boundary = raw.select(
    F.get_json_object(
        "geojson", "$.features[0].geometry"
    ).alias("geometry")
).where(
    F.col("geometry").isNotNull()
)

boundary.createOrReplaceTempView("boundary_json")

result = sedona.sql("""
    SELECT
        ST_GeometryType(ST_GeomFromGeoJSON(geometry)) AS geometry_type,
        ST_IsValid(ST_GeomFromGeoJSON(geometry)) AS is_valid,
        ST_Contains(
            ST_GeomFromGeoJSON(geometry),
            ST_Point(75.0, 19.0)
        ) AS test_point_inside
    FROM boundary_json
""")

result.show(truncate=False)

sedona.stop()
