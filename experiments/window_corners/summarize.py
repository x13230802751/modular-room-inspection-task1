"""Summarize detection coverage and metric error with explicit denominators."""
import argparse
import csv
from pathlib import Path

import numpy as np
from evaluate import METHODS, save
from run import write_table


def median(values):
    return float(np.median(values)) if values else None


def collect(folder):
    with (folder/"measurements.csv").open(encoding="utf-8-sig",newline="") as stream:
        all_rows=list(csv.DictReader(stream))
    results=[]
    for group in ("course","development","holdout"):
        for method in METHODS:
            rows=[r for r in all_rows if r["group"]==group and r["method"]==method]
            if not rows:
                continue
            def counts(k):
                return sum(int(r[k]) for r in rows)
            def numbers(k):
                return [float(r[k]) for r in rows if r.get(k)]
            correct=counts("tp")
            pos=counts("expected")
            fp=counts("fp")
            corners=numbers("corner_mean_error_mm")
            r=dict(group=group,method=method,scenes=len(rows),windows=pos,tp=correct,fp=fp,fn=pos-correct,
                   precision=correct/(correct+fp) if correct+fp else None,recall=correct/pos if pos else None,
                   median_corner_mm=median(corners),max_case_mean_corner_mm=max(corners,default=None),
                   all_four_within_10mm=sum(x<=10 for x in numbers("corner_max_error_mm")) if group!="course" else None,
                   width_abs_median_mm=median([abs(x) for x in numbers("width_difference_mm")]),
                   height_abs_median_mm=median([abs(x) for x in numbers("height_difference_mm")]),
                   supported_depth_widths=len(numbers("deep_width_mm")),depth_four_reported=sum(row.get("deep_four_status")=="candidate" for row in rows),
                   depth_four_truth_matches=len(numbers("deep_corner_mean_error_mm")),deep_corner_median_mm=median(numbers("deep_corner_mean_error_mm")),
                   solid_wall_false_positives=sum(int(row["fp"]) for row in rows if row["case"].startswith("solid_")),
                   blind_patch_false_positives=sum(int(row["fp"]) for row in rows if row["case"].startswith("blind_patch_")))
            pair=[a for a in rows if a.get("corner_mean_error_mm")]
            baseline={p["case"]:float(p["corner_mean_error_mm"]) for p in all_rows if p["group"]==group and p["method"]=="profile" and p.get("corner_mean_error_mm")}
            changes=[float(x["corner_mean_error_mm"])-baseline[x["case"]] for x in pair if x["case"] in baseline]
            r.update(paired_n=len(changes),paired_median_change_mm=median(changes),
                     paired_better=sum(x < -1e-6 for x in changes),paired_tied=sum(abs(x)<=1e-6 for x in changes))
            results.append(r)
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("study",type=Path)
    args=p.parse_args()
    table=collect(args.study)
    write_table(args.study/"method_summary.csv",table)
    save(args.study/"method_summary.json",table)
    for r in table:
        if r["group"]=="holdout":
            print(r["method"],r["tp"],r["fp"],r["median_corner_mm"],r["paired_median_change_mm"],r["depth_four_truth_matches"])


if __name__=="__main__":
    main()
