# -*- coding: utf-8 -*-
"""
Safety / information pictograms for the VX-0057 customer guide.

Single source of truth for icons:
  - HTML/PDF embeds the SVG inline (crisp, recolorable).
  - DOCX embeds a PNG rasterized from the same SVG (via Chrome headless).

ISO 7010-style hazard pictograms use a yellow warning triangle with a black
symbol; information / handling icons are simple line glyphs.
"""

# ---- palette -------------------------------------------------------------
YELLOW = "#F7C600"   # ISO warning triangle
INK    = "#111111"   # symbol black
BLUE   = "#1763A6"   # information / notice
GREEN  = "#2E7D32"   # recycle


def _triangle(inner: str, fill: str = YELLOW) -> str:
    """Wrap a black inner pictogram in the ISO warning triangle."""
    return (
        f'<path d="M32 4 L62 58 H2 Z" fill="{fill}" stroke="{INK}" '
        f'stroke-width="3.4" stroke-linejoin="round"/>{inner}'
    )


# Inner pictograms (drawn to sit in the lower-centre of the triangle, ~y40)
_EXCLAIM = (
    '<rect x="29.2" y="22" width="5.6" height="19" rx="2.6" fill="#111111"/>'
    '<circle cx="32" cy="49.5" r="3.4" fill="#111111"/>'
)
_BOLT = (
    '<path d="M36 21 L23.5 43 H31 L27.5 55 L41.5 38 H33.5 L37.5 28 Z" fill="#111111"/>'
)
_FLAME = (
    '<path d="M33 21 c5 6 1 9 4 12 c2 -2 2 -4 2 -6 c4 4 5 8 5 11 '
    'a11 11 0 0 1 -22 0 c0 -5 4 -8 5 -13 c2 3 1 6 3 7 c2 -3 -2 -7 3 -11 Z" '
    'fill="#111111"/>'
)
_HOT = (
    # surface bar + three rising heat waves
    '<rect x="18" y="48" width="28" height="3.4" rx="1.7" fill="#111111"/>'
    '<path d="M24 44 c-3 -3 3 -5 0 -9 c-3 -4 1 -6 1 -8" fill="none" '
    'stroke="#111111" stroke-width="3" stroke-linecap="round"/>'
    '<path d="M32 44 c-3 -3 3 -5 0 -9 c-3 -4 1 -6 1 -8" fill="none" '
    'stroke="#111111" stroke-width="3" stroke-linecap="round"/>'
    '<path d="M40 44 c-3 -3 3 -5 0 -9 c-3 -4 1 -6 1 -8" fill="none" '
    'stroke="#111111" stroke-width="3" stroke-linecap="round"/>'
)
_RF = (
    # antenna mast + radiating arcs
    '<rect x="30.5" y="34" width="3" height="16" rx="1.5" fill="#111111"/>'
    '<circle cx="32" cy="33" r="3.2" fill="#111111"/>'
    '<path d="M24 30 a11 11 0 0 1 16 0" fill="none" stroke="#111111" '
    'stroke-width="3" stroke-linecap="round"/>'
    '<path d="M20 26 a17 17 0 0 1 24 0" fill="none" stroke="#111111" '
    'stroke-width="3" stroke-linecap="round"/>'
)
_HAND = (
    # stylised reaching hand for ESD pictogram
    '<path d="M27 50 v-9 c0 -1.6 2.4 -1.6 2.4 0 v-3.5 c0 -1.6 2.4 -1.6 2.4 0 '
    'v-1 c0 -1.6 2.4 -1.6 2.4 0 v1 c0 -1.6 2.4 -1.6 2.4 0 v4 '
    'c2 -1 3.4 1 2.4 3 l-2.6 5 c-0.6 1.2 -1 2 -1 3 v1 Z" fill="#111111"/>'
)
_ESD = _HAND + '<path d="M18 24 L46 52" stroke="#111111" stroke-width="3.4" stroke-linecap="round"/>'

