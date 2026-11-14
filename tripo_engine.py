"""Tripo engine: sends the photo to Tripo's cloud (the same engine as studio.tripo3d.ai)
and turns the result into a mesh our print prep understands.

Costs Tripo credits per model. Needs an API key (starts with tsk_) from
https://platform.tripo3d.ai, put in tripo-key.txt next to this file or in the
TRIPO_API_KEY environment variable.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path
from typing import Callable

import numpy as np
import trimesh
from PIL import Image

HERE = Path(__file__).resolve().parent
KEY_FILE = HERE / "tripo-key.txt"
# Newest full-detail model in Tripo's SDK docs ("P-..." versions are their low-poly models).
MODEL_VERSION = os.environ.get("TRIPO_MODEL_VERSION", "v3.1-20260211")
TIMEOUT_SECONDS = 15 * 60


def api_key() -> str | None:
    key = os.environ.get("TRIPO_API_KEY", "").strip()
    if not key and KEY_FILE.is_file():
        key = KEY_FILE.read_text(encoding="utf-8-sig").strip()
    return key or None


class TripoError(RuntimeError):
    pass


def _friendly(e: Exception) -> str:
    msg = getattr(e, "message", None) or str(e)
    code = getattr(e, "code", None)
    text = f"Tripo said: {msg}" + (f" (code {code})" if code else "")
    low = msg.lower()
    if "credit" in low or "balance" in low or "insufficient" in low:
        text += ". Top up credits at platform.tripo3d.ai."
    elif "key" in low or "auth" in low or getattr(e, "status_code", None) in (401, 403):
        text += ". Check the key in tripo-key.txt."
    return text


async def _run(photo_path: Path, out_glb: Path, on_progress: Callable[[int], None] | None) -> dict:
    from tripo3d import TaskStatus, TripoClient

    async with TripoClient(api_key=api_key()) as client:
        task_id = await client.image_to_model(
            str(photo_path),
            model_version=MODEL_VERSION,
            texture=True,
            pbr=True,
            texture_quality="detailed",
            geometry_quality="detailed",
        )
        start, interval = time.monotonic(), 2.0
        while True:
            task = await client.get_task(task_id)
            if task.status.is_terminal():
                break
            if on_progress:
                on_progress(int(task.progress or 0))
            if time.monotonic() - start > TIMEOUT_SECONDS:
                raise TripoError(f"Tripo took over {TIMEOUT_SECONDS // 60} minutes. Task {task_id} may still finish on their site.")
            await asyncio.sleep(interval)
            interval = min(interval * 1.5, 10.0)

        if task.status != TaskStatus.SUCCESS:
            reason = task.error_msg or task.status.value
            raise TripoError(f"Tripo couldn't make this model: {reason}")
        url = task.output.model_url or task.output.pbr_model or task.output.model
        if not url:
            raise TripoError("Tripo finished but didn't return a model file.")
        await client.download_file(url, out_glb)
        info = {"task_id": task_id, "credits": task.credits_consumed}
        try:
            info["balance"] = (await client.get_balance()).balance
        except Exception:
            info["balance"] = None
        return info


def glb_to_mesh(path: Path) -> trimesh.Trimesh:
    """Load Tripo's textured GLB as one mesh with the texture baked into vertex colors,
    turned to our frame (Z up, front facing +X)."""
    scene = trimesh.load(str(path), force="scene")
    parts = []
    for node in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node]
        g = scene.geometry[geom_name]
        if not isinstance(g, trimesh.Trimesh) or len(g.faces) == 0:
            continue
        g = g.copy()
        try:
            g.visual = g.visual.to_color()  # sample the texture at each vertex
        except Exception:
            pass
        g.apply_transform(transform)
        parts.append(g)
    if not parts:
        raise TripoError("Tripo's model file was empty.")
    mesh = parts[0] if len(parts) == 1 else trimesh.util.concatenate(parts)
    # glTF is Y-up with the front facing +Z; turn to Z-up with the front facing +X.
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))
    return mesh


def generate(photo: Image.Image, out_dir: Path, stem: str, on_progress=None) -> tuple[trimesh.Trimesh, Path, dict]:
    """Photo -> (mesh, path to Tripo's original textured GLB, info with credits used/left)."""
    if not api_key():
        raise TripoError(
            "No Tripo API key yet. Get one at platform.tripo3d.ai (API Keys), then put it in "
            "tripo-key.txt in the app folder (start-public.bat asks for it) and restart the app."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_glb = out_dir / f"{stem}_tripo.glb"
    with tempfile.TemporaryDirectory() as tmp:
        photo_path = Path(tmp) / "photo.png"
        img = photo.convert("RGBA") if photo.mode in ("RGBA", "LA", "P") else photo.convert("RGB")
        img.save(photo_path)
        try:
            info = asyncio.run(_run(photo_path, out_glb, on_progress))
        except TripoError:
            raise
        except Exception as e:  # SDK / network errors
            raise TripoError(_friendly(e)) from None
    return glb_to_mesh(out_glb), out_glb, info
