# Reproduce the multi-filter room comparison

This experiment evaluates the released P2P-Bridge ScanNet++ XYZ network alongside nine deterministic input treatments. The conventional runs in this review came from the two prior course experiments. Their input, row-map, filter and protocol hashes were checked, and their measurement tables and native audits were recomputed together with the new P2P runs. Raw and radius inputs were subsequently integrated into the inspection application. P2P-Bridge continues in this separate experiment. The commands below reproduce the historical study with its pinned framework revision. [Experiment settings](protocol.json) · [Findings and evidence](FINDINGS.md)

## Required inputs

* A clean integrated inspection checkout at revision a7edfe5d75596f72f6b060d7ff19d4e6324376e4, its native binaries, the DLLs required by those binaries and Node.js. [Framework](https://github.com/x13230802751/room-inspection-integrated/tree/a7edfe5d75596f72f6b060d7ff19d4e6324376e4)
* The authorized M26.pcd and M04.pcd, in metres, Z up. Input SHA-256 values are checked against the manual course registry. Keep the scans in SCANS and use separate work folders outside the framework and SCANS.
* The P2P-Bridge author source at revision eb26f07326134839bdc32370cb40fee941d183c9, extracted into ASSETS/P2P-Bridge-main. [Author code](https://github.com/matvogel/P2P-Bridge/tree/eb26f07326134839bdc32370cb40fee941d183c9)
* The released step_100000.pth and opt.yaml from PVDL_SNPP_XYZ. Put them at ASSETS/snpp_xyz.pth and ASSETS/opt.yaml. Both SHA-256 values are in protocol.json. The inference loader uses tensor-only deserialization and strict EMA state loading. [Official weight folder](https://drive.google.com/drive/folders/1jRmBHZssY1zwnqLIlDd7kXJNm2bDA4CN)

## Environment

The tested model environment was 64-bit Windows with Python 3.12, CUDA-enabled PyTorch 2.8.0+cu128, an NVIDIA RTX 5060 Laptop GPU, NumPy, SciPy, fpsample 1.0.2, einops 0.7.0, ema-pytorch 0.4.2, beartype 0.18.5, OmegaConf 2.3.0, tqdm and loguru. The renderer additionally uses python-docx and Matplotlib. Install the upstream framework dependencies and prepare its two native programs as described in its README. Add the native DLL directory and Node.js to PATH or set TASK1_NODE to the Node executable.

The Windows operator loader expects NVIDIA's nvidia-cuda-nvrtc-cu12 12.8.93 wheel under ASSETS/support. This provides support/nvidia/cuda_nvrtc/bin/nvrtc64_120_0.dll. Add this bin directory and the installed torch/lib directory to PATH. Include ASSETS/support in PYTHONPATH if required by the local Python installation. On the tested Windows machine, the NVIDIA driver supported compute capability 12.0.

## Full run

Run from the folder containing this README. Replace the capitalized paths. CLASSICAL, CYLINDRICAL and NEURAL are independent local working directories. If the previous verified deterministic runs are available, supply their existing working directories and begin at the inference command.

```shell
python controls/classical/benchmark.py all --repo FRAMEWORK --cloud-dir SCANS --work CLASSICAL --jobs 2
python controls/cylindrical/benchmark.py all --repo FRAMEWORK --cloud-dir SCANS --work CYLINDRICAL --jobs 2
python infer.py --assets ASSETS --framework FRAMEWORK --scans SCANS --work NEURAL --rooms M04 M26 --batch-size 4
python measurements.py inspect --repo FRAMEWORK --cloud-dir SCANS --work NEURAL --rooms M04 M26
python measurements.py analyse --repo FRAMEWORK --cloud-dir SCANS --work NEURAL --classical CLASSICAL --cylindrical CYLINDRICAL --out EVIDENCE
python panel.py --assets ASSETS --out EVIDENCE/panel_control.csv
python verify_patch.py --assets ASSETS --framework FRAMEWORK --source SCANS/M04.pcd --out EVIDENCE/patch_audit.json
python report.py --repo FRAMEWORK --evidence EVIDENCE --out REPORT
```

Inference saves completed batch predictions and a run identity. Retry the same command to reuse matching completed batches after interruption. Use a fresh work directory after changing any inference parameter or implementation. The identity includes the source scan, weights, config, patch plan, code and batch size. We tested batch size four, full precision floats for the tensors and five bridge steps with the EMA network in evaluation mode.

## Point identity and independent checks

The network uses the original authors' forward CUDA kernel bodies, compiled with NVRTC. Its neighbourhood search and feature projection operators pass small known-input checks. On two genuine room patches verify_patch.py independently wraps the official EMA state, invokes the authors' denoise_patch_batch function in evaluation mode, and checks the maximum difference against the room adapter.

Each patch input has an index for every real sensor point. Padding duplicates with jitter supply context in short patches and are excluded from voting. Predictions are returned to metres and averaged for the same sensor row. Supplemental local patches predict rows missing after the usual coverage pass. This keeps the relationship needed to refit the RMS plane on original coordinates. The adapter iterates complete batches and avoids the stock utility's random replacement of unvisited rows. The author model, EMA weights and diffusion equations are retained. [Room inference source](https://github.com/matvogel/P2P-Bridge/blob/eb26f07326134839bdc32370cb40fee941d183c9/denoise_room.py)

The compact course review includes results and digests. The room scans, transformed clouds, batch predictions and pretrained weights must be obtained or generated separately. The result file definitions are in the accompanying interface. [Interface](INTERFACE.md)
