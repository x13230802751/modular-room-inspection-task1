"""Generate the English Word report from audited measurements and the vertical-panel control."""
import argparse
import csv
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

PROTOCOL=json.loads(Path(__file__).with_name("protocol.json").read_bytes())
METHODS=PROTOCOL["methods"]
REPORT="Room_Filter_Comparison_with_P2P_Bridge"


def records(folder,name):
    with (folder/(name+".csv")).open(encoding="utf8",newline="") as f:
        return list(csv.DictReader(f))


def num(x,d=2,sign=False):
    return "N/A" if x in (None,"") else format(float(x),("+" if sign else "")+f".{d}f")


def section_plot(profiles, windows, path):
    fig,ax=plt.subplots(figsize=(7.2,2.4))
    for m,color in (("raw","#35495E"),("p2p","#BB5834")):
        subset=[r for r in profiles if r["method"]==m and r["room"]=="M26"]
        if not subset:
            continue
        last=max(int(r["depth_mm"]) for r in subset)
        y=np.full(last//5+1,np.nan)
        for r in subset:
            if r["mid_height_width_mm"]:
                y[int(r["depth_mm"])//5]=float(r["mid_height_width_mm"])
        ax.plot(np.arange(len(y))*5,y,".-",c=color,ms=2.0,lw=1,label=METHODS[m])
        w=windows[m]
        if w["deep_width_mm"]:
            ax.scatter([.5*(float(w["first_slice_mm"])+float(w["last_slice_mm"]))],[float(w["deep_width_mm"])],
                       marker="D",facecolor="white",edgecolor=color,s=29,zorder=5)
        if w["face_width_mm"]:
            ax.scatter([0],[float(w["face_width_mm"])],s=22,facecolor=color,edgecolor="white",lw=.5,zorder=5)
    ax.axhline(2375,color="#5A6C65",ls="--",lw=.9,label="Tape reading, depth unspecified")
    ax.set_ylabel("Window width (mm)",size=9);ax.set_xlabel("Depth into the recess from the interior wall face (mm)",size=9)
    ax.set_axisbelow(True);ax.grid(axis="y",color="#DCE4E4",lw=.7);ax.spines[["top","right"]].set_visible(False)
    ax.legend(frameon=False,loc="lower center",bbox_to_anchor=(.5,-.55),ncol=3,fontsize=8)
    ax.tick_params(labelsize=8,length=2);fig.subplots_adjust(left=.1,right=.99,bottom=.34,top=.96)
    fig.savefig(path,dpi=190,bbox_inches="tight",pad_inches=.05);plt.close(fig)


def wall_plot(walls,path):
    colors=["#52667A","#12806F","#BD5B31"]
    fig,axes=plt.subplots(1,2,figsize=(7.2,2.5))
    for ax,room in zip(axes,("M26","M04")):
        x=np.arange(4)
        for k,(m,field,tag) in enumerate((("raw","native_rms_mm","Original scan"),("p2p","native_rms_mm","P2P run XYZ"),("p2p","raw_replay_mm","P2P rows at original XYZ"))):
            y=[float(walls[room,m,f"W{i:02d}"][field]) if walls[room,m,f"W{i:02d}"].get(field) else np.nan for i in range(1,5)]
            ax.bar(x+(k-1)*.235,y,.215,color=colors[k],label=tag)
        ax.set_title(room,loc="left",fontsize=11,weight="bold")
        ax.set_xticks(x,["W01","W02","W03","W04"]);ax.spines[["top","right"]].set_visible(False)
        ax.set_axisbelow(True);ax.grid(axis="y",lw=.65,color="#DFE6E6");ax.tick_params(length=0,labelsize=8)
    maximum=max([float(r[k]) for r in walls.values() for k in ("native_rms_mm","raw_replay_mm") if r["method"] in ("raw","p2p") and r.get(k)])
    for ax in axes: ax.set_ylim(0,maximum*1.12)
    axes[0].set_ylabel("Whole-wall RMS (mm)",size=8)
    fig.legend(*axes[0].get_legend_handles_labels(),loc="lower center",ncol=3,frameon=False,fontsize=8)
    fig.subplots_adjust(left=.095,right=.99,bottom=.24,top=.88,wspace=.25)
    fig.savefig(path,dpi=190,bbox_inches="tight",pad_inches=.04);plt.close(fig)


def build(repo,evidence,out):
    sys.path.insert(0,str(repo))
    from report_style import document,figure,heading,link,table
    out.mkdir(exist_ok=True,parents=True)
    plots=out/"figures";plots.mkdir(exist_ok=True)
    sums={r["method"]:r for r in records(evidence,"method_summary")}
    dims={(r["room"],r["method"],r["feature"]):r for r in records(evidence,"dimensions")}
    windows={r["method"]:r for r in records(evidence,"windows")}
    walls={(r["room"],r["method"],r["baseline_wall"]):r for r in records(evidence,"wall_rms")}
    cases={(r["room"],r["method"]):r for r in records(evidence,"cases")}
    profiles=records(evidence,"window_profile")
    controls={r["method"]:r for r in records(evidence,"panel_control")}
    audits=json.loads((evidence/"native_audit.json").read_bytes())["cases"]
    patch_check=json.loads((evidence/"patch_audit.json").read_bytes())
    assert patch_check["exact_ema_tensor_equality"]
    assert len(audits)==2*len(METHODS) and all(a["result"]=="passed" and a["exact_native_membership"] for a in audits)
    checks=records(evidence,"baseline_check");assert len(checks)==8 and all(abs(float(r["difference_mm"]))<1e-8 for r in checks)
    section_plot(profiles,windows,plots/"M26_window_sections.png")
    wall_plot(walls,plots/"wall_coordinate_comparison.png")
    doc=document("Room Filter Comparison with P2P Bridge")
    doc.core_properties.subject="CIVL 7023 Project 1 Task 1 | M26 and M04"
    def tab(title,cols,rows,widths,nd,size=9.6):
        t=table(doc,title,cols,rows,widths,nd,font_size=size)
        for i,r in enumerate(t.rows):
            color="E0EAEB" if i==0 else ("E8F1EE" if r.cells[0].text=="P2P-Bridge" else ("F4F6F6" if i%2==0 else None))
            if color:
                for c in r.cells:
                    shade=OxmlElement("w:shd");shade.set(qn("w:fill"),color);c._tc.get_or_add_tcPr().append(shade)
        return t
    def para(s):
        p=doc.add_paragraph(s);p.paragraph_format.space_before=Pt(3);return p
    def sources(p,pairs):
        for i,(title,url) in enumerate(pairs):
            p.add_run("  " if i==0 else " | ");link(p,title,url)
    def dim(room,m,f,key="value_mm"):
        return dims[room,m,f][key]
    def val(m,key):
        return sums[m][key]
    def err(m,key):
        return num(val(m,key))

    doc.add_paragraph("Room Filter Comparison with P2P Bridge","Title")
    heading(doc,"Door and window errors across ten input treatments")
    p=doc.add_paragraph()
    p.add_run("Retain original sensor coordinates for the Task 1 inspection report. ").bold=True
    p.add_run(f"Across five door and window tape comparisons, the mean absolute error (MAE) was "
              f"{err('raw','opening_excluding_window_width_mae_mm')} mm on the original scan, "
              f"{err('radius','opening_excluding_window_width_mae_mm')} mm with the radius mask and "
              f"{err('p2p','opening_excluding_window_width_mae_mm')} mm after P2P-Bridge. "
              "The window width is evaluated separately because its tape depth is unknown.")
    para("M26 and M04 contain 1,303,583 original points in total. The same native pipeline processed each treatment. "
         "Wall-plane and opening-centre matching paired physical features across runs. Counts in Table 1 show how many comparisons were available.")
    rows=[[name,err(m,"room_mae_mm"),err(m,"opening_excluding_window_width_mae_mm"),err(m,"opening_mae_mm"),
           val(m,"opening_excluding_window_width_n"),f"{val(m,'walls_matched')} / {val(m,'openings_matched')}"] for m,name in METHODS.items()]
    tab("Table 1  Absolute differences from course references and feature coverage",["Input treatment","Room MAE\n(mm)","Opening MAE\n5 items (mm)","Face MAE\n6 items (mm)","5-item\ncount","Walls /\nopenings"],
        rows,[1.66,.94,1.22,1.1,.65,.83],(1,2,3,4,5))
    para("Room MAE covers length, width and height in both rooms. The five opening items are two door widths, two door heights and the M26 window height. "
         "The six-item score adds the fitted window-face width against the 2,375 mm tape entry. It mixes a known face section with an unlocated field measurement.")
    para(f"The radius mask removed {int(val('radius','removed')):,} low-support points while preserving every retained coordinate. The learned model predicted "
         f"positions for all {sum(int(cases[r,'p2p']['retained_rows']) for r in ('M26','M04')):,} input rows. All ten conditions found both doors, the window and the eight wall planes. "
         "The larger dimensional errors after P2P-Bridge arise downstream of finding the correct openings. These two rooms do not establish how the ranking transfers to other scans.")

    heading(doc,"Individual door and window errors",new_page=True)
    fields=(("M26","door_width"),("M26","door_height"),("M04","door_width"),("M04","door_height"),("M26","window_height"))
    para("Door widths are measured on a horizontal section 1.00 m above the fitted floor. Opening heights are measured on the centreline. "
         "Signed differences below equal the point-cloud reading minus the manual reading. A positive difference indicates a larger point-cloud estimate.")
    rows=[["Tape reading",*[num(dim(r,"raw",f,"reference_mm"),0) for r,f in fields]]]
    rows += [[name,*[num(dim(r,m,f,"signed_difference_mm"),2,True) for r,f in fields]] for m,name in METHODS.items()]
    tab("Table 2  Tape dimensions and signed point-cloud differences in mm",["Input treatment","M26 door\nwidth","M26 door\nheight","M04 door\nwidth","M04 door\nheight","M26 window\nheight"],
        rows,[1.62,1,1,1,1,1.1],(1,2,3,4,5))
    rows=[[name,*[num(dim(r,m,f)) for r,f in fields]] for m,name in METHODS.items() if m in ("raw","radius","p2p")]
    tab("Table 3  Direct measurements for the three primary treatments in mm",["Input treatment","M26 door\nwidth","M26 door\nheight","M04 door\nwidth","M04 door\nheight","M26 window\nheight"],
        rows,[1.62,1,1,1,1,1.1],(1,2,3,4,5))
    comparable=[(r,f) for r,f in fields if dim(r,"p2p",f) and dim(r,"raw",f)]
    improved=sum(abs(float(dim(r,"p2p",f,"signed_difference_mm")))<abs(float(dim(r,"raw",f,"signed_difference_mm"))) for r,f in comparable)
    para(f"P2P-Bridge moved {improved} of {len(comparable)} comparable dimensions closer to the tape reading than the original scan. "
         f"M26 W02 door width changed from {num(dim('M26','raw','door_width'))} to {num(dim('M26','p2p','door_width'))} mm against 900 mm. "
         f"On M04, the learned estimate of {num(dim('M04','p2p','door_width'))} mm was closer to 918 mm, while the door-height error grew. "
         "Per-feature records also contain fitted wall identifiers and section heights.")

    heading(doc,"The M26 window at two physical locations",new_page=True)
    para("D is positive into the recess from the interior face of W01. In each run, the face width comes from fitted edges at D = 0 and the recessed "
         "candidate comes from supported depth slices at the same mid-window elevation. Each signed difference uses the 2,375 mm tape value as context.")
    rows=[]
    for m,name in METHODS.items():
        w=windows[m]
        depth=f'{w["first_slice_mm"]}–{w["last_slice_mm"]}' if w["first_slice_mm"] else "N/A"
        rows.append([name,num(w["face_height_m"],3),num(w["face_width_mm"]),
                     num(float(w["face_width_mm"])-2375,2,True) if w["face_width_mm"] else "N/A",depth,
                     num(w["deep_width_mm"]),num(float(w["deep_width_mm"])-2375,2,True) if w["deep_width_mm"] else "N/A"])
    tab("Table 4  Wall opening and recessed frame candidate on M26 W01",["Input treatment","Height\n(m)","Face width\n(mm)","Face Δ\n(mm)","Deep slice\nD (mm)","Deep width\n(mm)","Deep Δ\n(mm)"],
        rows,[1.55,.7,.94,.81,1.0,1.0,.82],(1,2,3,4,5,6),9.0)
    figure(doc,plots/"M26_window_sections.png","Figure 1  Mid-height slice widths. Filled circles show face fits and diamonds show recessed candidate medians.",width=5.95)
    para("The field notes omit both tape contacts and depth. A closer numerical match at the recess does not establish which physical frame the operator measured. "
         f"All ten methods independently selected the same 655–675 mm interval. P2P-Bridge changed its reported width from {num(windows['raw']['deep_width_mm'])} "
         f"to {num(windows['p2p']['deep_width_mm'])} mm. Gaps in the profile indicate missing paired edges.")

    heading(doc,"Whole-wall flatness and coordinate replay",new_page=True)
    para("The native algorithm fits an orthogonal least-squares plane to the wall support inside its structural boundary with detected openings excluded. "
         "The processed reading uses the current XYZ. Replay refits the same selected sensor row IDs at their original XYZ. Both results are in millimetres.")
    rows=[]
    for m,name in METHODS.items():
        a,b=walls["M26",m,"W03"],walls["M04",m,"W01"]
        rows.append([name,num(a.get("native_rms_mm"),3),num(a.get("raw_replay_mm"),3),num(b.get("native_rms_mm"),3),
                     num(b.get("raw_replay_mm"),3),num(val(m,"median_fixed_change_mm"),3,True)])
    tab("Table 5  Whole-wall RMS for the two walls with course manual references",["Input treatment","M26 W03\nrun XYZ","M26 W03\nraw replay","M04 W01\nrun XYZ","M04 W01\nraw replay","Fixed rows\nmedian Δ"],
        rows,[1.6,1,1,1,1,.9],(1,2,3,4,5))
    para("The final column holds the original detection's wall support fixed, keeps rows surviving the treatment and reports the median processed-minus-original RMS change "
         "over available walls. Matching a wall across runs alone does not make the selected points identical.")
    a,b=walls["M26","p2p","W03"],walls["M04","p2p","W01"]
    para(f"P2P-Bridge gave {num(a.get('native_rms_mm'),3)} mm on M26 W03 and {num(b.get('native_rms_mm'),3)} mm on M04 W01. The manual field readings are 1.0 and "
         "1.8 mm. The manual measurement footprints were not surveyed. Closeness to either value cannot establish whole-wall accuracy.")
    para("Structural-corner extrapolation is flagged in the per-wall evidence wherever the native algorithm inferred part of the boundary. The replay and original point counts "
         "support inspection of these cases. For P2P-Bridge this flag applies to M26 W02 and M04 W01, W02 and W04.")

    heading(doc,"All eight wall surfaces",new_page=True)
    keys=[(r,f"W{i:02d}") for r in ("M26","M04") for i in range(1,5)]
    rows=[[name,*[num(walls[r,m,w].get("native_rms_mm"),3) for r,w in keys]] for m,name in METHODS.items()]
    tab("Table 6  Native whole-wall RMS on the run coordinates in mm",["Input treatment",*[r+"\n"+w for r,w in keys]],
        rows,[1.48]+[.68]*8,tuple(range(1,9)),9.1)
    figure(doc,plots/"wall_coordinate_comparison.png","Figure 2  Original wall RMS, P2P-Bridge wall RMS and original-coordinate replay of the P2P selections.",width=6.0)
    para("Wall identifiers refer to the physical wall in the original scan. Each row in wall_rms.csv also records the fraction of shared selections, "
         "the fitted plane-offset difference, the fixed-support RMS pair and the original sensor-row digest. N/A indicates an unavailable measurement.")
    para(f"The P2P-Bridge scan gave higher native RMS on all eight walls. On the original support held fixed, the median RMS change was "
         f"{num(val('p2p','median_fixed_change_mm'),3,True)} mm. The combination of this measurement and the same-row replay in Table 5 distinguishes "
         "coordinate movement from a change in wall membership.")

    heading(doc,"A vertical panel with known surface relief",new_page=True)
    para("A wall sampled at 10 mm intervals has sinusoidal relief of 3 mm amplitude and 60 mm wavelength along its width. Gaussian noise with standard deviation "
         "0.7 mm acts along the wall-normal Y axis. The same 36 isolated returns and noise realization (seed 7023) were supplied to every filter. "
         "Flatness and coordinate error were evaluated on the same 5,329 interior surface samples.")
    rows=[[name,num(controls[m]["surface_y_rmse_mm"],3),num(controls[m]["measured_rms_mm"],3),num(controls[m]["flatness_bias_mm"],3,True),
           controls[m]["isolated_rows_retained"]] for m,name in METHODS.items()]
    tab("Table 7  Residual error and preservation of known wall relief",["Input treatment","Surface error\nRMSE (mm)","Measured wall\nRMS (mm)","RMS minus\ntruth (mm)","Isolated rows\nretained"],
        rows,[1.6,1.25,1.25,1.05,1.08],(1,2,3,4))
    raw,learn=controls["raw"],controls["p2p"]
    para(f"The clean panel has a true plane RMS of {num(raw['true_rms_mm'],3)} mm. The original noisy panel gives {num(raw['measured_rms_mm'],3)} mm and "
         f"P2P-Bridge gives {num(learn['measured_rms_mm'],3)} mm. The surface-error column measures the Y error to the analytic surface at the predicted X coordinate. "
         "A smoother plane-fit result can coexist with biased physical relief.")
    para("This controlled result measures one surface, spatial frequency, noise level and orientation. It provides a known flatness target while the two real rooms supply the separate tape and whole-wall comparisons.")

    heading(doc,"Inference settings and reproducibility",new_page=True)
    para("The released ScanNet++ XYZ checkpoint at training step 100,000 supplied 403 exponential-moving-average tensors. Strict loading covered every backbone tensor. "
         "The 118,641,731-parameter model ran on an NVIDIA GeForce RTX 5060 Laptop GPU with PyTorch 2.8.0 and CUDA 12.8. Each normalized 4,096-point patch used five bridge steps, "
         "a 0.30 m neighbourhood, mean centring and unit maximum radius. Coordinates were transformed back to metres before stitching.")
    p=para("We ran the authors' network and sampler. The Windows launcher compiled their forward CUDA kernel bodies with NVRTC and checked each operator. "
           "The room adapter includes every batch entry, uses seeded farthest-point patch selection, averages predictions by input row and adds local patches for uncovered points. "
           "These choices allow original-coordinate replay.")
    sources(p,[("ECCV paper","https://www.ecva.net/papers/eccv_2024/papers_ECCV/html/203_ECCV_2024_paper.php"),
               ("Author source",PROTOCOL["model_repository"]+"/tree/"+PROTOCOL["model_commit"]),("Released model",PROTOCOL["official_weight_folder"])])
    first_file=evidence/"patch_first_check.json"
    first=json.loads(first_file.read_bytes()) if first_file.exists() else None
    audit_text=(f"An initial patch comparison had a maximum vector difference of {num(first['max_vector_difference_mm'],3)} mm, "
                f"above the predeclared {num(first['tolerance_mm'],3)} mm target. " if first else "")
    para(audit_text+f"On the same two M04 patches, three repeat evaluations per path gave a maximum adapter-to-author difference of "
         f"{num(patch_check['max_vector_difference_mm'],4)} mm. Repeating the author's path alone gave up to "
         f"{num(patch_check['worst_within_author_mm'],4)} mm. Corresponding EMA tensors matched exactly.")
    rows=[]
    for r in ("M26","M04"):
        c=cases[r,"p2p"]
        rows.append([r,f"{int(c['retained_rows']):,}",c["initial_patches"],c["supplementary_patches"],c["uncovered_after_initial"],
                     num(c["median_move_mm"]),num(c["p95_move_mm"])])
    tab("Table 8  Complete-room inference coverage and movement from the original coordinates",["Room","Sensor rows\npredicted","Initial\npatches","Extra\npatches","Initially\nuncovered","Median shift\n(mm)","P95 shift\n(mm)"],
        rows,[.62,1.2,.85,.8,1,.95,.95],(1,2,3,4,5,6),9.1)
    para("The radius mask requires four other neighbours within 20 mm. The statistical mask uses the mean distance to 16 neighbours with a cutoff of the population mean plus two "
         "standard deviations. Gaussian and classical bilateral filters use up to 24 neighbours within 25 mm, spatial bandwidth 12 mm and, for bilateral smoothing, normal-distance bandwidth 2 mm. "
         "The two cylinder radii are 12 and 20 mm with a 30 mm PCA support and one projection pass. Combined methods apply the named mask first.")
    p=para("Classical and cylindrical runs were reused after validating the input, row-map and method fingerprints. All ten conditions were analysed together against the same manual records. "
           f"The native verification independently repeated wall selections and residuals in {len(audits)} room–method runs. The evaluation is separate from the production framework.")
    sources(p,[("Framework",PROTOCOL["repository"]+"/tree/"+PROTOCOL["commit"]),("PCL radius filter","https://pointclouds.org/documentation/tutorials/remove_outliers.html"),
               ("Bilateral filter","https://doi.org/10.5201/ipol.2017.179"),("Cylindrical filter","https://doi.org/10.3390/rs18122035")])
    doc.save(out/(REPORT+".docx"))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("repo","evidence","out"):p.add_argument("--"+name,required=True,type=Path)
    a=p.parse_args();build(a.repo.resolve(),a.evidence.resolve(),a.out.resolve())
