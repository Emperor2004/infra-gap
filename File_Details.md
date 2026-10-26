# File Details: India Infrastructure Gap Mapping

Complete file structure and the full code of every file **you write by hand**.
Setup: Spark 3.5.x standalone cluster (1 master + 2 workers) on three VMware Workstation VMs (Ubuntu 22.04, OpenJDK 11), Apache Sedona 1.9.1, H3. Hadoop 3.3.6 (HDFS + YARN) runs on the same VMs for Lab 1; the pipeline itself reads and writes a shared NFS folder, `/data`.

> VM, network, Hadoop and NFS setup are in `VM_Cluster_Setup.md` (Sections 2 to 9). This file covers the project files.
> Run everything on `h-primary` as `h-user`. The project lives in `~/infra-gap`, with two symlinks: `/workspace -> ~/infra-gap` and `~/infra-gap/data -> /data` (created in Section 8).
> This version replaces the Docker version: `Dockerfile`, `docker-compose.yml`, `.dockerignore` and `.wslconfig` are no longer used.

---

## 1. Folder structure

```
infra-gap/
├── README.md                      [write]  project overview (delivered separately)
├── .gitignore                     [write]
├── config/
│   └── settings.env               [write]  bounding box, H3 resolution, thresholds
├── cluster/                       VM cluster files (copied into /opt/spark/conf by install_spark.sh)
│   ├── install_spark.sh           [write]
│   ├── spark-defaults.conf        [write]
│   ├── spark-env.sh               [write]
│   └── workers                    [write]
├── prep/                          data preparation (plain Python / bash, run on h-primary)
│   ├── fetch_buildings.py         [write]
│   ├── prep_osm.sh                [write]
│   ├── raster_to_points.py        [write]
│   ├── prep_population.sh         [write]
│   ├── prep_boundaries.py         [write]
│   └── prep_official.py           [write]
├── src/                           Spark + Sedona jobs (run with spark-submit)
│   ├── config.py                  [write]
│   ├── common.py                  [write]
│   ├── smoke_test.py              [write]
│   ├── ingest_index.py            [write]
│   ├── access_score.py            [write]
│   ├── rollup.py                  [write]
│   ├── validate.py                [write]
│   ├── sensitivity.py             [write]
│   └── export_viz.py              [write]
├── analysis/
│   └── make_figures.py            [write]  charts and maps from the real outputs
├── scripts/                       run helpers (run on h-primary)
│   ├── run_all.sh                 [write]
│   └── benchmark.sh               [write]
└── data -> /data                  [symlink to the NFS share, git-ignored]

/data  (NFS export from h-primary, mounted at /data on all three VMs)
    ├── raw/
    │   ├── buildings/             tiles from fetch_buildings.py
    │   ├── osm/                   .osm.pbf files from prep_osm.sh
    │   ├── population/            HRSL GeoTIFF(s), downloaded by you
    │   ├── boundaries/            DataMeet clone, downloaded by you
    │   └── official/              official hospital CSV, downloaded by you
    ├── staging/                   cleaned inputs (pop_points, facilities, talukas.parquet, official.csv)
    ├── out/                       hex, facilities, severity_*, taluka_*, district_*, summaries, viz/, figures/, timings.csv
    └── spark-events/              Spark event logs
```

Outside the project: Hadoop and system files described in `VM_Cluster_Setup.md` (`/etc/hosts`, `/etc/environment`, netplan, `/etc/exports`, `/etc/fstab`, Hadoop XML files).

Create the folders once, on `h-primary`:

```bash
mkdir -p ~/infra-gap/{config,cluster,prep,src,analysis,scripts}
sudo ln -sfn ~/infra-gap /workspace
ln -sfn /data ~/infra-gap/data
mkdir -p /data/{spark-events,raw,staging,out}      # /data is the NFS export (VM_Cluster_Setup.md Section 8)
```

---

## 2. Cluster files (`cluster/`, `config/`)

