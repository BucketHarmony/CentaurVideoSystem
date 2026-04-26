"""
Generate a transparent-background version of the MPC logo.

Naive "set near-white to alpha 0" would punch holes through the star and the
white stripes inside the bird's body. Instead, flood-fill from the four corners
to identify ONLY the connected white background region, and zero its alpha.

Output: logo_wide_alpha.png alongside logo_wide.png
"""

from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import label

HERE = Path(__file__).resolve().parent
SRC = HERE / "logo_wide.png"
DST = HERE / "logo_wide_alpha.png"


def main() -> None:
    img = Image.open(SRC).convert("RGBA")
    arr = np.array(img)
    h, w = arr.shape[:2]

    # White-ish mask: all RGB channels > 240
    near_white = (arr[..., 0] > 240) & (arr[..., 1] > 240) & (arr[..., 2] > 240)

    # Connected components on the white mask
    labels, n = label(near_white)

    # Identify components that touch any of the four borders — those are bg
    border_labels = set()
    for y in [0, h - 1]:
        border_labels.update(labels[y, :].tolist())
    for x in [0, w - 1]:
        border_labels.update(labels[:, x].tolist())
    border_labels.discard(0)

    bg_mask = np.isin(labels, list(border_labels))
    print(f"Knocking out {bg_mask.sum():,} background pixels "
          f"({100*bg_mask.mean():.1f}% of image), preserving "
          f"{(near_white & ~bg_mask).sum():,} interior-white pixels")

    arr[bg_mask, 3] = 0
    Image.fromarray(arr).save(DST)
    print(f"Wrote {DST}")


if __name__ == "__main__":
    main()
