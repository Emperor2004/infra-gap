"""Stage 6: write CSVs for Kepler.gl (H3 layer) and for the report tables."""
import os

import h3

from common import get_sedona
from config import p

sedona = get_sedona("export-viz")
out_dir = p("out", "viz")
os.makedirs(out_dir, exist_ok=True)

pdf = (sedona.read.parquet(p("out", "severity_base"))
       .select("h3", "pop", "n_buildings", "d_hosp", "d_school", "d_water", "severity", "lon", "lat")
       .toPandas())
pdf["hex_id"] = pdf["h3"].apply(lambda x: h3.int_to_str(int(x)))
pdf.to_csv(os.path.join(out_dir, "severity_hex.csv"), index=False)
print(len(pdf), "hexagons written to severity_hex.csv")

(sedona.read.parquet(p("out", "taluka_base")).orderBy("severity_per_person", ascending=False)
 .toPandas().to_csv(os.path.join(out_dir, "taluka_ranking.csv"), index=False))
print("taluka_ranking.csv written")