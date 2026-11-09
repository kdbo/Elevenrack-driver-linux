# Blender helpers shared by the render scripts: scene setup, materials,
# simple solids, decals, lights, an orthographic top camera and render.
# Units are cm; 80 px per cm in the orthographic renders.

import math
import bpy

PX_PER_CM = 80


def reset(samples=96):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    world = bpy.data.worlds.new('w')
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs[0].default_value = (0.55, 0.56, 0.58, 1)
    bg.inputs[1].default_value = 0.35
    return sc


def mat(name, color, rough=0.4, metal=0.0, coat=0.0, emit=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (*srgb(color), 1)
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metal
    p.inputs['Coat Weight'].default_value = coat
    if emit:
        p.inputs['Emission Color'].default_value = (*srgb(emit), 1)
        p.inputs['Emission Strength'].default_value = 2.0
    return m


def _noise_into(m, socket, scale, detail=6.0, lo=0.0, hi=1.0, stretch=None, bump=None):
    # feed a noise texture into a BSDF input (through a map range), or into
    # the normal through a bump node
    nt = m.node_tree
    p = nt.nodes['Principled BSDF']
    n = nt.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail
    if stretch:
        tc = nt.nodes.new('ShaderNodeTexCoord')
        mp = nt.nodes.new('ShaderNodeMapping')
        mp.inputs['Scale'].default_value = stretch
        nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
        nt.links.new(mp.outputs['Vector'], n.inputs['Vector'])
    if bump is not None:
        b = nt.nodes.new('ShaderNodeBump')
        b.inputs['Strength'].default_value = bump
        b.inputs['Distance'].default_value = 0.02
        nt.links.new(n.outputs['Fac'], b.inputs['Height'])
        nt.links.new(b.outputs['Normal'], p.inputs['Normal'])
        return
    r = nt.nodes.new('ShaderNodeMapRange')
    r.inputs['To Min'].default_value = lo
    r.inputs['To Max'].default_value = hi
    nt.links.new(n.outputs['Fac'], r.inputs['Value'])
    nt.links.new(r.outputs['Result'], p.inputs[socket])


def crinkle(name, color, rough=0.75, scale=60.0, strength=0.6):
    # wrinkle / powder-coat paint: bumpy, and rougher in the dips
    m = mat(name, color, rough=rough)
    _noise_into(m, None, scale, detail=8.0, bump=strength)
    return m


def pebble(name, color, rough=0.6, scale=9.0, strength=0.7):
    # levant tolex: a grain of small rounded pebbles (voronoi cells)
    m = mat(name, color, rough=rough)
    nt = m.node_tree
    p = nt.nodes['Principled BSDF']
    v = nt.nodes.new('ShaderNodeTexVoronoi')
    v.feature = 'SMOOTH_F1'
    v.inputs['Scale'].default_value = scale
    v.inputs['Randomness'].default_value = 0.9
    b = nt.nodes.new('ShaderNodeBump')
    b.inputs['Strength'].default_value = strength
    b.inputs['Distance'].default_value = 0.03
    b.invert = True
    nt.links.new(v.outputs['Distance'], b.inputs['Height'])
    nt.links.new(b.outputs['Normal'], p.inputs['Normal'])
    return m


def brushed(name, color, rough=0.28):
    # brushed metal: anisotropic, with fine streaks across x
    m = mat(name, color, rough=rough, metal=1.0)
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Anisotropic'].default_value = 0.75
    # streaks along x: tangents circling the y axis lie along x on a top face
    t = m.node_tree.nodes.new('ShaderNodeTangent')
    t.direction_type = 'RADIAL'
    t.axis = 'Y'
    m.node_tree.links.new(t.outputs['Tangent'], p.inputs['Tangent'])
    _noise_into(m, 'Roughness', 6.0, detail=12.0, lo=rough * 0.6, hi=rough * 1.5, stretch=(0.6, 60.0, 0.6))
    return m


def flake(name, color, metal=0.55, rough=0.32):
    # metallic paint with flake under a clear coat
    m = mat(name, color, rough=rough, metal=metal, coat=1.0)
    _noise_into(m, 'Roughness', 900.0, detail=2.0, lo=rough * 0.5, hi=rough * 1.6)
    return m


def prism(name, pts, h, z0, material, bevel=0.0, seg=6):
    # an outline (list of (x, y), counter-clockwise) extruded h up from z0
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z0)) for x, y in pts]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [e for e in ext['geom'] if isinstance(e, bmesh.types.BMVert)]:
        v.co.z += h
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    return finish(ob, material, bevel, seg)


