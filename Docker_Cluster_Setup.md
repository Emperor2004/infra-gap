# Docker Cluster Setup (replaces the three VMs)

Three containers on one Windows laptop: `spark-master` (also runs your driver), `spark-worker-1`, `spark-worker-2`.
Everything from Section 6 onward of `Implementation_Plan_Infrastructure_Gap_Mapping.md` still applies, with the path changes in Section 6 below.

---

## 1. What you gain and what you do not

- **Gain:** no three guest operating systems (saves roughly 3 to 6 GB of RAM), a cluster that starts in seconds, and a setup that is reproducible from two files.
- **No gain in compute:** the containers share the same CPU cores and RAM as a single process would. A plain `local[*]` run uses all your cores with no network or serialisation overhead, so it will usually be equal or faster. Say this honestly in the report: the container cluster demonstrates the distributed architecture, not extra hardware.
- **No HDFS here:** the plan uses a shared folder instead. Add Hadoop containers only if your faculty requires HDFS (Section 8).

---

## 2. Prerequisites

| Item | Requirement |
|---|---|
| Windows | 10 or 11, virtualisation enabled in BIOS |
| Docker Desktop | with the **WSL2 backend** |
| WSL2 | Ubuntu distribution installed (`wsl --install -d Ubuntu`) |
| RAM | 16 GB minimum, 32 GB recommended |
| Disk | 60 GB free, on an SSD |

**Keep the project inside the WSL filesystem** (for example `~/infra-gap` in the Ubuntu terminal), not under `C:\`. Bind mounts from `C:` (`/mnt/c`) are much slower and will make Spark jobs crawl.

---

## 3. Cap WSL2 memory and CPUs

Docker Desktop runs inside WSL2, which by default takes a large share of your RAM. Create `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
memory=10GB
processors=14
swap=2GB
```

Then run in PowerShell: `wsl --shutdown` and reopen Docker Desktop.

Sizing (give Windows at least 4 GB):

| Laptop RAM | `memory=` | Master+driver | Each worker (container limit / Spark memory / executor) |
|---|---|---|---|
| 16 GB (your laptop) | 10GB | 2g | 3.5g / 2.5g / 2g |
| 32 GB | 24GB | 3g | 9g / 7g / 6g |

Cores: your i7-12700H has 20 logical processors. Give WSL 14, each worker 5, and the master 2. That leaves Windows 6.

---

## 3b. Your laptop (Core i7-12700H, 16 GB RAM, about 86 GB free disk)

| Resource | Budget | Why |
|---|---|---|
| RAM | WSL2 `memory=10GB`; Windows keeps about 5.5 GB | Windows plus a browser needs 4 to 5 GB. Going above 10 GB makes Windows itself swap. |
| Containers | master 2 GB, workers 3.5 GB each (9 GB total) | Leaves about 1 GB for Docker's own processes. |
| Spark memory | workers offer 2.5 GB; executors use 2 GB | Executor overhead (about 10%) must fit inside the container limit. |
| CPU | WSL 14 of 20 threads; workers 5 each, master 2 | Windows keeps 6 threads. Your CPU mixes performance and efficiency cores, so timings vary run to run. |
| Disk | Budget about 25 GB: Docker image 3 GB, WSL disk growth, pilot data 5 to 10 GB | Only about 86 GB is free, so a full-state run is not realistic. Use **one district**. |
| GPU | Not used | Spark and Sedona are CPU-only. |

Before you start:
- Plug the laptop in and set Windows power mode to **Best performance**; on battery the CPU throttles and timings become meaningless.
- Close browsers and heavy apps during runs.
- Check disk use anytime with `docker system df`; free space with `docker system prune` (only removes unused items).
- Take timings on a quiet machine and run each benchmark twice.

## 4. Files

Create this layout in WSL:

```
~/infra-gap/
  Dockerfile
  docker-compose.yml
  spark-defaults.conf
  src/        (the scripts from the plan)
  data/       (shared folder: raw data, staging, outputs)