### `cluster/install_spark.sh`

Run once on `h-primary` as `h-user` after SSH and NFS work. It installs Spark, the Sedona jars and the Python venv, applies the config files below, and copies everything to both workers (same paths on every VM).

```bash
#!/usr/bin/env bash
set -euo pipefail

SPARK_VER="${SPARK_VER:-3.5.7}"
SEDONA_VER="${SEDONA_VER:-1.9.1}"
GEOTOOLS_VER="${GEOTOOLS_VER:-1.9.1-33.5}"
WORKERS="h-secondary1 h-secondary2"
HERE="$(cd "$(dirname "$0")" && pwd)"
ME="$(id -un)"

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip curl git gdal-bin osmium-tool rsync

if [ ! -x /opt/spark/bin/spark-submit ]; then
  curl -fsSL "https://archive.apache.org/dist/spark/spark-${SPARK_VER}/spark-${SPARK_VER}-bin-hadoop3.tgz" | sudo tar xz -C /opt
  sudo mv "/opt/spark-${SPARK_VER}-bin-hadoop3" /opt/spark
  sudo chown -R "$ME:$ME" /opt/spark
fi

SED_JAR="/opt/spark/jars/sedona-spark-shaded-3.5_2.12-${SEDONA_VER}.jar"
GEO_JAR="/opt/spark/jars/geotools-wrapper-${GEOTOOLS_VER}.jar"
[ -f "$SED_JAR" ] || curl -fsSL -o "$SED_JAR" \
  "https://repo1.maven.org/maven2/org/apache/sedona/sedona-spark-shaded-3.5_2.12/${SEDONA_VER}/sedona-spark-shaded-3.5_2.12-${SEDONA_VER}.jar"
[ -f "$GEO_JAR" ] || curl -fsSL -o "$GEO_JAR" \
  "https://repo1.maven.org/maven2/org/datasyslab/geotools-wrapper/${GEOTOOLS_VER}/geotools-wrapper-${GEOTOOLS_VER}.jar"

if [ ! -x /opt/venv/bin/python ]; then
  sudo mkdir -p /opt/venv && sudo chown "$ME:$ME" /opt/venv
  python3 -m venv /opt/venv
  /opt/venv/bin/pip install --upgrade pip
  /opt/venv/bin/pip install "pyspark==${SPARK_VER}" "apache-sedona==${SEDONA_VER}" \
    shapely attrs pandas pyarrow geopandas pyogrio "h3>=4" mercantile rasterio requests tqdm scipy matplotlib
fi

cp "$HERE/spark-defaults.conf" "$HERE/spark-env.sh" "$HERE/workers" /opt/spark/conf/
mkdir -p /var/tmp/spark

for h in $WORKERS; do
  ssh "$h" "sudo mkdir -p /opt/spark /opt/venv /var/tmp/spark && sudo chown $ME:$ME /opt/spark /opt/venv /var/tmp/spark"
  rsync -a /opt/spark/ "$h:/opt/spark/"
  rsync -a /opt/venv/  "$h:/opt/venv/"
done
echo "Installed. Start the cluster with: /opt/spark/sbin/start-all.sh"
```

If `3.5.7` is not on archive.apache.org, run with `SPARK_VER=<latest 3.5.x patch> cluster/install_spark.sh`. Re-running is safe; it skips what exists and re-copies config.
Spark's `sbin` is deliberately not on `PATH`: Hadoop also ships a `start-all.sh`. Always call `/opt/spark/sbin/start-all.sh` with the full path.

### `cluster/spark-defaults.conf`

```
spark.master                   spark://h-primary:7077
spark.serializer               org.apache.spark.serializer.KryoSerializer
spark.kryo.registrator         org.apache.sedona.core.serde.SedonaKryoRegistrator
spark.driver.host              h-primary
spark.driver.bindAddress       0.0.0.0
spark.sql.shuffle.partitions   40
spark.sql.adaptive.enabled     true
spark.eventLog.enabled         true
spark.eventLog.dir             /data/spark-events
spark.local.dir                /var/tmp/spark
```

