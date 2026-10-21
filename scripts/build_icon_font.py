"""Build the map's icon font: a subset of the Material Design Icons webfont.

Input (not in the repo): a download of @mdi/font, e.g.

    dist/mdi-download/materialdesignicons-webfont.ttf
    dist/mdi-download/materialdesignicons.css

Output: custom_components/narwal_local/protocol/assets/mdi-subset.ttf plus
icons.json (icon name -> codepoint for every icon in the subset). The icon
choice per robot type lives in protocol/icons.py; this script reads it.

    python scripts/build_icon_font.py [download-dir]

Needs fontTools (pip install fonttools).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "custom_components" / "narwal_local" / "protocol" / "assets"
sys.path.insert(0, str(ROOT / "tests"))
import conftest  # noqa: E402,F401  (loads the `protocol` package)

from protocol.icons import all_icon_names  # noqa: E402

CSS_RULE = re.compile(r"\.mdi-([a-z0-9-]+)::before\s*\{\s*content:\s*\"\\([0-9A-Fa-f]+)\"")


def codepoints(css: str) -> dict[str, int]:
    return {name: int(hexcode, 16) for name, hexcode in CSS_RULE.findall(css)}


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "mdi-download"
    table = codepoints((src / "materialdesignicons.css").read_text(encoding="utf-8"))
    wanted = sorted(all_icon_names())
    missing = [n for n in wanted if n not in table]
    if missing:
        sys.exit(f"not in this MDI version: {missing}")

    from fontTools import subset  # noqa: PLC0415

    options = subset.Options()
    options.layout_features = []  # glyphs by codepoint only, no ligatures
    options.name_IDs = ["*"]  # keep the copyright/licence names
    options.notdef_outline = True
    font = subset.load_font(str(src / "materialdesignicons-webfont.ttf"), options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[table[n] for n in wanted])
    subsetter.subset(font)
    ASSETS.mkdir(parents=True, exist_ok=True)
    subset.save_font(font, str(ASSETS / "mdi-subset.ttf"), options)

    (ASSETS / "icons.json").write_text(
        json.dumps({n: table[n] for n in wanted}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"{len(wanted)} icons -> {ASSETS / 'mdi-subset.ttf'} "
          f"({(ASSETS / 'mdi-subset.ttf').stat().st_size} bytes)")


if __name__ == "__main__":
    main()
