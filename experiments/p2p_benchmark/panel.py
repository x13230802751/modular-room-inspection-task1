"""A vertical panel of known relief. All ten treatments see the same finite XYZ and known row IDs."""
import argparse
import csv
import importlib.util
from pathlib import Path
import sys

import numpy as np
import torch

from infer import get_model, normalized, plan_patches, predict


def filters_at(folder):
    spec=importlib.util.spec_from_file_location(folder.name+"_filters",folder/"filters.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rms(p):
    q=p-p.mean(axis=0)
    return float(np.linalg.svd(q,compute_uv=False)[-1]*1000/np.sqrt(len(q)))


def run(assets, destination):
    here=Path(__file__).resolve().parent
    methods = [(key,filters_at(here/"controls/classical")) for key in ("raw","radius","sor","gaussian","bilateral","sor_bilateral")]
    methods += [(key,filters_at(here/"controls/cylindrical")) for key in ("cylinder12","cylinder20","radius_cylinder12")]
    x,z=(v.ravel() for v in np.meshgrid(np.arange(81)*.01,np.arange(81)*.01))
    true_y=lambda at: .003*np.sin(2*np.pi*at/.060)
    surface=np.column_stack((x,true_y(x),z))
    noisy=surface.copy()
    noisy[:,1]+=np.random.default_rng(7023).normal(0,.0007,len(x))
    ox,oz=(v.ravel() for v in np.meshgrid(.10+np.arange(6)*.11,.10+np.arange(6)*.11))
    cloud=np.vstack((noisy,np.column_stack((ox, np.full(36,.12), oz))))
    interior=(x>=.04)&(x<=.76)&(z>=.04)&(z<=.76)
    outputs=[]
    for method,module in methods:
        p,ids,_=module.apply_filter(cloud,method)
        outputs.append((method,p,ids))
    model,_=get_model(assets)
    ids,seeds,votes,meta=plan_patches(cloud)
    total=np.zeros_like(cloud)
    for i in range(0,len(ids),4):
        indices=range(i,min(i+4,len(ids)))
        predicted=predict(model,[normalized(cloud,ids[k],seeds[k]) for k in indices])
        for batch,k in enumerate(indices):
            total[ids[k]]+=predicted[batch,:len(ids[k])]
    outputs.append(("p2p",total/votes[:,None],np.arange(len(cloud))))
    rows=[]
    for method,p,ids in outputs:
        use=ids<len(surface)
        use[use]&=interior[ids[use]]
        a=p[use]
        target=rms(surface[ids[use]])
        measured=rms(a)
        assert len(a)==5329
        rows.append(dict(method=method,orientation="vertical XZ, relief along Y",seed=7023,
                         noise_sigma_mm=.7,amplitude_mm=3,wavelength_mm=60,interior_rows=len(a),
                         true_rms_mm=target,measured_rms_mm=measured,flatness_bias_mm=measured-target,
                         surface_y_rmse_mm=float(np.mean(((a[:,1]-true_y(a[:,0]))*1000)**2)**.5),
                         isolated_rows_retained=int(np.sum(ids>=len(surface)))))
    destination.parent.mkdir(exist_ok=True,parents=True)
    with destination.open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    print("Controlled vertical panel",[(r["method"],round(r["measured_rms_mm"],3)) for r in rows],meta)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assets",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args();torch.manual_seed(42);run(a.assets.resolve(),a.out.resolve())