def rounded_outline(w_top, w_bot, y0, y1, r_top, r_bot, n=10):
    # a rounded rectangle tapered from w_top (at y1) to w_bot (at y0)
    pts = []
    def corner(cx, cy, r, a0):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    corner(w_bot / 2 - r_bot, y0 + r_bot, r_bot, -90)
    corner(w_top / 2 - r_top, y1 - r_top, r_top, 0)
    corner(-w_top / 2 + r_top, y1 - r_top, r_top, 90)
    corner(-w_bot / 2 + r_bot, y0 + r_bot, r_bot, 180)
    return pts


def ribs(n, r, h, z0, width, depth, material, name='rib'):
    # n thin ridges standing round a cylinder of radius r (knurling)
    for i in range(n):
        a = i * 2 * math.pi / n
        box(name, depth, width, h, math.cos(a) * r, math.sin(a) * r, z0, material)
        bpy.context.object.rotation_euler = (0, 0, a)


def srgb(hexc):
    h = hexc.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def finish(ob, material, bevel=0.0, seg=4):
    if bevel:
        b = ob.modifiers.new('bevel', 'BEVEL')
        b.width = bevel
        b.segments = seg
        b.limit_method = 'ANGLE'
        ob.modifiers.new('wn', 'WEIGHTED_NORMAL').keep_sharp = True
    for poly in ob.data.polygons:
        poly.use_smooth = True
    ob.data.materials.append(material)
    return ob


def box(name, sx, sy, sz, x, y, z0, material, bevel=0.0, seg=4):
    # z0 is the bottom of the box
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z0 + sz / 2))
    ob = bpy.context.object
    ob.name = name
    ob.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    return finish(ob, material, bevel, seg)


def cyl(name, r, h, x, y, z0, material, bevel=0.0, verts=48, rot=None):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=(x, y, z0 + h / 2))
    ob = bpy.context.object
    ob.name = name
    if rot:
        ob.rotation_euler = rot
    return finish(ob, material, bevel)


def decal(name, png, sx, sy, x, y, z, rough=0.6):
    # an image laid on a face: opaque where the artwork has ink, clear elsewhere
    bpy.ops.mesh.primitive_plane_add(size=1, location=(x, y, z))
    ob = bpy.context.object
    ob.name = name
    ob.scale = (sx, sy, 1)
    bpy.ops.object.transform_apply(scale=True)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.blend_method = 'BLEND'
    nt = m.node_tree
    p = nt.nodes['Principled BSDF']
    p.inputs['Roughness'].default_value = rough
    p.inputs['Specular IOR Level'].default_value = 0.15   # printed ink barely shines
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(png)
    tex.interpolation = 'Cubic'
    nt.links.new(tex.outputs['Color'], p.inputs['Base Color'])
    nt.links.new(tex.outputs['Alpha'], p.inputs['Alpha'])
    ob.data.materials.append(m)
    ob.visible_shadow = False
    return ob


def lights(scale=1.0):
    def area(name, loc, size, energy, rot):
        bpy.ops.object.light_add(type='AREA', location=loc, rotation=rot)
        l = bpy.context.object
        l.name = name
        l.data.size = size * scale
        l.data.energy = energy * scale * scale
    # key from the upper left, a soft fill from the right, a rim from behind
    area('key', (-14 * scale, 14 * scale, 30 * scale), 18, 9000, (math.radians(-22), math.radians(-22), 0))
    area('fill', (20 * scale, -6 * scale, 22 * scale), 22, 2500, (math.radians(10), math.radians(38), 0))
    area('rim', (0, 26 * scale, 10 * scale), 14, 1600, (math.radians(-62), 0, 0))


def camera(sw, sh, cx=0.0, cy=0.0, z=40.0):
    bpy.ops.object.camera_add(location=(cx, cy, z))
    cam = bpy.context.object
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = max(sw, sh)
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.resolution_x = round(sw * PX_PER_CM)
    sc.render.resolution_y = round(sh * PX_PER_CM)
    sc.render.resolution_percentage = 100


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def frustum(name, bot, top, z0, z1, material, bevel=0.0, seg=6):
    # a block whose top rectangle is smaller than (or offset from) its bottom
    # one: bot / top are (x0, x1, y0, y1)
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    (a0, a1, b0, b1), (c0, c1, d0, d1) = bot, top
    v = [bm.verts.new(p) for p in ((a0, b0, z0), (a1, b0, z0), (a1, b1, z0), (a0, b1, z0),
                                    (c0, d0, z1), (c1, d0, z1), (c1, d1, z1), (c0, d1, z1))]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        bm.faces.new([v[i] for i in f])
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    return finish(ob, material, bevel, seg)


