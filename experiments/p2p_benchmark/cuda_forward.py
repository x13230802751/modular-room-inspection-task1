"""Load the authors' forward CUDA kernels with NVRTC on Windows. Inputs are PyTorch CUDA tensors."""
import ctypes as ct
from pathlib import Path
import re
import sys
import types

import numpy as np
import torch


KERNELS = {
    "pvcnn_sampling_gpu.cu": ("furthest_point_sampling_kernel",),
    "pvcnn_ball_query_gpu.cu": ("ball_query_kernel",),
    "pvcnn_grouping_gpu.cu": ("grouping_kernel",),
    "vox_gpu.cu": ("grid_stats_kernel","avg_voxelize_kernel"),
    "pvcnn_neighbor_interpolate_gpu.cu": ("three_nearest_neighbors_kernel","three_nearest_neighbors_interpolate_kernel"),
    "trilinear_devox_gpu.cu": ("trilinear_devoxelize_kernel",),
}


def kernel_source(folder):
    parts = []
    for filename, names in KERNELS.items():
        code = (folder / filename).read_text(encoding="utf8")
        for name in names:
            start = re.search(r"__global__\s+void\s+" + name + r"\s*\(", code).start()
            i = code.index("{", start)
            depth = 1
            end = i + 1
            while depth:
                depth += (code[end] == "{") - (code[end] == "}")
                end += 1
            parts.append('extern "C" ' + code[start:end])
    return "\n".join(parts)


def threads(n):
    return min(512, 1 << (int(n).bit_length()-1))


