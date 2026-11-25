"""Compare geometrically matched features and audit original-coordinate whole-wall RMS."""
import argparse
import csv
import hashlib
from pathlib import Path
import platform
import sys
from importlib.metadata import version
import numpy as np
from scipy.optimize import linear_sum_assignment
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "controls/cylindrical"))
from benchmark import check_checkout, digest, inspect_case, load, read_points, save
PROTOCOL = load(HERE / "protocol.json")


def write_table(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def orthogonal_rms(points):
    centered = points - points.mean(axis=0)
    _, axes = np.linalg.eigh(centered.T @ centered)
    distance = centered @ axes[:, 0] * 1000
    return float(np.sqrt(np.mean(distance ** 2)))


def assign(first, second, difference):
    """Find the maximum number of eligible one-to-one matches, then minimize cost."""
    cost = np.full((len(first), len(second) + len(first)), 1000.0)
    valid = {}
    for i, x in enumerate(first):
        for j, y in enumerate(second):
            result = difference(x, y)
            cost[i, j] = 100000.0 if result is None else result[0]
            if result is not None:
                valid[i, j] = result[1]
    rows, cols = linear_sum_assignment(cost)
    return {i: (second[j], valid[i, j]) for i, j in zip(rows, cols) if (i, j) in valid}


def wall_distance(base, other):
    a, b = (np.array(w["plane_normal"]) for w in (base, other))
    delta = np.subtract(base["plane_center_m"], other["plane_center_m"])
    angle = float(np.rad2deg(np.arccos(np.clip(abs(a @ b), 0, 1))))
    offset = float(1000 * max(abs(delta @ a), abs(delta @ b)))
    ma, md = (PROTOCOL["matching"][key] for key in ("max_wall_angle_deg", "max_plane_offset_mm"))
    if angle > ma or offset > md:
        return None
    return angle / ma + offset / md, dict(angle_deg=angle, plane_offset_mm=offset)


def opening_distance(base, other):
    if base["type"] != other["type"]:
        return None
    delta = float(np.linalg.norm(np.subtract(base["center_xyz_m"], other["center_xyz_m"])))
    if delta > PROTOCOL["matching"]["max_opening_center_offset_m"]:
        return None
    return delta, delta


def error_row(room, method, group, name, measured, reference, **where):
    return dict(room=room, method=method, group=group, feature=name, value_mm=measured, reference_mm=reference,
                signed_difference_mm=None if measured is None else measured - reference, **where)


def key_digest(ids):
    return hashlib.sha256(np.sort(np.asarray(ids, dtype="<i8")).tobytes()).hexdigest()


def selected(result, wall):
    record = wall["whole"]
    if not record.get("residual_file"):
        return None, None
    with np.load(result / record["residual_file"]) as data:
        ids = data["point_index"].astype(np.int64)
        signed = data["signed_mm"]
        assert len(np.unique(ids)) == len(ids) == record["n_selected"]
        assert abs(np.sqrt(np.mean(signed ** 2)) - record["rms_mm"]) < 1e-7
        return ids, record["rms_mm"]


def wall_record(prefix, reference_wall, raw_ids, baseline_rms, found, folder, raw, points, mapping, reverse, ref):
    count = np.count_nonzero(reverse[raw_ids] >= 0) if raw_ids is not None else 0
    row = dict(**prefix, baseline_wall=reference_wall["id"], baseline_rms_mm=baseline_rms,
               manual_context_mm=ref["value_mm"] if reference_wall["id"] == ref["wall_id_in_this_scan"] else None,
               fixed_base_n=len(raw_ids) if raw_ids is not None else None, fixed_retained_n=count)
    if count >= 3:
        common = raw_ids[reverse[raw_ids] >= 0]
        row.update(fixed_raw_mm=orthogonal_rms(raw[common]), fixed_filtered_mm=orthogonal_rms(points[reverse[common]]),
                   fixed_rows_sha256=key_digest(common))
    if found is None:
        return dict(row, status="wall_not_matched")
    wall, geometry = found
    row.update(matched_wall=wall["id"], status=wall["whole"]["status"],
               warning_codes=" | ".join(wall["whole"].get("warnings", [])), **geometry)
    indices, measured = selected(folder, wall)
    if indices is None:
        return row
    original = mapping[indices]
    replay = orthogonal_rms(raw[original])
    np.testing.assert_allclose(orthogonal_rms(points[indices]), measured, rtol=0, atol=1e-7)
    row.update(native_rms_mm=measured, native_rows=len(indices), raw_replay_mm=replay,
               coverage_fraction=wall["whole"].get("coverage_fraction"),
               selected_raw_rows_sha256=key_digest(original))
    if raw_ids is not None:
        shared = len(np.intersect1d(raw_ids, original, assume_unique=True))
        row["selected_rows_iou"] = shared / (len(raw_ids) + len(original) - shared)
    if row["manual_context_mm"] is not None:
        row["difference_to_manual_mm"] = measured - row["manual_context_mm"]
    return row


def process_room(repo, scans, work_by_method, room, all_tables):
    refs = load(repo / "references/manual_reference.json")["rooms"][room]
    source = scans / f"{room}.pcd"
    assert digest(source) == refs["sha256"]
    raw = read_points(repo, source)
    raw_result = work_by_method["raw"] / "runs" / room / "raw"
    baseline = load(raw_result / "summary.json")
    base_walls = baseline["walls"]
    base_sets = [selected(raw_result, w) for w in base_walls]
    roles = [o["type"] for w in base_walls for o in w["openings"]]
    if sorted(roles) != sorted(refs["openings_mm"]):
        raise ValueError(f"Review raw opening identities for {room} before comparing against its manual records.")
    for method in PROTOCOL["methods"]:
        work = work_by_method[method]
        inputs, folder = work / "inputs" / room / method, work / "runs" / room / method
        info = load(inputs / "input.json")
        mapping = np.load(inputs / "source_rows.npy")
        assert digest(inputs / "source_rows.npy") == info["mapping_sha256"]
        assert info["source_sha256"] == refs["sha256"] and np.all(np.diff(mapping) > 0)
        assert (mapping >= 0).all() and (mapping < len(raw)).all()
        points = raw if method == "raw" else read_points(repo, inputs / "input.pcd")
        if method != "raw":
            assert digest(inputs / "input.pcd") == info["input_sha256"]
        assert len(mapping) == len(points)
        reverse = np.full(len(raw), -1, dtype=np.int64)
        reverse[mapping] = np.arange(len(mapping))
        log = load(work / "logs" / room / f"{method}.json")
        run = load(folder / "summary.json") if log["exit_code"] == 0 else {}
        if run:
            assert run["cloud"]["sha256"] == info["input_sha256"]
            assert run["algorithms"]["stages"]["rms"]["call"] == "extensions.native_support:measure"
        sections = load(folder / "window_sections.json")["windows"] if run else []
        actual_walls = run.get("walls", [])
        pairs = assign(base_walls, actual_walls, wall_distance)
        prefix = dict(room=room, method=method)
        dimensions, windows, flatness, cases = (all_tables[k] for k in ("dimensions", "windows", "wall_rms", "cases"))
        for name, ref in refs["dimensions_mm"].items():
            value = (run.get("room") or {}).get(name + "_mm")
            dimensions.append(error_row(room, method, "room", name, value, ref))
        matched_openings = 0
        for i, wall in enumerate(base_walls):
            matched = pairs.get(i)
            flatness.append(wall_record(prefix, wall, *base_sets[i], matched, folder, raw, points, mapping, reverse, refs["rms"]))
            actual = matched[0]["openings"] if matched else []
            items = assign(wall["openings"], actual, opening_distance)
            matched_openings += len(items)
            for j, base in enumerate(wall["openings"]):
                opening, offset = items.get(j, (None, None))
                role = base["type"]
                location = dict(baseline_wall=wall["id"], matched_wall=matched[0]["id"] if matched else None,
                                measured_opening=opening["id"] if opening else None, center_offset_m=offset)
                for direction in ("width", "height"):
                    value = opening.get(direction + "_mm") if opening else None
                    level = opening.get("width_at_height_m") if opening and direction == "width" else None
                    dimensions.append(error_row(room, method, "opening_face", role + "_" + direction, value,
                                      refs["openings_mm"][role][direction], width_height_m=level, **location))
                if role != "window":
                    continue
                section = next((v for v in sections if opening and v["opening_id"] == opening["id"]), {})
                face, deep = section.get("face", {}), section.get("deep", {})
                if section.get("profile_file"):
                    with (folder / section["profile_file"]).open(encoding="utf-8-sig", newline="") as handle:
                        for row in csv.DictReader(handle):
                            all_tables["window_profile"].append(dict(
                                **prefix, baseline_wall=wall["id"], measured_opening=opening["id"],
                                section_height_m=face["height_m"], depth_mm=row["depth_mm"],
                                mid_height_width_mm=row["width_0.50"], supported_width_strips=row["width_strips"]))
                interval = deep.get("depth_range_mm") or [None, None]
                record = dict(**prefix, **location, manual_mm=refs["openings_mm"][role]["width"],
                              face_height_m=face.get("height_m"), face_depth_mm=face.get("depth_mm"),
                              face_width_mm=face.get("width_mm"), deep_height_m=deep.get("height_m"),
                              first_slice_mm=interval[0], last_slice_mm=interval[1], deep_width_mm=deep.get("width_mm"),
                              deep_status=deep.get("status", "window_not_matched"))
                for endpoint in (deep.get("representative") or {}).get("endpoints", []):
                    row = endpoint["original_index"]
                    np.testing.assert_allclose(endpoint["xyz_m"], points[row], atol=1e-8, rtol=0)
                    record[endpoint["side"] + "_sensor_row"] = int(mapping[row])
                    record[endpoint["side"] + "_move_mm"] = float(np.linalg.norm(points[row] - raw[mapping[row]]) * 1000)
                windows.append(record)
        cases.append(dict(**info, native_exit=log["exit_code"], native_seconds=log["elapsed_seconds"],
                          walls_detected=len(actual_walls), walls_matched=len(pairs), openings_matched=matched_openings,
                          openings_detected=sum(len(w["openings"]) for w in actual_walls),
                          baseline_openings=len(roles), native_input_rows=len(points)))


def summaries(tables):
    dims = tables["dimensions"]
    common = {}
    for group in ("room", "opening_face"):
        valid = [{(r["room"], r["feature"]) for r in dims if r["group"] == group and r["method"] == m
                  and r["value_mm"] is not None} for m in PROTOCOL["methods"]]
        common[group] = set.intersection(*valid)
    out = []
    for method in PROTOCOL["methods"]:
        cases = [r for r in tables["cases"] if r["method"] == method]
        total, retained = (sum(r[key] for r in cases) for key in ("finite_rows", "retained_rows"))
        row = dict(method=method, retained_pct=100 * retained / total, removed=total-retained,
                   walls_matched=sum(r["walls_matched"] for r in cases),
                   openings_matched=sum(r["openings_matched"] for r in cases),
                   openings_detected=sum(r["openings_detected"] for r in cases))
        for group, prefix in (("room", "room"), ("opening_face", "opening")):
            records = [r for r in dims if r["group"] == group and r["method"] == method]
            for kind, eligible in (("", records), ("common_", [r for r in records if (r["room"], r["feature"]) in common[group]])):
                errors = np.array([r["signed_difference_mm"] for r in eligible if r["value_mm"] is not None])
                row[prefix + "_" + kind + "n"] = len(errors)
                row[prefix + "_" + kind + "mae_mm"] = float(np.abs(errors).mean()) if len(errors) else None
                row[prefix + "_" + kind + "rmse_mm"] = float(np.sqrt(np.mean(errors ** 2))) if len(errors) else None
        depth_independent = [r["signed_difference_mm"] for r in dims if r["method"] == method
                             and r["group"] == "opening_face" and r["feature"] != "window_width"
                             and r["value_mm"] is not None]
        row["opening_excluding_window_width_n"] = len(depth_independent)
        row["opening_excluding_window_width_mae_mm"] = float(np.mean(np.abs(depth_independent))) if depth_independent else None
        walls = [r for r in tables["wall_rms"] if r["method"] == method]
        row["valid_whole_walls"] = sum(r.get("native_rms_mm") is not None for r in walls)
        delta = [r["fixed_filtered_mm"]-r["fixed_raw_mm"] for r in walls if "fixed_filtered_mm" in r]
        row["median_fixed_change_mm"] = float(np.median(delta)) if delta else None
        for r in walls:
            if r["manual_context_mm"] is not None:
                row[r["room"] + "_whole_mm"] = r.get("native_rms_mm")
                row[r["room"] + "_raw_replay_mm"] = r.get("raw_replay_mm")
        out.append(row)
    return out


def analyse(repo, scans, roots, out):
    check_checkout(repo)
    work_by_method = {m: roots[v] for m,v in PROTOCOL["source_studies"].items()}
    from importlib import import_module
    sys.path.insert(0,str(repo / "tests"))
    audit_native = import_module("check_native_support").audit
    cases_audited = []
    tables = {k: [] for k in ("cases", "dimensions", "windows", "wall_rms", "window_profile")}
    for room in ("M26", "M04"):
        for m, work in work_by_method.items():
            inputs = work / "inputs" / room / m
            run = work / "runs" / room / m
            log = load(work / "logs" / room / (m + ".json"))
            assert log["repository_commit"] == PROTOCOL["commit"]
            meta = load(inputs / "input.json")
            if m != "p2p":
                folder = HERE/"controls"/PROTOCOL["source_studies"][m]
                assert meta["filter_sha256"] == digest(folder/"filters.py") and meta["protocol_sha256"] == digest(folder/"protocol.json")
            else:
                expected_code = hashlib.sha256((digest(HERE/"infer.py")+digest(HERE/"cuda_forward.py")).encode()).hexdigest()
                assert meta["code_sha256"]==expected_code and meta["vote_min"]>=1
                assert meta["vote_sha256"]==digest(inputs/"votes.npy")
                assert meta["weight_sha256"]==PROTOCOL["checkpoint_sha256"] and meta["config_sha256"]==PROTOCOL["config_sha256"]
            if log["exit_code"] != 0:
                cases_audited.append(dict(room=room,method=m,result="native_run_failed"))
                continue
            path = scans/(room+".pcd") if m=="raw" else inputs/"input.pcd"
            audit = audit_native(str(path),run)
            assert audit["sha256"] == meta["input_sha256"] == log["input_sha256"]
            cases_audited.append(dict(room=room,method=m,result="passed",**audit))
        process_room(repo, scans, work_by_method, room, tables)
    tables["method_summary"] = summaries(tables)
    out.mkdir(parents=True, exist_ok=True)
    save(out/"native_audit.json",dict(auditor="tests/check_native_support.py:audit",cases=cases_audited))
    for name, rows in tables.items():
        write_table(out / f"{name}.csv", rows)
    audit = load(repo / "validation/integration_verification.json")
    fresh = {(r["room"], r["baseline_wall"]): r for r in tables["wall_rms"] if r["method"] == "raw"}
    verification = []
    for run in audit["records"]:
        room = Path(run["source"]).stem
        for wall in run["walls"]:
            key = (room, wall["wall"])
            value = fresh[key]["native_rms_mm"]
            verification.append(dict(room=room, wall=wall["wall"], repository_mm=wall["whole_rms_mm"],
                                 reproduced_mm=value, difference_mm=value-wall["whole_rms_mm"]))
    write_table(out / "baseline_check.csv", verification)
    manifest = load(repo / "native_backend/native/bin/manifest.json")
    save(out / "provenance.json", dict(repository=PROTOCOL["repository"], commit=PROTOCOL["commit"],
         comparison_audit_commit=audit["git_commit"], protocol_sha256=digest(HERE / "protocol.json"),
         model_sha256=PROTOCOL["checkpoint_sha256"], model_config_sha256=PROTOCOL["config_sha256"], native_commits=manifest["source_commits"],
         native_compiler=manifest["compiler"], native_binaries=manifest["binaries"],
         system=platform.system(), machine=platform.machine(), python=platform.python_version(),
         packages={p: version(p) for p in ("numpy", "scipy", "matplotlib", "python-docx")},
         inputs={room: digest(scans / f"{room}.pcd") for room in ("M26", "M04")}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage",choices=["inspect","analyse"])
    for flag in ("repo", "cloud-dir", "work"):
        p.add_argument("--" + flag, type=Path, required=True)
    for flag in ("classical","cylindrical","out"):
        p.add_argument("--"+flag,type=Path)
    p.add_argument("--rooms",nargs="+",choices=["M26","M04"],default=["M26","M04"])
    a = p.parse_args()
    if a.stage=="inspect":
        check_checkout(a.repo.resolve())
        for room in a.rooms:
            if not inspect_case((a.repo.resolve(),a.cloud_dir.resolve(),a.work.resolve(),room,"p2p")):
                raise SystemExit(f"Native inspection failed for {room}. See work/logs.")
    elif all((a.classical,a.cylindrical,a.out)):
        analyse(a.repo.resolve(),a.cloud_dir.resolve(),dict(classical=a.classical.resolve(),cylindrical=a.cylindrical.resolve(),p2p=a.work.resolve()),a.out.resolve())
    else:
        p.error("Analysis requires --classical, --cylindrical and --out.")
