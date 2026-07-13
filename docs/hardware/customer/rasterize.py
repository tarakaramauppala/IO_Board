# -*- coding: utf-8 -*-
"""Rasterize each SVG icon to a transparent PNG using Chrome headless."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(HERE, "assets", "icons")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

import icons as ic


def rasterize(name: str, px: int = 256) -> str:
    """Render one icon SVG -> transparent PNG, return the PNG path."""
    os.makedirs(ICON_DIR, exist_ok=True)
    win = 96  # logical window; scale factor lifts to px
    scale = px / win
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:transparent}"
        f"svg{{display:block;width:{win}px;height:{win}px}}</style></head>"
        f"<body>{ic.svg(name, size=win)}</body></html>"
    )
    html_path = os.path.join(ICON_DIR, f"_{name}.html")
    png_path = os.path.join(ICON_DIR, f"{name}.png")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--default-background-color=00000000",
            f"--force-device-scale-factor={scale}",
            f"--window-size={win},{win}",
            f"--screenshot={png_path}",
            "file:///" + html_path.replace("\\", "/"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.remove(html_path)
    return png_path


def main():
    names = sys.argv[1:] or list(ic.ICONS.keys())
    for n in names:
        p = rasterize(n)
        ok = os.path.exists(p) and os.path.getsize(p) > 0
        print(f"{'OK ' if ok else 'ERR'} {n:10s} -> {p} ({os.path.getsize(p) if ok else 0} bytes)")


if __name__ == "__main__":
    main()
