#!/usr/bin/env python3
"""Remove paper/ivory background from generated illustrations, saving as RGBA PNG."""

import sys
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("PIL/numpy required: pip install Pillow numpy")
    sys.exit(1)


def make_transparent(input_path: str, output_path: str, threshold: int = 28) -> None:
    img = Image.open(input_path).convert("RGBA")
    data = np.array(img, dtype=np.int32)

    # Sample background color from four corners (5x5 average)
    corners = [
        data[:5, :5, :3],
        data[:5, -5:, :3],
        data[-5:, :5, :3],
        data[-5:, -5:, :3],
    ]
    bg = np.concatenate([c.reshape(-1, 3) for c in corners], axis=0).mean(axis=0)

    # Pixels within `threshold` distance (L-inf) of background become transparent
    diff = np.abs(data[:, :, :3] - bg).max(axis=2)
    mask = diff < threshold

    data[:, :, 3] = np.where(mask, 0, 255)

    out = Image.fromarray(data.astype(np.uint8), "RGBA")
    out.save(output_path, "PNG")
    print(f"Saved: {output_path}  ({mask.sum()} px removed)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 make_transparent.py <input.png> <output_transparent.png> [threshold]")
        sys.exit(1)
    thresh = int(sys.argv[3]) if len(sys.argv) > 3 else 28
    make_transparent(sys.argv[1], sys.argv[2], thresh)
