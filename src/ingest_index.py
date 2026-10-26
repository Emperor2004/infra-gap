"""Stage 1: Build Maharashtra-only H3 cells and facility tables."""

import json

from pyspark.sql import functions as F

from common import get_sedona, timed
from config import H3_RES, p

sedona = get_sedona("ingest-index")


def spark_path(*parts):
    """Return an HDFS URI for distributed input/output."""
    suffix = "/".join(str(part).strip("/") for part in parts)
    return f"hdfs://h-primary:9000/data/{suffix}"


# ---------------------------------------------------------
# 1. Load the Maharashtra state boundary
# ---------------------------------------------------------
boundary_path = spark_path("staging", "maharashtra_boundary.geojson")

# Parse the small FeatureCollection from HDFS on the driver.
# This avoids requiring the boundary file to exist on every VM.
import subprocess

boundary_text = subprocess.check_output(
    ["hdfs", "dfs", "-cat", boundary_path],
    text=True,
)
boundary_document = json.loads(boundary_text)

features = boundary_document.get("features", [])

if not features or not features[0].get("geometry"):
    raise RuntimeError(
        f"No geometry found in boundary file: {boundary_path}"
    )

boundary_geometry_json = json.dumps(features[0]["geometry"])

boundary_geo = sedona.createDataFrame(
    [(boundary_geometry_json,)],
    ["geometry"],
)

boundary = boundary_geo.select(
    F.expr("ST_GeomFromGeoJSON(geometry)").alias("geom")
)

boundary.createOrReplaceTempView("maharashtra_boundary")

boundary_check = boundary.selectExpr(
    "ST_IsValid(geom) AS is_valid",
    "ST_GeometryType(geom) AS geometry_type",
)

boundary_check.show(truncate=False)

if boundary_check.first()["is_valid"] is not True:
    raise RuntimeError("Maharashtra boundary geometry is invalid.")


# ---------------------------------------------------------
# 2. Read preprocessed Maharashtra building footprints
# ---------------------------------------------------------
with timed(sedona, "ingest", "hex_table"):

    raw = sedona.read.text(
        spark_path(
            "processed",
            "buildings",
            "buildings_maharashtra.geojsonl",
        )
    )

    geo = raw.select(
        F.get_json_object("value", "$.geometry").alias("gj")
    ).where("gj IS NOT NULL")

    # Check a small sample before processing the full dataset.
    sample = geo.limit(2000)
    n = sample.count()

    if n == 0:
        raise RuntimeError("No building geometries were found.")

    n_ok = sample.where(
        F.expr("ST_GeomFromGeoJSON(gj) IS NOT NULL")
    ).count()

    print(f"Building geometries successfully parsed: {n_ok}/{n}")

    if n_ok != n:
        raise RuntimeError(
            f"Some sampled building geometries failed to parse: {n_ok}/{n}"
        )

    # Parse geometries and aggregate directly to H3.
    # Avoid a separate full-dataset count and large geometry cache.
    buildings_geometry = geo.select(
        F.expr("ST_GeomFromGeoJSON(gj)").alias("geom")
    ).where("geom IS NOT NULL")

    buildings_geometry.createOrReplaceTempView("buildings_geometry")

    buildings = sedona.sql(f"""
        SELECT
            ST_H3CellIDs(ST_Centroid(geom), {H3_RES}, false)[0] AS h3
        FROM buildings_geometry
    """).where("h3 IS NOT NULL").groupBy("h3").agg(
        F.count("*").alias("n_buildings")
    )

# Read only the Maharashtra-filtered population dataset.
    population = (
        sedona.read.parquet(
            spark_path(
                "staging",
                "pop_points",
                "pop_points_maharashtra.parquet",
            )
        )
        .selectExpr(
            f"ST_H3CellIDs(ST_Point(lon, lat), {H3_RES}, false)[0] AS h3",
            "pop",
        )
        .groupBy("h3")
        .agg(F.sum("pop").alias("pop"))
    )

    hexes = (
        buildings.join(population, "h3", "full_outer")
        .fillna({"n_buildings": 0, "pop": 0.0})
        .where("n_buildings > 0 OR pop > 0")
    )

    hexes.createOrReplaceTempView("h")

    out = sedona.sql("""
        SELECT
            h3,
            n_buildings,
            pop,
            ST_X(ST_Centroid(ST_H3ToGeom(array(h3))[0])) AS lon,
            ST_Y(ST_Centroid(ST_H3ToGeom(array(h3))[0])) AS lat
        FROM h
    """)

    out.write.mode("overwrite").parquet(
        spark_path("out", "hex")
    )


# ---------------------------------------------------------
# 3. Summarize the generated H3 table
# ---------------------------------------------------------
hex_df = sedona.read.parquet(
    spark_path("out", "hex")
)

hex_df.agg(
    F.count("*").alias("hexagons"),
    F.sum("n_buildings").alias("buildings"),
    F.sum("pop").alias("population"),
).show(truncate=False)

hex_df.orderBy(F.desc("pop")).show(8, truncate=False)


# ---------------------------------------------------------
# 4. Read Maharashtra-filtered facilities only
# ---------------------------------------------------------
with timed(sedona, "ingest", "facilities"):

    fac = sedona.read.text(
        spark_path(
            "staging",
            "facilities",
            "fac_maharashtra_state.geojsonl",
        )
    )

    fac = fac.select(
        F.get_json_object("value", "$.properties.amenity").alias("amenity"),
        F.get_json_object("value", "$.properties.healthcare").alias("healthcare"),
        F.get_json_object("value", "$.geometry").alias("gj"),
    ).where("gj IS NOT NULL")

    fac = (
        fac.withColumn(
            "facility_type",
            F.when(
                (F.col("amenity") == "hospital")
                | (F.col("healthcare") == "hospital"),
                "hospital",
            )
            .when(F.col("amenity") == "school", "school")
            .when(F.col("amenity") == "drinking_water", "drinking_water"),
        )
        .where("facility_type IS NOT NULL")
    )

    fac.createOrReplaceTempView("facility_features")

    facilities_out = sedona.sql("""
        SELECT
            facility_type,
            ST_X(ST_Centroid(ST_GeomFromGeoJSON(gj))) AS lon,
            ST_Y(ST_Centroid(ST_GeomFromGeoJSON(gj))) AS lat
        FROM facility_features
        WHERE ST_GeomFromGeoJSON(gj) IS NOT NULL
    """)

    facilities_out.write.mode("overwrite").parquet(
        spark_path("out", "facilities")
    )


# ---------------------------------------------------------
# 5. Facility summary
# ---------------------------------------------------------
sedona.read.parquet(
    spark_path("out", "facilities")
).groupBy("facility_type").count().show()

sedona.stop()
