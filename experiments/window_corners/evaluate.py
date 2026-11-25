"""Measure face corners and depth candidates from each automatically proposed window."""
from pathlib import Path
from time import perf_counter
import json
import os
import shutil
import sys

import numpy as np
from scipy.optimize import linear_sum_assignment

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"third_party")]
from depth_profile import examine_depths
from openings import profile_candidates, position_openings
from preprocessing import validate_row_map
from room_geometry import room_interior
from wall_flatness.io import read_cloud
from window_sections import candidate_section
from geometry import REVEAL, WallView, dimensions, propose, raster, raw_refit, reveal_fit, select_lines

METHODS=("profile","profile_xyz","profile_reveal","profile_scalelsd","layer_grid","layer_xyz","layer_scalelsd")


def read(path):
    return json.loads(Path(path).read_bytes())


def as_json(value):
    if isinstance(value,np.ndarray):
        return value.tolist()
    if isinstance(value,np.generic):
        return value.item()
    raise TypeError(str(type(value)))


def save(path,record):
    Path(path).write_text(json.dumps(record,default=as_json,allow_nan=False,indent=2)+"\n",encoding="utf8")


def room_input(cloud,run):
    run=Path(run)
    data=read(run/"summary.json")
    xyz,digest=read_cloud(str(cloud),with_hash=True)
    if digest!=data["cloud"]["sha256"] or len(xyz)!=data["cloud"]["point_count"]:
        raise ValueError("The point cloud differs from the saved inspection.")
    if data["cloud"]["input_unit"]=="mm":
        xyz*=.001
    treatment=data["preprocessing"]
    validate_row_map(run,treatment)
    if treatment["source_rows_file"]:
        with np.load(run/treatment["source_rows_file"],allow_pickle=False) as archive:
            keep=np.zeros(len(xyz),bool)
            keep[archive["source_rows"]]=True
            xyz[~keep]=np.nan
    return xyz,data,np.flatnonzero(room_interior(xyz,data["walls"]))


def records_for_room(cloud,run,network,methods,plot_dir=None):
    xyz,data,inside=room_input(cloud,run)
    out=[]
    for wall in data["walls"]:
        name=Path(data["cloud"]["file"]).stem+"_"+wall["id"]
        if len(wall["structural_corners"])!=4:
            out.append(dict(case=name,status="missing_wall_boundary",methods={}))
            continue
        view=WallView(name,xyz,wall,data["floor"],inside,wall["structural_corners"])
        case=run_wall(view,network,methods,plot_dir)
        case["source_sha256"]=data["cloud"]["sha256"]
        case["preprocessing"]=data["preprocessing"]["method"]
        out.append(case)
    return out


def analyze_quad(view,q):
    opening=position_openings([{"type":"window","corners_uv_m":np.asarray(q).tolist()}],view.wall,view.floor)[0]
    height,x=opening["width_at_height_m"],opening["center_uv_m"][0]
    corners=view.world(q)
    gap,near=view.tree.query(corners)
    evidence={"face_uv_m":q,"face_xyz_m":corners,"face_width_mm":opening["width_mm"],"face_height_mm":opening["height_mm"],
              "face_depth_mm":0,"width_level_m":height,"height_level_u_m":x,
              "nearest_face_source_rows":view.face_ids[near],"nearest_face_gap_mm":gap*1000}
    rows=examine_depths(view.u,view.h,view.d,opening)
    deep=candidate_section(rows,height,view.xyz,view.u,view.h,view.d)
    result={k:deep[k] for k in ("status","width_mm","depth_range_mm","height_m","representative")}
    result["four_corners_status"]="no_supported_width_layer"
    if deep["status"]=="candidate":
        depth=deep["representative"]["slice_center_depth_mm"]/1000
        selected=np.flatnonzero(abs(view.d-depth)<=.006)
        candidate,diagnostic=raw_refit(view,q,selected)
        result.update(four_corners_status="insufficient_four_edge_support" if candidate is None else "candidate",
                      slice_center_mm=depth*1000,edge_evidence=diagnostic)
        if candidate is not None:
            result.update(corners_xyz_m=view.world(candidate,depth),corners_uv_m=candidate,
                          fitted_width_mm=dimensions(candidate,height,x)[0],fitted_height_mm=dimensions(candidate,height,x)[1])
    evidence["deep"]=result
    return evidence


def run_wall(view,network,methods,plot_dir=None):
    node=shutil.which(os.environ.get("TASK1_NODE") or "node")
    t0=perf_counter()
    raw,_=profile_candidates(view.xyz,view.inside,view.wall,view.floor,view.corners,node)
    profile=[np.asarray(o["corners_uv_m"]) for o in raw if o["type"]=="window"]
    profile_sec=perf_counter()-t0
    t0=perf_counter()
    proposals=propose(view)
    layered_sec=perf_counter()-t0
    record={"case":view.name,"status":"evaluated","face_points":len(view.face_ids),"bounds_m":view.bounds,
            "layered_proposals":len(proposals),"profile_proposals":len(profile),"methods":{}}
    segments=[]
    use_network=any(m.endswith("_scalelsd") for m in methods)
    if use_network or plot_dir:
        gray,origin,pitch=raster(view)
        if use_network:
            start=perf_counter()
            pixels=network(gray)
            segments=origin+(pixels+.5)*np.array([pitch,-pitch])
            record["network"]=dict(network.audit,seconds=perf_counter()-start)
        if plot_dir:
            from PIL import Image
            plot_dir.mkdir(parents=True,exist_ok=True)
            Image.fromarray(gray).save(plot_dir/(view.name+".png"))
            record["raster"]={"upper_left_boundary":origin,"pitch_m":pitch,"segments_uv_m":segments}
    for method in methods:
        start=perf_counter()
        is_profile=method.startswith("profile")
        seeds=profile if is_profile else proposals
        quads=[]; diagnostics=[]
        for q in seeds:
            if method.endswith("_xyz"):
                refined,diag=raw_refit(view,q)
                diagnostics.append(diag)
            elif method=="profile_reveal":
                refined,diag=reveal_fit(view,q,REVEAL)
                diagnostics.append(diag)
            elif method.endswith("_scalelsd"):
                refined=select_lines(segments,q)
            else:
                refined=q
            if refined is not None:
                quads.append(refined)
        seconds=(profile_sec if is_profile else layered_sec)+perf_counter()-start
        if method.endswith("_scalelsd"):
            seconds+=record["network"]["seconds"]
        measured=[analyze_quad(view,q) for q in quads]
        record["methods"][method]={"windows":measured,"proposal_count":len(seeds),"edge_evidence":diagnostics,
                                    "face_seconds":seconds}
    return record


def associate(items,truth):
    def box(q):
        return np.r_[q.min(axis=0),q.max(axis=0)]
    def iou(a,b):
        intersection=np.maximum(0,np.minimum(a[2:],b[2:])-np.maximum(a[:2],b[:2])).prod()
        return intersection/(np.prod(a[2:]-a[:2])+np.prod(b[2:]-b[:2])-intersection)
    if not items or not truth:
        return []
    matrix=np.array([[iou(box(np.asarray(w["face_uv_m"])),box(np.asarray(t["face"]))) for t in truth] for w in items])
    i,j=linear_sum_assignment(-((matrix>=.5)*(max(matrix.shape)+1)+matrix))
    return [(a,b,float(matrix[a,b])) for a,b in zip(i,j) if matrix[a,b]>=.50]
