"""One-time installer. Run inside the virtual environment (setup.bat / setup.sh do this for you).

1. Installs PyTorch: the NVIDIA (CUDA) build if an NVIDIA card is found, otherwise CPU.
2. Installs the other Python packages.
3. Downloads TripoSR's and Hunyuan3D-2's code (pinned versions) into vendor/.
Model weights download automatically the first time you run the app.
Safe to run again: it updates packages and fetches anything new.
"""

import io
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# (repo, pinned commit, folder under vendor/)
VENDORED = [
    ("VAST-AI-Research/TripoSR", "107cefdc244c39106fa830359024f6a2f1c78871", "TripoSR"),
    ("Tencent-Hunyuan/Hunyuan3D-2", "f8db63096c8282cb27354314d896feba5ba6ff8a", "Hunyuan3D-2"),
]
# Newest first; the first one that has a wheel for this Python wins.
CUDA_INDEXES = ["cu130", "cu128", "cu126"]


def pip(*args: str) -> bool:
    return subprocess.call([sys.executable, "-m", "pip", "install", *args]) == 0


def has_nvidia_gpu() -> bool:
    if shutil.which("nvidia-smi") is None:
        return False
    return subprocess.call(["nvidia-smi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def install_torch():
    system = platform.system()
    if system in ("Windows", "Linux") and has_nvidia_gpu():
        print("\n== NVIDIA GPU found: installing PyTorch with CUDA ==")
        for tag in CUDA_INDEXES:
            if pip("torch", "torchvision", "--index-url", f"https://download.pytorch.org/whl/{tag}"):
                return
            print(f"   ({tag} build not available, trying the next one)")
        print("!! Couldn't install a CUDA build; falling back to CPU.")
    else:
        print("\n== No NVIDIA GPU found: installing CPU PyTorch (works, just slower) ==")
    if system == "Linux":
        ok = pip("torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cpu")
    else:  # Windows and macOS: the default PyPI build is the CPU / Apple build
        ok = pip("torch", "torchvision")
    if not ok:
        sys.exit("PyTorch install failed. See the messages above.")


def install_vendored(repo: str, commit: str, folder: str):
    target = HERE / "vendor" / folder
    pinned = target / ".pinned"
    if pinned.is_file() and pinned.read_text().strip() == commit:
        print(f"\n== {folder} code already present ==")
        return
    if not pinned.is_file() and target.is_dir() and any(target.iterdir()):
        # Downloaded by an older version of this installer (same pinned commit): keep it.
        pinned.write_text(commit)
        print(f"\n== {folder} code already present ==")
        return
    shutil.rmtree(target, ignore_errors=True)
    print(f"\n== Downloading {folder} code ==")
    target.parent.mkdir(exist_ok=True)

    # The zip has no git history, so it's the smallest download. Fall back to git.
    try:
        with urllib.request.urlopen(f"https://github.com/{repo}/archive/{commit}.zip") as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = z.namelist()[0].split("/")[0]
            z.extractall(HERE / "vendor")
        (HERE / "vendor" / root).rename(target)
        pinned.write_text(commit)
        return
    except Exception as e:
        shutil.rmtree(target, ignore_errors=True)
        print(f"   (zip download failed: {e}; trying git)")

    if shutil.which("git"):
        url = f"https://github.com/{repo}.git"
        target.mkdir(parents=True)
        steps = (
            ["git", "init", "-q"],
            ["git", "fetch", "-q", "--depth", "1", url, commit],
            ["git", "checkout", "-q", "FETCH_HEAD"],
        )
        if all(subprocess.call(cmd, cwd=target) == 0 for cmd in steps):
            shutil.rmtree(target / ".git", ignore_errors=True)
            pinned.write_text(commit)
            return
        shutil.rmtree(target, ignore_errors=True)
    raise RuntimeError(f"Couldn't download the {folder} code. Check your internet connection and try again.")


def main():
    if sys.version_info < (3, 10) or sys.version_info >= (3, 13):
        print(f"!! You're on Python {platform.python_version()}. This was tested on 3.11; 3.10-3.12 should work.")
    pip("--upgrade", "pip")
    install_torch()
    print("\n== Installing the other packages ==")
    if not pip("-r", str(HERE / "requirements.txt")):
        sys.exit("Package install failed. See the messages above.")
    for repo, commit, folder in VENDORED:
        install_vendored(repo, commit, folder)

    import torch

    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    print("\n==============================================")
    print(" Setup finished.")
    print(f" Running on: {gpu or 'CPU (no NVIDIA GPU in use)'}")
    print(" Start the app with start.bat (Windows) or ./start.sh (Mac/Linux).")
    print("==============================================")


if __name__ == "__main__":
    main()
