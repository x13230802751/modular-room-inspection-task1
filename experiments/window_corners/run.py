"""Run a window audit beside a saved inspection, or reproduce the two-room study."""
import argparse
import csv
from hashlib import sha256
from pathlib import Path
import platform
from tempfile import TemporaryDirectory

import numpy as np

from evaluate import METHODS, ROOT, associate, dimensions, read, records_for_room, run_wall, save
from synthetic import build


def truth_stats(record,truth,kind):
    output=[]
    for method,result in record["methods"].items():
        windows=result["windows"]
        matches=associate(windows,truth)
        row=dict(case=record["case"],group=kind,method=method,expected=len(truth),reported=len(windows),
                 tp=len(matches),fp=len(windows)-len(matches),fn=len(truth)-len(matches),
                 face_seconds=result["face_seconds"])
        for i,j,iou in matches:
            w=windows[i]; t=truth[j]
            face=np.asarray(w["face_uv_m"])
            x,h=t["section"]
            width,height=dimensions(face,h,x)
            row.update(iou=iou,common_level_m=h,common_center_u_m=x,face_width_mm=width,face_height_mm=height,
                       width_difference_mm=width-t["width"],height_difference_mm=height-t["height"],
                       corner_mean_error_mm=None,deep_width_mm=w["deep"]["width_mm"],
                       deep_four_status=w["deep"]["four_corners_status"])
            if kind!="course":
                point_errors=np.linalg.norm(w["face_xyz_m"]-t["face_xyz"],axis=1)*1000
                row.update(corner_mean_error_mm=point_errors.mean(),corner_max_error_mm=point_errors.max())
                row["deep_four_observable"]=t["four_deep_observed"]
            deep=w["deep"]
            if deep["status"]=="candidate":
                row.update(deep_start_mm=deep["depth_range_mm"][0],deep_end_mm=deep["depth_range_mm"][1])
                if kind!="course":
                    k=deep["slice_center_mm"]/1000
                    if t["has_recess"]:
                        row["deep_start_minus_step_mm"]=deep["depth_range_mm"][0]-t["step_m"]*1000
                        row["deep_difference_mm"]=deep["width_mm"]-dimensions(t["deep"],deep["height_m"],x)[0]
                    if deep["four_corners_status"]=="candidate" and t["four_deep_observed"]:
                        row["deep_corner_mean_error_mm"]=np.linalg.norm(
                            np.asarray(deep["corners_xyz_m"])-t["view"].world(t["deep"],k),axis=1).mean()*1000
                else:
                    row["deep_difference_mm"]=deep["width_mm"]-t["width"]
        output.append(row)
    return output


def write_table(path,rows):
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=keys)
        writer.writeheader();writer.writerows(rows)


def train_free_network(args):
    if bool(args.network)!=bool(args.weights):
        raise ValueError("Supply both the official source checkout and the v2 weights.")
    if not args.network:
        return None
    from scalelsd_adapter import ScaleLines
    return ScaleLines(args.network,args.weights,args.device)


def study(args,output,network,methods):
    from geometry import edges
    test=read(Path(__file__).with_name("protocol.json"))
    (output/"cases").mkdir()
    all_rows=[]
    for room in ["M26","M04"]:
        run=args.runs/(room+"_raw")
        data=read(run/"summary.json")
        calibration=read(ROOT/"references/manual_reference.json")["rooms"][room]
        assert data["cloud"]["sha256"]==calibration["sha256"] and data["preprocessing"]["method"]=="raw"
        cases=records_for_room(args.clouds/(room+".pcd"),run,network,methods,output/"rasters")
        for case,wall in zip(cases,data["walls"],strict=True):
            truth=[]
            if room=="M26" and wall["id"]=="W01":
                o=next(o for o in wall["openings"] if o["type"]=="window")
                truth=[dict(face=o["corners_uv_m"],width=calibration["openings_mm"]["window"]["width"],
                            height=calibration["openings_mm"]["window"]["height"],section=[o["center_uv_m"][0],o["width_at_height_m"]])]
            case["reference_count"]=len(truth)
            baseline=case["methods"]["profile"]["windows"]
            saved=[o for o in wall["openings"] if o["type"]=="window"]
            assert len(baseline)==len(saved)
            for w,o in zip(baseline,saved):
                np.testing.assert_allclose(w["face_xyz_m"],o["corners_xyz_m"],atol=1e-8,rtol=0)
                stored=next(k for k in read(run/"window_sections.json")["windows"] if k["opening_id"]==o["id"])
                np.testing.assert_allclose(w["deep"]["width_mm"],stored["deep"]["width_mm"],atol=1e-7,rtol=0)
            save(output/"cases"/(case["case"]+".json"),case)
            all_rows.extend(truth_stats(case,truth,"course"))
            print(case["case"],{k:len(v["windows"]) for k,v in case["methods"].items()},flush=True)
    plan=test["synthetic"]
    for group,conditions,positive,negative in [
        ("development",plan["positive_conditions"],plan["seeds"],plan["negative_seeds"]),
        ("holdout",plan["holdout_positive_conditions"],plan["holdout_seeds"],plan["holdout_negative_seeds"])]:
        cases=[(c,i) for c in conditions for i in positive]+[(c,i) for c in plan["negative_conditions"] for i in negative]
        for condition,seed in cases:
            view,truth=build(seed,condition)
            case=run_wall(view,network,methods,output/"rasters")
            for t in truth:
                q=t["face"]; x=q[:,0].mean()
                l=edges(q)
                h=np.mean(l[2:,0]*x+l[2:,1])
                t["width"],t["height"]=dimensions(q,h,x)
                t.update(section=[x,h],view=view,face_xyz=view.world(q))
            case["truth"]=[{k:v for k,v in t.items() if k!="view"} for t in truth]
            save(output/"cases"/(case["case"]+".json"),case)
            all_rows.extend(truth_stats(case,truth,group))
            print(case["case"],{k:len(v["windows"]) for k,v in case["methods"].items()},flush=True)
    write_table(output/"measurements.csv",all_rows)


