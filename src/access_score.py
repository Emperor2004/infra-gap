"""Stage 2: nearest-facility distance per hexagon and the population-weighted Gap Severity Score."""
import argparse

import pandas as pd

from common import get_sedona, severity_sql, timed
from config import RADIUS_M, T, p

ap = argparse.ArgumentParser()
ap.add_argument("--tag", default="base")
ap.add_argument("--t-hosp", type=float, default=T["hosp"])
ap.add_argument("--t-school", type=float, default=T["school"])
ap.add_argument("--t-water", type=float, default=T["water"])
ap.add_argument("--w", type=float, nargs=3, default=[1 / 3, 1 / 3, 1 / 3])
ap.add_argument("--radius", type=float, default=RADIUS_M)
a = ap.parse_args()

sedona = get_sedona(f"access-score-{a.tag}")
R = a.radius
deg = R / 100000.0  # conservative planar pre-filter in degrees (1 degree >= 100 km here)

sedona.read.parquet(p("out", "hex")).selectExpr(
    "h3", "n_buildings", "pop", "lon", "lat", "ST_Point(lon, lat) AS ctr"
).createOrReplaceTempView("hexv")
sedona.read.parquet(p("out", "facilities")).selectExpr(
    "facility_type", "ST_Point(lon, lat) AS geom"
).createOrReplaceTempView("facv")

with timed(sedona, "access", "distance_join"):
    dist = sedona.sql(f"""
        SELECT h.h3, f.facility_type, MIN(ST_DistanceSphere(h.ctr, f.geom)) AS dist_m
        FROM hexv h JOIN facv f ON ST_Distance(h.ctr, f.geom) <= {deg}
        WHERE ST_DistanceSphere(h.ctr, f.geom) <= {R}
        GROUP BY h.h3, f.facility_type""")
    dist.write.mode("overwrite").parquet(p("staging", f"access_{a.tag}"))

with timed(sedona, "access", "scoring"):
    sedona.read.parquet(p("staging", f"access_{a.tag}")).createOrReplaceTempView("access")
    sedona.sql(f"""
        SELECT h.h3, h.pop, h.n_buildings, h.lon, h.lat,
          COALESCE(MAX(IF(x.facility_type = 'hospital',       x.dist_m, NULL)), {R}) AS d_hosp,
          COALESCE(MAX(IF(x.facility_type = 'school',         x.dist_m, NULL)), {R}) AS d_school,
          COALESCE(MAX(IF(x.facility_type = 'drinking_water', x.dist_m, NULL)), {R}) AS d_water
        FROM hexv h LEFT JOIN access x ON h.h3 = x.h3
        GROUP BY h.h3, h.pop, h.n_buildings, h.lon, h.lat""").createOrReplaceTempView("scored")
    sedona.sql(f"""
        SELECT *, {severity_sql(a.t_hosp, a.t_school, a.t_water, tuple(a.w))} AS severity
        FROM scored""").write.mode("overwrite").parquet(p("out", f"severity_{a.tag}"))

sv = sedona.read.parquet(p("out", f"severity_{a.tag}"))
sv.createOrReplaceTempView("sv")

# Percentiles are per hexagon; "pct_pop_beyond" is population-weighted.
summary = sedona.sql(f"""
    SELECT COUNT(*) AS hexagons, SUM(pop) AS population,
      percentile_approx(d_hosp, 0.5)   AS hosp_median_m,   percentile_approx(d_hosp, 0.9)   AS hosp_p90_m,
      percentile_approx(d_school, 0.5) AS school_median_m, percentile_approx(d_school, 0.9) AS school_p90_m,
      percentile_approx(d_water, 0.5)  AS water_median_m,  percentile_approx(d_water, 0.9)  AS water_p90_m,
      100 * SUM(IF(d_hosp   > {a.t_hosp},   pop, 0)) / SUM(pop) AS hosp_pct_pop_beyond,
      100 * SUM(IF(d_school > {a.t_school}, pop, 0)) / SUM(pop) AS school_pct_pop_beyond,
      100 * SUM(IF(d_water  > {a.t_water},  pop, 0)) / SUM(pop) AS water_pct_pop_beyond,
      SUM(IF(d_hosp   >= {R}, 1, 0)) AS hosp_none_in_radius,
      SUM(IF(d_school >= {R}, 1, 0)) AS school_none_in_radius,
      SUM(IF(d_water  >= {R}, 1, 0)) AS water_none_in_radius
    FROM sv""").toPandas()
summary.to_csv(p("out", f"summary_{a.tag}.csv"), index=False)
print(summary.T)

sv.orderBy("severity", ascending=False).select(
    "h3", "pop", "d_hosp", "d_school", "d_water", "severity").show(10, truncate=False)