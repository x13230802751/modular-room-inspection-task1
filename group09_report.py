"""Validate a saved paired result and prepare the same comparison tables for Word and HTML."""
from hashlib import sha256
import json
from pathlib import Path
import re

from preprocessing import MAP_FILE, validate_row_map

TITLE="Group 09 window corner review"
INTRO="Official room dimensions, opening dimensions and wall RMS use the original scan. Group 09 independently redetects walls and windows on radius-selected points and fits the four window sides."


def load_review(root, summary):
    descriptor=summary.get("group09_review")
    if descriptor is None:
        return None,[]
    if descriptor.get("file")!="group09/result.json" or descriptor.get("version")!=1 or descriptor.get("combination")!=9:
        raise ValueError("Unsupported Group 09 result descriptor.")
    directory=root/"group09"
    path=directory/"result.json"
    if directory.resolve().parent!=root.resolve() or path.resolve().parent!=directory.resolve():
        raise ValueError("Invalid Group 09 result location.")
    raw=path.read_bytes()
    record=json.loads(raw)
    if (sha256(raw).hexdigest()!=descriptor["sha256"] or record.get("version")!=1 or record.get("combination")!=9
            or descriptor["cloud_sha256"]!=summary["cloud"]["sha256"] or record["cloud_sha256"]!=descriptor["cloud_sha256"]
            or summary["preprocessing"]["method"]!="raw" or record["raw_selection_sha256"]!=summary["preprocessing"]["source_rows_sha256"]
            or record["status"]!=descriptor["status"] or record["status"] not in ("complete","limited","unavailable")):
        raise ValueError("The Group 09 record does not match the official raw inspection.")
    files=[path]
    treatment=record["preprocessing"]
    if treatment is not None:
        if (treatment["method"]!="radius" or treatment["parameters"]!={"radius_mm":20,"min_other_points":4}
                or treatment["input_rows"]!=summary["cloud"]["point_count"]):
            raise ValueError("Unexpected Group 09 point selection.")
        validate_row_map(directory,treatment)
        if treatment["source_rows_file"]:
            files.append(directory/MAP_FILE)
    elif record["status"]!="unavailable":
        raise ValueError("A completed Group 09 review requires a radius selection.")
    for window in record["windows"]:
        if window["status"]!="evaluated":
            continue
        if not all(re.fullmatch("[A-Za-z0-9_-]+",window[k]) for k in ("wall_id","id")):
            raise ValueError("Invalid Group 09 window identifier.")
        expected=Path("walls")/window["wall_id"]/(window["id"]+"_depth_profile.csv")
        profile=directory/expected
        if (expected.as_posix()!=window["profile_file"] or not profile.resolve().is_relative_to(directory.resolve())
                or sha256(profile.read_bytes()).hexdigest()!=window["profile_sha256"]):
            raise ValueError("The Group 09 depth profile does not match its recorded digest.")
        files.append(profile)
    return record,files


def fmt(value, places=2):
    return "—" if value is None else f"{value:.{places}f}"


def xyz(point):
    return "—" if point is None else ", ".join(f"{c:.4f}" for c in point)


def depth_band(section):
    interval=section.get("depth_range_mm")
    return "—" if not interval else f"{interval[0]}–{interval[1]}"


def status_text(record):
    t=record["preprocessing"]
    selection=(f'Group 09 retained {t["retained_rows"]:,} of {t["finite_rows"]:,} finite points. '
               if t else "")
    rule="Each retained point has at least four other points within 20 mm. "
    if record["status"]=="unavailable":
        return selection+rule+"The secondary measurement was unavailable. "+record["reason"]
    if record["status"]=="limited":
        return selection+rule+"The radius branch has incomplete wall boundaries. "+" ".join(record["warnings"])
    if not record["pairs"]:
        return selection+rule+"Neither branch detected a window."
    return selection+rule+"Window pairs are associated by their locations in the original scan."


