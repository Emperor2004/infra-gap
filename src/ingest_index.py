"""Stage 1: buildings, population and facilities -> H3 hexagon table and facility table."""
from pyspark.sql import functions as F

from common import get_sedona, timed
from config import H3_RES, p

sedona = get_sedona("ingest-index")

# ---------- hexagon table ----------
with timed(sedona, "ingest", "hex_table"):
    raw = sedona.read.option("recursiveFileLookup", "true").text(p("raw", "buildings"))
    geo = raw.select(F.get_json_object("value", "$.geometry").alias("gj"))

    sample = geo.limit(2000)
    n_ok, n = sample.where("gj IS NOT NULL").count(), sample.count()
    print(f"geometry parsed for {n_ok}/{n} sampled building lines")
    assert n > 0 and n_ok / n > 0.9, "Building lines are not GeoJSON features. Inspect a tile with: zcat <file> | head -2"

    buildings = (geo.where("gj IS NOT NULL")
                 .selectExpr(f"ST_H3CellIDs(ST_Centroid(ST_GeomFromGeoJSON(gj)), {H3_RES}, false)[0] AS h3")
                 .groupBy("h3").agg(F.count("*").alias("n_buildings")))

    population = (sedona.read.parquet(p("staging", "pop_points"))
                  .selectExpr(f"ST_H3CellIDs(ST_Point(lon, lat), {H3_RES}, false)[0] AS h3", "pop")
                  .groupBy("h3").agg(F.sum("pop").alias("pop")))

    hexes = (buildings.join(population, "h3", "full_outer")
             .fillna({"n_buildings": 0, "pop": 0.0})
             .where("n_buildings > 0 OR pop > 0"))
    hexes.createOrReplaceTempView("h")

    out = sedona.sql("""
        SELECT h3, n_buildings, pop,
               ST_X(ST_Centroid(ST_H3ToGeom(array(h3))[0])) AS lon,
               ST_Y(ST_Centroid(ST_H3ToGeom(array(h3))[0])) AS lat
        FROM h""")
    out.write.mode("overwrite").parquet(p("out", "hex"))

hex_df = sedona.read.parquet(p("out", "hex"))
hex_df.agg(F.count("*").alias("hexagons"), F.sum("n_buildings").alias("buildings"),
           F.sum("pop").alias("population")).show(truncate=False)
hex_df.orderBy(F.desc("pop")).show(8, truncate=False)

# ---------- facilities ----------
with timed(sedona, "ingest", "facilities"):
    fac = sedona.read.text(p("staging", "facilities"))
    fac = fac.select(
        F.get_json_object("value", "$.properties.amenity").alias("amenity"),
        F.get_json_object("value", "$.properties.healthcare").alias("healthcare"),
        F.get_json_object("value", "$.geometry").alias("gj"),
    ).where("gj IS NOT NULL")
    fac = (fac.withColumn(
        "facility_type",
        F.when((F.col("amenity") == "hospital") | (F.col("healthcare") == "hospital"), "hospital")
         .when(F.col("amenity") == "school", "school")
         .when(F.col("amenity") == "drinking_water", "drinking_water"))
           .where("facility_type IS NOT NULL"))
    fac.createOrReplaceTempView("f")
    sedona.sql("""
        SELECT facility_type,
               ST_X(ST_Centroid(ST_GeomFromGeoJSON(gj))) AS lon,
               ST_Y(ST_Centroid(ST_GeomFromGeoJSON(gj))) AS lat
        FROM f""").write.mode("overwrite").parquet(p("out", "facilities"))

sedona.read.parquet(p("out", "facilities")).groupBy("facility_type").count().show()