### `cluster/spark-env.sh`

```bash
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export SPARK_MASTER_HOST=h-primary
export SPARK_WORKER_CORES=4
export SPARK_WORKER_MEMORY=2g
export PYSPARK_PYTHON=/opt/venv/bin/python
export PYSPARK_DRIVER_PYTHON=/opt/venv/bin/python
```

### `cluster/workers`

```
h-secondary1
h-secondary2
```

Values are for 4 vCPU and 3.5 GB RAM per worker VM on a 16 GB host. Change `SPARK_WORKER_CORES`, `SPARK_WORKER_MEMORY`, the VM sizes and the `spark-submit` flags together.

### `.gitignore`

```
data
__pycache__/
*.pyc
.ipynb_checkpoints/
```

### `config/settings.env`

Plain `KEY=VALUE` lines (no `export`, no quotes). `~/.bashrc` on `h-primary` loads this file (`set -a; . ~/infra-gap/config/settings.env; set +a`), so every prep script and `spark-submit` run sees the variables. Open a new shell after editing.

```
# Study area bounding box (degrees). Generous box around the pilot district; adjust.
BBOX_W=73.0
BBOX_S=17.5
BBOX_E=75.5
BBOX_N=19.5

# H3 hexagon resolution (8 = about 0.74 km2 per cell)
H3_RES=8

# Search radius for nearest-facility distance, in metres
SEARCH_RADIUS_M=25000

# Distance thresholds in metres (working assumptions, see report Section 5.2)
T_HOSP_M=10000
T_SCHOOL_M=3000
T_WATER_M=2000

# Root folder for data (the NFS share, same path on every VM)
DATA_ROOT=/data
```

---


## 3. Shared Python modules (`src/`)

### `src/config.py`

```python
"""Settings shared by all scripts, read from environment variables (see config/settings.env)."""
import os

ROOT = os.environ.get("DATA_ROOT", "/data")


def p(*parts):
    """Build a path under the data root, for example p('out', 'hex')."""
    return os.path.join(ROOT, *parts)


BBOX = (
    float(os.environ.get("BBOX_W", 73.0)),
    float(os.environ.get("BBOX_S", 17.5)),
    float(os.environ.get("BBOX_E", 75.5)),
    float(os.environ.get("BBOX_N", 19.5)),
)
H3_RES = int(os.environ.get("H3_RES", 8))
RADIUS_M = float(os.environ.get("SEARCH_RADIUS_M", 25000))
T = {
    "hosp": float(os.environ.get("T_HOSP_M", 10000)),
    "school": float(os.environ.get("T_SCHOOL_M", 3000)),
    "water": float(os.environ.get("T_WATER_M", 2000)),
}
```

### `src/common.py`

```python
"""Helpers shared by the Spark jobs: session creation, stage timing, severity formula."""
import csv
import os
import time
from contextlib import contextmanager

from pyspark.sql import SparkSession
from sedona.spark import SedonaContext

from config import p


def get_sedona(app_name):
    """Create a Spark session with Sedona functions registered."""
    spark = SparkSession.builder.appName(app_name).getOrCreate()
    return SedonaContext.create(spark)


@contextmanager
def timed(sedona, job, stage):
    """Time a block (include the Spark action inside it) and append the result to out/timings.csv."""
    t0 = time.time()
    yield
    seconds = time.time() - t0
    master = sedona.sparkContext.master
    mode = "local" if master.startswith("local") else "cluster"
    path = p("out", "timings.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    is_new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["timestamp", "job", "stage", "seconds", "mode"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), job, stage, round(seconds, 2), mode])
    print(f"[timing] {job}/{stage}: {seconds:.1f}s ({mode})")


def severity_sql(t_hosp, t_school, t_water, w=(1 / 3, 1 / 3, 1 / 3)):
    """SQL expression for the Gap Severity Score.

    Needs columns: pop, d_hosp, d_school, d_water (distances in metres).
    ratio = min(max(0, d - T) / T, 3); severity = pop * sum(w * ratio)
    """
    return (
        f"pop * ({w[0]} * LEAST(GREATEST(d_hosp - {t_hosp}, 0) / {t_hosp}, 3) "
        f"+ {w[1]} * LEAST(GREATEST(d_school - {t_school}, 0) / {t_school}, 3) "
        f"+ {w[2]} * LEAST(GREATEST(d_water - {t_water}, 0) / {t_water}, 3))"
    )
```

