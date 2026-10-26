# VM Cluster Setup (VMware Workstation, 3 VMs)

Replaces `Docker_Cluster_Setup.md`. Same project, same code, different cluster.
Stack: Ubuntu 22.04 Server, OpenJDK 11, Hadoop 3.3.6 (HDFS + YARN, for Lab 1), Spark 3.5.x standalone + Sedona 1.9.1 (for the project).

Assumptions (change if yours differ): user `h-user` on all VMs; hostnames `h-primary`, `h-secondary1`, `h-secondary2` (as in the Lab 1 PDF); VMs already exist with Ubuntu, Java 11 and Hadoop 3.3.6 installed at `/usr/local/hadoop`.

---

## 1. Read this first

| Fact | Consequence |
|---|---|
| Three VMs on one laptop share the same CPU, RAM and SSD. | No extra compute. Local mode on one VM can be as fast or faster. State this in the report. |
| Three guest OSs cost RAM that containers did not. | VM sizes in Section 2 are tight on a 16 GB laptop. Run **either** YARN **or** Spark jobs, not both at once. |
| Docker Desktop / WSL2 / Hyper-V on the host force VMware onto the Windows Hypervisor Platform. | VMs get noticeably slower. If timings look bad, see Section 11. |
| The project code reads and writes `/data` with plain Python (`os.path`, `pandas`, `osmium`, GDAL). Workers cannot see a folder that exists on the primary only. | **Use an NFS share mounted at `/data` on all three VMs.** Code stays unchanged. HDFS stays installed for Lab 1; pointing the pipeline at HDFS needs code edits (Section 10). |
| The Lab 1 PDF has errors for this stack. | Corrections are in Section 12. |

---

## 2. VM sizing (16 GB laptop, i7-12700H, about 86 GB free disk)

Shut a VM down before changing hardware.

| VM | Role | RAM | vCPU | Disk (thin) |
|---|---|---|---|---|
| `h-primary` | NameNode, YARN RM, Spark master + driver, NFS server, data prep | 4096 MB | 4 | 40 GB |
| `h-secondary1` | DataNode, NodeManager, Spark worker | 3584 MB | 4 | 20 GB |
| `h-secondary2` | same | 3584 MB | 4 | 20 GB |

Total 11 GB RAM; Windows keeps about 5 GB. Remove sound, USB, printer and 3D acceleration from each VM. Use **Power mode: Best performance**, laptop plugged in, browsers closed during runs.

Spark budget: workers offer 4 cores and 2 GB each; run jobs with `--executor-memory 1500m --total-executor-cores 8 --driver-memory 1g`.

---

## 3. Network: NAT with static IPs

Do **not** use Bridged (Lab 1 Step 1) for this: on college or hotspot Wi-Fi the DHCP addresses change and VM-to-VM traffic can be blocked, which breaks Hadoop and Spark.

1. VMware: **Edit > Virtual Network Editor**, note the **VMnet8 (NAT)** subnet (example below: `192.168.150.0/24`, gateway `.2`). Set every VM adapter to **NAT**.
2. On each VM find the NIC name: `ip -br a` (usually `ens33`).
3. `sudo nano /etc/netplan/00-installer-config.yaml` (file name may differ; `ls /etc/netplan`). Use `.101`, `.102`, `.103` for the three VMs:

```yaml
network:
  version: 2
  ethernets:
    ens33:
      dhcp4: false
      addresses: [192.168.150.101/24]
      routes:
        - to: default
          via: 192.168.150.2
      nameservers:
        addresses: [192.168.150.2, 8.8.8.8]
```

```bash
sudo chmod 600 /etc/netplan/*.yaml && sudo netplan apply
```

4. `/etc/hosts` on **all three** (replace the file body; keep nothing that maps the hostname to `127.0.1.1`):

```
127.0.0.1 localhost
192.168.150.101 h-primary
192.168.150.102 h-secondary1
192.168.150.103 h-secondary2
```

