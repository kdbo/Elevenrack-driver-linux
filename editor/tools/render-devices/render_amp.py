# Render the Plexi stack (head on a 4x12 basketweave cabinet) as near-photo
# pictures for the editor: a perspective camera a little above the front,
# a studio HDRI for light and reflections, AgX colour.
#
#   blender -b -P render_amp.py -- <outdir> [<studio.hdr>]
#
# Writes plexi-head.png and cab-412.png (each with its shadow, transparent
# elsewhere), plexi-knob.png / plexi-pointer.png (one knob seen from the
# same angle, and its pointer on its own) and plexi-stack.json: where each
# picture lies against the head's / cab's front in CSS px (40 per unit at
# the front), and the knobs' and lamp's centres. Any CC0 studio HDRI will
# do (e.g. Poly Haven's studio_small_08); without one the world is grey.
# Shapes, colours and layout only: the rack's model name, no maker's logo.

import json, math, os, sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rhelp as R  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:]
OUT = argv[0]
HDRI = argv[1] if len(argv) > 1 else ''
ART = os.path.join(OUT, '_art-plexi')     # art.py's panel print (scales, labels)
SCRIPT_FONT = os.path.join(HERE, '..', '..', 'src', 'fonts', 'Damion.ttf')
CSS = 40                                   # CSS px per unit at the front faces
W = 19.0                                   # head and cab front width
HEAD_H, CAB_H, GAP = 7.25, 6.5, 0.15       # the editor's 290 / 260 px, 6 px apart
HEAD_D, CAB_D = 7.0, 9.0
PANEL = (-6.975, 6.975, -3.5, -1.25)       # gold panel on the head front, from its centre
KNOBS = [(-3.75 + 1.46 * i, -2.4) for i in range(6)]
LAMP = (-4.85, -2.45)
PITCH = math.radians(7)                    # camera looks this far down


def setup(samples):
    sc = R.reset(samples)
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except TypeError:
        pass
    nt = sc.world.node_tree
    if HDRI and os.path.exists(HDRI):
        env = nt.nodes.new('ShaderNodeTexEnvironment')
        env.image = bpy.data.images.load(HDRI)
        nt.links.new(env.outputs['Color'], nt.nodes['Background'].inputs['Color'])
        nt.nodes['Background'].inputs['Strength'].default_value = 0.9
    # a big soft key from the upper left, as a photographer's softbox
    bpy.ops.object.light_add(type='AREA', location=(-30, -40, 45))
    key = bpy.context.object
    key.data.size = 40
    key.data.energy = 60000
    key.rotation_euler = (math.radians(45), 0, math.radians(-35))
    return sc


def materials():
    m = {}
    # levant tolex: a fine pebble grain (sub-pixel here, it reads as a soft
    # sheen) over a coarser leathery lumpiness that breaks up the highlights
    tolex = R.pebble('tolex', '#141416', rough=0.48, scale=9.0, strength=0.55)
    R._noise_into(tolex, 'Roughness', 6.0, detail=3.0, lo=0.42, hi=0.56)
    m['tolex'] = tolex
    m['cream'] = R.mat('piping', '#efe7cf', rough=0.38, coat=0.4)
    # brushed gold behind clear acrylic: streaks along x (no anisotropy: the
    # panel stands upright, and a radial tangent would swirl)
    gold = R.mat('gold', '#e2c886', rough=0.3, metal=1.0)
    R._noise_into(gold, 'Roughness', 4.0, detail=12.0, lo=0.2, hi=0.38, stretch=(0.4, 1.0, 50.0))
    p = gold.node_tree.nodes['Principled BSDF']
    p.inputs['Coat Weight'].default_value = 1.0
    p.inputs['Coat Roughness'].default_value = 0.03
    m['gold'] = gold
    m['black'] = R.mat('black', '#0d0d0f', rough=0.35)
    m['chrome'] = R.mat('chrome', '#dadde1', rough=0.08, metal=1.0)
    m['brass'] = R.mat('brass', '#d4b778', rough=0.22, metal=1.0)
    m['corner'] = R.mat('corner', '#0b0b0c', rough=0.32, coat=0.4)
    # basketweave: tan and brown, woven in pairs, with a little relief
    cloth = R.weave('cloth', '#a38d63', '#40331f', scale=48.0)
    R._noise_into(cloth, None, 48.0, detail=1.0, bump=0.5)
    R._noise_into(cloth, 'Roughness', 3.0, detail=2.0, lo=0.75, hi=0.95)
    m['cloth'] = cloth
    return m