---

## 4. Data preparation scripts (`prep/`)

Run on `h-primary` as `h-user`, for example `python prep/fetch_buildings.py` (the venv python is first on `PATH`; `settings.env` is loaded by `~/.bashrc`).

### `prep/fetch_buildings.py`

```python
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
```

### `prep/prep_osm.sh`

```bash
#!/usr/bin/env bash
# Extract hospitals, schools and drinking-water points for the study box from OpenStreetMap.
set -euo pipefail

ROOT="${DATA_ROOT:-/data}"
RAW="$ROOT/raw/osm"
STG="$ROOT/staging/facilities"
ZONE_URL="${OSM_ZONE_URL:-https://download.geofabrik.de/asia/india/western-zone-latest.osm.pbf}"

mkdir -p "$RAW" "$STG"

if [ ! -f "$RAW/india-zone.osm.pbf" ]; then
  echo "Downloading $ZONE_URL"
  curl -L --fail -o "$RAW/india-zone.osm.pbf" "$ZONE_URL"
fi

osmium extract -b "$BBOX_W,$BBOX_S,$BBOX_E,$BBOX_N" "$RAW/india-zone.osm.pbf" -o "$RAW/pilot.osm.pbf" --overwrite
osmium tags-filter "$RAW/pilot.osm.pbf" \
  nwr/amenity=hospital nwr/healthcare=hospital nwr/amenity=school nwr/amenity=drinking_water \
  -o "$RAW/fac.osm.pbf" --overwrite
osmium export "$RAW/fac.osm.pbf" -f geojsonseq -o "$RAW/fac.geojsonseq" --overwrite

# geojsonseq lines start with an RFC 8142 record separator (0x1E); strip it so Spark can parse each line
tr -d '\036' < "$RAW/fac.geojsonseq" > "$STG/fac.geojsonl"
echo "facility features: $(wc -l < "$STG/fac.geojsonl")"
```

If Maharashtra is not in the Western Zone file, set `OSM_ZONE_URL` in `config/settings.env` to the correct Geofabrik file.

### `prep/raster_to_points.py`

```python
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
```

### `prep/prep_population.sh`

```bash
#!/usr/bin/env bash
# Clip the downloaded HRSL tile(s) to the study box and convert to Parquet points.
# Before running: download the India HRSL GeoTIFF(s) covering your box from HDX into data/raw/population/.
set -euo pipefail

ROOT="${DATA_ROOT:-/data}"
RAW="$ROOT/raw/population"
STG="$ROOT/staging"

shopt -s nullglob
tiles=("$RAW"/*.tif)
if [ ${#tiles[@]} -eq 0 ]; then
  echo "No .tif files in $RAW. Download the HRSL tile(s) first."; exit 1
fi

mkdir -p "$STG/pop_points"
gdalbuildvrt -overwrite "$STG/pop_all.vrt" "${tiles[@]}"
gdal_translate -projwin "$BBOX_W" "$BBOX_N" "$BBOX_E" "$BBOX_S" \
  -co COMPRESS=DEFLATE -co TILED=YES "$STG/pop_all.vrt" "$STG/pop_pilot.tif"

python /workspace/prep/raster_to_points.py "$STG/pop_pilot.tif" "$STG/pop_points/pop_points.parquet"
```

