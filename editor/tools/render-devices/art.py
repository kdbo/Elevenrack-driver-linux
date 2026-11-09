# Draw a device's printed artwork (decals) with PIL, before Blender runs.
#
#   python3 art.py <device> <outdir>
#
# Writes <outdir>/<decal>.png for each decal in devices.DEVICES[device],
# at 160 px per cm, white (or the ink colour) on transparent.

import math, os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import devices  # noqa: E402

PPC = 160
FONT = os.path.join(HERE, '..', '..', 'src', 'fonts', 'Manrope.ttf')


SERIF = '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf'
SCRIPT = os.path.join(HERE, '..', '..', 'src', 'fonts', 'Damion.ttf')


def font(size_cm, weight='SemiBold'):
    if weight in ('serif', 'serif-italic', 'script'):
        return ImageFont.truetype(SCRIPT if weight == 'script' else SERIF, max(1, round(size_cm * PPC)))
    f = ImageFont.truetype(FONT, max(1, round(size_cm * PPC)))
    f.set_variation_by_name(weight)
    return f


class Decal:
    def __init__(self, w, h, cx, cy):
        self.w, self.h, self.cx, self.cy = w, h, cx, cy
        self.im = Image.new('RGBA', (round(w * PPC), round(h * PPC)), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def px(self, x, y):
        # device cm -> decal pixels
        return ((x - self.cx + self.w / 2) * PPC, (self.cy + self.h / 2 - y) * PPC)

    def dots(self, x, y, r, ink, n=11, size=0.055):
        for i in range(n):
            a = math.radians(225 - 270 * i / (n - 1))
            px, py = self.px(x + math.cos(a) * r, y + math.sin(a) * r)
            s = size * PPC
            self.d.ellipse((px - s, py - s, px + s, py + s), fill=ink)

    def line(self, x0, y0, x1, y1, ink, width=0.06):
        self.d.line((*self.px(x0, y0), *self.px(x1, y1)), fill=ink, width=round(width * PPC))

    def arc(self, x, y, r, a0, a1, ink, width=0.06):
        # angles in degrees, counter-clockwise from +x as on the device
        (l, t), (rr, b) = self.px(x - r, y + r), self.px(x + r, y - r)
        self.d.arc((l, t, rr, b), -a1, -a0, fill=ink, width=round(width * PPC))

    def ray(self, x, y, a, r0, r1, ink, width=0.06):
        a = math.radians(a)
        self.line(x + math.cos(a) * r0, y + math.sin(a) * r0, x + math.cos(a) * r1, y + math.sin(a) * r1, ink, width)

    def dot(self, x, y, r, ink):
        px, py = self.px(x, y)
        self.d.ellipse((px - r * PPC, py - r * PPC, px + r * PPC, py + r * PPC), fill=ink)

    def panel(self, x0, y0, x1, y1, ink, radius=0.0, outline=None, width=0.06, corners=(True, True, True, True)):
        a, b = self.px(x0, y1), self.px(x1, y0)
        kw = dict(radius=round(radius * PPC), corners=corners)
        if outline:
            self.d.rounded_rectangle((a[0], a[1], b[0], b[1]), outline=outline, width=round(width * PPC), **kw)
        else:
            self.d.rounded_rectangle((a[0], a[1], b[0], b[1]), fill=ink, **kw)

    def clear_circle(self, x, y, r):
        m = Image.new('L', self.im.size, 255)
        px, py = self.px(x, y)
        ImageDraw.Draw(m).ellipse((px - r * PPC, py - r * PPC, px + r * PPC, py + r * PPC), fill=0)
        a = self.im.getchannel('A')
        self.im.putalpha(Image.composite(a, Image.new('L', self.im.size, 0), m))

    def clip(self, pts):
        # keep only what lies inside an outline (device cm)
        m = Image.new('L', self.im.size, 0)
        ImageDraw.Draw(m).polygon([self.px(x, y) for x, y in pts], fill=255)
        a = self.im.getchannel('A')
        self.im.putalpha(Image.composite(a, Image.new('L', self.im.size, 0), m))

    def block_text(self, x, y, s, size, ink, depth=0.08, weight='ExtraBold', stretch=1.15):
        # outlined capitals with a solid extrusion down-right; the faces stay
        # clear so the metal shows through
        f = font(size, weight)
        l, t, r, b = f.getbbox(s)
        pad = round(depth * PPC) + 12
        w, h = r - l + pad * 2, b - t + pad * 2
        ext = Image.new('RGBA', (w, h), (0, 0, 0, 0)); de = ImageDraw.Draw(ext)
        sw = max(2, round(0.035 * PPC))
        for i in range(round(depth * PPC), 0, -1):
            de.text((pad - l + i, pad - t + i), s, font=f, fill=ink, stroke_width=sw, stroke_fill=ink)
        de.text((pad - l, pad - t), s, font=f, fill=ink, stroke_width=sw, stroke_fill=ink)
        face = Image.new('L', (w, h), 0)
        ImageDraw.Draw(face).text((pad - l, pad - t), s, font=f, fill=255)
        a = ext.getchannel('A')
        ext.putalpha(Image.composite(Image.new('L', (w, h), 0), a, face))
        ext = ext.resize((w, round(h * stretch)), Image.LANCZOS)
        px, py = self.px(x, y)
        self.im.alpha_composite(ext, (round(px - ext.width / 2), round(py - ext.height / 2)))

    def text(self, x, y, s, size, ink, weight='SemiBold', squeeze=1.0, rotate=0, bg=None, spacing=0.0):
        f = font(size, weight)
        l, t, r, b = f.getbbox(s)
        sp = round(spacing * PPC)
        tw, th = r - l + sp * max(0, len(s) - 1), b - t
        pad = 6
        t_im = Image.new('RGBA', (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
        if sp:
            cx = pad - l
            for ch in s:
                ImageDraw.Draw(t_im).text((cx, pad - t), ch, font=f, fill=ink)
                cx += f.getlength(ch) + sp
        else:
            ImageDraw.Draw(t_im).text((pad - l, pad - t), s, font=f, fill=ink)
        if weight == 'serif-italic':
            # no italic face to hand: slant the upright one
            k = 0.22
            h = t_im.height
            t_im = t_im.transform((t_im.width + round(h * k), h), Image.AFFINE, (1, k, -k * h, 0, 1, 0), resample=Image.BICUBIC)
        if squeeze != 1.0:
            t_im = t_im.resize((max(1, round(t_im.width * squeeze)), t_im.height), Image.LANCZOS)
        if rotate:
            t_im = t_im.rotate(rotate, expand=True, resample=Image.BICUBIC)
        px, py = self.px(x, y)
        if bg:
            # knock a gap in a printed line behind the text
            m = 0.08 * PPC
            self.d.rectangle((px - t_im.width / 2 - m, py - t_im.height / 2 - m, px + t_im.width / 2 + m, py + t_im.height / 2 + m), fill=(0, 0, 0, 0))
        self.im.alpha_composite(t_im, (round(px - t_im.width / 2), round(py - t_im.height / 2)))

    def rect(self, x0, y0, x1, y1, ink, width=0.06):
        a, b = self.px(x0, y1), self.px(x1, y0)
        self.d.rectangle((a[0], a[1], b[0], b[1]), outline=ink, width=round(width * PPC))

    def save(self, path):
        self.im.save(path)


def green_jrc(out):
    ink = devices.INK
    dec = devices.DEVICES['green-jrc']['decals']
    w, h, cx, cy, _ = dec['upper']
    u = Decal(w, h, cx, cy)
    for x, y in devices.DEVICES['green-jrc']['knobs'].values():
        u.dots(x, y, 1.22, ink)
    u.text(-1.95, 2.88, 'OVERDRIVE', 0.36, ink, weight='Medium', squeeze=0.88)
    u.text(1.95, 2.88, 'LEVEL', 0.36, ink, weight='Medium', squeeze=0.88)
    u.text(0.0, 4.2, 'TONE', 0.36, ink, weight='Medium', squeeze=0.88)
    u.save(os.path.join(out, 'upper.png'))

    w, h, cx, cy, _ = dec['lower']
    lo = Decal(w, h, cx, cy)
    lo.rect(-3.3, -5.95, 3.3, 0.7, ink)
    lo.text(0.0, -0.45, 'GREEN JRC', 1.15, ink, weight='SemiBold', squeeze=0.66)
    lo.text(0.0, -1.35, 'Overdrive', 0.4, ink, weight='SemiBold')
    lo.text(-3.3, -1.0, 'OUTPUT', 0.32, ink, weight='Medium', rotate=-90, bg=True)
    lo.text(3.3, -1.0, 'INPUT', 0.32, ink, weight='Medium', rotate=-90, bg=True)
    lo.save(os.path.join(out, 'lower.png'))


def deck(dev):
    w, h, cx, cy, _ = devices.DEVICES[dev]['decals']['top']
    return Decal(w, h, cx, cy)


def black_op(out):
    ink = '#dcdee1'
    d = deck('black-op')
    d.rect(-3.95, 3.55, 3.95, 4.55, ink, width=0.07)
    for x in (-1.32, 1.32):
        d.line(x, 3.55, x, 4.55, ink, width=0.07)
    for x, s in ((-2.63, 'DISTORTION'), (0, 'CUT'), (2.63, 'VOLUME')):
        d.text(x, 4.05, s, 0.34, ink, weight='Bold', squeeze=0.92)
    for x, y in devices.DEVICES['black-op']['knobs'].values():
        d.arc(x, y, 0.98, -45, 225, ink, width=0.065)
        for i in range(7):
            a = 225 - 270 * i / 6
            if i in (0, 6):
                d.ray(x, y, a, 0.95, 1.18, ink, width=0.065)
            else:
                d.ray(x, y, a, 0.8, 0.98, ink, width=0.065)
    d.rect(-3.0, -2.4, 3.0, -0.8, ink, width=0.11)
    d.text(0, -1.6, 'BLACK OP', 0.98, '#f6f6f6', weight='ExtraBold')
    d.save(os.path.join(out, 'top.png'))


def white_boost(out):
    ink = '#1e1e20'
    d = deck('white-boost')
    # frame down the sides and round the bottom, open at the top
    r = 0.45
    d.line(-2.42, 2.55, -2.42, -4.75 + r, ink)
    d.line(2.42, 2.55, 2.42, -4.75 + r, ink)
    d.line(-2.42 + r, -4.75, 2.42 - r, -4.75, ink)
    d.arc(-2.42 + r, -4.75 + r, r, 180, 270, ink)
    d.arc(2.42 - r, -4.75 + r, r, 270, 360, ink)
    k = devices.DEVICES['white-boost']['knobs']
    for lo, s in (('02', 'GAIN'), ('03', 'TREBLE'), ('05', 'VOLUME'), ('04', 'BASS')):
        x, y = k[lo]
        d.text(x, y - 1.02, s, 0.3, ink, weight='ExtraBold', squeeze=0.86)
    d.text(0, -0.8, 'WHITE', 0.98, ink, weight='serif')
    d.text(0.35, -1.55, '-booster', 0.44, ink, weight='serif-italic')
    d.text(-2.42, 0.6, 'OUTPUT', 0.27, ink, weight='Bold', rotate=-90, bg=True)
    d.text(2.42, 0.6, 'INPUT', 0.27, ink, weight='Bold', rotate=-90, bg=True)
    d.save(os.path.join(out, 'top.png'))


def dc_dist(out):
    ink = '#2a1206'
    d = deck('dc-dist')
    o = devices.DC_OUTLINE
    d.panel(-3.4, 5.35, 3.4, 6.2, '#4a1c0c')                     # dark brown rim round the top
    d.clip(rounded_pts(o, inset=0.18))
    k = devices.DEVICES['dc-dist']['knobs']
    for lo, s in (('05', 'LEVEL'), ('03', 'TREBLE'), ('04', 'BASS')):
        x, y = k[lo][:2]
        d.text(x, y - 0.9, s, 0.26, ink, weight='serif', spacing=0.02)
    d.text(0, 1.85, 'DC', 0.62, '#3a1404', weight='serif-italic')
    d.text(0, -1.25, 'DISTORTION', 0.32, ink, weight='serif', spacing=0.05)
    a = math.radians(225)
    d.dot(math.cos(a) * 1.18, 0.3 + math.sin(a) * 1.18, 0.07, '#f6f2ea')
    d.save(os.path.join(out, 'top.png'))


def rounded_pts(o, inset=0.0, n=10):
    pts = []
    def corner(cx, cy, r, a0):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + (r - inset) * math.cos(a), cy + (r - inset) * math.sin(a)))
    wt, wb, y0, y1, rt, rb = o['w_top'], o['w_bot'], o['y0'], o['y1'], o['r_top'], o['r_bot']
    corner(wb / 2 - rb, y0 + rb, rb, -90)
    corner(wt / 2 - rt, y1 - rt, rt, 0)
    corner(-wt / 2 + rt, y1 - rt, rt, 90)
    corner(-wb / 2 + rb, y0 + rb, rb, 180)
    return pts


def tri_fuzz(out):
    ink, red = '#141414', '#d23a26'
    d = deck('tri-fuzz')
    d.panel(-4.15, 1.75, 4.15, 5.05, None, radius=0.85, outline=ink, width=0.09, corners=(True, True, False, False))
    d.text(-3.05, 4.6, 'AMPLIFIER', 0.32, ink, weight='ExtraBold')
    d.text(3.05, 4.6, 'INPUT', 0.32, ink, weight='ExtraBold')
    for x, s in ((-3.05, 'VOLUME'), (0, 'TONE'), (3.05, 'SUSTAIN')):
        d.text(x, 2.05, s, 0.34, ink, weight='ExtraBold')
    # the black lower panel with a half-round bay, the lower red rule round it
    d.panel(-4.15, -5.0, 4.15, -0.55, '#0f0f10', radius=0.7, corners=(False, False, True, True))
    d.clear_circle(0, -0.2, 1.62)
    d.line(-4.15, 1.3, 4.15, 1.3, red, width=0.12)
    d.block_text(0, 0.55, 'TRI-KNOB', 1.05, red)
    d.line(-4.15, -0.2, -1.36, -0.2, red, width=0.12)
    d.line(1.36, -0.2, 4.15, -0.2, red, width=0.12)
    d.arc(0, -0.2, 1.36, 180, 360, red, width=0.12)
    d.text(0, -0.85, 'Fuzz', 0.8, red, weight='script')
    d.save(os.path.join(out, 'top.png'))


def plexi(out):
    ink = '#1a1206'
    w, h, cx, cy, _ = devices.DEVICES['plexi']['decals']['panel']
    p = Decal(w, h, cx, cy)
    for (x, y), lab in zip(devices.PLEXI_KNOBS, ('PRESENCE', 'BASS', 'MIDDLE', 'TREBLE', 'VOLUME I', 'VOLUME II')):
        p.text(x, -1.4, lab, 0.2, ink, weight='ExtraBold')
        for i in range(0, 11, 2):
            a = math.radians(225 - 27 * i)
            p.text(x + math.cos(a) * 0.66, y + math.sin(a) * 0.66, str(i), 0.15, ink, weight='Bold')
        for i in range(11):
            p.ray(x, y, 225 - 27 * i, 0.5, 0.56, ink, width=0.018)
    for x, a in ((-5.75, 'MAINS'), (-4.75, 'STANDBY')):
        p.text(x, -1.4, a, 0.18, ink, weight='ExtraBold')
        p.text(x, -3.0, 'ON', 0.16, ink, weight='ExtraBold')
    p.text(-3.75, -3.0, 'INDICATOR', 0.16, ink, weight='ExtraBold')
    p.text(-6.65, -2.25, '100W', 0.2, ink, weight='ExtraBold')
    p.text(5.8, -2.27, 'INPUTS', 0.18, ink, weight='ExtraBold')
    p.text(6.95, -1.8, 'I', 0.18, ink, weight='serif')
    p.text(6.95, -2.75, 'II', 0.18, ink, weight='serif')
    p.save(os.path.join(out, 'panel.png'))

def wah_plate(text, ink, weight):
    # the name plate on a wah's toe end: dark, rimmed, the name in the middle
    def draw(out):
        d = Decal(7.0, 3.0, 0, 0)
        d.panel(-3.5, -1.5, 3.5, 1.5, '#121214', radius=0.25)
        d.panel(-3.5, -1.5, 3.5, 1.5, None, radius=0.25, outline='#5a5a5e', width=0.06)
        d.text(0, 0.05, text, 1.45, ink, weight=weight)
        d.save(os.path.join(out, 'plate.png'))
    return draw


def ce_1(out):
    ink, orange = '#16161a', '#e0621c'
    w, h, cx, cy, _ = devices.DEVICES['ce-1']['decals']['plate']
    d = Decal(w, h, cx, cy)
    k = devices.DEVICES['ce-1']['knobs']
    # black rings with white dot scales: one round Chorus, a joined pair round Depth / Rate
    for lo in ('02', '03', '04'):
        x, y = k[lo]
        d.dot(x, y, 0.9, ink)
    d.panel(k['03'][0], k['03'][1] - 0.18, k['04'][0], k['03'][1] + 0.18, ink)
    for lo in ('02', '03', '04'):
        x, y = k[lo]
        d.dots(x, y, 0.76, '#f2f2f2', size=0.035)
    d.text(k['02'][0], 3.95, 'chorus', 0.32, ink, weight='Bold')
    d.text(k['02'][0], 3.62, 'intensity', 0.24, ink, weight='SemiBold')
    d.text((k['03'][0] + k['04'][0]) / 2, 3.95, 'vibrato', 0.32, ink, weight='Bold')
    d.text(k['03'][0], 3.62, 'depth', 0.24, ink, weight='SemiBold')
    d.text(k['04'][0], 3.62, 'rate', 0.24, ink, weight='SemiBold')
    d.line(k['03'][0] + 0.45, 3.8, k['04'][0] - 0.45, 3.8, ink, width=0.03)
    d.text(-4.4, 3.35, 'sync', 0.3, ink, weight='Bold')
    d.text(-4.4, 2.2, 'tempo', 0.22, ink, weight='SemiBold')
    d.block_text(-2.65, 1.0, 'C1', 0.7, ink, depth=0.0, stretch=1.0)     # outlined capitals, open faces
    d.text(1.35, 1.0, 'Chorus Vibrato', 0.62, orange, weight='Bold')
    d.text(6.05, 0.95, 'power', 0.22, '#f2f2f2', weight='SemiBold')
    d.save(os.path.join(out, 'plate.png'))
    w, h, cx, cy, _ = devices.DEVICES['ce-1']['decals']['lower']
    lo = Decal(w, h, cx, cy)
    for x, lab in ((-4.6, 'effect on / off'), (4.6, 'chorus / vibrato')):
        lo.text(x, -1.62, lab, 0.28, ink, weight='Bold')
    lo.save(os.path.join(out, 'lower.png'))


def uni_vibe(out):
    ink = '#ecebe6'
    w, h, cx, cy, _ = devices.DEVICES['uni-vibe']['decals']['plate']
    d = Decal(w, h, cx, cy)
    # white frame with notched corners, and a band for the name
    x0, x1, y0, y1, n = -6.75, 6.75, -4.05, 4.25, 0.35
    for a, b in (((x0 + n, y1), (x1 - n, y1)), ((x0 + n, y0), (x1 - n, y0)), ((x0, y0 + n), (x0, y1 - n)), ((x1, y0 + n), (x1, y1 - n))):
        d.line(*a, *b, ink, width=0.04)
    for cx_, cy_, a0 in ((x0, y1, 270), (x1, y1, 180), (x0, y0, 0), (x1, y0, 90)):
        d.arc(cx_, cy_, n, a0, a0 + 90, ink, width=0.04)
    d.text(0, 3.45, 'Vibe Phaser', 1.25, ink, weight='script')
    k = devices.DEVICES['uni-vibe']['knobs']
    for lo, lab in (('04', 'VOLUME'), ('03', 'INTENSITY'), ('02', 'SPEED')):
        x, y = k[lo]
        d.arc(x, y, 0.92, -45, 225, ink, width=0.035)
        d.arc(x, y, 0.72, -45, 225, ink, width=0.025)
        for i, num in enumerate(('1', '3', '5', '7', '9')):
            a = 225 - 270 * (i + 0.5) / 5
            d.ray(x, y, a, 0.72, 0.92, ink, width=0.025)
            d.text(x + math.cos(math.radians(a)) * 1.12, y + math.sin(math.radians(a)) * 1.12, num, 0.22, ink, weight='Bold')
        d.text(x - 0.75, y - 0.92, 'MIN.', 0.17, ink, weight='Bold')
        d.text(x + 0.75, y - 0.92, 'MAX.', 0.17, ink, weight='Bold')
        d.text(x, y - 1.3, lab, 0.32, ink, weight='Bold', squeeze=0.8)
    d.line(-2.5, 0.7, -2.5, 0.15, ink, width=0.03); d.line(-2.5, 0.15, -2.75, 0.15, ink, width=0.03)
    d.line(-1.5, 0.7, -1.5, 0.15, ink, width=0.03); d.line(-1.5, 0.15, -1.25, 0.15, ink, width=0.03)
    d.text(-3.3, 0.15, 'CHORUS', 0.3, ink, weight='Bold', squeeze=0.8)
    d.text(-0.6, 0.15, 'VIBRATO', 0.3, ink, weight='Bold', squeeze=0.8)
    for x in (-5.5, -3.9, -1.1):          # a printed ring round each jack
        d.dot(x, -2.2, 0.62, ink)
        d.clear_circle(x, -2.2, 0.58)
    d.text(-5.65, -2.95, '1', 0.2, ink, weight='Bold'); d.text(-3.75, -2.95, '2', 0.2, ink, weight='Bold')
    d.text(-4.7, -3.3, 'INSTRUMENTS', 0.3, ink, weight='Bold', squeeze=0.8)
    d.text(-1.1, -3.3, 'OUTPUT', 0.3, ink, weight='Bold', squeeze=0.8)
    d.text(2.4, -1.55, 'SYNC', 0.3, ink, weight='Bold', squeeze=0.8)
    d.text(6.0, -1.2, 'ON', 0.28, ink, weight='Bold', squeeze=0.8)
    d.text(6.0, -3.2, 'POWER SW.', 0.28, ink, weight='Bold', squeeze=0.8)
    d.save(os.path.join(out, 'plate.png'))


def orange_phaser(out):
    ink = '#141414'
    d = deck('orange-phaser')
    d.text(0, 1.95, 'SPEED', 0.34, ink, weight='SemiBold')
    d.text(0, 1.5, 'sync', 0.26, ink, weight='SemiBold')
    d.text(-2.35, 0.9, 'OUTPUT', 0.3, ink, weight='SemiBold', rotate=-90)
    d.text(2.35, 0.9, 'INPUT', 0.3, ink, weight='SemiBold', rotate=-90)
    d.text(0, -4.3, 'Orange Phaser', 0.62, ink, weight='script')
    d.save(os.path.join(out, 'top.png'))


def gray_comp(out):
    ink = '#18181a'
    d = deck('gray-comp')
    d.text(-1.8, 4.35, 'OUT', 0.32, ink, weight='ExtraBold')
    d.text(1.8, 4.35, 'IN', 0.32, ink, weight='ExtraBold')
    d.text(-1.65, 0.75, 'LEVEL', 0.38, ink, weight='ExtraBold')
    d.text(1.65, 0.75, 'SUSTAIN', 0.38, ink, weight='ExtraBold')
    d.text(0, -1.3, 'Gray', 1.3, ink, weight='serif')
    d.text(0, -4.3, 'COMPRESSOR', 0.6, ink, weight='ExtraBold')
    d.save(os.path.join(out, 'top.png'))


def ep_3(out):
    ink = '#1a1a1c'
    dv = devices.DEVICES['ep-3']['decals']
    w, h, cx, cy, _ = dv['band']
    b = Decal(w, h, cx, cy)
    (x0, _), (x1, _), _ = devices.DEVICES['ep-3']['sliders']['04']
    for i in range(31):
        x = x0 + (x1 - x0) * i / 30
        b.line(x, -0.98, x, -0.88 if i % 5 else -0.8, ink, width=0.025)
        if i % 5 == 0:
            b.text(x, -1.12, str(i), 0.17, ink, weight='Bold')
    b.text(2.2, -1.32, 'ECHO DELAY', 0.14, ink, weight='Bold', spacing=0.02)
    b.save(os.path.join(out, 'band.png'))
    w, h, cx, cy, _ = dv['badge']
    g = Decal(w, h, cx, cy)
    g.text(2.2, 3.05, 'Tape Echo', 0.62, ink, weight='script')
    g.save(os.path.join(out, 'badge.png'))
    k = devices.DEVICES['ep-3']['knobs']
    w, h, cx, cy, _ = dv['bay']
    by = Decal(w, h, cx, cy)
    for lo, lab in (('06', 'REC. LEVEL'), ('03', 'REPEATS'), ('02', 'ECHO VOL.')):
        x, y = k[lo][:2]
        by.dots(x, y, 0.72, ink, size=0.028)
        by.text(x, y - 0.98, lab, 0.2, ink, weight='Bold')
    by.text(-6.35, 0.05, 'SYNC', 0.18, ink, weight='Bold')
    by.text(-6.35, 5.0, 'ECHO', 0.22, ink, weight='Bold', spacing=0.05)
    by.save(os.path.join(out, 'bay.png'))
    w, h, cx, cy, _ = dv['strip']
    st = Decal(w, h, cx, cy)
    st.text(-7.4, -2.15, 'ECHO', 0.2, ink, weight='Bold')
    st.text(-7.4, -4.85, 'ON / OFF', 0.2, ink, weight='Bold')
    for lo, lab in (('08', 'HEAD TILT'), ('07', 'WOW & FLUTTER')):
        x, y = k[lo][:2]
        st.dots(x, y, 0.72 * k[lo][2], ink, size=0.028)
        st.text(x, -4.75, lab, 0.18, ink, weight='Bold')
    st.text(-2.0, -4.75, 'EXPANDED', 0.18, ink, weight='Bold')
    st.text(-0.6, -4.75, 'TAPE HISS', 0.18, ink, weight='Bold')
    st.text(1.6, -4.75, 'INPUT', 0.2, ink, weight='Bold')
    st.text(3.0, -4.75, 'OUTPUT', 0.2, ink, weight='Bold')
    st.text(6.2, -3.65, 'Tape Echo', 0.6, ink, weight='script')
    st.save(os.path.join(out, 'strip.png'))

def roto(out):
    ink = '#2a1d06'
    w, h, cx, cy, _ = devices.DEVICES['roto']['decals']['plate']
    d = Decal(w, h, cx, cy)
    d.dots(-3.3, 0.3, 0.68, ink, size=0.03)
    d.text(-3.3, -0.55, 'BALANCE', 0.2, ink, weight='Bold')
    d.text(-2.05, 0.65, 'SPEED', 0.2, ink, weight='Bold')
    d.text(-2.05, -0.15, 'TYPE', 0.2, ink, weight='Bold')
    d.text(3.6, 1.15, 'PILOT', 0.18, ink, weight='Bold')
    d.text(3.6, -0.85, 'ON / OFF', 0.18, ink, weight='Bold')
    d.text(1.85, 0.25, 'Roto', 0.6, ink, weight='script')
    d.save(os.path.join(out, 'plate.png'))


def blackpanel(out):
    ink = '#ecebe6'
    w, h, cx, cy, _ = devices.DEVICES['blackpanel']['decals']['panel']
    d = Decal(w, h, cx, cy)
    for (x, y), lab in zip(devices.DEVICES['blackpanel']['knobs'].values(), ('DWELL', 'TONE', 'MIX')):
        d.text(x, y - 0.95, lab, 0.22, ink, weight='Bold', spacing=0.02)
        px, py = d.px(x, y + 0.72)               # the reading mark above each knob
        s_ = 0.07 * PPC
        d.d.polygon([(px - s_, py - s_), (px + s_, py - s_), (px, py + s_)], fill=ink)
    d.text(2.3, 0.85, 'Spring Reverb', 0.95, ink, weight='script')
    d.text(2.3, -0.3, 'BLACKPANEL', 0.2, ink, weight='Bold', spacing=0.06)
    d.save(os.path.join(out, 'panel.png'))
    # the skirt's numbers (the knob's turning layer): 1 at the top at the
    # knob's lowest setting, 10 at the top at its highest
    n = Decal(1.3, 1.3, 0, 0)
    for i in range(10):
        a = math.radians(135 - 30 * i)
        n.text(math.sin(a) * 0.52, math.cos(a) * 0.52, str(i + 1), 0.13, ink, weight='Bold')
    n.save(os.path.join(out, 'numbers.png'))


def memory_man(out):
    ink, red, white = '#141416', '#d8301e', '#ecebe6'
    d = deck('memory-man')
    # the black diagonal field over the lower left
    d.d.polygon([d.px(-6.0, 2.3), d.px(2.6, -5.1), d.px(-6.0, -5.1)], fill='#121214')
    k = devices.DEVICES['memory-man']['knobs']
    for lo, lab in (('06', 'Level'), ('02', 'Blend'), ('03', 'Feedback'), ('04', 'Delay'), ('07', 'Chorus-Vibrato')):
        x, y = k[lo]
        d.arc(x, y, 1.0, -45, 225, red, width=0.035)
        for i in range(11):
            d.ray(x, y, 225 - 27 * i, 1.0, 1.15 if i % 5 else 1.22, red, width=0.03)
        d.text(x, y - 1.25, lab, 0.26, white if lo == '07' else ink, weight='SemiBold')
    d.text(-4.6, 4.2, 'Power', 0.24, red, weight='SemiBold')
    d.text(-2.2, 4.2, 'Sync', 0.24, ink, weight='SemiBold')
    for x, lab in ((-2.4, 'Echo Out'), (-0.4, 'Direct Out'), (1.6, 'Input')):
        d.text(x, 4.75, lab, 0.22, ink, weight='SemiBold')
    d.text(4.4, 5.0, 'Chorus-Vibrato', 0.22, ink, weight='SemiBold')
    d.text(-2.9, -3.9, 'Expanded', 0.2, white, weight='SemiBold')
    d.text(-1.3, -3.9, 'Noise', 0.2, white, weight='SemiBold')
    d.text(-4.0, 0.05, 'Echo / Chorus / Vibrato', 0.4, red, weight='Bold', rotate=-41)   # along the diagonal
    d.block_text(-2.55, 1.85, 'BBD', 1.0, ink, depth=0.0, weight='Medium', stretch=1.0)
    d.block_text(-2.05, 0.8, 'DELAY', 0.75, ink, depth=0.0, weight='Medium', stretch=1.0)
    d.save(os.path.join(out, 'top.png'))


def rack_deck(dev):
    w, h, cx, cy, _ = devices.DEVICES[dev]['decals']['panel']
    return Decal(w, h, cx, cy)


def knob_labels(d, dev, labels, ink, dy=0.95, size=0.22, dots=True):
    k = devices.DEVICES[dev]['knobs']
    for lo, lab in labels.items():
        x, y = k[lo][:2]
        sc = k[lo][2] if len(k[lo]) > 2 else 1
        if dots:
            d.dots(x, y, 0.72 * sc, ink, size=0.028)
        d.text(x, y + dy * sc, lab, size, ink, weight='Bold', spacing=0.015)


def dyn3(out):
    ink, blue = '#e8eaee', '#4aa8ff'
    d = rack_deck('dyn3')
    knob_labels(d, 'dyn3', {'02': 'THRESHOLD', '03': 'ATTACK', '04': 'RELEASE', '05': 'RATIO', '06': 'KNEE', '07': 'GAIN'}, ink)
    d.text(-6.1, 2.55, 'Dyn3', 0.5, ink, weight='ExtraBold')
    d.text(-3.15, 2.5, 'COMPRESSOR / LIMITER', 0.24, ink, weight='SemiBold', spacing=0.03)
    d.line(-7.2, 2.0, 7.2, 2.0, blue, width=0.04)
    d.text(6.2, -0.75, 'BYPASS', 0.2, ink, weight='Bold')
    d.save(os.path.join(out, 'panel.png'))


def param_eq(out):
    ink = '#1a1a1c'
    d = rack_deck('param-eq')
    k = devices.DEVICES['param-eq']['knobs']
    bands = (('02', '03', '04', '#e83828', 'LOW'), ('06', '07', '08', '#e0a020', 'LOW MID'),
             ('09', '0a', '0b', '#30c050', 'HIGH MID'), ('0c', '0d', '0e', '#3f8fe0', 'HIGH'))
    for g, f, q, col, name in bands:
        x = k[g][0]
        d.text(x, 2.6, name, 0.24, ink, weight='ExtraBold', spacing=0.03)
        for lo, lab in ((g, 'GAIN'), (f, 'FREQ'), (q, 'Q')):
            y = k[lo][1]
            d.dot(x, y, 0.66, col)
            d.clear_circle(x, y, 0.58)
            d.text(x + 0.95, y, lab, 0.17, ink, weight='Bold')
    for x in (k['02'][0], k['0c'][0]):
        d.text(x, -2.35, 'TYPE', 0.17, ink, weight='Bold')
    knob_labels(d, 'param-eq', {'10': 'OUTPUT'}, ink)
    d.text(5.4, 1.15, 'IN', 0.2, ink, weight='Bold')
    d.text(5.4, -2.5, 'PARAMETRIC EQ', 0.24, ink, weight='ExtraBold', spacing=0.03)
    d.save(os.path.join(out, 'panel.png'))


def dyn_delay(out):
    ink = '#e8eaee'
    d = rack_deck('dyn-delay')
    knob_labels(d, 'dyn-delay', {'04': 'DELAY', '03': 'FEEDBACK', '07': 'L/R RATIO', '08': 'WIDTH', '0a': 'LOW CUT', '09': 'HIGH CUT',
                                 '0b': 'RATE', '0c': 'FBK', '0d': 'MIX', '02': 'MIX'}, ink, dy=-0.95)
    for x0, x1, y0, y1, cap in ((-3.0, -0.2, 0.05, 2.75, 'DELAY'), (0.2, 3.0, 0.05, 2.75, 'EQ'), (3.3, 6.1, -2.75, 2.75, 'ENV MOD')):
        d.rect(x0, y0, x1, y1, ink, width=0.03)
        d.text((x0 + x1) / 2, y1, ' ' + cap + ' ', 0.2, ink, weight='Bold', bg=True)
    d.text(-5.9, -0.85, 'SYNC', 0.18, ink, weight='Bold')
    d.text(-3.0, -1.0, 'FEEDBACK MODE', 0.18, ink, weight='Bold')
    d.text(1.7, -1.55, 'Dyn Delay', 0.42, ink, weight='ExtraBold')
    d.text(6.4, -2.4, 'BYPASS', 0.18, ink, weight='Bold')
    d.save(os.path.join(out, 'panel.png'))


def eleven_sr(out):
    ink = '#e6ecf6'
    d = rack_deck('eleven-sr')
    knob_labels(d, 'eleven-sr', {'02': 'DECAY', '06': 'PRE-DELAY', '03': 'TONE', '04': 'MIX', '05': 'TYPE'}, ink)
    d.text(-1.0, 2.65, 'Eleven SR', 0.46, ink, weight='ExtraBold')
    d.text(2.3, 2.6, 'STUDIO REVERB', 0.22, ink, weight='SemiBold', spacing=0.05)
    d.text(6.0, -0.65, 'BYPASS', 0.2, ink, weight='Bold')
    d.save(os.path.join(out, 'panel.png'))


def fx_loop(out):
    ink = '#e8eaee'
    d = rack_deck('fx-loop')
    knob_labels(d, 'fx-loop', {'02': 'SEND', '03': 'RETURN', '04': 'MIX'}, ink)
    d.text(-6.0, 0.05, 'FX LOOP', 0.36, ink, weight='ExtraBold')
    d.text(2.6, -0.75, 'SEND', 0.18, ink, weight='Bold')
    d.text(4.0, -0.75, 'RETURN', 0.18, ink, weight='Bold')
    d.text(6.0, -0.75, 'BYPASS', 0.18, ink, weight='Bold')
    d.save(os.path.join(out, 'panel.png'))


def multi_chorus(out):
    ink = '#eef3fb'
    d = deck('multi-chorus')
    knob_labels(d, 'multi-chorus', {'02': 'RATE', '04': 'DEPTH', '06': 'PRE DELAY', '05': 'MIX', '08': 'LOW CUT', '09': 'WIDTH'}, ink, dy=1.05, size=0.26)
    d.text(1.45, 1.3, 'VOICES', 0.24, ink, weight='Bold')
    d.text(4.3, 1.3, 'TRI    SINE', 0.22, ink, weight='Bold')
    d.text(1.0, -1.1, 'Multi Chorus', 0.8, ink, weight='ExtraBold')
    # Sync belongs to Rate: a printed line from the Rate knob down to its field
    for a, b in (((-5.2, 3.6), (-5.75, 3.6)), ((-5.75, 3.6), (-5.75, -1.35)), ((-5.75, -1.35), (-5.55, -1.35))):
        d.line(*a, *b, ink, width=0.035)
    d.text(-4.4, -0.85, 'SYNC', 0.24, ink, weight='Bold')
    d.save(os.path.join(out, 'top.png'))


def flanger(out):
    ink = '#f3eefb'
    d = deck('flanger')
    knob_labels(d, 'flanger', {'02': 'RATE', '03': 'DEPTH', '05': 'PRE-DELAY', '04': 'FEEDBACK'}, ink, dy=-1.05, size=0.26)
    d.text(0, -1.65, 'Flanger', 1.1, ink, weight='script')
    d.save(os.path.join(out, 'top.png'))


def graphic_eq(out):
    ink = '#1a1a1c'
    d = deck('graphic-eq')
    y0, y1 = devices.GEQ_Y
    for x, lab in zip(devices.GEQ_X, ('100', '370', '800', '2k', '3.25k', 'OUT')):
        d.text(x, y1 + 0.65, lab, 0.22, ink, weight='Bold')
        for t in range(9):
            y = y0 + (y1 - y0) * t / 8
            d.line(x - 0.42, y, x - 0.24, y, ink, width=0.025 if t % 4 else 0.04)
    for y, lab in ((y1, '+'), ((y0 + y1) / 2, '0'), (y0, '−')):
        d.text(-3.55, y, lab, 0.26, ink, weight='Bold')
    d.text(0, -1.85, 'GRAPHIC EQ', 0.62, ink, weight='ExtraBold', spacing=0.03)
    d.save(os.path.join(out, 'top.png'))


ART = {'cab-412': lambda out: None, 'dyn3': dyn3, 'param-eq': param_eq, 'dyn-delay': dyn_delay, 'eleven-sr': eleven_sr, 'fx-loop': fx_loop,
       'multi-chorus': multi_chorus, 'flanger': flanger, 'graphic-eq': graphic_eq, 'memory-man': memory_man, 'blackpanel': blackpanel, 'roto': roto, 'ep-3': ep_3, 'gray-comp': gray_comp, 'orange-phaser': orange_phaser, 'uni-vibe': uni_vibe, 'ce-1': ce_1, 'shine-wah': wah_plate('Shine', '#d8dadd', 'serif'), 'black-wah': wah_plate('black', '#f4f4f4', 'ExtraBold'), 'plexi': plexi, 'green-jrc': green_jrc, 'black-op': black_op, 'white-boost': white_boost, 'dc-dist': dc_dist, 'tri-fuzz': tri_fuzz}

if __name__ == '__main__':
    dev, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    ART[dev](out)