def piped_frame(name, x0, x1, z0, z1, y, mat, t=0.17, bar_z=None):
    # round cream piping laid on a front: a rectangle, and one bar across
    def bar(a, b):
        L = (b - a).length
        bpy.ops.mesh.primitive_cylinder_add(radius=t / 2, depth=L + t, vertices=20, location=(a + b) / 2)
        c = bpy.context.object
        c.rotation_euler = (b - a).to_track_quat('Z', 'Y').to_euler()
        R.finish(c, mat)
    pts = [Vector((x0, y, z0)), Vector((x1, y, z0)), Vector((x1, y, z1)), Vector((x0, y, z1))]
    for a, b in zip(pts, pts[1:] + pts[:1]):
        bar(a, b)
    if bar_z is not None:
        bar(Vector((x0, y, bar_z)), Vector((x1, y, bar_z)))


def corners(x0, x1, z0, z1, y0, y1, mat):
    # moulded black plastic caps wrapping a cab's eight corners
    for x in (x0, x1):
        for z in (z0, z1):
            for y in (y0, y1):
                R.box('corner', 1.25, 1.25, 1.25, x, y, z - 0.625, mat, bevel=0.42, seg=6)


def build_cab(m):
    zc = 0.0
    R.box('cab', W, CAB_D, CAB_H, 0, CAB_D / 2, zc, m['tolex'], bevel=0.45, seg=8)
    gx, gz0, gz1 = W / 2 - 0.65, zc + 0.5, zc + CAB_H - 0.5
    R.box('cloth', 2 * gx, 0.1, gz1 - gz0, 0, -0.02, gz0, m['cloth'], bevel=0.02)
    piped_frame('cab-piping', -gx, gx, gz0, gz1, -0.1, m['cream'])
    R.box('plate', 4.4, 0.08, 0.75, -6.4, -0.12, zc + CAB_H - 0.9 - 0.375, m['brass'], bevel=0.03)
    corners(-W / 2 + 0.5, W / 2 - 0.5, zc + 0.5, zc + CAB_H - 0.5, 0.5, CAB_D - 0.5, m['corner'])
    for x in (-W / 2 + 1.5, W / 2 - 1.5):          # castors' sockets under the cab
        R.cyl('foot', 0.6, 0.4, x, CAB_D / 2, -0.4, m['black'])


