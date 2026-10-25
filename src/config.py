"""Settings shared by all scripts, read from environment variables (see config/settings.env)."""
import os

ROOT = os.environ.get("DATA_ROOT", "/data")


def p(*parts):
    """Build a path under the data root, for example p('out', 'hex')."""
    return os.path.join(ROOT, *parts)


BBOX = (
    float(os.environ.get("BBOX_W", 73.0)),
    float(os.environ.get("BBOX_S", 17.5)),
    float(os.environ.get("BBOX_E", 75.5)),
    float(os.environ.get("BBOX_N", 19.5)),
)
H3_RES = int(os.environ.get("H3_RES", 8))
RADIUS_M = float(os.environ.get("SEARCH_RADIUS_M", 25000))
T = {
    "hosp": float(os.environ.get("T_HOSP_M", 10000)),
    "school": float(os.environ.get("T_SCHOOL_M", 3000)),
    "water": float(os.environ.get("T_WATER_M", 2000)),
}