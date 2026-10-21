# Icon font notice

`mdi-subset.ttf` is a modified version of `materialdesignicons-webfont.ttf`
from **@mdi/font 7.4.47** (Material Design Icons by the
[Pictogrammers](https://pictogrammers.com/) icon group,
https://github.com/Templarian/MaterialDesign-Webfont).

- License: Apache License 2.0, see `LICENSE-APACHE-2.0.txt`; the upstream
  licence statement is in `LICENSE-MDI`.
- Modification: the font was cut down to the icons listed in `icons.json`
  (glyph selection by codepoint, layout features removed) with fontTools,
  by `scripts/build_icon_font.py` in this repository. Glyph outlines are
  unchanged.
