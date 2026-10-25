"""Download Microsoft building-footprint tiles that intersect the study bounding box."""
import os
import sys

import mercantile
import pandas as pd
import requests
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from config import BBOX, p  # noqa: E402

MANIFEST = os.environ.get(
    "MANIFEST_URL",
    "https://bfppub.blob.core.windows.net/%24web/2026-07-24/dataset-links.csv",
)
W, S, E, N = BBOX

df = pd.read_csv(MANIFEST, dtype=str)  # dtype=str keeps leading zeros in quadkeys
print("manifest columns:", df.columns.tolist())
print(df.head(3))
missing = {"Location", "QuadKey", "Url"} - set(df.columns)
if missing:
    sys.exit(f"Manifest is missing columns {missing}. Edit this script to match the header above.")

df = df[df["Location"] == "India"]
zoom = int(df["QuadKey"].str.len().mode()[0])
needed = {mercantile.quadkey(t) for t in mercantile.tiles(W, S, E, N, zooms=zoom)}
sel = df[df["QuadKey"].isin(needed)]
print(f"{len(sel)} tiles intersect the bounding box (quadkey level {zoom})")
if sel.empty:
    sys.exit("No tiles found. Check BBOX in config/settings.env and the manifest Location value.")

dest = p("raw", "buildings")
os.makedirs(dest, exist_ok=True)
for row in tqdm(list(sel.itertuples()), desc="tiles"):
    name = f"{row.QuadKey}_{row.Url.split('?')[0].split('/')[-1]}"
    out = os.path.join(dest, name)
    if os.path.exists(out):
        continue
    tmp = out + ".part"
    with requests.get(row.Url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    os.replace(tmp, out)
print("done:", dest)