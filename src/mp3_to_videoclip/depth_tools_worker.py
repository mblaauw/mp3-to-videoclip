"""Estimate one still's depth, run inside the private tools environment.

This file is launched by `depth.py` with that environment's Python, so it imports
nothing from this project. It reports one JSON object per line on stdout.
"""

import json
import sys
from pathlib import Path

MODEL = "depth-anything/Depth-Anything-V2-Small-hf"
# Apache-2.0. Pinned, so the same still always gets the same map from the same weights.
REVISION = "5426e4f0f36572d16453bbda7a8389317b1bef99"


def say(step: str) -> None:
    print(json.dumps({"step": step}), flush=True)


def _load():
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    processor = AutoImageProcessor.from_pretrained(MODEL, revision=REVISION)
    model = AutoModelForDepthEstimation.from_pretrained(MODEL, revision=REVISION)
    return processor, model.eval()


def prepare() -> None:
    """Fetch the weights now, so the first still needs no download."""
    say("downloading-depth-model")
    _load()


def estimate(still: str, output: str) -> None:
    """Write a greyscale map the size of the still, where brighter is nearer."""
    import numpy as np
    import torch
    from PIL import Image

    say("reading-depth")
    processor, model = _load()
    image = Image.open(still).convert("RGB")
    with torch.no_grad():
        result = model(**processor(images=image, return_tensors="pt")).predicted_depth
    depth = torch.nn.functional.interpolate(
        result.unsqueeze(1), size=image.size[::-1], mode="bicubic", align_corners=False
    )[0, 0].numpy()
    low, high = float(depth.min()), float(depth.max())
    scaled = (depth - low) / ((high - low) or 1.0) * 255
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(scaled, 0, 255).astype(np.uint8), mode="L").save(output)


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "prepare":
        prepare()
    elif command == "estimate":
        estimate(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(f"unknown command {command}")