The `127.0.1.1 <hostname>` line that Ubuntu adds is the most common cause of "DataNodes/workers cannot register": the NameNode and Spark master bind to loopback. Delete it.

5. `sudo ufw status` should say `inactive`. If it is active: `sudo ufw allow from 192.168.150.0/24`.
6. Windows can reach the VMs on NAT by IP, so the web UIs open from the host browser.

---

## 4. VM identity (if the VMs were cloned)

Cloning must be a **full clone** from a powered-off VM. VMware assigns new MACs automatically. On each clone:

```bash
sudo hostnamectl set-hostname h-secondary1        # h-secondary2 on the other one
sudo rm -f /etc/machine-id && sudo systemd-machine-id-setup
sudo reboot
```

If the VMs are independent installs, skip the machine-id lines. Either way check that `id h-user` prints the **same uid and gid on all three**; NFS permissions depend on it.

---

## 5. Environment (all three VMs)

`/etc/environment` (read by non-interactive SSH sessions, which the start scripts use). Replace the content:

```
PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/usr/local/hadoop/bin:/usr/local/hadoop/sbin"
JAVA_HOME="/usr/lib/jvm/java-11-openjdk-amd64"
```

Check the path: `readlink -f $(which java)` should end in `.../java-11-openjdk-amd64/bin/java`. Use the JDK directory, not `/jre` (Lab 1 Step 11 is the Java 8 layout).

`~/.bashrc` of `h-user` on **all three** (append):

```bash
export HADOOP_HOME=/usr/local/hadoop
export HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop
export HADOOP_MAPRED_HOME=$HADOOP_HOME
export PDSH_RCMD_TYPE=ssh
export SPARK_HOME=/opt/spark
export PATH=/opt/venv/bin:$SPARK_HOME/bin:$PATH
# project settings (primary only matters, harmless elsewhere)
[ -f ~/infra-gap/config/settings.env ] && { set -a; . ~/infra-gap/config/settings.env; set +a; }
```

`source ~/.bashrc`. Spark's `sbin` is deliberately **not** on `PATH`: Spark and Hadoop both ship `start-all.sh`, and the wrong one runs silently. Call Spark's with the full path.

---

## 6. SSH and Hadoop configuration

Packages on all VMs: `sudo apt install -y openssh-server pdsh rsync`.

On `h-primary` as `h-user`:

```bash
ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa
for h in h-primary h-secondary1 h-secondary2; do ssh-copy-id -o StrictHostKeyChecking=accept-new h-user@$h; done
for h in h-primary h-secondary1 h-secondary2; do ssh $h hostname; done   # must print 3 names, no prompts
```

Hadoop files in `/usr/local/hadoop/etc/hadoop/` on **h-primary**, then copy to the others. `/usr/local/hadoop` must be owned by `h-user` on all three (`sudo chown -R h-user:h-user /usr/local/hadoop`).

`hadoop-env.sh`:

```bash
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export HADOOP_HEAPSIZE_MAX=512m
```

`core-site.xml` (inside `<configuration>`):

```xml
<property><name>fs.defaultFS</name><value>hdfs://h-primary:9000</value></property>
```

`hdfs-site.xml`:

```xml
<property><name>dfs.namenode.name.dir</name><value>file:///usr/local/hadoop/data/nameNode</value></property>
<property><name>dfs.datanode.data.dir</name><value>file:///usr/local/hadoop/data/dataNode</value></property>
<property><name>dfs.replication</name><value>2</value></property>
```

`workers` (replace content):

```
h-secondary1
h-secondary2
```

`mapred-site.xml` (needed for the Lab 1 MapReduce test; without it jobs fail with `MRAppMaster` class errors):

