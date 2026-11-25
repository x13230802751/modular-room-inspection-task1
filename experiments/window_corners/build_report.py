"""Build the English course evaluation from the saved comparison and a verified raw M26 run."""
import argparse
import csv
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
from PIL import Image

from evaluate import ROOT, read, METHODS
from report_style import document, figure, heading, table, link

LABEL={"profile":"Production profile","profile_xyz":"Profile + XYZ lines","profile_reveal":"Profile + reveal planes",
       "profile_scalelsd":"Profile + ScaleLSD","layer_grid":"Layered grid","layer_xyz":"Grid + XYZ lines","layer_scalelsd":"Grid + ScaleLSD"}


def rows(path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        return list(csv.DictReader(stream))


def fmt(x,d=2):
    return "—" if x is None or x=="" else f"{float(x):.{d}f}"


def make_figure(study,raw,out,case):
    fig=Figure(figsize=(7.0,3.15),layout="constrained")
    FigureCanvasAgg(fig)
    a,b=fig.subplots(1,2)
    pix=np.asarray(Image.open(study/"rasters/M26_W01.png"))
    info=case["raster"];x0,y0=info["upper_left_boundary"];pitch=info["pitch_m"]
    extent=(x0,x0+pix.shape[1]*pitch,y0-pix.shape[0]*pitch,y0)
    a.imshow(pix,cmap="gray",extent=extent,origin="upper",vmin=0,vmax=290)
    a.add_collection(LineCollection(info["segments_uv_m"],colors="#cd8643",linewidths=.7,alpha=.82))
    q=np.array(case["methods"]["profile"]["windows"][0]["face_uv_m"])
    cycle=np.vstack((q,q[:1]))
    a.plot(*cycle.T,color="#00b4b7",lw=1.4)
    a.scatter(*q.T,s=18,c="#00b4b7",edgecolors="black",linewidths=.5,zorder=4)
    a.set(title="M26 W01 wall projection",xlabel="Along wall (m)",ylabel="Above floor (m)",aspect="equal")
    sec=read(raw/"window_sections.json")["windows"][0];data=rows(raw/sec["profile_file"])
    x=[float(r["depth_mm"]) for r in data if r.get("width_0.50")]
    y=[float(r["width_0.50"]) for r in data if r.get("width_0.50")]
    b.scatter(x,y,s=5,c="#8799a4",label="Supported mid-height slices")
    b.scatter([0],[sec["face"]["width_mm"]],s=36,c="#14686b",marker="s",label="Fitted face",zorder=5)
    deep=sec["deep"];lo,hi=deep["depth_range_mm"]
    b.axvspan(lo,hi,color="#dca960",alpha=.35)
    b.scatter([(lo+hi)/2],[deep["width_mm"]],s=45,c="#ab5117",marker="D",label="Recessed five-slice median",zorder=5)
    b.set(title="Width through the opening",xlabel="Depth into opening (mm)",ylabel="Width (mm)",xlim=(-25,900))
    b.set_ylim(min(deep["width_mm"]-45,min([v for x0,v in zip(x,y) if 0<=x0<=900] or [deep["width_mm"]])),
               max(sec["face"]["width_mm"]+25,2500))
    b.legend(frameon=False,fontsize=7,loc="lower left")
    for ax in (a,b):
        ax.title.set_fontsize(10);ax.xaxis.label.set_size(9);ax.yaxis.label.set_size(9)
        ax.tick_params(labelsize=8);ax.spines[["top","right"]].set_visible(False)
    fig.savefig(out,dpi=215,facecolor="white")


def report(study,raw,out):
    out.parent.mkdir(parents=True,exist_ok=True)
    summary=read(study/"method_summary.json");records=rows(study/"measurements.csv")
    case=read(study/"cases/M26_W01.json");manifest=read(study/"run_manifest.json")
    sel={r["method"]:r for r in summary if r["group"]=="holdout"}
    course={r["method"]:r for r in records if r["case"]=="M26_W01"}
    a,b=sel["profile"],sel["profile_reveal"]
    art=study/"window_measurement_evidence.png";make_figure(study,raw,art,case)
    doc=document("Window corner recognition and measurement")
    doc.add_paragraph("Window corner recognition and measurement","Title")
    doc.add_paragraph("CIVL 7023 Project 1 Task 1   |   M26 and M04   |   25 November 2026")
    doc.add_paragraph(f'The production opening profile remains the primary measurement. The new optional check fits the sides of the recess behind the wall face. It reduced median corner error from {fmt(a["median_corner_mm"])} to {fmt(b["median_corner_mm"])} mm on {b["tp"]} matched holdout windows. M26 provides one field window with tape dimensions and no surveyed corner coordinates.')
    heading(doc,"Measured dimensions in M26")
    data=[]
    for m in ("profile","profile_reveal","profile_xyz","layer_grid","layer_xyz","profile_scalelsd","layer_scalelsd"):
        r=course[m]
        data.append([LABEL[m],fmt(r.get("face_width_mm")),fmt(r.get("face_height_mm")),fmt(r.get("deep_width_mm"))])
    table(doc,"Table 1   W01 opening measurements at shared reference sections",
          ["Method","Wall-face width (mm)","Wall-face height (mm)","Recessed width (mm)"],data,[2.1,1.55,1.6,1.45],(1,2,3),10)
    doc.add_paragraph("The face width is measured at D = 0, 1.280 m above the floor. Face height is read on the reference centreline. The recessed column uses the median of five mid-height slices at D = 655–675 mm. A dash means that a complete face window was unavailable for that method.")
    doc.add_paragraph("The field sheet gives 2375 mm width and 1736 mm height. The tape contact depth is unknown. The primary height differed by +1.25 mm and the reveal-plane check by +2.56 mm. M04 supplied a negative control. All seven configurations returned zero windows across its four walls.")
    heading(doc,"What the scanner supports",new_page=True)
    figure(doc,art,"Figure 1   Amber lines are ScaleLSD detections and teal marks the primary face corners. Positive depth extends behind the interior wall.",width=6.0)
    prod=case["methods"]["profile"]["windows"][0];deep=prod["deep"]
    doc.add_paragraph(f'The pretrained detector retained {case["network"]["retained_lines"]} lines on M26 W01. With either automatic proposal source it could not associate one qualifying line to each of the four sides. Its author-provided indoor photo yielded {manifest["author_photo_control"]["retained_lines"]} qualifying lines with the same checkpoint and threshold. A strong line response alone does not establish a closed window.')
    doc.add_paragraph(f'The production recessed width is {fmt(deep["width_mm"])} mm. At the representative slice D = {deep["slice_center_mm"]:.0f} mm, the optional four-edge fit gives {fmt(deep["fitted_width_mm"])} mm width and {fmt(deep["fitted_height_mm"])} mm height. These two widths use different estimators. Each of the four sides contributed 24 supported strips in the single-slice check.')
    review=case["methods"]["profile_reveal"]["windows"][0]
    points=[[letter,", ".join(fmt(x,4) for x in p),", ".join(fmt(x,4) for x in q)]
            for letter,p,q in zip("ABCD",review["face_xyz_m"],deep["corners_xyz_m"],strict=True)]
    table(doc,"Table 2   Fitted corners in the original scanner coordinate system",
          ["Corner","Wall-face XYZ at D = 0 (m)","Recessed XYZ at D = 665 mm (m)"],points,[.8,2.8,2.9],(1,2),10)
    doc.add_paragraph("A–D run from bottom left through bottom right and top right to top left in the wall elevation. These points are intersections of fitted edges. The result files separately identify the sensor returns supporting each fit.")
    heading(doc,"Held-out corner accuracy",new_page=True)
    doc.add_paragraph("The holdout contains 24 windows and four negative walls. Four new seeds generated six window conditions each. Each matched window contributes the mean Euclidean error of its four corresponding 3D face corners. The table reports the median across matched windows. Misses and extra candidates are counted separately.")
    data=[]
    for m in METHODS:
        r=sel[m]
        data.append([LABEL[m],f'{r["tp"]}/24',r["fp"],fmt(r["median_corner_mm"]),
                     fmt(r["width_abs_median_mm"]),fmt(r["height_abs_median_mm"]),r["all_four_within_10mm"]])
    table(doc,"Table 3   Positional and dimensional performance on held-out scenes",
          ["Method","Matched","Extra","Corner (mm)","Width¹ (mm)","Height¹ (mm)","All four ≤10 mm²"],
          data,[2.05,.88,.58,.88,.84,.9,1.1],(1,2,3,4,5,6),9.6)
    doc.add_paragraph("¹ Median absolute dimensional error on the method’s matched windows, at the common reference height and centreline.  ² Count out of all 24 true windows. Ten millimetres is a descriptive threshold for this study.")
    doc.add_paragraph(f'On the {b["paired_n"]} common matches, the reveal check improved {b["paired_better"]} and tied {b["paired_tied"]}. The median paired change was {fmt(b["paired_median_change_mm"])} mm. Both methods put all four corners within 10 mm in {b["all_four_within_10mm"]} of 24 windows. The largest mean corner error for the reveal check was {fmt(b["max_case_mean_corner_mm"],1)} mm when a central obstruction split the window.')
    doc.add_paragraph("Both original-profile routes reported five extra candidates. Two came from window-shaped blind spots in solid walls. Fitting side planes refines an existing outline and inherits its detection failures. The layered approach also missed windows when the top or sill left occupied returns in all three main bands.")
    doc.add_paragraph(f'The primary depth search recovered 14 of 20 designed recessed widths on the holdout. A four-edge estimate was available in {a["depth_four_truth_matches"]} of the 16 windows with four observable recessed sides. Its median mean corner error was {fmt(a["deep_corner_median_mm"])} mm. All four partial-reveal cases withheld the deep corner quartet, and all four flush windows had no supported width layer.')
    heading(doc,"Methods and evidence",new_page=True)
    doc.add_paragraph("The two real rooms were evaluated on the original metre XYZ coordinates and their saved wall and floor planes. All eight walls were searched. M26 W01 was associated to the inventory using its frozen production outline. That outline supplies a matching box and common measurement sections. Only the synthetic scenes have independent corner truth.")
    data=[
        ["Production profile","Detect gaps in horizontal strips, confirm with vertical sections, fit jambs, sill and head, and intersect the four lines."],
        ["Layered projection","Use 20 mm horizontal cells, three height bands and three sub-bands. Combine sub-band occupancy by OR and main bands by AND. A supported gap in the height histogram classifies a candidate window."],
        ["Original-point lines","For each proposed side, find supported extreme returns in 24 strips and fit a robust line. Require at least 12 supported strips and sufficient length coverage on each side."],
        ["ScaleLSD","Project original face returns to a metric occupancy image with nominal 5 mm pixels. Run the official v2 checkpoint on a 512 × 512 grayscale raster. Associate its retained segments to four sides of each proposal and intersect them."],
        ["Reveal-plane check","From the original points 8–80 mm behind the face, fit one plane per proposed side. Balance observations across height or width and depth, reserve every fourth along-edge bin for verification, and cap the change at the face at 20 mm. A rejected side retains its primary profile edge."],
        ["Recessed four corners","At the representative 12 mm thick depth slice, fit four independent lines from original returns and intersect them. An unavailable top or sill withholds the four-corner result. The existing paired-jamb width has its own evidence status."]]
    table(doc,"Table 4   Operations performed by the comparator and the optional inspection check",["Route","Implementation"],data,[1.55,4.75],font_size=10)
    doc.add_paragraph("The pilot used 16 positive and four negative wall patches. The reveal-plane variant was added after that pilot. The held-out seeds 211, 307, 419 and 557 were evaluated with fixed settings in clean, skewed, partially obscured, cluttered, flush and tapered cases. Cases from one seed share a base size. They are controlled stress tests rather than independent construction projects.")
    heading(doc,"Literature and reproduction",new_page=True)
    def citation(title,body,refs):
        doc.add_heading(title,level=2)
        p=doc.add_paragraph(body+"  ")
        for i,(label,url) in enumerate(refs):
            if i:p.add_run("  ·  ")
            link(p,label,url)
    citation("Modular construction measurements, 2026","Chen, Li, Hong and Li use semantic segmentation and fit a minimum-area rectangle to a trimmed window boundary. That route needs segmented window points. Their study provides the course comparison for geometry and measurement definitions.",[("ISARC paper","https://doi.org/10.22260/ISARC2026/0180")])
    citation("Indoor opening detection, 2026","Lightweight geometry-guided automated 3D indoor reconstruction from point clouds describes layered occupancy and height-based opening classification. Our local implementation adapts §3.6 to the framework’s known wall planes and uses a dominant vertical gap. It omits the paper’s reconstruction and occlusion-inpainting stages.",[("International Journal of Digital Earth","https://doi.org/10.1080/17538947.2026.2741454")])
    citation("Learned line segments, 2025","Ke et al. introduce ScaleLSD for image line segments. We ran the authors’ v2 SA-1B weights and forward pass on a local GPU. The metric wall image and four-side association are local additions.",[("CVPR paper","https://openaccess.thecvf.com/content/CVPR2025/html/Ke_ScaleLSD_Scalable_Deep_Line_Segment_Detection_Streamlined_CVPR_2025_paper.html"),("Author code","https://github.com/ant-research/scalelsd"),("Weights","https://huggingface.co/cherubicxn/scalelsd")])
    citation("Incomplete indoor wireframes, 2024","Qin et al. project structural surfaces to fitted planes, extract boundary lines and regularize the resulting wireframe. It provides geometric context for requiring side support before intersecting lines. The complete Gestalt reconstruction was outside the executed comparisons.",[("Original paper","https://doi.org/10.1016/j.jag.2024.103893")])
    doc.add_heading("Reproduce the result",level=2)
    doc.add_paragraph("Enable Include window corner cross-check on the local upload page, or add --window-review to the inspection command. The optional geometry check runs on the CPU. The source includes the seven-method study runner, fixed seeds, model fingerprints, original row evidence and a saved-report renderer. Future field verification requires surveyed A–D coordinates, specified tape depth, and additional rooms with confirmed windows and blind spots.")
    doc.save(out)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("study","raw","out"):p.add_argument("--"+arg,type=Path,required=True)
    args=p.parse_args()
    report(args.study,args.raw,args.out)