def decal_quad(name, png, corners, rough=0.6):
    # an image laid on any flat face: corners are the image's bottom-left,
    # bottom-right, top-right and top-left points
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in corners]
    f = bm.faces.new(vs)
    uv = bm.loops.layers.uv.new()
    for loop, co in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uv].uv = co
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.blend_method = 'BLEND'
    nt = m.node_tree
    p = nt.nodes['Principled BSDF']
    p.inputs['Roughness'].default_value = rough
    p.inputs['Specular IOR Level'].default_value = 0.15
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(png)
    nt.links.new(tex.outputs['Color'], p.inputs['Base Color'])
    nt.links.new(tex.outputs['Alpha'], p.inputs['Alpha'])
    ob.data.materials.append(m)
    ob.visible_shadow = False
    return ob


def camera_persp(loc, target, lens, w_px, h_px):
    bpy.ops.object.empty_add(location=target)
    aim = bpy.context.object
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.object
    cam.data.lens = lens
    t = cam.constraints.new('TRACK_TO')
    t.target = aim
    t.track_axis = 'TRACK_NEGATIVE_Z'
    t.up_axis = 'UP_Y'
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = w_px, h_px
    sc.render.resolution_percentage = 100
    return cam


def floor(size=200.0):
    # catches the shadows only; the page shows through everywhere else
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, 0))
    bpy.context.object.is_shadow_catcher = True


def wood(name, light, dark, rough=0.4, coat=0.6):
    # varnished wood: grain streaks along x between two tones
    m = mat(name, light, rough=rough, coat=coat)
    nt = m.node_tree
    p = nt.nodes['Principled BSDF']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (0.25, 9.0, 1.0)
    n = nt.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = 3.0
    n.inputs['Detail'].default_value = 10.0
    n.inputs['Distortion'].default_value = 1.5
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (*srgb(dark), 1)
    ramp.color_ramp.elements[1].color = (*srgb(light), 1)
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    nt.links.new(mp.outputs['Vector'], n.inputs['Vector'])
    nt.links.new(n.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], p.inputs['Base Color'])
    return m


def weave(name, light, dark, scale=140.0):
    # grille cloth: a fine two-tone weave
    m = mat(name, light, rough=0.8)
    nt = m.node_tree
    p = nt.nodes['Principled BSDF']
    c = nt.nodes.new('ShaderNodeTexChecker')
    c.inputs['Scale'].default_value = scale
    c.inputs['Color1'].default_value = (*srgb(light), 1)
    c.inputs['Color2'].default_value = (*srgb(dark), 1)
    nt.links.new(c.outputs['Color'], p.inputs['Base Color'])
    return m


def text3d(name, body, font_path, size, x, y, z, material, depth=0.05, bevel=0.015, align='CENTER'):
    # raised lettering (a logo badge, script on tolex): an extruded text object
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.font = bpy.data.fonts.load(font_path)
    cu.size = size
    cu.extrude = depth
    cu.bevel_depth = bevel
    cu.bevel_resolution = 3
    cu.align_x = align
    cu.align_y = 'CENTER'
    ob = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(ob)
    ob.location = (x, y, z + depth)
    ob.data.materials.append(material)
    return ob


def diamond(name, color, rough=0.35, scale=26.0, strength=0.35, metal=0.6):
    # embossed diamond-pattern sheet metal: a fine square grid turned 45 degrees
    m = mat(name, color, rough=rough, metal=metal)
    nt = m.node_tree
    p = nt.nodes['Principled BSDF']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Rotation'].default_value = (0, 0, math.radians(45))
    w = nt.nodes.new('ShaderNodeTexWave')
    w.wave_type = 'BANDS'
    w.inputs['Scale'].default_value = scale
    w2 = nt.nodes.new('ShaderNodeTexWave')
    w2.wave_type = 'BANDS'
    w2.bands_direction = 'Y'
    w2.inputs['Scale'].default_value = scale
    mx = nt.nodes.new('ShaderNodeMath')
    mx.operation = 'MULTIPLY'
    b = nt.nodes.new('ShaderNodeBump')
    b.inputs['Strength'].default_value = strength
    b.inputs['Distance'].default_value = 0.02
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    nt.links.new(mp.outputs['Vector'], w.inputs['Vector'])
    nt.links.new(mp.outputs['Vector'], w2.inputs['Vector'])
    nt.links.new(w.outputs['Fac'], mx.inputs[0])
    nt.links.new(w2.outputs['Fac'], mx.inputs[1])
    nt.links.new(mx.outputs['Value'], b.inputs['Height'])
    nt.links.new(b.outputs['Normal'], p.inputs['Normal'])
    return m


