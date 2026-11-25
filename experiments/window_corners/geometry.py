"""Wall coordinates, layered proposals and independently supported edge fits."""
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.optimize import least_squares
from scipy.spatial import cKDTree

from openings import wall_profile
from room_geometry import section_axis

PROTOCOL = json.loads(Path(__file__).with_name("protocol.json").read_bytes())
CFG = PROTOCOL["geometry"]
REVEAL = PROTOCOL["reveal_fit"]
GRID = CFG["grid_mm"]/1000
SEARCH = CFG["line_search_band_mm"]/1000


@dataclass
class WallView:
    name: str
    xyz: np.ndarray
    wall: dict
    floor: dict
    inside: np.ndarray
    corners: list

    def __post_init__(self):
        self.c = np.asarray(self.wall["plane_center_m"])
        self.n = np.asarray(self.wall["plane_normal"])
        self.f = np.asarray(self.floor["center_m"])
        self.z = np.asarray(self.floor["normal"])
        self.axis = section_axis(self.wall,self.floor)
        self.lift = (self.z-(self.z@self.n)*self.n)/(1-(self.z@self.n)**2)
        vertices = np.array([c["xyz_m"] for c in self.corners])
        self.u = (self.xyz-self.c)@self.axis
        self.h = (self.xyz-self.f)@self.z
        self.d = -(self.xyz-self.c)@self.n
        ul = (vertices-self.c)@self.axis
        hl = (vertices-self.f)@self.z
        self.bounds = np.array([ul.min(),ul.max(),hl.min(),hl.max()])
        profile = wall_profile(self.xyz,self.inside,self.wall,self.floor,vertices.tolist())
        self.face_ids = profile[:,2].astype(np.int64)
        self.face_uv = profile[:,:2]
        self.tree = cKDTree(self.xyz[self.face_ids]) if len(self.face_ids) else None

    def world(self, corners, depth=0.):
        p = np.asarray(corners)
        origin = self.c-depth*self.n
        return origin + p[:,0,None]*self.axis + (p[:,1]-(origin-self.f)@self.z)[:,None]*self.lift


def rect(left,right,bottom,top):
    return np.array([[left,bottom],[right,bottom],[right,top],[left,top]])


def runs(mask):
    transitions=np.diff(np.r_[False,mask,False].astype(int))
    return list(zip(np.flatnonzero(transitions==1),np.flatnonzero(transitions==-1)))


def propose(view):
    u,h=view.face_uv.T
    lo,hi,b,t=view.bounds
    nx=int(np.ceil((hi-lo)/GRID))
    if not len(u) or nx<2 or t-b<1:
        return []
    valid=(u>=lo)&(u<hi)&(h>=b+.04)&(h<t-.04)
    ix=np.floor((u[valid]-lo)/GRID).astype(int)
    bands=np.floor(9*(h[valid]-b-.04)/(t-b-.08)).astype(int).clip(0,8)
    sub=np.zeros((9,nx),bool)
    sub[bands,ix]=True
    solid=sub.reshape(3,3,nx).any(axis=1).all(axis=0)
    boxes=[]
    for i,j in runs(~solid):
        left,right=lo+i*GRID,lo+j*GRID
        if right-left<CFG["minimum_width_m"] or i==0 or j==nx:
            continue
        # Estimate the dominant internal void from occupancy across the width.
        central=(u>left+.12*(right-left))&(u<right-.12*(right-left))
        bins=np.arange(b,t+GRID,GRID)
        counts=np.histogram(h[central],bins)[0]
        if counts.max(initial=0)==0:
            continue
        limit=max(1,.08*np.percentile(counts[counts>0],75))
        seen=counts>limit
        for a,e in runs(~seen):
            bottom,top=bins[a],bins[e]
            if (bottom-b<CFG["minimum_sill_m"] or top-bottom<CFG["minimum_height_m"]
                    or t-top<.045 or seen[:a].sum()<4 or seen[e:].sum()<2):
                continue
            boxes.append(rect(left,right,bottom,top))
    return boxes


def edges(quad):
    """Each edge maps an along-edge coordinate to its across-edge coordinate."""
    q=np.asarray(quad)
    sides=[]
    for a,b,vertical in ((0,3,True),(1,2,True),(0,1,False),(3,2,False)):
        xy=q[[a,b]][:,::-1] if vertical else q[[a,b]]
        m=(xy[1,1]-xy[0,1])/(xy[1,0]-xy[0,0])
        sides.append((m,xy[0,1]-m*xy[0,0]))
    return np.asarray(sides)


