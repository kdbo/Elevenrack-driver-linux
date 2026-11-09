# Turn a finished illustration of a device into the editor's look, instead
# of rendering one: clear its background, paint out maker's marks, letter
# the rack's model name on, and cut each knob out so the editor can turn it.
#
#   python3 prepare_image.py <device> <source.png> <outdir>
#
# Writes <device>-body.png (the picture, transparent round it),
# <device>-knob-<key>.png per knob and <device>-image.json (placement and
# knob centres, read by export.py). The per-device recipe is in IMAGES.

import json, math, os, sys
from PIL import ImageChops, Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', '..', 'src', 'fonts', 'Damion.ttf')


def clear_background(im, sat_max=0.14, lum_min=150, warm=False):
    # (lum_min high, e.g. 225, when chrome parts touch the edge: they are pale and colourless too)
    # flood the pale, colourless surround (paper, sketched floor) from the
    # edges; the worn gold on the case's edges is saturated, so it stays
    rgb = im.convert('RGB')
    w, h = rgb.size
    cand = Image.new('L', (w, h), 0)
    px, cp = rgb.load(), cand.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            mx, mn = max(r, g, b), min(r, g, b)
            if mx >= lum_min and (mx - mn) <= sat_max * mx:
                cp[x, y] = 255
            elif warm and r - b > 22 and r > 70 and r >= g >= b:
                cp[x, y] = 255          # the paper's warm shadow (the device itself is grey)
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, h - 1), (w // 2, 0)):
        if cand.getpixel(seed) == 255:
            ImageDraw.floodfill(cand, seed, 128)
    alpha = cand.point(lambda v: 0 if v == 128 else 255).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    out = im.convert('RGBA')
    out.putalpha(alpha)
    box = alpha.getbbox()
    return out.crop(box), box


def patch(im, src_box, dst_box, feather=18):
    # cover dst_box with the texture from src_box (stretched to fit), soft-edged
    tile = im.crop(src_box).resize((dst_box[2] - dst_box[0], dst_box[3] - dst_box[1]), Image.LANCZOS)
    m = Image.new('L', tile.size, 0)
    ImageDraw.Draw(m).rectangle((feather, feather, tile.width - feather, tile.height - feather), fill=255)
    m = m.filter(ImageFilter.GaussianBlur(feather / 2))
    im.paste(tile, dst_box[:2], m)


def script_logo(im, text, centre, height, fill='#f1e4c0', edge='#2a1f12'):
    # cream script with a dark edge, a drop shadow and a lit upper rim, like a
    # moulded plastic logo
    f = ImageFont.truetype(SCRIPT, height)
    l, t, r, b = f.getbbox(text, stroke_width=4)
    pad = 30
    w, h = r - l + pad * 2, b - t + pad * 2
    org = (pad - l, pad - t)
    shadow = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((org[0] + 5, org[1] + 7), text, font=f, fill=(0, 0, 0, 170), stroke_width=4, stroke_fill=(0, 0, 0, 170))
    shadow = shadow.filter(ImageFilter.GaussianBlur(5))
    face = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(face).text(org, text, font=f, fill=fill, stroke_width=4, stroke_fill=edge)
    rim = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(rim).text((org[0] - 1, org[1] - 2), text, font=f, fill=(255, 250, 235, 120))
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).text(org, text, font=f, fill=255)
    rim.putalpha(Image.composite(rim.getchannel('A'), Image.new('L', (w, h), 0), mask))
    x, y = round(centre[0] - w / 2), round(centre[1] - h / 2)
    im.alpha_composite(shadow, (x, y))
    im.alpha_composite(face, (x, y))
    im.alpha_composite(rim, (x, y))


def label(im, text, centre, size, fill='#eadcb6', squeeze=0.78, weight='ExtraBold'):
    # condensed capitals like a panel's printed legends
    f = ImageFont.truetype(os.path.join(HERE, '..', '..', 'src', 'fonts', 'Manrope.ttf'), size)
    f.set_variation_by_name(weight)
    l, t, r, b = f.getbbox(text)
    t_im = Image.new('RGBA', (r - l + 8, b - t + 8), (0, 0, 0, 0))
    ImageDraw.Draw(t_im).text((4 - l, 4 - t), text, font=f, fill=fill)
    t_im = t_im.resize((round(t_im.width * squeeze), t_im.height), Image.LANCZOS)
    im.alpha_composite(t_im, (round(centre[0] - t_im.width / 2), round(centre[1] - t_im.height / 2)))


def dial(im, centre, r, fill='#eadcb6', numbers=True, width=2, long=10, short=7):
    # a printed 0-10 scale round a knob: ticks, and the even numbers
    d = ImageDraw.Draw(im)
    x, y = centre
    for i in range(11):
        a = math.radians(225 - 27 * i)
        p0 = (x + math.cos(a) * r, y - math.sin(a) * r)
        p1 = (x + math.cos(a) * (r + (short if i % 5 else long)), y - math.sin(a) * (r + (short if i % 5 else long)))
        d.line((p0, p1), fill=fill, width=width)
        if numbers and i % 2 == 0:
            label(im, str(i), (x + math.cos(a) * (r + 20), y - math.sin(a) * (r + 20)), 15, fill=fill, squeeze=0.9)


def lamp(im, centre, r=9):
    # a small panel LED, unlit: dark red lens in a chrome bezel
    d = ImageDraw.Draw(im)
    x, y = centre
    d.ellipse((x - r - 3, y - r - 3, x + r + 3, y + r + 3), fill='#b8b2a2', outline='#3a3428', width=2)
    d.ellipse((x - r, y - r, x + r, y + r), fill='#4a0e0a')
    d.ellipse((x - r * 0.5, y - r * 0.6, x - r * 0.05, y - r * 0.15), fill='#a0453a')


def cut_knob(im, centre, r, feather=1.5):
    x, y = centre
    box = (round(x - r - 2), round(y - r - 2), round(x + r + 2), round(y + r + 2))
    k = im.crop(box)
    m = Image.new('L', k.size, 0)
    c = (k.width / 2, k.height / 2)
    ImageDraw.Draw(m).ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), fill=255)
    k.putalpha(m.filter(ImageFilter.GaussianBlur(feather)))
    return k


# ── per device: what to paint out, the name to letter on, the knobs ──
def plexi(name):
    def prepare(src, out):
        im = Image.open(src).convert('RGBA')
        # paint out the maker's script (from the plain tolex to its left) and the
        # model badge on the panel (from the plain gold under it)
        patch(im, (200, 140, 600, 385), (695, 140, 1115, 385), feather=14)       # left half, from plain tolex on the left
        patch(im, (1560, 140, 1960, 385), (1075, 140, 1495, 385), feather=14)    # right half, from the right
        patch(im, (288, 568, 362, 604), (288, 526, 362, 570), feather=5)
        script_logo(im, name, (1095, 258), 150)          # the rack's model name
        knobs = {str(i): (793 + 154.4 * i, 547) for i in range(6)}
        return dict(im=im, knobs=knobs, r=33)
    return prepare


def ep3(src, out):
    im = Image.open(src).convert('RGBA')
    big = {'03': (555, 200), '02': (773, 200), '04': (991, 200)}        # Sustain = Feedback, Volume = Mix, Echo Delay = Delay
    r = 60
    # RECORD / ECHO become the Expanded and Tape Hiss switches: paint the
    # legends out with plain panel from under the toggles, letter the new ones
    patch(im, (1128, 258, 1240, 298), (1128, 74, 1240, 116), feather=6)
    patch(im, (1258, 258, 1360, 298), (1256, 74, 1362, 116), feather=6)
    label(im, 'EXPAND', (1185, 95), 30)
    label(im, 'HISS', (1307, 95), 30)
    # the name in the empty box top left
    script_logo(im, 'Tape Echo', (295, 128), 66, fill='#eadcb6', edge='#1a140c')
    # the trims on the dark plate behind the glass, as smaller copies of the knobs
    small = {'06': (770, 448), '08': (905, 448), '07': (1040, 448)}
    piece = cut_knob(im, big['03'], r)
    sc = 0.5
    for k, (x, y) in small.items():
        p = piece.resize((round(piece.width * sc), round(piece.height * sc)), Image.LANCZOS)
        dial(im, (x, y), r * sc + 3, numbers=False)
        im.alpha_composite(p, (round(x - p.width / 2), round(y - p.height / 2)))
    for (k, (x, y)), lab in zip(small.items(), ('REC LEVEL', 'HEAD TILT', 'WOW')):
        label(im, lab, (x, y + 52), 20)
    label(im, 'SYNC', (1250, 410), 20)
    knobs = dict(big)
    knobs.update({k: (x, y, sc) for k, (x, y) in small.items()})
    # the switches' bat, flipped for their ON position, and a lamp beside each
    toggles = {'tgl-09': (1183, 185, 42), 'tgl-0a': (1307, 187, 42)}
    leds = {'tgl-09': (1232, 190), 'tgl-0a': (1352, 190)}
    for c in leds.values():
        lamp(im, c)
    return dict(im=im, knobs=knobs, r=r, crop_from={k: '03' for k in small}, lum_min=225, toggles=toggles, leds=leds,
                switch=(352, 262, 28), led=(241, 258),
                controls={'tgl-09': (1186, 190, 50, 70), 'tgl-0a': (1307, 190, 50, 70), 'sync-select': (1250, 452, 220, 52)})