```xml
<property><name>mapreduce.framework.name</name><value>yarn</value></property>
<property><name>mapreduce.application.classpath</name>
  <value>/usr/local/hadoop/share/hadoop/mapreduce/*:/usr/local/hadoop/share/hadoop/mapreduce/lib/*</value></property>
<property><name>yarn.app.mapreduce.am.env</name><value>HADOOP_MAPRED_HOME=/usr/local/hadoop</value></property>
<property><name>mapreduce.map.env</name><value>HADOOP_MAPRED_HOME=/usr/local/hadoop</value></property>
<property><name>mapreduce.reduce.env</name><value>HADOOP_MAPRED_HOME=/usr/local/hadoop</value></property>
<property><name>yarn.app.mapreduce.am.resource.mb</name><value>512</value></property>
<property><name>mapreduce.map.memory.mb</name><value>512</value></property>
<property><name>mapreduce.reduce.memory.mb</name><value>512</value></property>
```

`yarn-site.xml` (**on all three**, including the primary; the PDF only edits the secondaries):

```xml
<property><name>yarn.resourcemanager.hostname</name><value>h-primary</value></property>
<property><name>yarn.nodemanager.aux-services</name><value>mapreduce_shuffle</value></property>
<property><name>yarn.nodemanager.resource.memory-mb</name><value>2048</value></property>
<property><name>yarn.scheduler.maximum-allocation-mb</name><value>2048</value></property>
<property><name>yarn.scheduler.minimum-allocation-mb</name><value>256</value></property>
<property><name>yarn.nodemanager.vmem-check-enabled</name><value>false</value></property>
```

Create data dirs and copy the config:

```bash
mkdir -p /usr/local/hadoop/data/nameNode /usr/local/hadoop/data/dataNode
for h in h-secondary1 h-secondary2; do
  ssh $h "mkdir -p /usr/local/hadoop/data/dataNode"
  rsync -a /usr/local/hadoop/etc/hadoop/ $h:/usr/local/hadoop/etc/hadoop/
done
```

---

## 7. Start and verify Hadoop (Lab 1)

On `h-primary` (format **once only**; reformatting later orphans the DataNodes):

```bash
hdfs namenode -format
start-dfs.sh
start-yarn.sh
jps
hdfs dfsadmin -report | grep -E "Live datanodes|Name:"
```

| Node | `jps` must show |
|---|---|
| h-primary | NameNode, SecondaryNameNode, ResourceManager |
| h-secondary1/2 | DataNode, NodeManager |

Check each from a secondary with `ssh h-secondary1 jps` (needs `jps` on the non-interactive PATH; if not found use `/usr/lib/jvm/java-11-openjdk-amd64/bin/jps`).

Web UIs from Windows: `http://192.168.150.101:9870` (HDFS, 2 live datanodes), `http://192.168.150.101:8088` (YARN, 2 nodes). Take the Lab 1 screenshots here.

End-to-end test:

```bash
hdfs dfs -mkdir -p /user/h-user/input
hdfs dfs -put $HADOOP_HOME/etc/hadoop/*.xml /user/h-user/input
hadoop jar $HADOOP_HOME/share/hadoop/mapreduce/hadoop-mapreduce-examples-3.3.6.jar wordcount /user/h-user/input /user/h-user/out
hdfs dfs -cat /user/h-user/out/part-r-00000 | head
```

Before running Spark jobs: `stop-yarn.sh` (frees about 1.5 GB across the VMs). Leave HDFS running or `stop-dfs.sh` too if RAM is short.

---

## 8. Shared `/data` over NFS

On `h-primary`:

```bash
sudo apt install -y nfs-kernel-server
sudo mkdir -p /data && sudo chown h-user:h-user /data
echo "/data 192.168.150.0/24(rw,sync,no_subtree_check)" | sudo tee -a /etc/exports
sudo exportfs -ra
mkdir -p /data/spark-events /data/raw /data/staging /data/out
```

On each secondary:

```bash
sudo apt install -y nfs-common
sudo mkdir -p /data
echo "h-primary:/data /data nfs rw,hard,noatime,_netdev 0 0" | sudo tee -a /etc/fstab
sudo mount -a && df -h /data
touch /data/test_from_$(hostname) && ls /data      # visible on all three VMs
```

