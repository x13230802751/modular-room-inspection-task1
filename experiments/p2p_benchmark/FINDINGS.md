# Why the pretrained model changed the measurements

In M26 and M04, P2P-Bridge detected the same three openings as the raw baseline. Its mean absolute error (MAE) across five opening dimensions increased from 8.22 to 16.88 mm. The two reported whole-wall RMS values, 2.948 and 2.624 mm, measure distances to a fitted plane. The manual readings used different, undocumented footprints. [Method comparison](results/method_summary.csv) · [Per-wall audit](results/wall_rms.csv)

## Which dimensions changed

| Room and feature | Manual (mm) | Raw (mm) | P2P-Bridge (mm) |
|---|---:|---:|---:|
| M26 door width at 1.00 m | 900 | 898.95 | 924.46 |
| M26 door height | 2180 | 2191.61 | 2200.73 |
| M26 window height | 1736 | 1737.25 | 1728.98 |
| M04 door width at 1.00 m | 918 | 920.23 | 919.37 |
| M04 door height | 2316 | 2340.95 | 2346.80 |

M26 door width alone accounts for about 54% of the increase in the sum of the five absolute errors. Both fitted jambs contribute. Projecting the change of each fitted jamb at 1.00 m onto the original wall's horizontal axis gives −11.59 mm on the left and +13.92 mm on the right. This widens the opening by about 25.51 mm. These shifts describe fitted edges. M04 door width moved closer to its manual reference. [Dimension evidence](results/dimensions.csv) · [Fitted jambs and projection axis](results/M26_jamb_projection.json)

Window width is excluded from that five-item MAE because the manual tape contact depth was unrecorded. M26's wall-face width at D = 0 was 2443.84 mm raw and 2447.09 mm after P2P. At the separate recessed candidate, D = 655–675 mm, the widths were 2378.35 and 2387.50 mm. The tape recorded 2375 mm. [Window sections](results/windows.csv)

## What happened to wall flatness

RMS below is the square root of the mean squared perpendicular residual after fitting a plane. Comparing the first two result columns isolates the coordinate change on identical point IDs. Comparing the first and third isolates the change in selected IDs at original coordinates. The last column is the complete experimental measurement. The two effects can interact when the plane is refitted.

| Wall | Raw IDs and raw XYZ (mm) | Raw IDs and model XYZ (mm) | Model-selected IDs and raw XYZ (mm) | Model-selected IDs and model XYZ (mm) |
|---|---:|---:|---:|---:|
| M26 W03 | 1.142 | 2.799 | 2.096 | 2.948 |
| M04 W01 | 1.351 | 2.568 | 2.328 | 2.624 |

Both coordinate motion and a change of support membership contributed on these walls. Only 328 original rows in M26 and 483 in M04 were removed by the optional radius filter. It leaves surviving coordinates in place. P2P retained every row and changed its predicted position. Median displacements were 2.54 mm in M26 and 2.16 mm in M04. Their 95th percentiles were 9.62 and 9.46 mm. These are three-dimensional displacements, while RMS is sensitive to displacement along the wall normal. [Displacement evidence](results/cases.csv) · [Fixed-support and selected-support refits](results/wall_rms.csv)

The effect can reverse on another surface. A synthetic panel with known relief had a true RMS of 2.127 mm. On the same 5,329 interior rows, the raw noisy scan yielded 2.246 mm and the model yielded 0.604 mm. Here the model suppressed real relief. A smaller post-treatment RMS can therefore also distort a flatness reading. [Controlled panel](results/panel_control.csv)

## What the evidence can establish

The authors evaluate recovered surfaces with Chamfer and point-to-mesh distances. This study used their ScanNet++ XYZ checkpoint, trained for indoor scan denoising. The room adapter averaged overlapping predictions per source row with supplementary patches for coverage. The evaluation objective and the training data offer plausible explanations for the transfer result. The two rooms do not establish which training characteristic caused it, or whether another checkpoint would produce the same effect. [Vogel et al., ECCV 2024, §§4.1–4.2](https://www.ecva.net/papers/eccv_2024/papers_ECCV/papers/00203.pdf) · [Model and inference settings](protocol.json) · [Author-path patch comparison](results/patch_audit.json)