### `prep/prep_boundaries.py`

```python
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
```

### `prep/prep_official.py`

```python
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
```

---

## 5. Spark jobs (`src/`)

Run each on `h-primary` with `spark-submit --driver-memory 1g --executor-memory 1500m --total-executor-cores 8 /workspace/src/<job>.py`.
The helper modules are used only on the driver, so no `--py-files` is needed.

### `src/smoke_test.py`

```python
"""Checks that Sedona works, work runs on both workers, and the shared /data folder is writable."""
import socket

from common import get_sedona
from config import p

sedona = get_sedona("smoke-test")

print(sedona.sql("SELECT ST_Point(73.85, 18.52) AS p").first())
print(sedona.sql("SELECT ST_H3CellIDs(ST_Point(73.85, 18.52), 8, false) AS h").first())
print(sedona.sql("SELECT ST_DistanceSphere(ST_Point(73.85, 18.52), ST_Point(73.86, 18.53)) AS d").first())
print(sedona.sql("SELECT ST_H3ToGeom(ST_H3CellIDs(ST_Point(73.85, 18.52), 8, false)) AS g").first())

hosts = (sedona.sparkContext.parallelize(range(400), 10)
         .map(lambda _: socket.gethostname()).distinct().collect())
print("executor hosts:", sorted(hosts))

path = p("staging", "smoke")
sedona.range(1000).write.mode("overwrite").parquet(path)
print("rows read back:", sedona.read.parquet(path).count())
```

Pass: four Sedona results print, `executor hosts` lists `spark-worker-1` and `spark-worker-2`, rows read back is `1000`.

### `src/ingest_index.py`

```python
"""Stage 1: buildings, population and facilities -> H3 hexagon table and facility table."""
from pyspark.sql import functions as F

from common import get_sedona, timed
from config import H3_RES, p

sedona = get_sedona("ingest-index")

# ---------- hexagon table ----------
with timed(sedona, "ingest", "hex_table"):
    raw = sedona.read.option("recursiveFileLookup", "true").text(p("raw", "buildings"))
    geo = raw.select(F.get_json_object("value", "$.geometry").alias("gj"))

    sample = geo.limit(2000)
    n_ok, n = sample.where("gj IS NOT NULL").count(), sample.count()
    print(f"geometry parsed for {n_ok}/{n} sampled building lines")
    assert n > 0 and n_ok / n > 0.9, "Building lines are not GeoJSON features. Inspect a tile with: zcat <file> | head -2"

    buildings = (geo.where("gj IS NOT NULL")
                 .selectExpr(f"ST_H3CellIDs(ST_Centroid(ST_GeomFromGeoJSON(gj)), {H3_RES}, false)[0] AS h3")
                 .groupBy("h3").agg(F.count("*").alias("n_buildings")))

    population = (sedona.read.parquet(p("staging", "pop_points"))
                  .selectExpr(f"ST_H3CellIDs(ST_Point(lon, lat), {H3_RES}, false)[0] AS h3", "pop")
                  .groupBy("h3").agg(F.sum("pop").alias("pop")))

    hexes = (buildings.join(population, "h3", "full_outer")
             .fillna({"n_buildings": 0, "pop": 0.0})
             .where("n_buildings > 0 OR pop > 0"))
    hexes.createOrReplaceTempView("h")

    out = sedona.sql("""
        SELECT h3, n_buildings, pop,
               ST_X(ST_Centroid(ST_H3ToGeom(array(h3))[0])) AS lon,
               ST_Y(ST_Centroid(ST_H3ToGeom(array(h3))[0])) AS lat
        FROM h""")
    out.write.mode("overwrite").parquet(p("out", "hex"))

hex_df = sedona.read.parquet(p("out", "hex"))
hex_df.agg(F.count("*").alias("hexagons"), F.sum("n_buildings").alias("buildings"),
           F.sum("pop").alias("population")).show(truncate=False)
hex_df.orderBy(F.desc("pop")).show(8, truncate=False)

# ---------- facilities ----------
with timed(sedona, "ingest", "facilities"):
    fac = sedona.read.text(p("staging", "facilities"))
    fac = fac.select(
        F.get_json_object("value", "$.properties.amenity").alias("amenity"),
        F.get_json_object("value", "$.properties.healthcare").alias("healthcare"),
        F.get_json_object("value", "$.geometry").alias("gj"),
    ).where("gj IS NOT NULL")
    fac = (fac.withColumn(
        "facility_type",
        F.when((F.col("amenity") == "hospital") | (F.col("healthcare") == "hospital"), "hospital")
         .when(F.col("amenity") == "school", "school")
         .when(F.col("amenity") == "drinking_water", "drinking_water"))
           .where("facility_type IS NOT NULL"))
    fac.createOrReplaceTempView("f")
    sedona.sql("""
        SELECT facility_type,
               ST_X(ST_Centroid(ST_GeomFromGeoJSON(gj))) AS lon,
               ST_Y(ST_Centroid(ST_GeomFromGeoJSON(gj))) AS lat
        FROM f""").write.mode("overwrite").parquet(p("out", "facilities"))

sedona.read.parquet(p("out", "facilities")).groupBy("facility_type").count().show()
```

