# Measurement and report inputs

| Input or table | Contract |
|---|---|
| Source cloud | Original N by 3 XYZ in metres. The two published course inputs are identified by SHA-256. |
| Transformed cloud | Finite K by 3 XYZ in the same frame and units. P2P-Bridge retains one indexed output for every original input. Binary masks return subsets. |
| Row map | An increasing K-vector of zero-based sensor rows stored in source_rows.npy. Map the native selected rows before retrieving sensor XYZ. |
| Neural support | votes.npy gives the number of genuine patch predictions per sensor row. Every row in the two evaluated scans received at least one vote. The input manifest records the checksum, movement, weights, patches and coverage. |
| dimensions.csv | Room, method, physical feature, measured mm, manual mm, signed difference and section height where applicable. Missing values remain empty. |
| windows.csv | M26 W01 face at D = 0 and the independently selected recessed candidate, both at that run's mid-height. Positive D points into the recess. The deep width is the median of supported middle-height slices. The tape contacts and depth are unavailable. |
| window_profile.csv | Per-method baseline wall, height, depth, middle-strip width and number of supported strips. Missing paired edges are marked by blank values. |
| wall_rms.csv | Run-coordinate native RMS, original-coordinate refit on exactly those selected sensor rows, survivor-matched comparison of fixed baseline supports, overlap, warnings and the relevant row-set hashes. All RMS values are in mm. |
| method_summary.csv | Per-treatment coverage, six room dimensions, six face-opening dimensions and five opening dimensions excluding the tape-depth-ambiguous window width. Each MAE and RMSE has a denominator count. |
| panel_control.csv | One synthetic vertical wall. Normal-axis error to the analytic surface and plane RMS on exactly 5,329 interior sensor rows are separate outcomes. |
| patch_audit.json and native_audit.json | Comparison with the authors' patch evaluation routine on the declared EMA evaluation path, and independent native membership and residual reproduction for each room and input treatment. |

The report renderer consumes the evidence directory. The original inspection program retains its existing replaceable RMS provider. A future integration should explicitly preserve the coordinate source, selected row IDs, dimensional section, window depth, wall identity and RMS provider in each reported result.
