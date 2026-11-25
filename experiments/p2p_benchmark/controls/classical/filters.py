"""Spatial filters for the review experiment. All internal XYZ coordinates are metres."""
from pathlib import Path
import json
import numpy as np
from scipy.spatial import cKDTree

PROTOCOL = json.loads(Path(__file__).with_name("protocol.json").read_text(encoding="utf8"))
CHUNK = 16384


def neighbourhoods(points, count, workers):
    """Yield up to count other rows per point. Coincident records remain distinct."""
    tree = cKDTree(points)
    k = min(len(points), count + 1)
    for start in range(0, len(points), CHUNK):
        rows = np.arange(start, min(start + CHUNK, len(points)))
        distances, indices = tree.query(points[rows], k=list(range(1, k + 1)), workers=workers)
        distances[indices == rows[:, None]] = np.inf
        order = np.argsort(distances, axis=1, kind="stable")[:, :min(count, k - 1)]
        yield rows, np.take_along_axis(distances, order, axis=1), np.take_along_axis(indices, order, axis=1)


def binary_mask(points, method, params, workers):
    statistic = np.empty(len(points))
    k = params["min_other_points"] if method == "radius" else params["sor_other_points"]
    if len(points) <= k:
        raise ValueError(f"The {method} mask needs at least {k + 1} finite points.")
    for rows, distances, _ in neighbourhoods(points, k, workers):
        statistic[rows] = distances[:, -1] if method == "radius" else distances.mean(axis=1)
    if method == "radius":
        threshold = params["radius_mm"] / 1000
    else:
        threshold = statistic.mean() + params["sor_sigma"] * statistic.std(ddof=0)
    return statistic <= threshold, float(threshold * 1000)


def smooth(points, mode, params, workers):
    result = points.copy()
    for rows, distances, indices in neighbourhoods(points, params["smoothing_other_points"], workers):
        offsets = points[indices] - points[rows, None]
        supported = distances <= params["support_radius_mm"] / 1000
        count = supported.sum(axis=1)
        usable = count >= params["min_smoothing_neighbours"]
        weights = np.exp(-0.5 * (distances * 1000 / params["spatial_sigma_mm"]) ** 2) * supported
        if mode == "gaussian":
            shift = np.einsum("ij,ijk->ik", weights, offsets) / (1 + weights.sum(axis=1))[:, None]
        else:
            # Centre and supported neighbours form the unweighted local PCA neighbourhood.
            mean = np.einsum("ij,ijk->ik", supported, offsets) / (count + 1)[:, None]
            second = np.einsum("ij,ijk,ijl->ikl", supported, offsets, offsets) / (count + 1)[:, None, None]
            values, vectors = np.linalg.eigh(second - mean[:, :, None] * mean[:, None, :])
            usable &= values[:, 1] > 1e-14
            normal = vectors[:, :, 0]
            height = np.einsum("ijk,ik->ij", offsets, normal)
            weights *= np.exp(-0.5 * (height * 1000 / params["normal_sigma_mm"]) ** 2)
            normal_step = (weights * height).sum(axis=1) / (1 + weights.sum(axis=1))
            shift = normal * normal_step[:, None]
        result[rows[usable]] += shift[usable]
    return result


def apply_filter(raw, method, workers=1):
    if method not in PROTOCOL["methods"]:
        raise ValueError(f"Unknown method {method}")
    params = PROTOCOL["parameters"]
    source_rows = np.flatnonzero(np.isfinite(raw).all(axis=1))
    points = raw[source_rows]
    if not len(points):
        raise ValueError("The input contains no finite coordinates.")
    threshold_mm = None
    if method in {"sor", "radius", "sor_bilateral"}:
        keep, threshold_mm = binary_mask(points, "radius" if method == "radius" else "sor", params, workers)
        points, source_rows = points[keep], source_rows[keep]
    if method in {"gaussian", "bilateral", "sor_bilateral"} and len(points):
        points = smooth(points, "gaussian" if method == "gaussian" else "bilateral", params, workers)
    if not len(points):
        raise ValueError("The filter rejected every finite input row.")
    displacement = np.linalg.norm(points - raw[source_rows], axis=1) * 1000
    stat = dict(input_rows=len(raw), finite_rows=int(np.isfinite(raw).all(axis=1).sum()),
                retained_rows=len(points), moved_over_1mm=int((displacement > 1).sum()),
                median_move_mm=float(np.median(displacement)), p95_move_mm=float(np.quantile(displacement, .95)),
                max_move_mm=float(displacement.max()), mask_threshold_mm=threshold_mm)
    return points, source_rows, stat
