# Implementation Details

## 1. Overview

This document describes the implementation of **Mapping India's Infrastructure Deserts: A Distributed Big Data Analytics Approach**.

The system uses Python, Apache Spark, Apache Sedona, and H3-based spatial indexing to process geographical datasets and estimate infrastructure accessibility gaps.

The processing workflow includes:

1. Input-data preparation.
2. Spatial indexing and data integration.
3. Essential-facility classification.
4. Nearest-facility distance analysis.
5. Gap Severity Score calculation.
6. Administrative aggregation and ranking.
7. Validation and sensitivity analysis.
8. Export and visualization.

The repository contains reusable processing scripts under `src/`, data preparation scripts under `prep/`, orchestration utilities under `scripts/`, and analytical visualization code.

> **Implementation note:** This document describes the project's architecture and intended responsibilities. Where exact function signatures, formulas, or input schemas are implementation-dependent, consult the corresponding source file before modifying or reproducing the behaviour.

## 2. Technology Stack

| Component | Technology | Responsibility |
|---|---|---|
| Programming language | Python | Pipeline and analytical logic |
| Distributed processing | Apache Spark | Parallel processing of large datasets |
| Python Spark API | PySpark | DataFrame transformations and execution |
| Geospatial processing | Apache Sedona | Spatial SQL and geometry operations |
| Spatial indexing | H3 | Hexagonal cell identification and aggregation |
| Intermediate storage | Parquet | Structured analytical datasets |
| Tabular exports | CSV | Summaries, rankings, and visualization inputs |
| Visualization | Python plotting libraries | Charts and maps |
| Interactive exploration | Kepler.gl | Exploration of exported spatial data |
| Execution environment | Linux-based Spark environment | Driver, workers, and data processing |
| Version control | Git and GitHub | Source management and reproducibility |

The actual installed versions should be checked on the machine where the pipeline runs.

## 3. Repository Structure

The following structure describes the principal project components. Additional files may exist in the current repository.

```text
infra-gap/
├── .gitignore
├── README.md
├── project_description.md
├── implementation_detail.md
├── File_Details.md
│
├── config/
│   └── settings.env
│
├── prep/
│   ├── fetch_buildings.py
│   ├── prep_boundaries.py
│   ├── prep_official.py
│   ├── prep_osm.sh
│   ├── prep_population.sh
│   ├── raster_to_points.py
│   └── preprocess_buildings.py
│
├── src/
│   ├── common.py
│   ├── config.py
│   ├── ingest_index.py
│   ├── access_score.py
│   ├── rollup.py
│   ├── validate.py
│   ├── sensitivity.py
│   ├── export_viz.py
│   ├── restore_facilities.py
│   └── smoke_test.py
│
├── scripts/
│   ├── run_all.sh
│   └── benchmark.sh
│
├── analysis/
│   └── make_figures.py
│
└── presentation_pack/
    ├── create_visuals.py
    ├── charts/
    └── maps/
```

The data directory is configured separately from the source repository. In the current environment, the main data root is `/data`.

Generated data, large source datasets, logs, and temporary files should not be committed unless there is a specific reason to version them.

## 4. Configuration

Project settings are defined in:

```text
config/settings.env
```

The known default settings are:

| Variable | Default | Description |
|---|---:|---|
| `BBOX_W` | `73.0` | Western longitude of the study bounding box |
| `BBOX_S` | `17.5` | Southern latitude of the study bounding box |
| `BBOX_E` | `75.5` | Eastern longitude of the study bounding box |
| `BBOX_N` | `19.5` | Northern latitude of the study bounding box |
| `H3_RES` | `8` | H3 spatial resolution |
| `SEARCH_RADIUS_M` | `25000` | Maximum search radius for nearby facilities |
| `T_HOSP_M` | `10000` | Hospital distance threshold |
| `T_SCHOOL_M` | `3000` | School distance threshold |
| `T_WATER_M` | `2000` | Drinking-water distance threshold |
| `DATA_ROOT` | `/data` | Root directory for datasets and outputs |

The bounding box specifies the rectangular geographical extent used for processing. It should not be treated as an exact administrative boundary.

