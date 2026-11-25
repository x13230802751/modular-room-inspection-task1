"""Recompute all published scores or explain one combination, using the Python standard library."""
import argparse
import csv
import json
import math
from pathlib import Path


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load_observations(folder):
    return {
        "plan": json.loads((folder / "protocol.json").read_bytes()),
        "manual": json.loads((folder / "manual_reference.json").read_bytes())["rooms"],
        "dimensions": read_csv(folder / "field_dimensions_archive.csv"),
        "walls": read_csv(folder / "field_wall_results.csv"),
        "scenes": read_csv(folder / "simulated_window_results.csv"),
        "panels": {row["method"]: row for row in read_csv(folder / "panel_control.csv")},
    }


def dimension_item(room, name, measured, reference, tolerance):
    error = measured - reference if measured is not None else None
    return {"room": room, "feature": name, "measured_mm": measured, "reference_mm": reference,
            "signed_error_mm": error, "passed": error is not None and abs(error) <= tolerance}


def score_combination(data, number, mode):
    """Return a trace calculated directly from the field, simulated and control observations."""
    plan = data["plan"]
    filters, routes = plan["filters"], plan["recognizers"]
    if not 1 <= number <= len(filters) * len(routes):
        raise ValueError(f"Choose a combination from 1 through {len(filters) * len(routes)}.")
    filter_index, route_index = divmod(number - 1, len(routes))
    method, route = filters[filter_index], routes[route_index]
    cut = plan["sensitivity"][mode]
    walls = [r for r in data["walls"] if r["filter"] == method and r["recognizer"] == route]
    scenes = [r for r in data["scenes"] if r["filter"] == method and r["recognizer"] == route]
    if (len(walls) != 8 or len({(r["room"], r["wall"]) for r in walls}) != 8 or
            len(scenes) != 28 or len({r["case"] for r in scenes}) != 28):
        raise ValueError("The benchmark requires eight distinct field walls and 28 distinct simulated scenes.")

    room_items, opening_items = [], []
    for row in data["dimensions"]:
        if row["method"] != method:
            continue
        if row["group"] == "room":
            items, tolerance = room_items, cut["room_mm"]
        elif row["group"] == "opening_face" and row["feature"].startswith("door_"):
            items, tolerance = opening_items, cut["opening_mm"]
        else:
            continue
        items.append(dimension_item(row["room"], row["feature"], float(row["value_mm"]),
                                    float(row["reference_mm"]), tolerance))
    if len(room_items) != 6 or len(opening_items) != 4 or sum(int(r["doors"]) for r in walls) != 2:
        raise ValueError("This historical benchmark assumes six room dimensions and four readings on the two doors.")

    # Every route shares the doors; the window height comes from this recognizer's matched wall.
    matched_walls = [r for r in walls if int(r["matched"])]
    if len(matched_walls) > 1 or any(r["room"] != "M26" for r in matched_walls):
        raise ValueError("Only the M26 reference window is eligible in the field benchmark.")
    window_height = float(matched_walls[0]["face_height_mm"]) if matched_walls else None
    reference = data["manual"]["M26"]["openings_mm"]["window"]["height"]
    opening_items.append(dimension_item("M26", "window_height", window_height, reference, cut["opening_mm"]))
    field_extra_windows = sum(int(r["detected"]) - int(r["matched"]) for r in walls)

    window_cases = []
    for row in scenes:
        matched = int(row["matched"])
        max_error = float(row["max_corner_mm"]) if row["max_corner_mm"] else None
        if matched not in (0, 1) or bool(matched) != (max_error is not None):
            raise ValueError(f"Inconsistent corner evidence for {row['case']}.")
        window_cases.append({"case": row["case"], "true": int(row["expected"]),
                             "predicted": int(row["predicted"]), "matched": matched, "max_corner_mm": max_error,
                             "qualified": bool(matched) and max_error <= cut["corner_mm"]})

    wall_rows = [{"room": r["room"], "wall": r["wall"], "rms_mm": float(r["rms_mm"]) if r["rms_mm"] else None}
                 for r in walls]
    panel = data["panels"][method]
    panel_true, panel_measured = float(panel["true_rms_mm"]), float(panel["measured_rms_mm"])
    panel_bias = abs(panel_measured - panel_true)

    room_pass = sum(item["passed"] for item in room_items)
    opening_pass = sum(item["passed"] for item in opening_items)
    qualified = sum(case["qualified"] for case in window_cases)
    true_windows = sum(case["true"] for case in window_cases)
    predicted_windows = sum(case["predicted"] for case in window_cases)
    available_walls = sum(wall["rms_mm"] is not None for wall in wall_rows)
    panel_pass = panel_bias <= cut["panel_mm"]
    if true_windows != 24:
        raise ValueError("The controlled benchmark requires 24 reference windows.")

    room_rate = room_pass / 6
    opening_rate = opening_pass / (5 + field_extra_windows)
    corner_rate = 2 * qualified / (true_windows + predicted_windows)
    wall_rate = (available_walls / 8) * int(panel_pass)
    total = 25 * (room_rate + opening_rate + corner_rate + wall_rate)

    return {"trace_version": 1, "scope": "historical_method_benchmark", "combination": number,
            "filter": method, "recognizer": route, "mode": mode, "tolerances": cut, "domain_weight": 25,
            "domains": {
                "room": {"passed": room_pass, "denominator": 6, "points": 25 * room_rate, "items": room_items},
                "opening": {"passed": opening_pass, "expected": 5, "extra_windows": field_extra_windows,
                            "denominator": 5 + field_extra_windows, "points": 25 * opening_rate, "items": opening_items},
                "corners": {"true": true_windows, "predicted": predicted_windows,
                            "matched": sum(c["matched"] for c in window_cases), "qualified": qualified,
                            "points": 25 * corner_rate, "cases": window_cases},
                "rms": {"available": available_walls, "denominator": 8, "panel_true_mm": panel_true,
                        "panel_measured_mm": panel_measured, "absolute_bias_mm": panel_bias, "panel_pass": panel_pass,
                        "points": 25 * wall_rate, "walls": wall_rows}},
            "total_points": total}


