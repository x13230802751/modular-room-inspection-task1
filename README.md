# Single-room point cloud inspection

Upload one room scan to obtain an editable English Word report. The default workflow measures the room, doors, windows and whole-wall RMS from the original point cloud. It independently redetects walls and windows on radius-selected points and reviews the four window corners with Group 09. The two branches share the uploaded source, units and up direction.

| Point cloud input | Door and window dimensions | Wall RMS |
|---|---|---|
| Official raw branch | Fit room and opening dimensions on finite original XYZ | Fit one RMS per supported wall, masking the official opening polygons |
| Group 09 review branch | Redetect openings, fit window reveals, measure the face and search for the recessed layer | The official wall values come from the raw branch |
| Optional single treatment | Select raw or radius for all primary geometry, with an optional same-input corner check | Use that single treatment's wall supports |

The Word report identifies the input treatment, the numbers of retained and finite points, and the RMS provider. Window widths appear in separate **wall-face aperture** and **recessed frame candidate** columns with depth and elevation.

The comparison page identifies each matched or single-branch window. It gives the face width, width of the recessed candidate, measurement elevation, depth, fitted corners and support status. It distinguishes the five-slice width from the four-line fit at a single depth. The final appendix explains the historical 86/100 method score. [Scoring rules and worked example](docs/GROUP09_SCORING.md)

## Read the project or reproduce the score

This is the GitHub source package. Extract it at the root of the target checkout to review and commit the code. The companion `Task1_Group09_Handshake.zip` contains the two saved inspections with their English Word reports. Maintainers can start from the [human handoff](TASK1_HANDOFF.md), [machine-readable manifest](HANDSHAKE.json) or [AI continuation prompt](CONTINUATION_PROMPT.md).

The benchmark can be replayed immediately with Python 3.10 or later and the standard library. The following commands work from the root of either extracted package.

```shell
python experiments/joint_benchmark/verify_scores.py --combination 9 --mode nominal
python experiments/joint_benchmark/verify_scores.py --combination 9 --mode nominal --json
python experiments/joint_benchmark/verify_scores.py
```

The first command prints each pass or miss and the four component scores. The second returns the full trace as JSON. The third verifies the 210 published scores. A [precomputed JSON trace](validation/group09_nominal_score_trace.json) is available for readers without Python.

## Install on Windows

Use Python 3.10 or later, Node.js 18 or later, Git and MinGW g++ on PATH. Run the following in the extracted repository root. The Python adapter sources are included. The native setup retrieves the two pinned C++ sources and builds them locally.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe prepare_backends.py
.\.venv\Scripts\python.exe native_backend/scripts/fetch_native.py
.\.venv\Scripts\python.exe native_backend/native/build.py --source-root native_backend/native/sources
```

## Inspect a scan

After installation, double-click **run.cmd**, choose a scan, set units and up direction, leave **Official raw measurements + Group 09 review** selected, and click **Measure and create Word report**. The browser downloads one combined Word report. The CLI uses the same default.

```powershell
.\.venv\Scripts\python.exe inspect_room.py D:/data/M26.pcd --out results/M26_paired
.\.venv\Scripts\python.exe inspect_room.py D:/data/M26.pcd --preprocess raw --out results/M26_raw
.\.venv\Scripts\python.exe inspect_room.py D:/data/M26.pcd --preprocess radius --out results/M26_radius
.\.venv\Scripts\python.exe reporting.py results/M26_paired --out results/M26_report_copy
```

The CLI accepts PCD, CSV with x, y and z headers, and an archive member such as `scan.zip::M26.pcd`. The defaults are metres and positive Z up. Use `--unit mm` or `--up X Y Z` for other input conventions. Give each run a new output directory. To run a distributable synthetic example, use `python examples/run_demo.py --out results/demo` in the prepared environment.

<a id="四接口流程"></a>

## Measurement workflow

The [seven-slide HKU Civil Engineering presentation](docs/Task1_Inspection_Presentation.pptx) includes the original wall-point and structural-corner dependencies, all 70 method scores, and an editable schematic of the selected Group 09 window review.

![A single scan feeds official raw measurements and independent Group 09 window review](assets/group09_workflow.png)

The four measurement interfaces in the upstream GitHub workflow run on the official branch. Group 09 redetects windows independently, and the offline method benchmark supplies the archived scoring appendix. [Interface mapping and editable Mermaid diagram](docs/INTEGRATED_WORKFLOW.md) · [Print-ready PDF](assets/group09_workflow.pdf)

Efficient RANSAC assigns wall supports. The corner module tests the enclosure and ceiling, then intersects their planes. The opening detector fits jambs, heads and sills. The default RMS provider fits a plane to the selected original returns inside the structural corners and outside the detected opening polygons. Insufficient enclosure evidence produces an unavailable whole-wall measurement. Review the reported support, coverage and corner warnings when comparing rooms or reference measurements.

## Continue the project

- [Human handoff](TASK1_HANDOFF.md), [machine handoff](HANDSHAKE.json) and [continuation prompt](CONTINUATION_PROMPT.md)
- [Measurement and preprocessing interfaces](INTERFACE_SPEC.md), [replaceable report and RMS interfaces](REPORT_API.md)
- [Four verified production runs](validation/preprocessing_verification.json), [course reference registry](references/manual_reference.json) and [original course evaluation](docs/Task1_Evaluation.docx)
- [Ten-treatment experiment and P2P-Bridge diagnosis](experiments/p2p_benchmark/FINDINGS.md), [experimental code and reproduction](experiments/p2p_benchmark/README.md)
- [Algorithm contributions](CONTRIBUTIONS.md), [native provenance and upstream usage terms](native_backend/PROVENANCE.md), [source map](docs/source_map.json) and [historical integration guide](docs/project_guide.md)