# ---- standalone (non-triangle) glyphs ------------------------------------
_INFO = (
    '<circle cx="32" cy="32" r="27" fill="#fff" stroke="' + BLUE + '" stroke-width="4"/>'
    '<circle cx="32" cy="20.5" r="3.6" fill="' + BLUE + '"/>'
    '<rect x="28.6" y="28" width="6.8" height="20" rx="3" fill="' + BLUE + '"/>'
)
_BOOK = (
    '<path d="M32 17 C26 13 16 13 10 15 V49 C16 47 26 47 32 51 '
    'C38 47 48 47 54 49 V15 C48 13 38 13 32 17 Z" fill="#fff" '
    'stroke="' + INK + '" stroke-width="3.2" stroke-linejoin="round"/>'
    '<path d="M32 17 V51" stroke="' + INK + '" stroke-width="3"/>'
)
_BATTERY = (
    '<rect x="9" y="22" width="42" height="22" rx="3" fill="#fff" '
    'stroke="' + INK + '" stroke-width="3.2"/>'
    '<rect x="51" y="28" width="5" height="10" rx="1.5" fill="' + INK + '"/>'
    '<rect x="16" y="31" width="9" height="4" rx="1" fill="' + INK + '"/>'
    '<rect x="34.5" y="31" width="9" height="4" rx="1" fill="' + INK + '"/>'
    '<rect x="37" y="27" width="4" height="9" rx="1" fill="' + INK + '"/>'
)
_GROUND = (
    '<rect x="30" y="12" width="4" height="20" fill="' + INK + '"/>'
    '<rect x="16" y="32" width="32" height="4" rx="2" fill="' + INK + '"/>'
    '<rect x="21" y="41" width="22" height="4" rx="2" fill="' + INK + '"/>'
    '<rect x="26" y="50" width="12" height="4" rx="2" fill="' + INK + '"/>'
)
_RECYCLE = (
    # WEEE crossed-out wheelie bin
    '<path d="M16 24 H48 L45 54 H19 Z" fill="#fff" stroke="' + INK + '" '
    'stroke-width="3" stroke-linejoin="round"/>'
    '<rect x="12" y="18" width="40" height="5" rx="2.5" fill="' + INK + '"/>'
    '<rect x="26" y="12" width="12" height="5" rx="2.5" fill="' + INK + '"/>'
    '<path d="M25 30 V48 M32 30 V48 M39 30 V48" stroke="' + INK + '" stroke-width="2.6"/>'
    '<path d="M8 52 L56 16" stroke="' + INK + '" stroke-width="4" stroke-linecap="round"/>'
)
_WRENCH = (
    '<path d="M41 14 a11 11 0 0 0 -13 14 L13 43 a4 4 0 0 0 6 6 L34 34 '
    'a11 11 0 0 0 14 -13 l-7 7 -7 -2 -2 -7 Z" fill="' + INK + '"/>'
)

# Registry: name -> inner SVG body (without the <svg> wrapper)
ICONS = {
    # hazard pictograms (yellow triangle)
    "alert":    _triangle(_EXCLAIM),
    "electric": _triangle(_BOLT),
    "fire":     _triangle(_FLAME),
    "hot":      _triangle(_HOT),
    "rf":       _triangle(_RF),
    "esd":      _triangle(_ESD),
    "battery_w": _triangle(_BATTERY.replace('#fff', YELLOW)),
    # information / handling glyphs
    "notice":  _INFO,
    "book":    _BOOK,
    "battery": _BATTERY,
    "ground":  _GROUND,
    "recycle": _RECYCLE,
    "wrench":  _WRENCH,
    # brand mark (telemetry-arc badge)
    "logo": (
        '<rect x="2" y="2" width="60" height="60" rx="14" fill="#0E2A47"/>'
        '<circle cx="22" cy="42" r="4.5" fill="#36C5F0"/>'
        '<path d="M22 30 a12 12 0 0 1 12 12" fill="none" stroke="#36C5F0" stroke-width="4" stroke-linecap="round"/>'
        '<path d="M22 22 a20 20 0 0 1 20 20" fill="none" stroke="#7FE0FF" stroke-width="4" stroke-linecap="round"/>'
    ),
}


def svg(name: str, size: int = 64, extra_class: str = "") -> str:
    """Full standalone <svg> string for inline embedding."""
    body = ICONS[name]
    cls = f' class="{extra_class}"' if extra_class else ""
    return (
        f'<svg{cls} xmlns="http://www.w3.org/2000/svg" width="{size}" '
        f'height="{size}" viewBox="0 0 64 64" role="img" aria-label="{name}">'
        f'{body}</svg>'
    )
