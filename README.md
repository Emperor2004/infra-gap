# India Infrastructure Gap Mapping

A distributed geospatial big data pipeline that finds where people live far from hospitals, schools and drinking-water points, and ranks those gaps by severity.
Study area: Maharashtra, India. First run: one district (pilot), then scale.

Built with **Apache Spark**, **Apache Sedona** and **Uber H3**, running as a 3-container Spark cluster (1 master + 2 workers) in Docker.

> Full file structure and the code of every file: see [`File_Details.md`](File_Details.md).

---

## 1. Problem

Infrastructure is usually planned from administrative records, which show where facilities were built, not how far residents are from them.
This project answers one question:

> Given where people live (building footprints and population density) and where essential services exist (mapped facilities), where is population dense but access to hospitals, schools and clean water unusually poor, and how severe is each gap?

It is a present-day accessibility audit, not a forecast.

## 2. Method in brief

1. **Ingest** building footprints, OpenStreetMap facilities, a population raster and administrative boundaries.
2. **Index** everything onto an H3 hexagon grid (resolution 8, about 0.74 km² per cell); sum population and count buildings per cell.
3. **Measure access**: for each populated hexagon, find the distance to the nearest hospital, school and drinking-water point (distributed range join, 25 km search radius).
4. **Score** each cell:

   ```
   ratio(h, s)  = min( max(0, d(h, s) - T(s)) / T(s), 3 )
   severity(h)  = population(h) × Σ  w(s) × ratio(h, s)
   ```

   `d` is distance to the nearest facility, `T(s)` the acceptable distance for service `s`, `w(s)` the service weight (equal by default).
5. **Roll up** to talukas and districts, **validate** against an official hospital list, and run a **sensitivity analysis** on thresholds and weights.

The thresholds (hospital 10 km, school 3 km, water point 2 km) are working assumptions, not official standards. Change them in `config/settings.env`.

## 3. Architecture

```
 Raw data                    Prep (Python/bash)             Spark + Sedona (Docker cluster)          Outputs
 ---------                   ------------------             -------------------------------          -------
 MS building tiles  ──┐
 OSM extract        ──┤──>  clean, clip, convert  ──>  H3 index ─> distance join ─> severity  ──>  data/out/*.parquet
 HRSL population    ──┤      to /data/staging           ─> taluka/district roll-up               CSV for Kepler.gl
 Census boundaries  ──┘                                 ─> validation, sensitivity               figures (PNG)
```

Cluster: `spark-master` (also runs the driver), `spark-worker-1`, `spark-worker-2`, all sharing one `/data` folder.
This is a distributed *architecture* on one machine; it does not add compute beyond your laptop's own cores and RAM.

## 4. Tech stack

| Layer | Tools |
|---|---|
| Compute | Apache Spark 3.5.x (standalone), PySpark |
| Spatial | Apache Sedona 1.9.1, H3 |
| Prep | GDAL, Osmium, Rasterio, GeoPandas |
| Storage | Parquet on a shared Docker volume |
| Visualisation | Kepler.gl (H3 layer), Matplotlib |
| Packaging | Docker, Docker Compose |

## 5. Data sources (all free)

| Data | Source |
|---|---|
| Building footprints | Microsoft Global ML Building Footprints (`github.com/microsoft/GlobalMLBuildingFootprints`) |
| Facilities | OpenStreetMap via Geofabrik (`download.geofabrik.de/asia/india.html`) |
| Population | Meta High Resolution Settlement Layer via HDX (`data.humdata.org`, "Pakistan & India: High Resolution Population Density Maps") |
| Boundaries | DataMeet maps (`github.com/datameet/maps`), Census 2011 |
| Validation | Official facility lists on `data.gov.in` |

Check each source's licence page before redistributing derived data. OpenStreetMap data requires attribution: © OpenStreetMap contributors.

## 6. Requirements

- Windows 10/11 with **Docker Desktop (WSL2 backend)** and an Ubuntu WSL distribution
- 16 GB RAM (32 GB recommended), a multi-core CPU, and about 25 GB free disk for a one-district run
- Internet access for downloads and the first Docker build

Keep the project **inside the WSL filesystem** (for example `~/infra-gap`), not under `C:\`; bind mounts from `C:` are slow.

## 7. Setup

1. Cap WSL2 resources in `C:\Users\<you>\.wslconfig` (example for a 16 GB laptop):

   ```ini
   [wsl2]
   memory=10GB
   processors=14
   swap=2GB
   ```

   Then run `wsl --shutdown` in PowerShell and restart Docker Desktop.

2. Create the project files exactly as listed in [`File_Details.md`](File_Details.md).

3. Edit `config/settings.env`: set the bounding box (`BBOX_W/S/E/N`) around your pilot district.

4. Build and start the cluster:

   ```bash
   cd ~/infra-gap
   docker compose up -d --build
   ```

5. Open `http://localhost:8080` and confirm **2 workers ALIVE**.

6. Run the smoke test:

   ```bash
   docker compose exec spark-master spark-submit --driver-memory 1g --executor-memory 2g \
     --total-executor-cores 10 /workspace/src/smoke_test.py
   ```

   It should print Sedona results, list both workers as executor hosts, and read back `1000` rows.

## 8. Run the pipeline

**Prepare data** (run from the project root):