### `src/access_score.py`

```python
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
```

### `src/rollup.py`

```python
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
```

### `src/validate.py`

```python
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
```

### `src/sensitivity.py`

```python
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
```

### `src/export_viz.py`

```python
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
```

For Kepler.gl: open https://kepler.gl/demo, drop in `severity_hex.csv`, add an **H3** layer using the `hex_id` column, and colour by `severity`.

---

## 6. Figures from real outputs (`analysis/`)

### `analysis/make_figures.py`

```python
"""Draw the report charts and maps from the pipeline outputs. Run: python analysis/make_figures.py"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from config import T, p  # noqa: E402

OUT = p("out", "figures")
os.makedirs(OUT, exist_ok=True)
sv = pd.read_parquet(p("out", "severity_base"))
aspect = 1 / np.cos(np.deg2rad(sv["lat"].mean()))


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", name)


def hexmap(values, title, label, name, cmap):
    fig, ax = plt.subplots(figsize=(7.4, 6))
    hb = ax.hexbin(sv["lon"], sv["lat"], C=values, reduce_C_function=np.mean, gridsize=80,
                   cmap=cmap, mincnt=1, linewidths=0.1)
    ax.set_aspect(aspect)
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude"); ax.set_title(title, fontweight="bold")
    fig.colorbar(hb, ax=ax, shrink=0.8).set_label(label)
    save(fig, name)


# 1 and 2: maps
hexmap(np.log10(sv["severity"] + 1), "Gap Severity Map", "log10(Gap Severity Score)", "fig_severity_map.png", "YlOrRd")
hexmap(sv["d_hosp"] / 1000, "Distance to nearest hospital", "Distance (km)", "fig_hospital_distance_map.png", "viridis_r")

# 3: population by distance band
thr = {"Hospital": ("d_hosp", T["hosp"]), "School": ("d_school", T["school"]), "Drinking water": ("d_water", T["water"])}
fig, ax = plt.subplots(figsize=(7.2, 3.6))
left = np.zeros(len(thr))
names = ["Within threshold", "1x to 2x threshold", "Beyond 2x threshold"]
cols = ["#4caf50", "#ffb300", "#d32f2f"]
shares = []
for col, t in thr.values():
    pop = sv["pop"]
    shares.append([100 * pop[sv[col] <= t].sum() / pop.sum(),
                   100 * pop[(sv[col] > t) & (sv[col] <= 2 * t)].sum() / pop.sum(),
                   100 * pop[sv[col] > 2 * t].sum() / pop.sum()])
shares = np.array(shares)
for k in range(3):
    ax.barh(list(thr), shares[:, k], left=left, color=cols[k], label=names[k])
    left += shares[:, k]
ax.set_xlim(0, 100); ax.set_xlabel("Share of population (%)")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, frameon=False)
ax.set_title("Population by distance band", fontweight="bold")
save(fig, "fig_population_bands.png")

# 4: top talukas
tpath = p("out", "taluka_base")
if os.path.exists(tpath):
    tl = pd.read_parquet(tpath).nlargest(10, "severity_per_person").iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 4))
    ax.barh(tl["taluka"] + " (" + tl["district"] + ")", tl["severity_per_person"], color="#c0392b")
    ax.set_xlabel("Severity per person"); ax.set_title("Top 10 underserved talukas", fontweight="bold")
    save(fig, "fig_top_talukas.png")

# 5: OSM vs official
vpath = p("out", "validation_by_district.csv")
if os.path.exists(vpath):
    v = pd.read_csv(vpath)
    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    ax.scatter(v["official_total"], v["matched_in_osm"], color="#1f77b4", zorder=3)
    m = max(v["official_total"].max(), 1) * 1.1
    ax.plot([0, m], [0, m], "--", color="gray", label="Perfect match")
    ax.set_xlim(0, m); ax.set_ylim(0, m)
    ax.set_xlabel("Official hospital count"); ax.set_ylabel("Found in OSM")
    ax.legend(frameon=False); ax.set_title("OSM vs official hospital counts", fontweight="bold")
    save(fig, "fig_osm_vs_official.png")

# 6: runtime, local vs cluster
tpath2 = p("out", "timings.csv")
if os.path.exists(tpath2):
    tm = pd.read_csv(tpath2)
    tm = tm[tm["job"] == "access"].groupby(["stage", "mode"])["seconds"].mean().unstack("mode")
    if not tm.empty:
        ax = (tm / 60).plot(kind="bar", figsize=(7.2, 3.8), rot=0, color=["#2980b9", "#7f8c8d"][: len(tm.columns)])
        ax.set_ylabel("Minutes"); ax.set_title("Runtime by stage: local vs cluster", fontweight="bold")
        save(ax.get_figure(), "fig_runtime.png")
```

