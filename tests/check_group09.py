"""Verify the score and pairing; optionally audit a paired run against two independent controls."""
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import numpy as np
from docx import Document

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"third_party")]
from algorithms import CloudContext
from group09 import associate_windows, run_review
from group09_report import comparisons, load_review, status_text
from preprocessing import row_digest
from room_geometry import section_axis
from wall_flatness.io import read_cloud


def load(path):
    return json.loads(path.read_bytes())


def benchmark_check():
    data=load(ROOT/"references/group09_benchmark.json")
    for file,digest in data["source_tables_sha256"].items():
        assert sha256((ROOT/"experiments/joint_benchmark"/file).read_bytes()).hexdigest()==digest
    c=data["counts"]
    cases=data["synthetic_cases"]
    assert len(cases)==28 and sum(a["true"] for a in cases)==24 and sum(a["predicted"] for a in cases)==26
    assert sum(a["matched"] for a in cases)==24 and len(data["field_items"])==11
    for mode,t in data["tolerances"].items():
        room=opening=0
        for item in data["field_items"]:
            error=abs(item["measured_mm"]-item["reference_mm"])
            if item["kind"]=="room":
                room+=error<=t["room_mm"]
            else:
                opening+=error<=t["opening_mm"]
        qualified=sum(a["matched"] and a["max_corner_error_mm"]<=t["corner_mm"] for a in cases)
        panel=data["panel"]
        bias=abs(panel["measured_mm"]-panel["truth_mm"])
        assert np.isclose(panel["absolute_bias_mm"],bias)
        coverage=sum(v["rms_mm"] is not None for v in data["field_wall_rms"])/8
        denom=c["opening_total"]+2*c["extra_field_doors"]+c["extra_field_windows"]
        score=25*(room/6+opening/denom+2*qualified/50+coverage*(bias<=t["panel_mm"]))
        assert np.isclose(score,data["scores"][mode])
        if mode=="nominal":
            assert (room,opening,qualified,score)==(6,3,21,86)
    return data["scores"]


def association_check():
    p=np.array([[0,0,0],[1,0,0],[1,0,1],[0,0,1]])
    floor={"normal":[0,0,1],"center_m":[0,0,0]}
    wall={"id":"A","plane_center_m":[0,0,0],"plane_normal":[0,1,0],"openings":[]}
    official={"walls":[wall],"floor":floor}
    def candidate(name,shift,normal=(0,1,0)):
        return {"id":name,"proposal_corners_xyz_m":p+shift,"wall_normal":normal}
    wall["openings"]=[{"id":name,"type":"window","corners_xyz_m":p+[shift,0,0]} for name,shift in [("a",0),("b",2)]]
    candidates=[candidate("x",[2.01,0,0]),candidate("y",[0,0,0],(0,-1,0)),candidate("z",[0,.15,0])]
    pairs=associate_windows(official,candidates)
    assert [(q["raw_id"],q["review_id"],q["status"]) for q in pairs]==[
        ("a",None,"raw_only"),("b","x","matched"),(None,"y","review_only"),(None,"z","review_only")]
    duplicate=associate_windows(official,[candidate("first",[0,0,0]),candidate("second",[.01,0,0])])
    assert [q["status"] for q in duplicate]==["matched","raw_only","review_only"]


def unavailable_check():
    with TemporaryDirectory() as tmp:
        out=Path(tmp)
        context=CloudContext("synthetic","m",(0,0,1),"a"*64,4)
        summary={"preprocessing":{"method":"raw","source_rows_sha256":row_digest(range(4))},
                 "cloud":{"sha256":context.sha256,"point_count":4}}
        summary["group09_review"]=run_review(out,np.zeros((4,3)),context,None,None,summary)
        record,_=load_review(out,summary)
        assert record["status"]=="unavailable" and "at least five" in record["reason"]
        assert "unavailable" in status_text(record) and record["pairs"]==[]
        path=out/summary["group09_review"]["file"]
        path.write_bytes(path.read_bytes()+b" ")
        try:
            load_review(out,summary)
        except ValueError:
            pass
        else:
            raise AssertionError("A modified branch record was accepted.")


def arrays_equal(a,b):
    with np.load(a,allow_pickle=False) as x,np.load(b,allow_pickle=False) as y:
        assert set(x.files)==set(y.files)
        for k in x.files:
            np.testing.assert_array_equal(x[k],y[k])


