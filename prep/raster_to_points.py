"""Convert a population GeoTIFF into a Parquet table of (lon, lat, pop) points for non-empty cells."""
import os
import sys

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
from rasterio.transform import xy

src_path, out_path = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(out_path), exist_ok=True)
if os.path.exists(out_path):
    os.remove(out_path)

writer = None
total = 0
with rasterio.open(src_path) as src:
    epsg = src.crs.to_epsg() if src.crs else None
    assert epsg == 4326, f"expected EPSG:4326, got {src.crs}"
    for _, win in src.block_windows(1):
        a = src.read(1, window=win)
        mask = np.isfinite(a) & (a > 0)
        if not mask.any():
            continue
        rows, cols = np.nonzero(mask)
        xs, ys = xy(src.window_transform(win), rows, cols, offset="center")
        table = pa.table({
            "lon": np.asarray(xs, dtype="float64"),
            "lat": np.asarray(ys, dtype="float64"),
            "pop": a[mask].astype("float32"),
        })
        writer = writer or pq.ParquetWriter(out_path, table.schema)
        writer.write_table(table)
        total += table.num_rows
if writer:
    writer.close()
print(f"wrote {total} populated cells to {out_path}")