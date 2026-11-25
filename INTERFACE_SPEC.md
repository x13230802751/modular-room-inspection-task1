# Measurement and preprocessing interfaces

The CLI and the local browser call the same inspection function. Profile API v1, report API v1 and saved summary format 2 remain readable. The preprocessing record is an additive interface, version 1.

## Input selection

| Entry | Contract |
|---|---|
| CLI | No mode flags or `--paired-review` requests the paired workflow. Explicit `--preprocess raw` or `--preprocess radius` requests a single treatment. `--window-review` selects the historical same-treatment check. |
| Local browser | `POST /inspect?name=M26.pcd&unit=m&up=z&mode=paired` carries one file as the request body and the page token in `X-Task1-Token`. The response contains local Word and HTML URLs. Requests without any selection choose paired mode. Old requests with preprocessing or a review flag retain their historical behavior. |
| Python | `inspect(source, output, unit, up, node, algorithms=None, *, preprocess=None, window_review=False, paired_review=None)`. Set `paired_review=True` for paired mode or `False` for a single treatment. The CLI stages measurement and publication in a new directory. |
| Stage input | An N × 3 array in metres in source-row order. Every stage uses the supplied finite coordinates. Source-defined invalid records and excluded records occupy their original positions. The latter have NaN coordinates in the stage array. |
| Optional context | Providers that request `context` receive source path, source unit, up vector, original file digest, original record count and `preprocessing_method`. Use the supplied stage array for measurements. The source path identifies the uploaded file. |

The radius rule counts distinct finite records, including coincident records, within an inclusive 20 mm sphere. It requires four other records. The retained points preserve their original coordinates. In single-treatment mode the same selection supplies every stage. In paired mode the raw pass supplies all official outputs and the selected radius points supply independent window proposals and corner fits.

## Independent Group 09 review

The secondary pass uses fixed native wall discovery, enclosure intersections, profile proposals and reveal-plane fitting. A custom algorithm profile controls the official pass and report writer. For each supported window, the secondary pass estimates its own wall, A–D polygon, cut elevations and recessed depth band. A side without sufficient reveal points inherits its profile fit. A deep four-corner set requires all four supported lines in the representative 12 mm slice.

The official-to-review association is one-to-one in original coordinates. Inward normals must agree within 10 degrees, centre separation must be at most 350 mm, and normal separation at both planes must be at most 120 mm. Projected box IoU must be at least 0.50. The assignment maximizes feasible matches then total IoU. Unmatched candidates appear as `raw_only` or `review_only`. Wall and window IDs belong to their own branches.

