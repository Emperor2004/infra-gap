"""Stage 3: roll hexagon severity up to talukas and districts."""
import argparse

from common import get_sedona, timed
from config import p

ap = argparse.ArgumentParser()
ap.add_argument("--tag", default="base")
a = ap.parse_args()

sedona = get_sedona(f"rollup-{a.tag}")

sedona.read.parquet(p("staging", "talukas.parquet")).selectExpr(
    "district", "taluka", "ST_GeomFromWKT(wkt) AS geom").createOrReplaceTempView("t")
sedona.read.parquet(p("out", f"severity_{a.tag}")).selectExpr(
    "pop", "severity", "ST_Point(lon, lat) AS ctr").createOrReplaceTempView("s")

with timed(sedona, "rollup", "taluka_district"):
    taluka = sedona.sql("""
        SELECT t.district, t.taluka, SUM(s.pop) AS population, SUM(s.severity) AS total_severity,
               SUM(s.severity) / SUM(s.pop) AS severity_per_person
        FROM s JOIN t ON ST_Within(s.ctr, t.geom)
        GROUP BY t.district, t.taluka""")
    taluka.write.mode("overwrite").parquet(p("out", f"taluka_{a.tag}"))

    district = sedona.sql("""
        SELECT t.district, SUM(s.pop) AS population, SUM(s.severity) AS total_severity,
               SUM(s.severity) / SUM(s.pop) AS severity_per_person
        FROM s JOIN t ON ST_Within(s.ctr, t.geom)
        GROUP BY t.district""")
    district.write.mode("overwrite").parquet(p("out", f"district_{a.tag}"))

sedona.read.parquet(p("out", f"taluka_{a.tag}")).orderBy("severity_per_person", ascending=False).show(20, truncate=False)
sedona.read.parquet(p("out", f"district_{a.tag}")).orderBy("severity_per_person", ascending=False).show(10, truncate=False)