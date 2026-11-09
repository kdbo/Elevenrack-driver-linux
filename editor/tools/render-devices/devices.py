# Geometry, layout and artwork of each rendered device, in cm with the
# origin at the centre of the enclosure's top view, y up the image.
# Imported by render_pedal.py (inside Blender, to build the model) and by
# art.py (plain Python with PIL, to draw the printed artwork); neither
# side imports anything the other lacks.

import math
import os

SCRIPT_FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src', 'fonts', 'Damion.ttf')

INK = '#f6faf4'

# ── Green JRC (TS808-style): green die-cast box, the lower part a step up;
#    knobs Overdrive / Level (0x02 / 0x04) top, Tone (0x03) between ──
JRC = dict(
    w=7.3, upper=(-1.0, 6.3), lower=(-6.3, 1.15), upper_z=3.5, lower_z=3.85,
    paint='#00a05e',
)


def jrc_build(R, art):
    d = JRC
    paint = R.mat('paint', d['paint'], rough=0.32, coat=0.3)
    y0, y1 = d['upper']
    R.box('upper', d['w'] - 0.12, y1 - y0, d['upper_z'], 0, (y0 + y1) / 2, 0, paint, bevel=0.42, seg=6)
    y0, y1 = d['lower']
    R.box('lower', d['w'], y1 - y0, d['lower_z'], 0, (y0 + y1) / 2, 0, paint, bevel=0.38, seg=6)
    for name, (sx, sy, x, y, z) in art.items():
        R.decal(name, art_path(name), sx, sy, x, y, z + 0.004)
    # LED (off; the editor lights it) in a dark bezel
    R.cyl('led-bezel', 0.3, 0.06, 0, 5.75, d['upper_z'], R.mat('bezel', '#1a1a1a', rough=0.5))
    R.cyl('led', 0.21, 0.14, 0, 5.75, d['upper_z'], R.mat('led', '#5a1410', rough=0.15, coat=1.0), bevel=0.06)
    # square metal footswitch in its frame
    metal = R.mat('switch', '#d8d0bd', rough=0.28, metal=1.0)
    R.box('sw-frame', 2.5, 2.2, 0.12, 0, -3.45, d['lower_z'], R.mat('sw-frame', '#c9c1ad', rough=0.35, metal=1.0), bevel=0.1)
    R.box('sw', 1.95, 1.7, 0.42, 0, -3.45, d['lower_z'] + 0.1, metal, bevel=0.14)
    # jacks on the sides of the lower part
    nut = R.mat('nut', '#c9cdd2', rough=0.25, metal=1.0)
    for sx in (-1, 1):
        R.cyl('jack-%d' % sx, 0.42, 0.55, sx * (d['w'] / 2 + 0.2), 0.0, 1.6, nut, verts=6, rot=(0, 1.5708, 0))
        R.cyl('sleeve-%d' % sx, 0.3, 0.8, sx * (d['w'] / 2 + 0.55), 0.0, 1.6, nut, rot=(0, 1.5708, 0))


def jrc_knob(R, pointer):
    # large flat-topped black knob on a notched skirt, white line at the rim
    black = R.mat('knob', '#18181a', rough=0.42)
    if pointer:
        R.box('pointer', 0.09, 0.36, 0.02, 0, 0.62, 1.31, R.mat('ptr', '#f2f2f2', rough=0.5, emit='#ffffff'))
        return
    import bpy, math
    R.cyl('skirt', 0.98, 0.32, 0, 0, 0, black, bevel=0.06)
    sk = bpy.context.object
    # square notches round the skirt rim
    for i in range(18):
        a = i * 2 * math.pi / 18
        R.box('notch', 0.2, 0.26, 0.4, math.cos(a) * 0.98, math.sin(a) * 0.98, -0.02, black)
        n = bpy.context.object
        n.rotation_euler = (0, 0, a)
        m = sk.modifiers.new('n%d' % i, 'BOOLEAN')
        m.operation = 'DIFFERENCE'
        m.object = n
        n.hide_render = True
    R.cyl('body', 0.84, 1.1, 0, 0, 0.2, black, bevel=0.08)
    R.cyl('top', 0.8, 0.02, 0, 0, 1.29, R.mat('top', '#1b1b1d', rough=0.7))


# ── Black Op (RAT-style): matte plate between crinkle side walls, jacks on
#    the top edge; Distortion / Cut / Volume (0x02 / 0x03 / 0x04) ──
def blackop_build(R, art):
    wall = R.crinkle('wall', '#111113', rough=0.85, scale=40, strength=0.8)
    for sx in (-1, 1):
        R.box('wall', 0.55, 12.0, 4.3, sx * 4.55, 0, 0, wall, bevel=0.15)
    R.box('plate', 8.6, 11.2, 4.0, 0, 0, 0, R.mat('plate', '#18181a', rough=0.6), bevel=0.12)
    decals(R, art)
    nut = R.mat('nut', '#c9cdd2', rough=0.22, metal=1.0)
    for sx in (-1, 1):
        R.cyl('jack', 0.32, 1.0, sx * 2.3, 6.0, 2.2 - 0.5, nut, rot=(1.5708, 0, 0))
        R.cyl('jack-nut', 0.46, 0.22, sx * 2.3, 5.68, 2.2 - 0.11, nut, verts=6, rot=(1.5708, 0, 0))
    stomp(R, 0, -4.0, 4.0)
    led(R, -1.35, -4.0, 4.0, '#4a1210', '#3a3a3c', r=0.16)


def blackop_knob(R, pointer):
    if pointer:
        R.box('pointer', 0.08, 0.34, 0.02, 0, 0.48, 1.41, R.mat('ptr', '#f2f2f2', rough=0.5, emit='#ffffff'))
        return
    black = R.mat('knob', '#161618', rough=0.4)
    R.cyl('skirt', 0.8, 0.25, 0, 0, 0, black, bevel=0.05)
    R.cyl('body', 0.7, 1.35, 0, 0, 0.05, black, bevel=0.06)
    R.ribs(40, 0.71, 1.05, 0.25, 0.05, 0.09, black)
    R.cyl('top', 0.67, 0.03, 0, 0, 1.38, R.mat('top', '#1c1c1e', rough=0.75))


# ── White Boost (RC-booster-style): textured white box; Gain / Treble over
#    Volume / Bass (0x02 0x03 / 0x05 0x04); blue LED over a stomp switch ──
def white_build(R, art):
    R.box('box', 6.0, 11.2, 3.1, 0, 0, 0, R.crinkle('paint', '#efeee8', rough=0.5, scale=140, strength=0.22), bevel=0.55, seg=8)
    decals(R, art)
    jacks_side(R, 3.0, 0.6, 1.5)
    led(R, 0, -2.35, 3.1, '#1c3a5a', '#c9cdd2', r=0.2, metal_bezel=True)
    stomp(R, 0, -3.75, 3.1)


def white_knob(R, pointer):
    chrome = R.mat('chrome', '#d4d8dd', rough=0.18, metal=1.0)
    if pointer:
        R.prism('wedge', [(-0.17, 0.58), (0.17, 0.58), (0.0, 1.0)], 0.26, 0.04, chrome, bevel=0.03)
        return
    import bpy
    R.cyl('skirt', 0.78, 0.32, 0, 0, 0, chrome, bevel=0.04)
    R.ribs(44, 0.78, 0.28, 0.02, 0.04, 0.07, chrome)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.66, segments=64, ring_count=32, location=(0, 0, 0.3))
    d = bpy.context.object
    d.scale = (1, 1, 0.62)
    R.finish(d, R.mat('dome', '#0c0c0e', rough=0.12, coat=1.0))


# ── DC Distortion (Avid's own design): rounded box in burnt metallic
#    orange, wider at the top; Level / Treble / Bass (0x05 0x03 0x04) over
#    the big Distortion knob (0x02) ──
DC_OUTLINE = dict(w_top=6.3, w_bot=5.4, y0=-6.0, y1=6.0, r_top=1.5, r_bot=1.9)