The `H3_RES` setting controls the spatial granularity of the hexagonal indexing system. A higher H3 resolution creates smaller cells and increases spatial detail, while potentially increasing processing and storage requirements.

The search radius and category-specific thresholds have different roles:

- The search radius limits the area considered for nearest-facility searches.
- The category thresholds define distance levels used to assess potential accessibility gaps.

Before running the pipeline in another environment, verify that the configuration loader in `src/config.py` reads these settings correctly.

## 5. Data Inputs

The pipeline uses geographical data representing population, buildings, boundaries, and essential facilities.

### 5.1 Population data

Population information is used to estimate the number of people associated with each spatial cell.

The source dataset and its spatial resolution determine the accuracy of this estimate. If population is derived from a gridded or modelled dataset, it should not be described as an exact census count.

### 5.2 Building footprints

Building footprints represent mapped building geometries.

The preprocessing workflow prepares building data for spatial analysis. Building counts can provide additional context about settlement distribution and the built environment.

Building counts and population estimates are different measurements and should not be used interchangeably.

### 5.3 Administrative boundaries

Boundary data provides geographical context for the study area and supports administrative reporting.

Boundary validity and coordinate handling are important because malformed geometries can cause spatial operations to fail or produce incorrect results.

### 5.4 Essential facilities

The facility data represents locations of selected essential services.

The current categories include:

- Hospitals.
- Schools.
- Drinking-water facilities.

Facility records are classified using available attributes. The resulting category depends on the completeness and correctness of those attributes.

### 5.5 Data staging

Input datasets and intermediate files are maintained in the configured data directory.

A typical layout is:

```text
/data/
├── raw/
├── staging/
└── out/
```

The exact filenames depend on the downloaded datasets and preparation steps.

## 6. Processing Architecture

The pipeline is organised into independent processing stages.

```text
Input datasets
     |
     v
Data preparation
     |
     v
Ingestion and spatial indexing
     |
     v
Population/building association
     |
     v
Facility classification
     |
     v
Nearest-facility analysis
     |
     v
Gap Severity Score
     |
     v
Administrative aggregation
     |
     +-------------------+
     |                   |
     v                   v
Validation        Sensitivity analysis
     |                   |
     +---------+---------+
               |
               v
       Visualization export
               |
               v
         Maps and charts
```

Apache Spark executes distributed transformations. Apache Sedona supplies geospatial SQL functions and geometry operations. H3 provides a consistent spatial index for hexagonal cells.

## 7. Implementation Modules

### 7.1 `src/common.py`

**Purpose:** Shared Spark and Sedona initialization utilities.

The project uses a common helper, `get_sedona(...)`, to initialize the processing session used by geospatial jobs.

Centralising initialization reduces duplication and helps keep Spark and Sedona configuration consistent across modules.

### 7.2 `src/config.py`

**Purpose:** Shared configuration access.

The module provides the project configuration interface, including the path helper `p(...)` used by processing scripts to resolve data locations.

For example, scripts use this helper to resolve staging and output paths without repeatedly hardcoding complete paths.

### 7.3 `prep/`

**Purpose:** Prepare raw geographical datasets for analytical processing.

The preparation scripts cover activities such as building-data acquisition, boundary preparation, population preparation, and raster-to-point conversion.

`prep/preprocess_buildings.py` contains additional building preprocessing logic.

The exact transformations and input/output schemas should be verified from the corresponding script before the process is reproduced.

### 7.4 `src/ingest_index.py`

**Purpose:** Ingest prepared data and construct the spatial analysis inputs.

This stage is responsible for preparing the data required by downstream analysis, including the H3-indexed representation used to associate population and building information with geographical cells.

The resulting spatial index provides a consistent unit for facility-distance analysis and severity calculation.

### 7.5 `src/access_score.py`

**Purpose:** Calculate accessibility measures and the Gap Severity Score.

This module performs the principal access-gap analysis.

Its responsibilities include calculating facility-distance measures, applying the configured category thresholds, and producing per-cell results for downstream aggregation.