```

### Dockerfile

```dockerfile
FROM eclipse-temurin:11-jdk-jammy

ARG SPARK_VER=3.5.7
ARG SEDONA_VER=1.9.1
ARG GEOTOOLS_VER=1.9.1-33.5

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip curl ca-certificates procps gdal-bin osmium-tool \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://archive.apache.org/dist/spark/spark-${SPARK_VER}/spark-${SPARK_VER}-bin-hadoop3.tgz \
      | tar xz -C /opt && mv /opt/spark-${SPARK_VER}-bin-hadoop3 /opt/spark

RUN curl -fsSL -o /opt/spark/jars/sedona-spark-shaded-3.5_2.12-${SEDONA_VER}.jar \
      https://repo1.maven.org/maven2/org/apache/sedona/sedona-spark-shaded-3.5_2.12/${SEDONA_VER}/sedona-spark-shaded-3.5_2.12-${SEDONA_VER}.jar \
 && curl -fsSL -o /opt/spark/jars/geotools-wrapper-${GEOTOOLS_VER}.jar \
      https://repo1.maven.org/maven2/org/datasyslab/geotools-wrapper/${GEOTOOLS_VER}/geotools-wrapper-${GEOTOOLS_VER}.jar

RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir pyspark==${SPARK_VER} apache-sedona==${SEDONA_VER} \
      shapely attrs pandas pyarrow geopandas pyogrio h3 mercantile rasterio requests tqdm scipy

ENV SPARK_HOME=/opt/spark \
    PYSPARK_PYTHON=/opt/venv/bin/python \
    PATH=/opt/spark/bin:/opt/venv/bin:$PATH

COPY spark-defaults.conf /opt/spark/conf/spark-defaults.conf
WORKDIR /workspace
```

Set `SPARK_VER` to the latest 3.5.x patch from spark.apache.org if 3.5.7 is not available.

### spark-defaults.conf

```
spark.master                   spark://spark-master:7077
spark.serializer               org.apache.spark.serializer.KryoSerializer
spark.kryo.registrator         org.apache.sedona.core.serde.SedonaKryoRegistrator
spark.driver.host              spark-master
spark.driver.bindAddress       0.0.0.0
spark.sql.shuffle.partitions   40
spark.sql.adaptive.enabled     true
spark.eventLog.enabled         true
spark.eventLog.dir             /data/spark-events
```

### docker-compose.yml

```yaml
x-spark: &spark
  build: .
  image: infragap-spark
  volumes:
    - ./data:/data
    - ./src:/workspace/src

services:
  spark-master:
    <<: *spark
    container_name: spark-master
    hostname: spark-master
    command: ["/opt/spark/bin/spark-class", "org.apache.spark.deploy.master.Master",
              "--host", "spark-master", "--port", "7077", "--webui-port", "8080"]
    ports: ["8080:8080", "4040:4040"]
    mem_limit: 2g
    cpus: 2

  spark-worker-1:
    <<: *spark
    container_name: spark-worker-1
    hostname: spark-worker-1
    depends_on: [spark-master]
    command: ["/opt/spark/bin/spark-class", "org.apache.spark.deploy.worker.Worker",
              "--cores", "5", "--memory", "2500m", "--webui-port", "8081", "spark://spark-master:7077"]
    ports: ["8081:8081"]
    mem_limit: 3500m
    cpus: 5

  spark-worker-2:
    <<: *spark
    container_name: spark-worker-2
    hostname: spark-worker-2
    depends_on: [spark-master]
    command: ["/opt/spark/bin/spark-class", "org.apache.spark.deploy.worker.Worker",
              "--cores", "5", "--memory", "2500m", "--webui-port", "8081", "spark://spark-master:7077"]
    ports: ["8082:8081"]
    mem_limit: 3500m
    cpus: 5