def dc_build(R, art):
    paint = R.flake('paint', '#b0581a')
    R.prism('body', R.rounded_outline(**DC_OUTLINE), 3.4, 0, paint, bevel=0.45)
    R.box('ridge', 6.0, 0.14, 0.05, 0, 2.55, 3.4, paint, bevel=0.03)
    decals(R, art)
    jacks_side(R, 2.95, 0.5, 1.4)
    led(R, 0, -2.25, 3.4, '#1c4a56', '#3a1a08', r=0.19)
    sw = R.mat('chrome', '#d4d8dd', rough=0.16, metal=1.0)
    R.box('sw-ring', 1.25, 1.35, 0.12, 0, -3.95, 3.4, sw, bevel=0.3)
    R.box('sw', 0.98, 1.08, 0.55, 0, -3.95, 3.45, sw, bevel=0.26, seg=8)


def dc_knob(R, pointer):
    black = R.mat('knob', '#121214', rough=0.25, coat=0.6)
    if pointer:
        R.prism('nub', [(-0.2, 0.52), (0.2, 0.52), (0.0, 0.86)], 0.5, 0.02, black, bevel=0.05)
        return
    R.cyl('knob', 0.62, 0.72, 0, 0, 0, black, bevel=0.26)


# ── Tri-Knob Fuzz (Big-Muff-style): brushed steel box, jacks on the top
#    edge; Volume / Tone / Sustain (0x04 / 0x03 / 0x02) ──
def fuzz_build(R, art):
    R.box('box', 9.6, 11.0, 3.6, 0, 0, 0, R.brushed('steel', '#cfd1d4'), bevel=0.14)
    decals(R, art)
    nut = R.mat('nut', '#c9cdd2', rough=0.22, metal=1.0)
    for sx in (-1, 1):
        R.cyl('jack', 0.32, 1.0, sx * 3.4, 5.9, 2.0 - 0.5, nut, rot=(1.5708, 0, 0))
        R.cyl('jack-nut', 0.46, 0.22, sx * 3.4, 5.58, 2.0 - 0.11, nut, verts=6, rot=(1.5708, 0, 0))
    screw = R.mat('screw', '#d4d8dd', rough=0.3, metal=1.0)
    for sx in (-1, 1):
        for y in (1.6, -2.6):
            R.cyl('screw', 0.2, 0.06, sx * 4.5, y, 3.6, screw, bevel=0.03)
    led(R, -1.55, 2.0, 3.6, '#4a1410', '#222224', r=0.17)
    stomp(R, 0, -3.6, 3.6)


def fuzz_knob(R, pointer):
    if pointer:
        R.box('pointer', 0.07, 0.32, 0.02, 0, 0.55, 1.08, R.mat('ptr', '#f2f2f2', rough=0.5, emit='#ffffff'))
        return
    R.cyl('nut', 0.98, 0.12, 0, 0, 0, R.mat('nut', '#c9cdd2', rough=0.22, metal=1.0), verts=6)
    R.cyl('knob', 0.9, 0.95, 0, 0, 0.11, R.mat('knob', '#18181a', rough=0.5), bevel=0.1)


# ── Plexi head (1959 Super Lead style), its front laid face-up under the
#    camera, drawn as an inked, aged illustration: worn black levant tolex
#    with the gold-brown backing showing through at its edges, gold piping
#    round the front and under the name, the name in raised cream script, a
#    recessed brushed gold panel with two bat toggles, a square red jewel,
#    six gold-capped knobs (Presence Bass Middle Treble Vol I Vol II) and
#    four inputs; the handle with gold end caps on the top edge.
#    19 x 7.25 cm = the editor's 760 x 290 px head. ──
PLEXI = dict(w=19.0, h=7.25, name_h=3.6, panel=(-7.2, 7.2, -3.2, -1.15))
PLEXI_KNOBS = [(-3.55 + 1.5 * i, -2.25) for i in range(6)]


def plexi_build(R, art):
    import bpy
    d = PLEXI
    tolex = R.worn('tolex', '#141312', '#a8772c', rough=0.62, under_rough=0.45, edge=0.35, amount=0.5, scale=3.0, scuffs=0.05, grain=55.0)
    R.box('front', d['w'], d['h'], 2.0, 0, 0, 0, tolex, bevel=0.8, seg=10)
    # gold piping: a round cord, round the front and under the name
    gold_cord = R.worn('piping', '#c9a04a', '#7a5a22', rough=0.4, under_rough=0.6, edge=0.05, amount=0.25, scale=8.0, scuffs=0.08)
    i, t = 0.55, 0.12
    x0, x1, y0, y1 = -d['w'] / 2 + i, d['w'] / 2 - i, -d['h'] / 2 + i, d['h'] / 2 - i
    yl = d['h'] / 2 - d['name_h']
    for (sx, sy, x, y) in ((x1 - x0 + t, t, 0, y1), (x1 - x0 + t, t, 0, y0), (t, y1 - y0, x0, 0), (t, y1 - y0, x1, 0), (x1 - x0, t, 0, yl)):
        R.box('piping', sx, sy, t, x, y, 1.97, gold_cord, bevel=t * 0.49, seg=6)
    # the panel sits in a recess of the tolex
    px0, px1, py0, py1 = d['panel']
    R.box('recess', px1 - px0 + 0.5, py1 - py0 + 0.45, 0.2, (px0 + px1) / 2, (py0 + py1) / 2, 1.85, R.mat('recess', '#080808', rough=0.8), bevel=0.15)
    gold = R.mat('gold', '#e0c27a', rough=0.32, metal=0.85)
    R._noise_into(gold, 'Roughness', 4.0, detail=12.0, lo=0.24, hi=0.42, stretch=(0.4, 50.0, 1.0))
    R.box('panel', px1 - px0, py1 - py0, 0.12, (px0 + px1) / 2, (py0 + py1) / 2, 1.95, gold, bevel=0.06)
    decals(R, art)
    top = 2.07
    # the name: raised cream script
    R.text3d('logo', 'Plexi', SCRIPT_FONT, 2.6, 0, d['h'] / 2 - d['name_h'] / 2 - 0.3, 2.0,
             R.mat('logo', '#f0e3c0', rough=0.3, coat=0.5), depth=0.12, bevel=0.03)
    # bat toggles and the square red jewel
    chrome = R.mat('chrome', '#d6d9dd', rough=0.12, metal=1.0)
    for x in (-5.75, -4.75):
        R.cyl('tog-nut', 0.3, 0.12, x, -2.25, top, chrome, verts=6, bevel=0.03)
        R.cyl('tog-ring', 0.24, 0.1, x, -2.25, top + 0.1, chrome, bevel=0.03)
        R.cyl('tog-bat', 0.09, 0.62, x, -2.42, top + 0.2, chrome, bevel=0.05, rot=(-1.1, 0.0, 0.0))
    R.box('jewel-bezel', 0.7, 0.7, 0.1, -3.75 + 0.0, -2.25, top, R.mat('bezel', '#2a2a2c', rough=0.4), bevel=0.04)
    R.prism('jewel', [(-0.27, -0.27), (0.27, -0.27), (0.27, 0.27), (-0.27, 0.27)], 0.22, top + 0.08,
            R.mat('jewel', '#b0140c', rough=0.06, coat=1.0, emit='#ff2010'), bevel=0.1)
    # four inputs
    nut = R.mat('nut', '#c9cdd2', rough=0.22, metal=1.0)
    for x in (5.15, 6.45):
        for y in (-1.8, -2.75):
            R.cyl('in-nut', 0.32, 0.1, x, y, top, nut, verts=6)
            R.cyl('in', 0.24, 0.14, x, y, top + 0.05, nut, bevel=0.03)
            R.cyl('in-hole', 0.13, 0.02, x, y, top + 0.19, R.mat('hole', '#050505', rough=0.9))