def build_head(m):
    z0 = CAB_H + GAP
    zt = z0 + HEAD_H
    R.box('head', W, HEAD_D, HEAD_H, 0, HEAD_D / 2, z0, m['tolex'], bevel=0.5, seg=8)
    for x in (-W / 2 + 1.4, W / 2 - 1.4):           # the head's rubber feet in the gap
        R.cyl('foot', 0.45, GAP, x, 1.2, z0 - GAP, m['black'])
        R.cyl('foot', 0.45, GAP, x, HEAD_D - 1.2, z0 - GAP, m['black'])
    i = 0.32
    piped_frame('head-piping', -W / 2 + i, W / 2 - i, z0 + i, zt - i, -0.07, m['cream'], bar_z=zt - 2.8)
    # the gold panel and its print
    zc = z0 + HEAD_H / 2
    px0, px1, py0, py1 = PANEL
    R.box('panel', px1 - px0, 0.18, py1 - py0, (px0 + px1) / 2, -0.09, zc + py0, m['gold'], bevel=0.05)
    pw, ph = px1 - px0, py1 - py0
    R.decal_quad('print', os.path.join(ART, 'panel.png'),
                 [(px0, -0.186, zc + py0), (px1, -0.186, zc + py0), (px1, -0.186, zc + py1), (px0, -0.186, zc + py1)], rough=0.7)
    for sx, sz in ((px0 + 0.22, py1 - 0.22), (px1 - 0.22, py1 - 0.22), (px0 + 0.22, py0 + 0.22), (px1 - 0.22, py0 + 0.22)):
        R.cyl('screw', 0.1, 0.05, sx, -0.18, zc + sz, m['brass'], bevel=0.03, rot=(math.pi / 2, 0, 0))
    # the logo: raised cream plastic, standing on the front
    logo = R.text3d('logo', 'Plexi 100W', SCRIPT_FONT, 1.8, 0, 0, 0, R.mat('logo', '#f2e8cc', rough=0.22, coat=0.7), depth=0.12, bevel=0.03)
    logo.rotation_euler = (math.pi / 2, 0, 0)
    logo.location = (0, -0.12, zt - 1.45)
    # rockers, jewel lamp, inputs, on the panel face (y = -0.18)
    yf = -0.18
    for x in (-6.45, -5.65):
        R.box('rocker-bezel', 0.42, 0.08, 0.7, x, yf - 0.04, zc - 2.5 - 0.35, m['black'], bevel=0.05)
        R.box('rocker', 0.3, 0.24, 0.55, x, yf - 0.16, zc - 2.5 - 0.275, m['corner'], bevel=0.08)
    R.cyl('lamp-bezel', 0.3, 0.16, LAMP[0], yf - 0.08, zc + LAMP[1], m['chrome'], verts=16, bevel=0.03, rot=(math.pi / 2, 0, 0))
    R.cyl('lamp', 0.22, 0.26, LAMP[0], yf - 0.15, zc + LAMP[1], R.mat('jewel', '#b0180c', rough=0.06, coat=1.0, emit='#ff2a14'), verts=12, bevel=0.1, rot=(math.pi / 2, 0, 0))
    for x in (5.05, 6.4):
        for z in (-1.98, -2.78):
            R.cyl('in-nut', 0.3, 0.1, x, yf - 0.05, zc + z, m['chrome'], verts=6, rot=(math.pi / 2, 0, 0))
            R.cyl('in', 0.21, 0.16, x, yf - 0.1, zc + z, m['chrome'], bevel=0.03, rot=(math.pi / 2, 0, 0))
            R.cyl('in-hole', 0.11, 0.02, x, yf - 0.27, zc + z, R.mat('hole', '#050505', rough=0.9), rot=(math.pi / 2, 0, 0))
    # carrying handle on top
    R.box('handle', 6.0, 1.0, 0.45, 0, HEAD_D / 2, zt, m['black'], bevel=0.2)
    for x in (-3.4, 3.4):
        R.box('handle-cap', 0.9, 1.3, 0.35, x, HEAD_D / 2, zt, m['chrome'], bevel=0.12)
    return zc


def camera():
    # long lens, far back and a little above, aimed at the stack's front
    target = Vector((0, 0, (CAB_H + GAP + HEAD_H) / 2))
    dist = 140.0
    loc = target + Vector((0, -math.cos(PITCH) * dist, math.sin(PITCH) * dist))
    cam = R.camera_persp(tuple(loc), tuple(target), 180, 1700, 1400)
    return cam


def project(cam, p):
    sc = bpy.context.scene
    v = world_to_camera_view(sc, cam, Vector(p))
    return (v.x * sc.render.resolution_x, (1 - v.y) * sc.render.resolution_y)


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


# ── the stack, head and cab rendered apart (each picture has its own shadow) ──
setup(96)
mats = materials()
build_cab(mats)
cab_objs = set(bpy.context.scene.objects)
zc = build_head(mats)
head_objs = set(bpy.context.scene.objects) - cab_objs
R.floor()
floor = bpy.context.object
floor.location.z = -0.4                    # under the cab's feet
cam = camera()
bpy.context.view_layer.update()


