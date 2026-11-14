"""Photo -> 3D mesh. Two engines:

* "best": Hunyuan3D-2 (Tencent, https://github.com/Tencent-Hunyuan/Hunyuan3D-2).
  A 1.1B-parameter diffusion model that generates the shape. Much sharper, more
  detailed geometry. Its shape stage needs ~6 GB of GPU memory; about 1-3 min on
  a laptop RTX 4070.
* "fast": TripoSR (https://github.com/VAST-AI-Research/TripoSR). Rough
  but takes seconds. We run its marching cubes ourselves with scikit-image, so
  `torchmcubes` (which needs compiling) isn't needed.

Both return a trimesh in the same frame: Z up, the photo's front facing +X.
Only the engine in use is kept on the GPU; the other waits on the CPU.
"""

from __future__ import annotations

import gc
import sys
import types
from pathlib import Path

import numpy as np
import torch
import trimesh
from PIL import Image
from skimage.measure import marching_cubes

HERE = Path(__file__).resolve().parent
TRIPOSR_DIR = HERE / "vendor" / "TripoSR"
HUNYUAN_DIR = HERE / "vendor" / "Hunyuan3D-2"

# Detail level -> engine setting
HUNYUAN_OCTREE = {"Normal": 256, "High": 384, "Max": 512}
TRIPOSR_GRID = {"Normal": 192, "High": 256, "Max": 320}


def pick_device(requested: str | None = None) -> str:
    if requested:
        return requested
    return "cuda:0" if torch.cuda.is_available() else "cpu"


def _free_gpu():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


# ------------------------------------------------------------------ photo prep
def resize_foreground(rgba: Image.Image, ratio: float) -> Image.Image:
    """Crop to the object, pad to a square so the object fills `ratio` of it."""
    arr = np.asarray(rgba)
    ys, xs = np.where(arr[..., 3] > 0)
    if len(xs) == 0:
        raise RuntimeError("Couldn't find an object in this photo. Try another photo, or turn off 'Remove background'.")
    fg = arr[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    size = max(fg.shape[:2])
    ph, pw = size - fg.shape[0], size - fg.shape[1]
    fg = np.pad(fg, ((ph // 2, ph - ph // 2), (pw // 2, pw - pw // 2), (0, 0)))
    full = int(size / ratio)
    p0 = (full - size) // 2
    fg = np.pad(fg, ((p0, full - size - p0), (p0, full - size - p0), (0, 0)))
    return Image.fromarray(fg)


def on_gray(rgba: Image.Image) -> Image.Image:
    arr = np.asarray(rgba).astype(np.float32) / 255.0
    arr = arr[:, :, :3] * arr[:, :, 3:4] + (1 - arr[:, :, 3:4]) * 0.5
    return Image.fromarray((arr * 255.0).astype(np.uint8))


# --------------------------------------------------------------------- TripoSR
def _import_triposr():
    if not (TRIPOSR_DIR / "tsr").is_dir():
        raise RuntimeError(f"TripoSR code not found in {TRIPOSR_DIR}. Run the setup script first.")
    if str(TRIPOSR_DIR) not in sys.path:
        sys.path.insert(0, str(TRIPOSR_DIR))
    # tsr imports torchmcubes at import time; we never call it, so stub it out.
    try:
        import torchmcubes  # noqa: F401
    except ImportError:
        stub = types.ModuleType("torchmcubes")

        def _unused(*_a, **_k):
            raise RuntimeError("torchmcubes is not used by this app")

        stub.marching_cubes = _unused
        sys.modules["torchmcubes"] = stub
    from tsr.system import TSR

    return TSR


class TripoSREngine:
    def __init__(self, chunk_size: int = 8192):
        TSR = _import_triposr()
        # Weights (~1.7 GB) download from Hugging Face on first use and are cached.
        self.model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
        self.model.renderer.set_chunk_size(chunk_size)
        self.model.eval()
        self.device = "cpu"

    def to(self, device: str):
        self.model.to(device)
        self.device = device

    @torch.no_grad()
    def generate(self, rgba: Image.Image, detail: str = "High", threshold: float = 25.0) -> trimesh.Trimesh:
        resolution = TRIPOSR_GRID.get(detail, 256)
        scene_code = self.model([on_gray(rgba)], device=self.device)[0]
        radius = float(self.model.renderer.cfg.radius)

        lin = torch.linspace(-radius, radius, resolution)
        grid = torch.stack(torch.meshgrid(lin, lin, lin, indexing="ij"), dim=-1).reshape(-1, 3)
        density = self.model.renderer.query_triplane(self.model.decoder, grid.to(self.device), scene_code)["density_act"]
        volume = (density.reshape(resolution, resolution, resolution) - threshold).float().cpu().numpy()
        del density, grid
        if volume.max() <= 0:
            raise RuntimeError("The model didn't find a solid object in this photo.")

        # Pad with empty space so the surface is always closed.
        volume = np.pad(volume, 1, mode="constant", constant_values=-threshold)
        verts, faces, _n, _ = marching_cubes(volume, level=0.0)
        verts = (verts - 1.0) / (resolution - 1.0) * (2 * radius) - radius

        colors = self.model.renderer.query_triplane(
            self.model.decoder, torch.from_numpy(verts.astype(np.float32)).to(self.device), scene_code
        )["color"]
        colors = (colors.clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, vertex_colors=colors, process=True)
        trimesh.repair.fix_normals(mesh)
        return mesh  # already Z-up, front facing +X


# ------------------------------------------------------------------- Hunyuan3D
def _import_hunyuan():
    if not (HUNYUAN_DIR / "hy3dgen").is_dir():
        raise RuntimeError(f"Hunyuan3D-2 code not found in {HUNYUAN_DIR}. Run the setup script again.")
    if str(HUNYUAN_DIR) not in sys.path:
        sys.path.insert(0, str(HUNYUAN_DIR))
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

    return Hunyuan3DDiTFlowMatchingPipeline


class HunyuanEngine:
    # Full 1.1B shape model, standard (non-turbo) VAE: the highest-quality combo
    # that fits in 8 GB.
    REPO = "tencent/Hunyuan3D-2"
    SUBFOLDER = "hunyuan3d-dit-v2-0"

    def __init__(self, device: str):
        Pipeline = _import_hunyuan()
        dtype = torch.float16 if device.startswith("cuda") else torch.float32
        # Weights (~5 GB) download from Hugging Face on first use and are cached.
        self.pipe = Pipeline.from_pretrained(
            self.REPO, subfolder=self.SUBFOLDER, use_safetensors=True, device=device, dtype=dtype
        )
        self.device = device

    def to(self, device: str):
        self.pipe.to(device)
        self.device = device

    @torch.no_grad()
    def generate(self, rgba: Image.Image, detail: str = "High", steps: int = 50, seed: int = 0) -> trimesh.Trimesh:
        octree = HUNYUAN_OCTREE.get(detail, 384)
        out = self.pipe(
            image=rgba,
            num_inference_steps=steps,
            guidance_scale=5.0,
            octree_resolution=octree,
            num_chunks=8000,
            generator=torch.Generator(device="cpu").manual_seed(seed),
            output_type="trimesh",
        )
        mesh = out[0]
        if isinstance(mesh, list):
            mesh = mesh[0]
        if mesh is None or len(mesh.faces) == 0:
            raise RuntimeError("The model didn't find a solid object in this photo.")
        # Hunyuan is Y-up with the photo's front facing +Z (3D-viewer convention).
        # Turn it to Z-up (printer convention) with the front facing +X, same as TripoSR.
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))  # Y up -> Z up
        mesh.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1]))  # front -> +X
        trimesh.repair.fix_normals(mesh)
        return mesh