Use `sync`, not `async`: Spark's output commit renames files and `async` can lose them if a VM stops. Shuffle files stay on each worker's local disk (`spark.local.dir`, Section 9), so only reads and final writes cross NFS.

---

## 9. Spark + Sedona

The commands below are automated by `cluster/install_spark.sh` in `File_Details.md` (plus the config files in `cluster/`). Use either, not both.

On `h-primary` (software installed once, then copied):

```bash
sudo apt install -y python3 python3-venv python3-pip curl git gdal-bin osmium-tool
SPARK_VER=3.5.7; SEDONA_VER=1.9.1; GEOTOOLS_VER=1.9.1-33.5
curl -fsSL https://archive.apache.org/dist/spark/spark-$SPARK_VER/spark-$SPARK_VER-bin-hadoop3.tgz | sudo tar xz -C /opt
sudo mv /opt/spark-$SPARK_VER-bin-hadoop3 /opt/spark && sudo chown -R h-user:h-user /opt/spark
curl -fsSL -o /opt/spark/jars/sedona-spark-shaded-3.5_2.12-$SEDONA_VER.jar \
  https://repo1.maven.org/maven2/org/apache/sedona/sedona-spark-shaded-3.5_2.12/$SEDONA_VER/sedona-spark-shaded-3.5_2.12-$SEDONA_VER.jar
curl -fsSL -o /opt/spark/jars/geotools-wrapper-$GEOTOOLS_VER.jar \
  https://repo1.maven.org/maven2/org/datasyslab/geotools-wrapper/$GEOTOOLS_VER/geotools-wrapper-$GEOTOOLS_VER.jar
sudo mkdir -p /opt/venv && sudo chown h-user:h-user /opt/venv
python3 -m venv /opt/venv
/opt/venv/bin/pip install --upgrade pip
/opt/venv/bin/pip install pyspark==$SPARK_VER apache-sedona==$SEDONA_VER shapely attrs pandas pyarrow \
  geopandas pyogrio "h3>=4" mercantile rasterio requests tqdm scipy matplotlib
```

If `3.5.7` is not on archive.apache.org, use the latest 3.5.x patch and set the same version for `pyspark`. The Spark download is the `bin-hadoop3` build: it bundles its own Hadoop client and talks to your 3.3.6 HDFS without extra setup.

Copy to the workers (same paths everywhere; `h-user` must own them):

```bash
for h in h-secondary1 h-secondary2; do
  ssh $h "sudo mkdir -p /opt/spark /opt/venv /var/tmp/spark && sudo chown h-user:h-user /opt/spark /opt/venv /var/tmp/spark"
  rsync -a /opt/spark/ $h:/opt/spark/
  rsync -a /opt/venv/  $h:/opt/venv/
done
mkdir -p /var/tmp/spark
```

`/opt/spark/conf/spark-env.sh` (copy to all three, `cp spark-env.sh.template` first):

```bash
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export SPARK_MASTER_HOST=h-primary
export SPARK_WORKER_CORES=4
export SPARK_WORKER_MEMORY=2g
export PYSPARK_PYTHON=/opt/venv/bin/python
export PYSPARK_DRIVER_PYTHON=/opt/venv/bin/python
```

`/opt/spark/conf/workers` (primary only):

```
h-secondary1
h-secondary2
```

`/opt/spark/conf/spark-defaults.conf` (replaces the Docker version; copy to all three):

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

Distribute the two conf files: `for h in h-secondary1 h-secondary2; do scp /opt/spark/conf/{spark-env.sh,spark-defaults.conf} $h:/opt/spark/conf/; done`

Start and test:

```bash
/opt/spark/sbin/start-all.sh          # full path on purpose
# http://192.168.150.101:8080  -> 2 workers ALIVE
spark-submit --driver-memory 1g --executor-memory 1500m --total-executor-cores 8 /workspace/src/smoke_test.py
```

Stop with `/opt/spark/sbin/stop-all.sh`. Driver UI: `http://192.168.150.101:4040` while a job runs.