```bash
# Building tiles for the bounding box
docker compose exec spark-master python prep/fetch_buildings.py

# Facilities from OpenStreetMap
docker compose exec spark-master bash prep/prep_osm.sh

# Population: download the HRSL GeoTIFF(s) covering your box from HDX into data/raw/population/, then:
docker compose exec spark-master bash prep/prep_population.sh

# Boundaries: clone DataMeet, inspect columns, then prepare talukas
git clone --depth 1 https://github.com/datameet/maps.git data/raw/boundaries/datameet-maps
docker compose exec spark-master python prep/prep_boundaries.py <path-to-shapefile> --inspect
docker compose exec spark-master python prep/prep_boundaries.py <path-to-shapefile> \
    --district-col <COL> --taluka-col <COL> --state-col <COL> --state Maharashtra

# Optional (for validation): an official hospital CSV with coordinates
docker compose exec spark-master python prep/prep_official.py data/raw/official/hospitals.csv \
    --name-col "<COL>" --lon-col "<COL>" --lat-col "<COL>"
```

**Run all Spark stages:**

```bash
chmod +x scripts/*.sh
scripts/run_all.sh
```

Or run one stage at a time:

```bash
SUBMIT="docker compose exec spark-master spark-submit --driver-memory 1g --executor-memory 2g --total-executor-cores 10"
$SUBMIT /workspace/src/ingest_index.py
$SUBMIT /workspace/src/access_score.py --tag base
$SUBMIT /workspace/src/rollup.py --tag base
$SUBMIT /workspace/src/validate.py --tag base
$SUBMIT /workspace/src/sensitivity.py
$SUBMIT /workspace/src/export_viz.py
docker compose exec spark-master python analysis/make_figures.py
```

**Benchmark (local vs cluster):** `scripts/benchmark.sh`. Local mode may be faster on one laptop; report what you measure.

## 9. Outputs

| Path | Contents |
|---|---|
| `data/out/hex/` | Hexagon table: population, building count, centroid |
| `data/out/facilities/` | Classified facility points |
| `data/out/severity_<tag>/` | Distances and Gap Severity Score per hexagon |
| `data/out/taluka_<tag>/`, `district_<tag>/` | Ranked talukas and districts |
| `data/out/summary_<tag>.csv` | Distance statistics and population share beyond thresholds |
| `data/out/validation_*.csv` | OSM completeness and false-alarm check |
| `data/out/sensitivity.csv` | Ranking stability under changed thresholds and weights |
| `data/out/timings.csv` | Stage timings (local vs cluster) |
| `data/out/viz/` | CSVs for Kepler.gl |
| `data/out/figures/` | Charts and maps (PNG) |

For the interactive map, open `https://kepler.gl/demo`, load `data/out/viz/severity_hex.csv`, add an **H3** layer on `hex_id`, and colour by `severity`.

## 10. Configuration

All settings live in `config/settings.env`.

| Variable | Default | Meaning |
|---|---|---|
| `BBOX_W/S/E/N` | 73.0 / 17.5 / 75.5 / 19.5 | Study box in degrees (generous box around the pilot district) |
| `H3_RES` | 8 | H3 resolution |
| `SEARCH_RADIUS_M` | 25000 | Nearest-facility search radius |
| `T_HOSP_M`, `T_SCHOOL_M`, `T_WATER_M` | 10000, 3000, 2000 | Distance thresholds |

If you have different hardware, change `mem_limit`, `cpus`, `--cores`, and `--memory` together in `docker-compose.yml`.

## 11. Project structure

```
infra-gap/
├── Dockerfile, docker-compose.yml, spark-defaults.conf
├── config/settings.env
├── prep/        data download and preparation scripts
├── src/         Spark + Sedona jobs
├── analysis/    figure generation
├── scripts/     run_all.sh, benchmark.sh
└── data/        raw, staging, out (generated, git-ignored)
```

The full tree and every file's code are in [`File_Details.md`](File_Details.md).

## 12. Limitations

- **OSM completeness:** a missing facility on the map is not necessarily missing on the ground. The validation step estimates this; it does not remove it.
- **Straight-line distance:** distance is Euclidean, not travel time. Terrain and roads can make real access worse.
- **Modelled population:** HRSL is a model, not a census count.
- **Facility quality:** a hospital counts the same regardless of size or staffing; the score measures proximity only.
- **Thresholds are assumptions:** see `data/out/sensitivity.csv` for how much the ranking depends on them.
- **Scope:** a one-district pilot fits a 16 GB laptop; a full-state run needs more disk and time.
- **Status:** the code has not been run end to end by its author at the time of writing; run the smoke test first and expect to adjust paths and column names.

## 13. Troubleshooting

| Symptom | Fix |
|---|---|
| Fewer than 2 workers at `localhost:8080` | `docker compose logs spark-worker-1`; lower `--memory` or raise `mem_limit` |
| `Initial job has not accepted any resources` | Executor memory exceeds worker memory; lower `--executor-memory` |
| Container exits with code 137 | Out of memory; raise `mem_limit` and WSL `memory=`, or shrink the study box |
| Very slow jobs | Project is under `/mnt/c`; move it into the WSL filesystem |
| `ClassNotFoundException` for Sedona | Rebuild: `docker compose build --no-cache` |
| Permission errors on `data/` | `sudo chown -R $USER data` in WSL |

## 14. References

- Zaharia, M. et al. (2016). Apache Spark: A Unified Engine for Big Data Processing. *Communications of the ACM*, 59(11).
- Yu, J., Zhang, Z., Sarwat, M. (2019). Spatial data management in Apache Spark: the GeoSpark perspective and beyond. *GeoInformatica*, 23.
- Apache Sedona documentation: https://sedona.apache.org
- Uber H3: https://h3geo.org
- Haklay, M., Weber, P. (2008). OpenStreetMap: User-Generated Street Maps. *IEEE Pervasive Computing*, 7(4).
- Barrington-Leigh, C., Millard-Ball, A. (2017). The world's user-generated road map is more than 80% complete. *PLoS ONE*, 12(8).

## 15. Licence

Add a licence of your choice for the code. Data keeps its own licences (see Section 5).
