"""Command-line version: python cli.py photo.jpg [more.jpg ...] --height 80"""

import argparse
import time
from pathlib import Path

from PIL import Image

from pipeline import Studio, on_gray
from printprep import PrintSettings, export_all, prepare_for_print


def main():
    ap = argparse.ArgumentParser(description="Turn photos into printable STL/3MF files.")
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--height", type=float, default=80.0, help="final print height in mm")
    ap.add_argument("--quality", choices=["best", "fast"], default="best", help="best = Hunyuan3D-2, fast = TripoSR")
    ap.add_argument("--detail", choices=["Normal", "High", "Max"], default="High")
    ap.add_argument("--smoothing", type=int, default=None, help="default: 1 for best, 5 for fast")
    ap.add_argument("--base-cut", type=float, default=3.0, help="percent of height cut off for a flat base")
    ap.add_argument("--no-flat-base", action="store_true")
    ap.add_argument("--keep-background", action="store_true", help="photo already has a clean/transparent background")
    ap.add_argument("--foreground-ratio", type=float, default=0.85)
    ap.add_argument("--max-triangles", type=int, default=None, help="default: 500k for best, 200k for fast")
    ap.add_argument("--device", default=None, help="cuda:0 or cpu (default: auto)")
    args = ap.parse_args()

    best = args.quality == "best"
    if args.smoothing is None:
        args.smoothing = 1 if best else 5
    if args.max_triangles is None:
        args.max_triangles = 500_000 if best else 200_000
    studio = Studio(device=args.device)
    print(f"Using {studio.device}, {args.quality} quality, {args.detail} detail")

    settings = PrintSettings(
        height_mm=args.height,
        flat_base=not args.no_flat_base,
        base_cut_percent=args.base_cut,
        smoothing=args.smoothing,
        max_triangles=args.max_triangles,
    )
    for path in args.images:
        t = time.time()
        rgba = studio.cutout(Image.open(path), not args.keep_background, args.foreground_ratio)
        raw = studio.generate(rgba, quality=args.quality, detail=args.detail)
        mesh, preview, report = prepare_for_print(raw, settings)
        files = export_all(mesh, args.out, path.stem, preview)
        on_gray(rgba).save(args.out / f"{path.stem}_input.png")
        print(f"\n{path.name} done in {time.time() - t:.0f}s")
        print(report.as_markdown().replace("**", "").replace("  \n", "\n"))
        for kind, p in files.items():
            print(f"  {kind}: {p}")


if __name__ == "__main__":
    main()