Pass criteria for the smoke test: Sedona queries return values and the executor hosts list both `h-secondary1` and `h-secondary2`. The part of the smoke test that writes and reads 1000 rows must write under `/data/...` (it already does if it uses `p(...)`).

---

## 10. Project files and what changes

Put the project on `h-primary` and make the Docker-era paths work without editing any script:

```bash
mkdir -p ~/infra-gap && cd ~/infra-gap          # create the files from File_Details.md here
sudo ln -s ~/infra-gap /workspace               # /workspace/src/... paths keep working
ln -s /data ~/infra-gap/data                    # data/staging/official.csv style paths keep working
```

| Docker version | VM version |
|---|---|
| `docker compose exec spark-master <cmd>` | run `<cmd>` directly on `h-primary` as `h-user` |
| `docker compose up -d` / `down` | `/opt/spark/sbin/start-all.sh` / `stop-all.sh` |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.wslconfig` | not used |
| `spark.master spark://spark-master:7077`, `spark.driver.host spark-master` | `h-primary` (Section 9) |
| `--executor-memory 2g --total-executor-cores 10` | `--executor-memory 1500m --total-executor-cores 8` |
| env from `config/settings.env` via compose | sourced in `~/.bashrc` (Section 5) |
| `sudo chown -R $USER data` | not needed (you own `/data`) |

Data prep runs on the primary with the same commands as the README, minus the `docker compose exec spark-master` prefix, for example `python prep/fetch_buildings.py` and `bash prep/prep_osm.sh`.

**Why NFS and not HDFS for the pipeline.** [Likely] these places would need edits to use `hdfs://`: `common.py` (`timed()` writes `timings.csv` with `open()`), every `os.makedirs` / `os.path.exists` in `prep/` and `src/`, `pd.read_parquet` in `analysis/make_figures.py`, and the prep tools (osmium, GDAL, rasterio) which cannot read `hdfs://` directly. If your faculty requires HDFS for the project, the cheap compromise is: keep NFS for the pipeline, and after staging run `hdfs dfs -put /data/staging /infra/staging` and read one stage (for example the hex table) from `hdfs://h-primary:9000/infra/...` in a demo script. Do not convert the whole pipeline.

### `scripts/run_all.sh` (replacement)