def green_jrc(src, out):
    im = Image.open(src).convert('RGBA')
    # the maker's model name: paint it out with plain green from under the
    # type line, letter the rack's name on in the same condensed cream capitals
    patch(im, (215, 980, 820, 1044), (205, 772, 830, 922), feather=12)
    label(im, 'GREEN JRC', (512, 842), 104, fill='#f1e4bf', squeeze=0.72)
    knobs = {'02': (281, 231), '04': (745, 231), '03': (511, 430, 104 / 116)}
    return dict(im=im, knobs=knobs, r=116, crop_r={'03': 104}, switch=(507, 1172, 150), led=(505, 123))


def jtm45(src, out):
    im = Image.open(src).convert('RGBA')
    script_logo(im, 'J45', (1086, 222), 175)                 # the empty tolex above the piping bar
    knobs = {str(i): c for i, c in enumerate(((714, 542), (886, 542), (1056, 542), (1228, 542), (1400, 542), (1568, 543)))}
    return dict(im=im, knobs=knobs, r=34)                    # the gold cap only, as on the Lead 800


def white_boost(src, out):
    im = Image.open(src).convert('RGBA')
    # four knobs as on the rack: Gain, Volume over Bass, Treble; each turns whole
    # (its pointer reaches over the skirt), round its cap's centre
    knobs = {'02': (304, 218), '05': (724, 218), '04': (304, 562), '03': (723, 562)}
    return dict(im=im, knobs=knobs, r=118, switch=(512, 1210, 120), led=(512, 128))

def lead800(src, out):
    im = Image.open(src).convert('RGBA')
    script_logo(im, 'Lead 800', (1086, 268), 170)            # the empty tolex above the panel
    # the caps' own centres (the drawing sets each a little off its skirt's)
    knobs = {str(i): c for i, c in enumerate(((661, 545), (846.5, 544.5), (1037.5, 544.5), (1232, 545), (1451, 545), (1642.5, 545)))}
    # only the gold cap with its pointer turns: the skirt and its shadow, drawn
    # falling to the lower right, stay where they are
    return dict(im=im, knobs=knobs, r=32)


def patch_tiled(im, src_box, dst_box, feather=10, mirror=True, oval=False):
    # cover dst_box with copies of src_box laid side by side (mirrored every
    # other one so the seams match) instead of stretching it
    sw, sh = src_box[2] - src_box[0], src_box[3] - src_box[1]
    tile = im.crop(src_box)
    w, h = dst_box[2] - dst_box[0], dst_box[3] - dst_box[1]
    canvas = Image.new('RGBA', (w, h))
    for j, y in enumerate(range(0, h, sh)):
        for i, x in enumerate(range(0, w, sw)):
            t = tile
            if mirror and i % 2: t = t.transpose(Image.FLIP_LEFT_RIGHT)
            if mirror and j % 2: t = t.transpose(Image.FLIP_TOP_BOTTOM)
            canvas.paste(t, (x, y))
    m = Image.new('L', (w, h), 0)
    (ImageDraw.Draw(m).ellipse if oval else ImageDraw.Draw(m).rectangle)((feather, feather, w - feather, h - feather), fill=255)
    im.paste(canvas, dst_box[:2], m.filter(ImageFilter.GaussianBlur(feather / 2)))


def patch_poly(im, src_box, poly, feather=4, flat=False):
    # cover a polygon with tiles of src_box (for slanted lettering); flat: with
    # src_box's mean colour and a fine grain instead, where the tiles would repeat visibly
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    box = (min(xs) - feather, min(ys) - feather, max(xs) + feather, max(ys) + feather)
    sw, sh = src_box[2] - src_box[0], src_box[3] - src_box[1]
    tile = im.crop(src_box)
    canvas = Image.new('RGBA', (box[2] - box[0], box[3] - box[1]))
    for j, y in enumerate(range(0, canvas.height, sh)):
        for i, x in enumerate(range(0, canvas.width, sw)):
            t = tile.transpose(Image.FLIP_LEFT_RIGHT) if i % 2 else tile
            canvas.paste(t.transpose(Image.FLIP_TOP_BOTTOM) if j % 2 else t, (x, y))
    if flat:
        from PIL import ImageStat
        mean = tuple(round(v) for v in ImageStat.Stat(tile.convert('RGB')).mean)
        grain = Image.effect_noise(canvas.size, 10).convert('L')       # centred on 128
        canvas = Image.merge('RGB', [grain.point(lambda v, c=c: max(0, min(255, round(c + (v - 128) * 0.6)))) for c in mean]).convert('RGBA')
    m = Image.new('L', canvas.size, 0)
    ImageDraw.Draw(m).polygon([(x - box[0], y - box[1]) for x, y in poly], fill=255)
    im.paste(canvas, box[:2], m.filter(ImageFilter.GaussianBlur(feather / 2)))


def patch_ellipse(im, src_box, centre, rx, ry, feather=10):
    # cover an oval with texture from src_box, soft-edged (for a logo in a bay)
    w, h = 2 * rx, 2 * ry
    tile = im.crop(src_box).resize((w, h), Image.LANCZOS)
    m = Image.new('L', (w, h), 0)
    ImageDraw.Draw(m).ellipse((feather, feather, w - feather, h - feather), fill=255)
    im.paste(tile, (centre[0] - rx, centre[1] - ry), m.filter(ImageFilter.GaussianBlur(feather / 2)))


def fitted(im, text, box, fill, weight='ExtraBold', opacity=0.92):
    # capitals filling a box: sized to its height, squeezed to its width;
    # a little see-through so the paint's texture shows, as printed ink
    x0, y0, x1, y1 = box
    f = ImageFont.truetype(os.path.join(HERE, '..', '..', 'src', 'fonts', 'Manrope.ttf'), round((y1 - y0) * 1.32))
    f.set_variation_by_name(weight)
    l, t, r, b = f.getbbox(text)
    t_im = Image.new('RGBA', (r - l, b - t), (0, 0, 0, 0))
    ImageDraw.Draw(t_im).text((-l, -t), text, font=f, fill=fill)
    t_im = t_im.resize((x1 - x0, y1 - y0), Image.LANCZOS)
    t_im.putalpha(t_im.getchannel('A').point(lambda v: round(v * opacity)))
    im.alpha_composite(t_im, (x0, y0))


