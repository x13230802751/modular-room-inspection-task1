"""Production point selection in metre coordinates, before all measurement stages."""
from hashlib import sha256

import numpy as np


METHODS = ("raw", "radius")
RADIUS_MM = 20
MIN_OTHER_POINTS = 4
MAP_FILE = "detector_source_rows.npz"


def row_digest(rows):
    return sha256(np.asarray(rows, dtype="<i8").tobytes()).hexdigest()


def select_input(points, method, output):
    """Keep the source row space. Excluded rows are unavailable to every geometry stage."""
    if method not in METHODS:
        raise ValueError(f"Unknown preprocessing method {method!r}. Choose raw or radius.")
    eligible = np.flatnonzero(np.isfinite(points).all(axis=1))
    finite_count = len(eligible)
    parameters = {}
    if method == "radius":
        from scipy.spatial import cKDTree
        if finite_count <= MIN_OTHER_POINTS:
            raise ValueError("Radius filtering needs at least five finite input points.")
        xyz = points[eligible]
        # The fifth nearest record counts the query itself exactly once, even at duplicate XYZ.
        distances, _ = cKDTree(xyz).query(xyz, k=[MIN_OTHER_POINTS + 1])
        keep = distances[:, 0] <= RADIUS_MM / 1000
        if not keep.any():
            raise ValueError("Radius filtering removed all finite rows. Check input units and point spacing.")
        if not keep.all():
            points = points.copy()
            points[eligible[~keep]] = np.nan
        eligible = eligible[keep]
        parameters = {"radius_mm": RADIUS_MM, "min_other_points": MIN_OTHER_POINTS}
    map_file = None
    if len(eligible) != len(points):
        map_file = MAP_FILE
        np.savez_compressed(output / map_file, source_rows=eligible.astype("<i8", copy=False))
    record = {
        "api_version": 1, "method": method, "parameters": parameters,
        "input_rows": len(points), "finite_rows": finite_count, "retained_rows": len(eligible),
        "removed_finite_rows": finite_count - len(eligible), "coordinates": "original_xyz",
        "source_rows_file": map_file, "source_rows_sha256": row_digest(eligible),
    }
    return points, record


def validate_row_map(directory, record):
    total, finite, retained=(record[k] for k in ("input_rows","finite_rows","retained_rows"))
    if not 0<=retained<=finite<=total or finite-retained!=record["removed_finite_rows"]:
        raise ValueError("Inconsistent counts in the recorded point selection.")
    if record["source_rows_file"] is None:
        digest=sha256()
        for start in range(0,total,65536):
            digest.update(np.arange(start,min(start+65536,total),dtype="<i8").tobytes())
        if retained!=total or digest.hexdigest()!=record["source_rows_sha256"]:
            raise ValueError("The recorded identity selection does not match the input rows.")
        return
    if record["source_rows_file"] != MAP_FILE or not (directory / MAP_FILE).is_file():
        raise ValueError("Missing the declared detector-to-source row map.")
    with np.load(directory / MAP_FILE, allow_pickle=False) as mapping:
        rows = mapping["source_rows"]
        if (rows.shape != (retained,) or rows.dtype.kind not in "iu"
                or (retained and (rows[0]<0 or rows[-1]>=total or np.any(rows[1:]<=rows[:-1])))
                or row_digest(rows) != record["source_rows_sha256"]):
            raise ValueError("The detector-to-source row map does not match the saved selection.")


def description(record):
    if record is None:
        return "Input preprocessing was not recorded in this saved inspection."
    if record["method"] == "raw":
        method = "Original point cloud (raw)."
    else:
        params = record["parameters"]
        method = (f'Radius outlier removal. Each retained point has at least {params["min_other_points"]} '
                  f'other points within {params["radius_mm"]} mm.')
    return (f'{method} Door and window dimensions and wall RMS use the original coordinates of '
            f'{record["retained_rows"]:,} of {record["finite_rows"]:,} finite input points.')