```bash
#!/usr/bin/env bash
# Runs every Spark stage in order on h-primary. Run the prep steps first (data must be in /data/staging).
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

### `scripts/benchmark.sh` (replacement)

```bash
#!/usr/bin/env bash
# Local mode (primary VM only, 4 vCPU) vs the 2-worker cluster (8 cores). Run with YARN stopped.
# Not a like-for-like comparison: local has 4 cores, the cluster has 8 plus NFS/network overhead. Say so in the report.
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
echo "Timings: /data/out/timings.csv; chart: /data/out/figures/fig_runtime.png"
```

Run order for the project: Sections 3 to 9 once, then `chmod +x scripts/*.sh`, prep steps, `scripts/run_all.sh`, `scripts/benchmark.sh`.

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| 0 DataNodes live / 0 workers ALIVE | `127.0.1.1 <hostname>` in `/etc/hosts`, or wrong hostnames | Section 3 step 4; `ss -ltnp \| grep -E "9000\|7077"` must show the VM IP or `*`, not `127.0.1.1` |
| `Incompatible clusterIDs` on DataNode | NameNode formatted twice | Stop HDFS; delete `/usr/local/hadoop/data/dataNode/*` on both secondaries; restart |
| `pdsh@...: connect: Connection refused` or `rcmd` errors | `PDSH_RCMD_TYPE` not set | Section 5 |
| `JAVA_HOME is not set` from start scripts over SSH | Only set in `.bashrc` | Set in `/etc/environment` and `hadoop-env.sh`/`spark-env.sh` |
| MapReduce: `Could not find or load main class ...MRAppMaster` | Missing `mapred-site.xml` properties | Section 6 |
| MapReduce job stuck `ACCEPTED` | YARN memory too small or nodes missing | Check `:8088` shows 2 nodes; keep values from Section 6 |
| `Initial job has not accepted any resources` | Executor memory above worker memory, or no workers | `--executor-memory` must be below 2g; check `:8080` |
| Executor lost / VM freezes | RAM exhausted | Stop YARN; lower `--executor-memory` to 1g; check `free -h` in each VM |
| `ClassNotFoundException` for Sedona on workers | Jars not copied | Re-run the `rsync` of `/opt/spark/` |
| `python: not found` or version mismatch on workers | `/opt/venv` not copied or `python3` missing | `rsync /opt/venv/`; `ssh h-secondary1 /opt/venv/bin/python -V` |
| `Permission denied` writing `/data` from a worker | `h-user` uid differs between VMs | Section 4 uid check; align uids |
| `/data` empty or stale on a secondary | NFS not mounted | `mount \| grep /data`; `sudo mount -a` |
| Everything slow vs expectations | VMware running on Windows Hypervisor Platform (WSL2/Docker/Hyper-V active) | Expect it; see below |
| Host freezes | Too much RAM given to VMs | Reduce each VM by 512 MB, close host apps |

If you want native VMware speed, Hyper-V features must be off (`bcdedit /set hypervisorlaunchtype off`, reboot). That disables WSL2 and Docker Desktop until you turn it back on, so decide before you start the benchmark and run all timings in one mode.

---

## 12. Lab 1 PDF: corrections for this stack

| PDF step | Problem | Use instead |
|---|---|---|
| Step 1 | Bridged adapter | NAT with static IPs (Section 3) |
| Step 7 | `openjdk-8-jdk` | `openjdk-11-jdk` (Hadoop 3.3+ supports Java 11 at runtime) |
| Step 8 | Hadoop 3.2.1 URL | `https://archive.apache.org/dist/hadoop/common/hadoop-3.3.6/hadoop-3.3.6.tar.gz` |
| Steps 9 and 11 | `JAVA_HOME` Java 8 paths, `/jre` | `/usr/lib/jvm/java-11-openjdk-amd64` |
| Step 12 | `usermod -aG hadoopuser h-user`: group does not exist | skip it; `chown -R h-user:h-user /usr/local/hadoop` is enough |
| Step 15 and `/etc/hosts` | Leaves `127.0.1.1 <hostname>` | delete that line |
| Step 17 | `ssh-copy-id` to the secondaries only | also to `h-primary` itself (the loop in Section 6) |
| Step 24 | `yarn-site.xml` edited on the secondaries only; no `mapred-site.xml` | Section 6, all nodes |
| Step 22 | `hdfs namenode -format` easy to repeat | once only |

---

## 13. Report wording

- Three VMs demonstrate the distributed architecture (HDFS replication across two DataNodes, Spark executors on two workers). They do not add hardware: all VMs share one laptop's cores, RAM and SSD.
- Run each benchmark stage twice, on a quiet machine, in one host configuration (Section 11), and report what you measured, including a result where local mode wins.
- OSM and population data limitations are in the README; they are unchanged by the cluster.

## 14. Sources

- Hadoop 3.3+ supports Java 8 and Java 11 (runtime only): https://cwiki.apache.org/confluence/display/HADOOP/Hadoop+Java+Versions
- Sedona 1.9.1 on Spark 3.5 requires Java 11; Python 3.10 supported: https://sedona.apache.org/1.9.1/setup/platform/
- Sedona 1.9.1 jar coordinates (`sedona-spark-shaded-3.5_2.12:1.9.1`, `geotools-wrapper:1.9.1-33.5`): https://sedona.apache.org/1.9.1/setup/maven-coordinates/

Not verified: Spark 3.5.7 availability on archive.apache.org, VMware NAT gateway being `.2` on your machine, and the code in `File_Details.md` end to end (it has never been run). The smoke test is the first real check.
