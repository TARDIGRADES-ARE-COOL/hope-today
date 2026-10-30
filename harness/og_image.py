"""Render the link-preview image (assets/og.png) from templates/og.html.
Run by hand when the look changes; the daily run just publishes the saved PNG."""
import subprocess
import tempfile
from pathlib import Path

from deck import env

ROOT = Path(__file__).resolve().parent.parent


def render():
    html = Path(tempfile.mkdtemp()) / "og.html"
    html.write_text(env.get_template("og.html").render(today="2026-10-30"), encoding="utf-8")
    out = ROOT / "assets" / "og.png"
    subprocess.run(["node", str(ROOT / "scripts" / "screenshot.mjs"), html.as_uri(), str(out), "1200", "630"], check=True)
    return out


if __name__ == "__main__":
    print("wrote", render())
