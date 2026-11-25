"""Independent radius-selected window measurement and association in original scan coordinates."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from scipy.optimize import linear_sum_assignment

from algorithms import load_profile
from experiments.window_corners import geometry
from extensions import window_corner_review as edge_review
from inspection_geometry import discover_geometry, locate_openings
from openings import position_openings
from preprocessing import select_input
from room_geometry import section_axis
from wall_rms import write_json
from window_sections import measure_section

DIRECTORY = "group09"
RESULT = "group09/result.json"
MATCH = {"min_iou":0.50, "max_center_m":0.35, "max_plane_m":0.12, "max_normal_angle_deg":10}


def file_digest(path):
    return sha256(path.read_bytes()).hexdigest()


def candidate_overlap(raw, other, floor):
    wall, opening = raw
    p = np.asarray(opening["corners_xyz_m"])
    q = np.asarray(other["proposal_corners_xyz_m"])
    n, m = np.asarray(wall["plane_normal"]), np.asarray(other["wall_normal"])
    delta = q.mean(axis=0)-p.mean(axis=0)
    gap = np.linalg.norm(delta)
    if (n@m < np.cos(np.deg2rad(MATCH["max_normal_angle_deg"])) or gap>MATCH["max_center_m"]
            or max(abs(delta@n),abs(delta@m))>MATCH["max_plane_m"]):
        return None
    axes = np.stack([section_axis(wall,floor),floor["normal"]],axis=1)
    a,b = p@axes,q@axes
    size = np.maximum(0,np.minimum(a.max(0),b.max(0))-np.maximum(a.min(0),b.min(0)))
    intersection = float(np.prod(size))
    union = np.prod(np.ptp(a,axis=0))+np.prod(np.ptp(b,axis=0))-intersection
    iou = intersection/union if union>0 else 0
    return (float(iou),float(gap*1000)) if iou>=MATCH["min_iou"] else None


def associate_windows(official, reviews):
    raw=[(wall,o) for wall in official["walls"] for o in wall["openings"] if o["type"]=="window"]
    pairs=[{"raw_id":o["id"],"review_id":None,"status":"raw_only"} for _,o in raw]
    used=set()
    if raw and reviews:
        weights=np.zeros((len(raw),len(reviews)))
        evidence={}
        for i,item in enumerate(raw):
            for j,other in enumerate(reviews):
                match=candidate_overlap(item,other,official["floor"])
                if match:
                    evidence[i,j]=match
                    weights[i,j]=min(weights.shape)+1+match[0]
        rows,cols=linear_sum_assignment(-weights)
        for i,j in zip(rows,cols):
            if (i,j) in evidence:
                overlap,gap=evidence[i,j]
                pairs[i].update(review_id=reviews[j]["id"],status="matched",iou=overlap,center_gap_mm=gap)
                used.add(j)
    pairs.extend({"raw_id":None,"review_id":w["id"],"status":"review_only"} for j,w in enumerate(reviews) if j not in used)
    return pairs


def measure_radius_windows(points, run_dir, context, config, node, record):
    points, record["preprocessing"] = select_input(points,"radius",run_dir)
    algorithms=load_profile().for_cloud(replace(context,preprocessing_method="radius"))
    record["geometry_providers"]={k:algorithms.manifest["stages"][k] for k in ("walls","corners","openings")}
    discovery,bounds,inside=discover_geometry(points,config,algorithms)
    floor=discovery["floor"]
    record["floor"]=floor
    record["warnings"]=list(discovery.get("warnings",[]))+list(bounds["warnings"])
    record["walls"]=[]
    for wall in bounds["walls"]:
        wid=wall["id"]
        corners=bounds["corners"].get(wid,[])
        record["walls"].append({"id":wid,"plane_center_m":wall["plane_center_m"],"plane_normal":wall["plane_normal"],
                                "boundary_xyz_m":[c["xyz_m"] for c in corners]})
        openings,_=locate_openings(algorithms,points,inside,wall,floor,corners,node,
                                  discovery.get("mode")=="efficient_ransac")
        windows=[o for o in openings if o["type"]=="window"]
        view=geometry.WallView(wid,points,wall,floor,inside,corners) if windows and len(corners)==4 else None
        for opening in windows:
            item={"id":opening["id"],"wall_id":wid,"wall_normal":wall["plane_normal"],
                  "proposal_corners_xyz_m":opening["corners_xyz_m"],"status":"missing_wall_boundary"}
            record["windows"].append(item)
            if view is None:
                continue
            refined,face=edge_review.review_face(view,np.asarray(opening["corners_uv_m"]),opening["width_at_height_m"],
                                                opening["center_uv_m"][0])
            fitted=position_openings([{"type":"window","corners_uv_m":refined}],wall,floor)[0]
            fitted["id"]=opening["id"]
            section=measure_section(points,wid,fitted,view.u,view.h,view.d,8,run_dir)
            deep=edge_review.review_recess(view,refined,section["deep"],fitted["center_uv_m"][0])
            item.update(status="evaluated",face=face,recessed_width=section["deep"],recessed_four_edges=deep,
                        profile_file=section["profile_file"],profile_sha256=file_digest(run_dir/section["profile_file"]))
    record["status"]=("complete" if record["walls"] and all(len(w["boundary_xyz_m"])==4 for w in record["walls"])
                      else "limited")


def run_review(output, points, context, config, node, official):
    with TemporaryDirectory(dir=output,prefix=".group09-") as tmp:
        location=Path(tmp)/DIRECTORY
        location.mkdir()
        record={"version":1,"combination":9,"method":"profile_reveal","cloud_sha256":context.sha256,
                "raw_selection_sha256":official["preprocessing"]["source_rows_sha256"],"preprocessing":None,
                "source_sha256":file_digest(Path(geometry.__file__)),"review_source_sha256":file_digest(Path(__file__)),
                "edge_adapter_sha256":file_digest(Path(edge_review.__file__)),
                "protocol_sha256":file_digest(Path(geometry.__file__).with_name("protocol.json")),
                "association":MATCH,"windows":[]}
        reference=Path(__file__).parent/"references/group09_benchmark.json"
        benchmark=json.loads(reference.read_bytes())
        record["benchmark"]={key:benchmark[key] for key in
                             ("version","benchmark_date","scope","nominal_score","tolerances","domain_weight_points","counts","panel","scores")}
        record["benchmark"]["reference_sha256"]=file_digest(reference)
        try:
            measure_radius_windows(points,location,context,config,node,record)
        except (ValueError,RuntimeError,np.linalg.LinAlgError) as error:
            # A failed secondary measurement must leave a usable, explicitly labelled raw inspection.
            record.update(status="unavailable",reason=str(error),windows=[])
            record["pairs"]=[]
            # Discard partial depth profiles. Keep the declared selection map for auditing a completed selection.
            complete=Path(tmp)/"unavailable"
            complete.mkdir()
            if record["preprocessing"] and record["preprocessing"]["source_rows_file"]:
                name=record["preprocessing"]["source_rows_file"]
                (location/name).replace(complete/name)
            location=complete
        else:
            record["pairs"]=associate_windows(official,record["windows"])
        write_json(location/"result.json",record)
        descriptor={"version":1,"combination":9,"status":record["status"],"file":RESULT,
                    "sha256":file_digest(location/"result.json"),"cloud_sha256":context.sha256}
        location.rename(output/DIRECTORY)
    return descriptor