The descriptor in `summary.group09_review` binds `group09/result.json` to the source by SHA-256. The branch holds method fingerprints, its own selection, detector row map when needed, floor, wall frames, proposals, side evidence, fitted XYZ corners, face/deep readings, pairing and a historical benchmark snapshot. Status is `complete`, `limited` (incomplete enclosure) or `unavailable` (secondary measurement failed). A complete search may return zero windows. See the [branch schema](schemas/group09_review.schema.json) and [benchmark interpretation](README.md#offline-method-benchmark).

## Geometry and providers

| Stage | Default callable | Input and output |
|---|---|---|
| Wall detection | `extensions.native_support:walls` | Accepts metre points and configuration. Returns floor, wall candidates, plane supports, native configuration and build provenance. The historical field `expanded_indices` holds exact source-row wall membership. |
| Structural corners | `room_geometry:room_boundaries` | Accepts points, discovery and configuration. Returns walls, inside source rows, ceiling, A–D corners and their nearest wall records, room dimensions and warnings. |
| Openings | `openings:profile_candidates` | Accepts points, inside source rows, wall, floor, corners and Node executable. Returns opening candidates and diagnostics. The local horizontal axis follows the inward wall normal crossed with the upward floor normal. The pipeline adds fitted world coordinates and sections. |
| Flatness | `extensions.native_support:measure` | Accepts eligible XYZ and a four-corner ROI in metres. Returns subset-local indices, signed residuals in mm, fitted plane, coverage, status and warnings. The wrapper maps the subset indices to original rows. |
| Reporting | `reporting:standard_reports` | Accepts the output directory, saved summary and window sections. Writes English DOCX and HTML from the supplied measurements. |

The default whole-wall region uses the structural corners and excludes detected opening footprints. The native SVD provider uses a two-dimensional footprint with `slab_half_thickness_mm=null`. The default opening fit uses a wall-face band of ±8 mm. Its recessed depth slices are 12 mm thick. The 50 mm corner warning measures distance to an assigned observation. These parameters describe different geometric operations. See the [algorithm profile schema](schemas/algorithm_profile.schema.json) and [RMS and report contract](REPORT_API.md).

## Saved data and point numbering

For a single-treatment run, CLI flag `--window-review`, Python keyword `window_review=True` or HTTP parameter `window_review=1` enables the older same-selection check. It writes `summary.window_corner_review` with method fingerprints, preprocessing identity and one entry per primary window. A run with zero primary windows stores an empty list. [Single-treatment review schema](schemas/window_corner_review.schema.json)

Each evaluated entry has a face check at D = 0 and a deep check at its own `slice_mm`. XYZ coordinates are in original scanner metres. In the wall elevation the four array entries are lower left, lower right, upper right and upper left. `width_level_m` measures height above the fitted floor. `height_level_u_m` gives the along-wall coordinate of the vertical section. Width and height use mm. The face lists the number of sides supported by reveal-plane fits, from zero to four. A deep width layer can exist without four usable deep sides. In that case the primary paired-jamb width stays in `window_sections.json` and the review's four-corner dimensions are null. Edge support IDs index the eligible original rows from zero.

| File or field | Interpretation |
|---|---|
| `summary.json → cloud` | Original filename, SHA-256 of the uploaded file bytes or uncompressed archive member, input unit, original row count and original invalid-row count. This identity also selects available course references after measurement. |
| `summary.json → preprocessing` | Method, parameter object, input, finite, retained and removed-finite counts, coordinate source, row-map filename and row-selection digest. Counts satisfy `finite_rows = retained_rows + removed_finite_rows`. [Schema](schemas/preprocessing.schema.json) |
| `native_supports.txt` | Unmodified native detector output. Its indices index the retained finite records in input order. To recover source rows, index `detector_source_rows.npz["source_rows"]` with those native indices. A null `source_rows_file` denotes the identity mapping. |
| `source_rows_sha256` | SHA-256 of the retained original row numbers, encoded as contiguous little-endian signed 64-bit integers in ascending order, without a NumPy header. |
| `wall_points.npz`, per-wall `residuals.npz`, corners, window endpoints and depth-profile CSVs | Public point IDs already refer to zero-based original scan rows. Residual arrays contain the provider's signed distances in mm. The original IDs also index the unmodified scan after a radius run. |
| `window_sections.json` | Fitted face at D = 0, separate recessed candidate, height above the floor, evidence status and observed endpoints where available. Positive D points into the opening. The shallow-section CSV labels its opposite sign convention explicitly. The original v1.0 file layout is preserved. Its byte digest in `summary.window_sections_sha256` binds the file to the recorded input selection. [Schema](schemas/window_sections.schema.json) |
| `report_manifest.json` | Source, summary and window-file digests, preprocessing record, RMS provider, report writer and output filenames. Older saved reports display “Input preprocessing was not recorded” when the record is absent. |

The native top-level `filter` field is `none` for raw input and `radius` for radius-selected input. Read `preprocessing` for the scope of the selection and `algorithms.stages.rms` for the actual RMS provider. The profile's discovery settings and the native detector's configuration remain in distinct fields. A custom provider should propagate unavailable measurements and preserve source-row identity.
