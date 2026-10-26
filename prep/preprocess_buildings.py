#!/usr/bin/env python3
"""
Preprocess Microsoft building footprints for Maharashtra.

Inputs:
    /data/raw/buildings/*.gz
    /data/staging/maharashtra_boundary.geojson

Outputs:
    /data/processed/buildings_maharashtra.geojsonl
    /data/processed/buildings_quality_report.json

Raw input files are never modified.

Processing:
    1. Read gzip-compressed GeoJSON Lines files.
    2. Parse and validate polygon geometries.
    3. Repair invalid geometries where possible.
    4. Retain footprints whose representative point is inside Maharashtra.
    5. Remove exact normalized geometry duplicates.
    6. Write cleaned GeoJSONL and a quality report.

The script refuses to overwrite existing final outputs.
"""

import gzip
import json
import os
import sys
from collections import Counter
from pathlib import Path

from shapely.geometry import shape, mapping, MultiPolygon
from shapely.validation import make_valid

ROOT = Path(os.environ.get("DATA_ROOT", "/data"))
INPUT_DIR = ROOT / "raw" / "buildings"
BOUNDARY_FILE = ROOT / "staging" / "maharashtra_boundary.geojson"
OUTPUT_DIR = ROOT / "processed"
OUTPUT_FILE = OUTPUT_DIR / "buildings_maharashtra.geojsonl"
REPORT_FILE = OUTPUT_DIR / "buildings_quality_report.json"

stats = Counter()
error_examples = []
MAX_EXAMPLES = 20


def record_error(category, filename, line_no, message):
    stats[category] += 1
    if len(error_examples) < MAX_EXAMPLES:
        error_examples.append({
            "file": filename,
            "line": line_no,
            "reason": str(message)[:500],
        })


def load_boundary(path):
    if not path.is_file():
        raise FileNotFoundError(f"Boundary file not found: {path}")

    with path.open("r", encoding="utf-8") as stream:
        document = json.load(stream)

    geometries = [
        shape(feature["geometry"])
        for feature in document.get("features", [])
        if isinstance(feature, dict) and feature.get("geometry")
    ]

    if not geometries:
        raise ValueError("No geometries found in the boundary file.")

    # The supplied GeoJSON boundary is expected to use WGS84 longitude/latitude.
    from shapely.ops import unary_union
    boundary = unary_union(geometries)

    if boundary.is_empty:
        raise ValueError("The Maharashtra boundary is empty.")

    if not boundary.is_valid:
        boundary = make_valid(boundary)

    if boundary.is_empty or not boundary.is_valid:
        raise ValueError("The boundary remains invalid after repair.")

    if boundary.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError(
            f"Unexpected boundary geometry type: {boundary.geom_type}"
        )

    return boundary


def polygonal_only(geom):
    """Extract polygonal components from a repaired geometry."""
    if geom is None or geom.is_empty:
        return None

    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom

    if geom.geom_type == "GeometryCollection":
        polygons = []

        for part in geom.geoms:
            if part.is_empty:
                continue

            if part.geom_type == "Polygon":
                polygons.append(part)
            elif part.geom_type == "MultiPolygon":
                polygons.extend(part.geoms)

        if not polygons:
            return None

        if len(polygons) == 1:
            return polygons[0]

        return MultiPolygon(polygons)

    return None


def geometry_key(geom):
    """
    Produce a key for exact normalized geometry deduplication.

    Coordinates are already in longitude/latitude. Projecting each individual
    footprint is unnecessary for exact duplicate detection and adds overhead.
    This does not remove overlaps or near-duplicate footprints.
    """
    return geom.normalize().wkb