The pipeline supports a configurable analysis tag, such as `base`, allowing output datasets from different runs or parameter configurations to be distinguished.

The exact score formula and weights must be taken from the implementation in this file.

### 7.6 `src/rollup.py`

**Purpose:** Aggregate cell-level results into administrative summaries.

The module supports the production of higher-level summaries and rankings, including taluka- and district-level outputs where the relevant administrative attributes are available.

Aggregation makes the cell-level results easier to compare across administrative units.

### 7.7 `src/validate.py`

**Purpose:** Examine analytical data quality and potential validation issues.

Validation outputs help assess the reliability of the analysis and the limitations of the input data.

The project documentation describes checks related to OpenStreetMap completeness and false-alarm assessment.

These checks do not guarantee that every facility has been captured or that every flagged location is genuinely underserved. Their interpretation depends on the available reference information and the implemented validation logic.

### 7.8 `src/sensitivity.py`

**Purpose:** Examine how parameter choices affect the results.

The project includes sensitivity analysis for alternative distance thresholds and scoring weights.

This analysis helps determine whether the resulting rankings remain similar when the modelling assumptions change.

Sensitivity results describe the behaviour of the model under tested configurations; they do not establish that one particular threshold is universally correct.

### 7.9 `src/export_viz.py`

**Purpose:** Export analytical results for visualization.

The export stage creates visualization-ready datasets, including data used to explore H3 cells and administrative rankings.

CSV files can be used by mapping and charting tools, while Parquet remains useful for structured analytical outputs.

### 7.10 `analysis/make_figures.py`

**Purpose:** Generate charts and figures from analytical outputs.

The analysis directory contains visualization code for reporting results.

The repository also includes `presentation_pack/create_visuals.py`, which generates presentation-oriented charts and maps.

These scripts serve the reporting layer and should not be confused with the core geospatial scoring stage.

### 7.11 `src/restore_facilities.py`

**Purpose:** Rebuild the processed facility output from staged facility GeoJSONL data.

This utility reads facility features, classifies supported facility categories, derives representative longitude and latitude values, and writes the resulting dataset in Parquet format.

It is a recovery utility rather than a required stage of every normal pipeline run.

## 8. Spatial Indexing with H3

H3 represents geographical locations using hierarchical hexagonal cells.

Each cell has an identifier that can be used to group spatial observations.

In this project, H3 provides a common spatial framework for combining population information, building information, and infrastructure accessibility results.

The configured resolution is:

```text
H3_RES = 8
```

The chosen resolution affects the granularity of the analysis.

Smaller cells provide more detailed spatial representation but can increase the number of records and the cost of distributed operations.

H3 indexing supports aggregation and mapping. It does not, by itself, calculate nearest-facility distances or guarantee that every point in a cell has the same accessibility.

## 9. Nearest-Facility Analysis

The accessibility analysis estimates distances from spatial cells to nearby essential facilities.

The configured search radius is:

```text
SEARCH_RADIUS_M = 25000
```

The analysis considers facility categories separately because each category uses a different distance threshold.

| Category | Threshold |
|---|---:|
| Hospital | 10,000 m |
| School | 3,000 m |
| Drinking water | 2,000 m |

The thresholds are configurable assumptions.

The project uses geospatial processing to calculate proximity. Straight-line proximity should not be interpreted as actual travel distance or travel time.

The precise geometry operations, distance calculations, and treatment of cells without a nearby facility are determined by the code in `src/access_score.py` and the associated spatial-processing modules.

## 10. Gap Severity Score Calculation

The Gap Severity Score combines population exposure and the modelled severity of distance-threshold exceedances.

Conceptually:

\[
S_h = P_h \times W_h
\]

where:

- \(S_h\) represents the score for hexagonal cell \(h\).
- \(P_h\) represents the population associated with that cell.
- \(W_h\) represents the combined weighted contribution of distance exceedances under the implemented scoring method.

The actual calculation may include normalization, caps, category-specific weights, or other implementation details. Those details should be read directly from `src/access_score.py`.

The interpretation is relative to the configured study area and assumptions:

