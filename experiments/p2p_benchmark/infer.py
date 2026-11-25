"""Run the released ScanNet++ XYZ EMA weights and keep per-sensor-row patch predictions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import warnings

import numpy as np
from scipy.spatial import cKDTree
import torch
from omegaconf import OmegaConf
import fpsample

from cuda_forward import Kernels


ROOM_HASH = {"M26":"a9b2b0c13d315314e106ecdbbc8e53acb693805dec8c6fb1c641f5a25dd48f91",
             "M04":"bbaa83cbd814c20b06c80e87f23c72bc7cbd5f07c57530ff67432dea6444568f"}
WEIGHT_HASH = "d8aceb0fbc871f4781c5948ef01a917ac1b3b50c46f81d2aaa31a8014424449d"
CONFIG_HASH = "96fbb99fccdd108e1265f3c5af216fdda8d27aa7f8f836f010fed0c70f782a6e"
PATCH = 4096
RADIUS_M = .30
STEPS = 5
SEED = 42


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False)+"\n",encoding="utf8")


def get_model(assets):
    authors = assets / "P2P-Bridge-main"
    sys.path.insert(0,str(authors))
    weight, opt = assets/"snpp_xyz.pth",assets/"opt.yaml"
    assert digest(weight)==WEIGHT_HASH and digest(opt)==CONFIG_HASH
    bindings = Kernels(authors,assets/"support/nvidia/cuda_nvrtc/bin/nvrtc64_120_0.dll")
    bindings.check_forward()
    bindings.install()
    from models.unet_pvc import PVCNN2Unet
    from models.p2pb import P2PB
    cfg = OmegaConf.load(opt)
    assert cfg.data.npoints == PATCH and cfg.data.use_rgb_features is False and cfg.data.point_features is None
    cfg.gpu = "cuda:0"
    cfg.local_rank = 0
    cfg.model.ema = False  # The inference backbone below is loaded directly from the exact EMA subtree.
    ckpt = torch.load(weight,map_location="cpu",weights_only=True,mmap=True)
    assert ckpt["step"]==100000
    prefix = "ema.ema_model."
    ema = {k[len(prefix):]:v for k,v in ckpt["model_state"].items() if k.startswith(prefix)}
    net = PVCNN2Unet(cfg)
    assert ema and set(ema) == set(net.state_dict())
    net.load_state_dict(ema,strict=True)
    count = len(ema)
    model = P2PB(cfg,net).cuda()
    model.eval()
    print(f"Strictly loaded {count} EMA tensors, {sum(p.numel() for p in net.parameters()):,} parameters, step 100000.",flush=True)
    return model, count


def farthest(xyz, n, start):
    return fpsample.bucket_fps_kdline_sampling(np.ascontiguousarray(xyz,dtype=np.float32),n,h=5,start_idx=int(start))


def plan_patches(raw):
    rng = np.random.RandomState(SEED)
    centers = farthest(raw,int(np.ceil(len(raw)/PATCH))*4,0)
    tree = cKDTree(raw)
    patches, seeds = [], []
    votes = np.zeros(len(raw),dtype=np.uint16)

    def add(ids):
        assert len(np.unique(ids)) == len(ids) and len(ids) <= PATCH
        patches.append(np.asarray(ids,dtype=np.int32))
        seeds.append(int(rng.randint(1,2**31-1)))
        votes[ids] += 1

    for center in centers:
        nearby = np.array(tree.query_ball_point(raw[center],RADIUS_M,return_sorted=True),dtype=np.int64)
        if len(nearby) < PATCH:
            add(nearby)
        else:
            for _ in range(len(nearby)//PATCH+1):
                subset = farthest(raw[nearby], PATCH, rng.randint(len(nearby)))
                add(nearby[subset])
    base_patches, missing_initially = len(patches),int((votes==0).sum())
    # Complete actual sensor-row coverage, including the final patch in each batch.
    # The stock room utility can fill uncovered entries from arbitrary donor rows.
    for center in np.flatnonzero(votes==0):
        if votes[center]:
            continue
        nearby = np.array(tree.query_ball_point(raw[center],RADIUS_M,return_sorted=True),dtype=np.int64)
        if len(nearby) > PATCH:
            required = nearby[votes[nearby] == 0]
            if len(required) >= PATCH:
                distance = np.sum((raw[required]-raw[center])**2,axis=1)
                nearby = required[np.argsort(distance,kind="stable")[:PATCH]]
            else:
                others = nearby[votes[nearby] > 0]
                n_fill = PATCH - len(required)
                take = farthest(raw[others],n_fill,rng.randint(len(others))) if len(others)>=32 else rng.choice(len(others),n_fill,replace=False)
                nearby = np.concatenate([required,others[take]])
        if center not in nearby:
            raise RuntimeError("Coverage patch lost its centre.")
        add(nearby)
    assert votes.min() >= 1
    meta = dict(initial_centers=len(centers),initial_patches=base_patches,uncovered_after_initial=missing_initially,
                supplementary_patches=len(patches)-base_patches,patches=len(patches),vote_min=int(votes.min()),
                vote_median=float(np.median(votes)),vote_max=int(votes.max()))
    return patches,seeds,votes,meta


def normalized(raw, indices, seed):
    points = raw[indices]
    if len(points) < PATCH:
        rng = np.random.RandomState(seed)
        fill = points[rng.randint(0,len(points),PATCH-len(points))].copy()
        fill += rng.normal(0,.01*np.linalg.norm(np.ptp(points,axis=0)),size=fill.shape)
        points = np.vstack((points,fill))
    center = points.mean(axis=0)
    centered = points - center
    scale = np.linalg.norm(centered,axis=1).max()
    if scale == 0:
        raise ValueError("Degenerate local patch with no recoverable spatial scale.")
    return (centered/scale).astype(np.float32),center,scale


@torch.inference_mode()
def predict(model, batch):
    x = torch.from_numpy(np.stack([p[0] for p in batch])).cuda().transpose(1,2)
    model.eval()
    out = model.sample(x_start=x, x_cond=None, steps=STEPS, log_count=1, verbose=False, use_ema=False)["x_pred"]
    y = out.transpose(1,2).cpu().numpy()
    assert np.isfinite(y).all() and y.shape == (len(batch),PATCH,3)
    centers = np.stack([p[1] for p in batch])
    scales = np.array([p[2] for p in batch])
    return y * scales[:,None,None] + centers[:,None,:]


def write_pcd(path, points):
    with path.open("wb") as handle:
        header = (f"# .PCD v0.7\nVERSION 0.7\nFIELDS x y z\nSIZE 8 8 8\nTYPE F F F\nCOUNT 1 1 1\n"
                  f"WIDTH {len(points)}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\nPOINTS {len(points)}\nDATA binary\n")
        handle.write(header.encode("ascii"))
        np.asarray(points,dtype="<f8").tofile(handle)


def infer_room(args, room, model, tensor_count):
    from wall_flatness.io import read_cloud
    source = args.scans/(room+".pcd")
    assert digest(source)==ROOM_HASH[room]
    raw = read_cloud(str(source))
    assert raw.shape[1]==3 and np.isfinite(raw).all()
    start=time.perf_counter()
    folder=args.work/"inputs"/room/"p2p"
    folder.mkdir(parents=True,exist_ok=True)
    chunks=folder/"batches"
    chunks.mkdir(exist_ok=True)
    patches,seeds,votes,meta=plan_patches(raw)
    plan_hash=hashlib.sha256()
    for ids,seed in zip(patches,seeds):
        plan_hash.update(np.array([len(ids),seed],dtype="<i8").tobytes())
        plan_hash.update(ids.astype("<i4").tobytes())
    code_hash=hashlib.sha256((digest(Path(__file__))+digest(Path(__file__).with_name("cuda_forward.py"))).encode()).hexdigest()
    identity=dict(weight_sha256=WEIGHT_HASH,config_sha256=CONFIG_HASH,code_sha256=code_hash,
                  source_sha256=ROOM_HASH[room],plan_sha256=plan_hash.hexdigest(),batch_size=args.batch_size,steps=STEPS)
    idfile=folder/"identity.json"
    if idfile.exists():
        assert json.loads(idfile.read_bytes())==identity, "Use a new work directory for changed settings."
    else:
        save_json(idfile,identity)
    print(f"{room} patch plan {meta}",flush=True)
    if args.smoke:
        t=time.perf_counter()
        batch=[normalized(raw,ids,seeds[i]) for i,ids in enumerate(patches[:args.batch_size])]
        pred=predict(model,batch)
        print(f"{room} {len(batch)} patches in {time.perf_counter()-t:.2f}s, max memory {torch.cuda.max_memory_allocated()/2**30:.2f} GiB.",
              "first patch median displacement mm",np.median(np.linalg.norm(pred[0,:len(patches[0])]-raw[patches[0]],axis=1))*1000, flush=True)
        return
    total=np.zeros_like(raw,dtype=float)
    n_batches=int(np.ceil(len(patches)/args.batch_size))
    for k, first in enumerate(range(0,len(patches),args.batch_size)):
        ids_range=range(first,min(first+args.batch_size,len(patches)))
        fn=chunks/f"{first:06d}.npy"
        if fn.exists():
            out=np.load(fn,allow_pickle=False)
        else:
            batch=[normalized(raw,patches[i],seeds[i]) for i in ids_range]
            out=predict(model,batch)
            tmp=chunks/f"{first:06d}.stage.npy"
            np.save(tmp,out,allow_pickle=False)
            os.replace(tmp,fn)
        assert out.shape==(len(ids_range),PATCH,3) and np.isfinite(out).all()
        for j,i in enumerate(ids_range):
            ids=patches[i]
            total[ids]+=out[j,:len(ids)]
        if k==0 or (k+1)%12==0 or k==n_batches-1:
            print(f"{room} {k+1}/{n_batches} batches, {time.perf_counter()-start:.0f}s",flush=True)
    denoised=total/votes[:,None]
    shift=np.linalg.norm(denoised-raw,axis=1)*1000
    write_pcd(folder/"input.pcd",denoised)
    np.save(folder/"source_rows.npy",np.arange(len(raw),dtype=np.int64),allow_pickle=False)
    np.save(folder/"votes.npy",votes,allow_pickle=False)
    info=dict(**identity,room=room,method="p2p",input_sha256=digest(folder/"input.pcd"),
              mapping_sha256=digest(folder/"source_rows.npy"),vote_sha256=digest(folder/"votes.npy"),
              preprocessing_seconds=time.perf_counter()-start,input_rows=len(raw),finite_rows=len(raw),retained_rows=len(raw),
              moved_over_1mm=int((shift>1).sum()),median_move_mm=float(np.median(shift)),p95_move_mm=float(np.quantile(shift,.95)),
              max_move_mm=float(shift.max()),mask_threshold_mm=None,ema_tensor_count=tensor_count,
              gpu=torch.cuda.get_device_name(),torch=torch.__version__,cuda=torch.version.cuda,**meta)
    save_json(folder/"input.json",info)
    print(f"Prepared {room}, median shift {info['median_move_mm']:.3f} mm, all {len(raw):,} rows predicted.",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("assets","framework","scans","work"):
        parser.add_argument("--"+name,required=True,type=Path)
    parser.add_argument("--rooms",nargs="+",choices=("M26","M04"),default=["M04","M26"])
    parser.add_argument("--batch-size",type=int,default=2)
    parser.add_argument("--smoke", action="store_true")
    args=parser.parse_args()
    sys.path.insert(0,str(args.framework.resolve()/"third_party"))
    torch.manual_seed(SEED)
    warnings.filterwarnings("ignore",category=FutureWarning,message=".*torch.cuda.amp.custom.*")
    model, keys=get_model(args.assets.resolve())
    for room in args.rooms:
        infer_room(args,room,model,keys)
