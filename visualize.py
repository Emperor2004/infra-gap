import os

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# --------------------------------------------------
# Configuration
# --------------------------------------------------

INPUT_DIR = "/data/out/viz"
OUTPUT_DIR = "/data/out/visualizations"

os.makedirs(OUTPUT_DIR, exist_ok=True)

sns.set_theme(style="whitegrid", context="notebook")


def save_chart(filename):
    """Save the current Matplotlib figure as a high-resolution PNG."""
    path = os.path.join(OUTPUT_DIR, filename)
    plt.tight_layout()
    plt.savefig(path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved: {path}")


# --------------------------------------------------
# 1. Top 15 talukas by severity per person
# --------------------------------------------------

talukas = pd.read_csv(
    os.path.join(INPUT_DIR, "taluka_ranking.csv")
)

top15 = (
    talukas.sort_values("severity_per_person", ascending=False)
    .head(15)
    .copy()
)

top15["location"] = top15["taluka"] + ", " + top15["district"]

plt.figure(figsize=(12, 8))

sns.barplot(
    data=top15,
    x="severity_per_person",
    y="location",
    errorbar=None
)

plt.title("Top 15 Talukas by Relative Infrastructure-Gap Severity")
plt.xlabel("Severity per Person")
plt.ylabel("Taluka and District")

save_chart("01_top15_talukas.png")


# --------------------------------------------------
# 2. Population vs severity
# --------------------------------------------------

hexagons = pd.read_csv(
    os.path.join(INPUT_DIR, "severity_hex.csv")
)

plt.figure(figsize=(10, 7))

sns.scatterplot(
    data=hexagons,
    x="pop",
    y="severity",
    alpha=0.3,
    s=12
)

plt.title("Population vs Infrastructure-Gap Severity")
plt.xlabel("Population per H3 Hexagon")
plt.ylabel("Severity Score")

save_chart("02_population_vs_severity.png")


# --------------------------------------------------
# 3. Distribution of facility distances
# --------------------------------------------------

distance_columns = ["d_hosp", "d_school", "d_water"]

distance_labels = {
    "d_hosp": "Hospital",
    "d_school": "School",
    "d_water": "Drinking Water"
}

distances = hexagons[distance_columns].rename(
    columns=distance_labels
)

# Sample for plotting so the chart remains responsive.
distance_sample = distances.sample(
    n=min(50000, len(distances)),
    random_state=42
)

distance_long = distance_sample.melt(
    var_name="Facility",
    value_name="Distance (metres)"
)

plt.figure(figsize=(10, 6))

sns.boxplot(
    data=distance_long,
    x="Facility",
    y="Distance (metres)"
)

plt.title("Distribution of Distance to Mapped Facilities")
plt.xlabel("Facility Type")
plt.ylabel("Distance from H3 Hexagon Centre (metres)")

save_chart("03_facility_distance_distribution.png")

# --------------------------------------------------
# 4. Population beyond access thresholds
# --------------------------------------------------

summary_path = "/data/out/summary_base.csv"
summary = pd.read_csv(summary_path)

row = summary.iloc[0]

threshold_data = pd.DataFrame({
    "Facility": ["Hospital", "School", "Drinking Water"],
    "Population beyond threshold (%)": [
        row["hosp_pct_pop_beyond"],
        row["school_pct_pop_beyond"],
        row["water_pct_pop_beyond"]
    ]
})

plt.figure(figsize=(9, 6))

ax = sns.barplot(
    data=threshold_data,
    x="Facility",
    y="Population beyond threshold (%)",
    errorbar=None
)

for container in ax.containers:
    ax.bar_label(container, fmt="%.2f%%", padding=3)

plt.title("Population Beyond Defined Facility-Access Thresholds")
plt.xlabel("Facility Type")
plt.ylabel("Population Beyond Threshold (%)")
plt.ylim(0, 100)

save_chart("04_population_beyond_thresholds.png")

# --------------------------------------------------
# 5. Official hospital reference validation
# --------------------------------------------------

validation_path = os.path.join(
    INPUT_DIR, "validation_summary.csv"
)

validation = pd.read_csv(validation_path)
v = validation.iloc[0]

matched = int(v["matched_in_osm"])
unmatched = int(v["official_total"] - matched)

validation_data = pd.DataFrame({
    "Result": [
        "Matched to OSM within 500 m",
        "Not matched within 500 m"
    ],
    "Records": [matched, unmatched]
})

plt.figure(figsize=(9, 6))

ax = sns.barplot(
    data=validation_data,
    x="Result",
    y="Records",
    errorbar=None
)

for container in ax.containers:
    ax.bar_label(container, fmt="%.0f", padding=3)

plt.title("Official Hospital Reference List vs OSM")
plt.xlabel("")
plt.ylabel("Number of Reference Records")
plt.xticks(rotation=10)

save_chart("05_hospital_validation.png")


print("\nAll charts generated.")
print(f"Output directory: {OUTPUT_DIR}")
