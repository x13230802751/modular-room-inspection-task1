"""Seeded scanner-like wall samples with independent face and recessed geometry."""
import numpy as np

from geometry import WallView, edges, intersections, rect


def build(seed, condition):
    rng=np.random.default_rng(seed)
    wall_width,wall_height=rng.uniform(3.4,4.5),rng.uniform(2.65,3.15)
    width,height=rng.uniform(1.12,1.90),rng.uniform(.98,1.45)
    left=rng.uniform(.45,.88); sill=rng.uniform(.55,.82)
    base=rect(left,left+width,sill,sill+height)
    if condition in ("skew","partial","clutter","taper"):
        base+=rng.uniform(-.022,.022,(4,2))
    lines=edges(base)
    inset=rng.uniform(.027,.046)
    deep_lines=lines.copy()
    deep_lines[:,1]+=[inset,-inset,.022,-.022]
    deep=intersections(deep_lines)
    step=rng.uniform(.149,.218)
    pitch=rng.uniform(.009,.016)
    u,h=np.meshgrid(np.arange(0,wall_width,pitch),np.arange(0,wall_height,pitch))
    u=u.ravel()+rng.uniform(-.44*pitch,.44*pitch,u.size)
    h=h.ravel()+rng.uniform(-.44*pitch,.44*pitch,h.size)
    m,b=lines.T
    hole=(u>m[0]*h+b[0])&(u<m[1]*h+b[1])&(h>m[2]*u+b[2])&(h<m[3]*u+b[3])
    keep=np.ones(len(u),bool) if condition=="solid" else ~hole
    if condition=="partial":
        for x,y in base[[0,2]]:
            keep &= ~((abs(u-x)<.10)&(abs(h-y)<.13))
        keep &= rng.random(len(u))>.20
    face=np.c_[u[keep],h[keep],rng.normal(0,.0014,keep.sum())]
    samples=[face]
    window=condition not in ("solid","blind_patch")
    if window and condition!="flush":
        for side in range(4):
            # The partial case has no recorded top or sill at the recessed frame.
            depths=np.arange(.010,.34,.006)
            start,end=(base[:,1].min(),base[:,1].max()) if side<2 else (base[:,0].min(),base[:,0].max())
            along,d=np.meshgrid(np.arange(start+.012,end-.01,pitch),depths)
            along,d=along.ravel(),d.ravel()
            along+=rng.normal(0,.0015,len(d));d+=rng.normal(0,.0009,len(d))
            which=(d>=step)
            across=m[side]*along+np.where(which,deep_lines[side,1],b[side])+rng.normal(0,.0008,len(d))
            if condition=="taper":
                across+=np.where(which,0.,d*(.15 if side in (0,2) else -.15))
            use=(~which if condition=="partial" and side>=2 else np.ones(len(d),bool))
            if side<2:
                use &= (along>=np.where(which,deep_lines[2,0]*across+deep_lines[2,1],m[2]*across+b[2])) & (along<=np.where(which,deep_lines[3,0]*across+deep_lines[3,1],m[3]*across+b[3]))
                samples.append(np.c_[across[use],along[use],d[use]])
            else:
                use &= (along>=np.where(which,deep_lines[0,0]*across+deep_lines[0,1],m[0]*across+b[0])) & (along<=np.where(which,deep_lines[1,0]*across+deep_lines[1,1],m[1]*across+b[1]))
                samples.append(np.c_[along[use],across[use],d[use]])
        if condition=="clutter":
            hh=np.arange(sill,sill+height,.011)
            samples.append(np.c_[np.full_like(hh,left+.52*width)+rng.normal(0,.002,len(hh)),hh,rng.normal(0,.002,len(hh))])
    all_samples=np.vstack(samples)
    rng.shuffle(all_samples)
    theta=rng.uniform(0,2*np.pi)
    normal=np.array([np.cos(theta),np.sin(theta),0.]); up=np.array([0.,0.,1.])
    axis=np.cross(normal,up); centre=rng.uniform(-7,7,3)
    def world(uv, depth):
        return centre+uv[:,0,None]*axis+uv[:,1,None]*up-np.asarray(depth).reshape(-1,1)*normal
    xyz=world(all_samples[:,:2],all_samples[:,2])
    corners=[{"xyz_m":p.tolist()} for p in world(rect(0,wall_width,0,wall_height),0)]
    wall={"id":"W01","plane_center_m":centre.tolist(),"plane_normal":normal.tolist()}
    floor={"center_m":centre.tolist(),"normal":up.tolist()}
    view=WallView(f"{condition}_{seed}",xyz,wall,floor,np.arange(len(xyz)),corners)
    truth=[] if not window else [{"face":base,"deep":deep,"step_m":step,
                                  "has_recess":condition!="flush","four_deep_observed":condition not in ("partial","flush")}]
    return view,truth