def block(x,y):
    tx = threads(x)
    return (tx, min(threads(y),512//tx),1)


class Kernels:
    def __init__(self, repo, nvrtc_path):
        torch.cuda.init()
        torch.empty(1, device="cuda")
        driver = self.driver = ct.WinDLL("nvcuda.dll")
        rtc = ct.WinDLL(str(nvrtc_path))
        code = kernel_source(repo/"third_party/openpoints/cpp/pointnet2_batch/src")
        prog = ct.c_void_p()
        self.check(rtc.nvrtcCreateProgram(ct.byref(prog),code.encode(),b"p2p.cu",0,None,None))
        capability = torch.cuda.get_device_capability()
        opts = (ct.c_char_p * 2)(f"--gpu-architecture=compute_{capability[0]}{capability[1]}".encode(),b"--std=c++14")
        status = rtc.nvrtcCompileProgram(prog,len(opts),opts)
        if status:
            size = ct.c_size_t()
            rtc.nvrtcGetProgramLogSize(prog,ct.byref(size))
            log = ct.create_string_buffer(size.value)
            rtc.nvrtcGetProgramLog(prog,log)
            raise RuntimeError(log.value.decode())
        size = ct.c_size_t()
        self.check(rtc.nvrtcGetPTXSize(prog,ct.byref(size)))
        ptx = ct.create_string_buffer(size.value)
        self.check(rtc.nvrtcGetPTX(prog,ptx))
        self.check(rtc.nvrtcDestroyProgram(ct.byref(prog)))
        self.module = ct.c_void_p()
        self.check(driver.cuModuleLoadData(ct.byref(self.module),ptx))
        self.funcs = {}
        for names in KERNELS.values():
            for name in names:
                fun = ct.c_void_p()
                self.check(driver.cuModuleGetFunction(ct.byref(fun),self.module,name.encode()))
                self.funcs[name] = fun

    @staticmethod
    def check(status):
        if status:
            raise RuntimeError(f"CUDA API error {status}")

    def launch(self, name, batches, dimensions, *args):
        dims = (dimensions,1,1) if isinstance(dimensions,int) else dimensions
        packed = []
        for x in args:
            if isinstance(x, torch.Tensor):
                if not x.is_contiguous() or not x.is_cuda:
                    raise ValueError(f"Unexpected tensor layout in {name}.")
                packed.append(ct.c_void_p(x.data_ptr()))
            elif isinstance(x, bool):
                packed.append(ct.c_bool(x))
            elif isinstance(x, float):
                packed.append(ct.c_float(x))
            else:
                packed.append(ct.c_int(int(x)))
        params = (ct.c_void_p * len(packed))(*(ct.addressof(x) for x in packed))
        stream = ct.c_void_p(torch.cuda.current_stream().cuda_stream)
        self.check(self.driver.cuLaunchKernel(self.funcs[name],batches,1,1,*dims,0,stream,params,None))

    def fps_indices(self, coords, count):
        coords = coords.contiguous()
        b,_,n = coords.shape
        ids = torch.zeros((b,count),device=coords.device,dtype=torch.int32)
        distances = torch.full((b,n),1e38,device=coords.device)
        self.launch("furthest_point_sampling_kernel",b,512,b,n,count,coords,distances,ids)
        return ids

    def furthest_point_sample_pvcnn(self, coords, count):
        ids = self.fps_indices(coords,count).long()
        return torch.gather(coords,2,ids[:,None].expand(-1,coords.shape[1],-1))

    def ball_query(self, centers, points, radius, neighbours):
        centers, points = centers[:,:3].contiguous(),points[:,:3].contiguous()
        b,_,m = centers.shape
        n = points.shape[2]
        ids = torch.zeros((b,m,neighbours),device=points.device,dtype=torch.int32)
        self.launch("ball_query_kernel",b,threads(m),b,n,m,float(radius*radius),neighbours,centers,points,ids)
        return ids

    def pvcnn_grouping(self, features, ids):
        features, ids = features.contiguous(),ids.int().contiguous()
        b,c,n = features.shape
        _,m,u = ids.shape
        out = features.new_empty((b,c,m,u))
        self.launch("grouping_kernel",b,block(m,c),b,c,n,m,u,features,ids,out)
        return out

    def avg_voxelize(self, features, coords, resolution):
        features, coords = features.contiguous(),coords[:,:3].int().contiguous()
        b,c,n = features.shape
        r = resolution
        ids = torch.zeros((b,n),device=coords.device,dtype=torch.int32)
        counts = torch.zeros((b,r**3),device=coords.device,dtype=torch.int32)
        out = features.new_zeros((b,c,r,r,r))
        self.launch("grid_stats_kernel",b,threads(n),b,n,r,r*r,r**3,coords,ids,counts)
        self.launch("avg_voxelize_kernel",b,threads(n),b,c,n,r**3,ids,counts,features,out)
        return out

    def trilinear_devoxelize(self, features, coords, resolution, is_training=True):
        features, coords = features.contiguous(),coords[:,:3].contiguous()
        b,c = features.shape[:2]
        n = coords.shape[-1]
        r = resolution
        out = features.new_empty((b,c,n))
        # Gradients are never requested for inference, irrespective of a calling layer's flag.
        placeholder_idx = torch.empty(1,device=features.device,dtype=torch.int32)
        placeholder_w = features.new_empty(1)
        self.launch("trilinear_devoxelize_kernel",b,threads(n),b,c,n,r,r*r,r**3,False,coords,features,placeholder_idx,placeholder_w,out)
        return out

    def nearest_neighbor_interpolate(self, points, centers, features):
        points,centers,features = points[:,:3].contiguous(),centers[:,:3].contiguous(),features.contiguous()
        b,c,m = features.shape
        n = points.shape[2]
        weights = features.new_zeros((b,3,n))
        ids = torch.zeros((b,3,n),device=features.device,dtype=torch.int32)
        out = features.new_empty((b,c,n))
        self.launch("three_nearest_neighbors_kernel",b,threads(n),b,n,m,points,centers,weights,ids)
        self.launch("three_nearest_neighbors_interpolate_kernel",b,block(n,c),b,c,m,n,features,ids,weights,out)
        return out

    def install(self):
        module = types.ModuleType("third_party.openpoints.models.layers")
        for key in ("avg_voxelize","ball_query","furthest_point_sample_pvcnn","nearest_neighbor_interpolate",
                    "pvcnn_grouping","trilinear_devoxelize"):
            setattr(module,key,getattr(self,key))
        sys.modules[module.__name__] = module
        # The author module imports training-only earth mover's distance eagerly. The XYZ checkpoint uses MSE.
        package = types.ModuleType("metrics.emd_assignment")
        package.emd_module = types.ModuleType("emd_module")
        sys.modules[package.__name__] = package

    def check_forward(self):
        x = torch.tensor([[[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]],device="cuda")
        f = torch.tensor([[[1.,2.,4.,8.]]],device="cuda")
        ids = self.ball_query(x,x,.25,2)
        np.testing.assert_array_equal(ids.cpu().numpy()[0],np.repeat(np.arange(4)[:,None],2,axis=1))
        grouped = self.pvcnn_grouping(f,ids)
        torch.testing.assert_close(grouped[:,:,:,0],f)
        v = self.avg_voxelize(f,x.int(),2)
        torch.testing.assert_close(self.trilinear_devoxelize(v,x,2,False),f)
        torch.testing.assert_close(self.nearest_neighbor_interpolate(x,x,f),f)
        assert sorted(self.fps_indices(x,4).cpu().tolist()[0]) == [0,1,2,3]
