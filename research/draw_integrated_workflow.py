"""Draw the inspection data dependencies from the original four-interface workflow."""
import math
from pathlib import Path
import shutil
import subprocess

from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1000, 529
# Bounds use a top-left origin. The same node labels and edges produce Mermaid and the printed figure.
NODES = {
    "scan": ("shared", (279, 31, 446, 46), "Single-room scan", "PCD or XYZ CSV, units, up direction and source IDs."),
    "walls": ("raw", (18, 97, 652, 47), "Wall segmentation on the raw scan", "Efficient RANSAC returns wall planes and the original point IDs assigned to each wall."),
    "radius": ("review", (718, 97, 264, 47), "Group 09 radius filter", "At least 4 other points within 20 mm."),
    "openings": ("raw", (18, 170, 196, 58), "Door and window fits", "Fit wall slices for centre,", "four corners and size."),
    "points": ("raw", (226, 170, 186, 58), "Original wall points", "Keep measured XYZ", "and source row IDs."),
    "check": ("raw", (424, 170, 246, 58), "Wall-corner check", "Do four walls enclose the room", "with a supported ceiling?"),
    "rediscover": ("review", (718, 170, 264, 58), "Independent window search", "Redetect walls and windows", "on the radius-selected points."),
    "eligible": ("raw", (76, 253, 322, 56), "Wall points outside openings", "Remove returns inside opening polygons.", "An empty mask keeps all assigned points."),
    "corners": ("raw", (424, 253, 246, 56), "Structural wall corners", "Intersect adjacent walls with floor", "and ceiling. Check point support."),
    "face": ("review", (718, 253, 264, 56), "Review the face at D = 0", "Fit the sides of the opening. Keep", "profile edges on unsupported sides."),
    "rms": ("raw", (76, 331, 322, 56), "Whole-wall RMS", "Fit an SVD plane inside the four corners.", "Return orthogonal RMS in mm."),
    "flag": ("flag", (424, 331, 246, 56), "Flag for review", "Record the missing boundary and", "mark whole-wall RMS unavailable."),
    "deep": ("review", (718, 331, 264, 56), "Recessed frame candidate", "Take the five-slice median. Test", "four edges at one supported depth."),
    "official": ("raw", (18, 408, 652, 46), "Official results", "Room size, structural corners, opening geometry, and a whole-wall RMS value or status."),
    "pair": ("review", (718, 408, 264, 46), "Match window locations", "Retain paired and one-sided detections."),
    "benchmark": ("flag", (18, 475, 273, 45), "Offline method benchmark", "Group 09 scored 86/100 on the test set."),
    "report": ("shared", (317, 475, 665, 45), "English Word and HTML report", "List wall-face and recessed widths separately, with depth, support and RMS method."),
}
PALETTE = {
    "shared": ("F2F5F5", "718892", "193744"),
    "raw": ("EDF6F3", "82AAA2", "155751"),
    "review": ("EEF2FA", "99AAC7", "334E7C"),
    "flag": ("FEF5E6", "C8A266", "82531E"),
}
# Source, target, displayed decision label, connector colour, and route.
EDGES = [
    ("scan", "walls", "", "raw", [(503,77),(503,86),(344,86),(344,97)]),
    ("scan", "radius", "", "review", [(503,77),(503,86),(850,86),(850,97)]),
    ("walls", "openings", "", "raw", [(344,144),(344,155),(116,155),(116,170)]),
    ("walls", "points", "", "raw", [(344,144),(344,155),(319,155),(319,170)]),
    ("walls", "check", "", "raw", [(344,144),(344,155),(547,155),(547,170)]),
    ("openings", "eligible", "", "raw", [(139,228),(139,253)]),
    ("points", "eligible", "", "raw", [(319,228),(319,253)]),
    ("check", "corners", "Pass", "raw", [(547,228),(547,253)]),
    ("check", "flag", "Fail", "flag", [(670,199),(691,199),(691,358),(670,358)]),
    ("eligible", "rms", "", "raw", [(212,309),(212,331)]),
    ("corners", "rms", "", "raw", [(471,309),(471,318),(356,318),(356,331)]),
    ("corners", "official", "", "raw", [(471,309),(471,318),(411,318),(411,408)]),
    ("openings", "official", "", "raw", [(43,228),(43,408)]),
    ("rms", "official", "", "raw", [(210,387),(210,408)]),
    ("flag", "official", "", "flag", [(548,387),(548,408)]),
    ("radius", "rediscover", "", "review", [(850,144),(850,170)]),
    ("rediscover", "face", "", "review", [(850,228),(850,253)]),
    ("face", "deep", "", "review", [(850,309),(850,331)]),
    ("deep", "pair", "", "review", [(850,387),(850,408)]),
    ("official", "pair", "", "review", [(670,431),(718,431)]),
    ("official", "report", "", "raw", [(519,454),(519,475)]),
    ("pair", "report", "", "review", [(850,454),(850,475)]),
    ("benchmark", "report", "Appendix", "flag", [(291,498),(317,498)]),
]


