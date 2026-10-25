"""Prepare taluka (sub-district) boundaries as Parquet with a WKT geometry column.

First run with --inspect to see the column names, then run again with the right ones.
Example:
  python prep/prep_boundaries.py data/raw/boundaries/<file>.shp --inspect
  python prep/prep_boundaries.py data/raw/boundaries/<file>.shp --district-col DISTRICT --taluka-col SUB_DIST \
      --state-col STATE --state Maharashtra
"""
import argparse
import os
import sys

import geopandas as gpd
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from config import BBOX, p  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("path")
ap.add_argument("--inspect", action="store_true")
ap.add_argument("--district-col")
ap.add_argument("--taluka-col")
ap.add_argument("--state-col")
ap.add_argument("--state")
a = ap.parse_args()

gdf = gpd.read_file(a.path)
if a.inspect:
    print("CRS:", gdf.crs)
    print("columns:", gdf.columns.tolist())
    print(gdf.drop(columns="geometry").head(10))
    sys.exit(0)

if not (a.district_col and a.taluka_col):
    sys.exit("Give --district-col and --taluka-col (use --inspect to list columns).")

gdf = gdf.to_crs(4326)
if a.state_col and a.state:
    gdf = gdf[gdf[a.state_col].astype(str).str.upper() == a.state.upper()]
W, S, E, N = BBOX
gdf = gdf.cx[W:E, S:N]  # keep only talukas that touch the study box

out = pd.DataFrame({
    "district": gdf[a.district_col].astype(str),
    "taluka": gdf[a.taluka_col].astype(str),
    "wkt": gdf.geometry.to_wkt(),
})
os.makedirs(p("staging"), exist_ok=True)
out.to_parquet(p("staging", "talukas.parquet"), index=False)
print(f"wrote {len(out)} talukas to {p('staging', 'talukas.parquet')}")