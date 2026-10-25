"""Draw the report charts and maps from the pipeline outputs. Run: python analysis/make_figures.py"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from config import T, p  # noqa: E402

OUT = p("out", "figures")
os.makedirs(OUT, exist_ok=True)
sv = pd.read_parquet(p("out", "severity_base"))
aspect = 1 / np.cos(np.deg2rad(sv["lat"].mean()))


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", name)


def hexmap(values, title, label, name, cmap):
    fig, ax = plt.subplots(figsize=(7.4, 6))
    hb = ax.hexbin(sv["lon"], sv["lat"], C=values, reduce_C_function=np.mean, gridsize=80,
                   cmap=cmap, mincnt=1, linewidths=0.1)
    ax.set_aspect(aspect)
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude"); ax.set_title(title, fontweight="bold")
    fig.colorbar(hb, ax=ax, shrink=0.8).set_label(label)
    save(fig, name)


# 1 and 2: maps
hexmap(np.log10(sv["severity"] + 1), "Gap Severity Map", "log10(Gap Severity Score)", "fig_severity_map.png", "YlOrRd")
hexmap(sv["d_hosp"] / 1000, "Distance to nearest hospital", "Distance (km)", "fig_hospital_distance_map.png", "viridis_r")

# 3: population by distance band
thr = {"Hospital": ("d_hosp", T["hosp"]), "School": ("d_school", T["school"]), "Drinking water": ("d_water", T["water"])}
fig, ax = plt.subplots(figsize=(7.2, 3.6))
left = np.zeros(len(thr))
names = ["Within threshold", "1x to 2x threshold", "Beyond 2x threshold"]
cols = ["#4caf50", "#ffb300", "#d32f2f"]
shares = []
for col, t in thr.values():
    pop = sv["pop"]
    shares.append([100 * pop[sv[col] <= t].sum() / pop.sum(),
                   100 * pop[(sv[col] > t) & (sv[col] <= 2 * t)].sum() / pop.sum(),
                   100 * pop[sv[col] > 2 * t].sum() / pop.sum()])
shares = np.array(shares)
for k in range(3):
    ax.barh(list(thr), shares[:, k], left=left, color=cols[k], label=names[k])
    left += shares[:, k]
ax.set_xlim(0, 100); ax.set_xlabel("Share of population (%)")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, frameon=False)
ax.set_title("Population by distance band", fontweight="bold")
save(fig, "fig_population_bands.png")

# 4: top talukas
tpath = p("out", "taluka_base")
if os.path.exists(tpath):
    tl = pd.read_parquet(tpath).nlargest(10, "severity_per_person").iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 4))
    ax.barh(tl["taluka"] + " (" + tl["district"] + ")", tl["severity_per_person"], color="#c0392b")
    ax.set_xlabel("Severity per person"); ax.set_title("Top 10 underserved talukas", fontweight="bold")
    save(fig, "fig_top_talukas.png")

# 5: OSM vs official
vpath = p("out", "validation_by_district.csv")
if os.path.exists(vpath):
    v = pd.read_csv(vpath)
    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    ax.scatter(v["official_total"], v["matched_in_osm"], color="#1f77b4", zorder=3)
    m = max(v["official_total"].max(), 1) * 1.1
    ax.plot([0, m], [0, m], "--", color="gray", label="Perfect match")
    ax.set_xlim(0, m); ax.set_ylim(0, m)
    ax.set_xlabel("Official hospital count"); ax.set_ylabel("Found in OSM")
    ax.legend(frameon=False); ax.set_title("OSM vs official hospital counts", fontweight="bold")
    save(fig, "fig_osm_vs_official.png")

# 6: runtime, local vs cluster
tpath2 = p("out", "timings.csv")
if os.path.exists(tpath2):
    tm = pd.read_csv(tpath2)
    tm = tm[tm["job"] == "access"].groupby(["stage", "mode"])["seconds"].mean().unstack("mode")
    if not tm.empty:
        ax = (tm / 60).plot(kind="bar", figsize=(7.2, 3.8), rot=0, color=["#2980b9", "#7f8c8d"][: len(tm.columns)])
        ax.set_ylabel("Minutes"); ax.set_title("Runtime by stage: local vs cluster", fontweight="bold")
        save(ax.get_figure(), "fig_runtime.png")