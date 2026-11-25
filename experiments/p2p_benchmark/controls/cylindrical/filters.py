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


def radius_mask(points, params, workers):
    statistic = np.empty(len(points))
    k = params["min_other_points"]
    if len(points) <= k:
        return np.zeros(len(points), dtype=bool), params["radius_mm"]
    for rows, distances, _ in neighbourhoods(points, k, workers):
        statistic[rows] = distances[:, -1]
    threshold = params["radius_mm"] / 1000
    return statistic <= threshold, float(threshold * 1000)


def classical_bilateral(points, params, workers):
    result = points.copy()
    for rows, distances, indices in neighbourhoods(points, params["smoothing_other_points"], workers):
        offsets = points[indices] - points[rows, None]
        supported = distances <= params["support_radius_mm"] / 1000
        count = supported.sum(axis=1)
        usable = count >= params["min_smoothing_neighbours"]
        weights = np.exp(-0.5 * (distances * 1000 / params["spatial_sigma_mm"]) ** 2) * supported
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


def ball_batches(tree, target_ids, radius, workers):
    """All rows inside each search ball, including its centre. No k-neighbour truncation."""
    for start in range(0, len(target_ids), 4096):
        rows = target_ids[start:start + 4096]
        groups = tree.query_ball_point(tree.data[rows], radius, workers=workers, return_sorted=True)
        count = np.fromiter(map(len, groups), dtype=np.int64, count=len(rows))
        first = np.r_[0, np.cumsum(count)[:-1]]
        query = np.repeat(np.arange(len(rows)), count)
        neighbour = np.concatenate(groups).astype(np.intp, copy=False)
        offset = tree.data[neighbour] - tree.data[rows[query]]
        yield rows, query, neighbour, offset, first, count


def pca(offset, weight, first):
    total = np.maximum(np.add.reduceat(weight, first), np.finfo(float).tiny)
    mean = np.add.reduceat(offset * weight[:, None], first, axis=0) / total[:, None]
    covariance = np.empty((len(first), 3, 3))
    for i in range(3):
        for j in range(i + 1):
            second = np.add.reduceat(offset[:, i] * offset[:, j] * weight, first) / total
            covariance[:, i, j] = covariance[:, j, i] = second - mean[:, i] * mean[:, j]
    values, vectors = np.linalg.eigh(covariance)
    return np.maximum(values, 0), vectors[:, :, 0]


def normal_field(tree, settings, workers):
    radius = settings["pca_radius_mm"] / 1000
    rows_all = np.arange(len(tree.data))
    normals = np.zeros_like(tree.data)
    curvature = np.zeros(len(rows_all))
    valid = np.zeros(len(rows_all), dtype=bool)
    for rows, _, _, offsets, first, count in ball_batches(tree, rows_all, radius, workers):
        values, normals[rows] = pca(offsets, np.ones(len(offsets)), first)
        valid[rows] = (count > settings["pca_min_other_points"]) & (values[:, 1] > 1e-14)
        curvature[rows] = values[:, 0] / np.maximum(values.sum(axis=1), 1e-30)
    if not valid.any():
        return normals, valid, 0
    threshold = np.quantile(curvature[valid], settings["feature_curvature_quantile"])
    features = np.flatnonzero(valid & (curvature > threshold))
    refined = normals.copy()
    angular_scale = np.deg2rad(settings["normal_bandwidth_degrees_as_radians"])
    for rows, q, neighbours, offsets, first, count in ball_batches(tree, features, radius, workers):
        bandwidth = settings["density_scale"] * (4 * np.pi / 3) ** (1/3) * radius / np.cbrt(count)
        dot = np.abs(np.einsum("ij,ij->i", normals[rows[q]], normals[neighbours])).clip(0, 1)
        distance2 = np.einsum("ij,ij->i", offsets, offsets)
        weight = np.exp(-.5 * (distance2 / bandwidth[q]**2 + ((1 - dot) / angular_scale)**2)) * valid[neighbours]
        values, estimated = pca(offsets, weight, first)
        usable = values[:, 1] > 1e-14
        refined[rows[usable]] = estimated[usable]
    return refined, valid, len(features)


def cylindrical_projection(points, radius_mm, settings, workers):
    """One synchronous pass based on Liu et al. (2026), with settings recorded in the protocol."""
    tree = cKDTree(points)
    normals, valid, feature_count = normal_field(tree, settings, workers)
    radius = radius_mm / 1000
    half_height = radius * settings["height_over_radius"] / 2
    angular_scale = np.deg2rad(settings["normal_bandwidth_degrees_as_radians"])
    result = points.copy()
    supported = 0
    candidates = np.flatnonzero(valid)
    for rows, q, neighbour, offset, first, _ in ball_batches(tree, candidates, np.hypot(radius, half_height), workers):
        normal = normals[rows[q]]
        height = np.einsum("ij,ij->i", offset, normal)
        distance2 = np.einsum("ij,ij->i", offset, offset)
        inside = (distance2 - height**2 <= radius**2) & (np.abs(height) <= half_height) & valid[neighbour]
        dot = np.abs(np.einsum("ij,ij->i", normal, normals[neighbour])).clip(0, 1)
        weight = inside * np.exp(-.5 * (distance2 / radius**2 + ((1 - dot) / angular_scale)**2))
        usable = np.add.reduceat(inside.astype(np.int64), first) > settings["min_other_valid_in_cylinder"]
        step = np.add.reduceat(weight * height, first) / np.add.reduceat(weight, first)
        result[rows[usable]] += (step[:, None] * normals[rows])[usable]
        supported += int(usable.sum())
    return result, dict(valid_normals=int(valid.sum()), curvature_features=feature_count, supported_cylinders=supported)


def apply_filter(raw, method, workers=1):
    if method not in PROTOCOL["methods"]:
        raise ValueError(f"Unknown method {method}")
    params = PROTOCOL["parameters"]
    source_rows = np.flatnonzero(np.isfinite(raw).all(axis=1))
    points = raw[source_rows]
    if not len(points):
        raise ValueError("The input contains no finite coordinates.")
    threshold_mm = None
    detail = {}
    if method in {"radius", "radius_cylinder12"}:
        keep, threshold_mm = radius_mask(points, params, workers)
        points, source_rows = points[keep], source_rows[keep]
    if not len(points):
        raise ValueError("The filter rejected every finite input row.")
    if method == "bilateral":
        points = classical_bilateral(points, params, workers)
    elif method in params["cylinder"]["radii_mm"]:
        radius = params["cylinder"]["radii_mm"][method]
        points, detail = cylindrical_projection(points, radius, params["cylinder"], workers)
    displacement = np.linalg.norm(points - raw[source_rows], axis=1) * 1000
    stat = dict(input_rows=len(raw), finite_rows=int(np.isfinite(raw).all(axis=1).sum()),
                retained_rows=len(points), moved_over_1mm=int((displacement > 1).sum()),
                median_move_mm=float(np.median(displacement)), p95_move_mm=float(np.quantile(displacement, .95)),
                max_move_mm=float(displacement.max()), mask_threshold_mm=threshold_mm, **detail)
    return points, source_rows, stat
