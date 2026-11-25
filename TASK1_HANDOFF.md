# Task 1 inspection handoff

**Distribution 2026-11-25.6.** The GitHub archive contains this source tree. Its companion `Task1_Group09_Handshake.zip` contains the inspected M26 and M04 runs from measurement release 2026-11-25.3. Install the native programs once, open `run.cmd`, choose one scan and leave **Official raw measurements + Group 09 review** selected. The official pass measures the room, doors, windows and wall RMS on the original point cloud. Group 09 independently redetects windows on radius-selected points and fits their reveals. One English Word report presents both. The baseline checkout is `a7edfe5d75596f72f6b060d7ff19d4e6324376e4`. [Setup and commands](README.md)

The [seven-slide HKU Civil Engineering presentation](docs/Task1_Inspection_Presentation.pptx) shows the four-interface workflow on slide 3, all 70 nominal scores on slide 6 and the selected algorithm's radius, wall-face and recessed-frame geometry on slide 7.

1. Read the official wall-face and five-slice recessed widths separately. Read the next comparison table for the secondary face fit and recessed candidate. The four-line width at the representative depth is an additional reading. Each branch uses its own fitted wall and recorded elevation.
2. Follow `summary.group09_review.file` to the branch result. Trace fitted sides to the selected original rows, check for partial support and read spatial associations before comparing IDs. A complete search with zero windows is a valid outcome. [Interface](INTERFACE_SPEC.md)
3. The research comparison gave Group 09 a nominal 86/100. This is a result on two measured rooms and controlled geometries. Each new scan reports its own geometry, support and branch agreement. [Worked scoring guide](docs/GROUP09_SCORING.md) · [Paired verification](validation/group09_verification.json)
4. Run `python experiments/joint_benchmark/verify_scores.py --combination 9 --mode nominal` to follow individual measurements through the four calculations. Add `--json` for the item-level trace, or run the same script without options to verify all 210 scores. Run `python tests/check_group09.py` for the branch and benchmark checks. To replace RMS or the writer, use the local profile interfaces. [RMS and report contract](REPORT_API.md)

## Earlier single-treatment controls

In a single-treatment run, the checkbox **Include a corner check on the selected input** or CLI flag `--window-review` enables the earlier same-input method. On 24 held-out simulated windows, the baseline and the extension each matched 23 and produced five extra detections across the 28 walls. The median four-corner error on those matches fell from 4.54 to 0.19 mm. Both put all four corners within 10 mm on 19 of the 24 windows. The single real window has tape dimensions and no surveyed corner coordinates. M26 face height changed from 1737.25 to 1738.56 mm against a field height of 1736 mm. Use the new columns as an independent geometric check of the primary profile's edge positions. [Seven-method evaluation](experiments/window_corners/README.md) · [Validation records](validation/window_corner_verification.json)

| Room and measurement | Original | Radius | Field reference |
|---|---:|---:|---:|
| M26 W02 door width at 1.00 m (mm) | 898.95 | 898.95 | 900 |
| M04 W02 door width at 1.00 m (mm) | 920.23 | 920.23 | 918 |
| M26 W01 wall-face aperture at D = 0 (mm) | 2443.84 | 2443.85 | Tape width 2375, contact depth unknown |
| M26 W01 recessed candidate at D = 655–675 mm (mm) | 2378.35 | 2378.35 | Same tape record, contact depth unknown |
| M26 W03 whole-wall RMS (mm) | 1.142 | 1.142 | 1.0, footprint unrecorded |
| M04 W01 whole-wall RMS (mm) | 1.351 | 1.352 | 1.8, footprint unrecorded |

The M26 window was measured near 1.280 m above the fitted floor. D increases from the interior face into the opening. Both runs detected one window in M26 and none in M04. The radius rule retained 793,065 of 793,393 finite points in M26 and 509,707 of 510,190 in M04. All four runs reproduced the prior experiment's opening dimensions, RMS residuals and point memberships. Both original files were matched by their byte digests to the reference registry. [Verified run records](validation/preprocessing_verification.json) · [Manual reference registry](references/manual_reference.json)

## Reading and extending a run

1. Open `report.docx` for the input selection, opening dimensions, window sections, whole-wall RMS, elevations and source provenance. `report.html` links the measurement records for the same run.
2. Read `summary.json → preprocessing`. Coordinates are in metres, reported widths and RMS in mm. Corner, endpoint and residual IDs index the original scan from zero. The native detector's compact support text has a separate row map when required. [Interface specification](INTERFACE_SPEC.md)
3. To change the RMS provider, register it in a local profile and rerun measurement. To change only the writer, use `python reporting.py EXISTING_RUN --out NEW_DIRECTORY`. The report-only route consumes saved measurements and checks their bound files. [Report and RMS API](REPORT_API.md)
4. To verify an installation, run `python tests/check_preprocessing.py` and `python tests/check_native_support.py SCAN RUN`. The latter audits exact native membership and independently reconstructs RMS on the original coordinates. [Continuation instructions](CONTINUATION_PROMPT.md) · [Machine-readable handoff](HANDSHAKE.json)

## P2P-Bridge experiment

The ScanNet++ XYZ model moved the fitted sides of M26's 900 mm doorway outward by about 11.59 and 13.92 mm at 1 m when projected onto the original wall axis. This door accounts for about 54% of the increase in the five-item opening MAE. On M26 W03, changing only the coordinates of the original wall support raised RMS from 1.142 to 2.799 mm. Reselecting the support after inference yielded 2.948 mm. These observations motivate retaining the model in the experiment directory. The experiment includes all ten treatments, the model protocol and the measured evidence. [Diagnosis and source tables](experiments/p2p_benchmark/FINDINGS.md)

## Upload to GitHub

The source ZIP contains this README, the Python and JavaScript entry points, the native adapters, interfaces, verification records, experimental scripts and existing upstream documentation. Extract its contents at the root of a checkout of the integrated GitHub repository. In GitHub Desktop, create a branch, inspect the changes, commit and publish the branch. Then open a pull request. The archive has a single repository root with `README.md` at its top level. Build the native programs on each new machine using the setup commands. [Integrated repository](https://github.com/x13230802751/room-inspection-integrated) · [Native source provenance](native_backend/PROVENANCE.md)

For a browser upload, select the destination branch and use **Add file → Upload files**. Upload the extracted files in batches of up to 100. Preserve repository-relative paths, including the root `.gitignore`, and check the final tree against the archive. A local Git checkout and GitHub Desktop preserve the directory structure in one commit. [GitHub file upload instructions](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)
