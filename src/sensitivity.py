"""Stage 5: how stable is the taluka ranking when thresholds or weights change?

Distances do not depend on thresholds, so this reuses out/severity_base and only recomputes the score.
"""
import pandas as pd
from scipy.stats import spearmanr

from common import get_sedona, severity_sql
from config import T, p

sedona = get_sedona("sensitivity")

sedona.read.parquet(p("staging", "talukas.parquet")).selectExpr(
    "district", "taluka", "ST_GeomFromWKT(wkt) AS geom").createOrReplaceTempView("t")
sedona.read.parquet(p("out", "severity_base")).selectExpr(
    "pop", "d_hosp", "d_school", "d_water", "ST_Point(lon, lat) AS ctr").createOrReplaceTempView("s")
joined = sedona.sql("""
    SELECT concat(t.district, ' | ', t.taluka) AS key, s.pop, s.d_hosp, s.d_school, s.d_water
    FROM s JOIN t ON ST_Within(s.ctr, t.geom)""").cache()
joined.createOrReplaceTempView("j")

th, ts, tw = T["hosp"], T["school"], T["water"]
scenarios = {
    "baseline": (th, ts, tw, (1 / 3, 1 / 3, 1 / 3)),
    "thresholds -25%": (th * 0.75, ts * 0.75, tw * 0.75, (1 / 3, 1 / 3, 1 / 3)),
    "thresholds +25%": (th * 1.25, ts * 1.25, tw * 1.25, (1 / 3, 1 / 3, 1 / 3)),
    "hospital weight doubled": (th, ts, tw, (0.5, 0.25, 0.25)),
}


def taluka_scores(params):
    sev = severity_sql(*params)
    df = sedona.sql(f"SELECT key, SUM({sev}) / SUM(pop) AS spp FROM j GROUP BY key").toPandas()
    return df.set_index("key")["spp"]


scores = {name: taluka_scores(params) for name, params in scenarios.items()}
base = scores["baseline"]
rows = []
for name, s in scores.items():
    both = pd.concat([base, s], axis=1, join="inner").dropna()
    rho = spearmanr(both.iloc[:, 0], both.iloc[:, 1]).correlation
    overlap = len(set(base.nlargest(10).index) & set(s.nlargest(10).index))
    rows.append({"scenario": name, "top10_overlap": f"{overlap} of 10", "spearman_rho": round(float(rho), 3)})
out = pd.DataFrame(rows)
out.to_csv(p("out", "sensitivity.csv"), index=False)
print(out.to_string(index=False))