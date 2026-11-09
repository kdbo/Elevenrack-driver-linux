# Render a treadle pedal (wah, volume) with Blender (Cycles) for the editor,
# seen from the front left and a little above like a product photo, at
# FRAMES treadle positions from toe-up (value 0) to toe-down (value 127).
#
#   python3 art.py <device> <outdir>/_art-<device>      (name plates, if any)
#   blender -b -P render_treadle.py -- <device> <outdir>
#
# Writes <device>-f00.png ... <device>-f16.png (920 x 500 px, transparent,
# with the pedal's shadow on the floor). Shapes, colours and layout only:
# the rack's model names, no maker's logo.

import math, os, sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rhelp as R  # noqa: E402

FRAMES = 17
W_PX, H_PX = 920, 500

argv = sys.argv[sys.argv.index('--') + 1:]
DEV, OUT = argv[0], argv[1]
ART = os.path.join(OUT, '_art-' + DEV)

# pedal along x (toe at -x), near side at -y, floor at z = 0; cm
SPECS = {
    # chrome treadle on a black hammertone base, name plate on the toe end
    'shine-wah': dict(L=25.5, D=10.2, hb=5.0, tt=2.0, pivot=4.6, tilt=(12.0, -2.0),
                      base='hammer', treadle='chrome', post=True, plate=True),
    # satin black all over, the name in white on the toe plate
    'black-wah': dict(L=25.5, D=10.2, hb=5.0, tt=2.0, pivot=4.6, tilt=(12.0, -2.0),
                      base='satin', treadle='black', post=True, plate=True),
    # black plastic, ribbed rubber tread, pale toe cap; low base, pivot at the heel
    'fv-vol': dict(L=28.0, D=10.8, hb=3.6, tt=1.9, pivot=2.2, tilt=(10.0, -1.5),
                   base='plastic', treadle='rubber', post=False, plate=False),
}
S = SPECS[DEV]

R.reset(40)
# a bright studio round the pedal for the chrome to mirror (the page still
# shows through: the film is transparent)
bpy.context.scene.world.node_tree.nodes['Background'].inputs[1].default_value = 0.9
L, D, hb, tt = S['L'], S['D'], S['hb'], S['tt']
ft = 0.5                                   # rubber feet lift the base this much
x0, x1, y0, y1 = -L / 2, L / 2, -D / 2, D / 2

# ── materials ──
if S['base'] == 'hammer':
    base_m = R.crinkle('base', '#2e2e31', rough=0.45, scale=6.0, strength=0.5)
elif S['base'] == 'satin':
    base_m = R.mat('base', '#1b1b1d', rough=0.42, coat=0.2)
else:
    base_m = R.mat('base', '#1d1d1f', rough=0.55)
chrome = R.mat('chrome', '#dfe2e6', rough=0.08, metal=1.0)
dark = R.mat('dark', '#0b0b0c', rough=0.7)
rubber = R.mat('rubber', '#141415', rough=0.85)

# ── base, feet, side jack, toe-end plate ──
inset = 0.7
R.frustum('base', (x0, x1, y0, y1), (x0 + inset, x1 - inset * 0.6, y0 + 0.35, y1 - 0.35), ft, ft + hb, base_m, bevel=0.35)
for fx in (x0 + 2.2, x1 - 2.2):
    for fy in (y0 + 1.6, y1 - 1.6):
        R.cyl('foot', 0.8, ft, fx, fy, 0, rubber, bevel=0.15)
jy = y0 + 0.1
R.cyl('jack-nut', 0.75, 0.25, 2.5, jy, ft + hb * 0.45 - 0.125, chrome, verts=6, rot=(math.pi / 2, 0, 0))
R.cyl('jack-hole', 0.42, 0.3, 2.5, jy - 0.05, ft + hb * 0.45 - 0.15, dark, rot=(math.pi / 2, 0, 0))
R.box('dc', 0.9, 0.3, 1.1, 4.3, jy, ft + hb * 0.45 - 0.55, dark, bevel=0.08)
if S['plate']:
    # the plate follows the toe end's slope
    zb, zt = ft + hb * 0.2, ft + hb * 0.8
    xb, xt = x0 - 0.02 + inset * 0.2, x0 - 0.02 + inset * 0.8
    yb = lambda f: y1 - 1.6 - f * (D - 3.2)
    R.decal_quad('plate', os.path.join(ART, 'plate.png'),
                 [(xb, yb(0), zb), (xb, yb(1), zb), (xt, yb(1), zt), (xt, yb(0), zt)], rough=0.4)

# ── treadle on its pivot near the heel, and what shows in the gap under it ──
px, pz = x1 - S['pivot'], ft + hb + 0.7
bpy.ops.object.empty_add(location=(px, 0, pz))
pivot = bpy.context.object
tl = L - 0.6
tx0 = x0 + 0.3 - px                         # treadle x range relative to the pivot
parts = []
if S['treadle'] == 'chrome':
    parts.append(R.box('treadle', tl, D - 0.2, tt, tx0 + tl / 2 + px, 0, pz, chrome, bevel=0.45))
elif S['treadle'] == 'black':
    parts.append(R.box('treadle', tl, D - 0.2, tt, tx0 + tl / 2 + px, 0, pz, R.mat('treadle', '#19191b', rough=0.35, coat=0.3), bevel=0.45))
else:
    plastic = R.mat('treadle', '#1b1b1d', rough=0.5)
    parts.append(R.box('treadle', tl, D, tt, tx0 + tl / 2 + px, 0, pz, plastic, bevel=0.5))
    cap = 6.5
    parts.append(R.box('toe-cap', cap, D - 0.6, 0.35, x0 + 0.3 + cap / 2 + 0.2, 0, pz + tt - 0.05, R.mat('cap', '#c8d8e2', rough=0.4), bevel=0.25))
    for i in range(int((tl - cap - 1.5) / 1.25)):
        x = x0 + 0.3 + cap + 0.9 + i * 1.25
        parts.append(R.box('rib', 0.55, D - 1.4, 0.32, x, 0, pz + tt - 0.05, rubber, bevel=0.12))
for p in parts:
    p.parent = pivot
    p.matrix_parent_inverse = pivot.matrix_world.inverted()
# the gap: a dark mechanism box, and the toe switch's threaded post
R.box('works', L - 8, D - 3, 0.9, -1.0, 0, ft + hb, dark)
if S['post']:
    R.cyl('post', 0.42, 1.2, x0 + 3.2, 0, ft + hb, chrome)

R.floor()
R.lights(1.6)
R.camera_persp((-37.0, -49.0, 28.0), (0.6, 0.0, 3.4), 68, W_PX, H_PX)

# ── one frame per treadle position ──
sc = bpy.context.scene
sc.frame_start, sc.frame_end = 0, FRAMES - 1
a0, a1 = S['tilt']
for f in range(FRAMES):
    pivot.rotation_euler = (0, math.radians(a0 + (a1 - a0) * f / (FRAMES - 1)), 0)
    pivot.keyframe_insert('rotation_euler', frame=f)
if 'test' in argv[2:]:
    sc.frame_start = sc.frame_end = FRAMES // 2      # one middle frame, to check the framing
sc.render.filepath = os.path.join(OUT, DEV + '-f##')
bpy.ops.render.render(animation=True)
