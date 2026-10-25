"""Helpers shared by the Spark jobs: session creation, stage timing, severity formula."""
import csv
import os
import time
from contextlib import contextmanager

from pyspark.sql import SparkSession
from sedona.spark import SedonaContext

from config import p


def get_sedona(app_name):
    """Create a Spark session with Sedona functions registered."""
    spark = SparkSession.builder.appName(app_name).getOrCreate()
    return SedonaContext.create(spark)


@contextmanager
def timed(sedona, job, stage):
    """Time a block (include the Spark action inside it) and append the result to out/timings.csv."""
    t0 = time.time()
    yield
    seconds = time.time() - t0
    master = sedona.sparkContext.master
    mode = "local" if master.startswith("local") else "cluster"
    path = p("out", "timings.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    is_new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["timestamp", "job", "stage", "seconds", "mode"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), job, stage, round(seconds, 2), mode])
    print(f"[timing] {job}/{stage}: {seconds:.1f}s ({mode})")


def severity_sql(t_hosp, t_school, t_water, w=(1 / 3, 1 / 3, 1 / 3)):
    """SQL expression for the Gap Severity Score.

    Needs columns: pop, d_hosp, d_school, d_water (distances in metres).
    ratio = min(max(0, d - T) / T, 3); severity = pop * sum(w * ratio)
    """
    return (
        f"pop * ({w[0]} * LEAST(GREATEST(d_hosp - {t_hosp}, 0) / {t_hosp}, 3) "
        f"+ {w[1]} * LEAST(GREATEST(d_school - {t_school}, 0) / {t_school}, 3) "
        f"+ {w[2]} * LEAST(GREATEST(d_water - {t_water}, 0) / {t_water}, 3))"
    )