def plexi_knob(R, pointer):
    if pointer:
        R.box('pointer', 0.05, 0.28, 0.02, 0, 0.17, 0.99, R.mat('ptr', '#1a1206', rough=0.6))
        return
    black = R.mat('knob', '#121214', rough=0.38)
    R.cyl('skirt', 0.6, 0.18, 0, 0, 0, black, bevel=0.04)
    R.cyl('body', 0.5, 0.75, 0, 0, 0.1, black, bevel=0.05)
    R.ribs(28, 0.5, 0.6, 0.18, 0.05, 0.08, black)
    # the gold cap, a shallow dome
    import bpy
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.44, segments=48, ring_count=24, location=(0, 0, 0.8))
    cap = bpy.context.object
    cap.scale = (1, 1, 0.42)
    R.finish(cap, R.mat('cap', '#e2c27a', rough=0.22, metal=0.9))


# ── C1 Chorus/Vibrato (CE-1 style): wide hammertone casting, a brushed
#    plate with Chorus (0x02) and the joined Depth / Rate (0x03 / 0x04) rings,
#    the sync picker where the original's level knob sits; two lamps and two
#    footswitches: bypass on the left, Mode (0x05 Chorus / Vibrato) on the
#    right with its lamp ──
def ce1_build(R, art):
    body = R.crinkle('body', '#4b5350', rough=0.5, scale=7.0, strength=0.5)
    R.box('body', 15.0, 10.4, 3.0, 0, 0, 0, body, bevel=0.6, seg=6)
    R.box('lip', 14.4, 0.7, 0.45, 0, 4.7, 2.8, body, bevel=0.2)
    R.box('plate', 13.4, 3.6, 0.06, 0, 2.35, 3.0, R.brushed('alu', '#cfd2d6', rough=0.3), bevel=0.03)
    decals(R, art)
    nut = R.mat('nut', '#c9cdd2', rough=0.22, metal=1.0)
    for x in (-4.5, -2.8, -1.1):
        R.cyl('jack', 0.3, 0.9, x, 5.55, 1.7 - 0.45, nut, rot=(1.5708, 0, 0))
        R.cyl('jack-nut', 0.44, 0.2, x, 5.25, 1.7 - 0.1, nut, verts=6, rot=(1.5708, 0, 0))
    # power rocker in its black surround
    R.box('rocker-bed', 0.9, 2.2, 0.05, 6.05, 2.35, 3.06, R.mat('bed', '#151517', rough=0.6), bevel=0.2)
    R.box('rocker', 0.5, 1.2, 0.35, 6.05, 2.5, 3.06, R.mat('rocker', '#0e0e10', rough=0.3), bevel=0.12)
    chrome = R.mat('chrome', '#d4d8dd', rough=0.16, metal=1.0)
    for x in (-4.6, 4.6):
        led(R, x, -0.75, 3.0, '#4a1210', '#2a2a2c', r=0.2)
        R.cyl('sw-plate', 1.05, 0.05, x, -2.95, 3.0, R.brushed('swplate', '#d0d3d7', rough=0.25), bevel=0.02)
        stomp(R, x, -2.95, 3.05)


def ce1_knob(R, pointer):
    if pointer:
        R.box('pointer', 0.06, 0.26, 0.02, 0, 0.27, 0.9, R.mat('ptr', '#f2f2f2', rough=0.5, emit='#ffffff'))
        return
    R.cyl('ring', 0.64, 0.25, 0, 0, 0, R.mat('chrome', '#d4d8dd', rough=0.16, metal=1.0), bevel=0.05)
    black = R.mat('knob', '#151517', rough=0.45)
    R.cyl('cap', 0.5, 0.65, 0, 0, 0.22, black, bevel=0.06)
    R.ribs(32, 0.5, 0.5, 0.25, 0.04, 0.07, black)


# ── Vibe Phaser (Uni-Vibe style console): grey hammertone box, a black
#    plate framed in white with the name in script; Volume (0x04), the red /
#    white Chorus-Vibrato rocker (Mode 0x05), Intensity (Depth 0x03) and
#    Speed (Rate 0x02, on the original's foot controller) in chicken-head
#    knobs; the jewel lamp; jacks, the sync picker and the power toggle
#    (bypass) along the bottom ──
def vibe_build(R, art):
    R.box('body', 15.0, 9.9, 3.2, 0, 0, 0, R.crinkle('body', '#6a6c64', rough=0.6, scale=6.0, strength=0.45), bevel=0.25)
    R.box('plate', 13.9, 8.7, 0.06, 0, 0.1, 3.2, R.brushed('plate', '#19191b', rough=0.32), bevel=0.02)
    decals(R, art)
    screw = R.mat('screw', '#c9cdd2', rough=0.3, metal=1.0)
    for x, y in ((-6.6, 4.1), (6.6, 4.1), (-6.6, -3.9), (6.6, -3.9)):
        R.cyl('screw', 0.13, 0.05, x, y, 3.26, screw)
    # the rocker, red half and white half
    R.box('rocker-bed', 2.2, 1.0, 0.05, -2.0, 1.15, 3.26, R.mat('bed', '#0a0a0b', rough=0.6), bevel=0.04)
    R.box('rocker-red', 0.98, 0.78, 0.3, -2.5, 1.15, 3.28, R.mat('red', '#c41e1e', rough=0.3, coat=0.5), bevel=0.06)
    R.box('rocker-white', 0.98, 0.78, 0.3, -1.5, 1.15, 3.28, R.mat('white', '#ecebe6', rough=0.3, coat=0.5), bevel=0.06)
    # jewel lamp in a chrome bezel
    R.cyl('lamp-bezel', 0.55, 0.3, 6.0, 1.25, 3.26, R.mat('chrome', '#d4d8dd', rough=0.12, metal=1.0), bevel=0.08)
    R.cyl('lamp', 0.38, 0.4, 6.0, 1.25, 3.4, R.mat('jewel', '#7a0e08', rough=0.08, coat=1.0), verts=12, bevel=0.14)
    nut = R.mat('nut', '#cbb88a', rough=0.3, metal=1.0)
    for x in (-5.5, -3.9, -1.1):
        R.cyl('jack-nut', 0.48, 0.16, x, -2.2, 3.26, nut, verts=6)
        R.cyl('jack-hole', 0.3, 0.02, x, -2.2, 3.42, R.mat('hole', '#050505', rough=0.9))
    # power toggle: chrome bat on a nut
    tg = R.mat('chrome', '#d4d8dd', rough=0.12, metal=1.0)
    R.cyl('tog-nut', 0.42, 0.14, 6.0, -2.2, 3.26, tg, verts=6)
    R.cyl('tog-bat', 0.14, 0.95, 6.0, -2.2, 3.4, tg, bevel=0.07, rot=(0.5, 0.0, 0.0))


def vibe_knob(R, pointer):
    black = R.mat('knob', '#111113', rough=0.22, coat=0.6)
    if pointer:
        # the chicken-head wing, with a white line inlaid along it
        R.prism('wing', [(-0.34, -0.2), (0.34, -0.2), (0.12, 1.02), (-0.12, 1.02)], 0.55, 0.0, black, bevel=0.1)
        R.box('line', 0.05, 0.75, 0.02, 0, 0.5, 0.56, R.mat('ptr', '#f2f2f2', rough=0.5))
        return
    R.cyl('boss', 0.5, 0.48, 0, 0, 0, black, bevel=0.12)


