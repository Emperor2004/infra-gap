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