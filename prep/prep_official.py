"""Normalise an official hospital list (from data.gov.in or similar) to name, lon, lat.

Example:
  python prep/prep_official.py data/raw/official/hospitals.csv --name-col "Hospital Name" --lon-col Longitude --lat-col Latitude
The list must contain coordinates. If it only has addresses, geocode it first.
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from config import BBOX, p  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("path")
ap.add_argument("--name-col", required=True)
ap.add_argument("--lon-col", required=True)
ap.add_argument("--lat-col", required=True)
ap.add_argument("--encoding", default="utf-8")
a = ap.parse_args()

df = pd.read_csv(a.path, encoding=a.encoding)
out = pd.DataFrame({
    "name": df[a.name_col].astype(str),
    "lon": pd.to_numeric(df[a.lon_col], errors="coerce"),
    "lat": pd.to_numeric(df[a.lat_col], errors="coerce"),
}).dropna()
W, S, E, N = BBOX
out = out[(out.lon.between(W, E)) & (out.lat.between(S, N))]
os.makedirs(p("staging"), exist_ok=True)
out.to_csv(p("staging", "official.csv"), index=False)
print(f"wrote {len(out)} official facilities inside the study box")