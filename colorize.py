"""Color a mesh by projecting the photo onto it.

Our meshes face the camera the same way the photo did: front toward +X,
image-right toward +Y, up toward +Z. So each point on the front can take its
color straight from the photo. Points the camera couldn't see (back,
undersides) take the color of the nearest point it could see.
"""

from __future__ import annotations

import numpy as np
import trimesh
from PIL import Image
from scipy.spatial import cKDTree


def project_photo_colors(mesh: trimesh.Trimesh, rgba: Image.Image, grid: int = 256) -> trimesh.Trimesh:
    """Return a copy of `mesh` with vertex colors taken from the photo `rgba`."""
    mesh = mesh.copy()
    img = np.asarray(rgba.convert("RGBA")).astype(np.float32)
    alpha = img[..., 3] > 127
    ys, xs = np.nonzero(alpha)
    if len(xs) == 0:
        return mesh
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()

    v = mesh.vertices
    lo, hi = v.min(axis=0), v.max(axis=0)
    span = np.maximum(hi - lo, 1e-9)
    # Fit the model's outline (as seen from the front) to the object's outline in the photo.
    u = (v[:, 1] - lo[1]) / span[1]  # 0 = image left, 1 = image right
    w = (hi[2] - v[:, 2]) / span[2]  # 0 = image top, 1 = image bottom
    px = np.clip(np.round(x0 + u * (x1 - x0)).astype(int), 0, img.shape[1] - 1)
    py = np.clip(np.round(y0 + w * (y1 - y0)).astype(int), 0, img.shape[0] - 1)

    # Depth test: which vertices are the frontmost (camera-visible) at their spot?
    gx = np.clip((u * (grid - 1)).astype(int), 0, grid - 1)
    gy = np.clip((w * (grid - 1)).astype(int), 0, grid - 1)
    cell = gy * grid + gx
    front = np.full(grid * grid, -np.inf)
    np.maximum.at(front, cell, v[:, 0])
    visible = v[:, 0] >= front[cell] - 0.03 * span[0]
    # Also require the surface to face the camera at least a little.
    visible &= mesh.vertex_normals[:, 0] > -0.1

    colors = np.zeros((len(v), 4), dtype=np.uint8)
    colors[:, 3] = 255
    sampled = img[py, px, :3]
    # Near the photo's outline, a pixel may be background: pull it from just inside instead.
    bg = ~alpha[py, px]
    if bg.any():
        inside = np.argwhere(alpha)
        _, idx = cKDTree(inside).query(np.c_[py[bg], px[bg]])
        sampled[bg] = img[inside[idx, 0], inside[idx, 1], :3]
    colors[visible, :3] = sampled[visible].astype(np.uint8)

    hidden = ~visible
    if hidden.any() and visible.any():
        colors[hidden, :3] = _body_color(colors, mesh.vertex_normals, visible)
    mesh.visual.vertex_colors = colors
    return mesh


def _body_color(colors: np.ndarray, normals: np.ndarray, visible: np.ndarray) -> np.ndarray:
    """The object's main color, for the parts the photo doesn't show.

    Taken from visible surfaces that face sideways (the object's sides, not
    its detailed front), using the most common color among them.
    """
    side = visible & (np.abs(normals[:, 0]) < 0.5)
    pool = colors[side if side.sum() >= 50 else visible, :3].astype(int)
    bins = pool // 32  # group similar colors
    keys = bins[:, 0] * 64 + bins[:, 1] * 8 + bins[:, 2]
    common = np.bincount(keys).argmax()
    return pool[keys == common].mean(axis=0).astype(np.uint8)