```

The values above are set for your laptop (Core i7-12700H, 16 GB; see Section 3b). Adjust `mem_limit`, `cpus`, `--cores`, and `--memory` together.

---

## 5. Start, test, run

```bash
cd ~/infra-gap
mkdir -p data/spark-events data/infra/raw data/infra/staging data/infra/out src
docker compose up -d --build        # first build downloads Spark and Python packages (several minutes)
docker compose ps
```

Open `http://localhost:8080`: you should see **2 workers ALIVE**.

Run the smoke test from the plan (Section 5 of the main plan) with the driver in the master container:

```bash
docker compose exec spark-master spark-submit \
  --py-files /workspace/src/common.py \
  --driver-memory 1g --executor-memory 2g --total-executor-cores 10 \
  /workspace/src/00_smoke_test.py
```

Pass criteria: the Sedona queries return values and `executor hosts` lists both workers (`spark-worker-1`, `spark-worker-2`). The HDFS part of the smoke test will fail, so change it to write to `/data/infra/staging/smoke`.

Driver UI at `http://localhost:4040` while a job runs. Stop everything with `docker compose down`.

---

## 6. Changes to the main plan's code and paths

| Main plan | Docker version |
|---|---|
| Sections 3, 4, 5 (VM setup, installs, start-all) | Replaced by Sections 2 to 5 of this file |
| `hdfs://h-primary:9000/...` in every script | `/data/...` (shared folder, same path in all containers) |
| `hdfs dfs -put file /infra/raw/...` | copy the file into `./data/infra/raw/...` |
| `spark-submit ... script.py` | `docker compose exec spark-master spark-submit ... /workspace/src/script.py` |
| Prep tools on the primary (osmium, GDAL, rasterio, geopandas) | run them inside the master container: `docker compose exec spark-master bash` |
| `--total-executor-cores 6`, `--executor-memory 4g` | `10` and `2g` (your 16 GB laptop), or `10` and `6g` (32 GB laptop) |

To convert the scripts quickly:

```bash
sed -i 's#hdfs://h-primary:9000#/data#g' src/*.py
```

Because every container sees `/data`, executors read and write the same files. Do not put the data on `C:\`.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Only 0 or 1 workers on port 8080 | Worker started before master, or crashed (out of memory) | `docker compose logs spark-worker-1`; raise limits or lower `--memory` |
| `Initial job has not accepted any resources` | Executor memory larger than worker memory | Lower `--executor-memory` below the worker's `--memory` |
| Container killed (exit 137) | Out of memory for the container limit | Increase `mem_limit` and `memory=` in `.wslconfig`, or shrink the job scope |
| Workers cannot reach driver | Driver host not resolvable | Keep `spark.driver.host=spark-master` and run `spark-submit` inside `spark-master` |
| Jobs very slow | Data under `/mnt/c` | Move the project into the WSL filesystem |
| Laptop freezes | WSL2 memory too high | Lower `memory=` and `processors=`, run `wsl --shutdown` |
| `ClassNotFoundException` for Sedona | Image built without the jars | Rebuild: `docker compose build --no-cache` |

---

## 8. Optional: HDFS in containers

Only add this if your faculty requires HDFS. It adds a NameNode and two DataNodes (about 3 extra GB of RAM), plus configuration work, and the pipeline does not need it. If you add it, use the Apache Hadoop 3.3.6 image from Docker Hub, point `fs.defaultFS` at the NameNode, and set `HADOOP_CONF_DIR` in the Spark image. Then the original `hdfs://` paths from the main plan work again. Test with `hdfs dfsadmin -report` before running any job.

---

## 9. Benchmark note for the report

Run the same stage three ways and record the times: `--master "local[*]"` inside the master container, the 2-worker cluster, and (optional) a single worker. [Expect] local mode to be as fast or faster on one laptop; state that, and explain that the cluster shows how the same code scales to separate machines.
