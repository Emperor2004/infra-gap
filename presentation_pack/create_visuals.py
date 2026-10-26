from pathlib import Path
import warnings

import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.collections import PolyCollection
from shapely.geometry import Polygon
import h3

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path.home() / "infra-gap" / "presentation_pack"
DATA = ROOT / "data"
CHARTS = ROOT / "charts"
MAPS = ROOT / "maps"

CHARTS.mkdir(parents=True, exist_ok=True)
MAPS.mkdir(parents=True, exist_ok=True)

severity = pd.read_csv(DATA / "severity_hex.csv")
talukas = pd.read_csv(DATA / "taluka_ranking.csv")
summary = pd.read_csv(DATA / "summary_base.csv").iloc[0]
sensitivity = pd.read_csv(DATA / "sensitivity.csv")
boundary = gpd.read_file("/data/staging/maharashtra_boundary.geojson")

if boundary.crs is None:
    boundary = boundary.set_crs("EPSG:4326")
else:
    boundary = boundary.to_crs("EPSG:4326")

print(f"Loaded {len(severity):,} H3 cells")
print(f"Loaded {len(talukas):,} taluka records")
print(f"Loaded {len(boundary):,} boundary features")


# ---------------------------------------------------------
# 1. Maharashtra infrastructure-gap severity map
# ---------------------------------------------------------
print("Creating severity map...")

polygons = []
values = []

for row in severity.itertuples(index=False):
    cell = str(row.hex_id)
    try:
        # H3 returns (latitude, longitude); Shapely expects (x, y).
        ring = [(lon, lat) for lat, lon in h3.cell_to_boundary(cell)]
        polygons.append(Polygon(ring))
        values.append(max(float(row.severity), 0))
    except (ValueError, TypeError):
        continue

fig, ax = plt.subplots(figsize=(11, 12))

collection = PolyCollection(
    [list(poly.exterior.coords) for poly in polygons],
    array=pd.Series(values).to_numpy(),
    cmap="YlOrRd",
    norm=mcolors.LogNorm(
        vmin=max(min((v for v in values if v > 0), default=0.001), 0.001),
        vmax=max(max(values, default=1), 1)
    ),
    edgecolors="none",
    linewidths=0
)
ax.add_collection(collection)

boundary.boundary.plot(ax=ax, color="black", linewidth=0.65)

ax.set_xlim(boundary.total_bounds[0], boundary.total_bounds[2])
ax.set_ylim(boundary.total_bounds[1], boundary.total_bounds[3])
ax.set_aspect("equal")
ax.set_axis_off()

cbar = fig.colorbar(collection, ax=ax, fraction=0.035, pad=0.02, shrink=0.7)
cbar.set_label("Infrastructure-gap severity (log scale)", fontsize=10)

ax.set_title(
    "Maharashtra Infrastructure Gap Map\n"
    "H3 spatial cells | Higher severity indicates greater modelled gaps",
    fontsize=14,
    pad=16
)

fig.savefig(MAPS / "maharashtra_severity_map.png",
            dpi=220, bbox_inches="tight")
plt.close(fig)


# ---------------------------------------------------------
# 2. Population beyond the selected distance thresholds
# ---------------------------------------------------------
print("Creating access-gap comparison...")

labels = ["Hospitals\n(10 km)", "Schools\n(3 km)", "Drinking water\n(2 km)"]
percentages = [
    float(summary["hosp_pct_pop_beyond"]),
    float(summary["school_pct_pop_beyond"]),
    float(summary["water_pct_pop_beyond"])
]

fig, ax = plt.subplots(figsize=(9, 5.5))
bars = ax.bar(labels, percentages)

ax.set_ylim(0, 105)
ax.set_ylabel("Modelled population beyond threshold (%)")
ax.set_title("Estimated Population Beyond Selected Access Thresholds")
ax.grid(axis="y", alpha=0.25)
ax.set_axisbelow(True)

for bar, value in zip(bars, percentages):
    ax.text(
        bar.get_x() + bar.get_width() / 2,
        value + 2,
        f"{value:.2f}%",
        ha="center",
        va="bottom",
        fontsize=10
    )

fig.text(
    0.5, 0.015,
    "Based on mapped facilities and selected thresholds; not an official deprivation estimate.",
    ha="center", fontsize=8
)
fig.tight_layout(rect=[0, 0.05, 1, 1])
fig.savefig(CHARTS / "population_beyond_thresholds.png",
            dpi=220, bbox_inches="tight")
plt.close(fig)


# ---------------------------------------------------------
# 3. Top 15 talukas by severity per person
# ---------------------------------------------------------
print("Creating taluka ranking chart...")

top = (
    talukas.sort_values("severity_per_person", ascending=False)
    .head(15)
    .copy()
)
top["label"] = top["taluka"].astype(str) + ", " + top["district"].astype(str)
top = top.sort_values("severity_per_person", ascending=True)

fig, ax = plt.subplots(figsize=(11, 8))
bars = ax.barh(top["label"], top["severity_per_person"])

ax.set_xlabel("Severity per person (model score)")
ax.set_title("15 Highest-Ranked Talukas by Severity per Person")
ax.grid(axis="x", alpha=0.25)
ax.set_axisbelow(True)

for bar, value in zip(bars, top["severity_per_person"]):
    ax.text(
        value,
        bar.get_y() + bar.get_height() / 2,
        f" {value:.3f}",
        va="center",
        fontsize=8
    )

fig.tight_layout()
fig.savefig(CHARTS / "top15_talukas.png", dpi=220, bbox_inches="tight")
plt.close(fig)


# ---------------------------------------------------------
# 4. Sensitivity analysis: rank stability
# ---------------------------------------------------------
print("Creating sensitivity chart...")

sens = sensitivity.copy()
sens["rho"] = pd.to_numeric(sens["spearman_rho"])
sens["overlap_count"] = sens["top10_overlap"].str.extract(r"(\d+)").astype(int)

fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))

axes[0].barh(sens["scenario"], sens["rho"])
axes[0].set_xlim(0, 1.05)
axes[0].set_xlabel("Spearman rank correlation")
axes[0].set_title("Overall Ranking Stability")
axes[0].grid(axis="x", alpha=0.25)

axes[1].barh(sens["scenario"], sens["overlap_count"])
axes[1].set_xlim(0, 10.8)
axes[1].set_xticks(range(0, 11, 2))
axes[1].set_xlabel("Talukas retained in top 10")
axes[1].set_title("Top-10 Overlap")
axes[1].grid(axis="x", alpha=0.25)

fig.suptitle("Sensitivity Analysis of Taluka Rankings", fontsize=14)
fig.tight_layout()
fig.savefig(CHARTS / "sensitivity_analysis.png", dpi=220, bbox_inches="tight")
plt.close(fig)


# ---------------------------------------------------------
# Save the exact top-15 data used in the chart
# ---------------------------------------------------------
top.sort_values("severity_per_person", ascending=False).to_csv(
    DATA / "top15_talukas.csv", index=False
)

print("\nVISUALIZATION COMPLETE")
print("\nCreated files:")
for folder in (MAPS, CHARTS):
    for file in sorted(folder.glob("*.png")):
        print(f"{file} ({file.stat().st_size / 1024:.1f} KB)")

print(f"\nTop 15 talukas data: {DATA / 'top15_talukas.csv'}")