# ── Orange Phaser (Phase 90 style): glossy orange box, one big scalloped
#    Speed knob (Rate 0x02), the sync picker where the maker's name sits;
#    LED, stomp switch, the name in script along the bottom ──
def phaser_build(R, art):
    R.box('box', 6.0, 11.2, 3.1, 0, 0, 0, R.mat('paint', '#f07a0c', rough=0.22, coat=0.8), bevel=0.55, seg=8)
    decals(R, art)
    jacks_side(R, 3.0, 0.9, 1.5)
    led(R, 0, -0.65, 3.1, '#3a0e0a', '#1a1a1a', r=0.2)
    stomp(R, 0, -2.35, 3.1)


def phaser_knob(R, pointer):
    black = R.mat('knob', '#0c0c0e', rough=0.14, coat=1.0)
    if pointer:
        R.box('pointer', 0.07, 0.62, 0.02, 0, 0.36, 0.86, R.mat('ptr', '#f4f4f4', rough=0.4))
        return
    R.cyl('skirt', 1.0, 0.18, 0, 0, 0, black, bevel=0.05)
    # nine shallow scallops round the rim
    r = lambda t: 0.86 + 0.07 * math.cos(9 * t)
    lobes = [(math.cos(t) * r(t), math.sin(t) * r(t)) for t in (i * 2 * math.pi / 108 for i in range(108))]
    R.prism('body', lobes, 0.7, 0.15, black, bevel=0.16)


# ── Gray Compressor (Ross style): glossy grey box, jacks on the top edge,
#    the LED between OUT and IN; Level (0x03) and Sustain (0x02) as big
#    black knobs in black rings; the name in serif, COMPRESSOR at the foot ──
def gray_build(R, art):
    R.box('box', 7.0, 10.6, 3.3, 0, 0, 0, R.mat('paint', '#9ba1a7', rough=0.25, coat=0.7), bevel=0.5, seg=8)
    decals(R, art)
    nut = R.mat('nut', '#c9cdd2', rough=0.22, metal=1.0)
    for sx in (-1, 1):
        R.cyl('jack', 0.32, 1.0, sx * 2.3, 5.75, 1.9 - 0.5, nut, rot=(1.5708, 0, 0))
        R.cyl('jack-nut', 0.46, 0.22, sx * 2.3, 5.43, 1.9 - 0.11, nut, verts=6, rot=(1.5708, 0, 0))
    led(R, 0, 4.35, 3.3, '#4a1210', '#2a2a2c', r=0.17)
    stomp(R, 0, -3.0, 3.3)


def gray_knob(R, pointer):
    black = R.mat('knob', '#0f0f11', rough=0.3, coat=0.4)
    if pointer:
        # the two grip grooves and the white line turn with the knob
        groove = R.mat('groove', '#262628', rough=0.5)
        for x in (-0.38, 0.38):
            R.box('groove', 0.07, 1.7, 0.02, x, 0, 0.82, groove)
        R.box('pointer', 0.07, 0.5, 0.02, 0, 0.55, 0.83, R.mat('ptr', '#f4f4f4', rough=0.4))
        return
    R.cyl('ring', 1.2, 0.12, 0, 0, 0, black, bevel=0.04)
    R.cyl('knob', 1.0, 0.8, 0, 0, 0.02, black, bevel=0.1)


# ── EP Tape Echo (EP-3 style), the closed case from the front: black tolex
#    rim, the coiled cords in the bay on the left, the diamond-plate cover
#    with its embossed rings and badge, the head carriage in the cover's
#    slot (the Delay slider, 0x04) over the printed ECHO DELAY scale; the
#    diamond-plate front strip: echo on/off toggle (bypass), Rec Level
#    (0x06), Feedback (0x03), Mix (0x02), Head Tilt (0x08) and Wow/Flutter
#    (0x07), the jacks, the Expanded (0x09) and Tape Hiss (0x0A) toggles
#    with their lamps, and the sync picker ──
def ep3_build(R, art):
    import bpy
    tolex = R.pebble('tolex', '#121214', rough=0.6, scale=9.0, strength=0.8)
    R.box('floor', 18.0, 12.0, 2.6, 0, 0, 0, R.mat('inside', '#0c0c0d', rough=0.8), bevel=0.3)
    for (sx, sy, x, y) in ((18.6, 0.75, 0, 5.85), (18.6, 0.75, 0, -5.85), (0.75, 12.4, -8.95, 0), (0.75, 12.4, 8.95, 0)):
        R.box('rim', sx, sy, 3.6, x, y, 0, tolex, bevel=0.25)
    plate = R.diamond('plate', '#8d9196', rough=0.42, metal=0.7, scale=5.0, strength=0.7)
    # the cover: upper part with embossed rings, and the band with the carriage slot
    R.box('cover', 12.1, 5.0, 0.6, 2.05, 3.0, 2.6, plate, bevel=0.12)
    R.box('band', 12.1, 1.8, 0.6, 2.05, -0.5, 2.6, plate, bevel=0.12)
    R.box('slot', 8.2, 0.42, 0.1, 2.2, -0.5, 3.16, R.mat('slot', '#050506', rough=0.9), bevel=0.04)
    ring = R.mat('ring', '#9a9ea3', rough=0.3, metal=0.7)
    for r in (2.15, 1.55, 0.95):
        bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=0.045, major_segments=96, minor_segments=8, location=(2.2, 3.05, 3.2))
        R.finish(bpy.context.object, ring)
    screw = R.mat('screw', '#cfd3d8', rough=0.25, metal=1.0)
    for x in (-3.4, 7.5):
        R.cyl('screw', 0.2, 0.1, x, 0.65, 3.2, screw, bevel=0.05)
    # front strip for the trims, and a panel in the bay on the left for the main controls
    R.box('strip', 17.0, 3.7, 0.4, 0, -3.65, 2.6, plate, bevel=0.06)
    R.box('bay', 4.5, 6.75, 0.6, -6.35, 2.0, 2.6, plate, bevel=0.12)
    decals(R, art)
    chrome = R.mat('chrome', '#d4d8dd', rough=0.12, metal=1.0)
    for x in (1.6, 3.0):
        R.cyl('jack-nut', 0.38, 0.12, x, -3.65, 3.0, chrome, verts=6)
        R.cyl('jack-ring', 0.3, 0.16, x, -3.65, 3.05, chrome, bevel=0.04)
        R.cyl('jack-hole', 0.15, 0.02, x, -3.65, 3.22, R.mat('hole', '#050505', rough=0.9))
    for x, y, z in ((-7.4, -3.65, 3.0), (-2.0, -3.65, 3.0), (-0.6, -3.65, 3.0)):
        R.cyl('tog-nut', 0.3, 0.12, x, y, z, chrome, verts=6)
        R.cyl('tog-bat', 0.1, 0.72, x, y, z + 0.12, chrome, bevel=0.05, rot=(0.45, 0.0, 0.0))


def ep3_knob(R, pointer):
    # a spun-aluminium knob on a dark skirt
    if pointer:
        R.box('pointer', 0.06, 0.26, 0.02, 0, 0.32, 0.9, R.mat('ptr', '#1a1a1c', rough=0.5))
        return
    R.cyl('skirt', 0.62, 0.12, 0, 0, 0, R.mat('skirt', '#151517', rough=0.4), bevel=0.03)
    R.cyl('cap', 0.52, 0.78, 0, 0, 0.1, R.mat('alu', '#d0d3d7', rough=0.18, metal=1.0), bevel=0.12)


def ep3_carriage(R):
    # the moving head carriage: a chrome block with a black thumb knob
    R.box('carriage', 1.0, 1.3, 0.35, 0, 0, 0, R.mat('chrome', '#d4d8dd', rough=0.14, metal=1.0), bevel=0.08)
    R.cyl('thumb', 0.32, 0.5, 0, 0, 0.3, R.mat('thumb', '#121214', rough=0.3, coat=0.5), bevel=0.08)