# --------------------------------------------------------------------- manager
class Studio:
    """Holds both engines, loads each on first use, keeps only the active one on the GPU."""

    ENGINES = {"best": HunyuanEngine, "fast": TripoSREngine}

    def __init__(self, device: str | None = None):
        self.device = pick_device(device)
        self._engines: dict = {}
        self._active: str | None = None
        self._rembg_session = None

    def cutout(self, image: Image.Image, remove_background: bool = True, foreground_ratio: float = 0.85) -> Image.Image:
        """Cut the object out of the photo and center it. Returns RGBA."""
        if remove_background:
            if self._rembg_session is None:
                import rembg

                # isnet-general-use: small, Apache-2.0 licensed, good on objects
                self._rembg_session = rembg.new_session("isnet-general-use")
            import rembg

            rgba = rembg.remove(image.convert("RGB"), session=self._rembg_session)
        else:
            rgba = image.convert("RGBA")
        return resize_foreground(rgba, foreground_ratio)

    def _engine(self, name: str):
        if self._active == name:
            return self._engines[name]
        if self._active is not None and self.device != "cpu":
            self._engines[self._active].to("cpu")  # make room on the GPU
            _free_gpu()
        if name not in self._engines:
            cls = self.ENGINES[name]
            self._engines[name] = cls(self.device) if cls is HunyuanEngine else cls()
        self._engines[name].to(self.device)
        self._active = name
        return self._engines[name]

    def generate(self, rgba: Image.Image, quality: str = "best", detail: str = "High") -> trimesh.Trimesh:
        engine = self._engine(quality)
        try:
            return engine.generate(rgba, detail=detail)
        except torch.cuda.OutOfMemoryError:
            _free_gpu()
            raise RuntimeError(
                "Ran out of graphics card memory. Set Detail to a lower level, close other apps "
                "that use the GPU (games, video editors), and try again."
            ) from None
