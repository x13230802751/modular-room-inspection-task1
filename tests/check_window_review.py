"""Audit a window review and compare primary measurements with a reference run."""
from pathlib import Path
import json
import sys

import numpy as np
from docx import Document

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"third_party")]
from wall_flatness.io import read_cloud
from room_geometry import section_axis


def audit(cloud,run,control):
    load=lambda p: json.loads(p.read_bytes())
    s,old=[load(p/"summary.json") for p in (run,control)]
    xyz,digest=read_cloud(str(cloud),with_hash=True)
    if s["cloud"]["input_unit"]=="mm":
        xyz*=.001
    assert digest==s["cloud"]["sha256"]==old["cloud"]["sha256"]
    for key in ("walls","room","preprocessing","manual_reference","floor","ceiling"):
        assert s[key]==old[key],key
    assert (run/"window_sections.json").read_bytes()==(control/"window_sections.json").read_bytes()
    review=s["window_corner_review"]
    assert review["source_rows_sha256"]==s["preprocessing"]["source_rows_sha256"]
    assert review["preprocessing"]==s["preprocessing"]["method"]
    assert len(review["windows"])==sum(o["type"]=="window" for w in s["walls"] for o in w["openings"])
    eligible=np.isfinite(xyz).all(1)
    if s["preprocessing"]["source_rows_file"]:
        with np.load(run/s["preprocessing"]["source_rows_file"]) as a:
            eligible[:]=False;eligible[a["source_rows"]]=True
    for w in s["walls"]:
        path=w["whole"].get("residual_file")
        if path:
            with np.load(run/path) as a,np.load(control/path) as b:
                for key in a.files:
                    np.testing.assert_array_equal(a[key],b[key])
    by_id={w["id"]:w for w in s["walls"]}
    for item in review["windows"]:
        if item["status"]!="evaluated":
            continue
        wall=by_id[item["wall_id"]];c=np.array(wall["plane_center_m"]);n=np.array(wall["plane_normal"])
        for key in ("face","deep"):
            fit=item[key];target=0 if key=="face" else fit["slice_mm"]
            if fit["corners_xyz_m"] is not None:
                corners=np.asarray(fit["corners_xyz_m"])
                np.testing.assert_allclose(-(corners-c)@n*1000,target,atol=1e-7)
                u=(corners-c)@section_axis(wall,s["floor"]);h=(corners-s["floor"]["center_m"])@s["floor"]["normal"]
                def at(a,b,along,across,cut):
                    return across[a]+(cut-along[a])*(across[b]-across[a])/(along[b]-along[a])
                height=fit["width_level_m"];x=fit["height_level_u_m"]
                width=(at(1,2,h,u,height)-at(0,3,h,u,height))*1000
                size=(at(3,2,u,h,x)-at(0,1,u,h,x))*1000
                np.testing.assert_allclose([width,size],[fit["width_mm"],fit["height_mm"]],atol=1e-7)
            for edge in fit.get("edge_evidence",[]):
                ids=edge.get("source_rows",[])
                if ids:
                    assert eligible[ids].all()
                    depths=-(xyz[ids]-c)@n*1000
                    if key=="face":
                        assert depths.min()>=8-1e-7 and depths.max()<=80+1e-7
                    else:
                        assert np.max(abs(depths-target))<=6+1e-7
    doc=Document(run/"report.docx")
    snippets=" ".join(p.text for p in doc.paragraphs)
    assert "window corner cross-check" in snippets.lower()
    assert "window corner cross-check" in (run/"report.html").read_text(encoding="utf8").lower()
    assert load(run/"report_manifest.json")["window_corner_review"]["method"]=="profile_reveal"
    return {"cloud_sha256":digest,"method":review["method"],"preprocessing":review["preprocessing"],
            "windows":len(review["windows"]),"original_row_depths":True,"reprojected_dimensions":True,
            "primary_and_rms_match_control":True,"word_and_html":True}


if __name__=="__main__":
    print(json.dumps(audit(sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3])),indent=2))