def main():
    if not INPUT_DIR.is_dir():
        raise FileNotFoundError(f"Input directory not found: {INPUT_DIR}")

    files = sorted(INPUT_DIR.glob("*.gz"))
    if not files:
        raise RuntimeError(f"No .gz files found in {INPUT_DIR}")

    if OUTPUT_FILE.exists() or REPORT_FILE.exists():
        raise FileExistsError(
            "Final output already exists. Nothing was overwritten.\n"
            f"Output: {OUTPUT_FILE}\n"
            f"Report: {REPORT_FILE}"
        )

    boundary = load_boundary(BOUNDARY_FILE)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Unique temporary names prevent confusion with leftovers from earlier runs.
    output_tmp = OUTPUT_FILE.with_name(
        OUTPUT_FILE.name + f".tmp.{os.getpid()}"
    )
    report_tmp = REPORT_FILE.with_name(
        REPORT_FILE.name + f".tmp.{os.getpid()}"
    )

    seen_geometries = set()
    output_count = 0

    try:
        with output_tmp.open("w", encoding="utf-8") as out:
            for file_index, path in enumerate(files, start=1):
                print(
                    f"[{file_index}/{len(files)}] Processing {path.name}",
                    flush=True,
                )
                stats["files_seen"] += 1

                try:
                    with gzip.open(path, "rt", encoding="utf-8") as source:
                        for line_no, line in enumerate(source, start=1):
                            if not line.strip():
                                stats["blank_lines"] += 1
                                continue

                            stats["records_read"] += 1

                            try:
                                feature = json.loads(line)
                            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                                record_error(
                                    "invalid_json", path.name, line_no, exc
                                )
                                continue

                            if not isinstance(feature, dict):
                                record_error(
                                    "non_object_record", path.name, line_no,
                                    "Record is not a JSON object",
                                )
                                continue

                            geometry_json = feature.get("geometry")
                            if not isinstance(geometry_json, dict):
                                record_error(
                                    "missing_geometry", path.name, line_no,
                                    "Missing or malformed geometry object",
                                )
                                continue

                            try:
                                geom = shape(geometry_json)
                            except Exception as exc:
                                record_error(
                                    "geometry_parse_errors",
                                    path.name, line_no, exc,
                                )
                                continue

                            if geom.is_empty:
                                stats["empty_geometries"] += 1
                                continue

                            if geom.geom_type not in ("Polygon", "MultiPolygon"):
                                stats["non_polygon_geometries"] += 1
                                continue

                            if not geom.is_valid:
                                stats["invalid_geometries_before_repair"] += 1

                                try:
                                    geom = polygonal_only(make_valid(geom))
                                except Exception as exc:
                                    record_error(
                                        "geometry_repair_errors",
                                        path.name, line_no, exc,
                                    )
                                    geom = None

                                if geom is None or geom.is_empty:
                                    stats["unrepairable_geometries"] += 1
                                    continue

                                if not geom.is_valid:
                                    stats["unrepairable_geometries"] += 1
                                    continue

                                stats["geometries_repaired"] += 1

                            stats["valid_polygon_geometries"] += 1

                            try:
                                point = geom.representative_point()

                                if not boundary.covers(point):
                                    stats["outside_state"] += 1
                                    continue
                            except Exception as exc:
                                record_error(
                                    "boundary_test_errors",
                                    path.name, line_no, exc,
                                )
                                continue

                            stats["inside_state_before_dedup"] += 1

                            try:
                                key = geometry_key(geom)
                            except Exception as exc:
                                record_error(
                                    "geometry_key_errors",
                                    path.name, line_no, exc,
                                )
                                continue

                            if key in seen_geometries:
                                stats["exact_geometry_duplicates"] += 1
                                continue

                            seen_geometries.add(key)

                            properties = feature.get("properties")
                            if not isinstance(properties, dict):
                                properties = {}

                            cleaned_feature = {
                                "type": "Feature",
                                "properties": properties,
                                "geometry": mapping(geom),
                            }

                            out.write(
                                json.dumps(
                                    cleaned_feature,
                                    separators=(",", ":"),
                                    ensure_ascii=False,
                                ) + "\n"
                            )

                            output_count += 1
                            stats["records_written"] += 1

                except (OSError, EOFError, UnicodeError) as exc:
                    record_error("file_read_errors", path.name, 0, exc)

        # Never publish a dataset if a source file could not be read fully.
        if stats["file_read_errors"]:
            raise RuntimeError(
                f"{stats['file_read_errors']} source file(s) could not be "
                "read completely. Temporary output will not be published."
            )

        report = {
            "status": "completed",
            "input_directory": str(INPUT_DIR),
            "boundary_file": str(BOUNDARY_FILE),
            "output_file": str(OUTPUT_FILE),
            "files_discovered": len(files),
            "records_written": output_count,
            "geometry_deduplication": (
                "Exact normalized geometry only. Overlapping or near-identical "
                "footprints are not necessarily deduplicated."
            ),
            "boundary_filter": (
                "A footprint is retained when its representative point is "
                "covered by the Maharashtra boundary. The full footprint "
                "is not clipped to the state boundary."
            ),
            "statistics": dict(sorted(stats.items())),
            "error_examples": error_examples,
        }

        with report_tmp.open("w", encoding="utf-8") as report_stream:
            json.dump(
                report, report_stream, indent=2, ensure_ascii=False
            )
            report_stream.write("\n")

        # Publish only after processing and report generation succeed.
        os.replace(output_tmp, OUTPUT_FILE)
        os.replace(report_tmp, REPORT_FILE)

        print("\n=== PREPROCESSING SUMMARY ===")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nCleaned output: {OUTPUT_FILE}")
        print(f"Quality report: {REPORT_FILE}")

    finally:
        # Remove temporary files after either success or failure.
        for temp_path in (output_tmp, report_tmp):
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
