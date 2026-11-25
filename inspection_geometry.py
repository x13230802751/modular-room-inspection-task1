"""Shared wall discovery and window proposal stages for the two input treatments."""
import re

import numpy as np
from openings import position_openings


def discover_geometry(points, config, algorithms):
    discovery = algorithms.walls(points, config)
    candidates = discovery["walls"]
    named = set()
    for wall in candidates:
        wid = wall["id"]
        if not isinstance(wid,str) or not re.fullmatch("[A-Za-z0-9_-]+",wid) or wid in named:
            raise ValueError("Wall IDs must be unique and contain only letters, digits, underscores or hyphens.")
        named.add(wid)
        ids = np.asarray(wall["expanded_indices"])
        if (ids.ndim!=1 or ids.dtype.kind not in "iu" or len(ids)<3 or np.any(ids<0) or np.any(ids>=len(points))
                or len(np.unique(ids))!=len(ids) or not np.isfinite(points[ids]).all()):
            raise ValueError(f"{wid} requires distinct valid original point indices.")
        wall["expanded_indices"]=ids
        wall.setdefault("discovery_support_count",len(ids))
    bounds = algorithms.corners(points, discovery, config)
    walls, inside_ids = bounds["walls"], np.asarray(bounds["inside_ids"])
    if (inside_ids.ndim!=1 or inside_ids.dtype.kind not in "iu" or np.any(inside_ids<0)
            or np.any(inside_ids>=len(points)) or not np.isfinite(points[inside_ids]).all()):
        raise ValueError("The room boundary stage must return valid original point indices.")
    measured_ids = {w["id"] for w in walls}
    if len(measured_ids)!=len(walls) or not measured_ids.issubset(named):
        raise ValueError("Boundary walls must be distinct members of the candidate set.")
    return discovery, bounds, inside_ids


def locate_openings(algorithms, points, inside_ids, wall, floor, structural, node, native):
    items, checks = algorithms.openings(points, inside_ids, wall, floor, structural, node)
    items = position_openings(items, wall, floor)
    if native:
        for item in items:
            item.setdefault("status", "candidate")
    return items, checks