# ── Roto Speaker (Leslie 122 style), the cabinet's front: walnut, louvred
#    above (horn rotor behind) and below (drum behind); a brass control
#    plate between with Balance (0x04), the Speed and Type pickers (0x02,
#    0x03), the pilot lamp and a bypass toggle ──
def roto_build(R, art):
    walnut = R.wood('walnut', '#7a4f2c', '#4a2c16')
    R.box('cabinet', 12.0, 13.0, 2.0, 0, 0, 0, walnut, bevel=0.35)
    dark = R.mat('inside', '#070708', rough=0.9)
    for y0, y1 in ((1.9, 5.8), (-5.8, -1.3)):
        R.box('opening', 10.6, y1 - y0, 0.1, 0, (y0 + y1) / 2, 1.95, dark)
        # what shows behind the louvres: the horn rotor above, the drum below
        if y0 > 0:
            R.box('horn', 7.5, 1.1, 0.05, 0, (y0 + y1) / 2, 2.0, R.mat('horn', '#1a1a1c', rough=0.4), bevel=0.4)
        else:
            R.cyl('drum', 2.6, 0.05, 0, (y0 + y1) / 2, 2.0, R.mat('drum', '#141416', rough=0.6))
        n = int((y1 - y0) / 0.62)
        for i in range(n):
            y = y0 + 0.31 + i * (y1 - y0 - 0.62) / max(1, n - 1)
            R.box('louvre', 10.6, 0.36, 0.22, 0, y, 2.0, walnut, bevel=0.08)
    R.box('plate', 9.0, 2.3, 0.08, 0, 0.3, 2.0, R.brushed('brass', '#c9a75a', rough=0.28), bevel=0.04)
    decals(R, art)
    R.cyl('lamp-bezel', 0.32, 0.14, 3.6, 0.65, 2.08, R.mat('chrome', '#d4d8dd', rough=0.12, metal=1.0), bevel=0.04)
    R.cyl('lamp', 0.22, 0.2, 3.6, 0.65, 2.15, R.mat('jewel', '#6a3a06', rough=0.08, coat=1.0), verts=12, bevel=0.08)
    chrome = R.mat('chrome', '#d4d8dd', rough=0.12, metal=1.0)
    R.cyl('tog-nut', 0.3, 0.12, 3.6, -0.25, 2.08, chrome, verts=6)
    R.cyl('tog-bat', 0.1, 0.7, 3.6, -0.25, 2.2, chrome, bevel=0.05, rot=(0.45, 0.0, 0.0))


# ── Blackpanel Spring Reverb (a blackface amp's front): tolex above, the
#    black control panel with Dwell / Tone / Mix (Decay 0x02, Tone 0x03,
#    Mix 0x04) in skirted knobs whose numbers turn with them, the name in
#    script and the jewel lamp (also the bypass); grille cloth below ──
def bf_build(R, art):
    tolex = R.pebble('tolex', '#151517', rough=0.6, scale=9.0, strength=0.8)
    R.box('tolex', 16.0, 1.4, 1.6, 0, 2.9, 0, tolex, bevel=0.3)
    R.box('panel', 16.0, 3.6, 1.4, 0, 0.5, 0, R.mat('panel', '#121214', rough=0.35, coat=0.3), bevel=0.05)
    R.box('trim', 15.6, 0.1, 0.03, 0, 2.2, 1.4, R.mat('trim', '#c9cdd2', rough=0.25, metal=1.0))
    R.box('grille', 16.0, 3.0, 1.2, 0, -2.75, 0, R.weave('grille', '#a8a9a6', '#2a2a2a'), bevel=0.1)
    decals(R, art)
    R.cyl('lamp-bezel', 0.42, 0.2, 6.6, 0.55, 1.4, R.mat('chrome', '#d4d8dd', rough=0.12, metal=1.0), bevel=0.06)
    R.cyl('lamp', 0.3, 0.3, 6.6, 0.55, 1.5, R.mat('jewel', '#7a0e08', rough=0.08, coat=1.0), verts=12, bevel=0.12)


def bf_knob(R, pointer):
    if pointer:
        # the skirt's numbers, which turn with the knob
        R.decal('numbers', art_path('numbers'), 1.3, 1.3, 0, 0, 0.19)
        return
    black = R.mat('knob', '#101012', rough=0.3, coat=0.4)
    R.cyl('skirt', 0.62, 0.18, 0, 0, 0, black, bevel=0.03)
    R.cyl('body', 0.42, 0.55, 0, 0, 0.15, black, bevel=0.05)
    R.ribs(28, 0.42, 0.4, 0.2, 0.035, 0.06, black)
    R.cyl('cap', 0.32, 0.05, 0, 0, 0.7, R.brushed('cap', '#d8dbdf', rough=0.2), bevel=0.02)


# ── BBD Delay (Deluxe Memory Man style): a dull aluminium box, the lower
#    left printed black on the diagonal; Level (Input 0x06), Blend (Mix
#    0x02), Feedback (0x03), Delay (0x04) and Chorus-Vibrato (Depth 0x07);
#    slide switches for Chorus / Vibrato (0x08), Expanded Delay (0x09) and
#    Noise (0x0A); jacks on the top edge, the power lamp, the sync picker ──
def mm_build(R, art):
    R.box('box', 12.4, 10.6, 3.0, 0, 0, 0, R.brushed('alu', '#c9c5bd', rough=0.38), bevel=0.15)
    decals(R, art)
    nut = R.mat('nut', '#c9cdd2', rough=0.22, metal=1.0)
    for x in (-2.4, -0.4, 1.6):
        R.cyl('jack', 0.32, 1.0, x, 5.75, 1.7 - 0.5, nut, rot=(1.5708, 0, 0))
        R.cyl('jack-nut', 0.46, 0.22, x, 5.43, 1.7 - 0.11, nut, verts=6, rot=(1.5708, 0, 0))
    slide = R.mat('slide', '#121214', rough=0.4)
    for x, y in ((4.4, 4.55), (-2.9, -4.45), (-1.3, -4.45)):
        R.box('slide-bed', 1.5, 0.55, 0.04, x, y, 3.0, R.mat('bed', '#0a0a0b', rough=0.6), bevel=0.05)
        R.box('slide', 0.55, 0.42, 0.3, x, y, 3.02, slide, bevel=0.06)
    led(R, -4.6, 3.6, 3.0, '#4a1210', '#2a2a2c', r=0.17)
    stomp(R, -5.0, -3.85, 3.0)


def mm_knob(R, pointer):
    if pointer:
        R.box('pointer', 0.07, 0.42, 0.02, 0, 0.4, 0.96, R.mat('ptr', '#f4f4f4', rough=0.4))
        return
    R.cyl('knob', 0.75, 0.95, 0, 0, 0, R.mat('knob', '#101012', rough=0.22, coat=0.6), bevel=0.3)


# ── Rack units (Avid's own designs, drawn as 19-inch rack gear): a ~3U
#    panel with ears, slotted screw holes and chrome handles; the controls
#    and printing differ per unit, all share the rack knob and a rubber
#    bypass button that lights up ──
RACK_W = 18.0


def rack_build(R, art, panel, h=6.7, buttons=()):
    R.box('chassis', RACK_W - 1.6, h - 0.2, 2.5, 0, 0, 0, R.mat('chassis', '#101012', rough=0.6))
    R.box('panel', RACK_W, h, 0.45, 0, 0, 2.5, panel, bevel=0.06)
    decals(R, art)
    dark = R.mat('slot', '#050506', rough=0.9)
    screw = R.mat('screw', '#cfd3d8', rough=0.25, metal=1.0)
    chrome = R.mat('chrome', '#dfe2e6', rough=0.1, metal=1.0)
    for sx in (-1, 1):
        x = sx * (RACK_W / 2 - 0.45)
        for y in (h / 2 - 0.9, -h / 2 + 0.9) if h > 5 else (0.0,):
            R.box('slot', 0.62, 0.32, 0.05, x, y, 2.93, dark, bevel=0.14)
            R.cyl('screw', 0.26, 0.12, x, y, 2.93, screw, bevel=0.06)
        hx = sx * (RACK_W / 2 - 1.1)
        R.box('handle', 0.34, h - 1.6, 0.34, hx, 0, 3.55, chrome, bevel=0.16)
        for y in (h / 2 - 0.8, -h / 2 + 0.8):
            R.cyl('handle-post', 0.2, 0.62, hx, y, 2.95, chrome)
    rubber = R.mat('button', '#2a2a2d', rough=0.55)
    for x, y in buttons:
        R.box('button-bezel', 1.05, 0.85, 0.06, x, y, 2.95, R.mat('bezel', '#0c0c0e', rough=0.5), bevel=0.06)
        R.box('button', 0.85, 0.65, 0.3, x, y, 2.95, rubber, bevel=0.12)