def worn(name, color, under, rough=0.5, under_rough=0.35, edge=0.12, amount=0.55, scale=2.5, scuffs=0.06, grain=None):
    # a paint or covering worn through at its edges and corners (and scuffed
    # here and there) to the material under it: a bevel-normal edge mask
    # broken up by noise drives the colour and the roughness
    m = mat(name, color, rough=rough)
    nt = m.node_tree
    p = nt.nodes['Principled BSDF']
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    bev = nt.nodes.new('ShaderNodeBevel')
    bev.samples = 8
    bev.inputs['Radius'].default_value = edge
    dot = nt.nodes.new('ShaderNodeVectorMath')
    dot.operation = 'DOT_PRODUCT'
    nt.links.new(geo.outputs['Normal'], dot.inputs[0])
    nt.links.new(bev.outputs['Normal'], dot.inputs[1])
    e = nt.nodes.new('ShaderNodeMapRange')          # 1 on a flat face, 0 on an edge -> edge mask 0..1
    e.inputs['From Min'].default_value = 0.995
    e.inputs['From Max'].default_value = 0.93
    nt.links.new(dot.outputs['Value'], e.inputs['Value'])
    n = nt.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = 12.0
    n.inputs['Roughness'].default_value = 0.7
    add = nt.nodes.new('ShaderNodeMath')
    add.operation = 'MULTIPLY'
    nt.links.new(e.outputs['Result'], add.inputs[0])
    nt.links.new(n.outputs['Fac'], add.inputs[1])
    # scuffs: rare specks of wear on the faces too
    n2 = nt.nodes.new('ShaderNodeTexNoise')
    n2.inputs['Scale'].default_value = scale * 6
    n2.inputs['Detail'].default_value = 8.0
    sc = nt.nodes.new('ShaderNodeMapRange')
    sc.inputs['From Min'].default_value = 0.72 - scuffs
    sc.inputs['From Max'].default_value = 0.74
    nt.links.new(n2.outputs['Fac'], sc.inputs['Value'])
    mx = nt.nodes.new('ShaderNodeMath')
    mx.operation = 'MAXIMUM'
    nt.links.new(add.outputs['Value'], mx.inputs[0])
    nt.links.new(sc.outputs['Result'], mx.inputs[1])
    th = nt.nodes.new('ShaderNodeMapRange')
    th.inputs['From Min'].default_value = 1.0 - amount
    th.inputs['From Max'].default_value = 1.0 - amount + 0.06
    nt.links.new(mx.outputs['Value'], th.inputs['Value'])
    mixc = nt.nodes.new('ShaderNodeMix')
    mixc.data_type = 'RGBA'
    mixc.inputs[6].default_value = (*srgb(color), 1)
    mixc.inputs[7].default_value = (*srgb(under), 1)
    nt.links.new(th.outputs['Result'], mixc.inputs['Factor'])
    nt.links.new(mixc.outputs[2], p.inputs['Base Color'])
    mixr = nt.nodes.new('ShaderNodeMapRange')
    mixr.inputs['To Min'].default_value = rough
    mixr.inputs['To Max'].default_value = under_rough
    nt.links.new(th.outputs['Result'], mixr.inputs['Value'])
    nt.links.new(mixr.outputs['Result'], p.inputs['Roughness'])
    if grain:
        # a leathery grain in the covering itself
        v = nt.nodes.new('ShaderNodeTexVoronoi')
        v.feature = 'SMOOTH_F1'
        v.inputs['Scale'].default_value = grain
        b = nt.nodes.new('ShaderNodeBump')
        b.inputs['Strength'].default_value = 0.6
        b.inputs['Distance'].default_value = 0.02
        b.invert = True
        nt.links.new(v.outputs['Distance'], b.inputs['Height'])
        nt.links.new(b.outputs['Normal'], p.inputs['Normal'])
    return m


def ink(thickness=1.1, color=(0.06, 0.05, 0.04)):
    # Freestyle outlines, as an inked drawing: silhouettes, borders, creases
    sc = bpy.context.scene
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = 'ABSOLUTE'
    sc.render.line_thickness = thickness
    fs = sc.view_layers[0].freestyle_settings
    ls = fs.linesets[0] if fs.linesets else fs.linesets.new('ink')
    if ls.linestyle is None:                  # a factory-reset scene has no line style yet
        ls.linestyle = bpy.data.linestyles.new('ink')
    ls.select_by_visibility = True
    ls.select_silhouette = ls.select_border = ls.select_crease = True
    ls.linestyle.color = color
    ls.linestyle.alpha = 0.85
