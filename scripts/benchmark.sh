#!/usr/bin/env bash
# Fair timing: local mode gets the same resources as the cluster (10 cores, 7 GB) in its own container.
# The cluster is stopped first so local mode is not competing for the 10 GB WSL memory.
set -euo pipefail

echo "== local mode (cluster stopped)"
docker compose stop
for i in 1 2; do
  docker run --rm --cpus 10 --memory 7g \
    --env-file config/settings.env \
    -v "$PWD/data:/data" -v "$PWD:/workspace" infragap-spark \
    spark-submit --master "local[10]" --driver-memory 5g \
      --conf spark.driver.host=localhost --conf spark.driver.bindAddress=127.0.0.1 \
      /workspace/src/access_score.py --tag bench_local
done

echo "== cluster mode"
docker compose up -d
sleep 15
for i in 1 2; do
  docker compose exec -T spark-master spark-submit \
    --driver-memory 1g --executor-memory 2g --total-executor-cores 10 \
    /workspace/src/access_score.py --tag bench_cluster
done

docker compose exec -T spark-master python /workspace/analysis/make_figures.py
echo "Timings are in data/out/timings.csv; runtime chart in data/out/figures/fig_runtime.png"