def comparisons(summary, sections, record):
    raw={o["id"]:o for w in summary["walls"] for o in w["openings"] if o["type"]=="window"}
    sec={s["opening_id"]:s for s in sections["windows"]}
    other={w["id"]:w for w in record["windows"]}
    for pair in record["pairs"]:
        rid,gid=pair["raw_id"],pair["review_id"]
        op=raw.get(rid,{})
        first=sec.get(rid,{})
        a=first.get("face",{})
        b=first.get("deep",{})
        item=other.get(gid,{})
        face=item.get("face",{})
        deep=item.get("recessed_width",{})
        four=item.get("recessed_four_edges",{})
        label={"matched":f"Raw {rid} and Group 09 {gid}","raw_only":f"Raw {rid} only",
               "review_only":f"Group 09 {gid} only"}[pair["status"]]
        message={"matched":"The raw and radius proposals refer to the same location.",
                 "raw_only":"The radius branch did not identify a matching window.",
                 "review_only":"The radius branch found an additional candidate."}[pair["status"]]
        if item.get("status")=="missing_wall_boundary":
            message+=" The radius wall boundary was insufficient for four-corner fitting."
        rows=[["Official raw",fmt(a.get("width_mm")),fmt(b.get("width_mm")),depth_band(b)],
              ["Group 09",fmt(face.get("width_mm")),fmt(deep.get("width_mm")),depth_band(deep)]]
        levels=[["Official raw",fmt(a.get("height_m"),5),fmt(op.get("height_mm")),fmt(b.get("height_m"),5)],
                ["Group 09",fmt(face.get("width_level_m"),5),fmt(face.get("height_mm")),fmt(deep.get("height_m"),5)]]
        evidence=[]
        if face:
            evidence.append(f'{face["supported_sides"]} of four sides passed the reveal-plane checks at D = 0. '
                            'Sides with insufficient returns retained their radius-profile fit.')
            if four.get("status")=="candidate":
                evidence.append(f'The four-line fit at D = {fmt(four["slice_mm"],0)} mm gives width {fmt(four["width_mm"])} mm '
                                f'and height {fmt(four["height_mm"])} mm. The recessed width in the table is the median of five paired-jamb slices.')
            else:
                state=four.get("status","unavailable").replace("_"," ")
                evidence.append(f'The recessed four-corner result was recorded as {state}.')
        def points(q):
            return [None]*4 if q is None else q
        corners=[[letter,xyz(p),xyz(q),xyz(d)] for letter,p,q,d in zip("ABCD",points(op.get("corners_xyz_m")),
                 points(face.get("corners_xyz_m")),points(four.get("corners_xyz_m")),strict=True)]
        yield label,message,rows,levels,corners,evidence


WIDTH_COLUMNS=["Branch","Wall-face aperture (mm)","Recessed frame width (mm)","Recess depth band (mm)"]
LEVEL_COLUMNS=["Branch","Face width level (m)","Face height (mm)","Recessed width level (m)"]
CORNER_COLUMNS=["Corner","Raw face XYZ (m)","Group 09 face XYZ (m)","Group 09 recessed XYZ (m)"]
BENCH_TITLE="How the Group 09 benchmark was scored"
SENS_COLUMNS=["Tolerance","Room / opening / corner (mm)","Panel bias (mm)","Points / 100"]


def sensitivity_table(benchmark):
    return [[name.capitalize(),f'{s["room_mm"]} / {s["opening_mm"]} / {s["corner_mm"]}',
             fmt(s["panel_mm"]),fmt(benchmark["scores"][name])]
            for name,s in benchmark["tolerances"].items()]


def benchmark_table(benchmark):
    c=benchmark["counts"]
    den=c["opening_total"]+2*c["extra_field_doors"]+c["extra_field_windows"]
    panel=benchmark["panel"]
    cuts=benchmark["tolerances"]["nominal"]
    weights=benchmark["domain_weight_points"]
    values=[
        ["Room size",f'{c["room_pass"]} / {c["room_total"]} dimensions within {cuts["room_mm"]} mm',c["room_pass"]/c["room_total"]],
        ["Opening size",f'{c["opening_pass"]} / {den} eligible field items within {cuts["opening_mm"]} mm',c["opening_pass"]/den],
        ["Four corners",f'2 × {c["qualified_windows"]} / ({c["synthetic_windows"]} true + {c["predicted_windows"]} predicted)',
         2*c["qualified_windows"]/(c["synthetic_windows"]+c["predicted_windows"])],
        ["Wall flatness",f'{c["rms_walls"]} / {c["field_walls"]} walls × panel test ({panel["absolute_bias_mm"]:.3f} ≤ {cuts["panel_mm"]:.2f} mm)',
         c["rms_walls"]/c["field_walls"]*int(panel["absolute_bias_mm"]<=cuts["panel_mm"])]]
    return [[label,definition,fmt(rate*weights,1)] for label,definition,rate in values]


BENCH_NOTE="This benchmark evaluates the method on M26, M04, 24 simulated windows, four negative walls and a known-relief panel. It is reported separately from this scan’s measurements."
BENCH_DETAIL="Each domain contributes up to 25 points. The field opening test uses two door widths, two door heights and one window height. A missing item earns zero. An extra door adds two items to the denominator, an extra window adds one. The recorded 2375 mm tape width has unknown contact depth. Both window widths are reported separately. For the corner test a window must match at box IoU ≥ 0.50 and all four 3D corner errors must be within tolerance. The panel tests preservation of known surface relief. The two field RMS records have unknown manual footprints."
