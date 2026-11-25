"""Draw the English methods figure used in the inspection report."""
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch


def main(paired=False):
    if paired:
        import subprocess
        import sys
        subprocess.run([sys.executable, str(Path(__file__).with_name("draw_integrated_workflow.py"))], check=True)
        return
    fig = Figure(figsize=(7.0, 4.2), facecolor="white")
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1], xlim=(0, 10), ylim=(0, 7))
    ax.axis("off")

    def box(x, y, width, title, body, fill="#f0f5f5"):
        ax.add_patch(FancyBboxPatch((x, y), width, 1.3, boxstyle="round,pad=.04,rounding_size=.10",
                                    edgecolor="#546a72", facecolor=fill, linewidth=0.8))
        ax.text(x+width/2, y+.98, title, ha="center", va="center", fontsize=11,
                fontweight="bold", color="#172d36")
        ax.text(x+width/2, y+.42, body, ha="center", va="center", fontsize=9.6,
                linespacing=1.22, color="#223e48")

    def arrow(start, end):
        ax.annotate("", end, start, arrowprops=dict(arrowstyle="-|>", color="#506976",
                                                   linewidth=1.2, shrinkA=1, shrinkB=1))

    box(.18, 5.55, 3.85, "Single-room scan", "PCD or XYZ CSV\nUnits and up direction")
    box(4.80, 5.55, 5.02, "Select measurement points", "Raw by default, or a 20 mm radius filter\nOriginal coordinates and row IDs")
    arrow((4.09,6.20),(4.71,6.20))
    box(2.03, 3.74, 5.94, "Fit the room", "Detect plane supports and fit the wall, floor\nand ceiling boundaries")
    arrow((7.00,5.48),(6.37,5.10))
    box(.18, 1.91, 4.66, "Measure openings", "Fit jambs, sill and head. Check window\nwidth at the face and recessed frame.", "#e9f2f4")
    box(5.16, 1.91, 4.66, "Measure wall flatness", "Mask openings within wall corners. Fit\na plane and calculate RMS residuals.", "#e9f2f4")
    arrow((3.25,3.68),(2.65,3.27))
    arrow((6.75,3.68),(7.35,3.27))
    box(1.82, .09, 6.36, "Write the inspection report", "English Word and HTML, measurements, source rows\nand the recorded preprocessing method")
    arrow((2.65,1.85),(3.30,1.45))
    arrow((7.35,1.85),(6.70,1.45))
    fig.savefig(Path(__file__).resolve().parents[1]/"assets"/"measurement_workflow.png", dpi=210)


if __name__ == "__main__":
    main()
    main(paired=True)
