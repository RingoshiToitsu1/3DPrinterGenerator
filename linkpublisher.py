"""Keeps the app's current public link in a GitHub gist so the GitHub Pages
front door (docs/index.html) can always find it.

The gist holds one small file, photo-to-3d-link.json:
    {"url": "https://xxxx.gradio.live", "updated": 1731600000}
It's re-saved every few minutes as a heartbeat. The front door treats the
laptop as offline when the heartbeat is old. When the app stops cleanly,
the url is cleared.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

API = os.environ.get("PHOTO3D_GITHUB_API", "https://api.github.com")
FILENAME = "photo-to-3d-link.json"
HEARTBEAT_SECONDS = 300


class LinkPublisher:
    def __init__(self, token: str):
        self.token = token.strip()
        self.gist_id: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ API
    def _request(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(
            API + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "photo-to-3d",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read() or b"null")

    def _find_or_create_gist(self) -> str:
        page = 1
        while True:
            gists = self._request("GET", f"/gists?per_page=100&page={page}")
            for g in gists:
                if FILENAME in (g.get("files") or {}):
                    return g["id"]
            if len(gists) < 100:
                break
            page += 1
        created = self._request(
            "POST",
            "/gists",
            {
                "description": "Photo to 3D Print: current link (updated automatically)",
                "public": True,  # the GitHub Pages front door finds it without a token
                "files": {FILENAME: {"content": json.dumps({"url": "", "updated": 0})}},
            },
        )
        return created["id"]

    def _save(self, url: str):
        content = json.dumps({"url": url, "updated": int(time.time())})
        self._request("PATCH", f"/gists/{self.gist_id}", {"files": {FILENAME: {"content": content}}})

    # -------------------------------------------------------------- public
    def start(self, url: str) -> bool:
        """Publish `url` now and keep it fresh in the background. Returns False on failure."""
        try:
            self.gist_id = self._find_or_create_gist()
            self._save(url)
        except urllib.error.HTTPError as e:
            hint = " (check the token has the 'gist' permission)" if e.code in (401, 403, 404) else ""
            print(f"Couldn't update the GitHub link: HTTP {e.code}{hint}")
            return False
        except Exception as e:  # network down etc.
            print(f"Couldn't update the GitHub link: {e}")
            return False

        def beat():
            while not self._stop.wait(HEARTBEAT_SECONDS):
                try:
                    self._save(url)
                except Exception as e:
                    print(f"(link heartbeat failed, will retry: {e})")

        self._thread = threading.Thread(target=beat, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """Mark the laptop offline (best effort)."""
        self._stop.set()
        if self.gist_id:
            try:
                self._save("")
            except Exception:
                pass
