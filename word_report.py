"""Export a reusable English single-room inspection report."""
from pathlib import Path
from course_reference import matched_reference
from preprocessing import description
from report_style import document, figure, heading, table
import group09_report as paired

FLOW = Path(__file__).parent / "assets" / "measurement_workflow.png"


def fmt(x, digits=2):
    return "—" if x is None else f"{x:.{digits}f}"


def write_word_report(output, data, sections):
    doc = document("Room point cloud inspection")
    cloud, walls = data["cloud"], data["walls"]
    ref = data["manual_reference"] if "manual_reference" in data else matched_reference(data)
    doc.add_paragraph("Room point cloud inspection", "Title")
    doc.add_paragraph(f'{cloud["file"]} contains {cloud["point_count"]:,} input points. The {data["algorithms"]["name"]} profile reported {len(walls)} walls.')
    doc.add_paragraph(description(data.get("preprocessing")))
    group=data.get("group09_result")
    if group:
        doc.add_paragraph(paired.INTRO)
    heading(doc,"1  Official raw dimensions and wall RMS" if group else "1  Dimensions and surface flatness")
    room=data["room"]
    if room:
        rows=[]
        for key in ("length","width","height"):
            value=room[key+"_mm"]; manual=ref["dimensions_mm"][key] if ref else None
            rows.append([key.capitalize(),fmt(value),fmt(manual),fmt(value-manual) if manual is not None else "—"])
        table(doc,"Table 1  Interior room dimensions (mm)",["Dimension","Scan","Manual","Scan − manual"],rows,[3,2,2,2.5],(1,2,3))
    else:
        doc.add_paragraph("A supported floor-to-ceiling enclosure was unavailable.")
    ops=[o for w in walls for o in w["openings"]]
    if ops:
        rows=[]
        for o in ops:
            manual=ref["openings_mm"].get(o["type"]) if ref and sum(a["type"]==o["type"] for a in ops)==1 else None
            rows.append([o["id"],o["type"].capitalize(),fmt(o["width_at_height_m"],3),fmt(o["width_mm"]),fmt(o["height_mm"]),
                         f'{manual["width"]} × {manual["height"]}' if manual else "—"])
        table(doc,"Table 2  Wall-face openings",["ID","Type","Width level (m)","Width (mm)","Height (mm)","Manual W × H (mm)"],
              rows,[1.35,1.1,1.35,1.35,1.35,1.9],(2,3,4,5))
        doc.add_paragraph("Width is projected along the local wall axis at the listed elevation above the floor. Height is taken at the centreline. The default detector fits the visible edges within 8 mm of the wall plane.")
    else:
        doc.add_paragraph("The detector found no openings with sufficient edge support.")
    table(doc,"Table 3  Whole-wall RMS",
          ["Wall","Whole RMS (mm)","Points used in RMS"],
          [[w["id"],fmt(w["whole"].get("rms_mm"),3),w["whole"].get("n_selected","—")] for w in walls],
          [1.5,3,3],(1,2))
    if data.get('recovery')=='none':
        doc.add_paragraph('The wall detector assigns support points from the selected input. The structural corners and detected opening footprints define the region supplied to the RMS algorithm.')
    if ref:
        r=ref["rms"]
        doc.add_paragraph(f'Manual RMS is {r["value_mm"]:.1f} mm. {r["wall_description"]}. The measured footprint in the photograph or field notes has no recorded corner coordinates.')
    for warning in data["warnings"]: doc.add_paragraph(warning)
    if sections.get("availability")=="not_recorded":
        doc.add_paragraph("This saved inspection predates the separate window-depth record.")
    if sections["windows"]:
        heading(doc,"2  Window measurement positions",new_page=True)
        for w in sections["windows"]:
            a,b=w["face"],w["deep"]
            doc.add_heading(w["opening_id"],level=2)
            doc.add_paragraph("Depth D starts at the fitted interior wall face and increases into the opening. The face endpoints are intersections on the fitted plane. The recessed search tests paired original edge returns in 12 mm thick depth slices.")
            rng=b["depth_range_mm"]
            rows=[["Width (mm)",fmt(a["width_mm"],3),fmt(b["width_mm"])],
                  ["Depth D (mm)","0",f"{rng[0]}–{rng[1]}" if rng else "—"],
                  ["Height above floor (m)",fmt(a["height_m"],4),fmt(b["height_m"],4)],
                  ["Evidence","Fitted jambs",b["status"].replace("_"," ")]]
            table(doc,"Window width by physical section",["Measurement","Wall-face aperture","Recessed frame candidate"],rows,[2.2,2,2.3],(1,2))
            for side,xyz in zip(("Left","Right"),a["endpoints_xyz_m"]):
                doc.add_paragraph(f'{side} fitted wall-face endpoint (XYZ in m)  '+", ".join(fmt(x,4) for x in xyz))
            if b["representative"]:
                example=b["representative"]; left,right=example["endpoints"]
                doc.add_paragraph(f'At D = {example["slice_center_depth_mm"]} mm, original rows {left["original_index"]} and {right["original_index"]} span {example["width_mm"]:.2f} mm in projection. The primary recessed width is the median of five mid-height widths. The separate median across supported height strips and depths is {b["strip_median_width_mm"]:.2f} mm.')
            m=ref["openings_mm"].get("window",{}).get("width") if ref and len(sections["windows"])==1 else None
            if m is not None:
                extra=f' and {b["width_mm"]-m:+.2f} mm at the recessed candidate' if b["width_mm"] is not None else ""
                doc.add_paragraph(f'The manual width of {m} mm gives {a["width_mm"]-m:+.3f} mm at the wall face{extra}. The tape depth and contact points were not recorded.')
    if group:
        heading(doc,paired.TITLE,new_page=bool(group["pairs"]))
        doc.add_paragraph(paired.status_text(group))
        for i,(label,message,widths,levels,corners,evidence) in enumerate(paired.comparisons(data,sections,group)):
            if i:
                heading(doc,paired.TITLE,new_page=True)
            doc.add_heading(label,level=2)
            doc.add_paragraph(message+" Depth D is zero at each fitted interior wall face and increases into the opening.")
            table(doc,"Window widths by physical position",paired.WIDTH_COLUMNS,widths,[1.15,1.6,1.9,1.55],(1,2,3))
            table(doc,"Measurement elevations above the floor and face height",paired.LEVEL_COLUMNS,levels,[1.15,1.6,1.6,1.85],(1,2,3))
            table(doc,"Fitted four corners in original scan coordinates",paired.CORNER_COLUMNS,corners,[.65,1.85,1.85,1.85],font_size=10)
            for line in evidence:
                doc.add_paragraph(line)
    review=data.get("window_corner_review")
    if review:
        from window_review_display import COLUMNS, XYZ_COLUMNS, EXPLANATION, tables
        if not review["windows"]:
            doc.add_paragraph("Optional window corner cross-check requested. No window was detected.")
        for item in review["windows"]:
            heading(doc,"Window corner cross-check",new_page=True)
            doc.add_heading(item["opening_id"],level=2)
            if item["status"]!="evaluated":
                doc.add_paragraph("The wall boundary was unavailable for this check.")
                continue
            doc.add_paragraph(EXPLANATION)
            rows,points=tables(item)
            table(doc,"Cross-check measurements",COLUMNS,rows,[2.1,2,2.4],(1,2))
            table(doc,"Fitted corners in the original coordinate system",XYZ_COLUMNS,points,[.8,2.85,2.85],(1,2),10.5)
            doc.add_paragraph("The summary records source rows for each supported fit. The primary opening dimensions and whole-wall RMS use the measurement profile selected for this scan.")
    for i,w in enumerate(walls,1):
        heading(doc,f'{w["id"]}  Wall elevation and original-point support',new_page=True)
        figure(doc,output/w["elevation_file"],f'Figure {i}  {w["id"]} in wall-local coordinates.',width=5.4)
        doc.add_paragraph("The navy outline joins structural corners A–D. Orange and teal mark doors and windows. A red circle marks a corner farther than 50 mm from its nearest observed wall point.")
        if w["structural_corners"]:
            table(doc,"Structural corners and nearest assigned wall samples",["Corner","X (m)","Y (m)","Z (m)","Gap (mm)","Original row"],
                  [[key,*[fmt(t,3) for t in c["xyz_m"]],fmt(c["nearest_distance_mm"],1),c["nearest_wall_point_index"]] for key,c in zip("ABCD",w["structural_corners"])],
                  [1.2,1.25,1.25,1.25,1.5,1.6],(1,2,3,4,5))
        if w["openings"]:
            locations=[]
            for o in w["openings"]:
                for name,point in zip(("Centre","A","B","C","D"),[o["center_xyz_m"],*o["corners_xyz_m"]]):
                    locations.append([o["id"],name,*(fmt(t,4) for t in point)])
            table(doc,"Fitted opening centres and corners in scan coordinates",["Opening","Point","X (m)","Y (m)","Z (m)"],locations,[1.6,1.3,1.7,1.7,1.7],(2,3,4))
        footprints=[]
        for scope in ("whole",):
            roi=w[scope]
            coverage=roi.get("coverage_fraction")
            footprints.append([scope.capitalize(),fmt(roi.get("rms_mm"),3),fmt(roi.get("p95_abs_mm"),3),
                               "—" if coverage is None else f"{coverage:.1%}",roi["status"]])
        table(doc,"Flatness and observed coverage for this wall",["Region","RMS (mm)","Abs. P95 (mm)","Coverage","Status"],
              footprints,[1.3,1.5,1.9,1.6,1.7],(1,2,3))
        for key in ("whole",):
            item=w[key]
            if item.get("reason"): doc.add_paragraph(key.capitalize()+" footprint. "+item["reason"])
            elif item.get("warnings"): doc.add_paragraph(key.capitalize()+" footprint flags include "+", ".join(item["warnings"])+".")
    heading(doc,"Methods and reproduction",new_page=True)
    workflow_caption = ("Inputs to whole-wall RMS and the independent Group 09 window review."
                        if group else "From a room scan to traceable measurements.")
    figure(doc,FLOW.with_name("group09_workflow.png") if group else FLOW,
           f'Figure {len(walls)+1}  {workflow_caption}',width=6.4 if group else 6.0)
    if group:
        doc.add_paragraph("The RMS provider receives the assigned wall points outside detected openings and the four structural corners. If the enclosure or ceiling cannot support these corners, the report records the reason and preserves the available opening measurements.")
    table(doc,"Algorithm entry points used for this scan",["Stage","Callable"],
          [[stage,details["call"]] for stage,details in data["algorithms"]["stages"].items()],[1.8,6.4])
    if data.get("reporting"):
        doc.add_paragraph("Report writer  "+data["reporting"]["writer"]["call"])
    doc.add_paragraph("The output folder contains opening dimensions, the four wall corners, source indices, window depth sections and signed RMS residuals. The JSON manifest records fitted planes, footprint coverage and the algorithm source fingerprints.")
    doc.add_paragraph("Input SHA-256"); doc.add_paragraph(cloud["sha256"])
    if group:
        benchmark=group["benchmark"]
        heading(doc,paired.BENCH_TITLE,new_page=True)
        doc.add_paragraph(paired.BENCH_NOTE)
        table(doc,"Nominal thresholds and earned points",["Domain","Benchmark evidence","Points / 25"],
              paired.benchmark_table(benchmark),[1.5,3.95,1.15],(2,))
        doc.add_paragraph(f'Group 09 earned {benchmark["nominal_score"]:.1f} out of 100 at the nominal tolerances.')
        doc.add_paragraph(paired.BENCH_DETAIL)
        table(doc,"Sensitivity to inspection tolerances",paired.SENS_COLUMNS,paired.sensitivity_table(benchmark),
              [1.05,2.6,1.5,1.05],(1,2,3))
        doc.add_paragraph("The benchmark uses research thresholds. A scan without comparable ground truth receives measurements and support evidence. The benchmark score belongs to the historical comparison.")
    doc.save(output/data["word_report"])