def inspect(args,output,network,methods):
    cases=records_for_room(args.cloud,args.run,network,methods,output/"rasters")
    save(output/"window_corner_comparison.json",cases)
    rows=[]
    for c in cases:
        for method,result in c["methods"].items():
            body=result["windows"]
            if not body:
                rows.append(dict(wall=c["case"],method=method,windows=0))
            for i,w in enumerate(body,1):
                rows.append(dict(wall=c["case"],method=method,windows=len(body),window=i,face_width_mm=w["face_width_mm"],
                                 face_height_mm=w["face_height_mm"],face_height_level_m=w["width_level_m"],face_depth_mm=0,
                                 deep_width_mm=w["deep"]["width_mm"],deep_depths_mm=w["deep"]["depth_range_mm"],
                                 deep_four_corners=w["deep"]["four_corners_status"]))
    write_table(output/"measurements.csv",rows)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    modes=ap.add_subparsers(dest="command",required=True)
    a=modes.add_parser("inspect");a.add_argument("--cloud",type=Path,required=True);a.add_argument("--run",type=Path,required=True)
    b=modes.add_parser("study");b.add_argument("--clouds",type=Path,required=True);b.add_argument("--runs",type=Path,required=True)
    for p in [a,b]:
        p.add_argument("--out",type=Path,required=True)
        p.add_argument("--network",type=Path);p.add_argument("--weights",type=Path)
        p.add_argument("--device",default="cuda",choices=["cpu","cuda"])
    args=ap.parse_args()
    dest=args.out.resolve()
    if dest.exists():
        ap.error("Choose a new output directory.")
    if args.command=="inspect" and dest.is_relative_to(args.run.resolve()):
        ap.error("Save the evaluation in a directory outside the measurement run.")
    dest.parent.mkdir(parents=True,exist_ok=True)
    network=train_free_network(args)
    methods=[m for m in METHODS if network or not m.endswith("_scalelsd")]
    with TemporaryDirectory(dir=dest.parent,prefix=".window-eval-") as tmp:
        out=Path(tmp)/"result";out.mkdir()
        here=Path(__file__).resolve().parent
        info={"methods":methods,"protocol_sha256":sha256((here/"protocol.json").read_bytes()).hexdigest(),
              "source_sha256":{name:sha256((here/name).read_bytes()).hexdigest() for name in
                               ("run.py","evaluate.py","geometry.py","synthetic.py","scalelsd_adapter.py")},
              "python":platform.python_version(),"numpy":np.__version__}
        if network:
            import timm,cv2,torch,subprocess
            from scalelsd_adapter import WEIGHT_SHA256, AUTHOR_COMMIT
            commit=subprocess.check_output(["git","-c",f"safe.directory={args.network.resolve().as_posix()}","-C",str(args.network),"rev-parse","HEAD"],text=True).strip()
            if commit!=AUTHOR_COMMIT:
                raise ValueError("Use the official source revision in the model adapter.")
            info.update(model_source=commit,weights_sha256=WEIGHT_SHA256,torch=torch.__version__,timm=timm.__version__,
                        opencv=cv2.__version__,device=args.device,device_name=torch.cuda.get_device_name() if args.device=="cuda" else "CPU")
            control_path=args.network/"assets"/"indoor.jpg"
            control=cv2.imread(str(control_path),cv2.IMREAD_GRAYSCALE)
            network(control)
            info["author_photo_control"]=dict(network.audit,photo_sha256=sha256(control_path.read_bytes()).hexdigest())
            if not network.audit["retained_lines"]:
                raise ValueError("The author indoor image produced no qualifying lines.")
        (study if args.command=="study" else inspect)(args,out,network,methods)
        save(out/"run_manifest.json",info)
        out.rename(dest)


if __name__=="__main__":
    main()