def rack_knob(R, pointer):
    if pointer:
        R.box('pointer', 0.06, 0.3, 0.02, 0, 0.27, 0.78, R.mat('ptr', '#1a1a1c', rough=0.5))
        return
    R.cyl('skirt', 0.6, 0.12, 0, 0, 0, R.mat('skirt', '#121214', rough=0.4), bevel=0.03)
    alu = R.brushed('alu', '#d2d5d9', rough=0.22)
    R.cyl('body', 0.48, 0.65, 0, 0, 0.1, alu, bevel=0.06)
    R.ribs(36, 0.48, 0.5, 0.12, 0.035, 0.06, alu)


def dyn3_build(R, art):
    rack_build(R, art, R.brushed('panel', '#2c2e33', rough=0.35), buttons=[(6.2, 0.1)])


def peq_build(R, art):
    rack_build(R, art, R.brushed('panel', '#c6c9cd', rough=0.3), buttons=[(5.4, 1.9)])


def ddelay_build(R, art):
    rack_build(R, art, R.mat('panel', '#141416', rough=0.4, coat=0.2), buttons=[(6.4, -1.6)])


def esr_build(R, art):
    rack_build(R, art, R.brushed('panel', '#1c2c48', rough=0.35), buttons=[(6.0, 0.2)])


def fxloop_build(R, art):
    rack_build(R, art, R.mat('panel', '#18181b', rough=0.45), h=4.4, buttons=[(6.0, 0.0)])
    nut = R.mat('nut', '#c9cdd2', rough=0.22, metal=1.0)
    for x in (2.6, 4.0):
        R.cyl('jack-nut', 0.42, 0.12, x, 0.0, 2.95, nut, verts=6)
        R.cyl('jack', 0.3, 0.14, x, 0.0, 3.0, nut, bevel=0.04)
        R.cyl('jack-hole', 0.15, 0.02, x, 0.0, 3.14, R.mat('hole', '#050505', rough=0.9))


# ── Multi Chorus (blue), Flanger (purple), Graphic EQ (white): stompboxes
#    of our own design in the same drawn style ──
def mchorus_build(R, art):
    R.box('box', 12.5, 11.4, 3.2, 0, 0, 0, R.flake('paint', '#1f5cae', metal=0.5), bevel=0.5, seg=6)
    decals(R, art)
    slide = R.mat('slide', '#121214', rough=0.4)
    R.box('slide-bed', 1.5, 0.55, 0.04, 4.3, 0.7, 3.2, R.mat('bed', '#0a0a0b', rough=0.6), bevel=0.05)
    R.box('slide', 0.55, 0.42, 0.3, 4.3, 0.7, 3.22, slide, bevel=0.06)
    jacks_side(R, 6.25, 0.0, 1.6)
    led(R, 0, -2.4, 3.2, '#4a1210', '#2a2a2c', r=0.18)
    stomp(R, 0, -3.95, 3.2)


def flanger_build(R, art):
    R.box('box', 7.4, 11.8, 3.2, 0, 0, 0, R.flake('paint', '#6a2c9e', metal=0.5), bevel=0.5, seg=6)
    decals(R, art)
    jacks_side(R, 3.7, 0.5, 1.6)
    led(R, 0, -2.75, 3.2, '#4a1210', '#2a2a2c', r=0.18)
    stomp(R, 0, -4.15, 3.2)


GEQ_X = [-2.75 + 1.1 * i for i in range(6)]
GEQ_Y = (-0.7, 3.5)                      # each fader's minimum and maximum ends


def geq_build(R, art):
    R.box('box', 7.8, 12.6, 3.0, 0, 0, 0, R.mat('paint', '#eeede8', rough=0.3, coat=0.6), bevel=0.5, seg=6)
    slot = R.mat('slot', '#0a0a0b', rough=0.8)
    for x in GEQ_X:
        R.box('slot', 0.16, GEQ_Y[1] - GEQ_Y[0] + 0.5, 0.05, x, sum(GEQ_Y) / 2, 2.98, slot, bevel=0.06)
    decals(R, art)
    jacks_side(R, 3.9, 0.4, 1.5)
    led(R, 0, -3.15, 3.0, '#4a1210', '#2a2a2c', r=0.18)
    stomp(R, 0, -4.6, 3.0)


def geq_cap(R):
    # a fader cap: black, ridged, with a white line across
    R.box('cap', 0.8, 0.5, 0.45, 0, 0, 0, R.mat('cap', '#141416', rough=0.35), bevel=0.1)
    R.box('line', 0.7, 0.05, 0.02, 0, 0, 0.45, R.mat('line', '#f2f2f2', rough=0.5))


def dc_dist_knob_white(R, pointer):
    # a glossy black knob with a white line, for the blue and purple pedals
    if pointer:
        R.box('pointer', 0.07, 0.38, 0.02, 0, 0.38, 0.9, R.mat('ptr', '#f4f4f4', rough=0.4))
        return
    R.cyl('knob', 0.72, 0.9, 0, 0, 0, R.mat('knob', '#101012', rough=0.2, coat=0.6), bevel=0.28)


# ── 4x12 basketweave cabinet (1960 style), its front: black tolex, a cream
#    piped frame round a basketweave grille, the four speakers' shadows
#    behind the cloth, a brass plate for the name. Body only; the editor
#    writes the cab's name on the plate. 19 x 6.5 cm = the editor's cab. ──
def cab_build(R, art):
    W, H = 19.0, 6.5
    R.box('cab', W, H, 2.0, 0, 0, 0, R.pebble('tolex', '#141416', rough=0.55, scale=14.0, strength=1.2), bevel=0.5, seg=8)
    R.box('baffle', W - 1.2, H - 1.0, 0.05, 0, 0, 1.95, R.mat('baffle', '#050506', rough=0.9))
    for x in (-4.6, 4.6):
        for y in (-1.3, 1.3):
            R.cyl('speaker', 1.15, 0.04, x * 0.95, y * 0.95, 1.97, R.mat('cone', '#0a0a0b', rough=0.8))
    cloth = R.weave('cloth', '#b8a37a', '#6a5838', scale=190.0)   # a fine tan-and-brown basketweave
    cloth.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value = 0.93
    cloth.blend_method = 'BLEND'
    R.box('grille', W - 1.2, H - 1.0, 0.06, 0, 0, 2.0, cloth)
    cream = R.mat('piping', '#efe8d2', rough=0.35, coat=0.3)
    t = 0.16
    x0, x1, y0, y1 = -(W - 1.2) / 2, (W - 1.2) / 2, -(H - 1.0) / 2, (H - 1.0) / 2
    for (sx, sy, x, y) in ((x1 - x0 + t, t, 0, y1), (x1 - x0 + t, t, 0, y0), (t, y1 - y0, x0, 0), (t, y1 - y0, x1, 0)):
        R.box('piping', sx, sy, t, x, y, 1.98, cream, bevel=t * 0.49, seg=6)
    R.box('plate', 4.4, 0.75, 0.06, -6.4, 2.35, 2.05, R.brushed('brass', '#cdb173', rough=0.3), bevel=0.03)


