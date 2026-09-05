#!/usr/bin/env python3
"""Rebuild the macOS icon from the retained PNG using macOS system tools."""

from pathlib import Path
import subprocess
import tempfile


def main() -> None:
    assets = Path(__file__).resolve().parents[1] / "assets"
    source = assets / "gptpro-launcher-source.png"
    output = assets / "gptpro-launcher.icns"
    with tempfile.TemporaryDirectory(prefix="gptpro-icon-") as temporary:
        iconset = Path(temporary) / "gptpro.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                suffix = "@2x" if scale == 2 else ""
                subprocess.run([
                    "/usr/bin/sips", "-z", str(size * scale), str(size * scale),
                    str(source), "--out", str(iconset / f"icon_{size}x{size}{suffix}.png"),
                ], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["/usr/bin/iconutil", "-c", "icns", str(iconset), "-o", str(output)], check=True)
    print(output)


if __name__ == "__main__":
    main()
