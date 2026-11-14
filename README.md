# Photo to 3D Print

Upload a photo, get a 3MF/STL file ready for Bambu Studio. It runs on your own computer, free, with no per-model fees.

It has two AI models:

- **Best: Hunyuan3D-2** (Tencent). Sharp, detailed shapes. About 1–3 minutes per model on an NVIDIA card.
- **Fast: TripoSR** (Tripo AI). Seconds per model, but rough and blobby. Good for quick tests.

The app then cleans the model up for printing: it keeps one solid piece, gives it a flat base, scales it to the height you pick in mm and sets it on the build plate.

## Updating from an older version

1. Download the new ZIP (green **Code** button → **Download ZIP**).
2. Copy everything from it into your app folder and click **Replace** when Windows asks. Your password, token and installed packages are kept.
3. Double-click **`setup.bat`** again. It adds what the Best model needs (a few minutes).
4. The first start after updating downloads the Best model (several GB), so give it some time.

## What you need

- A Windows PC (Mac/Linux work too).
- An NVIDIA graphics card with **8 GB+** of memory for Best quality (e.g. RTX 4070 Laptop, RTX 3060 or better).
- **No NVIDIA card?** Fast works on the CPU (30–60 seconds per photo). Best on the CPU takes 10–30 minutes.
- About 20 GB of free disk space (the AI models are big).

## Setup (one time, Windows)

1. Install **Python 3.11** from <https://www.python.org/downloads/>. On the first install screen, tick **"Add python.exe to PATH"**.
2. Optional: install **Git** from <https://git-scm.com/download/win>. Setup works without it.
3. Download this repo (green **Code** button → **Download ZIP**) and unzip it somewhere, e.g. `C:\photo-to-3d`. Or with Git: `git clone https://github.com/RingoshiToitsu1/3DPrinterGenerator.git`
4. Double-click **`setup.bat`**. It finds your NVIDIA card if you have one and installs everything (5–15 minutes).

Mac/Linux: run `./setup.sh` instead.

## Use it

1. Double-click **`start.bat`** (Mac/Linux: `./start.sh`). Your browser opens to the app.
   The first start downloads the AI models (several GB). After that it's quick.
2. Drop in a photo, set the **print height in mm**, then click **Make 3D model**.
3. Check the 3D preview, then download the **3MF** and open it in Bambu Studio. Your files are also saved in the `output` folder.

## Use it from your phone, anywhere

Your phone address never changes: **<https://ringoshitoitsu1.github.io/3DPrinterGenerator/>**

That GitHub page is a front door. It finds your laptop's current link and forwards you to it. Your laptop's graphics card still does all the work.

### One-time setup

1. **Turn on the GitHub page:** in this repo on GitHub, go to **Settings → Pages**. Under *Branch*, pick **main** and the **/docs** folder, then click **Save**. It goes live in a minute or two.
2. **Make a GitHub token** so the laptop can save its link. Go to <https://github.com/settings/tokens/new>:
   - **Note:** `photo to 3d`
   - **Expiration:** *No expiration*, or a long one
   - Tick only **gist**, then click **Generate token** and copy it.
3. On the laptop, double-click **`start-public.bat`**. The first time, it asks for:
   - a **password** for the app, saved in `phone-password.txt`
   - the **GitHub token**, saved in `github-token.txt`

   Both files stay on your laptop and never get uploaded to GitHub.

### Every time

1. On the laptop, double-click **`start-public.bat`** and keep the window open.
2. On your phone, open the GitHub address above. It shows **Laptop is online** and opens the app. Log in with any username and your password.
3. To get an app icon: in Safari tap **Share → Add to Home Screen**, or in Chrome tap **⋮ → Add to Home screen**.

If it says **Laptop is offline**, the app isn't running, or it stopped within the last ~12 minutes. Start `start-public.bat` and tap **Check again**.

Good to know:
- Keep the laptop on, plugged in and awake. Go to Settings → System → Power and set **Sleep when plugged in** to **Never**.
- The first time, Gradio downloads a small connection helper. If Windows Defender or your antivirus blocks it, allow it and start again.
- The laptop's link is saved in a public gist named `photo-to-3d-link.json` in your GitHub account, so the GitHub page can read it without a login. Anyone who finds it still needs your password.
- To change the password or token, delete `phone-password.txt` or `github-token.txt` and start again.

## Tips for good results

- **One object, plain background, whole object in the frame.** Background removal does the rest.
- Shoot from slightly above, the way you'd look at it on a table.
- Chunky objects (figures, toys, statues, products) work best. Very thin parts, like wires, straps or long legs at small sizes, come out lumpy or too thin to print.
- The AI has to guess the back of the object. If the back matters, check it in the preview.
- At small heights, thin parts like legs may come out under 1–2 mm. Print bigger, or turn on supports in Bambu Studio.

## Settings

| Setting | What it does |
| --- | --- |
| Print height | Final height in mm, after the base cut. |
| Remove background | Turn off only if your photo already has a clean or transparent background. |
| Object size in frame | How much of the frame the object fills before the AI sees it. 0.85 is a good default. |
| Quality | **Best** (Hunyuan3D-2): detailed, 1–3 min. **Fast** (TripoSR): rough, seconds. |
| Detail | **High** is the sweet spot. **Max** is sharper but slower and uses more memory. If you get "out of memory", use High or Normal. |
| Model lying down? Turn it | If a model comes out on its side or upside down, pick a turn and make it again. |
| Smoothing | Removes the small "stair-step" texture. Best mode defaults to 1 so detail survives. Raise it for a smoother look. |
| Flat base / Base cut | Slices a little off the bottom so it sits flat on the plate. |
| Max triangles | Keeps files a sensible size. Best mode defaults to 500k so fine detail is kept. |

## Troubleshooting

- **"Ran out of graphics card memory"**: set Detail to High or Normal, and close games or other apps that use the GPU.
- **Best mode errors or won't load**: run `setup.bat` again. Fast mode keeps working in the meantime.
- **It says "CPU" but you have an NVIDIA card**: update your NVIDIA driver, delete the `.venv` folder and run `setup.bat` again.
- **Bad cut-out** (part of the background became part of the model): crop the photo tighter, or remove the background yourself first (phone photo apps can do this) and untick "Remove background".

## Files

- `app.py`: the browser app
- `cli.py`: command-line version
- `pipeline.py`: photo → 3D with Hunyuan3D-2 (Best) or TripoSR (Fast). Keeps only the model in use on the GPU.
- `printprep.py`: makes the mesh printable and exports STL/3MF
- `install.py`, `setup.bat`/`setup.sh`, `start.bat`/`start.sh`: setup and launch scripts
- `start-public.bat`: launch for phone use (password-protected public link)
- `linkpublisher.py`: saves the current link to a GitHub gist for the front door
- `docs/`: the GitHub Pages front door

## Licenses

- TripoSR: MIT.
- Hunyuan3D-2: Tencent Hunyuan 3D 2.0 Community License. Free to use, but **not licensed in the EU, UK or South Korea**. Very large companies (over 1 million monthly users) need a separate license from Tencent.
