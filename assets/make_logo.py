"""Builds assets/logo.svg: an animated dog catching a football, with PUP FANTASY lettering (as outlines).
usage: python make_logo.py OUT.svg [ballX ballY sparkX sparkY]"""
import sys, pathlib
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

OUT = pathlib.Path(sys.argv[1])
FONT = "C:/Windows/Fonts/ariblk.ttf"      # Arial Black, converted to outlines so it looks the same everywhere


def text_path(text, size, tracking=0):
    """Return (svg path d, width) for text set in FONT, baseline at y=0, starting at x=0."""
    f = TTFont(FONT)
    gs, cmap, hmtx = f.getGlyphSet(), f.getBestCmap(), f["hmtx"]
    scale = size / f["head"].unitsPerEm
    x, parts = 0.0, []
    for ch in text:
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[g].draw(TransformPen(pen, (scale, 0, 0, -scale, x, 0)))
        parts.append(pen.getCommands())
        x += hmtx[g][0] * scale + tracking
    return " ".join(p for p in parts if p), x - tracking


W, H = 520, 446
size = 54
pup_d, pup_w = text_path("PUP", size, 2)
fan_d, fan_w = text_path("FANTASY", size, 2)
space = size * 0.32
total = pup_w + space + fan_w
x0 = (W - total) / 2
base_y = 413

BALL = """<path class="ball" d="M-30 0 C-18 -17 18 -17 30 0 C18 17 -18 17 -30 0Z"/>
    <path class="ballShade" d="M-30 0 C-18 7 18 7 30 0 C18 17 -18 17 -30 0Z"/>
    <path d="M-23 -9Q-20 0 -23 9M23 -9Q20 0 23 9" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round"/>
    <path class="lace" d="M-10 0H10M-6 -5V5M0 -5V5M6 -5V5"/>"""

SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">
<title id="t">Pup Fantasy</title>
<desc id="d">A black and tan dog leaping to catch a football, above the words PUP FANTASY.</desc>
<style>
  :root {{ --ink: #1d2433; --pup: #e08a2c; --badge: #f6e6c8; --badge2: #efd2a0; }}
  .fur {{ fill: #1b1a21; }} .fur2 {{ fill: #101016; }} .tan {{ fill: #c98a4b; }} .tan2 {{ fill: #a8692e; }}
  .blue {{ stroke: #6f9fc7; }} .silver {{ fill: #cfd4dc; stroke: #8b93a0; stroke-width: 1.6; }}
  .ball {{ fill: #8d4a26; }} .ballShade {{ fill: #6f3a1e; }} .lace {{ fill: none; stroke: #fff; stroke-width: 3; stroke-linecap: round; }}
  .limb {{ fill: none; stroke: #1b1a21; stroke-linecap: round; stroke-linejoin: round; }} .limb2 {{ fill: none; stroke: #101016; stroke-linecap: round; stroke-linejoin: round; }}
  .paw {{ fill: none; stroke: #c98a4b; stroke-linecap: round; }} .paw2 {{ fill: none; stroke: #a8692e; stroke-linecap: round; }}
  .pup {{ fill: var(--pup); }} .fan {{ fill: var(--ink); }}

  /* Resting pose = the catch. People who prefer reduced motion see this still image. */
  #dog      {{ transform: translate(210px, 202px) rotate(-12deg); }}
  #heldBall {{ opacity: 1; }}  #flyBall {{ opacity: 0; }}  #spark {{ opacity: 0; }}
  #shadow   {{ transform: translate(210px, 318px) scale(.62, .8); opacity: .16; }}

  @media (prefers-reduced-motion: no-preference) {{
    #dog      {{ animation: jump 4s cubic-bezier(.45,0,.4,1) infinite; }}
    #flyBall  {{ animation: fly 4s linear infinite; }}
    #heldBall {{ animation: held 4s linear infinite; }}
    #spark    {{ animation: spark 4s linear infinite; transform-box: fill-box; transform-origin: center; }}
    #shadow   {{ animation: shadow 4s cubic-bezier(.45,0,.4,1) infinite; }}
    #tail     {{ animation: wag .4s ease-in-out infinite alternate; transform-box: fill-box; transform-origin: 100% 100%; }}
    #flop     {{ animation: flop 4s ease-in-out infinite; transform-box: fill-box; transform-origin: 85% 10%; }}
    #perk     {{ animation: perk 4s ease-in-out infinite; transform-box: fill-box; transform-origin: 50% 100%; }}
    #tag      {{ animation: tag 4s ease-in-out infinite; transform-box: fill-box; transform-origin: 50% 0%; }}
    #fwd, #fwd2 {{ animation: reach 4s ease-in-out infinite; transform-box: fill-box; transform-origin: 0% 100%; }}
    #bwd, #bwd2 {{ animation: trail 4s ease-in-out infinite; transform-box: fill-box; transform-origin: 100% 0%; }}
  }}
  @keyframes jump {{
    0%, 14% {{ transform: translate(208px, 268px) rotate(8deg) scale(1.02, .88); }}
    30%     {{ transform: translate(200px, 238px) rotate(-16deg) scale(1, 1.03); }}
    46%     {{ transform: translate(210px, 202px) rotate(-12deg) scale(1, 1); }}
    62%     {{ transform: translate(218px, 210px) rotate(-6deg) scale(1, 1); }}
    82%     {{ transform: translate(222px, 262px) rotate(5deg) scale(1.02, .92); }}
    92%, 100% {{ transform: translate(208px, 268px) rotate(8deg) scale(1.02, .88); }}
  }}
  @keyframes fly {{
    0%    {{ opacity: 0; transform: translate(64px, 70px) rotate(-60deg); }}
    8%    {{ opacity: 1; transform: translate(64px, 70px) rotate(-60deg); }}
    20%   {{ opacity: 1; transform: translate(150px, 36px) rotate(-30deg); }}
    33%   {{ opacity: 1; transform: translate(262px, 54px) rotate(-14deg); }}
    46%   {{ opacity: 1; transform: translate(BALLXpx, BALLYpx) rotate(-38deg); }}
    46.1%, 100% {{ opacity: 0; transform: translate(BALLXpx, BALLYpx) rotate(-38deg); }}
  }}
  @keyframes held   {{ 0%, 45.9% {{ opacity: 0; }} 46%, 84% {{ opacity: 1; }} 84.1%, 100% {{ opacity: 0; }} }}
  @keyframes spark  {{ 0%, 44% {{ opacity: 0; transform: scale(.3); }} 48% {{ opacity: 1; transform: scale(1); }} 62%, 100% {{ opacity: 0; transform: scale(1.5); }} }}
  @keyframes shadow {{
    0%, 14%, 92%, 100% {{ transform: translate(200px, 318px) scale(1, 1); opacity: .3; }}
    46% {{ transform: translate(210px, 318px) scale(.62, .8); opacity: .14; }}
    82% {{ transform: translate(222px, 318px) scale(.95, 1); opacity: .26; }}
  }}
  @keyframes wag   {{ from {{ transform: rotate(-16deg); }} to {{ transform: rotate(18deg); }} }}
  @keyframes flop  {{ 0%, 14% {{ transform: rotate(0); }} 30% {{ transform: rotate(-26deg); }} 46%, 62% {{ transform: rotate(-12deg); }} 82% {{ transform: rotate(8deg); }} 100% {{ transform: rotate(0); }} }}
  @keyframes perk  {{ 0%, 14% {{ transform: rotate(0); }} 30% {{ transform: rotate(-8deg); }} 46%, 62% {{ transform: rotate(5deg); }} 100% {{ transform: rotate(0); }} }}
  @keyframes tag   {{ 0%, 14% {{ transform: rotate(0); }} 30% {{ transform: rotate(-26deg); }} 46%, 62% {{ transform: rotate(14deg); }} 82% {{ transform: rotate(-6deg); }} 100% {{ transform: rotate(0); }} }}
  @keyframes reach {{ 0%, 14% {{ transform: rotate(40deg); }} 30% {{ transform: rotate(8deg); }} 46%, 62% {{ transform: rotate(0); }} 82% {{ transform: rotate(30deg); }} 100% {{ transform: rotate(40deg); }} }}
  @keyframes trail {{ 0%, 14% {{ transform: rotate(-36deg); }} 30% {{ transform: rotate(-4deg); }} 46%, 62% {{ transform: rotate(0); }} 82% {{ transform: rotate(-24deg); }} 100% {{ transform: rotate(-36deg); }} }}
</style>

<!-- badge behind the dog, so the black coat reads on light and dark pages -->
<circle cx="260" cy="178" r="162" fill="var(--badge)"/>
<circle cx="260" cy="178" r="162" fill="none" stroke="var(--badge2)" stroke-width="6"/>
<ellipse id="shadow" cx="0" cy="0" rx="80" ry="10" fill="#1d2433"/>

<g id="dog">
  <!-- tail -->
  <g id="tail"><path class="limb" stroke-width="9" d="M-48 -6 Q-82 -14 -78 -52"/></g>
  <!-- far legs (darker) -->
  <g id="bwd2"><path class="limb2" stroke-width="15" d="M-28 14 L-52 30 L-76 30"/><path class="paw2" stroke-width="13" d="M-76 30 L-88 33"/></g>
  <g id="fwd2"><path class="limb2" stroke-width="15" d="M30 6 L58 2 L84 -6"/><path class="paw2" stroke-width="13" d="M84 -6 L95 -10"/></g>
  <!-- body -->
  <ellipse class="fur" cx="0" cy="0" rx="56" ry="35"/>
  <path class="tan" d="M24 -2 C46 -10 64 6 56 26 C48 40 28 38 22 24Z"/>
  <!-- near legs -->
  <g id="bwd"><path class="limb" stroke-width="16" d="M-32 12 L-60 28 L-86 36"/><path class="paw" stroke-width="14" d="M-86 36 L-98 40"/></g>
  <g id="fwd"><path class="limb" stroke-width="16" d="M34 16 L64 18 L92 10"/><path class="paw" stroke-width="14" d="M92 10 L104 6"/></g>
  <!-- head (tilted up toward the ball) -->
  <g transform="translate(78 -46) rotate(-14)">
    <g id="flop"><path class="fur2" stroke="#34333d" stroke-width="2.5" stroke-linejoin="round" d="M-18 -30 C-46 -36 -62 -12 -54 12 C-50 24 -36 20 -28 8 C-20 -4 -14 -18 -14 -28Z"/></g>
    <ellipse class="fur" cx="0" cy="0" rx="42" ry="38"/>
    <g id="perk"><path class="fur" stroke="#34333d" stroke-width="2" stroke-linejoin="round" d="M4 -30 L22 -82 L44 -24Z"/><path class="tan2" d="M14 -34 L24 -64 L34 -30Z" opacity=".9"/></g>
    <!-- muzzle, open mouth -->
    <path d="M14 14 C30 10 58 12 76 22 C70 46 38 52 18 38Z" fill="#7a2b2f"/>
    <path d="M26 30 C42 26 60 28 70 34 C60 46 40 48 28 40Z" fill="#ef7f8d"/>
    <path class="tan" d="M10 -4 C24 -18 56 -22 78 -10 C90 -2 84 14 70 20 C52 26 28 22 10 12Z"/>
    <path d="M30 22 L34 14 L38 22 M52 22 L56 15 L60 23" fill="#fff"/>
    <ellipse cx="80" cy="-9" rx="10" ry="7.5" fill="#1b1a21" transform="rotate(-18 80 -9)"/>
    <!-- eye + tan eyebrow -->
    <circle class="tan" cx="12" cy="-24" r="6.5"/>
    <circle cx="22" cy="-8" r="9.5" fill="#2a1d14"/><circle cx="25.5" cy="-11.5" r="3.4" fill="#fff"/>
    <!-- ball caught in the mouth -->
    <g id="heldBall" transform="translate(92 22) rotate(-26) scale(.92)">{BALL}</g>
  </g>
  <!-- collar + tag -->
  <path class="blue" fill="none" stroke-width="11" stroke-linecap="round" d="M44 -26 Q56 -12 54 6"/>
  <g id="tag"><circle cx="54" cy="16" r="10" class="silver"/><circle cx="54" cy="16" r="5.5" fill="none" stroke="#8b93a0" stroke-width="1.4"/></g>
</g>

<!-- football flying in (in front of the dog) -->
<g id="flyBall"><g transform="scale(1.05)">{BALL}</g></g>

<!-- catch sparkle -->
<g transform="translate(SPKX SPKY)"><g id="spark" stroke="#e08a2c" stroke-width="5" stroke-linecap="round">
  <path d="M0 -26V-12M0 12V26M-26 0H-12M12 0H26M-18 -18L-9 -9M9 9L18 18M18 -18L9 -9M-9 9L-18 18"/>
</g></g>

<!-- lettering on a banner of its own, so the logo reads on any page background -->
<rect x="{x0 - 22:.1f}" y="361" width="{total + 44:.1f}" height="70" rx="20" fill="var(--badge)" stroke="var(--badge2)" stroke-width="5"/>
<!-- lettering (outlines) -->
<g transform="translate({x0:.1f} {base_y})">
  <path class="pup" d="{pup_d}"/>
  <path class="fan" transform="translate({pup_w + space:.2f} 0)" d="{fan_d}"/>
</g>
</svg>
"""
BALLX, BALLY, SPKX, SPKY = sys.argv[2:6] if len(sys.argv) > 5 else ("358", "116", "384", "84")
SVG = SVG.replace("BALLX", BALLX).replace("BALLY", BALLY).replace("SPKX", SPKX).replace("SPKY", SPKY)
OUT.write_text(SVG, encoding="utf8")
print("wrote", OUT, len(SVG), "bytes; text width", round(total), "of", W)
