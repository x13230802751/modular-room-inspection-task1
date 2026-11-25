"""Run the frozen preprocessing experiment beside a clean integrated repository checkout."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import numpy as np
from filters import PROTOCOL, apply_filter

HERE = Path(__file__).resolve().parent


def digest(path):
    with Path(path).open("rb") as f:
        value = hashlib.sha256()
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf8")


def check_checkout(repo):
    def git(*args):
        return subprocess.check_output(["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
                                       text=True).strip()
    if git("rev-parse", "HEAD") != PROTOCOL["commit"]:
        raise ValueError("Use the checkout specified by protocol.json for this comparison.")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Modified tracked files would change the frozen comparison.")


def read_points(repo, path):
    sys.path.insert(0, str(repo / "third_party"))
    try:
        from wall_flatness.io import read_cloud
    finally:
        sys.path.pop(0)
    return read_cloud(str(path))


def write_xyz_pcd(path, points):
    header = ("# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 8 8 8\nTYPE F F F\nCOUNT 1 1 1\n"
              f"WIDTH {len(points)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {len(points)}\nDATA binary\n")
    with path.open("wb") as f:
        f.write(header.encode("ascii"))
        np.asarray(points, dtype="<f8").tofile(f)


def prepare_room(repo, scans, work, room, methods, workers):
    source = scans / f"{room}.pcd"
    original_hash = digest(source)
    expected = load(repo / "references/manual_reference.json")["rooms"][room]["sha256"]
    if original_hash != expected:
        raise ValueError(f"{room} input hash does not match the course reference.")
    raw = read_points(repo, source)
    root = work / "inputs" / room
    root.mkdir(parents=True, exist_ok=True)
    for method in methods:
        destination = root / method
        if destination.exists():
            previous = load(destination / "input.json")
            if (previous["source_sha256"] != original_hash or previous["filter_sha256"] != digest(HERE / "filters.py")
                    or previous["protocol_sha256"] != digest(HERE / "protocol.json")):
                raise ValueError("Use a new work directory for a changed experiment.")
            continue
        with TemporaryDirectory(dir=root) as temp:
            staged = Path(temp) / "input"
            staged.mkdir()
            start = time.perf_counter()
            transformed, source_rows, stats = apply_filter(raw, method, workers)
            elapsed = time.perf_counter() - start
            if method == "raw":
                # The native pipeline indexes the unchanged source, including its nonfinite rows.
                source_rows = np.arange(len(raw), dtype=np.int64)
                condition_hash = original_hash
            else:
                write_xyz_pcd(staged / "input.pcd", transformed)
                condition_hash = digest(staged / "input.pcd")
            np.save(staged / "source_rows.npy", source_rows, allow_pickle=False)
            record = dict(room=room, method=method, source_sha256=original_hash, input_sha256=condition_hash,
                          mapping_sha256=digest(staged / "source_rows.npy"), filter_sha256=digest(HERE / "filters.py"),
                          protocol_sha256=digest(HERE / "protocol.json"), preprocessing_seconds=elapsed, **stats)
            save(staged / "input.json", record)
            staged.rename(destination)
        print(f"{room} {method}: {len(transformed):,} retained, P95 move {stats['p95_move_mm']:.3f} mm", flush=True)


def inspect_case(job):
    repo, scans, work, room, method = job
    inputs = work / "inputs" / room / method
    info = load(inputs / "input.json")
    source = scans / f"{room}.pcd" if method == "raw" else inputs / "input.pcd"
    if digest(source) != info["input_sha256"] or digest(inputs / "source_rows.npy") != info["mapping_sha256"]:
        raise ValueError("A prepared cloud or row map has changed.")
    result = work / "runs" / room / method
    logs = work / "logs" / room
    logs.mkdir(parents=True, exist_ok=True)
    if result.exists():
        existing = load(result / "summary.json")
        if existing["cloud"]["sha256"] != info["input_sha256"]:
            raise ValueError("Existing result has a different input digest.")
        return True
    print(f"Inspecting {room} / {method}", flush=True)
    start = time.perf_counter()
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    env.pop("TASK1_RMS_FRAMEWORK", None)
    with (logs / f"{method}.txt").open("w", encoding="utf8") as log:
        task = subprocess.run([sys.executable, str(repo / "inspect_room.py"), str(source), "--unit", "m",
                               "--up", "0", "0", "1", "--out", str(result)], env=env, stdout=log, stderr=subprocess.STDOUT)
    save(logs / f"{method}.json", dict(exit_code=task.returncode, elapsed_seconds=time.perf_counter() - start,
                                       input_sha256=info["input_sha256"], repository_commit=PROTOCOL["commit"]))
    print(f"Finished {room} / {method}, exit {task.returncode}", flush=True)
    return task.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "inspect", "all"])
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--cloud-dir", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--rooms", nargs="+", choices=["M26", "M04"], default=["M26", "M04"])
    parser.add_argument("--methods", nargs="+", choices=list(PROTOCOL["methods"]), default=list(PROTOCOL["methods"]))
    parser.add_argument("--jobs", type=int, default=1, help="concurrent native inspections")
    parser.add_argument("--workers", type=int, default=2, help="threads for nearest-neighbour lookup")
    args = parser.parse_args()
    repo, scans, work = (p.resolve() for p in (args.repo, args.cloud_dir, args.work))
    if work.is_relative_to(repo) or work.is_relative_to(scans):
        parser.error("Use an experiment work directory outside the framework and original dataset.")
    check_checkout(repo)
    if args.stage in {"prepare", "all"}:
        for room in args.rooms:
            prepare_room(repo, scans, work, room, args.methods, args.workers)
    if args.stage in {"inspect", "all"}:
        jobs = [(repo, scans, work, room, method) for method in args.methods for room in args.rooms]
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            outcomes = list(pool.map(inspect_case, jobs))
        if not all(outcomes):
            raise SystemExit("Some native runs failed. Inspect work/logs, and retain missing outcomes in the review.")


if __name__ == "__main__":
    main()
