"""Stage 4: check OSM completeness and false alarms against an official hospital list (staging/official.csv)."""
import argparse

import pandas as pd
from pyspark.sql import functions as F

from common import get_sedona
from config import T, p

ap = argparse.ArgumentParser()
ap.add_argument("--tag", default="base")
ap.add_argument("--official", default=p("staging", "official.csv"))
ap.add_argument("--top-n", type=int, default=400)
ap.add_argument("--match-m", type=float, default=500)
a = ap.parse_args()

sedona = get_sedona("validate")

official = (sedona.read.csv(a.official, header=True, inferSchema=True)
            .withColumn("oid", F.monotonically_increasing_id())
            .selectExpr("oid", "name", "ST_Point(CAST(lon AS double), CAST(lat AS double)) AS g"))
official.createOrReplaceTempView("official")
sedona.read.parquet(p("out", "facilities")).where("facility_type = 'hospital'").selectExpr(
    "ST_Point(lon, lat) AS g").createOrReplaceTempView("osmh")
sedona.read.parquet(p("staging", "talukas.parquet")).selectExpr(
    "district", "ST_GeomFromWKT(wkt) AS geom").createOrReplaceTempView("t")

# 1. Which official hospitals exist in OSM (within match radius)?
deg_m = a.match_m / 100000.0
sedona.sql(f"""
    SELECT DISTINCT o.oid FROM official o JOIN osmh m ON ST_Distance(o.g, m.g) <= {deg_m}
    WHERE ST_DistanceSphere(o.g, m.g) <= {a.match_m}""").createOrReplaceTempView("matched")
n_off = official.count()
n_match = sedona.sql("SELECT COUNT(*) AS c FROM matched").first()["c"]
print(f"official hospitals: {n_off}, found in OSM within {a.match_m:.0f} m: {n_match} ({100 * n_match / max(n_off, 1):.1f}%)")

by_district = sedona.sql("""
    SELECT t.district, COUNT(*) AS official_total, COUNT(m.oid) AS matched_in_osm
    FROM official o JOIN t ON ST_Within(o.g, t.geom) LEFT JOIN matched m ON o.oid = m.oid
    GROUP BY t.district""").toPandas()
by_district.to_csv(p("out", "validation_by_district.csv"), index=False)
print(by_district)

# 2. Of the top-N flagged hexagons, how many have an official hospital within the hospital threshold?
top = (sedona.read.parquet(p("out", f"severity_{a.tag}")).orderBy(F.desc("severity")).limit(a.top_n)
       .selectExpr("h3", "ST_Point(lon, lat) AS ctr"))
top.createOrReplaceTempView("top")
n_top = top.count()
deg_t = T["hosp"] / 100000.0
n_false = sedona.sql(f"""
    SELECT COUNT(DISTINCT tp.h3) AS c FROM top tp JOIN official o ON ST_Distance(tp.ctr, o.g) <= {deg_t}
    WHERE ST_DistanceSphere(tp.ctr, o.g) <= {T['hosp']}""").first()["c"]
print(f"top {n_top} flagged hexagons: {n_false} have an official hospital within {T['hosp']:.0f} m "
      f"(false alarms), {n_top - n_false} confirmed gaps ({100 * (n_top - n_false) / max(n_top, 1):.1f}%)")

pd.DataFrame([{
    "official_total": n_off, "matched_in_osm": n_match,
    "osm_match_pct": 100 * n_match / max(n_off, 1),
    "top_n": n_top, "false_alarms": n_false,
    "confirmed_gap_pct": 100 * (n_top - n_false) / max(n_top, 1),
}]).to_csv(p("out", "validation_summary.csv"), index=False)