def check_geometry(item,wall,floor,xyz,eligible):
    center=np.asarray(wall["plane_center_m"])
    normal=np.asarray(wall["plane_normal"])
    for key in ("face","recessed_four_edges"):
        fit=item[key]
        depth=0 if key=="face" else fit["slice_mm"]
        if fit["corners_xyz_m"] is not None:
            p=np.asarray(fit["corners_xyz_m"])
            np.testing.assert_allclose(-(p-center)@normal*1000,depth,atol=1e-7)
            u=(p-center)@section_axis(wall,floor)
            h=(p-floor["center_m"])@floor["normal"]
            def cross(a,b,along,across,cut):
                return across[a]+(cut-along[a])*(across[b]-across[a])/(along[b]-along[a])
            height=fit["width_level_m"]
            x=fit["height_level_u_m"]
            width=(cross(1,2,h,u,height)-cross(0,3,h,u,height))*1000
            size=(cross(3,2,u,h,x)-cross(0,1,u,h,x))*1000
            np.testing.assert_allclose([width,size],[fit["width_mm"],fit["height_mm"]],atol=1e-7,rtol=0)
        for edge in fit.get("edge_evidence",[]):
            ids=edge.get("source_rows",[])
            if ids:
                assert eligible[ids].all()
                d=-(xyz[ids]-center)@normal*1000
                if key=="face": assert d.min()>=8-1e-7 and d.max()<=80+1e-7
                else: assert np.max(abs(d-depth))<=6+1e-7
    deep=item["recessed_width"]
    if deep["status"]=="candidate":
        assert np.median(deep["mid_height_samples_mm"])==deep["width_mm"]
        for endpoint in deep["representative"]["endpoints"]:
            i=endpoint["original_index"]
            assert eligible[i]
            np.testing.assert_array_equal(xyz[i],endpoint["xyz_m"])


def audit(cloud,run,raw,radius):
    official=load(run/"summary.json")
    baseline=load(raw/"summary.json")
    filtered=load(radius/"summary.json")
    record,_=load_review(run,official)
    xyz,digest=read_cloud(str(cloud),with_hash=True)
    if official["cloud"]["input_unit"]=="mm":
        xyz*=.001
    assert digest==official["cloud"]["sha256"]==baseline["cloud"]["sha256"]==filtered["cloud"]["sha256"]
    for k in ("preprocessing","walls","room","floor","ceiling","manual_reference"):
        assert official[k]==baseline[k],k
    arrays_equal(run/"wall_points.npz",raw/"wall_points.npz")
    for w in official["walls"]:
        if path:=w["whole"].get("residual_file"): arrays_equal(run/path,raw/path)
    assert (run/"window_sections.json").read_bytes()==(raw/"window_sections.json").read_bytes()
    assert record["status"]=="complete" and record["preprocessing"]==filtered["preprocessing"]
    assert record["floor"]==filtered["floor"]
    selected=np.isfinite(xyz).all(1)
    name=record["preprocessing"]["source_rows_file"]
    if name:
        arrays_equal(run/"group09"/name,radius/name)
        with np.load(radius/name) as f:
            selected[:]=False
            selected[f["source_rows"]]=True
    windows={o["id"]:o for w in filtered["walls"] for o in w["openings"] if o["type"]=="window"}
    assert set(windows)=={v["id"] for v in record["windows"]}
    walls={w["id"]:w for w in filtered["walls"]}
    for w in record["walls"]:
        b=walls[w["id"]]
        for k in ("plane_center_m","plane_normal"): assert w[k]==b[k]
        assert w["boundary_xyz_m"]==[c["xyz_m"] for c in b["structural_corners"]]
    for w in record["windows"]:
        assert w["proposal_corners_xyz_m"]==windows[w["id"]]["corners_xyz_m"]
        if w["status"]=="evaluated":
            check_geometry(w,walls[w["wall_id"]],record["floor"],xyz,selected)
    sections=load(run/"window_sections.json")
    html=(run/"report.html").read_text(encoding="utf8")
    doc=Document(run/"report.docx")
    words=" ".join(p.text for p in doc.paragraphs)
    cells={c.text for t in doc.tables for row in t.rows for c in row.cells}
    for phrase in ("Official raw dimensions and wall RMS","Group 09 window corner review","How the Group 09 benchmark was scored"):
        assert phrase in words and phrase in html
    for label,_,widths,levels,corners,_ in comparisons(official,sections,record):
        assert label in words
        for r in widths+levels+corners:
            assert all(value in cells and value in html for value in r)
    assert load(run/"report_manifest.json")["group09_review"]==official["group09_review"]
    return {"source_sha256":digest,"raw_rows":official["preprocessing"]["retained_rows"],
            "radius_rows":int(selected.sum()),"raw_walls":len(official["walls"]),"pairs":record["pairs"],
            "radius_windows":len(windows),"status":record["status"],
            "official_geometry_equals_raw_control":True,"wall_rows_and_residuals_equal_raw_control":True,
            "independent_radius_proposals_equal_radius_control":True,"fits_and_source_rows_verified":True,
            "paired_tables_verified_in_word_and_html":True}


if __name__=="__main__":
    association_check()
    unavailable_check()
    scores=benchmark_check()
    if len(sys.argv)==1:
        print("Pairing, unavailable and integrity checks passed. Historical scores:",scores)
    elif len(sys.argv)==5:
        print(json.dumps(audit(*map(Path,sys.argv[1:])),indent=2))
    else:
        raise SystemExit("Usage: check_group09.py [SCAN PAIRED RAW_CONTROL RADIUS_CONTROL]")
