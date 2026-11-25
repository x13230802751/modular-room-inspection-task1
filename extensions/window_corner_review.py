"""Optional, read-only window measurement cross-check on a completed geometry fit."""
from hashlib import sha256
from pathlib import Path

import numpy as np

from experiments.window_corners import geometry


def review_face(view, seed, height, horizontal):
    refined, evidence = geometry.reveal_fit(view, seed, geometry.REVEAL)
    count = sum(edge["status"] == "reveal_plane" for edge in evidence)
    width, size = geometry.dimensions(refined, height, horizontal)
    return refined, {"depth_mm":0, "width_level_m":height, "height_level_u_m":horizontal,
                     "width_mm":width, "height_mm":size, "supported_sides":count,
                     "corners_xyz_m":view.world(refined), "edge_evidence":evidence,
                     "status":"reveal_supported" if count==4 else "mixed" if count else "profile_only"}


def review_recess(view, outline, deep, horizontal):
    fit = {"status":"no_supported_width_layer","width_mm":None,"height_mm":None,"corners_xyz_m":None,
           "slice_mm":None,"width_level_m":deep["height_m"],"height_level_u_m":horizontal}
    if deep["status"]=="candidate":
        level=deep["representative"]["slice_center_depth_mm"]
        ids=np.flatnonzero(abs(view.d-level/1000)<=.006)
        q,audit=geometry.raw_refit(view,outline,ids)
        fit.update(status="insufficient_four_edge_support",slice_mm=level,edge_evidence=audit)
        if q is not None:
            dw,dh=geometry.dimensions(q,deep["height_m"],horizontal)
            fit.update(status="candidate",width_mm=dw,height_mm=dh,corners_xyz_m=view.world(q,level/1000))
    return fit


def review_windows(points, inside_ids, summary, sections):
    directory=Path(geometry.__file__).parent
    record={"version":1,"method":"profile_reveal","preprocessing":summary["preprocessing"]["method"],
            "source_rows_sha256":summary["preprocessing"]["source_rows_sha256"],
            "protocol_sha256":sha256((directory/"protocol.json").read_bytes()).hexdigest(),
            "source_sha256":sha256((directory/"geometry.py").read_bytes()).hexdigest(),"windows":[]}
    section_by_id={w["opening_id"]:w for w in sections["windows"]}
    for wall in summary["walls"]:
        windows=[o for o in wall["openings"] if o["type"]=="window"]
        if not windows:
            continue
        view=None
        if len(wall["structural_corners"])==4:
            view=geometry.WallView(wall["id"],points,wall,summary["floor"],inside_ids,wall["structural_corners"])
        for o in windows:
            item={"wall_id":wall["id"],"opening_id":o["id"]}
            record["windows"].append(item)
            if view is None:
                item["status"]="missing_wall_boundary"
                continue
            item["status"]="evaluated"
            height=o["width_at_height_m"]; horizontal=o["center_uv_m"][0]
            seed=np.asarray(o["corners_uv_m"])
            _,item["face"]=review_face(view,seed,height,horizontal)
            deep=section_by_id[o["id"]]["deep"]
            item["deep"]=review_recess(view,seed,deep,horizontal)
    return record
