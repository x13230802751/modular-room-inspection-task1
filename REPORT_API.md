# Report and RMS integration

Reports display the whole-wall RMS recorded by the measurement pipeline. Every ROI uses slab_half_thickness_mm=null.

An inspection writes its measurements to disk before creating its Word and HTML files. Report API v1 renders the saved values. An RMS replacement belongs to the measurement profile. A layout replacement belongs to the independent report property of that profile.

Both reports display the input treatment from `summary.preprocessing`. Its source digest and row-selection identity apply to the saved window sections. Renderers display separate columns for the fitted wall-face aperture and the recessed frame candidate, including height above the floor, depth into the opening and evidence status. A missing recessed estimate stays unavailable. Current bundles include a detector-to-source map whenever the selection has gaps. The reporting-only command carries that map to the new bundle and rejects window records from a different selection. A missing preprocessing field in a historical bundle is displayed as unrecorded. [Measurement interface](INTERFACE_SPEC.md)

## Replace the RMS calculation and use the existing report

In paired mode a writer also receives the validated, in-memory object `summary["group09_result"]`. The small descriptor `summary.group09_review` is persisted in the summary and report manifest. Both point to the same branch record. Read official dimensions and wall RMS from the ordinary summary, and official window depths from `window_sections`. Retrieve independent radius/reveal results from the branch object. Display both wall-face and recessed widths, the respective levels, the five-slice depth band, the single-slice quartet and the per-side evidence. Preserve unmatched candidates and unavailable fits. A report-only run copies and verifies the independent result, selection map and depth profile files. Earlier single-treatment bundles use the same report function signature. [Paired result schema](schemas/group09_review.schema.json)

The RMS callable accepts (xyz, roi) and configured keyword options. The actual callable and source fingerprint are recorded in the summary.

| Backend return | Meaning |
|---|---|
| `indices` | Unique offsets into the **supplied subset**, one per selected point. The wrapper maps them to original scan rows. |
| `signed_mm` | Finite, signed, orthogonal point-to-plane residuals in millimetres, one per index. |
| `plane_center_m`, `plane_normal` | A finite three-coordinate point on the fitted reference plane and its unit normal in the input coordinate frame. |
| `coverage_fraction` | Occupied fraction of the ROI grid in [0,1], or null when unavailable. |
| `status`, `warnings` | `ok` or `warning` and an English list of warning codes or explanations. Raise `ValueError` with a reason when the footprint cannot be measured. |

The wrapper calculates RMS as the square root of the mean squared signed residual, saves P95 and maximum absolute residuals, and writes `point_index` and `signed_mm` to the footprint’s NPZ. A backend that returns only a scalar needs an adapter supplying the supporting residuals for this audited measurement path. The report reads `walls[].whole` from the resulting summary. An unavailable record carries a reason and displays a dash. [Adapter implementation](wall_rms.py) · [Machine-readable report RMS contract](schemas/report_rms.schema.json)

## Regenerate the report from an existing result

```shell
python reporting.py results/new-rms --out results/reformatted
```

This command consumes the stored evidence without the original scan, Node.js or the measurement backend. Its input must be a summary v2 run with a measurement manifest. The new directory contains the Word and HTML reports and the evidence files needed for the links. The original run remains available. To change actual RMS values, first run the replacement algorithm. Re-rendering preserves the measurements and the original RMS provenance.

## Replace the report writer

The default writer is `reporting:standard_reports`. A replacement implements the following function.

```python
def render(result_dir, summary, window_sections, **configured_options):
    # Read scan and RMS values from summary and physical window sections from window_sections.
    # Save an editable Word package to result_dir / "report.docx".
    # Save its offline HTML companion to result_dir / "report.html".
    ...
```

`result_dir` is a pathlib.Path for the staged bundle. Wall elevations, ROI files and residual files live at the relative paths in `summary`. Both result arguments are parsed JSON dictionaries. `summary["algorithms"]["stages"]["rms"]` identifies the actual measurement backend. New runs store a matched manual comparison in `summary["manual_reference"]`, or null if none is available. This preserves tape comparisons when partners render a saved run on another computer. `summary["reporting"]` supplies the active writer in memory. The window record uses schema 1.0. A legacy v2 result that predates this file is marked `availability="not_recorded"`. A declared but missing or mismatched window file fails validation.

Use a local profile with independent entries as shown below. Use the same `--profile` argument in the CLI or select the installed profile in the local browser. The reporting-only command resolves just the writer, even if the original RMS model is unavailable.

```json
{
  "api_version": 1,
  "name": "Partner inspection",
  "stages": {"rms": {"call": "extensions.partner_rms:measure"}},
  "report": {"call": "extensions.partner_report:render", "options": {}}
}
```

The measurement CLI and the reporting-only CLI publish a new directory after successful generation. Missing, empty or invalid report outputs fail the run. `report_manifest.json` records the writer, RMS backend, input scan digest, summary and window-file digests, and the two output filenames. The example integration test supplies a different writer and a saved RMS fixture, and verifies that the value reaches both formats. [Report dispatcher](reporting.py) · [Executable contract test](tests/check_reporting.py)

### Optional window corner review

A report writer can read `summary.get("window_corner_review")`. For a recorded review, render the secondary wall-face and recessed results with their section positions and evidence status. The standard writer draws these from the saved summary and adds a separate section to Word and HTML. The canonical door/window measures and RMS remain in the existing fields. A future RMS implementation uses the same report interface. The manifest records the review version, method and geometry/protocol fingerprints. [Data contract](schemas/window_corner_review.schema.json) · [Cross-format and original-row audit](tests/check_window_review.py)
