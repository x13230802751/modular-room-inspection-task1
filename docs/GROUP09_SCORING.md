# How to read the Group 09 score

Group 09 crosses the second point treatment (F02, radius outlier removal) with the second window recognizer (R02, profile proposals refined against the opening reveals). The ten treatments and seven recognizers give 70 combinations. Combination number = 7 × (filter position − 1) + recognizer position. Its nominal result was **86.00 out of 100**, joint first with Group 58. Group 09 earned **80.83** at the strict settings, compared with **50.83** for Group 58.

The benchmark applied each candidate as the measurement and window masking method. The released application uses raw data for official results and Group 09 for a second window opinion. Every report labels the benchmark date and scope. Applying the historical 86 to a single scan or to the paired application would require a separate validation.

## Follow one calculation in the code

From the root of either distribution archive, run either command with Python 3.10 or later. The scoring program uses the standard library. The first command prints the readings, flags, counts, component scores and total. The second emits full-precision JSON, including every synthetic scene and all eight wall RMS values.

```shell
python experiments/joint_benchmark/verify_scores.py --combination 9 --mode nominal
python experiments/joint_benchmark/verify_scores.py --combination 9 --mode nominal --json
```

**How the program chooses the evidence.** In the protocol, each filter is paired with seven recognition routes. For combination 9, `divmod(9 - 1, 7)` gives zero-based indices `(1, 1)`. The corresponding entries are `radius` and `profile_reveal`. The scorer then reads the following inputs. [Protocol](../experiments/joint_benchmark/protocol.json) · [Executable scoring implementation](../experiments/joint_benchmark/verify_scores.py)

| Input in the benchmark directory | Values the scorer uses |
|---|---|
| [Field dimension archive](../experiments/joint_benchmark/field_dimensions_archive.csv) | Select the filter. For the six room dimensions and four door readings, subtract `reference_mm` from `value_mm`. Door readings are shared across window recognizers for that filter. |
| [Field wall observations](../experiments/joint_benchmark/field_wall_results.csv) and [tape references](../experiments/joint_benchmark/manual_reference.json) | Select both filter and recognizer. Add the matched M26 window's `face_height_mm` minus its 1736 mm reference to the opening errors. Count unmatched field window predictions and walls with a numeric RMS. |
| [Simulated scenes](../experiments/joint_benchmark/simulated_window_results.csv) | Select the same filter and recognizer. Read truth count, prediction count, match status and the largest A–D face-corner distance in mm. Every prediction, including those on a negative wall, enters the denominator. |
| [Known-relief panel](../experiments/joint_benchmark/panel_control.csv) | Select the filter and compute the absolute difference between the measured RMS and the independently known RMS. |

**The original scoring loop.** This is the calculation in `analysis/score.py` in the historical study archive. Variable names follow the original program. `room` and `opening` contain signed measurement errors in mm. `t` contains 28 simulated scene records. Python counts each true comparison as 1 and each false comparison as 0.

```python
for mode, cut in PROTOCOL["sensitivity"].items():
    nr = sum(abs(x) <= cut["room_mm"] for x in room)
    no = sum(abs(x) <= cut["opening_mm"] for x in opening)
    nc = sum(r["matched"] and r["max_corner_mm"] <= cut["corner_mm"] for r in t)
    room_rate = nr / 6
    open_rate = no / (5 + field_pred - field_tp)
    corners = 2 * nc / (truth + n)
    panel_rate = (present / 8) * (abs(bias) <= cut["panel_mm"])
    prefix[mode + "_score"] = 25 * (room_rate + open_rate + corners + panel_rate)
```

Here `field_pred - field_tp` counts **extra windows in the two real rooms**. The original driver checks that exactly two field doors were present and four door readings were available. A missed M26 window contributes no passing height, while the fixed denominator still includes that expected height. In the simulated term, `truth` and `n` mean **all true windows and all predicted windows across the controlled scenes**. They count a different population. In the panel term, `present` is the number of field walls with an RMS reading and `bias` is the measured panel RMS minus its reference.

For M26's 900 mm door, the scan returned 898.9495 mm. Its absolute difference is 1.0505 mm, so the opening counter advances by one at 10 mm. The corresponding door height differs by 11.6085 mm, so the counter stays unchanged for that reading. A value exactly on the cutoff passes. The code compares the original floating-point readings before formatting for display. With five eligible readings across three openings and zero false positives, each passing reading contributes five points.

The current Python replay returns the counters and per-item decisions in addition to the four fractions. The expected Group 09 nominal calculation is `25 * (6/6 + 3/5 + 2*21/(24+26) + (8/8)*1) = 86.00`. The single-combination command calculates this value from the observation files. The default no-argument command additionally opens the published scorecard and verifies the results for all 70 combinations at all three settings. [Full Group 09 nominal trace](../validation/group09_nominal_score_trace.json)

## Reconstruct the nominal score

Let an item pass when its unrounded absolute error is at or below the tolerance. Add four fractions scaled by 25. Each domain represents a different inspection deliverable. The equal weights and cutoffs were chosen for this study. They carry no course grading or construction acceptance status.

Page 4 of the CIVL 7023 Project 1 requirements asks for a literature review, framework novelty and reasonable measurement performance evaluated through measurement error. This score supports the performance discussion. The literature and novelty arguments require their own evidence. See the [course evaluation report](Task1_Evaluation.docx).