def print_trace(trace):
    cut = trace["tolerances"]
    domains = trace["domains"]
    print(f"Group {trace['combination']:02} | {trace['filter']} + {trace['recognizer']} | {trace['mode']}")
    for name in ("room", "opening"):
        domain = domains[name]
        print(f"\n{name.capitalize()} dimensions | tolerance {cut[name + '_mm']} mm")
        for item in domain["items"]:
            value = item["measured_mm"]
            reading = "missing" if value is None else f"{value:.4f} mm (signed error {item['signed_error_mm']:+.4f} mm)"
            status = "PASS" if item["passed"] else "MISS"
            print(f"  {item['room']} {item['feature']} | {reading}, reference {item['reference_mm']:g} mm [{status}]")
        if name == "opening":
            print(f"  Denominator = {domain['expected']} expected readings + {domain['extra_windows']} extra windows")
        print(f"  25 * {domain['passed']} / {domain['denominator']} = {domain['points']:.2f}")
    c = domains["corners"]
    print(f"\nWindow face corners | tolerance {cut['corner_mm']} mm")
    print(f"  Matched {c['matched']} true windows. All four corners qualify for {c['qualified']} matches.")
    for case in c["cases"]:
        if case["matched"] and not case["qualified"]:
            print(f"  {case['case']} | largest corner error {case['max_corner_mm']:.4f} mm")
        extra = case["predicted"] - case["matched"]
        missed = case["true"] - case["matched"]
        if extra or missed:
            print(f"  {case['case']} | extra predictions {extra}, missed windows {missed}")
    print(f"  25 * 2 * {c['qualified']} / ({c['true']} + {c['predicted']}) = {c['points']:.2f}")
    w = domains["rms"]
    print(f"\nWall RMS | {w['available']} of 8 field walls returned a value")
    print(f"  Panel absolute bias = abs({w['panel_measured_mm']:.6f} - {w['panel_true_mm']:.6f})"
          f" = {w['absolute_bias_mm']:.6f} mm (threshold {cut['panel_mm']:g} mm)")
    print(f"  25 * {w['available']} / 8 * {int(w['panel_pass'])} = {w['points']:.2f}")
    print(f"\nTotal = {trace['total_points']:.2f} / 100")


def verify(folder):
    data = load_observations(folder)
    published = read_csv(folder / "Combination_Scorecard.csv")
    if len(data["walls"]) != 560 or len(data["scenes"]) != 1960 or len(published) != 70:
        raise ValueError("Incomplete historical benchmark tables.")
    for number, row in enumerate(published, 1):
        for mode in data["plan"]["sensitivity"]:
            result = score_combination(data, number, mode)
            if (number, result["filter"], result["recognizer"]) != (int(row["combination"]), row["filter"], row["recognizer"]):
                raise ValueError(f"Combination {number} differs from the published method order.")
            if not math.isclose(result["total_points"], float(row[mode + "_score"]), rel_tol=0, abs_tol=1e-8):
                raise ValueError(f"Recomputed score differs for combination {number} at {mode} tolerance.")
        observed = [abs(item["signed_error_mm"]) for item in result["domains"]["opening"]["items"]
                    if item["signed_error_mm"] is not None]
        if not math.isclose(sum(observed) / len(observed), float(row["opening_observed_mae_mm"]), abs_tol=1e-8):
            raise ValueError(f"Opening MAE differs for combination {number}.")
        deep = sum(bool(r["deep_width_error_mm"]) and abs(float(r["deep_width_error_mm"])) <= 10 for r in data["scenes"]
                   if r["filter"] == row["filter"] and r["recognizer"] == row["recognizer"])
        if deep != int(row["synthetic_deep_width_within_10mm"]):
            raise ValueError(f"Recessed-width count differs for combination {number}.")
    leaders = [r["combination"] for r in published if r["nominal_rank"] == "1"]
    print("Verified 70 combinations, 210 tolerance scores, 560 field wall observations and 1960 simulated observations.")
    print("Nominal leaders:", ", ".join(leaders))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, nargs="?", default=Path(__file__).resolve().parent)
    parser.add_argument("--combination", type=int, help="explain one historical combination, numbered 1 to 70")
    parser.add_argument("--mode", choices=("strict", "nominal", "relaxed"), help="tolerance setting (default: nominal)")
    parser.add_argument("--json", action="store_true", help="print the selected combination's full measurement trace as JSON")
    args = parser.parse_args()
    if args.combination is None and (args.json or args.mode):
        parser.error("--mode and --json require --combination")
    try:
        if args.combination is None:
            verify(args.folder)
        else:
            record = score_combination(load_observations(args.folder), args.combination, args.mode or "nominal")
            if args.json:
                print(json.dumps(record, indent=2, allow_nan=False))
            else:
                print_trace(record)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"Scoring failed. {error}\n")
