# Brand assets

From the Bishop & Barrister brand guide. The lettering is Playfair Display, outlined to paths, so no font is
needed to show them.

| File                     | Use                                                            |
| ------------------------ | -------------------------------------------------------------- |
| `bb-lockup-light-bg.svg` | The README header on a light background                        |
| `bb-lockup-dark-bg.svg`  | The README header on a dark background                         |
| `bb-tile.svg`            | App icons, avatars, the GitHub picture; source of the plugin icon |
| `bb-mark.svg`            | The mark alone, on light backgrounds                           |
| `bb-mark-reversed.svg`   | The mark alone, on dark backgrounds                            |
| `bb-favicon.svg`         | Small sizes: the ampersand alone                               |

Colours: Ink navy `#1C2B3A`, Oxblood `#6B1E23` (the ampersand on light), Parchment gold `#E3C9A8` (the
ampersand on dark), Ivory `#FBFAF7`.

`plugin/.claude-plugin/icon.png` is `bb-tile.svg` at 1024 px. Claude Code accepts only PNG or JPEG there, so
re-render it when the tile changes, for example with headless Chrome or Edge:

```bash
msedge --headless=new --hide-scrollbars --window-size=1024,1024 --screenshot=icon.png tile.html
```

where `tile.html` shows `bb-tile.svg` at 1024 by 1024 with no margin.