---

## 7. Helper scripts (`scripts/`, run on `h-primary`)

Make both executable: `chmod +x scripts/*.sh`.

### `scripts/run_all.sh`

```bash
#!/usr/bin/env bash
# Runs every Spark stage in order. Run the prep steps from README.md first (data must be in /data/staging).
# Stop YARN first (stop-yarn.sh): the VMs do not have RAM for YARN and Spark executors together.
set -euo pipefail

SUBMIT="spark-submit --driver-memory 1g --executor-memory 1500m --total-executor-cores 8"

echo "== 1/7 smoke test";   $SUBMIT /workspace/src/smoke_test.py
echo "== 2/7 ingest+index"; $SUBMIT /workspace/src/ingest_index.py
echo "== 3/7 access+score"; $SUBMIT /workspace/src/access_score.py --tag base
echo "== 4/7 rollup";       $SUBMIT /workspace/src/rollup.py --tag base

if [ -f /data/staging/official.csv ]; then
  echo "== 5/7 validate";   $SUBMIT /workspace/src/validate.py --tag base
else
  echo "== 5/7 validate skipped (no /data/staging/official.csv)"
fi

echo "== 6/7 sensitivity";  $SUBMIT /workspace/src/sensitivity.py
echo "== 7/7 export+figures"
$SUBMIT /workspace/src/export_viz.py
python /workspace/analysis/make_figures.py
echo "Done. Outputs: /data/out (figures in /data/out/figures, CSVs in /data/out/viz)"
```

### `scripts/benchmark.sh`