def mermaid():
    output = ["flowchart TB"]
    for name, (style, bounds, *labels) in NODES.items():
        output.append(f'    {name}["{"<br/>".join(labels)}"]:::{style}')
    for source, target, label, style, route in EDGES:
        arrow = "-.->" if source == "benchmark" else "-->"
        tag = f"|{label}|" if label else ""
        output.append(f"    {source} {arrow}{tag} {target}")
    for name, (fill, stroke, ink) in PALETTE.items():
        output.append(f"    classDef {name} fill:#{fill},stroke:#{stroke},color:#{ink}")
    return "\n".join(output) + "\n"


def draw_pdf(path):
    pdf = Canvas(str(path), pagesize=(WIDTH, HEIGHT), invariant=1, pageCompression=1)
    pdf.setTitle("Single-room inspection workflow")
    pdf.setAuthor("CIVL 7023 Task 1")

    def color(hex_value):
        return HexColor("#" + hex_value)

    def label(x, y, words, size, font="Helvetica", ink="203744", limit=None):
        if limit and stringWidth(words, font, size) > limit:
            raise ValueError(f"Label exceeds the available width: {words}")
        pdf.setFillColor(color(ink))
        pdf.setFont(font, size)
        pdf.drawString(x, HEIGHT-y, words)

    label(18, 22, "Single-room inspection workflow", 22, "Helvetica-Bold")
    for source, target, edge_label, style, route in EDGES:
        edge = color(PALETTE[style][2])
        pdf.saveState()
        pdf.setStrokeColor(edge)
        pdf.setFillColor(edge)
        pdf.setLineWidth(1.4)
        if source == "benchmark":
            pdf.setDash(3, 2)
        wire = pdf.beginPath()
        wire.moveTo(route[0][0], HEIGHT-route[0][1])
        for x, y in route[1:]:
            wire.lineTo(x, HEIGHT-y)
        pdf.drawPath(wire)
        x, y = route[-1]
        dx, dy = x-route[-2][0], y-route[-2][1]
        norm = math.hypot(dx, dy)
        dx, dy = dx/norm, dy/norm
        head = pdf.beginPath()
        head.moveTo(x, HEIGHT-y)
        for sign in (-1, 1):
            head.lineTo(x-7*dx+sign*3.3*dy, HEIGHT-(y-7*dy-sign*3.3*dx))
        head.close()
        pdf.drawPath(head, fill=1, stroke=0)
        pdf.restoreState()
    for name, (style, (x, y, w, h), title, *lines) in NODES.items():
        fill, border, ink = PALETTE[style]
        pdf.setFillColor(color(fill))
        pdf.setStrokeColor(color(border))
        pdf.setLineWidth(1.15)
        pdf.roundRect(x, HEIGHT-y-h, w, h, 5, stroke=1, fill=1)
        label(x+9, y+18, title, 16.6, "Helvetica-Bold", ink, w-18)
        for i, words in enumerate(lines):
            label(x+9, y+36+i*15.2, words, 13.5, limit=w-18)
    label(553, 245, "Pass", 12, "Helvetica-Bold", PALETTE["raw"][2])
    label(694, 245, "Fail", 12, "Helvetica-Bold", PALETTE["flag"][2])
    pdf.showPage()
    pdf.save()


def main():
    base = ROOT / "assets/group09_workflow"
    pdf = base.with_suffix(".pdf")
    binary = shutil.which("pdftoppm")
    if not binary:
        raise SystemExit("Install Poppler and put pdftoppm on PATH to regenerate the PNG.")
    draw_pdf(pdf)
    subprocess.run([binary, "-r", "220", "-singlefile", "-png", str(pdf), str(base)], check=True)
    diagram = mermaid()
    base.with_suffix(".mmd").write_text(diagram, encoding="utf8")
    guide = ROOT / "docs/INTEGRATED_WORKFLOW.md"
    before, after = guide.read_text(encoding="utf8").split("```mermaid\n", 1)
    _, tail = after.split("\n```", 1)
    guide.write_text(before + "```mermaid\n" + diagram.rstrip() + "\n```" + tail, encoding="utf8")


if __name__ == "__main__":
    main()