# ── shared parts ──
def decals(R, art):
    for name, (sx, sy, x, y, z) in art.items():
        R.decal(name, art_path(name), sx, sy, x, y, z + 0.004)


def stomp(R, x, y, z):
    # round chrome stomp switch on a hex nut
    chrome = R.mat('chrome', '#d4d8dd', rough=0.16, metal=1.0)
    R.cyl('sw-nut', 0.78, 0.22, x, y, z, chrome, verts=6, bevel=0.04)
    R.cyl('sw-ring', 0.62, 0.3, x, y, z + 0.2, chrome, bevel=0.05)
    R.cyl('sw', 0.5, 0.75, x, y, z + 0.3, chrome, bevel=0.16)


def led(R, x, y, z, lens, bezel, r=0.18, metal_bezel=False):
    R.cyl('led-bezel', r + 0.1, 0.08, x, y, z, R.mat('bezel', bezel, rough=0.25 if metal_bezel else 0.5, metal=1.0 if metal_bezel else 0.0), bevel=0.03)
    R.cyl('led', r, 0.16, x, y, z, R.mat('lens', lens, rough=0.12, coat=1.0), bevel=r * 0.4)


def jacks_side(R, half_w, y, z):
    nut = R.mat('nut', '#c9cdd2', rough=0.22, metal=1.0)
    for sx in (-1, 1):
        R.cyl('jack-nut', 0.42, 0.3, sx * (half_w + 0.15), y, z - 0.15, nut, verts=6, rot=(0, 1.5708, 0))
        R.cyl('jack', 0.3, 0.75, sx * (half_w + 0.5), y, z - 0.375, nut, rot=(0, 1.5708, 0))


def art_path(name):
    import os
    return os.path.join(ART_DIR, name + '.png')


ART_DIR = '.'