def tri_fuzz(src, out):
    im = Image.open(src).convert('RGBA')
    red = '#c41e18'
    # the maker's name and its symbol: paint out with plain cream from the
    # top of the box, then the rack's name in red block capitals, and Fuzz
    # in red script in the bay
    patch_tiled(im, (330, 110, 700, 185), (78, 584, 948, 776), feather=8)
    fitted(im, 'TRI-KNOB', (100, 606, 924, 750), red)
    patch_tiled(im, (380, 110, 560, 185), (380, 752, 642, 962), feather=8, oval=True)
    patch_tiled(im, (380, 110, 560, 185), (360, 740, 660, 812), feather=6)       # the symbol's top, above the rule   # inside the bay's red arc
    f = ImageFont.truetype(SCRIPT, 132)
    l, t, r, b = f.getbbox('Fuzz')
    t_im = Image.new('RGBA', (r - l + 8, b - t + 8), (0, 0, 0, 0))
    ImageDraw.Draw(t_im).text((4 - l, 4 - t), 'Fuzz', font=f, fill=red)
    t_im.putalpha(t_im.getchannel('A').point(lambda v: round(v * 0.92)))
    im.alpha_composite(t_im, (511 - t_im.width // 2, 862 - t_im.height // 2))
    # the knobs' top faces turn; their side walls stay
    knobs = {'04': (205, 298), '03': (511, 298), '02': (818, 298)}
    return dict(im=im, knobs=knobs, r=100, switch=(512, 1125, 95), led=(360, 507))


def dc_dist(src, out):
    im = Image.open(src).convert('RGBA')
    # the maker's logo at the top: plain black plate from near the foot over it
    patch_tiled(im, (472, 196, 552, 392), (232, 71, 818, 174), feather=3)       # (from the plain plate between the top knobs)
    # Drive is the rack's Distortion
    knobs = {'02': (323, 300), '05': (693, 300), '04': (323, 610), '03': (693, 610)}
    return dict(im=im, knobs=knobs, r=96, switch=(512, 1150, 95), led=(512, 793))


def warp_onto(im, flat, quad):
    # lay a flat picture onto a quadrilateral (its top-left, top-right,
    # bottom-right, bottom-left corners) seen in perspective
    w, h = flat.size
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    # solve for the 8 coefficients mapping each output point back into the flat picture
    A, B = [], []
    for (x, y), (u, v) in zip(quad, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    n = 8
    M = [row[:] + [b] for row, b in zip(A, B)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    coef = [M[i][n] / M[i][i] for i in range(n)]
    layer = flat.transform(im.size, Image.PERSPECTIVE, coef, Image.BICUBIC)
    im.alpha_composite(layer)


def fv_vol(src, out):
    im = Image.open(src).convert('RGBA')
    # nothing to paint out; no knobs in the picture: Volume and Min Vol as
    # bars, and the taper switch, in a strip under it (CSS px)
    return dict(im=im, knobs={}, r=10, pad_bottom=155, sat_max=0.3, lum_min=170, warm=True,
                bars={'02': (220, 'VOLUME'), '03': (262, 'MIN VOL')},
                css_controls={'tgl-04': (220, 326, 110, 26, 'plain')})

def treadle_strip(**extra):
    # a treadle pedal drawn in one position: no knobs to cut; the treadle's
    # value as a bar under the picture (CSS px), and anything else beside it
    rec = dict(knobs={}, r=10, pad_bottom=64, sat_max=0.3, lum_min=170, warm=True, bars={'02': (220, 'POSITION')})
    rec.update(extra)
    return rec


def moulded_name(im, text, quad, size, face=(58, 57, 55, 255)):
    # a name moulded into a rubber pad, laid on in the pad's perspective
    flat = Image.new('RGBA', (1000, 520), (0, 0, 0, 0))
    f = ImageFont.truetype(SCRIPT, size)
    l, t, r, b = f.getbbox(text)
    ox, oy = (1000 - (r - l)) // 2 - l, (520 - (b - t)) // 2 - t
    d = ImageDraw.Draw(flat)
    d.text((ox + 5, oy + 7), text, font=f, fill=(8, 8, 8, 230))
    d.text((ox - 3, oy - 4), text, font=f, fill=(150, 146, 138, 200))
    d.text((ox, oy), text, font=f, fill=face)
    warp_onto(im, flat, quad)


def shine_wah(src, out):
    im = Image.open(src).convert('RGBA')
    # the smooth pad on the treadle (its top-left, top-right, bottom-right,
    # bottom-left corners), the name moulded across it
    moulded_name(im, 'Shine', [(725, 190), (985, 440), (742, 476), (470, 222)], 300)   # reading along the treadle
    return dict(im=im, **treadle_strip())


def black_wah(src, out):
    im = Image.open(src).convert('RGBA')
    # a name plate on the base's front end, as on the real pedal: dark, a
    # thin chrome rim, the name in white lower-case
    flat = Image.new('RGBA', (1000, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(flat)
    d.rounded_rectangle((4, 4, 996, 296), radius=34, fill=(20, 20, 21, 255), outline=(196, 190, 176, 255), width=10)
    d.rounded_rectangle((18, 18, 982, 282), radius=26, outline=(70, 68, 64, 255), width=3)
    f = ImageFont.truetype(os.path.join(HERE, '..', '..', 'src', 'fonts', 'Manrope.ttf'), 190)
    f.set_variation_by_name('ExtraBold')
    l, t, r, b = f.getbbox('black')
    d.text(((1000 - (r - l)) // 2 - l, (300 - (b - t)) // 2 - t), 'black', font=f, fill=(238, 236, 230, 255))
    warp_onto(im, flat, [(842, 792), (1222, 748), (1240, 852), (860, 905)])
    return dict(im=im, **treadle_strip())


def cut_wing(im, centre, r, boss=(0, -3, 48), wing=((-11, -79), (5, -79), (18, 88), (-38, 88)), panel=(22, 22, 23)):
    # lift a chicken-head knob off its printed dial by its shape: the round
    # boss and the wing (offsets from the shaft, in source pixels); the panel
    # is painted in where it was, so the drawing's own knob is gone
    x, y = round(centre[0]), round(centre[1])
    box = (x - r - 2, y - r - 2, x + r + 2, y + r + 2)
    k = im.crop(box)
    c = k.width / 2
    m = Image.new('L', k.size, 0)
    d = ImageDraw.Draw(m)
    bx, by, br = boss
    d.ellipse((c + bx - br, c + by - br, c + bx + br, c + by + br), fill=255)
    d.polygon([(c + u, c + v) for u, v in wing], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(1.2))
    k.putalpha(m)
    grain = Image.effect_noise(k.size, 8).convert('L')
    fill = Image.merge('RGB', [grain.point(lambda v, cc=cc: max(0, min(255, round(cc + (v - 128) * 0.4)))) for cc in panel]).convert('RGBA')
    im.paste(fill, box[:2], m.filter(ImageFilter.MaxFilter(3)))
    return k


def vibe(src, out):
    im = Image.open(src).convert('RGBA')
    panel = (22, 22, 23)
    # the name: plain panel over it, the rack's name in the same cream script
    patch_tiled(im, (1150, 130, 1330, 225), (430, 112, 1150, 238), feather=8)
    script_logo(im, 'Vibe Phaser', (790, 172), 130, fill='#f3efe4', edge='#0c0c0c')
    pieces = {'04': cut_wing(im, (270, 368), 92), '03': cut_wing(im, (834, 368), 92)}
    # Speed (the original's foot controller) where the fuse is
    patch_tiled(im, (1150, 280, 1220, 340), (1020, 300, 1150, 440), feather=10, oval=True)
    dial(im, (1085, 368), 60, fill='#ecebe6', numbers=False, width=3, long=12, short=8)
    label(im, 'SPEED', (1085, 482), 34, fill='#ecebe6', squeeze=0.8)
    # Sync where the foot-control socket is
    patch_tiled(im, (1150, 560, 1230, 620), (850, 555, 1060, 760), feather=10)
    label(im, 'SYNC', (953, 705), 34, fill='#ecebe6', squeeze=0.8)
    sc = 0.78
    knobs = {'04': (270, 368), '03': (834, 368), '02': (1085, 368, sc)}
    pieces['02'] = pieces['03']
    return dict(im=im, knobs=knobs, r=92, pieces=pieces, switch=(1302, 630, 46), led=(1302, 372), sat_max=0.3, lum_min=180,
                controls={'tgl-05': (548, 372, 124, 58, 'rocker-r0'), 'sync-06': (953, 640, 190, 48)})


def ce1(src, out):
    im = Image.open(src).convert('RGBA')
    # no level knob on the rack: the level control becomes the sync picker
    patch_tiled(im, (448, 300, 548, 470), (286, 266, 436, 471), feather=4)
    label(im, 'sync', (378, 300), 34, fill='#1c1c1e', squeeze=0.95, weight='Bold')
    # the caps turn, their chrome skirts and printed dots stay
    knobs = {'02': (656, 324), '03': (910, 324), '04': (1120, 328)}
    return dict(im=im, knobs=knobs, r=46, switch=(283, 808, 56), led=(283, 598), sat_max=0.3, lum_min=180,
                controls={'tgl-05': (1248, 808, 112, 112), 'sync-06': (378, 352, 104, 40)},
                leds={'tgl-05': (1246, 598)})


def orange_phaser(src, out):
    im = Image.open(src).convert('RGBA')
    ink = '#1c1408'
    # the maker's model name: plain orange from above it, the rack's name in
    # the same thin lower-case
    patch_tiled(im, (560, 700, 680, 760), (568, 778, 972, 862), feather=8)
    f = ImageFont.truetype(os.path.join(HERE, '..', '..', 'src', 'fonts', 'Manrope.ttf'), 64)
    f.set_variation_by_name('Light')
    l, t, r, b = f.getbbox('orange phaser')
    t_im = Image.new('RGBA', (r - l + 8, b - t + 8), (0, 0, 0, 0))
    ImageDraw.Draw(t_im).text((4 - l, 4 - t), 'orange phaser', font=f, fill=ink)
    t_im = t_im.resize((round(t_im.width * 0.92), t_im.height), Image.LANCZOS)
    im.alpha_composite(t_im, (770 - t_im.width // 2, 822 - t_im.height // 2))
    label(im, 'SYNC', (768, 418), 26, fill=ink, squeeze=0.95)
    # the scalloped top face turns; its side wall stays
    return dict(im=im, knobs={'02': (770, 177)}, r=106, switch=(768, 664, 70), led=(768, 552), sat_max=0.3, lum_min=180,
                controls={'sync-03': (768, 458, 190, 44)})


def flanger(src, out):
    im = Image.open(src).convert('RGBA')
    plain = (450, 110, 580, 175)               # bare purple between RATE and DEPTH
    # the rack's names: REGEN is its Feedback, MIX its Pre-Delay
    patch_tiled(im, plain, (226, 448, 392, 502), feather=8)
    patch_tiled(im, plain, (672, 448, 778, 502), feather=8)
    label(im, 'FEEDBACK', (305, 475), 42, squeeze=0.8)
    label(im, 'PRE-DELAY', (720, 475), 42, squeeze=0.76)
    # the MANUAL toggle goes; the Sync picker sits under the knobs, where the
    # middle column is clear
    patch_tiled(im, (452, 604, 578, 700), (422, 352, 606, 604), feather=12)
    label(im, 'SYNC', (512, 700), 30, squeeze=0.86)
    # the LED drawn lit: a dark lens, the editor lights it
    d = ImageDraw.Draw(im)
    d.ellipse((512 - 31, 1028 - 31, 512 + 31, 1028 + 31), fill='#2a0a3c')
    d.ellipse((498, 1012, 512, 1024), fill='#6a3a86')
    return dict(im=im, knobs={'02': (305, 280), '03': (720, 280), '04': (305, 650), '05': (720, 650)}, r=118,
                switch=(512, 1225, 105), led=(512, 1028), sat_max=0.3, lum_min=180,
                controls={'sync-06': (512, 752, 270, 52)})


def graphic_eq(src, out):
    im = Image.open(src).convert('RGBA')
    # the fader caps become sprites the editor slides; under each, the same
    # fader's bare groove from a stretch whole tick steps away (so its tick
    # dashes line up, where they show), soft-edged wide enough to take the cap's shadow, but
    # keeping the printed numbers, which differ from tick to tick
    cap = im.crop((418 - 40, 382 - 40, 418 + 40, 382 + 40))
    m = Image.new('L', cap.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((7, 6, 73, 74), radius=9, fill=255)
    cap.putalpha(m.filter(ImageFilter.GaussianBlur(0.8)))
    grey = im.convert('L')
    for (cx, cy), shift, (t, b) in (((285, 538), -153, (80, 92)), ((418, 382), 169, (80, 92)), ((551, 427), 113, (58, 80)),
                                    ((681, 350), 169, (70, 80)), ((813, 538), -153, (80, 92)), ((941, 428), 120, (66, 90))):
        dst = (cx - 58, cy - t, cx + 58, cy + b)
        src_box = (dst[0], dst[1] + shift, dst[2], dst[3] + shift)
        tile = im.crop(src_box)
        mk = Image.new('L', tile.size, 0)
        ImageDraw.Draw(mk).rectangle((14, 14, tile.width - 14, tile.height - 14), fill=255)
        mk = mk.filter(ImageFilter.GaussianBlur(7))
        ink = Image.new('L', tile.size, 0)
        for g in (grey.crop(src_box), grey.crop(dst)):
            ink.paste(255, (0, 0), g.point(lambda v: 255 if v < 140 else 0))
        # the groove, and the cap's own footprint (its dark line, and the
        # dashes it hid: those match in the stretch copied) are taken whole
        ImageDraw.Draw(ink).rectangle((58 - 30, 0, 58 + 30, tile.height), fill=0)
        ImageDraw.Draw(ink).rectangle((58 - 37, t - 42, 58 + 37, t + 46), fill=0)
        ink = ink.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(1.5))
        mk = ImageChops.subtract(mk, ink)
        im.paste(tile, dst[:2], mk)
    # the 2 kHz cap hid half its "+12": the 800 Hz one, whole
    lab = im.crop((466, 324, 518, 353))
    m = Image.new('L', lab.size, 0)
    ImageDraw.Draw(m).rectangle((2, 2, lab.width - 3, lab.height - 3), fill=255)
    im.paste(lab, (595, 324), m.filter(ImageFilter.GaussianBlur(1.5)))
    # the LED drawn lit (and its glow on the paint): dark, the editor lights it
    patch_tiled(im, (380, 760, 460, 840), (552, 754, 644, 846), feather=6, oval=True)
    d = ImageDraw.Draw(im)
    d.ellipse((598 - 29, 800 - 29, 598 + 29, 800 + 29), fill='#b9b4ad', outline='#5a5650', width=2)
    d.ellipse((598 - 23, 800 - 23, 598 + 23, 800 + 23), fill='#3c0c08')
    d.ellipse((585, 787, 597, 797), fill='#8a3a32')
    # the white case on cream paper: cut out by its outline, not its colour
    shape = Image.new('L', im.size, 0)
    ImageDraw.Draw(shape).rounded_rectangle((115, 7, 1083, 1273), radius=58, fill=255)
    px = im.convert('RGB').load()
    for x0, x1 in ((66, 116), (1082, 1134)):
        for y in range(505, 665):
            for x in range(x0, x1):
                r, g, b = px[x, y]
                if max(r, g, b) - min(r, g, b) < 0.13 * max(r, g, b, 1):
                    shape.putpixel((x, y), 255)
    tracks = {'02': (285, 612, 306), '03': (418, 624, 286), '04': (551, 624, 286),
              '05': (681, 624, 287), '06': (813, 612, 306), '07': (941, 611, 298)}
    return dict(im=im, knobs={}, r=40, switch=(598, 975, 90), led=(598, 800), shape=shape,
                sprites={'cap': cap}, sliders={k: ((x, y0), (x, y1), 'cap', 80) for k, (x, y0, y1) in tracks.items()})


def multi_chorus(src, out):
    im = Image.open(src).convert('RGBA')
    ink = '#f2f4f8'
    top = (290, 318, 470, 338)                    # bare blue
    # the scale ends as the rack shows them: Rate as a period, Depth and
    # Pre Delay up to 24 ms, Low Cut from 24 Hz, Width up to 100 %; each
    # painted over with the blue just under it (the panel's light varies)
    for (x0, x1), y, text in (((286, 372), 302, '0.01 s'), ((409, 478), 302, '10 s'), ((549, 597), 302, '0 ms'),
                              ((656, 728), 302, '24 ms'), ((907, 982), 302, '24 ms'), ((127, 197), 588, '24 Hz'),
                              ((554, 630), 588, '100 %')):
        patch_tiled(im, (x0 - 8, y + 20, x1 + 8, y + 37), (x0 - 8, y - 19, x1 + 8, y + 19), feather=4)
        label(im, text, ((x0 + x1) / 2, y), 31, fill=ink, squeeze=0.84, weight='Bold')
    # the drawn Sync box: the editor's own picker takes its place
    patch_tiled(im, (90, 302, 260, 322), (66, 216, 284, 312), feather=6)
    # both LEDs drawn lit: dark lenses, the editor lights them (SYNC's while
    # a Sync value is picked)
    for (x, y), r in (((171, 139), 16), ((655, 812), 19)):
        patch_tiled(im, top, (x - r - 22, y - r - 22, x + r + 22, y + r + 22), feather=10, oval=True)
        d = ImageDraw.Draw(im)
        d.ellipse((x - r - 3, y - r - 3, x + r + 3, y + r + 3), fill='#a9b0bb', outline='#0a1530', width=2)
        d.ellipse((x - r, y - r, x + r, y + r), fill='#0b1a3e')
        d.ellipse((x - r * 0.5, y - r * 0.6, x - r * 0.05, y - r * 0.15), fill='#3b5a92')
    knobs = {'02': (381, 202), '04': (626, 202), '06': (885, 202), '05': (1137, 202), '08': (224, 491), '09': (524, 491)}
    # Voices: the rack has 1, 2, 3, 4 and 6 voices; its knob points at those
    # printed ticks (it was drawn at the 4)
    voices = cut_knob(im, (1092, 502), 58)
    return dict(im=im, knobs=knobs, r=72, switch=(655, 945, 85), led=(655, 812), sat_max=0.3, lum_min=180, warm=True,
                toggles={'tgl-0a': (801, 500, 40)}, leds={'sync-03': (171, 139)},
                sprites={'knob-sel-07': voices},
                dials={'sel-07': dict(at=(1092, 502), r=58, angles=[-120, -70, -30, 29, 120], drawn=29)},
                controls={'sync-03': (175, 262, 180, 58), 'tgl-0a': (801, 500, 80, 84), 'sel-07': (1092, 502, 116, 116, 'knob')})


def roto(src, out):
    im = Image.open(src).convert('RGBA')
    # the drawn TYPE box ("Classic" is none of the rack's types): the
    # editor's picker takes its place; wood from beside it, the grain runs across
    patch_tiled(im, (630, 506, 698, 606), (700, 506, 1000, 606), feather=8)
    # the lamps drawn lit (BREAK, and the on LED): an unlit one in their place
    dark = im.crop((1218 - 17, 532 - 17, 1218 + 17, 532 + 17))
    m = Image.new('L', dark.size, 0)
    ImageDraw.Draw(m).ellipse((1, 1, dark.width - 2, dark.height - 2), fill=255)
    m = m.filter(ImageFilter.GaussianBlur(1))
    for (x, y), wood in (((1218, 583), (1120, 553, 1180, 613)), ((835, 648), (740, 616, 796, 680))):
        patch_tiled(im, wood, (x - 34, y - 32, x + 34, y + 32), feather=8, oval=True)
        im.paste(dark, (x - 17, y - 17), m)
    # the reddish wood on cream paper: cut out by its outline (with the jacks
    # and feet, where they are not paper-coloured)
    shape = Image.new('L', im.size, 0)
    ImageDraw.Draw(shape).rounded_rectangle((44, 26, 1623, 918), radius=44, fill=255)
    px = im.convert('RGB').load()
    for x0, y0, x1, y1 in ((8, 430, 46, 545), (1621, 410, 1664, 560), (145, 8, 262, 28), (1405, 8, 1527, 28)):
        for y in range(y0, y1):
            for x in range(x0, x1):
                r, g, b = px[x, y]
                if max(r, g, b) - min(r, g, b) < 0.15 * max(r, g, b, 1) or max(r, g, b) < 120:
                    shape.putpixel((x, y), 255)
    return dict(im=im, knobs={'04': (410, 570)}, r=66, switch=(832, 730, 58), led=(835, 648), shape=shape,
                leds={'sel-02:2': (1218, 532), 'sel-02:1': (1218, 583), 'sel-02:0': (1218, 634)},
                controls={'sel-03': (849, 556, 250, 54), 'sel-02': (1268, 583, 180, 158, 'hidden')})


def rack_bypass(im, x, y_led, y_button, caption=True):
    # a purple LED over a chrome push button (the rack panels have no bypass drawn)
    d = ImageDraw.Draw(im)
    d.ellipse((x - 13, y_led - 13, x + 13, y_led + 13), fill='#9a9aa0', outline='#111114', width=2)
    d.ellipse((x - 9, y_led - 9, x + 9, y_led + 9), fill='#1e0f33')
    d.ellipse((x - 5, y_led - 6, x - 1, y_led - 2), fill='#5a3d8a')
    y = y_button
    d.ellipse((x - 30, y - 30, x + 30, y + 30), fill='#0c0c0e')
    for i in range(24, 0, -1):
        v = int(70 + 140 * (1 - i / 24) ** 0.8)
        d.ellipse((x - i - 2, y - i - 4, x + i - 2, y + i - 4) if i < 8 else (x - i, y - i, x + i, y + i), fill=(v, v, v + 4))
    if caption:
        label(im, 'BYPASS', (x, y + 47), 18, fill='#c8c8ce', squeeze=0.9, weight='SemiBold')


def rack_bypass_small(im, x_led, x_button, y):
    # a smaller purple LED beside a smaller push button, where a panel has no room for rack_bypass
    d = ImageDraw.Draw(im)
    x = x_led
    d.ellipse((x - 11, y - 11, x + 11, y + 11), fill='#9a9aa0', outline='#111114', width=2)
    d.ellipse((x - 7, y - 7, x + 7, y + 7), fill='#1e0f33')
    d.ellipse((x - 4, y - 5, x - 1, y - 2), fill='#5a3d8a')
    x = x_button
    d.ellipse((x - 24, y - 24, x + 24, y + 24), fill='#0c0c0e')
    for i in range(19, 0, -1):
        v = int(70 + 140 * (1 - i / 19) ** 0.8)
        d.ellipse((x - i - 2, y - i - 3, x + i - 2, y + i - 3) if i < 7 else (x - i, y - i, x + i, y + i), fill=(v, v, v + 4))


def dyn3(src, out):
    im = Image.open(src).convert('RGBA')
    # the scale ends as the rack shows them: Ratio to 100:1, Attack 10 us to
    # 300 ms, Release to 4 s, Gain 0 to 40 dB; painted over with the brushed
    # metal just under them (its grain runs across)
    for (x0, x1), text in (((805, 843), '100:1'), ((942, 1013), '10 \u00b5s'), ((1060, 1138), '300 ms'),
                           ((1348, 1381), '4 s'), ((1722, 1801), '0 dB'), ((1845, 1923), '40 dB')):
        patch_tiled(im, (x0 - 10, 492, x1 + 10, 514), (x0 - 10, 456, x1 + 10, 491), feather=4)
        label(im, text, ((x0 + x1) / 2, 476 if '\u00b5' in text else 473), 27, fill='#e2e2e6', squeeze=0.92, weight='SemiBold')
    # no bypass in the drawing: one in the free space right of GAIN
    rack_bypass(im, 1975, 300, 385)
    shape = Image.new('L', im.size, 0)
    ImageDraw.Draw(shape).rounded_rectangle((8, 151, 2163, 561), radius=14, fill=255)
    knobs = {'02': (500, 360), '05': (764, 360), '03': (1035, 360), '04': (1298, 360), '06': (1558, 360), '07': (1822, 360)}
    return dict(im=im, knobs=knobs, r=76, switch=(1975, 385, 30), led=(1975, 300), shape=shape)


def param_eq(src, out):
    im = Image.open(src).convert('RGBA')
    M = '\u2212'
    # the ranges as the rack has them; each old legend painted over with the
    # brushed metal under it (or beside it, where the Q knob is below)
    for (x0, x1), y, text, dx, dy in (
            ((345, 417), 403, M + '24 dB', 0, 22), ((595, 650), 403, '2 kHz', 0, 22), ((445, 470), 537, '0.2', -65, 0),
            ((725, 780), 403, M + '18 dB', 0, 22), ((803, 860), 403, '+18 dB', 0, 22), ((978, 1038), 403, '10 kHz', 0, 22),
            ((825, 852), 537, '0.2', -65, 0),
            ((1115, 1178), 403, M + '18 dB', 0, 22), ((1195, 1252), 403, '+18 dB', 0, 22), ((1295, 1352), 403, '200 Hz', 0, 22),
            ((1370, 1428), 403, '20 kHz', 0, 22), ((1222, 1248), 537, '0.2', -65, 0),
            ((1515, 1578), 403, M + '24 dB', 0, 22), ((1695, 1758), 403, '200 Hz', 0, 22), ((1622, 1650), 537, '0.2', -65, 0),
            ((1925, 1988), 447, M + '24 dB', 0, 24), ((2020, 2082), 447, '+24 dB', 0, 24)):
        dst = (x0 - 6, y - 11, x1 + 6, y + 11)
        patch_tiled(im, (dst[0] + dx, dst[1] + dy, dst[2] + dx, dst[3] + dy), dst, feather=3)
        label(im, text, ((x0 + x1) / 2, y), 21, fill='#e2e2e6', squeeze=0.92, weight='SemiBold')
    # the drawn Shelf boxes: the editor's Type pickers take their place
    patch_tiled(im, (290, 196, 388, 270), (388, 196, 604, 270), feather=5)
    patch_tiled(im, (1786, 196, 1866, 270), (1564, 196, 1784, 270), feather=5)
    # no bypass in the drawing: one under OUTPUT
    rack_bypass_small(im, 1912, 1962, 510)
    shape = Image.new('L', im.size, 0)
    ImageDraw.Draw(shape).rounded_rectangle((8, 151, 2163, 561), radius=14, fill=255)
    knobs = {'02': (415, 340), '03': (582, 340), '04': (500, 480, 0.91),
             '06': (795, 340), '07': (960, 340), '08': (880, 480, 0.91),
             '09': (1185, 340), '0a': (1357, 340), '0b': (1272, 480, 0.91),
             '0c': (1585, 340), '0d': (1757, 340), '0e': (1672, 480, 0.91), '10': (2005, 360, 1.26)}
    return dict(im=im, knobs=knobs, r=44, crop_r={'04': 40, '08': 40, '0b': 40, '0e': 40, '10': 56},
                switch=(1962, 510, 24), led=(1912, 510), shape=shape,
                controls={'sel-05': (495, 232, 180, 44), 'sel-0f': (1674, 232, 180, 44)})


def fx_loop(src, out):
    im = Image.open(src).convert('RGBA')
    # Send and Return run from -12 dB on the rack, not from silence
    for x0, x1 in ((548, 628), (1005, 1088)):
        patch_tiled(im, (x0 - 10, 492, x1 + 10, 514), (x0 - 10, 456, x1 + 10, 491), feather=4)
        label(im, '\u221212 dB', ((x0 + x1) / 2, 473), 27, fill='#e2e2e6', squeeze=0.92, weight='SemiBold')
    rack_bypass(im, 1930, 300, 385)
    shape = Image.new('L', im.size, 0)
    ImageDraw.Draw(shape).rounded_rectangle((8, 151, 2163, 561), radius=14, fill=255)
    return dict(im=im, knobs={'02': (670, 365), '03': (1130, 365), '04': (1600, 365)}, r=80,
                switch=(1930, 385, 30), led=(1930, 300), shape=shape)


def memory_man(src, out):
    im = Image.open(src).convert('RGBA')
    ink, paper = '#141414', '#e9e4da'
    # the rack's names: Blend is its Mix, Level its Input, Delay Time its Depth
    for (x0, y0, x1, y1), plain, text in (((905, 338, 1012, 380), (1010, 340, 1090, 378), 'Mix'),
                                          ((1205, 340, 1318, 382), (1330, 340, 1420, 378), 'Input'),
                                          ((1180, 866, 1352, 910), (1360, 868, 1440, 908), 'Depth')):
        patch_tiled(im, plain, (x0, y0, x1, y1), feather=6)
        label(im, text, ((x0 + x1) / 2, (y0 + y1) / 2), 34, fill=ink, squeeze=0.86)
    # the Chorus-Vibrato knob is the rack's two-way switch: no Off
    patch_tiled(im, (560, 800, 640, 846), (796, 800, 880, 846), feather=6)
    # both LEDs drawn lit: dark lenses, the editor lights them (the small one
    # by the knob shows Vibrato)
    d = ImageDraw.Draw(im)
    for (x, y), r in (((342, 128), 13), ((956, 658), 9)):
        d.ellipse((x - r - 4, y - r - 4, x + r + 4, y + r + 4), fill=im.getpixel((x + r + 12, y))[:3])
        d.ellipse((x - r, y - r, x + r, y + r), fill='#3a0806')
        d.ellipse((x - r * 0.5, y - r * 0.6, x - r * 0.05, y - r * 0.15), fill='#8a2a22')
    # what the drawing lacks, in the black field: Expanded and Noise lamps
    # (click them), and the Sync picker
    for (x, y), text in (((430, 618), 'EXPANDED'), ((600, 618), 'NOISE')):
        lamp(im, (x, y), r=11)
        label(im, text, (x, y + 42), 26, fill=paper, squeeze=0.8)
    label(im, 'SYNC', (515, 755), 26, fill=paper, squeeze=0.8)
    shape = Image.new('L', im.size, 0)
    ImageDraw.Draw(shape).rounded_rectangle((49, 52, 1476, 982), radius=30, fill=255)
    px = im.convert('RGB').load()
    for x0, x1 in ((182, 258), (496, 604), (712, 814), (928, 1028), (1170, 1304)):
        for y in range(8, 60):
            for x in range(x0, x1):
                r, g, b = px[x, y]
                if max(r, g, b) - min(r, g, b) < 0.18 * max(r, g, b, 1) or max(r, g, b) < 60:
                    shape.putpixel((x, y), 255)
    return dict(im=im, knobs={'02': (960, 250), '06': (1265, 250), '03': (965, 505), '04': (1265, 510), '07': (1270, 775)},
                r=80, switch=(258, 768, 62), led=(342, 128), shape=shape,
                sprites={'knob-tgl-08': cut_knob(im, (965, 770), 80)},
                dials={'tgl-08': dict(at=(965, 770), r=80, angles=[-63, -91], drawn=0)},
                leds={'tgl-09': (430, 618), 'tgl-0a': (600, 618), 'tgl-08': (956, 658)},
                controls={'tgl-08': (965, 770, 170, 170), 'tgl-09': (430, 640, 150, 84), 'tgl-0a': (600, 640, 120, 84),
                          'sync-select': (515, 798, 230, 46)})


def gray_comp(src, out):
    im = Image.open(src).convert('RGBA')
    # the knobs are drawn turned different ways: each cut-out is turned
    # upright here, so one spin (0) suits both
    pieces = {k: cut_knob(im, c, 158).rotate(a, resample=Image.BICUBIC) for k, c, a in (('02', (430, 312), -36), ('03', (820, 312), 71))}
    # no LED in the drawing: a small one over the footswitch
    lamp(im, (628, 800), r=12)
    shape = Image.new('L', im.size, 0)
    ImageDraw.Draw(shape).rounded_rectangle((205, 80, 1047, 1190), radius=40, fill=255)
    px = im.convert('RGB').load()
    for x0, y0, x1, y1 in ((150, 640, 206, 810), (1046, 640, 1104, 960)):
        for y in range(y0, y1):
            for x in range(x0, x1):
                if max(px[x, y]) < 236:
                    shape.putpixel((x, y), 255)
    return dict(im=im, knobs={'02': (430, 312), '03': (820, 312)}, r=158, pieces=pieces,
                switch=(628, 945, 72), led=(628, 800), shape=shape)


def blackpanel(src, out):
    im = Image.open(src).convert('RGBA')
    cream = '#ece2c6'
    # each scale has "3" twice: the upper one is the 4
    for x, y in ((648, 233), (1080, 233), (1527, 233)):
        patch_tiled(im, (x - 24, y - 84, x + 24, y - 44), (x - 24, y - 20, x + 24, y + 20), feather=4)
        label(im, '4', (x, y), 38, fill=cream, squeeze=0.95)
    # the rack calls Dwell its Decay
    patch_tiled(im, (556, 478, 646, 540), (650, 478, 862, 540), feather=6)
    label(im, 'DECAY', (755, 508), 54, fill=cream, squeeze=0.92)
    # the jewel drawn lit: dark, the editor lights it
    d = ImageDraw.Draw(im)
    x, y = 1984, 322
    d.ellipse((x - 40, y - 40, x + 40, y + 40), fill='#3c0705')
    d.ellipse((x - 30, y - 30, x + 30, y + 30), fill='#520a07')
    d.ellipse((x - 20, y - 24, x - 4, y - 10), fill='#9a3a30')
    # the knobs are drawn turned different ways: each cut-out is turned upright
    knobs = {'02': (750, 320), '04': (1184, 320), '03': (1634, 318)}
    pieces = {k: cut_knob(im, knobs[k], 102).rotate(a, resample=Image.BICUBIC) for k, a in (('02', 0), ('04', -27), ('03', 20))}
    shape = Image.new('L', im.size, 255)
    return dict(im=im, knobs=knobs, r=102, pieces=pieces, switch=(1984, 322, 52), led=(1984, 322), shape=shape)


def eleven_sr(src, out):
    im = Image.open(src).convert('RGBA')
    # the drawn Type box: the editor's Type picker takes its place
    patch_tiled(im, (370, 432, 772, 470), (370, 330, 772, 424), feather=6)
    # no bypass in the drawing: one under the Type picker
    rack_bypass_small(im, 520, 576, 478)
    # the knobs are drawn turned different ways: each cut-out is turned upright
    knobs = {'02': (950, 371), '06': (1263, 371), '03': (1577, 371), '04': (1895, 371)}
    pieces = {k: cut_knob(im, knobs[k], 88).rotate(a, resample=Image.BICUBIC) for k, a in (('02', 45), ('06', -37), ('03', 0), ('04', 54))}
    shape = Image.new('L', im.size, 0)
    ImageDraw.Draw(shape).rounded_rectangle((8, 151, 2163, 561), radius=14, fill=255)
    return dict(im=im, knobs=knobs, r=88, pieces=pieces, switch=(576, 478, 24), led=(520, 478), shape=shape,
                controls={'type-select': (573, 376, 300, 50)})


def dyn_delay(src, out):
    im = Image.open(src).convert('RGBA')
    ink, M = '#e2e2e6', '\u2212'
    # the scale ends as the rack shows them, over the brushed metal under them
    for x, w, text in ((568, 40, '4000 ms'), (801, 22, '1:2'), (899, 22, '2:1'), (1503, 44, '10 ms'), (1589, 32, '1 s'),
                       (1663, 26, M + '100 %'), (1740, 32, '+100 %'), (1819, 26, M + '100 %'), (1896, 32, '+100 %')):
        patch_tiled(im, (x - w - 6, 478, x + w + 6, 496), (x - w - 6, 446, x + w + 6, 474), feather=4)
        label(im, text, (x, 459), 22, fill=ink, squeeze=0.86, weight='Medium')
    # no EQ switch on the rack: the toggle goes, the header's line drawn on
    patch_tiled(im, (1296, 168, 1428, 204), (1296, 206, 1428, 260), feather=5)
    d = ImageDraw.Draw(im)
    d.line((1282, 234, 1372, 234), fill='#ba81d5', width=2)
    d.line((1282, 236, 1372, 236), fill='#6a488d', width=1)
    # the drawn Sync and Feedback Mode boxes: the editor's pickers take their place
    for y0, y1 in ((290, 342), (405, 456)):
        patch_tiled(im, (240, y0, 262, y1), (262, y0, 440, y1), feather=5)
    rack_bypass_small(im, 290, 346, 492)
    knobs = {k: (x, 375) for k, x in (('04', 533), ('03', 687), ('07', 850), ('08', 1000), ('0a', 1176),
                                       ('09', 1347), ('0b', 1543), ('0c', 1700), ('0d', 1856), ('02', 2040))}
    shape = Image.new('L', im.size, 0)
    ImageDraw.Draw(shape).rounded_rectangle((8, 151, 2163, 561), radius=14, fill=255)
    return dict(im=im, knobs=knobs, r=56, switch=(346, 492, 24), led=(290, 492), shape=shape,
                controls={'sync-select': (350, 316, 168, 42), 'sel-06': (350, 431, 168, 42)})


def ac30(src, out):
    im = Image.open(src).convert('RGBA')
    # chicken heads lifted off their printed dials by shape (each drawn at its
    # own angle, given here, so its wing is turned to match, and the cut-out
    # turned upright again); the shaft is the dial's centre. Tone slots in the
    # rack's default order: Speed, Depth, Normal Vol, Brill Vol, Treble, Bass, Cut
    upright = ((-6, -55), (6, -55), (12, 43), (-12, 43))
    pieces, knobs = {}, {}
    for k, x, a in (('2', 701, 38), ('3', 838, 36), ('5', 985, 34), ('4', 1120, 33), ('6', 1256, 35), ('0', 1398, 37), ('1', 1533, 28)):
        t = math.radians(a)
        wing = [(u * math.cos(t) - v * math.sin(t), u * math.sin(t) + v * math.cos(t)) for u, v in upright]
        pieces[k] = cut_wing(im, (x, 567), 60, boss=(1, -1, 33), wing=wing, panel=(98, 21, 25)).rotate(a, resample=Image.BICUBIC)
        knobs[k] = (x, 567)
    # the input jacks make way for the tremolo's Sync picker (the rack has no inputs here)
    patch_poly(im, (1062, 596, 1102, 626), [(318, 478), (510, 478), (510, 642), (318, 642)], feather=5, flat=True)
    label(im, 'SYNC', (414, 520), 26, fill='#efdcae', squeeze=0.9, weight='Bold')
    return dict(im=im, knobs=knobs, r=60, pieces=pieces, shape=Image.new('L', im.size, 255),
                toggles={'btn-trem': (573, 563, 40)},
                controls={'btn-trem': (573, 563, 50, 76), 'sync-select': (414, 572, 170, 50)})


def cab_ac212(src, out):
    im = Image.open(src).convert('RGBA')
    # the cabinet's name in the empty tolex above the cloth, as its own
    # badge would be (the editor's name plate steps aside)
    script_logo(im, 'AC Blue', (768, 190), 150, fill='#e9c374', edge='#2a1a08')
    return dict(im=im, knobs={}, r=10, shape=im.getchannel('A'), extra={'label': 'baked'})


def cab_green(watts):
    def prepare(src, out):
        im = Image.open(src).convert('RGBA')
        # the brass plate names the speaker's maker: plain brass over it, the
        # rack's cabinet name stamped in its place
        patch_poly(im, (100, 1072, 116, 1120), [(117, 1052), (220, 1052), (220, 1140), (117, 1140)], feather=3, flat=True)
        ink = '#1c1408'
        label(im, '4\u00d712', (168, 1072), 22, fill=ink, squeeze=0.95, weight='SemiBold')
        ImageDraw.Draw(im).line((140, 1086, 196, 1086), fill=ink, width=2)
        label(im, 'GREEN', (168, 1105), 19, fill=ink, squeeze=0.95, weight='Bold')
        label(im, '%d W' % watts, (168, 1127), 19, fill=ink, squeeze=0.95, weight='Bold')
        return dict(im=im, knobs={}, r=10, shape=im.getchannel('A'), extra={'label': 'baked'})
    return prepare


def tweed_bass(src, out):
    im = Image.open(src).convert('RGBA')
    cream = '#efe6d2'
    # the printed scales are garbled (two 3s, an 18, a 13): each number
    # painted out with the rusty panel and an even 0-10 set lettered where
    # the knob actually points at each value (-135 to +135 degrees)
    drawn = ((-30, 53), (-52, 30), (-59, 1), (-52, -28), (-30, -50), (1, -56), (31, -50), (53, -28), (58, 0), (53, 30), (33, 53))
    upright = ((-7, -52), (7, -52), (9, 50), (-9, 50))
    pieces, knobs = {}, {}
    for k, cx in enumerate((894, 1045, 1193, 1345, 1498, 1645)):
        cy = 566
        for dx, dy in drawn:
            x, y = cx + dx, cy + dy
            patch_poly(im, (960, 600, 990, 620), [(x - 17, y - 15), (x + 17, y - 15), (x + 17, y + 15), (x - 17, y + 15)], feather=4, flat=True)
        for i in range(11):
            a = math.radians(-135 + 27 * i)
            label(im, str(i), (cx + 60 * math.sin(a), cy - 57 * math.cos(a)), 21, fill=cream, squeeze=0.9)
        # the chicken heads stand at about 2 o'clock; lifted off by shape
        t = math.radians(60)
        wing = [(u * math.cos(t) - v * math.sin(t), u * math.sin(t) + v * math.cos(t)) for u, v in upright]
        pieces[str(k)] = cut_wing(im, (cx, cy), 62, boss=(8, 5, 36), wing=wing, panel=(62, 36, 26)).rotate(60, resample=Image.BICUBIC)
        knobs[str(k)] = (cx, cy)
    return dict(im=im, knobs=knobs, r=62, pieces=pieces, shape=Image.new('L', im.size, 255))


def tweed_lux(src, out):
    im = Image.open(src).convert('RGBA')
    cream = '#efe6d2'
    # the printed 1-12 scales are garbled (two 7s, two 2s): painted out, an
    # even 0-10 set lettered where the knob points at each value
    drawn = ((-36, 67), (-61, 37), (-71, 4), (-62, -31), (-35, -63), (-4, -71), (28, -68), (48, -58), (66, -29), (71, 4), (64, 37), (44, 66))
    upright = ((-10, -72), (10, -72), (11, 58), (-11, 58))
    pieces, knobs = {}, {}
    for k, cx in enumerate((1009, 1198, 1390)):
        cy = 516
        for dx, dy in drawn:
            x, y = cx + dx, cy + dy
            patch_poly(im, (1110, 440, 1130, 455), [(x - 19, y - 17), (x + 19, y - 17), (x + 19, y + 17), (x - 19, y + 17)], feather=4, flat=True)
        for i in range(11):
            a = math.radians(-135 + 27 * i)
            label(im, str(i), (cx + 72 * math.sin(a), cy - 68 * math.cos(a)), 25, fill=cream, squeeze=0.9)
        # the chicken heads stand at about 1 o'clock; lifted off by shape
        t = math.radians(36)
        wing = [(u * math.cos(t) - v * math.sin(t), u * math.sin(t) + v * math.cos(t)) for u, v in upright]
        pieces[str(k)] = cut_wing(im, (cx, cy), 76, boss=(1, 9, 42), wing=wing, panel=(58, 36, 26)).rotate(36, resample=Image.BICUBIC)
        knobs[str(k)] = (cx, cy)
    return dict(im=im, knobs=knobs, r=74, pieces=pieces, shape=Image.new('L', im.size, 255))


def fender_skirt(im, centre, r_in=19, r_out=36.5, ring=27, size=13):
    # a skirted knob's own numbers turn with it and are read at the panel's
    # index notch above it: the garbled ones painted out with the skirt's own
    # shading (a low percentile round the same circle), 0-10 lettered on so
    # each value stands under the notch when the knob points at it, i.e.
    # counting up anticlockwise, the drawing being at noon (5)
    import statistics
    cx, cy = centre
    src = im.copy().load()
    px = im.load()
    for y in range(round(cy - r_out), round(cy + r_out) + 1):
        for x in range(round(cx - r_out), round(cx + r_out) + 1):
            d = math.hypot(x - cx, y - cy)
            if not r_in <= d <= r_out:
                continue
            a0 = math.atan2(y - cy, x - cx)
            ring_px = [src[round(cx + d * math.cos(a0 + math.radians(k * 3))), round(cy + d * math.sin(a0 + math.radians(k * 3)))] for k in range(-10, 11)]
            ring_px.sort(key=lambda p: p[0] + p[1] + p[2])
            p = ring_px[len(ring_px) // 4]
            w = min(1, (d - r_in) / 1.5, (r_out - d) / 1.5)
            q = px[x, y]
            px[x, y] = tuple(round(q[i] + (p[i] - q[i]) * w) for i in range(3)) + (255,)
    f = ImageFont.truetype(os.path.join(HERE, '..', '..', 'src', 'fonts', 'Manrope.ttf'), size)
    f.set_variation_by_name('Bold')
    for v in range(11):
        phi = 135 - 27 * v                     # clockwise from the top, in the drawing
        l, t, r, b = f.getbbox(str(v))
        t_im = Image.new('RGBA', (r - l + 6, b - t + 6), (0, 0, 0, 0))
        ImageDraw.Draw(t_im).text((3 - l, 3 - t), str(v), font=f, fill='#ece4d0')
        if v == 10:
            t_im = t_im.resize((round(t_im.width * 0.8), t_im.height), Image.LANCZOS)
        t_im = t_im.rotate(-phi, resample=Image.BICUBIC, expand=True)
        a = math.radians(phi)
        x, y = cx + ring * math.sin(a), cy - ring * math.cos(a)
        im.alpha_composite(t_im, (round(x - t_im.width / 2), round(y - t_im.height / 2)))


def lux(channel):
    def prepare(src, out):
        im0 = Image.open(src).convert('RGBA')
        # a combo cut down to a head: the cabinet's top with the panel and a
        # strip of grille, then its bottom rail and feet
        top, bot = im0.crop((0, 0, 1402, 362)), im0.crop((0, 1000, 1402, 1110))
        im = Image.new('RGBA', (1402, 340 + 110))
        im.paste(bot, (0, 340))
        m = Image.new('L', (1402, 362), 255)
        ImageDraw.Draw(m).rectangle((0, 352, 1402, 362), fill=0)
        im.paste(top, (0, 0), m.filter(ImageFilter.GaussianBlur(4)))
        flat = (1040, 222, 1060, 250)              # plain panel
        # the maker's script and line make way for the rack's name
        patch_poly(im, flat, [(1058, 142), (1272, 142), (1272, 254), (1058, 254)], feather=4)
        script_logo(im, 'Lux', (1150, 170), 50, fill='#ece3cf', edge='#0c0c0c')
        script_logo(im, 'Vibrato' if channel == 'vib' else 'Normal', (1180, 210), 46, fill='#ece3cf', edge='#0c0c0c')
        label(im, "'64 HAND-WIRED", (1180, 241), 15, fill='#e6ddc8', squeeze=0.9, weight='Bold')
        # the second channel is the vibrato one on the real amp
        patch_poly(im, flat, [(450, 220), (525, 220), (525, 248), (450, 248)], feather=3)
        label(im, 'VIBRATO', (488, 233), 20, fill='#e6ddc8', squeeze=0.86, weight='SemiBold')
        # no reverb in the rack's amp: its knob makes way for the vibrato's Sync picker
        patch_poly(im, flat, [(800, 150), (884, 150), (884, 252), (800, 252)], feather=4)
        label(im, 'SYNC', (842, 241), 15, fill='#e6ddc8', squeeze=0.86, weight='Bold')
        for c in ((217.7, 187.6), (296.7, 187.6), (376.6, 187.6), (581.5, 187.9), (660.8, 187.7), (740.2, 187.7),
                  (921.6, 188.0), (1001.7, 187.8)):
            fender_skirt(im, c)
        # tone slots in the rack's order: Volume, Treble, Bass on this
        # look's channel, Speed, Intensity
        vtb = ((581.5, 187.9), (660.8, 187.7), (740.2, 187.7)) if channel == 'vib' else ((217.7, 187.6), (296.7, 187.6), (376.6, 187.6))
        knobs = {str(i): c for i, c in enumerate(vtb + ((921.6, 188.0), (1001.7, 187.8)))}
        # the panel's index notch reaches into the skirt's top: it stays put
        pieces = {}
        for k, c in knobs.items():
            pieces[k] = cut_knob(im, c, 37)
            a = pieces[k].getchannel('A')
            ImageDraw.Draw(a).rectangle((pieces[k].width / 2 - 4, 0, pieces[k].width / 2 + 4, 7), fill=0)
            pieces[k].putalpha(a)
        # the black round the cabinet goes
        cand = im.convert('L').point(lambda v: 255 if v <= 4 else 0)
        for seed in ((0, 0), (1401, 0), (0, im.height - 1), (1401, im.height - 1), (700, 0), (700, im.height - 1)):
            if cand.getpixel(seed) == 255:
                ImageDraw.floodfill(cand, seed, 128)
        shape = cand.point(lambda v: 0 if v == 128 else 255).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
        return dict(im=im, knobs=knobs, r=37, pieces=pieces, shape=shape, controls={'sync-select': (842, 190, 92, 38)})
    return prepare


def cab_tweed(name, plate, size):
    def prepare(src, out):
        im = Image.open(src).convert('RGBA')
        # the blank brass plate carries the cabinet's name
        script_logo(im, name, plate, size, fill='#f0dcae', edge='#2a1608')
        return dict(im=im, knobs={}, r=10, shape=im.getchannel('A'), extra={'label': 'baked'})
    return prepare


def cab_1960(lines):
    def prepare(src, out):
        im = Image.open(src).convert('RGBA')
        # the plate's maker and speaker lines: plain brass, the rack's speakers in their place
        patch_poly(im, (104, 1062, 116, 1110), [(117, 1094), (214, 1094), (214, 1137), (117, 1137)], feather=3, flat=True)
        for y, (text, size) in zip((1114,) if len(lines) == 1 else (1104, 1126), lines):
            label(im, text, (166, y), size, fill='#1c1408', squeeze=0.95, weight='Bold')
        return dict(im=im, knobs={}, r=10, shape=im.getchannel('A'), extra={'label': 'baked'})
    return prepare


IMAGES = {
    # 760 CSS px wide head; its knobs point at about 7 o'clock in the picture
    'plexi-vari': dict(prepare=plexi('Plexi Vari'), width=760, spin=-147),
    'plexi-50': dict(prepare=plexi('Plexi 50W'), width=760, spin=-147),
    'plexi-100': dict(prepare=plexi('Plexi 100W'), width=760, spin=-147),
    # 720 CSS px wide; the knobs are drawn at 5, straight up
    'ep-3': dict(prepare=ep3, width=720, spin=0),
    # 330 CSS px wide; knobs drawn pointing straight up
    'green-jrc': dict(prepare=green_jrc, width=330, spin=0),
    # 760 CSS px wide head; its knobs point at about 1 o'clock
    'jtm45': dict(prepare=jtm45, width=760, spin=28),
    # 300 CSS px wide; knobs drawn pointing straight up
    'white-boost': dict(prepare=white_boost, width=300, spin=0),
    # 760 CSS px wide head; its knobs point at about 1 o'clock
    'lead800': dict(prepare=lead800, width=760, spin=28),
    # 330 CSS px wide; knobs drawn pointing straight up
    'tri-fuzz': dict(prepare=tri_fuzz, width=330, spin=0),
    # 320 CSS px wide; knobs drawn pointing straight up
    'dc-dist': dict(prepare=dc_dist, width=320, spin=0),
    # 440 CSS px wide; no knobs to turn
    'fv-vol': dict(prepare=fv_vol, width=440, spin=0),
    'shine-wah': dict(prepare=shine_wah, width=440, spin=0),
    'black-wah': dict(prepare=black_wah, width=440, spin=0),
    # 640 CSS px wide; the chicken heads point straight up (at 5)
    'uni-vibe': dict(prepare=vibe, width=640, spin=0),
    # 640 CSS px wide; its pointers stand at about 1 o'clock
    'ce-1': dict(prepare=ce1, width=640, spin=30),
    # 300 CSS px wide; the pointer stands at about 1 o'clock
    'orange-phaser': dict(prepare=orange_phaser, width=300, spin=29),
    # 300 CSS px wide; the pointers stand at about 1 o'clock
    'flanger': dict(prepare=flanger, width=300, spin=25),
    # 330 CSS px wide; faders, no knobs
    'graphic-eq': dict(prepare=graphic_eq, width=330, spin=0),
    # 480 CSS px wide; the knobs are drawn pointing straight up
    'multi-chorus': dict(prepare=multi_chorus, width=480, spin=0),
    # 640 CSS px wide; the Balance knob is drawn pointing straight up
    'roto': dict(prepare=roto, width=640, spin=0),
    # 760 CSS px wide rack panel; the knobs are drawn pointing straight up
    'dyn3': dict(prepare=dyn3, width=760, spin=0),
    'param-eq': dict(prepare=param_eq, width=760, spin=0),
    'fx-loop': dict(prepare=fx_loop, width=760, spin=0),
    # 600 CSS px wide; the knobs are drawn pointing straight up
    'memory-man': dict(prepare=memory_man, width=600, spin=0),
    # 330 CSS px wide; its cut-out knobs are turned upright
    'gray-comp': dict(prepare=gray_comp, width=330, spin=0),
    # 760 CSS px wide amp panel; its cut-out knobs are turned upright
    'blackpanel': dict(prepare=blackpanel, width=760, spin=0),
    'eleven-sr': dict(prepare=eleven_sr, width=760, spin=0),
    'dyn-delay': dict(prepare=dyn_delay, width=760, spin=0),
    # 760 CSS px wide head; its cut-out chicken heads are turned upright
    'ac30': dict(prepare=ac30, width=760, spin=0),
    # 760 CSS px wide cabinet front, its name lettered on
    'cab-ac212': dict(prepare=cab_ac212, width=760, spin=0),
    # 760 CSS px wide head; its cut-out chicken heads are turned upright
    'tweed-bass': dict(prepare=tweed_bass, width=760, spin=0),
    'tweed-lux': dict(prepare=tweed_lux, width=760, spin=0),
    # the Deluxe Reverb cut down to a head, its Vibrato or Normal channel live;
    # its skirted knobs are drawn at noon
    'lux-vib': dict(prepare=lux('vib'), width=760, spin=0),
    'lux-norm': dict(prepare=lux('norm'), width=760, spin=0),
    # the same 4x12, its plate stamped for the 25 W or the 20 W speakers
    'cab-green25': dict(prepare=cab_green(25), width=760, spin=0),
    'cab-green20': dict(prepare=cab_green(20), width=760, spin=0),
    'cab-tweed410': dict(prepare=cab_tweed('Tweed Bass', (629, 94), 46), width=760, spin=0),
    # the same 1960 4x12 with 65 W speakers, or with Classic 30s
    'cab-1960': dict(prepare=cab_1960([('65 W', 22)]), width=760, spin=0),
    'cab-1960c30': dict(prepare=cab_1960([('CLASSIC', 18), ('30', 18)]), width=760, spin=0),
    'cab-tweed112': dict(prepare=cab_tweed('Tweed Lux', (708, 102), 42), width=760, spin=0),
}


def main(dev, src, out):
    os.makedirs(out, exist_ok=True)
    spec = IMAGES[dev]
    rec = spec['prepare'](src, out)
    im, knobs, r = rec['im'], rec['knobs'], rec['r']
    for k, (x, y, h) in rec.get('toggles', {}).items():
        # a bat toggle's ON picture: its square round the nut, upside down
        t = im.crop((x - h, y - h, x + h, y + h)).transpose(Image.FLIP_TOP_BOTTOM)
        m = Image.new('L', t.size, 0)
        ImageDraw.Draw(m).ellipse((2, 2, t.width - 2, t.height - 2), fill=255)
        t.putalpha(m.filter(ImageFilter.GaussianBlur(2)))
        t.save(os.path.join(out, '%s-tog-%s.png' % (dev, k)))
    for k, c in knobs.items():
        # a smaller copy turns its full-size twin's cut-out, scaled down by the editor
        if k in rec.get('pieces', {}):
            rec['pieces'][k].save(os.path.join(out, '%s-knob-%s.png' % (dev, k)))
            continue
        cut_knob(im, knobs[rec.get('crop_from', {}).get(k, k)][:2], rec.get('crop_r', {}).get(k, r)).save(os.path.join(out, '%s-knob-%s.png' % (dev, k)))
    if 'shape' in rec:
        body = im.copy()
        body.putalpha(rec['shape'])
        ox, oy, _, _ = box = rec['shape'].getbbox()
        body = body.crop(box)
    else:
        body, (ox, oy, _, _) = clear_background(im, sat_max=rec.get('sat_max', 0.14), lum_min=rec.get('lum_min', 150), warm=rec.get('warm', False))
    for name, sp in rec.get('sprites', {}).items():
        sp.save(os.path.join(out, '%s-%s.png' % (dev, name)))
    body.save(os.path.join(out, dev + '-body.png'))
    s = spec['width'] / body.width
    at = lambda x, y: [round((x - ox) * s, 1), round((y - oy) * s, 1)]
    img_h = round(body.height * s)
    pad = rec.get('pad_bottom', 0)
    meta = {'width': spec['width'], 'height': img_h + pad, 'img_h': img_h, 'spin': spec['spin'],
            'knob': round((2 * r + 4) * s, 1),
            'knobs': {k: at(*c[:2]) + [c[2] if len(c) > 2 else 1] for k, c in knobs.items()}}
    if 'switch' in rec:
        meta['switch'] = at(*rec['switch'][:2]) + [round(rec['switch'][2] * s, 1)]
    if 'led' in rec:
        meta['led'] = at(*rec['led'])
    meta['toggles'] = {k: at(x, y) + [round(2 * h * s, 1)] for k, (x, y, h) in rec.get('toggles', {}).items()}
    meta['leds'] = {k: at(*c) for k, c in rec.get('leds', {}).items()}
    # faders: the track's minimum and maximum ends, the carriage sprite's size and name
    meta['sliders'] = {k: at(*a) + at(*b) + [round(size * s, 1), name] for k, (a, b, name, size) in rec.get('sliders', {}).items()}
    meta['sprites'] = sorted(rec.get('sprites', {}))
    # a picker drawn as a knob: its centre and size, the angle of each option, the angle it was drawn at
    meta['dials'] = {k: at(*v['at']) + [round((2 * v['r'] + 4) * s, 1), v['angles'], v['drawn']] for k, v in rec.get('dials', {}).items()}
    meta['controls'] = {k: at(*v[:2]) + [round(v[2] * s), round(v[3] * s)] + list(v[4:5]) for k, v in rec.get('controls', {}).items()}
    # controls and bars in the strip under the picture, given in CSS px (y from the strip's top)
    for k, (x, y, w, h, *style) in rec.get('css_controls', {}).items():
        meta['controls'][k] = [x, img_h + y - 220, w, h] + style
    meta['bars'] = {k: [spec['width'] / 2, img_h + y - 220 + 20, spec['width'] - 120, 14, lab] for k, (y, lab) in rec.get('bars', {}).items()}
    meta.update(rec.get('extra', {}))
    with open(os.path.join(out, dev + '-image.json'), 'w') as f:
        json.dump(meta, f, indent=1)


if __name__ == '__main__':
    main(*sys.argv[1:4])
