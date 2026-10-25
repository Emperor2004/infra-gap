#!/usr/bin/env bash
# Runs every Spark stage in order. Run the prep steps from README.md first (data must be in data/staging).
set -euo pipefail

EXEC="docker compose exec -T spark-master"
SUBMIT="$EXEC spark-submit --driver-memory 1g --executor-memory 2g --total-executor-cores 10"

echo "== 1/7 smoke test";   $SUBMIT /workspace/src/smoke_test.py
echo "== 2/7 ingest+index"; $SUBMIT /workspace/src/ingest_index.py
echo "== 3/7 access+score"; $SUBMIT /workspace/src/access_score.py --tag base
echo "== 4/7 rollup";       $SUBMIT /workspace/src/rollup.py --tag base

if [ -f data/staging/official.csv ]; then
  echo "== 5/7 validate";   $SUBMIT /workspace/src/validate.py --tag base
else
  echo "== 5/7 validate skipped (no data/staging/official.csv)"
fi

echo "== 6/7 sensitivity";  $SUBMIT /workspace/src/sensitivity.py
echo "== 7/7 export+figures"
$SUBMIT /workspace/src/export_viz.py
$EXEC python /workspace/analysis/make_figures.py
echo "Done. Outputs: data/out/ (figures in data/out/figures, CSVs in data/out/viz)"