DEVICES = {
    'cab-412': dict(
        frame=(19.0, 6.5), samples=128,
        build=cab_build, build_knob=lambda R, pointer: None, knob=dict(frame=0.5), knobs={},
        switch=(0.0, 0.0, 0.0), led=(0.0, 0.0), decals={},
    ),
    'dyn3': dict(
        frame=(18.4, 7.2), build=dyn3_build, build_knob=rack_knob, knob=dict(frame=1.4),
        knobs={'02': (-5.4, 0.1), '03': (-3.5, 0.1), '04': (-1.6, 0.1), '05': (0.3, 0.1), '06': (2.2, 0.1), '07': (4.1, 0.1)},
        switch=(6.2, 0.1, 0.5), led=(6.2, 0.1),
        decals={'panel': (RACK_W, 6.7, 0, 0, 2.95)},
    ),
    'param-eq': dict(
        frame=(18.4, 7.2), build=peq_build, build_knob=rack_knob, knob=dict(frame=1.4),
        knobs=dict([(lo, (x, y, 0.85)) for x, los in zip((-5.7, -3.0, -0.3, 2.4), (('02', '03', '04'), ('06', '07', '08'), ('09', '0a', '0b'), ('0c', '0d', '0e')))
                    for lo, y in zip(los, (1.5, -0.05, -1.6))] + [('10', (5.4, -0.75))]),
        switch=(5.4, 1.9, 0.5), led=(5.4, 1.9),
        controls={'sel-05': (-5.7, -2.75, 2.2, 0.5), 'sel-0f': (2.4, -2.75, 2.2, 0.5)},
        decals={'panel': (RACK_W, 6.7, 0, 0, 2.95)},
    ),
    'dyn-delay': dict(
        frame=(18.4, 7.2), build=ddelay_build, build_knob=rack_knob, knob=dict(frame=1.4),
        knobs={'04': (-5.9, 1.1, 1.25), '03': (-4.0, 1.25), '07': (-2.3, 1.25), '08': (-0.9, 1.25), '0a': (0.9, 1.25), '09': (2.3, 1.25),
               '0b': (4.0, 1.25), '0c': (5.4, 1.25), '0d': (4.7, -1.55), '02': (-0.2, -1.55)},
        switch=(6.4, -1.6, 0.5), led=(6.4, -1.6),
        controls={'sync-select': (-5.9, -1.4, 2.2, 0.5), 'sel-06': (-3.0, -1.55, 2.2, 0.5)},
        decals={'panel': (RACK_W, 6.7, 0, 0, 2.95)},
    ),
    'eleven-sr': dict(
        frame=(18.4, 7.2), build=esr_build, build_knob=rack_knob, knob=dict(frame=1.4),
        knobs={'02': (-5.2, 0.5), '06': (-3.2, 0.5), '03': (-1.2, 0.5), '04': (0.8, 0.5), '05': (3.3, 0.6)},
        switch=(6.0, 0.2, 0.5), led=(6.0, 0.2),
        decals={'panel': (RACK_W, 6.7, 0, 0, 2.95)},
    ),
    'fx-loop': dict(
        frame=(18.4, 4.9), build=fxloop_build, build_knob=rack_knob, knob=dict(frame=1.4),
        knobs={'02': (-3.4, 0.0), '03': (-1.6, 0.0), '04': (0.2, 0.0)},
        switch=(6.0, 0.0, 0.5), led=(6.0, 0.0),
        decals={'panel': (RACK_W, 4.4, 0, 0, 2.95)},
    ),
    'multi-chorus': dict(
        frame=(14.2, 12.6), build=mchorus_build, build_knob=lambda R, pointer: dc_dist_knob_white(R, pointer), knob=dict(frame=1.9),
        knobs={'02': (-4.3, 3.6), '04': (-1.45, 3.6), '06': (1.45, 3.6), '05': (4.3, 3.6), '08': (-4.3, 0.7), '09': (-1.45, 0.7)},
        switch=(0.0, -3.95, 0.8), led=(0.0, -2.4),
        controls={'sync-03': (-4.4, -1.35, 2.2, 0.5), 'sel-07': (1.45, 0.7, 2.2, 0.5), 'tgl-0a': (4.3, 0.7, 1.5, 0.55, 'rocker-l0')},
        decals={'top': (12.0, 10.9, 0, 0, 3.2)},
    ),
    'flanger': dict(
        frame=(9.4, 13.0), build=flanger_build, build_knob=lambda R, pointer: dc_dist_knob_white(R, pointer), knob=dict(frame=1.9),
        knobs={'02': (-1.65, 3.9), '03': (1.65, 3.9), '05': (-1.65, 1.2), '04': (1.65, 1.2)},
        switch=(0.0, -4.15, 0.8), led=(0.0, -2.75),
        controls={'sync-06': (0.0, -0.3, 2.4, 0.5)},
        decals={'top': (6.9, 11.3, 0, 0, 3.2)},
    ),
    'graphic-eq': dict(
        frame=(9.8, 13.6), build=geq_build, build_knob=rack_knob, knob=dict(frame=1.4), knobs={},
        sliders={lo: ((x, GEQ_Y[0]), (x, GEQ_Y[1]), 'cap') for lo, x in zip(('02', '03', '04', '05', '06', '07'), GEQ_X)},
        sprites={'cap': (geq_cap, 1.0)},
        switch=(0.0, -4.6, 0.8), led=(0.0, -3.15),
        decals={'top': (7.3, 12.1, 0, 0, 3.0)},
    ),
    'memory-man': dict(
        frame=(13.4, 12.2),
        build=mm_build, build_knob=mm_knob,
        knob=dict(frame=2.0),
        knobs={'06': (0.6, 2.6), '02': (3.9, 2.6), '03': (3.9, -0.3), '04': (3.9, -3.1), '07': (0.6, -3.1)},
        switch=(-5.0, -3.85, 0.75),
        led=(-4.6, 3.6),
        controls={'tgl-08': (4.4, 4.55, 1.5, 0.55, 'rocker-l0'), 'tgl-09': (-2.9, -4.45, 1.5, 0.55, 'rocker-l0'),
                  'tgl-0a': (-1.3, -4.45, 1.5, 0.55, 'rocker-l0'), 'sync-select': (-2.2, 3.6, 2.4, 0.55)},
        decals={'top': (12.0, 10.2, 0, 0, 3.0)},
    ),
    'blackpanel': dict(
        frame=(16.6, 9.0),
        build=bf_build, build_knob=bf_knob,
        knob=dict(frame=1.5),
        knobs={'02': (-5.6, 0.75), '03': (-3.9, 0.75), '04': (-2.2, 0.75)},
        switch=(6.6, 0.55, 0.45),
        led=(6.6, 0.55),
        decals={'panel': (16.0, 3.4, 0, 0.5, 1.4)},
    ),
    'roto': dict(
        frame=(13.0, 13.6),
        build=roto_build, build_knob=lambda R, pointer: ce1_knob(R, pointer),
        knob=dict(frame=1.6),
        knobs={'04': (-3.3, 0.3)},
        switch=(3.6, -0.25, 0.45),
        led=(3.6, 0.65),
        controls={'sel-02': (-0.6, 0.65, 2.4, 0.55), 'sel-03': (-0.6, -0.15, 2.4, 0.55)},
        decals={'plate': (9.0, 2.3, 0, 0.3, 2.08)},
    ),
    'ep-3': dict(
        frame=(19.6, 13.4),
        build=ep3_build, build_knob=ep3_knob,
        knob=dict(frame=1.6),
        knobs={'06': (-7.4, 4.0), '03': (-5.3, 4.0), '02': (-6.35, 1.75), '08': (-5.4, -3.55, 0.85), '07': (-3.8, -3.55, 0.85)},
        sliders={'04': ((-1.6, -0.5), (6.0, -0.5), 'carriage')},
        sprites={'carriage': (ep3_carriage, 1.8)},
        switch=(-7.4, -3.65, 0.5),
        led=(-7.4, -2.6),
        controls={'tgl-09': (-2.0, -3.65, 0.9, 0.9), 'tgl-0a': (-0.6, -3.65, 0.9, 0.9), 'sync-select': (-6.35, -0.85, 2.4, 0.55)},
        leds={'tgl-09': (-2.0, -2.6), 'tgl-0a': (-0.6, -2.6)},
        decals={'strip': (17.0, 3.7, 0, -3.65, 3.0), 'bay': (4.5, 6.75, -6.35, 2.0, 3.2), 'band': (12.1, 1.8, 2.05, -0.5, 3.2), 'badge': (3.2, 1.3, 2.2, 3.05, 3.21)},
    ),
    'gray-comp': dict(
        frame=(9.2, 12.6),
        build=gray_build, build_knob=gray_knob,
        knob=dict(frame=2.8),
        knobs={'03': (-1.65, 2.5), '02': (1.65, 2.5)},
        switch=(0.0, -3.0, 0.8),
        led=(0.0, 4.35),
        decals={'top': (6.4, 10.0, 0, 0, 3.3)},
    ),
    'orange-phaser': dict(
        frame=(8.2, 12.6),
        build=phaser_build, build_knob=phaser_knob,
        knob=dict(frame=2.3),
        knobs={'02': (0.0, 3.5)},
        switch=(0.0, -2.35, 0.8),
        led=(0.0, -0.65),
        controls={'sync-03': (0.0, 0.95, 2.4, 0.6)},
        decals={'top': (5.4, 10.6, 0, 0, 3.1)},
    ),
    'uni-vibe': dict(
        frame=(16.0, 11.0),
        build=vibe_build, build_knob=vibe_knob,
        knob=dict(frame=2.4),
        knobs={'04': (-5.4, 1.15), '03': (1.4, 1.15), '02': (4.3, 1.15)},
        switch=(6.0, -2.2, 0.6),
        led=(6.0, 1.25),
        controls={'tgl-05': (-2.0, 1.15, 2.0, 0.8, 'rocker-r0'), 'sync-06': (2.4, -2.2, 2.4, 0.6)},
        decals={'plate': (13.9, 8.7, 0, 0.1, 3.26)},
    ),
    'ce-1': dict(
        frame=(16.4, 12.6),
        build=ce1_build, build_knob=ce1_knob,
        knob=dict(frame=1.6),
        knobs={'02': (-0.9, 2.6), '03': (2.5, 2.6), '04': (4.35, 2.6)},
        switch=(-4.6, -2.95, 0.75),
        led=(-4.6, -0.75),
        controls={'tgl-05': (4.6, -2.95, 1.5, 1.5), 'sync-06': (-4.4, 2.75, 2.3, 0.55)},
        leds={'tgl-05': (4.6, -0.75)},
        decals={'plate': (13.4, 3.6, 0, 2.35, 3.06), 'lower': (14.0, 5.0, 0, -2.4, 3.0)},
    ),
    'plexi': dict(
        frame=(PLEXI['w'], PLEXI['h']), samples=96, ink=1.0,
        build=plexi_build, build_knob=plexi_knob,
        knob=dict(frame=1.4),
        knobs={str(i): v for i, v in enumerate(PLEXI_KNOBS)},
        switch=(0.0, 0.0, 0.0),
        led=(-3.75, -2.25),
        decals={'panel': (14.4, 2.05, 0, -2.175, 2.01)},
    ),
    'black-op': dict(
        frame=(10.4, 13.4),
        build=blackop_build, build_knob=blackop_knob,
        knob=dict(frame=2.0),
        knobs={'02': (-2.75, 2.15), '03': (0.0, 2.15), '04': (2.75, 2.15)},
        switch=(0.0, -4.0, 0.8),  # x, y, radius of the stomp switch
        led=(-1.35, -4.0),
        decals={'top': (8.2, 10.8, 0, 0, 4.0)},
    ),
    'white-boost': dict(
        frame=(8.2, 12.6),
        build=white_build, build_knob=white_knob,
        knob=dict(frame=2.2),
        knobs={'02': (-1.45, 3.75), '03': (1.45, 3.75), '05': (-1.45, 1.25), '04': (1.45, 1.25)},
        switch=(0.0, -3.75, 0.8),  # x, y, radius of the stomp switch
        led=(0.0, -2.35),
        decals={'top': (5.4, 10.6, 0, 0, 3.1)},
    ),
    'dc-dist': dict(
        frame=(8.2, 13.0),
        build=dc_build, build_knob=dc_knob,
        knob=dict(frame=1.9),
        knobs={'05': (-1.9, 4.35), '03': (0.0, 4.6), '04': (1.9, 4.35), '02': (0.0, 0.3, 1.6)},
        switch=(0.0, -3.95, 0.7),  # x, y, radius of the stomp switch
        led=(0.0, -2.25),
        decals={'top': (6.2, 11.8, 0, 0, 3.4)},
    ),
    'tri-fuzz': dict(
        frame=(11.0, 13.0),
        build=fuzz_build, build_knob=fuzz_knob,
        knob=dict(frame=2.4),
        knobs={'04': (-3.05, 3.25), '03': (0.0, 3.25), '02': (3.05, 3.25)},
        switch=(0.0, -3.6, 0.8),  # x, y, radius of the stomp switch
        led=(-1.55, 2.0),
        decals={'top': (9.2, 10.6, 0, 0, 3.6)},
    ),
    'green-jrc': dict(
        frame=(9.4, 13.4),
        build=jrc_build, build_knob=jrc_knob,
        knob=dict(frame=2.6),
        knobs={'02': (-1.95, 4.35), '04': (1.95, 4.35), '03': (0.0, 2.75)},
        switch=(0.0, -3.45, 1.15),  # x, y, radius of the stomp switch
        led=(0.0, 5.75),
        # decal name -> (width, height, centre x, centre y, z)
        decals={
            'upper': (7.0, 5.05, 0, 3.72, JRC['upper_z']),
            'lower': (7.1, 7.35, 0, -2.5, JRC['lower_z']),
        },
    ),
}
