"""Photo -> 3D print web app. Run `python app.py`, then open http://127.0.0.1:7860"""

import argparse
import os
import re
import time
from pathlib import Path

import gradio as gr
from PIL import Image

from pipeline import Studio, on_gray
from printprep import TURNS, PrintSettings, export_all, prepare_for_print

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
studio: Studio | None = None

QUALITY = {
    "Best (Hunyuan3D-2, about 1-3 min)": "best",
    "Fast (TripoSR, seconds, rough)": "fast",
}
# Per-quality defaults: the sharp model needs little smoothing and more triangles to keep detail.
DEFAULTS = {"best": dict(smoothing=1, max_tris=500_000), "fast": dict(smoothing=5, max_tris=200_000)}


def make_model(
    photo,
    quality_label,
    detail,
    remove_bg,
    foreground_ratio,
    height_mm,
    flat_base,
    base_cut,
    smoothing,
    max_triangles,
    turn,
    name,
    progress=gr.Progress(),
):
    if photo is None:
        raise gr.Error("Add a photo first.")
    quality = QUALITY.get(quality_label, "best")
    t = time.time()
    try:
        progress(0.05, desc="Removing background")
        rgba = studio.cutout(Image.fromarray(photo), remove_bg, foreground_ratio)

        slow = "1-3 min" if quality == "best" else "a few seconds"
        progress(0.2, desc=f"Building 3D shape ({slow})")
        raw = studio.generate(rgba, quality=quality, detail=detail)

        progress(0.85, desc="Making it printable")
        settings = PrintSettings(
            height_mm=height_mm,
            flat_base=flat_base,
            base_cut_percent=base_cut,
            smoothing=int(smoothing),
            max_triangles=int(max_triangles),
            turn=turn,
        )
        mesh, preview, report = prepare_for_print(raw, settings)
    except RuntimeError as e:
        raise gr.Error(str(e))

    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", (name or "").strip()) or time.strftime("model_%Y%m%d_%H%M%S")
    files = export_all(mesh, OUTPUT_DIR, stem, preview)
    info = (
        report.as_markdown()
        + f"  \n**Time:** {time.time() - t:.0f}s ({quality}, {detail}) on {studio.device}"
        + f"  \n**Saved to:** `{OUTPUT_DIR}`"
    )
    return on_gray(rgba), str(files["glb"]), str(files["3mf"]), str(files["stl"]), info