def placement(x0, z_top, z_bot):
    # where the picture lies against a front whose top-left corner is (x0, z_top):
    # that corner's pixel, and the scale from pixels to CSS px
    a, b = project(cam, (x0, 0, z_top)), project(cam, (-x0, 0, z_top))
    s = (2 * -x0 * CSS) / (b[0] - a[0])
    sc = bpy.context.scene
    return {'left': round(-a[0] * s, 1), 'top': round(-a[1] * s, 1),
            'width': round(sc.render.resolution_x * s, 1), 'height': round(sc.render.resolution_y * s, 1)}, a, s


meta = {}
for name, show, hide in (('plexi-head', head_objs, cab_objs), ('cab-412', cab_objs, head_objs)):
    floor.hide_render = name == 'plexi-head'   # the head's shadow would fall where the cab is
    for o in hide:
        if o.type == 'MESH' or o.type == 'FONT':
            o.hide_render = True
    for o in show:
        o.hide_render = False
    render(os.path.join(OUT, name + '.png'))
for o in cab_objs | head_objs:
    o.hide_render = False

zt = CAB_H + GAP + HEAD_H
head_place, origin, s = placement(-W / 2, zt, CAB_H + GAP)
cab_place, corigin, cs = placement(-W / 2, CAB_H, 0)
meta['plexi-head'] = head_place
meta['cab-412'] = cab_place
knobs = {}
for i, (x, z) in enumerate(KNOBS):
    p = project(cam, (x, -0.18 - 0.5, zc + z))
    knobs[str(i)] = [round((p[0] - origin[0]) * s, 1), round((p[1] - origin[1]) * s, 1), 1]
meta['knobs'] = knobs
lp = project(cam, (LAMP[0], -0.3, zc + LAMP[1]))
meta['led'] = [round((lp[0] - origin[0]) * s, 1), round((lp[1] - origin[1]) * s, 1)]
pp = project(cam, (-6.4, -0.16, CAB_H - 0.9 - 0.375 / 1))
meta['plate'] = [round((pp[0] - corigin[0]) * cs, 1), round((pp[1] - corigin[1]) * cs, 1)]
# one knob's size in CSS px at the panel
k0, k1 = project(cam, (KNOBS[0][0] - 0.65, -0.7, zc + KNOBS[0][1])), project(cam, (KNOBS[0][0] + 0.65, -0.7, zc + KNOBS[0][1]))
meta['knob'] = round((k1[0] - k0[0]) * s, 1)

# ── one knob and its pointer, from the same angle ──
for part in ('knob', 'pointer'):
    setup(96)
    black = R.mat('knob', '#121214', rough=0.36)
    if part == 'knob':
        R.cyl('skirt', 0.58, 0.2, 0, 0, 0, black, bevel=0.04)
        R.cyl('body', 0.5, 0.82, 0, 0, 0.1, black, bevel=0.05)
        R.ribs(24, 0.5, 0.62, 0.2, 0.05, 0.08, black)
        cap = R.brushed('cap', '#e2c67f', rough=0.2)
        R.cyl('cap', 0.38, 0.06, 0, 0, 0.93, cap, bevel=0.02)
    else:
        R.box('pointer', 0.06, 0.3, 0.02, 0, 0.19, 1.0, R.mat('ptr', '#2a1d06', rough=0.6))
    # the knob stands out of the front: tip it so the camera sees it as on the stack
    # (the knob's +y is up on the stack, and the camera sees a little of that side)
    bpy.ops.object.camera_add(location=(0, math.sin(PITCH) * 40, math.cos(PITCH) * 40), rotation=(-PITCH, 0, 0))
    c = bpy.context.object
    c.data.type = 'ORTHO'
    c.data.ortho_scale = 1.3
    sc = bpy.context.scene
    sc.camera = c
    sc.render.resolution_x = sc.render.resolution_y = 128
    render(os.path.join(OUT, 'plexi-' + part + '.png'))

with open(os.path.join(OUT, 'plexi-stack.json'), 'w') as f:
    json.dump(meta, f, indent=1)
