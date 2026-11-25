# Window corner recognition and measurement

This experiment compares seven ways to detect and measure windows on the same wall planes. The inspection program offers the reveal-plane method as an optional CPU cross-check on each primary window. The default measurements use the production profile. M26 W01 has the only listed window in the two course rooms. The field sheet gives width 2375 mm and height 1736 mm. It omits the tape contact depth and surveyed corner coordinates.

## Evidence and measurements

| M26 W01 at the mid-height section | Depth into opening | Width (mm) | Height at centre (mm) |
|---|---:|---:|---:|
| Primary wall-face profile | 0 mm | 2443.84 | 1737.25 |
| Optional reveal planes projected to the face | 0 mm | 2445.39 | 1738.56 |
| Primary recessed frame candidate, median of five paired-jamb widths | 655–675 mm | 2378.35 | — |
| Optional four-line fit on one recessed section | 665 mm | 2376.70 | 1738.72 |

The face width section is approximately 1.280 m above the fitted floor. The empirical recessed width is a candidate for comparison with the tape. A numerical agreement does not identify the tape contacts. The [course reference registry](../../references/manual_reference.json) identifies the source scans by SHA-256.

The held-out test contains 24 positive wall patches and four negative patches. The production and reveal-plane routes each had 23 matches, five extra candidates and one miss. On matched windows, the median of the per-window mean four-corner 3D errors was 4.54 mm for the profile and 0.19 mm for the reveal-plane method. Of 23 common matches, 19 improved and four tied. Both methods put all four corners within 10 mm on 19 of 24 true windows. Partial occlusion and window-shaped holes in scan coverage can cause much larger errors. The real M26 face-height errors against the field sheet were +1.25 and +2.56 mm respectively. Primary and cross-check share their starting outline. The experiment does not establish general sub-millimetre field accuracy.

| Method ID | Proposal source and corner estimator |
|---|---|
| `profile` | Current horizontal profile and its four fitted face lines |
| `profile_xyz` | Same proposals, original-XYZ strip fits |
| `profile_reveal` | Same proposals, a near-face side plane where supported for each edge |
| `profile_scalelsd` | Same proposals, segments from the released ScaleLSD model |
| `layer_grid` | Three main height bands with three sub-bands, a 20 mm grid and a vertical gap test |
| `layer_xyz` | Layered proposals with original-XYZ strip fits |
| `layer_scalelsd` | Layered proposals with ScaleLSD segments |

The reveal check samples original returns 8–80 mm behind each side. It balances points over along-edge and depth bins, fits a plane with RANSAC, tests spatially held-out along-edge bins, and rejects a shift above 20 mm at the face. A rejected side keeps the primary fitted edge. A separate recessed reconstruction requires enough support along all four sides of a 12 mm thick slice. Two observed jambs alone can establish the primary recessed width. Source-row IDs in the JSON identify physical returns. The corners themselves are fitted intersections.

## Inspect one scan

From the prepared repository root, run either command in its own new output directory. The upload page offers the same optional review through **Include window corner cross-check**.

```powershell
python inspect_room.py D:/data/M26.pcd --window-review --out results/M26_review
python inspect_room.py D:/data/M26.pcd --preprocess radius --window-review --out results/M26_radius_review
python reporting.py results/M26_review --out results/M26_review_copy
```

For a saved measurement run and its exact source scan, the standalone comparator uses the recorded preprocessing and source-row map. The default command below runs the five geometric configurations.

```powershell
python experiments/window_corners/run.py inspect --cloud D:/data/M26.pcd --run results/M26_review --out results/M26_methods
```

## Reproduce the seven-method benchmark

