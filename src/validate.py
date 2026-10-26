"""Stage 4: check OSM completeness and false alarms against an official hospital list (staging/official.csv)."""
import argparse

import pandas as pd
from pyspark.sql import functions as F

from common import get_sedona
from config import T, p

def spark_path(*parts):
    """Return an HDFS URI for distributed input/output."""
    suffix = "/".join(str(part).strip("/") for part in parts)
    return f"hdfs://h-primary:9000/data/{suffix}"

ap = argparse.ArgumentParser()
ap.add_argument("--tag", default="base")
ap.add_argument(
    "--official",
    default=spark_path("staging", "official.csv"),
)
ap.add_argument("--top-n", type=int, default=400)
ap.add_argument("--match-m", type=float, default=500)
a = ap.parse_args()

sedona = get_sedona("validate")

official = (sedona.read.csv(a.official, header=True, inferSchema=True)
            .withColumn("oid", F.monotonically_increasing_id())
            .selectExpr("oid", "name", "ST_Point(CAST(lon AS double), CAST(lat AS double)) AS g"))
official.createOrReplaceTempView("official")
sedona.read.parquet(spark_path("out", "facilities")).where("facility_type = 'hospital'").selectExpr("ST_Point(lon, lat) AS g").createOrReplaceTempView("osmh")
sedona.read.parquet(spark_path("staging", "talukas.parquet")).selectExpr("district", "ST_GeomFromWKT(wkt) AS geom").createOrReplaceTempView("t")

# 1. Which official hospitals exist in OSM (within match radius)?
deg_m = a.match_m / 100000.0
sedona.sql(f"""
    SELECT DISTINCT o.oid FROM official o JOIN osmh m ON ST_Distance(o.g, m.g) <= {deg_m}
    WHERE ST_DistanceSphere(o.g, m.g) <= {a.match_m}""").createOrReplaceTempView("matched")
n_off = official.count()
n_match = sedona.sql("SELECT COUNT(*) AS c FROM matched").first()["c"]
print(f"official hospitals: {n_off}, found in OSM within {a.match_m:.0f} m: {n_match} ({100 * n_match / max(n_off, 1):.1f}%)")

by_district = sedona.sql("""
    WITH assigned AS (
        SELECT
            o.oid,
            t.district
        FROM official o
        LEFT JOIN t
            ON ST_Within(o.g, t.geom)
    )
    SELECT
        COALESCE(district, 'UNASSIGNED') AS district,
        COUNT(DISTINCT assigned.oid) AS official_total,
        COUNT(DISTINCT CASE
            WHEN m.oid IS NOT NULL THEN assigned.oid
        END) AS matched_in_osm
    FROM assigned
    LEFT JOIN matched m
        ON assigned.oid = m.oid
    GROUP BY COALESCE(district, 'UNASSIGNED')
    ORDER BY district
""").toPandas()

by_district.to_csv(p("out", "validation_by_district.csv"), index=False)
print(by_district)

# 2. Of the top-N flagged hexagons, how many have an official hospital within the hospital threshold?
top = (
    sedona.read.parquet(
        spark_path("out", f"severity_{a.tag}")
    )
    .orderBy(F.desc("severity"))
    .limit(a.top_n)
    .selectExpr("h3", "ST_Point(lon, lat) AS ctr")
)
top.createOrReplaceTempView("top")
n_top = top.count()
deg_t = T["hosp"] / 100000.0
n_with_official_hospital = sedona.sql(f"""
    SELECT COUNT(DISTINCT tp.h3) AS c
    FROM top tp
    JOIN official o
      ON ST_Distance(tp.ctr, o.g) <= {deg_t}
    WHERE ST_DistanceSphere(tp.ctr, o.g) <= {T['hosp']}
""").first()["c"]

print(
    f"Top {n_top} severity-ranked hexagons: "
    f"{n_with_official_hospital} have an official hospital within "
    f"{T['hosp']:.0f} m; "
    f"{n_top - n_with_official_hospital} have no listed official hospital "
    f"within that distance."
)
pd.DataFrame([{
    "official_total": n_off,
    "matched_in_osm": n_match,
    "osm_match_pct": 100 * n_match / max(n_off, 1),
    "top_n_severity_hexagons": n_top,
    "top_hexagons_with_official_hospital": n_with_official_hospital,
    "top_hexagons_without_listed_official_hospital": (
        n_top - n_with_official_hospital
    ),
    "hospital_threshold_m": T["hosp"],
}]).to_csv(p("out", "validation_summary.csv"), index=False)
