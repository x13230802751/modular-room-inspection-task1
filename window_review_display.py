"""Shared English labels for the optional window review in Word and HTML."""


def tables(item):
    face,deep=item["face"],item["deep"]
    def mm(value):
        return "—" if value is None else f"{value:.2f}"
    rows=[["Depth D (mm)","0","—" if deep["slice_mm"] is None else str(deep["slice_mm"])],
          ["Width (mm)",mm(face["width_mm"]),mm(deep["width_mm"])],
          ["Height (mm)",mm(face["height_mm"]),mm(deep["height_mm"])],
          ["Edge evidence",f'{face["supported_sides"]} of 4 reveal planes',deep["status"].replace("_"," ")]]
    points=[]
    for i,name in enumerate("ABCD"):
        xyz=[]
        for section in (face,deep):
            q=section["corners_xyz_m"]
            xyz.append("—" if q is None else ", ".join(f"{v:.4f}" for v in q[i]))
        points.append([name,*xyz])
    return rows,points


EXPLANATION=("At the wall face, supported reveal planes are extended to D = 0. Each unsupported side retains "
             "its primary fit. The recessed check fits four sides at the centre of the documented layer. "
             "Its single-slice width can differ from the primary five-slice median. All corners below are fitted coordinates.")
COLUMNS=["Measurement","Wall-face aperture","Recessed frame candidate"]
XYZ_COLUMNS=["Corner","Face XYZ (m)","Recessed XYZ (m)"]