- A higher score indicates a more severe modelled access gap.
- Population exposure influences the importance of a gap.
- Distance thresholds define the reference levels used by the model.
- Changes to the thresholds or weights can change scores and rankings.

The score does not directly measure service quality, facility capacity, road-network accessibility, or actual unmet demand.

## 11. Administrative Aggregation

Cell-level outputs provide spatial detail but may be difficult to interpret as a complete study-area summary.

The rollup stage aggregates analytical results into administrative units where the required geographic attributes are available.

The resulting outputs can support:

- Comparing talukas.
- Comparing districts.
- Ranking areas by aggregated severity.
- Identifying administrative areas that warrant closer investigation.

The interpretation of an administrative ranking depends on the aggregation method and the population or area represented by each unit.

A high aggregate score and a high per-capita severity measure are not necessarily equivalent. The specific metric should be stated when presenting a ranking.

## 12. Validation and Sensitivity Analysis

### 12.1 Validation

The validation stage generates diagnostic outputs that help assess the analytical results.

The project documentation identifies OpenStreetMap completeness and false-alarm assessment as validation concerns.

Validation is important because incomplete facility data can make an area appear more isolated than it actually is.

The outputs should be interpreted as diagnostic evidence, not as proof that every detected gap is genuine.

### 12.2 Sensitivity analysis

The sensitivity stage tests alternative parameter settings, including distance thresholds and scoring weights.

It helps answer questions such as:

- Do the same areas remain highly ranked under alternative thresholds?
- Are rankings sensitive to the relative importance assigned to facility categories?
- Do small parameter changes lead to substantially different conclusions?

The results are exported for inspection and comparison.

## 13. Storage and Output Structure

The main data root is:

```text
/data
```

The pipeline produces outputs in locations such as:

| Output location | Purpose |
|---|---|
| `/data/out/hex/` | H3-indexed cell information |
| `/data/out/facilities/` | Classified facility data |
| `/data/out/severity_<tag>/` | Cell-level distance and severity results |
| `/data/out/taluka_<tag>/` | Taluka-level results |
| `/data/out/district_<tag>/` | District-level results |
| `/data/out/summary_<tag>.csv` | Summary statistics |
| `/data/out/validation_*.csv` | Validation outputs |
| `/data/out/sensitivity.csv` | Sensitivity-analysis results |
| `/data/out/viz/` | Visualization-ready CSV datasets |
| `/data/out/figures/` | Generated figures, where configured |

The `<tag>` placeholder represents the selected analysis tag.

The actual output names should be confirmed from the latest code and configuration. The pipeline may also produce additional intermediate files.

## 14. Visualization

The visualization layer converts analytical outputs into maps and charts.

The project includes presentation-oriented figures such as:

- Severity maps.
- Taluka rankings.
- Population beyond configured distance thresholds.
- Sensitivity-analysis charts.

The repository's `presentation_pack/` directory contains generated visual assets.

For interactive exploration, the exported H3 dataset can be loaded into Kepler.gl. A suitable H3 layer can display the cells using their H3 identifiers and colour them according to the severity field, provided the exported schema contains the expected columns.

Visualizations communicate the modelled results. They do not remove the limitations of the input data or the scoring assumptions.

## 15. Distributed Execution

Apache Spark supports distributed execution of the processing stages.

In the current project environment, the processing jobs are executed against a Spark cluster, with shared data available under `/data`.

The main operational components are:

- A Spark driver that coordinates execution.
- Spark workers that execute distributed tasks.
- Spark DataFrames for structured data transformations.
- Apache Sedona for spatial operations.
- Shared input and output storage.

The amount of parallelism depends on the cluster's available CPU and memory resources and the job configuration.

Distributed execution can improve scalability for suitable workloads, but it does not guarantee that a cluster will outperform local execution on a small dataset. Network communication, scheduling, and data-shuffling overhead can affect runtime.

## 16. Running the Project

### 16.1 Verify the repository

```bash
cd ~/infra-gap
git status
git branch --show-current
git remote -v
```

### 16.2 Verify the configuration

```bash
cat config/settings.env
```

Confirm that the bounding box, H3 resolution, search radius, thresholds, and data root match the intended experiment.