def intersections(lines):
    out=[]
    for i,j in ((0,2),(1,2),(1,3),(0,3)):
        m,b=lines[i]
        k,c=lines[j]
        if abs(1-m*k)<.33:
            return None
        x=(m*c+b)/(1-m*k)
        out.append([x,k*x+c])
    q=np.asarray(out)
    if min(q[1,0]-q[0,0],q[2,0]-q[3,0],q[2,1]-q[1,1],q[3,1]-q[0,1])<=0:
        return None
    return q


def dimensions(quad, height, horizontal):
    m,b=edges(quad).T
    return ((m[1]-m[0])*height+b[1]-b[0])*1000, ((m[3]-m[2])*horizontal+b[3]-b[2])*1000


def raw_refit(view, seed, ids=None):
    ids=view.face_ids if ids is None else ids
    uv=np.c_[view.u[ids],view.h[ids]]
    sides=edges(seed)
    lines=[]; audit=[]
    for side,(m,b) in enumerate(sides):
        along,across=uv[:,1-side//2],uv[:,side//2]
        start,end=np.min(seed[:,1-side//2]),np.max(seed[:,1-side//2])
        length=end-start
        close=np.flatnonzero((abs(across-(m*along+b))<=SEARCH)&(along>start)&(along<end))
        samples=[]
        for centre in np.linspace(start+.09*length,end-.09*length,CFG["strip_count"]):
            pool=close[abs(along[close]-centre)<=min(.022,.40*length/CFG["strip_count"])]
            if len(pool)<3:
                continue
            order=pool[np.argsort(across[pool]-m*along[pool])]
            if side in (0,2):
                order=order[::-1]
            vals=(across[order]-m*along[order])
            dense=np.flatnonzero(abs(vals[:-2]-vals[2:])<=.020)
            if len(dense):
                samples.append(int(order[dense[0]]))
        audit.append({"strips":len(samples)})
        if len(samples)<CFG["minimum_supported_strips"]:
            continue
        x,y=along[samples],across[samples]
        mid=x.mean()
        result=least_squares(lambda a: y-(a[0]*(x-mid)+a[1]),[m,m*mid+b],
                             loss="soft_l1",f_scale=.003)
        a,c=result.x
        err=np.abs(y-(a*(x-mid)+c))
        good=err<=CFG["maximum_residual_mm"]/1000
        if (good.sum()<CFG["minimum_supported_strips"] or np.ptp(x[good])<CFG["minimum_edge_span_fraction"]*length
                or abs(a)>.30):
            continue
        audit[-1].update(source_rows=ids[np.array(samples)[good]].tolist(),median_residual_mm=float(np.median(err)*1000))
        lines.append((a,c-a*mid))
    return (intersections(lines) if len(lines)==4 else None),audit


def raster(view):
    lo,hi,b,t=view.bounds
    pitch=max(CFG["raster_mm"]/1000,(hi-lo)/1600,(t-b)/1600)
    margin=.10
    x0,y0=lo-margin,t+margin
    shape=(int(np.ceil((t-b+2*margin)/pitch)),int(np.ceil((hi-lo+2*margin)/pitch)))
    u,h=view.face_uv.T
    col=np.floor((u-x0)/pitch).astype(int); row=np.floor((y0-h)/pitch).astype(int)
    valid=(row>=0)&(row<shape[0])&(col>=0)&(col<shape[1])
    occupied=np.zeros(shape,bool)
    occupied[row[valid],col[valid]]=True
    dist=ndimage.distance_transform_edt(~occupied)*pitch
    image=np.rint(255*np.clip((.026-dist)/.018,0,1)).astype("uint8")
    return image,np.array([x0,y0]),pitch


def reveal_fit(view,seed,settings):
    """Intersect each supported reveal plane with D=0, retaining original edge fits on abstention."""
    lines=edges(seed)
    details=[]
    dmin,dmax=np.array(settings["fit_depth_mm"])/1000
    near=np.flatnonzero((view.d>=dmin)&(view.d<=dmax))
    for side,(m,b) in enumerate(lines.copy()):
        along,across=(view.h,view.u) if side<2 else (view.u,view.h)
        low,high=seed[:,1-side//2].min(),seed[:,1-side//2].max()
        length=high-low
        ids=near[(abs(across[near]-(m*along[near]+b))<settings["source_band_mm"]/1000)
                 &(along[near]>low+.08*length)&(along[near]<high-.08*length)]
        diag={"edge":("left","right","bottom","top")[side],"status":"retained_profile_edge","rows_tested":len(ids)}
        details.append(diag)
        if not len(ids):
            continue
        nx,nd=settings["bins_along_edge"],settings["bins_in_depth"]
        ix=np.floor(nx*(along[ids]-low)/length).astype(int).clip(0,nx-1)
        iz=np.floor(nd*(view.d[ids]-dmin)/(dmax-dmin)).astype(int).clip(0,nd-1)
        cell=ix*nd+iz
        order=np.lexsort((across[ids]-m*along[ids],cell))
        values,first,count=np.unique(cell[order],return_index=True,return_counts=True)
        chosen=ids[order[first+count//2]]
        # One observed return per occupied cell prevents dense strips dominating the fit.
        x=along[chosen]-(low+high)/2; d=view.d[chosen]; y=across[chosen]
        A=np.c_[x,d,np.ones(len(x))]
        test=(values//nd)%4==1
        train=np.flatnonzero(~test)
        if len(chosen)<settings["minimum_support_cells"] or len(train)<3 or test.sum()<6:
            continue
        rng=np.random.default_rng(settings["seed"])
        winning=np.zeros(len(train),bool)
        for _ in range(settings["trials"]):
            trial=rng.choice(train,3,replace=False)
            if abs(np.linalg.det(A[trial]))<.0003:
                continue
            coeff=np.linalg.solve(A[trial],y[trial])
            if abs(coeff[0])>.3 or abs(coeff[1])>.6:
                continue
            on=abs(A[train]@coeff-y[train])<=settings["inlier_mm"]/1000
            if on.sum()>winning.sum():
                winning=on
        if winning.mean()<settings["minimum_fraction"]:
            continue
        coeff=np.linalg.lstsq(A[train[winning]],y[train[winning]],rcond=None)[0]
        err=abs(A@coeff-y)
        good=err<=settings["inlier_mm"]/1000
        diag.update(heldout_fraction=float(good[test].mean()),cells=len(chosen))
        if (good[test].mean()<settings["minimum_fraction"] or len(np.unique(values[good]//nd))<9
                or d[good].min()>settings["require_near_depth_mm"]/1000 or d[good].max()<settings["require_far_depth_mm"]/1000):
            continue
        a,tilt,c=np.linalg.lstsq(A[good],y[good],rcond=None)[0]
        intercept=c-a*(low+high)/2
        shift=abs((a-m)*np.array([low,high])+intercept-b).max()
        if shift>settings["max_face_shift_mm"]/1000:
            continue
        lines[side]=[a,intercept]
        diag.update(status="reveal_plane",source_rows=chosen[good].tolist(),
                    fitted_depth_slope=float(tilt),max_face_shift_mm=float(shift*1000))
    q=intersections(lines)
    if q is None:
        return seed,[dict(d,status="retained_profile_edge") for d in details]
    return q,details


def select_lines(segments,quad):
    if not len(segments):
        return None
    chosen=[]
    for side,(m,b) in enumerate(edges(quad)):
        x=segments[:,:,1-side//2]; y=segments[:,:,side//2]
        low,high=quad[:,1-side//2].min(),quad[:,1-side//2].max()
        dx=x[:,1]-x[:,0]; dy=y[:,1]-y[:,0]
        slope=np.divide(dy,dx,out=np.full(len(x),np.inf),where=abs(dx)>1e-8)
        overlap=np.minimum(x.max(1),high)-np.maximum(x.min(1),low)
        error=np.max(abs(y-(m*x+b)),axis=1)
        ok=np.flatnonzero((overlap>=.42*(high-low))&(error<=SEARCH)&(abs(slope)<.30))
        if not len(ok):
            return None
        cost=error[ok]/SEARCH+.35*(1-np.clip(overlap[ok]/(high-low),0,1))
        i=ok[np.argmin(cost)]
        chosen.append((slope[i],y[i,0]-slope[i]*x[i,0]))
    return intersections(chosen)
