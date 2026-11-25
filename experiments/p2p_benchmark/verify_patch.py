"""Compare the row adapter with the authors' denoise_patch_batch on identical genuine room patches."""
import argparse
import ast
import json
from pathlib import Path
import sys
from typing import Optional, Tuple

import numpy as np
import torch
from einops import rearrange
from ema_pytorch import EMA
from omegaconf import DictConfig
from scipy.spatial import cKDTree

from infer import PATCH, get_model, predict, save_json


def check(assets,framework,source,out):
    authors=assets/"P2P-Bridge-main"
    sys.path.insert(0,str(framework/"third_party"))
    from wall_flatness.io import read_cloud
    raw=read_cloud(str(source))
    tree=cKDTree(raw)
    targets=[len(raw)//3,2*len(raw)//3]
    ids=tree.query(raw[targets],k=PATCH)[1]
    pts=raw[ids]
    centers=pts.mean(axis=1)
    shifted=pts-centers[:,None]
    scales=np.linalg.norm(shifted,axis=-1).max(axis=1)
    prepared=[((s/scale).astype(np.float32),center,scale) for s,center,scale in zip(shifted,centers,scales)]
    model,_=get_model(assets)
    adapted=[predict(model,prepared) for _ in range(3)]
    state=torch.load(assets/"snpp_xyz.pth",weights_only=True,map_location="cpu",mmap=True)["model_state"]
    ema_state={k[4:]:v for k,v in state.items() if k.startswith("ema.")}
    for key,tensor in model.model.state_dict().items():
        assert torch.equal(tensor.cpu(),ema_state["ema_model."+key]),key
    model.ema=EMA(model.model,beta=.999)
    model.ema.cuda()
    # Match the declared inference mode for the released EMA network on both paths.
    model.ema.load_state_dict(ema_state,strict=True);model.ema.eval()
    tree_ast=ast.parse((authors/"denoise_room.py").read_text(encoding="utf8"))
    original=next(node for node in tree_ast.body if isinstance(node,ast.FunctionDef) and node.name=="denoise_patch_batch")
    subset=ast.Module(body=[original],type_ignores=[])
    names=dict(torch=torch,np=np,Tensor=torch.Tensor,DictConfig=DictConfig,Optional=Optional,Tuple=Tuple,rearrange=rearrange)
    exec(compile(subset,str(authors/"denoise_room.py"),"exec"),names)
    model.cfg.steps=5;model.cfg.use_ema=True
    reference=[names["denoise_patch_batch"](pts.copy(),model,model.cfg)[0] for _ in range(3)]
    def compare(a,b):
        difference=np.linalg.norm(a-b,axis=-1)*1000
        assert np.isfinite(difference).all()
        return dict(max_mm=float(difference.max()),mean_mm=float(difference.mean()),p99_mm=float(np.quantile(difference,.99)))
    cross=[compare(a,b) for a in adapted for b in reference]
    within_adapter=[compare(adapted[i],adapted[j]) for i,j in ((0,1),(1,2),(0,2))]
    within_author=[compare(reference[i],reference[j]) for i,j in ((0,1),(1,2),(0,2))]
    maximum=max(d["max_mm"] for d in cross)
    result=dict(room=source.stem,point_indices=targets,patch_points=PATCH,patches=len(targets),repeats_per_path=3,
                ema_wrapper_keys=len(ema_state),author_function="denoise_room.py:denoise_patch_batch",
                inference_mode="evaluation on both EMA paths",exact_ema_tensor_equality=True,
                all_cross_pairs=cross,within_adapter=within_adapter,within_author=within_author,
                max_vector_difference_mm=maximum,mean_vector_difference_mm=float(np.mean([d["mean_mm"] for d in cross])),
                worst_within_author_mm=max(d["max_mm"] for d in within_author),tolerance_mm=.02,
                all_cross_pairs_within_original_tolerance=maximum<.02)
    save_json(out,result)
    print("Three repeats per path. Max cross-path / within-author / within-adapter differences (mm):",
          maximum,result["worst_within_author_mm"],max(d["max_mm"] for d in within_adapter),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("assets","framework","source","out"):
        p.add_argument("--"+key,required=True,type=Path)
    a=p.parse_args();check(a.assets.resolve(),a.framework.resolve(),a.source.resolve(),a.out.resolve())
