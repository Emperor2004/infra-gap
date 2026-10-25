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