### 16.3 Verify the environment

Check the installed tools:

```bash
java -version
python3 --version
spark-submit --version
```

Verify that the Spark cluster is reachable and that the configured input datasets exist.

### 16.4 Execute the pipeline

The repository contains an orchestration script:

```text
scripts/run_all.sh
```

Inspect the script before execution to confirm that its commands, data paths, Spark configuration, and optional stages match the current environment.

If the script is configured for the current environment, execute:

```bash
bash scripts/run_all.sh
```

If individual stages need to be run separately, use the commands and dependency order documented in the current `README.md`.

Do not rerun expensive stages unnecessarily when their outputs already exist and the input data and configuration have not changed.

### 16.5 Inspect generated outputs

After a successful run, inspect the output directories:

```bash
find /data/out -maxdepth 2 -type f | sort | head -200
```

Check that the expected severity results, administrative summaries, validation outputs, and visualization datasets exist.

### 16.6 Run syntax checks

A lightweight Python syntax check can be run with:

```bash
python3 -m py_compile \
  src/access_score.py \
  src/export_viz.py \
  src/ingest_index.py \
  src/rollup.py \
  src/sensitivity.py \
  src/validate.py \
  src/restore_facilities.py \
  prep/preprocess_buildings.py
```

This checks syntax only. It does not prove that the Spark jobs will complete successfully.

## 17. Performance Considerations

The pipeline's runtime and memory usage depend on:

- The number and size of input records.
- The spatial resolution selected for H3 indexing.
- The number of facility records.
- The nearest-facility search implementation.
- Spark partitioning and shuffle behaviour.
- Driver and executor memory.
- The number of available worker cores.
- Input/output storage performance.

Useful performance practices include:

1. Avoid collecting large distributed datasets into driver memory.
2. Filter and preprocess input records before expensive spatial operations where appropriate.
3. Use appropriate partitioning for large joins and aggregations.
4. Avoid repeating expensive preprocessing when the inputs have not changed.
5. Monitor executor failures, memory pressure, and shuffle volume.
6. Record actual runtime measurements when comparing local and distributed execution.

The benchmark results should be measured in the actual environment rather than inferred from hardware specifications.

## 18. Reproducibility and Version Control

The source code is maintained in the GitHub repository:

https://github.com/Emperor2004/infra-gap

The repository stores the processing logic, configuration template, documentation, and selected visualization assets.

Large raw datasets and generated analytical outputs are maintained outside the repository to avoid unnecessary repository growth.

To inspect the current version:

```bash
git log -5 --oneline
git status
```

For a reproducible experiment, record:

- Input dataset versions and sources.
- Configuration values.
- Software versions.
- Spark resource settings.
- The analysis tag.
- Execution date and runtime.
- Any preprocessing changes.
- The locations of generated outputs.

## 19. Limitations

The implementation has several important limitations:

1. **Incomplete source data:** Some facilities may be absent from the source datasets.
2. **Proximity-based analysis:** Straight-line distance does not represent road travel time.
3. **Population uncertainty:** Modelled population distributions may not exactly match the population on the ground.
4. **Facility quality:** Location-based analysis does not fully represent capacity, staffing, quality, or availability.
5. **Parameter dependence:** Thresholds and weights influence the scores and rankings.
6. **Geographical scope:** The current pilot is not a completed nationwide assessment.
7. **Execution dependence:** Results and runtime depend on the datasets, configuration, and available compute resources.

## 20. Conclusion

The implementation demonstrates a distributed geospatial workflow for examining potential infrastructure access gaps.

It integrates population and facility information, uses H3 for spatial indexing, applies distance-based accessibility analysis, calculates severity scores, aggregates results, and generates validation and visualization outputs.

Apache Spark provides distributed processing, Apache Sedona supports spatial operations, and Parquet and CSV provide storage and export formats for subsequent analysis.

The resulting system is a configurable pilot framework for identifying geographical areas that may warrant further infrastructure assessment. Its conclusions must be interpreted in light of source-data completeness, distance assumptions, scoring parameters, and the geographical scope of the current implementation.