1. Prepare the standard inspection environment, including the native wall detector and Node.js. Generate the two baseline inspections named `results/M26_raw` and `results/M04_raw` using the original scans. [Installation and inspection](../../README.md)
2. For the two learned-line configurations, use a separate Python environment with the standard inspection dependencies and the authors' inference dependencies. Clone the author code, check out commit `e2751fcd0eb82694abeb12ef7ec9d46237e2ca06`, and download `scalelsd-vitbase-v2-train-sa1b.pt`. The adapter verifies SHA-256 `d0a7333c4de518a70af7d6ea4a283aa0ce9ffe1047525373b94070b1d1d4003f` and loads the state dict strictly. The recorded run used PyTorch 2.8.0+cu128, timm 1.0.15, OpenCV 4.12.0 and an RTX 5060 Laptop GPU. [Author source and setup](https://github.com/ant-research/scalelsd/tree/e2751fcd0eb82694abeb12ef7ec9d46237e2ca06) · [Author weights](https://huggingface.co/cherubicxn/scalelsd/tree/f0a119fb3d4a12c53c317a8746db80d267fb2a0f)
3. Put the two course scans in a directory containing `M26.pcd` and `M04.pcd`, then run the commands below. All paths in the example are local. The report builder uses the seven-method output. Omitting the network and weight arguments to the study runs the five geometric methods, which can be evaluated with `summarize.py`.

```powershell
python inspect_room.py D:/data/M26.pcd --out results/M26_raw
python inspect_room.py D:/data/M04.pcd --out results/M04_raw
python experiments/window_corners/run.py study --clouds D:/data --runs results --out results/window_study --network D:/models/scalelsd --weights D:/models/scalelsd-vitbase-v2-train-sa1b.pt --device cuda
python experiments/window_corners/summarize.py results/window_study
python experiments/window_corners/build_report.py --study results/window_study --raw results/M26_raw --out results/window_evaluation.docx
python tests/check_window_review.py D:/data/M26.pcd results/M26_review results/M26_raw
```

The protocol freezes wall and floor planes across alternatives. Real matches use the known inventory and a frozen primary box as a location proxy. Synthetic truth is generated independently of the detector. Matching is one-to-one on the same wall at box IoU ≥ 0.50. Dimensions use common metric sections. The study records eight real walls, 20 development patches and 28 held-out patches. Conditions include central obstructions, missing sides, flush and tapered openings, and two types of negative control. `measurements.csv` stores one row per wall and method. `cases/*.json` contains each proposal, fitted geometry, evidence and synthetic truth where available. The run manifest fingerprints the model, code and protocol. [Benchmark protocol](protocol.json) · [Integration verification](../../validation/window_corner_verification.json)

## Research sources

- Chen, Li, Hong and Li (ISARC 2026) apply point-cloud semantic segmentation and a minimum-area rectangle to a trimmed window boundary. This is the course reference for the measurement task. Its segmentation model was not run in this comparison. [ISARC proceedings](https://doi.org/10.22260/ISARC2026/0180)
- *Lightweight geometry-guided automated 3D indoor reconstruction from point clouds* (2026), section 3.6, motivates the layered proposals. The local code borrows its sub-band combination and adapts the height test to a dominant vertical gap on the supplied wall. The paper's complete reconstruction and inpainting system was not reproduced. [International Journal of Digital Earth](https://doi.org/10.1080/17538947.2026.2741454)
- Ke et al. (CVPR 2025) release an image line-segment detector. We ran their forward pass and pretrained weights on metric wall occupancy rasters. On M26 W01, 111 segments passed the vote threshold, yet neither automatic proposal route produced a four-sided neural window. The same checkpoint retained 575 segments on the author's indoor photo. Projection and four-side association are local components. [CVPR paper](https://openaccess.thecvf.com/content/CVPR2025/html/Ke_ScaleLSD_Scalable_Deep_Line_Segment_Detection_Streamlined_CVPR_2025_paper.html) · [Official implementation](https://github.com/ant-research/scalelsd)
- Qin et al. (2024) study wireframe reconstruction for incomplete indoor point clouds. The paper provides context for fitting and validating geometric boundaries. [Original paper](https://doi.org/10.1016/j.jag.2024.103893)