def quality_changed(quality_label):
    d = DEFAULTS[QUALITY.get(quality_label, "best")]
    return gr.update(value=d["smoothing"]), gr.update(value=d["max_tris"])


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Photo to 3D Print") as demo:
        gr.Markdown(
            "# Photo to 3D Print\n"
            "Upload a photo of one object, get a 3MF/STL ready for Bambu Studio. "
            "Best results: one object, plain background, shot slightly from above, nothing cut off."
        )
        with gr.Row():
            with gr.Column():
                photo = gr.Image(label="Photo", type="numpy", image_mode="RGBA", sources=["upload", "clipboard", "webcam"])
                quality = gr.Radio(list(QUALITY), value=list(QUALITY)[0], label="Quality")
                detail = gr.Radio(
                    ["Normal", "High", "Max"], value="High", label="Detail (Max = sharpest, slowest, most memory)"
                )
                height = gr.Slider(10, 250, value=80, step=1, label="Print height (mm)")
                name = gr.Textbox(label="File name (optional)", placeholder="e.g. bitcoin_miner")
                with gr.Accordion("Settings", open=False):
                    turn = gr.Dropdown(list(TURNS), value="None", label="Model lying down? Turn it")
                    remove_bg = gr.Checkbox(value=True, label="Remove background")
                    fg_ratio = gr.Slider(0.5, 1.0, value=0.85, step=0.05, label="Object size in frame")
                    smoothing = gr.Slider(0, 20, value=DEFAULTS["best"]["smoothing"], step=1, label="Smoothing (lower keeps more detail)")
                    flat_base = gr.Checkbox(value=True, label="Flat base (cut the bottom so it sits on the plate)")
                    base_cut = gr.Slider(0, 20, value=3, step=0.5, label="Base cut (% of height)")
                    max_tris = gr.Slider(
                        0, 2_000_000, value=DEFAULTS["best"]["max_tris"], step=50_000, label="Max triangles (0 = no limit)"
                    )
                go = gr.Button("Make 3D model", variant="primary")
            with gr.Column():
                processed = gr.Image(label="What the AI sees", interactive=False, height=220)
                viewer = gr.Model3D(label="3D preview (drag to rotate)", height=420)
                info = gr.Markdown()
                with gr.Row():
                    file_3mf = gr.File(label="3MF (open in Bambu Studio)")
                    file_stl = gr.File(label="STL")

        quality.change(quality_changed, inputs=quality, outputs=[smoothing, max_tris])
        go.click(
            make_model,
            inputs=[photo, quality, detail, remove_bg, fg_ratio, height, flat_base, base_cut, smoothing, max_tris, turn, name],
            outputs=[processed, viewer, file_3mf, file_stl, info],
        )
    return demo


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default=None, help="cuda:0 or cpu (default: auto)")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument(
        "--share-on-network", action="store_true", help="let other devices on your Wi-Fi open it"
    )
    ap.add_argument(
        "--password",
        default=os.environ.get("PHOTO3D_PASSWORD"),
        help="require this password (any username) to open the app; or set PHOTO3D_PASSWORD",
    )
    ap.add_argument(
        "--public-link",
        action="store_true",
        help="get a temporary public https://xxxx.gradio.live address (requires --password)",
    )
    ap.add_argument(
        "--preload", choices=["best", "fast", "none"], default="best", help="load this model at startup"
    )
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    if args.public_link and not args.password:
        ap.error("--public-link needs a password, otherwise anyone with the link could use your GPU.")

    auth = None
    if args.password:
        password = args.password
        auth = lambda _user, pw: pw == password  # noqa: E731
    elif args.share_on_network:
        print("Tip: add --password <something> so nobody else on the same network can use it.")

    studio = Studio(device=args.device)
    print(f"Using {studio.device}.")
    if studio.device == "cpu":
        print("No NVIDIA GPU found: running on CPU. Fast works; Best is very slow on CPU (10-30 min).")
    if args.preload != "none":
        name = "Hunyuan3D-2 (first run downloads several GB)" if args.preload == "best" else "TripoSR"
        print(f"Loading {name}...")
        try:
            studio._engine(args.preload)
            print("Model ready.")
        except Exception as e:
            print(f"!! Couldn't load the {args.preload} model: {e}")
            print("   The app will still start; it tries again when you make a model.")
    demo = build_ui().queue(default_concurrency_limit=1)
    demo.launch(
        server_name="0.0.0.0" if args.share_on_network else "127.0.0.1",
        server_port=args.port,
        inbrowser=not args.no_browser,
        allowed_paths=[str(OUTPUT_DIR)],
        auth=auth,
        auth_message="Photo to 3D Print. Any username, your password.",
        pwa=True,  # lets the phone "Add to Home Screen" like an app
        share=args.public_link,
        prevent_thread_lock=True,
    )

    publisher = None
    token = os.environ.get("PHOTO3D_GITHUB_TOKEN", "").strip()
    if args.public_link and not demo.share_url:
        print(
            "\n!! Couldn't create the public link. Usually Windows Defender or antivirus blocked\n"
            "   Gradio's connection helper (frpc). Allow it, then close this window and start again."
        )
    elif args.public_link and not token:
        print(
            "\n!! No GitHub token, so your GitHub page can't find this link.\n"
            "   Delete github-token.txt in this folder, start again, and paste the token when asked."
        )
    elif args.public_link:
        from linkpublisher import LinkPublisher

        print("Saving this link to GitHub...")
        publisher = LinkPublisher(token)
        if publisher.start(demo.share_url):
            print("Saved this link to GitHub. Your GitHub page will forward to it.")
        else:
            print(
                "   Fix: delete github-token.txt, make a new token with the 'gist' box ticked,\n"
                "   then start again and paste it."
            )
    try:
        demo.block_thread()
    finally:
        if publisher:
            publisher.stop()