| Domain | Calculation at nominal settings | Earned |
|---|---|---:|
| Room size | 6 of 6 length, width and height readings within 10 mm | 25.00 |
| Opening dimensions | 3 of 5 eligible field readings within 10 mm, with zero extra detections | 15.00 |
| Window face corners | 2 × 21 qualified windows / (24 true windows + 26 predictions) | 21.00 |
| Wall flatness | 8/8 field walls with an RMS result × panel-bias pass | 25.00 |
| **Total** | **25 + 15 + 21 + 25** | **86.00** |

### 1. Room size

M26 and M04 each supply three tape references. Divide the count of passing length, width and height items by six. The M26 signed differences (scan minus tape) were +3.96, +5.29 and −0.57 mm. The M04 differences were +3.99, +1.77 and +1.74 mm. All six pass at 10 mm. The M26 width exceeds the strict 5 mm cutoff.

### 2. Opening dimensions

For the archived trial the denominator is **5 + extra field windows**. The five expected items are two door widths, two door heights and the M26 wall-face window height. The protocol also describes a two-item penalty for each extra field door. The historical code verifies the two-door inventory and uses a shared door detector across recognition routes, so that additional term is always zero in these results. Reusing this score on a new dataset with extra or missing doors requires matching the new door inventory explicitly.

| Field item | Manual (mm) | Group 09 benchmark (mm) | Signed error (mm) | Within 10 mm |
|---|---:|---:|---:|---|
| M26 door width | 900 | 898.95 | −1.05 | Yes |
| M26 door height | 2180 | 2191.61 | +11.61 | No |
| M04 door width | 918 | 920.23 | +2.23 | Yes |
| M04 door height | 2316 | 2340.95 | +24.95 | No |
| M26 wall-face window height | 1736 | 1738.55 | +2.55 | Yes |

Their mean absolute error is 8.48 mm. Threshold scoring and MAE answer different questions. An 11 mm miss and a 25 mm miss both earn zero at a 10 mm cutoff. Use the underlying signed errors and MAE when the size of a miss matters.

### 3. Window detection and four-corner position

The controlled set contains four seeds for each of six positive wall conditions and four negative walls, giving 24 true windows across 28 scenes. The negative walls can contribute false positives. Match predictions one-to-one on the same wall at projected bounding-box intersection over union (IoU) of at least 0.50. IoU is the intersection area divided by the union area.

For each match, compute the 3D Euclidean distance from each predicted A–D face corner to its corresponding designed corner. A match qualifies only when the **largest** of its four errors is within tolerance. The score is **25 × 2 × qualified matches / (all true windows + all predicted windows)**. Missed, additional and inaccurately localized predictions reduce the fraction.

Group 09 matched all 24 true windows and produced two extra predictions. Detection alone gives 2 × 24 / 50 = 0.96. Three matches had at least one corner beyond 10 mm, so qualified-corner F1 is 2 × 21 / 50 = 0.84, worth 21 points. This assesses the wall-face corners. The study separately recorded a recessed width within 10 mm at the designed layer on 16 of 20 recessed examples, and four corners at the designed layer on 12 of 16 cases designed with four observable deep edges.

### 4. Wall RMS

Wall RMS is the square root of the mean squared orthogonal residual to the fitted reference plane, expressed in mm. The score is **25 × number of field walls returning a valid RMS / 8 × panel pass**. The known-relief panel supplies an independent true RMS of 2.127406 mm. Group 09 measured 2.245700 mm, giving absolute bias 0.118294 mm. The panel pass is 1 when this bias is within tolerance and 0 otherwise. A larger genuine surface deviation can increase RMS. Smoothing a real deviation away can reduce the score on the known panel.

All eight field walls returned an RMS. With panel bias ≤ 0.50 mm Group 09 earned 25 points. The manual M26 and M04 patches have no surveyed footprint vertices, so the eight-wall component measures availability. A claim of field accuracy would require a reference for the same footprint and a compatible fitting convention.

## Threshold sensitivity and scope

| Setting | Room / opening / four-corner tolerance (mm) | Panel bias tolerance (mm) | Group 09 |
|---|---:|---:|---:|
| Strict | 5 / 5 / 5 | 0.25 | 80.83 |
| Nominal | 10 / 10 / 10 | 0.50 | 86.00 |
| Relaxed | 20 / 20 / 20 | 1.00 | 91.00 |

The experiment sets 10 mm for dimensions and face corners and 0.50 mm for panel bias as the nominal working tolerances. The other two settings halve and double them to show sensitivity. Equal weighting gives each output domain one quarter of the score despite its different sample count. The project records these numbers as evaluation choices. Applying a contractual acceptance limit would require the applicable project tolerance and a comparable reference measurement.

The M26 tape width of 2375 mm has no recorded contact depth. Report the opening at D = 0 and the deeper candidate at its measured depth in separate columns. Agreement with one width alone cannot identify the tape contact location. Runtime, memory, deep-layer success, door error magnitude and each wall's RMS are separate diagnostics. A field sample of two rooms and a controlled synthetic suite support comparisons within this experiment. Report external accuracy only after testing independent rooms with surveyed matching features.

## Evidence and reproduction

From the repository root run `python experiments/joint_benchmark/verify_scores.py` to reproduce all 210 scores using the archived observations and thresholds. Run `python tests/check_group09.py` to verify the packaged Group 09 snapshot and pairing logic. [Frozen Group 09 observations](../references/group09_benchmark.json) · [All 70 score rows](../experiments/joint_benchmark/Combination_Scorecard.csv) · [Combination definitions](../experiments/joint_benchmark/Combination_Guide.csv) · [Evaluation protocol](../experiments/joint_benchmark/protocol.json)
