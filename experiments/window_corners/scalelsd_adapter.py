"""Use the released ScaleLSD v2 inference path on a metric wall occupancy image."""
from hashlib import sha256
from pathlib import Path
import sys

import numpy as np

WEIGHT_SHA256 = "d0a7333c4de518a70af7d6ea4a283aa0ce9ffe1047525373b94070b1d1d4003f"
AUTHOR_COMMIT = "e2751fcd0eb82694abeb12ef7ec9d46237e2ca06"


class ScaleLines:
    def __init__(self, checkout, weights, device):
        import torch
        sys.path.insert(0, str(Path(checkout).resolve()))
        from scalelsd.ssl.models.detector import ScaleLSD
        from scalelsd.ssl.misc.train_utils import fix_seeds
        with Path(weights).open("rb") as stream:
            digest = sha256()
            for block in iter(lambda: stream.read(2**20), b""):
                digest.update(block)
        if digest.hexdigest() != WEIGHT_SHA256:
            raise ValueError("Expected the author's ScaleLSD v2 SA-1B checkpoint.")
        fix_seeds(0)
        self.device = device
        self.model = ScaleLSD(gray_scale=True, use_layer_scale=True)
        state = torch.load(weights, map_location="cpu", weights_only=True)
        self.model.load_state_dict(state.get("model_state", state), strict=True)
        self.model.eval().to(device)
        self.model.junction_threshold_hm = .008
        self.model.num_junctions_inference = 512

    def __call__(self, gray):
        import cv2
        import torch
        scaled = cv2.resize(gray, (512,512), interpolation=cv2.INTER_LINEAR)
        tensor = torch.from_numpy(scaled).to(self.device, dtype=torch.float32)[None,None] / 255
        meta = dict(width=gray.shape[1], height=gray.shape[0], filename="",
                    use_lsd=False, use_nms=False)
        with torch.inference_mode():
            try:
                outputs, _ = self.model(tensor, meta)
            except IndexError:
                # The author's matcher takes a minimum over an empty junction set.
                field, _, _ = self.model.forward_backbone(tensor)
                if (field[:,5:7].softmax(1)[:,1] > self.model.junction_threshold_hm).any():
                    raise
                self.audit = {"raw_lines":0,"retained_lines":0,"junctions":0,"max_votes":0}
                return np.empty((0,2,2))
        pred = outputs[0]
        scores = pred["lines_score"].cpu().numpy()
        self.audit = {"raw_lines":len(scores),"retained_lines":int((scores>10).sum()),
                      "junctions":len(pred["juncs_pred"]),"max_votes":float(scores.max(initial=0))}
        return pred["lines_pred"].cpu().numpy()[scores > 10].reshape(-1, 2, 2)
