
# Mapping India's Infrastructure Deserts: A Distributed Big Data Analytics Approach

A geospatial Big Data Analytics project that identifies relative infrastructure-access gaps across Maharashtra, India, using distributed processing, H3 hexagonal cells, population estimates, mapped facilities, and administrative boundaries.

> **Disclaimer:** The Gap Severity Score is a project-defined analytical metric, not an official government index. Results depend on the source data, spatial coverage, and assumptions used.

## Table of Contents

- [Project Overview](#project-overview)
- [Problem Statement](#problem-statement)
- [Objectives](#objectives)
- [Study Area and SDGs](#study-area-and-sdgs)
- [Technology Stack](#technology-stack)
- [Project Architecture](#project-architecture)
- [Methodology](#methodology)
- [Gap Severity Score](#gap-severity-score)
- [Results](#results)
- [Validation](#validation)
- [Sensitivity Analysis](#sensitivity-analysis)
- [Visualizations](#visualizations)
- [Project Structure](#project-structure)
- [Environment Setup](#environment-setup)
- [Running the Visualization Script](#running-the-visualization-script)
- [Exporting Results to Windows](#exporting-results-to-windows)
- [Limitations](#limitations)
- [Future Scope](#future-scope)

## Project Overview

Infrastructure availability is not uniform across geographic areas. Some localities may have limited access to essential services even when district-level statistics appear satisfactory.

This project analyzes the relative accessibility of three facility types across Maharashtra:

- Hospitals
- Schools
- Drinking-water points

The study uses H3 hexagonal spatial indexing, facility locations, population and building information, and administrative boundaries. Apache Spark distributes data processing across a three-node Ubuntu virtual-machine cluster, while Apache Sedona provides spatial SQL operations.

The pipeline generates H3-level severity scores, taluka and district summaries, rankings, validation results, sensitivity-analysis results, and visualization-ready CSV files.

## Problem Statement

Traditional administrative averages can hide local infrastructure gaps. A district may appear adequately served overall while some areas remain far from essential facilities.

The project addresses this problem by dividing the study area into hexagonal cells, estimating proximity to mapped facilities, combining normalized access gaps with population, and aggregating results by administrative area.

## Objectives

1. Process geospatial datasets using distributed computing.
2. Represent locations using H3 hexagons at resolution 8.
3. Estimate proximity to hospitals, schools, and drinking-water points.
4. Calculate a population-weighted, multi-service Gap Severity Score.
5. Rank talukas and districts using the defined metric.
6. Cross-check mapped hospital locations against an official hospital reference list.
7. Test ranking stability under alternative thresholds and weights.
8. Generate visualizations for analysis, reporting, and presentations.

## Study Area and SDGs

- **Study area:** Maharashtra, India
- **Primary SDG alignment:** SDG 11 — Sustainable Cities and Communities
- **Related SDGs:** SDG 3 — Good Health and Well-being; SDG 4 — Quality Education; SDG 6 — Clean Water and Sanitation

These indicate the project's thematic alignment; the analysis does not directly calculate official SDG indicators.

## Technology Stack

| Technology | Purpose |
|---|---|
| Apache Spark / PySpark | Distributed data processing |
| Spark SQL | Data transformations and aggregations |
| Apache Sedona | Spatial SQL and geometry operations |
| H3 | Hexagonal spatial indexing |
| Hadoop HDFS | Distributed storage |
| Python | Pipeline implementation and analysis |
| Pandas | CSV export and tabular analysis |
| Matplotlib | Static chart generation |
| Seaborn | Statistical visualizations |
| Ubuntu on VMware | Distributed execution environment |

## Project Architecture

The project follows a staged processing pipeline:

1. **Data ingestion:** Prepare and stage population, building, facility, and administrative-boundary data.
2. **Spatial indexing:** Represent the study area using H3 cells at resolution 8.
3. **Access-distance calculation:** Calculate distances from cell centres to mapped facilities.
4. **Severity scoring:** Apply access thresholds and combine the normalized gaps with population.
5. **Administrative rollups:** Aggregate results by taluka and district.
6. **Sensitivity analysis:** Compare rankings under alternative assumptions.
7. **Validation:** Compare hospital reference records with mapped OpenStreetMap hospitals.
8. **Visualization:** Export CSVs and create charts using Matplotlib and Seaborn.

### Distributed environment

The project uses three Ubuntu VMs:

- `h-primary` — Spark master and driver execution host
- `h-secondary1` — Spark worker
- `h-secondary2` — Spark worker

The Spark master URL used in the current environment is:

```text
spark://<SPARK_MASTER_IP>:7077
```

HDFS is configured at:

```text
hdfs://h-primary:9000
```

These addresses are specific to the current VM setup and may need adjustment in another environment.

## Methodology

### 1. Data preparation

Population and building information, facility points, and taluka boundary geometries are prepared for analysis. Distributed inputs and intermediate datasets are stored in HDFS.

### 2. H3 spatial indexing

The study area is represented by H3 hexagonal cells at **resolution 8**.

The current output contains **321,165 H3 cells**.

### 3. Facility-access distance calculation

For each H3 cell centre, the pipeline calculates the nearest mapped distance for each facility type:

- Hospital
- School
- Drinking water

The search radius is **25,000 metres (25 km)**.

When no facility of a particular type is found within the search radius, its stored distance is set to 25,000 metres.

**Interpretation:** A stored distance of 25 km can mean that no mapped facility was found within the search radius. It does not establish that the true nearest facility is exactly 25 km away.

### 4. Access thresholds

| Facility type | Access threshold |
|---|---:|
| Hospital | 10 km |
| School | 3 km |
| Drinking water | 2 km |

These are project-defined analytical assumptions rather than universal accessibility standards.

### 5. Gap Severity Score

For each facility type \(i\), the normalized gap is calculated as:

\[
g_i = \min\left(\max\left(\frac{d_i-T_i}{T_i},0\right),3\right)
\]

Where:

- \(d_i\) is the stored distance to the facility.
- \(T_i\) is the access threshold for that facility type.
- The gap is zero when the distance is at or below the threshold.
- The normalized gap is capped at 3.

The composite score uses equal weights for the three facility types:

\[
\text{Severity} =
\text{Population}\times
\frac{g_{\text{hospital}}+g_{\text{school}}+g_{\text{water}}}{3}
\]

This formula combines population with normalized access gaps.

A higher score indicates a larger population-weighted access gap under the project's assumptions. It should not be interpreted as a direct count of people without services or as an official measure of deprivation.

### 6. Administrative aggregation

H3-level outputs are joined to taluka and district polygons using spatial operations based on `ST_Within`.

For each assigned administrative area, the pipeline calculates:

- Population
- Total severity
- Severity per person

Severity per person is defined as:

\[
\text{Severity per person} =
\frac{\sum \text{Severity}}{\sum \text{Population}}
\]

This is a population-weighted average of the cell-level severity component across the assigned cells.

**Coverage caveat:** The spatial join does not assign every H3 cell to a taluka. Unassigned cells must be reported separately rather than silently treated as zero or automatically assigned to a nearby taluka.

## Results

The following figures describe the current processed run.

### Processed data

| Metric | Result |
|---|---:|
| H3 cells | 321,165 |
| Population represented by H3 cells | Approximately 132.36 million |
| Buildings represented | 4,164,597 |
| Mapped hospitals | 8,782 |
| Mapped schools | 3,665 |
| Mapped drinking-water points | 190 |
| H3 cells assigned to talukas | 320,548 |
| H3 cells unassigned to talukas | 617 |
| Population assigned to talukas | Approximately 132.21 million |
| Share of population assigned to talukas | Approximately 99.88% |

These counts describe the current inputs and outputs; they do not guarantee complete real-world facility coverage.

### Facility-access results

| Facility type | Median stored distance | 90th percentile | Population beyond threshold |
|---|---:|---:|---:|
| Hospital | 7.52 km | 14.44 km | 16.52% |
| School | 14.81 km | 25 km (search-radius cap) | 71.74% |
| Drinking water | 25 km (search-radius cap) | 25 km (search-radius cap) | 95.03% |

The capped distances mean that the relevant facility was not found within 25 km for those cells. They should not be reported as exact nearest-facility distances.

### Taluka ranking

The current results place the following talukas among the top ten by severity per person:

| Rank | Taluka | District | Severity per person |
|---:|---|---|---:|
| 1 | Jiwati | Chandrapur | 2.250474 |
| 2 | Etapalli | Gadchiroli | 2.186530 |
| 3 | Pombhurna | Chandrapur | 2.186119 |
| 4 | Chikhaldara | Amravati | 2.160152 |
| 5 | Ashti | Wardha | 2.156595 |
| 6 | Kalamb | Yavatmal | 2.140982 |
| 7 | Dhanora | Gadchiroli | 2.125008 |
| 8 | Dharni | Amravati | 2.113155 |
| 9 | Aheri | Gadchiroli | 2.111325 |
| 10 | Deglur | Nanded | 2.102447 |

These are rankings under the current model and input datasets, not definitive rankings of government infrastructure performance.

## Validation

The validation stage compares an official hospital reference list against mapped OpenStreetMap (OSM) hospital locations.

A reference record is counted as matched when an OSM hospital is found within **500 metres**.

### Hospital reference results

| Measure | Result |
|---|---:|
| Official hospital reference records | 2,913 |
| Matched to OSM within 500 m | 2,469 |
| Match percentage | 84.76% |
| Not matched within 500 m | 444 |
| Top 400 severity-ranked hexagons with an official hospital within 10 km | 235 |
| Top 400 without a listed official hospital within 10 km | 165 |

This validation is a hospital-focused cross-check, not definitive validation of the complete severity metric.

An unmatched reference record does not automatically mean that OSM is missing a hospital. Differences may arise from data coverage, coordinate accuracy, facility classification, duplicates, or update dates.

Likewise, a nearby hospital does not mean that a hexagon has adequate access to schools and drinking-water points.

## Sensitivity Analysis

The sensitivity stage compares the top-ten taluka rankings under alternative assumptions.

| Scenario | Top-10 overlap with baseline | Spearman rank correlation |
|---|---:|---:|
| Baseline | 10 of 10 | 1.000 |
| Thresholds reduced by 25% | 9 of 10 | 0.980 |
| Thresholds increased by 25% | 8 of 10 | 0.987 |
| Hospital weight doubled | 10 of 10 | 0.994 |

The results show relatively stable rankings under these tested changes. They do not establish that the source data or rankings are error-free.

## Visualizations

The project uses Pandas, Matplotlib, and Seaborn to generate static charts from the existing CSV outputs.

The visualization script is:

```text
visualize.py
```

It currently generates:

| Output file | Description |
|---|---|
| `01_top15_talukas.png` | Top 15 talukas by severity per person |
| `02_population_vs_severity.png` | Population versus H3-level severity |
| `03_facility_distance_distribution.png` | Distribution of stored distances to facilities |
| `04_population_beyond_thresholds.png` | Population beyond defined access thresholds |
| `05_hospital_validation.png` | Official hospital reference records matched and unmatched to OSM |

The charts are saved at 300 DPI in:

```text
/data/out/visualizations/
```

These are statistical charts. A geographic map requires the H3 cell boundaries or a suitable H3 rendering method; plotting only cell-centre points is not equivalent to displaying hexagon polygons.

## Project Structure

The principal project files include:

```text
infra-gap/
├── src/
│   ├── common.py
│   ├── config.py
│   ├── ingest_index.py
│   ├── access_score.py
│   ├── rollup.py
│   ├── sensitivity.py
│   ├── validate.py
│   └── export_viz.py
├── visualize.py
└── README.md
```

The exact contents of `src/` may include additional scripts and configuration files.

### Important output paths

| Path | Contents |
|---|---|
| `/data/out/severity_base` | H3-level severity data in Parquet format |
| `/data/out/facilities` | Staged facility data |
| `/data/out/taluka_base` | Taluka rollup in Parquet format |
| `/data/out/district_base` | District rollup in Parquet format |
| `/data/out/summary_base.csv` | Overall summary metrics |
| `/data/out/sensitivity.csv` | Sensitivity-analysis results |
| `/data/out/timings.csv` | Stage timings |
| `/data/out/validation_summary.csv` | Overall validation summary |
| `/data/out/validation_by_district.csv` | District-level validation counts |
| `/data/out/viz/severity_hex.csv` | H3-level visualization data |
| `/data/out/viz/taluka_ranking.csv` | Taluka ranking data |
| `/data/out/viz/validation_summary.csv` | Validation summary for reporting |
| `/data/out/viz/validation_by_district.csv` | District validation data for reporting |
| `/data/out/visualizations/` | Generated PNG charts |

CSV and PNG files are local files on the primary VM unless copied elsewhere. Parquet inputs and outputs may be stored in HDFS as specified by the pipeline.

## Environment Setup

The commands below describe the current VM setup. They assume the Spark cluster and HDFS are installed and configured.

### Visualization environment

Create a separate Python environment:

```bash
cd ~/infra-gap

python3 -m venv .venv-viz
source .venv-viz/bin/activate

python -m pip install --upgrade pip
python -m pip install pandas matplotlib seaborn
```

Verify the libraries:

```bash
python -c "import pandas, matplotlib, seaborn; print('Visualization libraries ready')"
```

### Run the visualization script

```bash
cd ~/infra-gap
source .venv-viz/bin/activate
python visualize.py
```

The script reads existing CSV outputs and writes the charts to `/data/out/visualizations/`. It does not rerun the Spark pipeline.

### Spark submission example

The following is the command used for the validation stage:

```bash
cd ~/infra-gap
export PYTHONPATH="$PWD/src:$PYTHONPATH"

"$SPARK_HOME/bin/spark-submit" \
  --master spark://<SPARK_MASTER_IP>:7077 \
  --deploy-mode client \
  --driver-memory 1g \
  --executor-memory 2g \
  --total-executor-cores 4 \
  src/validate.py \
  --tag base \
  --top-n 400 \
  --match-m 500
```

Run Spark jobs only when the required inputs and services are available. Do not run the validation stage solely to regenerate charts.

## Exporting Results to Windows

After generating the PNG files, copy them from the primary VM to a Windows folder using SCP, provided SSH access to the VM is available.

Run the following in **Windows PowerShell**:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\Downloads\infra-gap-visualizations"
```

Then copy the charts:

```powershell
scp -r h-user@1<SPARK_MASTER_IP>:/data/out/visualizations/* "$env:USERPROFILE\Downloads\infra-gap-visualizations/"
```

To copy the visualization CSV files as well:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\Downloads\infra-gap-viz"

scp h-user@1<SPARK_MASTER_IP>:/data/out/viz/severity_hex.csv "$env:USERPROFILE\Downloads\infra-gap-viz/"
scp h-user@1<SPARK_MASTER_IP>:/data/out/viz/taluka_ranking.csv "$env:USERPROFILE\Downloads\infra-gap-viz/"
scp h-user@1<SPARK_MASTER_IP>:/data/out/viz/validation_summary.csv "$env:USERPROFILE\Downloads\infra-gap-viz/"
scp h-user@1<SPARK_MASTER_IP>:/data/out/viz/validation_by_district.csv "$env:USERPROFILE\Downloads\infra-gap-viz/"
```

If SSH connectivity is unavailable, use an appropriately configured VMware shared folder instead.

## Limitations

- Results depend on the completeness, quality, and dates of the input datasets.
- OpenStreetMap coverage may be incomplete or geographically uneven.
- The 25 km search radius caps distances when no facility is found within the radius.
- The thresholds are project assumptions, not universal standards.
- Equal weights are used for the three service types in the baseline model.
- H3 cell-centre distance is a proximity estimate, not road-network distance or travel time.
- The analysis does not model road conditions, terrain, facility capacity, service quality, or opening hours.
- Spatial joins leave some cells and reference points unassigned; these must be disclosed.
- The official hospital comparison does not validate schools, drinking-water points, population estimates, or the full composite score.
- Sensitivity analysis covers only the scenarios tested.
- High severity indicates relative priority under the model; it is not proof that a locality has no infrastructure or that a specific intervention is required.

## Future Scope

- Generate a geographic map using actual H3 cell boundaries.
- Export static maps and interactive HTML maps.
- Incorporate road-network travel times and terrain-aware accessibility.
- Improve facility deduplication and category harmonization.
- Investigate unassigned H3 cells and official reference records outside administrative polygons.
- Expand independent validation to schools and drinking-water sources.
- Test additional weighting schemes and access thresholds.
- Record dataset versions, licenses, parameters, and software versions for reproducibility.

## Reproducibility Checklist

For a reproducible analysis, record:

- Dataset names, sources, versions, dates, and licenses
- H3 resolution
- Search radius
- Facility access thresholds
- Severity weights
- Spark, Hadoop, Sedona, H3, and Python versions
- Counts of assigned and unassigned cells
- Validation and sensitivity-analysis results
- Stage execution timings

---

**Project:** Mapping India's Infrastructure Deserts: A Distributed Big Data Analytics Approach