```bash
#!/usr/bin/env bash
# Local mode on h-primary (4 vCPU) vs the 2-worker cluster (8 cores). Run with YARN stopped.
# Not like for like: local has 4 cores and no network; the cluster has 8 cores plus NFS and network overhead.
set -euo pipefail

echo "== local mode"
for i in 1 2; do
  spark-submit --master "local[4]" --driver-memory 2g \
    --conf spark.driver.host=localhost --conf spark.driver.bindAddress=127.0.0.1 \
    /workspace/src/access_score.py --tag bench_local
done

echo "== cluster mode"
/opt/spark/sbin/start-all.sh || true
sleep 10
for i in 1 2; do
  spark-submit --driver-memory 1g --executor-memory 1500m --total-executor-cores 8 \
    /workspace/src/access_score.py --tag bench_cluster
done

python /workspace/analysis/make_figures.py
echo "Timings are in /data/out/timings.csv; runtime chart in /data/out/figures/fig_runtime.png"
```

Report the numbers you get, from one host configuration (see `VM_Cluster_Setup.md` Section 11 on Hyper-V). On a one-district dataset, local mode may be faster; say so and explain that the cluster demonstrates the architecture, not extra hardware.

---

## 8. Order of work (what you write, what you run)

1. Build the three VMs, network, SSH, Hadoop and the NFS share: `VM_Cluster_Setup.md` Sections 2 to 8. Check HDFS (`:9870`) and YARN (`:8088`) for Lab 1, then `stop-yarn.sh`.
2. Create the project folders and symlinks (Section 1) and write all files above (Sections 2 to 7). Add the `settings.env` loader to `~/.bashrc` and open a new shell.
3. `chmod +x cluster/install_spark.sh scripts/*.sh`, then `cluster/install_spark.sh`.
4. `/opt/spark/sbin/start-all.sh`; open `http://<h-primary IP>:8080` and confirm 2 workers ALIVE.
5. Smoke test (`src/smoke_test.py`, Section 5). Fix anything before continuing.
6. Prep steps (commands are in `README.md`, "Run the pipeline").
7. `scripts/run_all.sh`.
8. `scripts/benchmark.sh`.
9. Take screenshots (HDFS `:9870`, YARN `:8088`, Spark UI `:8080` and `:4040`, terminal outputs, Kepler.gl map) and copy figures from `/data/out/figures/` into the report.

---

## 9. VM resource settings (replaces the Windows `.wslconfig`)

| VM | RAM | vCPU | Disk (thin) |
|---|---|---|---|
| `h-primary` | 4096 MB | 4 | 40 GB |
| `h-secondary1`, `h-secondary2` | 3584 MB each | 4 each | 20 GB each |

Set in VMware Workstation (VM Settings, with the VM shut down). Windows keeps about 5 GB. Details, network and NFS steps: `VM_Cluster_Setup.md`.

---

## 10. Known risks in this code

- Written and checked by reading only; it has **not been executed** (no access to Maven Central or the data hosts from my sandbox). The smoke test and the first ingest run are the real tests.
- Function names (`ST_H3CellIDs`, `ST_H3ToGeom`, `ST_DistanceSphere`) and the Microsoft manifest header are assumed; scripts print or assert so you see failures immediately.
- The building-tile format is assumed to be one GeoJSON feature per line. `ingest_index.py` checks a sample and stops with an instruction if not.
- `prep_boundaries.py` and `prep_official.py` depend on column names in files I have not seen; both print columns or take them as arguments.
- The pipeline needs `/data` mounted on all three VMs. If a worker reports missing files, run `df -h /data` on it; `sudo mount -a` fixes a lost mount.
- `h-user` must have the same uid on all VMs, or workers cannot write to `/data`. Check with `id h-user`.
- Spark writes under `/data` as `h-user` from the workers; if a stage fails with `Permission denied`, check ownership with `ls -ld /data /data/out`.
- The VM and Spark settings (executor memory, cores, NFS options) are sized by estimate for a 16 GB host, not measured. Expect to lower `--executor-memory` or `--total-executor-cores` if a VM runs out of memory.
